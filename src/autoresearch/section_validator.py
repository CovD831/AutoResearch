from __future__ import annotations

import re

from autoresearch.pipeline_contracts import (
    BenchmarkPlan,
    MaterialReadinessResult,
    ReadinessStatus,
    SectionDraft,
    SectionKind,
    SectionPlan,
    SectionValidationReport,
    ValidationVerdict,
    WritingProfile,
)


class SectionValidator:
    REQUIRED_HEADINGS = [
        "## Objective",
        "## Claims",
        "## Evidence",
        "## Benchmark Plan",
        "## Missing Materials",
        "## Unknowns",
        "## Limitations",
        "## Notes",
    ]
    RESULT_NUMBER_PATTERNS = (
        re.compile(
            r"\b(?:accuracy|precision|recall|f1(?:[- ]score)?|auc|latency|"
            r"error(?: rate)?|success rate|quality|performance|score)\b"
            r"[^\n.]{0,80}\b(?:improv\w*|reduc\w*|increas\w*|decreas\w*|"
            r"outperform\w*|achiev\w*|reach\w*|obtain\w*|attain\w*|yield\w*|"
            r"deliver\w*)\b"
            r"[^\n.]{0,40}\b\d+(?:\.\d+)?%?(?:\s*(?:ms|s|seconds?|points?))?\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:achiev\w*|reach\w*|obtain\w*|record\w*|attain\w*|yield\w*|"
            r"deliver\w*)\b"
            r"[^\n.]{0,50}\b\d+(?:\.\d+)?%?\b[^\n.]{0,25}\b"
            r"(?:accuracy|precision|recall|f1(?:[- ]score)?|auc|latency|"
            r"error(?: rate)?|success rate|quality|performance|score)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b\d+(?:\.\d+)?%?\s+"
            r"(?:accuracy|precision|recall|f1(?:[- ]score)?|auc|latency|"
            r"error(?: rate)?|success rate|quality|performance|score)\b",
            re.IGNORECASE,
        ),
    )

    @classmethod
    def _result_like_numeric_claims(cls, body: str) -> list[str]:
        return list(
            dict.fromkeys(
                match.group(0).strip()
                for pattern in cls.RESULT_NUMBER_PATTERNS
                for match in pattern.finditer(body)
            )
        )

    def validate(
        self,
        plan: SectionPlan,
        draft: SectionDraft,
        readiness: MaterialReadinessResult,
        benchmark_plan: BenchmarkPlan,
        *,
        profile: WritingProfile | None = None,
    ) -> SectionValidationReport:
        issues: list[str] = []
        required_changes: list[str] = []
        allowed_claims = set(plan.claims)
        allowed_evidence_ids = set(readiness.evidence_ids)

        if readiness.status == ReadinessStatus.BLOCKED:
            issues.extend(readiness.missing_required)
            required_changes.extend(readiness.action_items or readiness.missing_required)
            return SectionValidationReport(
                project_id=plan.project_id,
                section_id=plan.plan_id,
                plan_id=plan.plan_id,
                draft_id=draft.draft_id,
                benchmark_plan_id=benchmark_plan.benchmark_plan_id,
                profile_id=(profile.profile_id if profile is not None else draft.profile_id),
                verdict=ValidationVerdict.BLOCKED,
                issues=issues,
                required_changes=required_changes,
                checked_evidence_ids=readiness.evidence_ids,
            )

        if draft.observed_result_summary is not None:
            issues.append("observed results must not appear in an evaluation section draft")
            required_changes.append("remove observed result text and keep the benchmark plan only")
        draft_claims = set(draft.claims)
        if draft_claims - allowed_claims:
            issues.append("draft introduces claims outside the plan")
            required_changes.append("remove out-of-plan claims")
        if set(draft.claim_evidence_map) - draft_claims:
            issues.append("claim bindings are not aligned with the draft claims")
            required_changes.append("align claim bindings with draft claims")
        if not benchmark_plan.planned_only:
            issues.append("benchmark plan is not marked as planned-only")
            required_changes.append("reset benchmark plan to planned-only")
        if benchmark_plan.observed_result_summary is not None:
            issues.append("benchmark plan carries an observed result summary")
            required_changes.append("remove observed result summary")
        if not any(value.strip() for value in benchmark_plan.baseline):
            issues.append("benchmark plan has no concrete baseline")
            required_changes.append("define a concrete baseline before verification")
        for result_claim in self._result_like_numeric_claims(draft.body):
            issues.append(f"unsupported result-like numeric claim: {result_claim}")
            required_changes.append(
                "remove unverified numeric outcomes and keep the benchmark plan-only"
            )
        if draft.section_id != plan.plan_id:
            issues.append("draft section id does not match the plan")
            required_changes.append("align the draft section id with the plan")
        if benchmark_plan.section_id != plan.plan_id:
            issues.append("benchmark plan section id does not match the plan")
            required_changes.append("align the benchmark plan with the section plan")
        if plan.profile_id != draft.profile_id:
            issues.append("draft profile does not match the planned profile")
            required_changes.append("align the draft with the planned writing profile")
        if profile is not None:
            if profile.profile_id != plan.profile_id:
                issues.append("writing profile does not match the section plan")
                required_changes.append("use the same writing profile for planning and drafting")
            if profile.section_kind != SectionKind.EVALUATION:
                issues.append("writing profile kind is not evaluation")
                required_changes.append("switch to the evaluation writing profile")
            if profile.section_name != plan.section_name:
                issues.append("writing profile section name does not match the plan")
                required_changes.append("align the writing profile section name")
        for heading in self.REQUIRED_HEADINGS:
            if heading not in draft.body:
                issues.append(f"missing section heading: {heading}")
                required_changes.append(f"add heading {heading}")
        if not draft.claims:
            issues.append("draft does not bind any claims")
            required_changes.append("bind claims to evidence")
        if set(draft.evidence_ids) - allowed_evidence_ids:
            issues.append("draft references evidence outside the allowed plan")
            required_changes.append("remove out-of-plan evidence references")
        if draft_claims - set(draft.claim_evidence_map):
            issues.append("draft does not bind every drafted claim")
            required_changes.append("bind every drafted claim to evidence")
        for claim in draft.claims:
            evidence_ids = draft.claim_evidence_map.get(claim, [])
            if not evidence_ids:
                issues.append(f"claim lacks evidence binding: {claim}")
                required_changes.append(f"attach evidence to {claim}")
                continue
            if set(evidence_ids) - allowed_evidence_ids:
                issues.append(f"claim evidence binding exceeds the allowed plan: {claim}")
                required_changes.append(f"remove out-of-plan evidence from {claim}")
        if readiness.status == ReadinessStatus.NEEDS_MATERIAL:
            missing_materials = {
                *readiness.missing_optional,
                *readiness.missing_required,
            }
            for item in missing_materials:
                if item not in draft.body:
                    issues.append(f"draft does not preserve missing material: {item}")
                    required_changes.append(f"surface missing material {item} in the draft")
        for gap in plan.gaps:
            if gap not in draft.body:
                issues.append(f"draft does not preserve planned gap: {gap}")
                required_changes.append(f"surface planned gap {gap} in the draft")

        verdict = ValidationVerdict.VERIFIED
        if issues:
            verdict = (
                ValidationVerdict.BLOCKED
                if readiness.status == ReadinessStatus.BLOCKED
                else ValidationVerdict.REVISE
            )

        return SectionValidationReport(
            project_id=plan.project_id,
            section_id=plan.plan_id,
            plan_id=plan.plan_id,
            draft_id=draft.draft_id,
            benchmark_plan_id=benchmark_plan.benchmark_plan_id,
            profile_id=(profile.profile_id if profile is not None else draft.profile_id),
            verdict=verdict,
            issues=issues,
            required_changes=required_changes,
            checked_evidence_ids=readiness.evidence_ids,
        )
