from __future__ import annotations

from autoresearch.contracts import EvidenceGrade, EvidenceType, ReadingCard
from autoresearch.pipeline_contracts import (
    EvidenceCandidate,
    ReadinessStatus,
    SectionDraft,
    ValidationVerdict,
)


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


def _prepared_pipeline(runtime):
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
    draft = runtime.writing.draft_evaluation_section(
        plan,
        benchmark_plan,
        readiness,
        profile=profile,
    )
    return profile, plan, benchmark_plan, readiness, draft


def test_evaluation_section_validation_verifies_and_revises_when_the_draft_changes(
    runtime,
    project,
):
    profile, plan, benchmark_plan, readiness, draft = _prepared_pipeline(runtime)

    report = runtime.writing.validate_evaluation_section(
        plan,
        benchmark_plan,
        readiness,
        draft,
        profile=profile,
    )
    assert report.verdict == ValidationVerdict.VERIFIED

    revised_draft = draft.model_copy(update={"observed_result_summary": "Accuracy improved by 2%"})
    revise_report = runtime.writing.validate_evaluation_section(
        plan,
        benchmark_plan,
        readiness,
        revised_draft,
        profile=profile,
    )
    assert revise_report.verdict == ValidationVerdict.REVISE
    assert any("observed results" in issue for issue in revise_report.issues)


def test_evaluation_section_validation_blocks_when_readiness_is_blocked(
    runtime,
    project,
):
    profile = runtime.writing.build_writing_profile("demo")
    plan = runtime.writing.plan_evaluation_section(
        "demo",
        "Evaluate the evidence-first section pipeline.",
        [],
        evidence_ids=[],
        profile=profile,
    )
    benchmark_plan = runtime.writing.advise_benchmark_plan(plan, [])
    readiness = runtime.writing.assess_evaluation_readiness(
        plan,
        benchmark_plan,
        [],
        profile=profile,
    )
    assert readiness.status == ReadinessStatus.BLOCKED

    draft = SectionDraft(
        project_id=plan.project_id,
        section_id=plan.plan_id,
        profile_id=profile.profile_id,
        plan_id=plan.plan_id,
        benchmark_plan_id=benchmark_plan.benchmark_plan_id,
        title=plan.section_name,
        body="Placeholder evaluation draft for blocked readiness.",
        claims=plan.claims,
        claim_evidence_map={claim: [] for claim in plan.claims},
        evidence_ids=[],
        unresolved_gaps=readiness.missing_required,
        limitations=plan.gaps,
        observed_result_summary=None,
        review_ready=False,
        notes=readiness.action_items,
    )
    report = runtime.writing.validate_evaluation_section(
        plan,
        benchmark_plan,
        readiness,
        draft,
        profile=profile,
    )
    assert report.verdict == ValidationVerdict.BLOCKED
    assert "reading cards" in " ".join(report.issues)
