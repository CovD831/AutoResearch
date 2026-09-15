"""M14-05 licence *policy gate* tests -- N-5 (attempted paywall bypass is refused).

Boundary note: this module does **not** determine licence facts (that is L-04's
``external_sources.py`` / ``retraction.py``); the :class:`LicenseTerm` is an input.
These tests therefore exercise the gate, never a fact-finding routine.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from autoresearch.licensing import (
    ENTITLEMENT_EXPIRED_REASON,
    ENTITLEMENT_NOT_COVERING_REASON,
    ENTITLEMENT_REQUIRED_REASON,
    LICENSE_UNKNOWN_REASON,
    OPEN_ACCESS_REASON,
    PAYWALL_REASON,
    Entitlement,
    LicenseAction,
    LicenseDecision,
    LicenseError,
    LicenseGate,
    LicenseTerm,
    LicenseViolation,
    as_action,
    as_term,
)

SUBJECT = "alice"
RESOURCE = "doi:10.1/paywalled"
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def _entitlement(
    gate: LicenseGate,
    *,
    actions: list[str] | None = None,
    valid_until: datetime | None = None,
    subject: str = SUBJECT,
    resource_id: str = RESOURCE,
) -> Entitlement:
    return gate.register_entitlement(
        Entitlement(
            subject=subject,
            resource_id=resource_id,
            actions=actions or ["read", "export"],  # type: ignore[arg-type]
            valid_until=valid_until,
            reference="order-2026-0001",
        )
    )


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


def test_license_terms_match_the_gate_contract():
    assert {t.value for t in LicenseTerm} == {
        "open_access",
        "licensed",
        "paywalled",
        "unknown",
    }
    assert {a.value for a in LicenseAction} == {"read", "export"}


def test_narrowing_helpers_accept_strings_and_reject_typos():
    assert as_term("paywalled") is LicenseTerm.PAYWALLED
    assert as_action("read") is LicenseAction.READ
    with pytest.raises(ValueError, match="unknown license term"):
        as_term("paid")
    with pytest.raises(ValueError, match="unknown license action"):
        as_action("download")


def test_entitlement_requires_a_reference_to_the_receipt():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Entitlement(
            subject=SUBJECT,
            resource_id=RESOURCE,
            actions=["read"],  # type: ignore[arg-type]
            reference="",
        )


# ---------------------------------------------------------------------------
# Open access / unknown
# ---------------------------------------------------------------------------


def test_open_access_needs_no_entitlement():
    gate = LicenseGate()
    for action in ("read", "export"):
        decision = gate.check(
            subject=SUBJECT, resource_id=RESOURCE, term="open_access", action=action
        )
        assert decision.allowed is True
        assert decision.reason == OPEN_ACCESS_REASON


def test_unknown_term_is_refused_and_never_treated_as_open():
    """An undetermined licence is not an open one (the "unknown recorded as fine" family)."""
    gate = LicenseGate()
    for action in ("read", "export"):
        decision = gate.check(
            subject=SUBJECT, resource_id=RESOURCE, term="unknown", action=action
        )
        assert decision.allowed is False
        assert decision.reason == LICENSE_UNKNOWN_REASON
    # an entitlement must not be able to launder an unknown term into access either
    _entitlement(gate)
    still_unknown = gate.check(
        subject=SUBJECT, resource_id=RESOURCE, term="unknown", action="export"
    )
    assert still_unknown.allowed is False
    assert still_unknown.reason == LICENSE_UNKNOWN_REASON


# ---------------------------------------------------------------------------
# N-5: attempted paywall bypass is refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["read", "export"])
def test_paywalled_without_entitlement_is_refused(action: str):
    gate = LicenseGate()
    decision = gate.check(
        subject=SUBJECT, resource_id=RESOURCE, term="paywalled", action=action
    )
    assert decision.allowed is False
    assert decision.reason == PAYWALL_REASON
    assert decision.entitlement is None


def test_require_records_the_bypass_attempt_and_raises():
    gate = LicenseGate()
    assert gate.violations == ()
    with pytest.raises(LicenseViolation) as excinfo:
        gate.require(
            subject=SUBJECT, resource_id=RESOURCE, term="paywalled", action="export"
        )
    assert excinfo.value.decision.reason == PAYWALL_REASON
    assert len(gate.violations) == 1
    record = gate.violations[0]
    assert record.subject == SUBJECT
    assert record.resource_id == RESOURCE
    assert record.term is LicenseTerm.PAYWALLED
    assert record.action is LicenseAction.EXPORT
    assert record.reason == PAYWALL_REASON


def test_check_alone_records_nothing():
    gate = LicenseGate()
    gate.check(subject=SUBJECT, resource_id=RESOURCE, term="paywalled", action="read")
    assert gate.violations == ()


def test_the_gate_exposes_no_bypass_parameter():
    """N-5 by construction: there is no ``force``/``override``/``skip`` to call.

    A bypass needs a code path; this asserts the public surface has none, so the
    refusal above cannot be side-stepped by a caller-supplied flag.
    """
    surface = {
        name for name in dir(LicenseGate) if not name.startswith("__")
    }
    assert not [name for name in surface if name in {"force", "override", "skip", "bypass"}]
    import inspect

    for name in ("check", "require"):
        params = set(inspect.signature(getattr(LicenseGate, name)).parameters)
        assert not params & {"force", "override", "skip", "bypass"}


# ---------------------------------------------------------------------------
# Entitlements
# ---------------------------------------------------------------------------


def test_paywalled_with_a_matching_entitlement_is_allowed():
    gate = LicenseGate()
    _entitlement(gate, actions=["read"])
    read = gate.check(
        subject=SUBJECT, resource_id=RESOURCE, term="paywalled", action="read", now=NOW
    )
    assert read.allowed is True
    assert read.entitlement is not None
    # ... but only for the action it covers
    export = gate.check(
        subject=SUBJECT, resource_id=RESOURCE, term="paywalled", action="export", now=NOW
    )
    assert export.allowed is False
    assert export.reason == ENTITLEMENT_NOT_COVERING_REASON
    assert export.reason != ENTITLEMENT_EXPIRED_REASON


def test_expired_entitlement_is_refused():
    gate = LicenseGate()
    _entitlement(gate, actions=["read"], valid_until=NOW - timedelta(days=1))
    decision = gate.check(
        subject=SUBJECT, resource_id=RESOURCE, term="licensed", action="read", now=NOW
    )
    assert decision.allowed is False
    assert decision.reason == ENTITLEMENT_EXPIRED_REASON


def test_entitlement_that_is_still_valid_is_accepted_at_the_boundary():
    gate = LicenseGate()
    _entitlement(gate, actions=["read"], valid_until=NOW)
    decision = gate.check(
        subject=SUBJECT, resource_id=RESOURCE, term="licensed", action="read", now=NOW
    )
    assert decision.allowed is True


def test_entitlement_is_scoped_to_the_subject():
    gate = LicenseGate()
    _entitlement(gate, actions=["read"])  # belongs to alice
    decision = gate.check(
        subject="bob", resource_id=RESOURCE, term="licensed", action="read", now=NOW
    )
    assert decision.allowed is False
    assert decision.reason == ENTITLEMENT_REQUIRED_REASON


def test_licensed_without_entitlement_is_refused_with_its_own_reason():
    gate = LicenseGate()
    decision = gate.check(
        subject=SUBJECT, resource_id=RESOURCE, term="licensed", action="read", now=NOW
    )
    assert decision.allowed is False
    assert decision.reason == ENTITLEMENT_REQUIRED_REASON
    assert decision.reason != PAYWALL_REASON


def test_violation_carries_a_decision_and_shares_the_permission_base_class():
    gate = LicenseGate()
    with pytest.raises(LicenseViolation) as excinfo:
        gate.require(subject=SUBJECT, resource_id=RESOURCE, term="paywalled", action="read")
    decision = excinfo.value.decision
    assert isinstance(decision, LicenseDecision)
    assert isinstance(excinfo.value, LicenseError)
    assert isinstance(excinfo.value, PermissionError)
