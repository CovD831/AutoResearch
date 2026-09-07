from __future__ import annotations

from autoresearch.contracts import EvidenceGrade, EvidenceType, ReadingCard
from autoresearch.pipeline_contracts import EvidenceCandidate, ReadinessStatus, ValidationVerdict


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


def _reading_card(project_id: str, evidence_id: str) -> ReadingCard:
    return ReadingCard(
        project_id=project_id,
        paper_id="paper-a",
        research_question="How should the evaluation section stay evidence-first?",
        method="Evidence-first section planning",
        data_or_setting="Synthetic paper-project notes",
        findings=[
            "A section draft should keep claims and evidence visible together.",
        ],
        limitations=[
            "One comparator is still missing for a fully closed comparison.",
        ],
        locators=["p.1"],
        evidence_ids=[evidence_id],
        confidence=0.9,
    )


def test_evaluation_section_pipeline_builds_plan_and_keeps_benchmark_planned_only(
    runtime,
    project,
):
    candidate = _candidate("demo")
    admission = runtime.evidence.admit_candidate(candidate, actor="tester")
    card = _reading_card("demo", admission.evidence_id)
    runtime.store.put(
        "reading_card",
        card.card_id,
        card,
        project_id="demo",
        partition="papers",
    )

    profile = runtime.writing.build_writing_profile("demo")
    plan = runtime.writing.plan_evaluation_section(
        "demo",
        "Evaluate the evidence-first section pipeline.",
        [card],
        evidence_ids=[admission.evidence_id],
        profile=profile,
    )
    assert plan.objective.startswith("Draft an evidence-first evaluation section")
    assert len(plan.claims) == 1
    assert plan.claim_evidence_map[plan.claims[0]] == [admission.evidence_id]

    benchmark_plan = runtime.writing.advise_benchmark_plan(plan, [card])
    assert benchmark_plan.planned_only is True
    assert benchmark_plan.observed_result_summary is None
    assert "planned-only result guard" in benchmark_plan.required_materials

    result = runtime.writing.compose_evaluation_section(
        "demo",
        "Evaluate the evidence-first section pipeline.",
        [card],
        evidence_ids=[admission.evidence_id],
        profile=profile,
    )
    assert result.readiness.status == ReadinessStatus.NEEDS_MATERIAL
    assert result.draft is not None
    assert result.validation is not None
    assert result.validation.verdict == ValidationVerdict.VERIFIED
    assert result.draft.observed_result_summary is None
    assert "## Benchmark Plan" in result.draft.body
    assert "planned only" in result.draft.body
