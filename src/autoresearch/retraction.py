"""M05-06 retraction / correction facts and access-basis facts (K10).

This module owns exactly two determinations:

1. **Is this work retracted, corrected, or still active?** Projected from B5's
   Crossref verdict. The criterion -- Crossref's ``updated-by[]`` array -- is
   read in exactly one place, ``external_sources.CrossrefAdapter._from_live``;
   this module consumes the resulting verdict and never re-reads the relation
   arrays (K10-3: reuse, do not rewrite).
2. **What access basis does the record state?** Read from Crossref
   ``license[]`` via ``CrossrefAdapter.licence``. That is a fact about the
   source, not a policy: who may read, export or delete a resource is K11 /
   L-09's ``licensing.py``.

K10-1 is the load-bearing invariant: ``UNAVAILABLE`` is never ``ACTIVE``. A
transport failure, a missing record, a permission denial and an unmapped
upstream status all project to ``UNAVAILABLE``; only an explicit ``found``
verdict from B5 becomes ``ACTIVE``. "We could not retrieve it" and "we
confirmed it is not retracted" are different conclusions and are never
collapsed into one.

The projection is coarse on purpose -- K10 is a frozen four-value enum -- so
``not_found`` and ``unknown`` both land on ``UNAVAILABLE``. The underlying
facts are *not* merged: they stay recoverable from
:attr:`RetractionCheck.source_status` and ``reasons``. The projection layer may
merge; the audit layer may not.

``ACTIVE`` does not imply the work is reachable today. When a live lookup fails
and an offline snapshot supplies a ``found`` verdict, the status is still
``ACTIVE`` -- with ``transport_degraded`` set. That is the only path in this
module that turns a degraded lookup into a normal-looking value, and it sits on
the seam between here and B5, where a consumer is most likely to miss it:
**callers that need a fresh confirmation must check
:attr:`RetractionCheck.transport_degraded`; reading ``ACTIVE`` alone is not
enough.**

K10-2 (``RETRACTED`` must propagate) is enforced structurally rather than by
convention: ``check()`` cannot return a retracted status without having called
an :class:`InvalidationSink`, and it refuses outright when no sink is wired -- a
status that says "propagated" while nothing propagated is the same defect family
as K10-1.

Who derives the blast radius is **K8's decision, not this module's**. K8-2 makes
the evidence -> claim -> gate walk the K8 owner's job, because only the graph
knows those relations. :class:`K8InvalidationAdapter` therefore does not pass a
caller-supplied claim set through as *input*; when one is supplied it is treated
as an *assertion* and cross-checked against what K8's plan derived. An earlier
revision of this module required the caller to produce ``affected_claims`` and
rejected an empty set -- that was wrong on two counts: it made the caller invent
facts about a graph it cannot see, and it duplicated K8-3's guard away from its
owner.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, replace
from enum import StrEnum
from types import ModuleType
from typing import Protocol, runtime_checkable

from autoresearch.external_sources import (
    AccessStatus,
    CrossrefAdapter,
    DoiVerdict,
    LicenceVerdict,
    SourceStatus,
    TransportOutcome,
)


class RetractionStatus(StrEnum):
    """K10 (frozen). The retraction/correction axis of a work's status."""

    ACTIVE = "active"
    RETRACTED = "retracted"
    CORRECTED = "corrected"
    UNAVAILABLE = "unavailable"


# K10-1 stated as data: only an explicit B5 ``found`` has an ``ACTIVE`` image.
# ``not_found`` maps to ``UNAVAILABLE`` rather than ``ACTIVE`` on purpose -- a
# DOI that does not resolve is not a work we confirmed to be fine. The finer
# distinction between "does not exist" and "could not be retrieved" survives in
# ``RetractionCheck.source_status`` and ``reasons``; it is not erased, only
# projected onto the four frozen K10 values.
SOURCE_STATUS_TO_RETRACTION: dict[SourceStatus, RetractionStatus] = {
    SourceStatus.FOUND: RetractionStatus.ACTIVE,
    SourceStatus.RETRACTED: RetractionStatus.RETRACTED,
    SourceStatus.CORRECTED: RetractionStatus.CORRECTED,
    SourceStatus.NOT_FOUND: RetractionStatus.UNAVAILABLE,
    SourceStatus.UNKNOWN: RetractionStatus.UNAVAILABLE,
}

