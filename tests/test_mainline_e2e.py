"""I2 mainline end-to-end: one minimal Evaluation Section scenario on merged main.

Chain under test (all stages durable and traceable):
  Paper Search (bounded invocation boundary, offline seeds)
    -> Evidence admission (evidence lane classification)
    -> material readiness -> BenchmarkPlan -> SectionDraft -> RuleValidation.

Rerunnable offline evidence for the I2 Promotion Gate: no network, no real
papers, no invented results.
"""

from __future__ import annotations

from autoresearch.application import AutoResearchApplication
from autoresearch.contracts import (
    EvidenceCandidate,
    EvidenceGrade,
    EvidenceType,
    PaperRecord,
    ReadingCard,
)
from autoresearch.evidence import EvidenceService
from autoresearch.pipeline_contracts import (
    EvidenceAdmissionStatus,
    ReadinessStatus,
    ValidationVerdict,
)
from autoresearch.storage import RecordStore


def test_mainline_minimal_evaluation_section_end_to_end(runtime: AutoResearchApplication, project):
    store: RecordStore = runtime.store

    # Stage 1 — Paper Search through the reliable invocation boundary.
    seed_paper = PaperRecord(
        project_id="demo",
        title="Evidence-aware agent workflows",
        abstract="Offline seed describing evidence-gated agent workflows.",
        authors=["A. Author"],
        year=2024,
        source="seed",
        url="https://example.invalid/seed-paper",
    )
    outcome = runtime.search_port.search(
        "demo",
        ["evidence-aware agent workflows"],
        seed_papers=[seed_paper],
    )
    assert len(outcome.papers) == 1
    searched = outcome.papers[0]
    assert any(
        event["event_type"] == "papers.search_completed"
        and event["payload"]["paper_ids"] == [searched.paper_id]
        for event in store.events("demo")
    )
    invocation_records = store.list_idempotent("paper_search")
    assert invocation_records
    assert invocation_records[-1]["record"]["state"] == "finalized"

    # Stage 2 — Evidence admission with evidence-lane classification.
    candidate = EvidenceCandidate(
        project_id="demo",
        evidence_type=EvidenceType.PAPER,
        grade=EvidenceGrade.E1,
        title=searched.title,
        claim="The seeded source supports a bounded evaluation claim.",
        source_uri=searched.url,
        source_id=searched.paper_id,
        locator="abstract",
        checksum="sha256:seed-paper",
        independent_source=searched.paper_id,
    )
    evidence = EvidenceService(store)
    admission = evidence.admit_candidate(candidate, actor="i2-e2e")
    assert admission.status == EvidenceAdmissionStatus.ACCEPTED
    assert store.get("evidence", admission.evidence_id) is not None

    # Stage 3 — reading card bound to the admitted evidence.
    card = ReadingCard(
        project_id="demo",
        paper_id=searched.paper_id,
        research_question="Can the mainline pipeline keep evaluation claims evidence-bound?",
        method="Comparator method",
        data_or_setting="Offline seed fixture",
        findings=["A bounded claim remains tied to its durable evidence."],
        limitations=["The second comparator is not available in this fixture."],
        locators=["abstract"],
        evidence_ids=[admission.evidence_id],
        confidence=0.9,
    )

    # Stages 4-6 — orchestrated readiness, benchmark plan, draft, validation.
    result = runtime.run_evaluation_section(
        "demo",
        "Evaluate the mainline evaluation section pipeline end to end.",
        [card],
        evidence_ids=[admission.evidence_id],
    )

    assert result.readiness.status != ReadinessStatus.BLOCKED
    assert result.benchmark_plan.baseline
    assert all(value.strip() for value in result.benchmark_plan.baseline)
    assert result.draft is not None
    assert result.validation is not None
    assert result.validation.verdict == ValidationVerdict.VERIFIED

    # Traceability: every downstream stage resolves back to the admitted evidence.
    assert admission.evidence_id in result.readiness.evidence_ids
    assert admission.evidence_id in result.validation.checked_evidence_ids
    assert result.draft.claim_evidence_map
    assert all(
        evidence_ids == [admission.evidence_id]
        for evidence_ids in result.draft.claim_evidence_map.values()
    )

    # Audit stream shows the full chain for this project.
    event_types = [event["event_type"] for event in store.events("demo")]
    assert "papers.search_completed" in event_types
    assert any(event_type.startswith("writing.") for event_type in event_types)
