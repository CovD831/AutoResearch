from __future__ import annotations

from autoresearch.evidence import EvidenceService
from autoresearch.pipeline_contracts import (
    BenchmarkPlan,
    MaterialReadinessResult,
    ReadinessStatus,
    SectionPlan,
    WritingProfile,
)


class EvaluationReadinessService:
    def __init__(self, evidence: EvidenceService):
        self.evidence = evidence

    def assess(
        self,
        plan: SectionPlan,
        benchmark_plan: BenchmarkPlan,
        cards: list,
        *,
        profile: WritingProfile | None = None,
    ) -> MaterialReadinessResult:
        valid_evidence = self.evidence.resolve(plan.evidence_ids, valid_only=True)
        invalid_evidence = {
            evidence_id: reason
            for evidence_id in dict.fromkeys(plan.evidence_ids)
            if (reason := self.evidence.validity_reason(evidence_id)) is not None
        }
        missing_required: list[str] = []
        missing_optional: list[str] = []
        action_items: list[str] = []

        if not plan.claims:
            missing_required.append("evaluation claims")
        if not valid_evidence:
            missing_required.append("valid supporting evidence")
        if not cards:
            missing_required.append("reading cards")
        if not any(value.strip() for value in benchmark_plan.baseline):
            missing_required.append("benchmark baseline")
        if not any(value.strip() for value in benchmark_plan.metrics):
            missing_required.append("benchmark metrics")
        if not any(value.strip() for value in benchmark_plan.required_materials):
            missing_required.append("benchmark required materials")
        if not benchmark_plan.planned_only or (
            benchmark_plan.observed_result_summary
            and benchmark_plan.observed_result_summary.strip()
        ):
            missing_required.append("planned-only benchmark guard")

        if invalid_evidence:
            missing_optional.append("invalid supporting evidence")
            for evidence_id, reason in invalid_evidence.items():
                action_items.append(f"Remove invalid evidence {evidence_id}: {reason}.")

        if len(cards) < 2 and cards:
            missing_optional.append("secondary comparator card")
        if not plan.artifact_refs:
            missing_optional.append("artifact references")
        if not plan.gaps:
            missing_optional.append("explicit gap statement")
        if cards and not any(card.limitations for card in cards):
            missing_optional.append("documented limitation")
        if profile is None:
            missing_optional.append("writing profile")

        if missing_required:
            status = ReadinessStatus.BLOCKED
        elif missing_optional:
            status = ReadinessStatus.NEEDS_MATERIAL
        else:
            status = ReadinessStatus.READY

        for item in [*missing_required, *missing_optional]:
            action_items.append(f"Provide {item} or record why it remains unavailable.")

        return MaterialReadinessResult(
            project_id=plan.project_id,
            section_id=plan.plan_id,
            status=status,
            missing_required=missing_required,
            missing_optional=missing_optional,
            action_items=action_items,
            evidence_ids=[item.evidence_id for item in valid_evidence],
            benchmark_plan_id=benchmark_plan.benchmark_plan_id,
            profile_id=profile.profile_id if profile is not None else plan.profile_id,
        )