# K8 invariant 1: these reasons cannot be waived, so their action is fixed.
# Kept as data (not as a branch inside the caller) so the mapping is checkable
# without exercising a transport.
_ACTION_BY_REASON: dict[str, str] = {
    "retracted": "recompute",
    "expired": "recompute",
    "forged": "permanent_block",
    "paywall_bypass": "permanent_block",
    "unapproved_egress": "permanent_block",
}

PERMANENT_BLOCK_REASONS = frozenset(
    {"forged", "paywall_bypass", "unapproved_egress"}
)

# The full reason domain K8 freezes (``04-l2-contracts.md`` K8). Exposed so a
# cross-module consistency check can compare *both* directions: a table that is a
# subset of K8's would otherwise be indistinguishable from one that matches.
K8_REASONS = frozenset(_ACTION_BY_REASON)


class UnmappedSourceStatusError(ValueError):
    """A B5 status with no K10 projection. Raised instead of guessing."""


class UnmappedPropagationReasonError(ValueError):
    """A propagation reason outside K8's frozen set. Raised instead of guessing."""


class PropagationContractMismatchError(ValueError):
    """This module and K8 disagree about a propagation's contents.

    Raised instead of dropping the disagreement: two implementations of one
    concept that are never compared are the defect (D2).
    """


class K8UnavailableError(RuntimeError):
    """The K8 seam cannot be used: the module is absent, or the service has no plan()."""


class PropagationRequiredError(RuntimeError):
    """A retraction could not be propagated. Raised instead of reporting success."""


class PaywallBypassRefused(PermissionError):
    """Retrieval was asked to circumvent an access basis. It will not."""


def retraction_status_for(source_status: SourceStatus) -> RetractionStatus:
    """Project a B5 status onto K10.

    Raises :class:`UnmappedSourceStatusError` for an unknown member: a status
    K10 cannot express must fail loudly rather than default to "fine".
    """

    try:
        return SOURCE_STATUS_TO_RETRACTION[source_status]
    except KeyError as exc:
        raise UnmappedSourceStatusError(
            f"no K10 projection for source status {source_status!r}; refusing to guess "
            "(an unknown status must never read as active)"
        ) from exc


def k8_action_for(reason: str) -> str:
    """K8 action for a propagation reason. Unmapped reasons raise."""

    try:
        return _ACTION_BY_REASON[reason]
    except KeyError as exc:
        raise UnmappedPropagationReasonError(
            f"{reason!r} is not a K8 propagation reason"
        ) from exc


@dataclass(frozen=True)
class RetractionCheck:
    """The K10 verdict for one work, with the B5 evidence it came from."""

    doi: str
    status: RetractionStatus
    source_status: SourceStatus
    transport: TransportOutcome
    reasons: tuple[str, ...] = ()
    related_dois: tuple[str, ...] = ()
    propagation: object | None = None

    @property
    def confirmed_active(self) -> bool:
        """True only for an explicit ``found`` verdict. ``UNAVAILABLE`` is False."""

        return self.status is RetractionStatus.ACTIVE

    @property
    def needs_propagation(self) -> bool:
        return self.status is RetractionStatus.RETRACTED

    @property
    def transport_degraded(self) -> bool:
        """The live lookup did not succeed; a snapshot supplied the verdict.

        The verdict is still what the snapshot says, but it is not a fresh
        confirmation. Callers that require freshness must check this.
        """

        return self.transport is not TransportOutcome.OK


@dataclass(frozen=True)
class PropagationContext:
    """What a K8 propagation needs from this module's caller.

    Only ``source_evidence_id`` is required. ``affected_claims`` and
    ``affected_gates`` are **optional**, and when supplied they are an
    *assertion of completeness* rather than the propagation input: K8-2 makes the
    evidence -> claim -> gate walk the K8 owner's job because only the graph
    knows those relations, so this module does not pretend to know them. Leaving
    both empty is the normal case, and an empty set is **not** an error here --
    K8-3 is enforced by K8's owner, at the point where the walk actually happens.
    """

    source_evidence_id: str
    affected_claims: tuple[str, ...] = ()
    affected_gates: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalDecision:
    """Whether the source's own licence permits an unrestricted retrieval."""

    doi: str
    access: AccessStatus
    granted: bool
    basis: str
    reasons: tuple[str, ...] = ()


