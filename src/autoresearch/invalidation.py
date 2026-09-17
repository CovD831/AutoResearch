"""K8 ``InvalidationPropagation`` -- invalidation reaches claims and gates (M02-09).

Three invariants, all mechanically checkable:

* **K8-1** permanent reasons (``forged`` / ``paywall_bypass`` /
  ``unapproved_egress``) admit no exemption: they must map to
  ``action="permanent_block"``. The mapping is a table, not a branch buried in
  code, so it can be read and reviewed as data.
* **K8-2** a propagation walks from the invalidated source to the claims that
  depend on it, and onwards to the gates those claims feed.
* **K8-3** ``affected_claims`` may not be empty. An invalidation that reaches
  no claim is a *broken chain*, and a broken chain must raise -- returning an
  empty list would let "propagated nowhere" read as "propagated fine". This
  module is a deliberate counter-measure to the "empty set treated as a full
  pass" defect family.

Reuse, not rewrite: the retraction verdict comes from B5's ``updated-by[]``
reading (:mod:`autoresearch.external_sources`, PR #17 / ``7fdfb89``).
:func:`reason_from_source_status` only *maps* that verdict onto a K8 reason; no
Crossref relation array is parsed here.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from autoresearch.contracts import new_id, utc_now
from autoresearch.external_sources import SourceStatus

INVALIDATION_KIND = "invalidation_propagation"
GRAPH_EDGE_KIND = "graph_edge"


class InvalidationReason(StrEnum):
    RETRACTED = "retracted"
    EXPIRED = "expired"
    FORGED = "forged"
    PAYWALL_BYPASS = "paywall_bypass"
    UNAPPROVED_EGRESS = "unapproved_egress"


class InvalidationAction(StrEnum):
    RECOMPUTE = "recompute"
    PERMANENT_BLOCK = "permanent_block"


# K8-1 as a table. Permanent means permanent: these three admit no exemption.
PERMANENT_BLOCK_REASONS: frozenset[InvalidationReason] = frozenset(
    {
        InvalidationReason.FORGED,
        InvalidationReason.PAYWALL_BYPASS,
        InvalidationReason.UNAPPROVED_EGRESS,
    }
)


class InvalidationContractError(ValueError):
    """Base class for K8 contract violations raised by this module."""


class BrokenPropagationError(InvalidationContractError):
    """K8-3: the invalidation reached no claim -- a broken chain, not a no-op."""


def action_for_reason(reason: InvalidationReason) -> InvalidationAction:
    """K8-1 decision: permanent reasons can only ever be permanently blocked."""

    if reason in PERMANENT_BLOCK_REASONS:
        return InvalidationAction.PERMANENT_BLOCK
    return InvalidationAction.RECOMPUTE


def reason_from_source_status(status: SourceStatus) -> InvalidationReason | None:
    """Map B5's ``updated-by[]`` verdict onto a K8 reason.

    ``RETRACTED`` is the only status B5 can prove an invalidation from. Every
    other status -- including ``UNKNOWN`` and ``NOT_FOUND`` -- returns ``None``:
    "we could not tell" is not "it was retracted", and it is not "it is fine"
    either. The caller decides what to do with an undecidable verdict; this
    function refuses to invent one.
    """

    if status is SourceStatus.RETRACTED:
        return InvalidationReason.RETRACTED
    return None


class InvalidationPropagation(BaseModel):
    """One invalidation fact and the blast radius it reached."""

    propagation_id: str = Field(default_factory=lambda: new_id("inval"))
    source_evidence_id: str = Field(min_length=1)
    reason: InvalidationReason
    affected_claims: list[str] = Field(default_factory=list)
    affected_gates: list[str] = Field(default_factory=list)
    action: InvalidationAction
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _permanent_block_is_not_exemptible(self) -> InvalidationPropagation:
        """K8-1: a permanent reason may never be downgraded to ``recompute``."""

        if (
            self.reason in PERMANENT_BLOCK_REASONS
            and self.action is not InvalidationAction.PERMANENT_BLOCK
        ):
            raise ValueError(
                f"reason={self.reason.value!r} requires action='permanent_block' "
                f"(K8-1: permanent block is not exemptible); got {self.action.value!r}"
            )
        return self

    @model_validator(mode="after")
    def _propagation_must_reach_a_claim(self) -> InvalidationPropagation:
        """K8-3: an empty claim set is a broken chain, never a success."""

        if not self.affected_claims:
            raise ValueError(
                "affected_claims is empty: the invalidation reached no claim "
                "(K8-3 broken propagation chain)"
            )
        return self


class ClaimGraph(Protocol):
    """The dependency graph a propagation walks (K8-2).

    Implementations answer two questions. Keeping them separate lets callers
    with a richer node registry (L-06's knowledge graph, a Gate index) plug in
    without this module re-deriving node kinds.
    """

    def claims_for_evidence(self, evidence_id: str) -> list[str]: ...

    def gates_for_claims(self, claim_ids: Sequence[str]) -> list[str]: ...


class StoreClaimGraph:
    """Default traversal over ``graph_edge`` records.

    Node kinds are inferred from id prefixes (``claim_`` / ``gate_`` by
    default) because R-007's graph nodes carry no kind column. This is a
    documented heuristic: a repository whose claim ids do not follow those
    prefixes must inject its own :class:`ClaimGraph`.

    ``partitions`` scopes the walk. **Pass it in production.** ``None`` means
    "every partition in the store", so an invalidation raised in one partition
    would reach claims in unrelated ones -- and a ``permanent_block`` there is
    not recoverable. The parameter exists because K8 carries no project or
    partition field, so the scope has to come from the caller.
    """

    def __init__(
        self,
        store,  # noqa: ANN001 - duck-typed RecordStore
        *,
        partitions: Sequence[str] | None = None,
        claim_prefixes: tuple[str, ...] = ("claim_",),
        gate_prefixes: tuple[str, ...] = ("gate_",),
    ) -> None:
        self.store = store
        self.partitions = list(partitions) if partitions is not None else None
        self.claim_prefixes = claim_prefixes
        self.gate_prefixes = gate_prefixes

    def _edges(self) -> list[dict]:
        if self.partitions is None:
            return self.store.list(GRAPH_EDGE_KIND)
        edges: list[dict] = []
        for partition in self.partitions:
            edges.extend(self.store.list(GRAPH_EDGE_KIND, partition=partition))
        return edges

    @staticmethod
    def _other_endpoints(edge: dict, node_id: str) -> list[str]:
        endpoints = []
        if edge.get("source_id") == node_id:
            endpoints.append(edge.get("target_id"))
        if edge.get("target_id") == node_id:
            endpoints.append(edge.get("source_id"))
        return [value for value in endpoints if isinstance(value, str) and value]

    def _matches(self, node_id: str, prefixes: tuple[str, ...]) -> bool:
        return node_id.startswith(prefixes)

    def _neighbours(self, node_id: str) -> list[str]:
        """Nodes that depend on ``node_id``, one hop out.

        Two ways a dependency is declared: the edge names the node as an
        endpoint, or the edge carries the node in ``evidence_ids`` (the node is
        the evidence backing that edge, so both endpoints depend on it).
        """

        neighbours: list[str] = []
        for edge in self._edges():
            attached = edge.get("source_id") == node_id or edge.get("target_id") == node_id
            if attached:
                candidates = self._other_endpoints(edge, node_id)
            elif node_id in (edge.get("evidence_ids") or []):
                candidates = [edge.get("source_id"), edge.get("target_id")]
            else:
                continue
            for candidate in candidates:
                if isinstance(candidate, str) and candidate and candidate not in neighbours:
                    neighbours.append(candidate)
        return neighbours

    def claims_for_evidence(self, evidence_id: str) -> list[str]:
        """First hop: nodes reachable from the invalidated evidence.

        K8-2 scopes propagation to *claims* and gates. The earlier version
        excluded only ``gate_prefixes`` and accepted anything else, so an
        ordinary neighbour (an artifact, a record id) read as a claim and
        K8 would invent an affected_claim list with the wrong shape.

        ``claim_prefixes`` is the configured contract for what counts as a
        claim; ``gate_prefixes`` is the symmetric "this is definitely a
        gate, skip it here". Require both: a neighbour qualifies as a
        claim only if it matches a claim prefix.
        """

        claims: list[str] = []
        for node_id in self._neighbours(evidence_id):
            if node_id == evidence_id:
                continue
            if not self._matches(node_id, self.claim_prefixes):
                continue
            if node_id not in claims:
                claims.append(node_id)
        return claims

    def gates_for_claims(self, claim_ids: Sequence[str]) -> list[str]:
        """Second hop: gates reachable from the affected claims."""

        gates: list[str] = []
        for claim_id in claim_ids:
            for node_id in self._neighbours(claim_id):
                if not self._matches(node_id, self.gate_prefixes):
                    continue
                if node_id not in gates:
                    gates.append(node_id)
        return gates


# Fields that change between two attempts at the *same* fact. A retry is a new
# attempt at a new time, so comparing ``created_at`` would make every retry look
# like a conflicting payload and turn a legitimate fold into a hard error.
VOLATILE_FIELDS: frozenset[str] = frozenset({"created_at"})


def _fact_payload(payload: dict) -> dict:
    """The identity-bearing part of a record, minus volatile fields."""

    return {key: value for key, value in payload.items() if key not in VOLATILE_FIELDS}


class InvalidationService:
    """K8: turns an invalidation signal into a propagated, audited fact."""

    def __init__(
        self,
        store,  # noqa: ANN001 - duck-typed RecordStore
        *,
        graph: ClaimGraph | None = None,
        partitions: Sequence[str] | None = None,
    ) -> None:
        self.store = store
        if graph is not None:
            self.graph = graph
        else:
            # ``partitions=None`` walks every partition -- see StoreClaimGraph.
            self.graph = StoreClaimGraph(store, partitions=partitions)

    def plan(
        self,
        *,
        source_evidence_id: str,
        reason: InvalidationReason,
        propagation_id: str | None = None,
    ) -> InvalidationPropagation:
        """Derive the blast radius and action **without persisting anything**.

        The returned object is a full K8 record that has **not been stored and
        has not produced an audit event**. That distinction is the point: a
        caller that wants to cross-check the blast radius *before* the
        invalidation becomes real can validate the plan, then call
        :meth:`record` -- instead of validating afterwards, when the fact is
        already durable.

        Raises :class:`BrokenPropagationError` when the walk reaches no claim
        (K8-3), and the K8-1 / K8-3 model validators run here, so no invalid
        plan object can be constructed in the first place.

        ``propagation_id`` is the caller's *identity* choice and the only lever
        over retry collapsing (see :meth:`record`). Left unset, every call mints
        a fresh identity, so two calls are two facts. A caller that wants a
        retry to fold onto the same record must supply a stable id -- and that
        id must encode whatever *it* considers the same invalidation. K8 is
        silent on this: the frozen contract has no idempotency key.
        """

        claims = self.graph.claims_for_evidence(source_evidence_id)
        if not claims:
            raise BrokenPropagationError(
                f"invalidation of {source_evidence_id!r} reached no claim "
                "(K8-3): refusing to record an empty propagation as a success"
            )
        gates = self.graph.gates_for_claims(claims)
        fields: dict[str, object] = {
            "source_evidence_id": source_evidence_id,
            "reason": reason,
            "affected_claims": claims,
            "affected_gates": gates,
            "action": action_for_reason(reason),
        }
        if propagation_id is not None:
            fields["propagation_id"] = propagation_id
        return InvalidationPropagation(**fields)  # type: ignore[arg-type]

    def record(
        self,
        plan: InvalidationPropagation,
        *,
        actor: str = "system",
    ) -> InvalidationPropagation:
        """Persist a plan produced by :meth:`plan`.

        Idempotency keyed on ``propagation_id``. **Scope of that guard, stated
        exactly** (an earlier version of this docstring over-promised):

        * ``record(same_plan_object)`` twice -> one record, one audit event. The
          guard holds.
        * ``record(plan(...))`` twice -> **two** records, **two** audit events,
          because :meth:`plan` mints a fresh id per call. The guard does *not*
          reach across re-planning, which is exactly what a retry loop does.

        So "retrying does not duplicate the audit trail" is **not** something
        this method provides on its own. A caller that needs it must pass a
        stable ``propagation_id`` to :meth:`plan` (see that method's notes); K8
        fixes no idempotency key, so the policy is the caller's, not this
        module's, to choose.

        A stored payload that disagrees with the plan **on the fact itself**
        raises instead of silently overwriting -- including when a caller reuses
        an id for a *different* blast radius, which is a deliberate refusal
        rather than a merge. ``created_at`` is excluded from that comparison
        (see ``VOLATILE_FIELDS``): a retry necessarily carries a later timestamp,
        so comparing it would turn every legitimate fold into a hard error. A
        folded retry returns the **already-stored** record -- the durable fact
        with its original timestamp -- not the retry's transient object.
        """

        existing = self.store.get(INVALIDATION_KIND, plan.propagation_id)
        if existing is not None:
            if _fact_payload(existing) != _fact_payload(plan.model_dump(mode="json")):
                raise InvalidationContractError(
                    f"propagation {plan.propagation_id!r} is already stored with "
                    "different content; refusing to overwrite it"
                )
            return InvalidationPropagation.model_validate(existing)
        self.store.put(INVALIDATION_KIND, plan.propagation_id, plan, partition="invalidation")
        self.store.append_event("invalidation.propagated", plan, actor=actor)
        return plan

    def propagate(
        self,
        *,
        source_evidence_id: str,
        reason: InvalidationReason,
        actor: str = "system",
        propagation_id: str | None = None,
    ) -> InvalidationPropagation:
        """Walk evidence -> claims -> gates, then persist the fact.

        Shorthand for ``record(plan(...))``. Raises
        :class:`BrokenPropagationError` when the walk reaches no claim, so no
        half-propagated fact ever lands. Note that the one-shot form hands the
        caller no plan object to validate -- a caller that must check the blast
        radius before anything is written should use ``record(plan(...))``
        explicitly.
        """

        return self.record(
            self.plan(
                source_evidence_id=source_evidence_id,
                reason=reason,
                propagation_id=propagation_id,
            ),
            actor=actor,
        )
