"""K12 ``SensitivityClass`` tests (M14-04) -- labels, unmeasured != zero, egress trace.

Two things this file deliberately does:

* **N-2** -- an unmeasured PII scan keeps ``value is None``; it is never coerced
  to ``0``.  ``0`` means "we looked and found none"; ``None`` means "we did not
  look".  Asserting ``is None`` (not ``== 0``) is the point.
* **The empty constraint is registered, not asserted** -- see
  :func:`test_sensitive_embedding_ban_is_annotated_not_asserted`.  That test
  guards a *string* (the deferral annotation), it is **not** evidence that the
  embedding ban holds, because nothing in this repository can violate it yet.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from autoresearch.pii import (
    DEFERRED_INVARIANTS,
    PiiSpan,
    SensitivityClass,
    SensitivityError,
    SensitivityLabel,
    SensitivityLedger,
    TraceAction,
    UnclassifiedExport,
    UntraceableExport,
    default_scanner,
    scan_for_pii,
)

RESOURCE = "paper-1"


def _label(
    ledger: SensitivityLedger,
    sensitivity: SensitivityClass = SensitivityClass.SENSITIVE,
    *,
    resource_kind: str = "artifact",
    resource_id: str = RESOURCE,
) -> SensitivityLabel:
    return ledger.label(
        SensitivityLabel(
            resource_kind=resource_kind,
            resource_id=resource_id,
            sensitivity=sensitivity,
            assigned_by="tester",
        )
    )


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


def test_sensitivity_classes_match_the_contract():
    assert {c.value for c in SensitivityClass} == {"public", "internal", "sensitive"}


def test_sensitive_is_treated_as_the_restricted_end():
    assert SensitivityClass.SENSITIVE.value == "sensitive"
    assert SensitivityClass.INTERNAL.value == "internal"
    assert len(SensitivityClass) == 3


# ---------------------------------------------------------------------------
# Empty-constraint discipline (R-007 §5)
# ---------------------------------------------------------------------------


def test_sensitive_embedding_ban_is_annotated_not_asserted():
    """Guards the *deferral annotation*, not the invariant.

    The embedding ban cannot be violated today (no vector implementation exists),
    so a ``passes`` assertion would be a permanently-green test -- exactly the
    R-006 §11.8 failure mode.  What this test can honestly check is that the
    deferral is still *registered* and still names its activation stage.  It goes
    red if someone silently drops the registration.
    """
    entry = DEFERRED_INVARIANTS.get("K12.SENSITIVE_FORBIDS_EMBEDDING")
    assert entry is not None
    assert "【向量落地后生效】" in entry
    # The registration must say what to do when the stage arrives, not just "later".
    assert "embedding" in entry


def test_the_deferral_registration_is_immutable():
    """A registry that callers can mutate is not a record of anything."""
    with pytest.raises(TypeError):
        DEFERRED_INVARIANTS["K12.SENSITIVE_FORBIDS_EMBEDDING"] = "overwritten"  # type: ignore[index]


def test_pii_module_still_has_no_embedding_surface_tripwire():
    """A *tripwire*, not evidence: if it fails, K12① must be re-tested for real.

    It asserts only that this module still exposes no embedding/vector API, i.e.
    that the activation condition for ``【向量落地后生效】`` has not fired.  It says
    nothing about whether SENSITIVE data is embedded -- nothing here can.
    """
    import autoresearch.pii as pii_module

    surface = [name for name in dir(pii_module) if not name.startswith("__")]
    assert not [name for name in surface if "embed" in name.lower()]
    assert not [name for name in surface if "vector" in name.lower()]


# ---------------------------------------------------------------------------
# N-2: value=None means NOT MEASURED -- never 0
# ---------------------------------------------------------------------------


def test_unmeasured_scan_keeps_none_not_zero():
    """N-2 core: no scanner -> ``value is None``; ``== 0`` would be a false "clean"."""
    result = scan_for_pii("contact alice@example.com now", resource_id=RESOURCE, scanner=None)
    assert result.value is None
    assert result.value != 0
    assert result.measured is False
    assert result.scanner is None
    assert result.spans == []


def test_measured_scan_reports_a_real_count_including_a_true_zero():
    """A scan that really ran reports a number -- and ``0`` is then meaningful."""
    clean = scan_for_pii("no personal data here", resource_id=RESOURCE, scanner=default_scanner)
    assert clean.scanner == "default_scanner"
    assert clean.measured is True
    assert clean.value == 0  # "we looked and found none" -- legitimately zero
    assert clean.spans == []

    dirty = scan_for_pii(
        "alice@example.com or +8613800001111", resource_id=RESOURCE, scanner=default_scanner
    )
    assert dirty.value == 2
    assert [span.kind for span in dirty.spans] == ["email", "phone"]


def test_the_two_zero_ish_states_are_distinguishable():
    """The whole point of N-2: ``None`` and ``0`` must not collapse."""
    unmeasured = scan_for_pii("x", resource_id=RESOURCE, scanner=None)
    measured = scan_for_pii("x", resource_id=RESOURCE, scanner=default_scanner)
    assert unmeasured.value is None
    assert measured.value == 0
    assert unmeasured.value is not measured.value
    assert unmeasured.measured is False
    assert measured.measured is True


def test_scan_result_refuses_an_impossible_combination():
    with pytest.raises(ValidationError):
        # claims a scanner ran but carries no value
        from autoresearch.pii import PiiScanResult

        PiiScanResult(resource_id=RESOURCE, scanner="default_scanner", value=None)
    with pytest.raises(ValidationError):
        # claims a value but no scanner produced it
        from autoresearch.pii import PiiScanResult

        PiiScanResult(resource_id=RESOURCE, scanner=None, value=3)
    with pytest.raises(ValidationError):
        from autoresearch.pii import PiiScanResult

        PiiScanResult(
            resource_id=RESOURCE,
            scanner="default_scanner",
            value=3,
            spans=[PiiSpan(kind="email", start=0, end=5)],
        )


def test_spans_carry_offsets_not_the_secret_text():
    result = scan_for_pii(
        "alice@example.com", resource_id=RESOURCE, scanner=default_scanner
    )
    span = result.spans[0]
    assert (span.kind, span.start, span.end) == ("email", 0, 17)
    # the matched substring must not be anywhere on the object
    dumped = result.model_dump_json()
    assert "alice@example.com" not in dumped


def test_span_rejects_inverted_offsets():
    with pytest.raises(ValidationError):
        PiiSpan(kind="email", start=5, end=2)


# ---------------------------------------------------------------------------
# K12 (2): export / delete traceability
# ---------------------------------------------------------------------------


def test_export_of_a_labelled_resource_is_traceable():
    ledger = SensitivityLedger()
    _label(ledger)
    trace = ledger.record(
        action=TraceAction.EXPORT,
        resource_kind="artifact",
        resource_id=RESOURCE,
        subject="alice",
        reason="external review request OPS-7",
    )
    assert trace.sensitivity is SensitivityClass.SENSITIVE
    assert trace.subject == "alice"
    assert ledger.traces == (trace,)


def test_delete_is_traceable_on_the_same_channel():
    ledger = SensitivityLedger()
    _label(ledger)
    trace = ledger.record(
        action=TraceAction.DELETE,
        resource_kind="artifact",
        resource_id=RESOURCE,
        subject="alice",
        reason="retention expiry",
    )
    assert trace.action is TraceAction.DELETE
    assert len(ledger.traces) == 1


@pytest.mark.parametrize("action", [TraceAction.EXPORT, TraceAction.DELETE])
def test_egress_without_a_reason_is_refused(action: TraceAction):
    ledger = SensitivityLedger()
    _label(ledger)
    with pytest.raises(UntraceableExport):
        ledger.record(
            action=action,
            resource_kind="artifact",
            resource_id=RESOURCE,
            subject="alice",
            reason="   ",
        )
    assert ledger.traces == ()


@pytest.mark.parametrize("action", [TraceAction.EXPORT, TraceAction.DELETE])
def test_egress_of_an_unlabelled_resource_is_refused(action: TraceAction):
    """D-L09-06: an unlabelled resource is not assumed PUBLIC."""
    ledger = SensitivityLedger()
    with pytest.raises(UnclassifiedExport):
        ledger.record(
            action=action,
            resource_kind="artifact",
            resource_id="never-labelled",
            subject="alice",
            reason="looks fine",
        )
    assert ledger.traces == ()


def test_ledger_resolves_the_label_it_recorded():
    ledger = SensitivityLedger()
    assert ledger.sensitivity_of("artifact", RESOURCE) is None
    _label(ledger, SensitivityClass.INTERNAL)
    assert ledger.sensitivity_of("artifact", RESOURCE) is SensitivityClass.INTERNAL
    # labels are scoped by (kind, id), not id alone
    assert ledger.sensitivity_of("partition", RESOURCE) is None


def test_untraceable_and_unclassified_share_a_base_class():
    assert issubclass(UntraceableExport, SensitivityError)
    assert issubclass(UnclassifiedExport, SensitivityError)