@runtime_checkable
class InvalidationSink(Protocol):
    """Port to the K8 ``InvalidationPropagation`` owner (L-02, ``invalidation.py``).

    **This port is satisfied by :class:`K8InvalidationAdapter`, not by the K8
    service itself.** ``InvalidationService.propagate`` takes
    ``(source_evidence_id, reason, actor)`` and derives the blast radius from the
    graph, whereas this port additionally carries the caller's assertions and the
    K8-1 action. Wiring a raw service therefore raises ``TypeError`` on the first
    call. Always wrap: ``sink=K8InvalidationAdapter(service)``.

    ``implements_retraction_sink`` is not decoration: ``runtime_checkable``
    verifies member *names*, not signatures, and a raw service does have a method
    called ``propagate``. Without a discriminator ``isinstance`` would return
    ``True`` for an object that cannot serve as a sink at all -- a green light on
    a trap. It also lets a test double (or a future K8 owner) declare conformance
    to *this* call shape explicitly instead of being guessed at by name.
    """

    #: Discriminator: declared by implementations of this call shape.
    implements_retraction_sink: bool

    def propagate(
        self,
        *,
        source_evidence_id: str,
        reason: str,
        affected_claims: tuple[str, ...],
        affected_gates: tuple[str, ...],
        action: str,
    ) -> object: ...


# L-02's exclusive file. Absent from this lane's base (``main@8dd8780``), so the
# import is lazy -- a module-level one would make this module unimportable there.
K8_MODULE = "autoresearch.invalidation"


def _k8_module() -> ModuleType:
    """Import L-02's K8 module on demand.

    The dependency is real either way; laziness only moves the failure to the
    point of use and gives it a name, instead of breaking every import of this
    module on a base where L-02 has not landed.
    """

    try:
        return importlib.import_module(K8_MODULE)
    except ImportError as exc:
        raise K8UnavailableError(
            f"{K8_MODULE} is required to propagate an invalidation (K8 owner is L-02): {exc}"
        ) from exc


