from __future__ import annotations

from autoresearch.contracts import EvidenceGrade, EvidenceType, ReadingCard
from autoresearch.pipeline_contracts import EvidenceCandidate, ReadinessStatus


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


def test_evaluation_section_pipeline_blocks_when_core_material_is_missing(
    runtime,
    project,
):
    profile = runtime.writing.build_writing_profile("demo")
    result = runtime.writing.compose_evaluation_section(
        "demo",
        "Evaluate the evidence-first section pipeline.",
        [],
        [],
        evidence_ids=[],
        profile=profile,
    )
    assert result.benchmark_plan.planned_only is True
    assert result.benchmark_plan.observed_result_summary is None
    assert result.readiness.status == ReadinessStatus.BLOCKED
    assert result.draft is None
    assert result.validation is None


def test_evaluation_readiness_marks_missing_optional_material(
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
    benchmark_plan = runtime.writing.advise_benchmark_plan(plan, [card])
    readiness = runtime.writing.assess_evaluation_readiness(
        plan,
        benchmark_plan,
        [card],
        profile=profile,
    )
    assert readiness.status == ReadinessStatus.NEEDS_MATERIAL
    assert "secondary comparator card" in readiness.missing_optional
