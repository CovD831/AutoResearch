from __future__ import annotations

import pytest

from autoresearch.contracts import EvidenceGrade, EvidenceType
from autoresearch.pipeline_contracts import EvidenceAdmissionStatus, EvidenceCandidate


def _candidate(
    project_id: str,
    *,
    locator: str | None = "section 1",
    metadata: dict | None = None,
) -> EvidenceCandidate:
    return EvidenceCandidate(
        project_id=project_id,
        evidence_type=EvidenceType.PAPER,
        grade=EvidenceGrade.E1,
        title="Adversarial evidence fixture",
        claim="The source supports a bounded, locatable claim.",
        source_uri="https://example.invalid/source-a",
        source_id="source-a",
        locator=locator,
        checksum="sha256:source-a",
        independent_source="source-a",
        metadata=metadata or {},
    )


@pytest.mark.parametrize("locator", [None, "", "   "])
def test_missing_candidate_locator_is_blocked_without_writing_evidence(
    runtime,
    project,
    locator,
):
    result = runtime.evidence.admit_candidate(
        _candidate("demo", locator=locator),
        actor="adversarial-test",
    )

    assert result.status == EvidenceAdmissionStatus.BLOCKED
    assert result.evidence_id is None
    assert result.reasons == ["candidate locator is required"]
    assert runtime.evidence.list("demo") == []


def test_direct_evidence_write_without_locator_fails_closed(runtime, project):
    from autoresearch.contracts import EvidenceItem

    with pytest.raises(ValueError, match="evidence locator is required"):
        runtime.evidence.add(
            EvidenceItem(
                project_id="demo",
                evidence_type=EvidenceType.PAPER,
                grade=EvidenceGrade.E1,
                title="Unlocatable evidence",
                claim="This claim has no source locator.",
                source_id="source-unlocatable",
                independent_source="source-unlocatable",
            ),
            actor="adversarial-test",
        )

    assert runtime.evidence.list("demo") == []


@pytest.mark.parametrize(
    ("expires_at", "is_valid"),
    [
        ("2000-01-01T00:00:00+00:00", False),
        ("2099-01-01T00:00:00+00:00", True),
        ("not-a-timestamp", False),
        ("2099-01-01T00:00:00", False),
    ],
)
def test_expiry_metadata_is_deterministic_and_fail_closed(
    runtime,
    project,
    expires_at,
    is_valid,
):
    admission = runtime.evidence.admit_candidate(
        _candidate("demo", metadata={"expires_at": expires_at}),
        actor="adversarial-test",
    )
    item = runtime.evidence.get(admission.evidence_id)

    assert item is not None
    assert item.valid is is_valid
    assert (item in runtime.evidence.list("demo", valid_only=True)) is is_valid
    if is_valid:
        assert runtime.evidence.validity_reason(item.evidence_id) is None
    else:
        assert runtime.evidence.validity_reason(item.evidence_id) is not None


def test_invalidated_evidence_remains_traceable_but_is_not_valid_support(
    runtime,
    project,
):
    admission = runtime.evidence.admit_candidate(
        _candidate("demo"),
        actor="adversarial-test",
    )
    runtime.evidence.invalidate(
        admission.evidence_id,
        "source retracted",
        actor="adversarial-reviewer",
    )

    item = runtime.evidence.get(admission.evidence_id)

    assert item is not None
    assert item.valid is False
    assert runtime.evidence.resolve([admission.evidence_id]) == [item]
    assert runtime.evidence.resolve([admission.evidence_id], valid_only=True) == []
    assert runtime.evidence.validity_reason(admission.evidence_id) == "source retracted"
