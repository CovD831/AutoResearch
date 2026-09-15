"""M14-05 -- license *policy and gate* layer (not license *fact* determination).

Division of labour (L3 §2.3): L-04's
:mod:`autoresearch.external_sources` / ``retraction.py`` decides the *fact* --
is this work open access, is it retracted, which ``updated-by[]`` notice applies.
This module never re-derives that.  :class:`LicenseTerm` is an **input**, handed
in by the source declaration or by L-04's finding; this layer answers only
"may *this subject* ``read``/``export`` it?".

The gate is fail-closed in the direction the contract cares about:

* ``open_access``       -> allowed (``reason="open_access"``);
* ``licensed``          -> allowed **only** with a live matching entitlement;
* ``paywalled``         -> allowed **only** with a live matching entitlement,
                           otherwise refused with ``reason="paywall"`` (N-5);
* ``unknown``           -> **always refused** (``reason="license_unknown"``).
  An undetermined licence is never treated as open -- collapsing "unknown" into
  "fine" is the defect family this repository keeps re-discovering
  (``UNAVAILABLE`` != ``ACTIVE``, K10; ``R0`` = not run, K4).

There is deliberately **no bypass path**: :class:`LicenseGate` exposes no
``force`` / ``override`` / ``skip`` parameter, so "绕过付费墙" has no
implementation to reach.  Every refusal is appended to
:attr:`LicenseGate.violations`, which is what makes an attempted paywall bypass
observable instead of silent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from autoresearch.contracts import new_id, utc_now

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


class LicenseTerm(StrEnum):
    """The licence *fact* about a resource -- supplied by the caller (see module docstring)."""

    OPEN_ACCESS = "open_access"
    LICENSED = "licensed"
    PAYWALLED = "paywalled"
    UNKNOWN = "unknown"


class LicenseAction(StrEnum):
    READ = "read"
    EXPORT = "export"


OPEN_ACCESS_REASON = "open_access"
ENTITLEMENT_REQUIRED_REASON = "entitlement_required"
ENTITLEMENT_EXPIRED_REASON = "entitlement_expired"
ENTITLEMENT_NOT_COVERING_REASON = "entitlement_does_not_cover_action"
PAYWALL_REASON = "paywall"
LICENSE_UNKNOWN_REASON = "license_unknown"
ENTITLED_REASON = "entitled"


def as_term(value: LicenseTerm | str) -> LicenseTerm:
    """Narrow a plain ``str`` to :class:`LicenseTerm`, failing loudly on a typo."""
    if isinstance(value, LicenseTerm):
        return value
    try:
        return LicenseTerm(value)
    except ValueError as exc:
        raise ValueError(
            f"unknown license term {value!r}; expected one of "
            f"{sorted(t.value for t in LicenseTerm)}"
        ) from exc


def as_action(value: LicenseAction | str) -> LicenseAction:
    """Narrow a plain ``str`` to :class:`LicenseAction`, failing loudly on a typo."""
    if isinstance(value, LicenseAction):
        return value
    try:
        return LicenseAction(value)
    except ValueError as exc:
        raise ValueError(
            f"unknown license action {value!r}; expected one of "
            f"{sorted(a.value for a in LicenseAction)}"
        ) from exc


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LicenseError(PermissionError):
    """Base class for licence-gate failures."""


class LicenseViolation(LicenseError):
    """An access that the licence policy refuses (N-5: attempted paywall bypass)."""

    def __init__(self, decision: LicenseDecision) -> None:
        super().__init__(
            f"license violation: subject={decision.subject!r} resource={decision.resource_id!r} "
            f"action={decision.action.value} term={decision.term.value} reason={decision.reason}"
        )
        self.decision = decision


# ---------------------------------------------------------------------------
# Entitlements + decisions
# ---------------------------------------------------------------------------


class Entitlement(BaseModel):
    """A subject's right to act on a resource.

    ``reference`` names the receipt for the right (order id, contract id) --
    a *reference*, never the document itself, mirroring the handoff discipline.
    """

    entitlement_id: str = Field(default_factory=lambda: new_id("ent"))
    subject: str = Field(min_length=1, max_length=200)
    resource_id: str = Field(min_length=1, max_length=400)
    actions: list[LicenseAction] = Field(default_factory=list)
    valid_until: datetime | None = None  # None == no expiry
    reference: str = Field(min_length=1, max_length=400)

    def covers(self, action: LicenseAction, *, now: datetime) -> bool:
        return action in self.actions and self.is_valid_at(now)

    def is_valid_at(self, now: datetime) -> bool:
        """``valid_until is None`` means "no expiry", not "expired"."""
        return self.valid_until is None or now <= self.valid_until


class LicenseDecision(BaseModel):
    subject: str
    resource_id: str
    action: LicenseAction
    term: LicenseTerm
    allowed: bool
    reason: str
    entitlement: Entitlement | None = None
    created_at: datetime = Field(default_factory=utc_now)


class LicenseViolationRecord(BaseModel):
    """One observable refusal (the analogue of ``acl.DenialRecord``)."""

    record_id: str = Field(default_factory=lambda: new_id("lic_violation"))
    subject: str
    resource_id: str
    action: LicenseAction
    term: LicenseTerm
    reason: str
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


class LicenseGate:
    """Fail-closed licence gate.  No bypass parameter exists, by design."""

    def __init__(self) -> None:
        self._entitlements: dict[tuple[str, str], Entitlement] = {}
        self._violations: list[LicenseViolationRecord] = []

    # -- entitlements ------------------------------------------------------

    def register_entitlement(self, entitlement: Entitlement) -> Entitlement:
        self._entitlements[(entitlement.subject, entitlement.resource_id)] = entitlement
        return entitlement

    def entitlement_for(self, subject: str, resource_id: str) -> Entitlement | None:
        return self._entitlements.get((subject, resource_id))

    @property
    def violations(self) -> tuple[LicenseViolationRecord, ...]:
        return tuple(self._violations)

    # -- authorization -----------------------------------------------------

    def check(
        self,
        *,
        subject: str,
        resource_id: str,
        term: LicenseTerm | str,
        action: LicenseAction | str,
        now: datetime | None = None,
    ) -> LicenseDecision:
        """Pure query.  Never raises, never records."""
        moment = now or datetime.now(UTC)
        term_value = as_term(term)
        action_value = as_action(action)
        entitlement = self.entitlement_for(subject, resource_id)

        def decision(allowed: bool, reason: str) -> LicenseDecision:
            return LicenseDecision(
                subject=subject,
                resource_id=resource_id,
                action=action_value,
                term=term_value,
                allowed=allowed,
                reason=reason,
                entitlement=entitlement,
            )

        if term_value is LicenseTerm.OPEN_ACCESS:
            return decision(True, OPEN_ACCESS_REASON)
        if term_value is LicenseTerm.UNKNOWN:
            # Fail-closed: an undetermined licence is not an open one.
            return decision(False, LICENSE_UNKNOWN_REASON)
        # LICENSED / PAYWALLED both need a live, covering entitlement.
        if entitlement is None:
            reason = (
                PAYWALL_REASON
                if term_value is LicenseTerm.PAYWALLED
                else ENTITLEMENT_REQUIRED_REASON
            )
            return decision(False, reason)
        if action_value not in entitlement.actions:
            return decision(False, ENTITLEMENT_NOT_COVERING_REASON)
        if not entitlement.is_valid_at(moment):
            return decision(False, ENTITLEMENT_EXPIRED_REASON)
        return decision(True, ENTITLED_REASON)

    def require(
        self,
        *,
        subject: str,
        resource_id: str,
        term: LicenseTerm | str,
        action: LicenseAction | str,
        now: datetime | None = None,
    ) -> LicenseDecision:
        """``check`` + record the refusal + raise :class:`LicenseViolation`."""
        result = self.check(
            subject=subject, resource_id=resource_id, term=term, action=action, now=now
        )
        if not result.allowed:
            self._violations.append(
                LicenseViolationRecord(
                    subject=result.subject,
                    resource_id=result.resource_id,
                    action=result.action,
                    term=result.term,
                    reason=result.reason,
                )
            )
            raise LicenseViolation(result)
        return result
