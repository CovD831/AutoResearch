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
