"""I0 shared-contract integration tests.

These pin the cross-lane contract integration that I0 owns: both member
lanes share one RecordStore, one EvidenceCandidate definition, and the
runtime lane's invocation output can feed the evidence lane's admission
pipeline once the evidence lane supplies classification.
"""

from __future__ import annotations

from pathlib import Path

from a2_runtime_fixtures import FixtureService, paper, request_for

from autoresearch.capability import PaperSearchCapabilityAdapter
from autoresearch.contracts import EvidenceCandidate as SharedCandidate
from autoresearch.contracts import EvidenceGrade, EvidenceType
from autoresearch.evidence import EvidenceService
from autoresearch.invocation_contracts import EvidenceCandidate as InvocationCandidate
from autoresearch.pipeline_contracts import (
    EvidenceAdmissionStatus,
)
from autoresearch.pipeline_contracts import (
    EvidenceCandidate as PipelineCandidate,
)
from autoresearch.storage import RecordStore


def test_evidence_candidate_is_a_single_shared_contract():
    """I0: the two lanes must not carry divergent EvidenceCandidate definitions."""

    assert InvocationCandidate is SharedCandidate
    assert PipelineCandidate is SharedCandidate


def test_invocation_candidates_feed_evidence_admission(tmp_path: Path):
    """I0 compose: runtime-lane output satisfies evidence-lane admission input."""

    store = RecordStore(tmp_path / "compose.sqlite3")
    adapter = PaperSearchCapabilityAdapter(
        FixtureService(papers=[paper()]),
        store,
    )
    evidence = EvidenceService(store)

    invocation = adapter.invoke(request_for("compose"))
    assert invocation.evidence_candidates, "search must produce candidates"

    raw_candidate = invocation.evidence_candidates[0]
    assert raw_candidate.evidence_type is None  # runtime lane never grades (R005)

    classified = raw_candidate.model_copy(
        update={
            "evidence_type": EvidenceType.PAPER,
            "grade": EvidenceGrade.E1,
            "title": "Composed fixture paper",
        }
    )
    admission = evidence.admit_candidate(classified, actor="i0-compose")

    assert admission.status == EvidenceAdmissionStatus.ACCEPTED
    assert admission.evidence_id is not None
    assert store.get("evidence", admission.evidence_id) is not None
