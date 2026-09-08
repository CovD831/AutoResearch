from __future__ import annotations

from autoresearch.contracts import EvidenceGrade, EvidenceType, ReadingCard
from autoresearch.pipeline_contracts import (
    EvidenceCandidate,
    ReadinessStatus,
    ValidationVerdict,
)


def _candidate(project_id: str, source_id: str) -> EvidenceCandidate:
    return EvidenceCandidate(
        project_id=project_id,
        evidence_type=EvidenceType.PAPER,
        grade=EvidenceGrade.E1,
        title=f"Evidence fixture {source_id}",
        claim="The source supports a bounded evaluation claim.",
        source_uri=f"https://example.invalid/{source_id}",
        source_id=source_id,
        locator="section 1",
        checksum=f"sha256:{source_id}",
        independent_source=source_id,
    )


def _card(project_id: str, evidence_id: str, *, method: str = "Comparator method") -> ReadingCard:
    return ReadingCard(
        project_id=project_id,
        paper_id="paper-adversarial",
        research_question="How should unsupported evaluation claims be blocked?",
        method=method,
        data_or_setting="Offline fixture",
        findings=["A bounded claim remains tied to its evidence."],
        limitations=["The second comparator is not available in this fixture."],
        locators=["p.1"],
        evidence_ids=[evidence_id],
        confidence=0.9,
    )


def _prepared_pipeline(runtime, *, method: str = "Comparator method"):
    admission = runtime.evidence.admit_candidate(
        _candidate("demo", "source-a"),
        actor="adversarial-test",
    )
    card = _card("demo", admission.evidence_id, method=method)
    profile = runtime.writing.build_writing_profile("demo")
    plan = runtime.writing.plan_evaluation_section(
        "demo",
        "Evaluate the fail-closed evidence pipeline.",
        [card],
        evidence_ids=[admission.evidence_id],
        profile=profile,
    )
    benchmark = runtime.writing.advise_benchmark_plan(plan, [card])
    readiness = runtime.writing.assess_evaluation_readiness(
        plan,
        benchmark,
        [card],
        profile=profile,
    )
    draft = None
    if readiness.status != ReadinessStatus.BLOCKED:
        draft = runtime.writing.draft_evaluation_section(
            plan,
            benchmark,
            readiness,
            profile=profile,
        )
    return profile, plan, benchmark, readiness, draft, card


def test_missing_concrete_baseline_blocks_readiness(runtime, project):
    _, plan, benchmark, _, _, card = _prepared_pipeline(runtime, method="   ")
    assert benchmark.baseline == []

    readiness = runtime.writing.assess_evaluation_readiness(
        plan,
        benchmark,
        [card],
        profile=None,
    )

    assert readiness.status == ReadinessStatus.BLOCKED
    assert "benchmark baseline" in readiness.missing_required


def test_invalidated_evidence_cannot_support_readiness(runtime, project):
    valid = runtime.evidence.admit_candidate(
        _candidate("demo", "source-valid"),
        actor="adversarial-test",
    )
    invalid = runtime.evidence.admit_candidate(
        _candidate("demo", "source-invalid"),
        actor="adversarial-test",
    )
    runtime.evidence.invalidate(invalid.evidence_id, "retracted", actor="reviewer")
    card = _card("demo", invalid.evidence_id)
    profile = runtime.writing.build_writing_profile("demo")
    plan = runtime.writing.plan_evaluation_section(
        "demo",
        "Evaluate the fail-closed evidence pipeline.",
        [card],
        evidence_ids=[valid.evidence_id],
        profile=profile,
    )
    benchmark = runtime.writing.advise_benchmark_plan(plan, [card])
    readiness = runtime.writing.assess_evaluation_readiness(
        plan,
        benchmark,
        [card],
        profile=profile,
    )
    draft = runtime.writing.draft_evaluation_section(
        plan,
        benchmark,
        readiness,
        profile=profile,
    )
    report = runtime.writing.validate_evaluation_section(
        plan,
        benchmark,
        readiness,
        draft,
        profile=profile,
    )

    assert invalid.evidence_id not in readiness.evidence_ids
    assert report.verdict == ValidationVerdict.REVISE
    assert any("allowed plan" in issue for issue in report.issues)


def test_result_like_numeric_claim_is_never_verified(runtime, project):
    profile, plan, benchmark, readiness, draft, _ = _prepared_pipeline(runtime)
    revised = draft.model_copy(
        update={"body": draft.body + "\n\nAccuracy improved by 2%."}
    )

    report = runtime.writing.validate_evaluation_section(
        plan,
        benchmark,
        readiness,
        revised,
        profile=profile,
    )

    assert report.verdict == ValidationVerdict.REVISE
    assert any("numeric claim" in issue for issue in report.issues)


def test_observed_benchmark_result_is_blocked_before_validation(
    runtime,
    project,
):
    profile, plan, benchmark, _, _, card = _prepared_pipeline(runtime)
    observed = benchmark.model_copy(
        update={"observed_result_summary": "Accuracy improved by 2%"}
    )
    readiness = runtime.writing.assess_evaluation_readiness(
        plan,
        observed,
        [card],
        profile=profile,
    )

    assert readiness.status == ReadinessStatus.BLOCKED
    assert "planned-only benchmark guard" in readiness.missing_required