class K8InvalidationAdapter:
    """Adapts this module's port onto L-02's K8 ``InvalidationService``.

    The two sides disagreed about who derives the blast radius (D1). K8-2 says a
    propagation walks *from the invalidated source to the claims that depend on
    it*, and only the graph knows that relation -- so L-02 derives it and L-04
    does not. This adapter therefore passes through only what K8's owner needs
    (``source_evidence_id`` + ``reason``) and does **not** forward a
    caller-supplied claim set as input.

    What it does instead is compare, so the same concept is never implemented
    twice without being checked:

    * ``action`` must equal ``action_for_reason(reason)``. A disagreement means
      one of the two K8-1 tables is stale -- raises, never silently dropped.
    * an asserted ``affected_claims`` must equal the set the plan derives. An
      assertion is a claim of completeness, so a mismatch is a real broken
      chain, and it raises.
    * ``affected_gates`` likewise.

    **The comparison happens on a plan, before anything is written.** The adapter
    drives K8's two-step API -- ``plan()`` (derive, no side effects) then
    ``record(plan)`` -- and cross-checks the object ``plan()`` returned. Because
    ``record`` persists *that same object*, "refused" means "nothing was written"
    **by construction**, not by ordering: there is no window between the check
    and the write. An earlier revision validated after ``propagate()`` had
    already returned, which reports the error while the fact stands (D-M05-09);
    reading ``service.graph`` directly fixed the ordering but reached into K8's
    internals. ``plan``/``record`` removes both problems.

    That "by construction" rests on one precondition this module **cannot verify
    from the outside**: ``plan()`` must be side-effect free. What is checked here
    is only the observable part -- the returned object's blast radius -- and a
    shape mismatch fails loudly (``AttributeError`` on the attributes read
    below), never silently. Do not read this adapter as *proving* K8's purity;
    that property belongs to K8's owner and its tests.
    """

    def __init__(self, service: object) -> None:
        #: Declares conformance to InvalidationSink's call shape (see the port's
        #: docstring: names are not enough for ``runtime_checkable``).
        self.implements_retraction_sink = True
        self.service = service

    def _plan(self, source_evidence_id: str, reason: object) -> object:
        plan = getattr(self.service, "plan", None)
        if plan is None:
            raise K8UnavailableError(
                "the wired K8 service exposes no plan(); a pre-write cross-check "
                "cannot be performed without the two-step plan/record API, and "
                "verifying after the fact has already been persisted is not an "
                "acceptable substitute"
            )
        return plan(source_evidence_id=source_evidence_id, reason=reason)

    def propagate(
        self,
        *,
        source_evidence_id: str,
        reason: str,
        affected_claims: tuple[str, ...] = (),
        affected_gates: tuple[str, ...] = (),
        action: str,
    ) -> object:
        k8 = _k8_module()
        try:
            k8_reason = k8.InvalidationReason(reason)
        except ValueError as exc:
            raise UnmappedPropagationReasonError(
                f"{reason!r} is not a K8 propagation reason"
            ) from exc

        action_value = getattr(action, "value", action)
        expected = k8.action_for_reason(k8_reason)
        if action_value != expected.value:
            raise PropagationContractMismatchError(
                f"action disagreement for reason={reason!r}: this module computed "
                f"{action_value!r}, K8 computes {expected.value!r} -- one of the two "
                "K8-1 tables is stale (D2)"
            )

        plan = self._plan(source_evidence_id, k8_reason)
        _cross_check("affected_claims", affected_claims, plan.affected_claims)
        _cross_check("affected_gates", affected_gates, plan.affected_gates)
        # ``record`` persists this exact object, so the checks above cover the
        # persisted fact with no window in between -- no after-the-fact backstop
        # is needed or wanted.
        return self.service.record(plan)


def _cross_check(field: str, asserted: tuple[str, ...], derived: list[str]) -> None:
    """Compare a caller assertion with what K8's plan derived.

    No assertion means no claim to check -- the K8 owner's derivation stands on
    its own (and K8-3 guards it there). An assertion that disagrees with the plan
    is a broken chain, and is reported rather than absorbed.
    """

    if not asserted:
        return
    if sorted(asserted) != sorted(derived):
        raise PropagationContractMismatchError(
            f"{field} disagreement: the caller asserted {sorted(asserted)}, K8's plan "
            f"derived {sorted(derived)} -- an assertion claims completeness, so a "
            "mismatch is a broken propagation chain, not a rounding difference"
        )


def check_from_verdict(verdict: DoiVerdict) -> RetractionCheck:
    """Project a B5 :class:`DoiVerdict` onto K10, keeping the evidence."""

    return RetractionCheck(
        doi=verdict.doi,
        status=retraction_status_for(verdict.status),
        source_status=verdict.status,
        transport=verdict.transport,
        reasons=tuple(verdict.reasons),
        related_dois=tuple(verdict.related_dois),
    )


