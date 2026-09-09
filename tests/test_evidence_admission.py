from __future__ import annotations

from autoresearch.contracts import EvidenceGrade, EvidenceType
from autoresearch.pipeline_contracts import EvidenceAdmissionStatus, EvidenceCandidate


def _candidate(project_id: str) -> EvidenceCandidate:
    return EvidenceCandidate(
        project_id=project_id,
        evidence_type=EvidenceType.PAPER,
        grade=EvidenceGrade.E1,
        title="Evidence-aware writing input",
        claim="The source exists and can support the section plan.",
        source_uri="https://example.invalid/source-a",
        source_id="source-a",
        locator="section 1",
        checksum="sha256:source-a",
        independent_source="source-a",
    )


def test_evidence_candidate_admission_handles_duplicate_and_conflict(
    runtime,
    project,
):
    candidate = _candidate("demo")
    first = runtime.evidence.admit_candidate(candidate, actor="tester")
    assert first.status == EvidenceAdmissionStatus.ACCEPTED
    assert first.evidence_id is not None

    duplicate = runtime.evidence.admit_candidate(
        candidate.model_copy(update={"candidate_id": "evcand-duplicate"}),
        actor="tester",
    )
    assert duplicate.status == EvidenceAdmissionStatus.DUPLICATE
    assert duplicate.existing_evidence_id == first.evidence_id

    conflict = runtime.evidence.admit_candidate(
        candidate.model_copy(
            update={"candidate_id": "evcand-conflict", "claim": "Different claim"}
        ),
        actor="tester",
    )
    assert conflict.status == EvidenceAdmissionStatus.CONFLICT
    assert conflict.existing_evidence_id == first.evidence_id
    assert len(runtime.evidence.list("demo")) == 1


def test_admission_rejects_unclassified_candidate_gracefully(runtime, project):
    """F-10 / D-I0-01: runtime-lane candidates arrive without classification.

    Admission must return a deterministic BLOCKED result instead of crashing
    on the required EvidenceItem fields.
    """

    unclassified = _candidate("demo").model_copy(
        update={"grade": None, "evidence_type": None, "candidate_id": "evcand-nograde"}
    )
    result = runtime.evidence.admit_candidate(unclassified, actor="tester")
    assert result.status == EvidenceAdmissionStatus.BLOCKED
    assert result.evidence_id is None
    assert any("evidence classification" in reason for reason in result.reasons)
    assert runtime.evidence.list("demo") == []
    blocked_events = [
        event
        for event in runtime.store.events("demo")
        if event["event_type"] == "evidence.candidate_blocked"
    ]
    assert blocked_events, "blocked admission must be auditable"


def test_admission_rejects_missing_grade_only(runtime, project):
    partial = _candidate("demo").model_copy(
        update={"grade": None, "candidate_id": "evcand-nograde-only"}
    )
    result = runtime.evidence.admit_candidate(partial, actor="tester")
    assert result.status == EvidenceAdmissionStatus.BLOCKED
    assert any("grade" in reason for reason in result.reasons)
    assert runtime.evidence.list("demo") == []