class RetractionChecker:
    """The M05-06 entry point: classify a work, and propagate a retraction."""

    def __init__(
        self, *, adapter: CrossrefAdapter, sink: InvalidationSink | None = None
    ):
        if sink is not None and not isinstance(sink, InvalidationSink):
            # Fail at wiring time, with the fix in the message. Without this the
            # mistake surfaces as ``TypeError: ... unexpected keyword argument
            # 'affected_claims'`` from inside the first propagation, which names
            # the service rather than the wiring. The common cause is passing
            # ``invalidation.InvalidationService`` directly -- see the port's
            # docstring: it does not implement this call shape.
            raise PropagationRequiredError(
                f"{type(sink).__name__} does not implement the InvalidationSink call "
                "shape; wrap it: sink=K8InvalidationAdapter(service)"
            )
        self.adapter = adapter
        self.sink = sink

    def classify(self, doi: str) -> RetractionCheck:
        """Determine the K10 status. Never raises for an unreachable source."""

        try:
            verdict = self.adapter.resolve(doi)
        except Exception as exc:  # noqa: BLE001 - the whole point is to not guess
            # An exception carries no verdict, so it is projected exactly like a
            # transport failure -- through the same mapping, so that "we could
            # not tell" has one decision point instead of two.
            return RetractionCheck(
                doi=doi,
                status=retraction_status_for(SourceStatus.UNKNOWN),
                source_status=SourceStatus.UNKNOWN,
                transport=TransportOutcome.UNAVAILABLE,
                reasons=(f"resolver raised {type(exc).__name__}: {str(exc)[:160]}",),
            )
        return check_from_verdict(verdict)

    def check(self, doi: str, *, context: PropagationContext) -> RetractionCheck:
        """Classify, and propagate to K8 when the work is retracted.

        A retracted work cannot be returned without a propagation: a missing
        sink raises rather than yielding a status that claims a propagation
        which never happened (K10-2). The claim/gate blast radius is *not*
        validated here -- deriving it is the K8 owner's job (K8-2), so an empty
        claim set is the normal case and is not an error at this seam; K8-3's
        empty-set guard lives where the evidence -> claim -> gate walk actually
        happens.

        **Not retry-safe.** Calling this twice for the same work emits two K8
        propagations: ``plan()`` mints a fresh ``propagation_id`` per call, so
        K8's ``record()`` idempotency (which is keyed on that id) does not
        collapse them. Measured: two calls -> two ``invalidation_propagation``
        records and two ``invalidation.propagated`` audit events. K8's frozen
        contract carries no idempotency key, so the retry semantics are
        unspecified rather than decided -- see D-M05-10 in the lane L3. Do not
        paper over this at the call site; it needs an owner ruling.
        """

        result = self.classify(doi)
        if not result.needs_propagation:
            return result
        receipt = self.propagate("retracted", context)
        return replace(result, propagation=receipt)

    def propagate(self, reason: str, context: PropagationContext) -> object:
        """Emit one K8 propagation. Raises when it cannot be emitted.

        The claim/gate blast radius is **not** checked here: deriving it is the
        K8 owner's job (K8-2), and K8-3's empty-set guard belongs there too. This
        method only refuses to claim a propagation it did not perform.
        """

        action = k8_action_for(reason)
        if self.sink is None:
            raise PropagationRequiredError(
                f"{reason} requires K8 propagation but no invalidation sink is wired; "
                "refusing to report a status whose propagation did not happen"
            )
        if not context.source_evidence_id:
            raise PropagationRequiredError(
                "source_evidence_id is required to address a K8 propagation"
            )
        return self.sink.propagate(
            source_evidence_id=context.source_evidence_id,
            reason=reason,
            affected_claims=context.affected_claims,
            affected_gates=context.affected_gates,
            action=action,
        )

    def access_basis(self, doi: str) -> LicenceVerdict:
        """The access basis the record states (fact only, no policy)."""

        return self.adapter.licence(doi)

    def decide_retrieval(
        self,
        doi: str,
        *,
        bypass_paywall: bool = False,
        context: PropagationContext | None = None,
    ) -> RetrievalDecision:
        """Decide whether the stated licence permits an unrestricted retrieval.

        This answers "what does the source permit", never "is this caller
        entitled" -- the latter is K11 / L-09.

        Requesting a bypass is refused for every work, including an open one:
        circumventing an access basis is not a retrieval mode. When the caller
        supplies a propagation context the attempt is recorded first as a K8
        ``paywall_bypass`` permanent block (K8 invariant 1), then refused.
        """

        licence = self.access_basis(doi)
        if bypass_paywall:
            if context is not None:
                self.propagate("paywall_bypass", context)
            raise PaywallBypassRefused(
                f"refusing to retrieve {doi} by circumventing its access basis "
                f"({licence.status.value}); bypass is not a retrieval mode"
            )
        granted = licence.status is AccessStatus.OPEN
        return RetrievalDecision(
            doi=doi,
            access=licence.status,
            granted=granted,
            basis="open_licence" if granted else licence.status.value,
            reasons=tuple(licence.reasons),
        )
