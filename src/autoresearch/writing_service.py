from __future__ import annotations

import re
from pathlib import Path

from autoresearch.benchmark_advisor import BenchmarkAdvisor
from autoresearch.contracts import (
    ArtifactRef,
    EvidenceGrade,
    EvidenceType,
    InnovationCandidate,
    Manuscript,
    PaperRecord,
    ReadingCard,
)
from autoresearch.evidence import EvidenceService
from autoresearch.llm import LLMService
from autoresearch.pipeline_contracts import (
    BenchmarkPlan,
    EvaluationSectionPipelineResult,
    MaterialReadinessResult,
    ReadinessStatus,
    SectionDraft,
    SectionPlan,
    SectionValidationReport,
    WritingProfile,
)
from autoresearch.readiness import EvaluationReadinessService
from autoresearch.section_validator import SectionValidator
from autoresearch.storage import RecordStore


class WritingService:
    def __init__(
        self,
        store: RecordStore,
        evidence: EvidenceService,
        projects_dir: Path,
        llm: LLMService,
    ):
        self.store = store
        self.evidence = evidence
        self.projects_dir = projects_dir.resolve()
        self.llm = llm

    @staticmethod
    def _citations(cards: list[ReadingCard]) -> str:
        if not cards:
            return "尚无可引用阅读卡。"
        return "\n".join(
            f"- [{card.paper_id}] {card.findings[0]} (locator: {', '.join(card.locators[:3])})"
            for card in cards
        )

    def draft(
        self,
        project_id: str,
        idea: str,
        papers: list[PaperRecord],
        cards: list[ReadingCard],
        innovations: list[InnovationCandidate],
        evidence_ids: list[str],
    ) -> Manuscript:
        evidence = self.evidence.resolve(evidence_ids)
        experiment_evidence = [
            item
            for item in evidence
            if item.evidence_type == EvidenceType.EXPERIMENT
            and item.grade in {EvidenceGrade.E2, EvidenceGrade.E3}
            and item.valid
        ]
        gaps: list[str] = []
        if not experiment_evidence:
            gaps.append("缺少可追溯实验结果；Results 只能保留待填占位，不得声称性能提升。")
        if len(cards) < 2:
            gaps.append("阅读卡不足两篇，相关工作覆盖度尚未闭环。")
        if not innovations:
            gaps.append("尚无经阅读 Agent 形成的创新候选。")

        innovation_text = (
            "\n".join(
                f"- {item.statement}（状态：{item.status.value}；验证：{item.falsification_test}）"
                for item in innovations
            )
            or "尚未形成创新候选。"
        )
        references = "\n".join(
            f"- [{paper.paper_id}] {paper.title}. {paper.year or 'n.d.'}. "
            f"{paper.doi or paper.url or paper.source}"
            for paper in papers
        )
        results = (
            "\n".join(f"- {item.claim} [{item.evidence_id}]" for item in experiment_evidence)
            if experiment_evidence
            else "【待真实实验】此处禁止填入推测数值。"
        )
        manuscript = Manuscript(
            project_id=project_id,
            title=f"Research draft: {idea[:100]}",
            sections={
                "Abstract": (
                    "本稿是证据约束的研究草稿。研究目标、方法和结果须在对应 Gate "
                    "通过后才能升级为可发布表述。"
                ),
                "Introduction": idea,
                "Related Work": self._citations(cards),
                "Proposed Contribution": innovation_text,
                "Method": (
                    "方法由工作包驱动；每项实现、数据、基线与消融均需产出带校验信息的证据。"
                ),
                "Experiments": ("执行计划应记录环境、输入、版本、指标、随机性与失败结果。"),
                "Results": results,
                "Discussion": "\n".join(gaps) or "当前已登记的主要证据缺口为空。",
                "Conclusion": (
                    "仅总结已由证据支持的内容；创新性与外部发布仍由审核和人工门禁控制。"
                ),
                "References": references or "尚无参考文献。",
            },
            evidence_ids=[item.evidence_id for item in evidence if item.valid],
            unresolved_gaps=gaps,
            release_ready=False,
        )
        self.store.put(
            "manuscript",
            manuscript.manuscript_id,
            manuscript,
            project_id=project_id,
            partition="projects",
        )
        self.store.append_event(
            "manuscript.drafted",
            {
                "manuscript_id": manuscript.manuscript_id,
                "unresolved_gaps": gaps,
            },
            project_id=project_id,
            actor="writer",
        )
        self.write_project_file(manuscript)
        return manuscript

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        return [value for value in dict.fromkeys(value for value in values if value)]

    def build_writing_profile(
        self,
        project_id: str,
        *,
        section_name: str = "Evaluation",
        version: str = "v1",
        voice: str = "evidence-first",
        citation_style: str = "inline-id",
    ) -> WritingProfile:
        profile = WritingProfile(
            project_id=project_id,
            section_name=section_name,
            version=version,
            voice=voice,
            citation_style=citation_style,
        )
        self.store.put(
            "writing_profile",
            profile.profile_id,
            profile,
            project_id=project_id,
            partition="projects",
        )
        self.store.append_event(
            "writing.profile_created",
            {
                "profile_id": profile.profile_id,
                "project_id": project_id,
                "section_name": section_name,
                "version": version,
            },
            project_id=project_id,
            actor="writing_service",
        )
        return profile

    def plan_evaluation_section(
        self,
        project_id: str,
        idea: str,
        cards: list[ReadingCard],
        innovations: list[InnovationCandidate] | None = None,
        evidence_ids: list[str] | None = None,
        *,
        profile: WritingProfile | None = None,
    ) -> SectionPlan:
        profile = profile or self.build_writing_profile(project_id)
        innovations = innovations or []
        derived_evidence_ids = self._unique(
            [
                *(evidence_ids or []),
                *[evidence_id for card in cards for evidence_id in card.evidence_ids],
                *[
                    evidence_id
                    for innovation in innovations
                    for evidence_id in innovation.evidence_ids
                ],
            ]
        )
        resolved_evidence = self.evidence.resolve(derived_evidence_ids, valid_only=True)
        artifact_refs = [
            ArtifactRef(
                artifact_id=card.card_id,
                kind="reading_card",
                summary=card.findings[0][:300] if card.findings else card.research_question[:300],
            )
            for card in cards
        ]
        claims: list[str] = []
        claim_evidence_map: dict[str, list[str]] = {}
        for card in cards:
            for finding in card.findings[:1]:
                claims.append(finding)
                claim_evidence_map.setdefault(finding, [])
                claim_evidence_map[finding] = self._unique(
                    [*claim_evidence_map[finding], *card.evidence_ids]
                )
        for innovation in innovations:
            claim = f"Hypothesis: {innovation.statement}"
            claims.append(claim)
            claim_evidence_map.setdefault(claim, [])
            claim_evidence_map[claim] = self._unique(
                [*claim_evidence_map[claim], *innovation.evidence_ids]
            )
        if not claims and idea.strip():
            claims.append(f"Hypothesis: {idea[:240]}")
            claim_evidence_map[claims[-1]] = [
                evidence.evidence_id for evidence in resolved_evidence
            ]
        claims = self._unique(claims)
        gaps: list[str] = []
        if not cards:
            gaps.append("No reading card has been collected yet.")
        elif len(cards) < 2:
            gaps.append("A second comparator reading card is still missing.")
        if not resolved_evidence:
            gaps.append("No valid evidence item is available for the section.")
        if cards and not any(card.limitations for card in cards):
            gaps.append("No explicit limitation was extracted from the reading cards.")
        if innovations:
            gaps.extend(
                self._unique(
                    [
                        f"Falsification pending: {innovation.falsification_test}"
                        for innovation in innovations
                    ]
                )
            )
        plan = SectionPlan(
            project_id=project_id,
            objective=(
                "Draft an evidence-first evaluation section that stays plan-only until "
                "real results are registered."
            ),
            claims=claims,
            claim_evidence_map=claim_evidence_map,
            evidence_ids=[item.evidence_id for item in resolved_evidence],
            artifact_refs=artifact_refs,
            experiment_dependencies=self._unique(
                [
                    "planned benchmark only",
                    *(
                        innovation.falsification_test
                        for innovation in innovations
                        if innovation.falsification_test
                    ),
                ]
            ),
            gaps=self._unique(gaps),
            profile_id=profile.profile_id,
        )
        self.store.put(
            "section_plan",
            plan.plan_id,
            plan,
            project_id=project_id,
            partition="projects",
        )
        self.store.append_event(
            "section.planned",
            {
                "plan_id": plan.plan_id,
                "project_id": project_id,
                "claim_count": len(plan.claims),
                "evidence_count": len(plan.evidence_ids),
                "gap_count": len(plan.gaps),
            },
            project_id=project_id,
            actor="writing_service",
        )
        return plan

    def advise_benchmark_plan(
        self,
        plan: SectionPlan,
        cards: list[ReadingCard],
        *,
        innovations: list[InnovationCandidate] | None = None,
    ) -> BenchmarkPlan:
        benchmark_plan = BenchmarkAdvisor().propose(
            plan,
            cards,
            innovations=innovations,
        )
        self.store.put(
            "benchmark_plan",
            benchmark_plan.benchmark_plan_id,
            benchmark_plan,
            project_id=plan.project_id,
            partition="projects",
        )
        self.store.append_event(
            "section.benchmark_planned",
            {
                "benchmark_plan_id": benchmark_plan.benchmark_plan_id,
                "plan_id": plan.plan_id,
                "planned_only": benchmark_plan.planned_only,
            },
            project_id=plan.project_id,
            actor="writing_service",
        )
        return benchmark_plan

    def assess_evaluation_readiness(
        self,
        plan: SectionPlan,
        benchmark_plan: BenchmarkPlan,
        cards: list[ReadingCard],
        *,
        profile: WritingProfile | None = None,
    ) -> MaterialReadinessResult:
        readiness = EvaluationReadinessService(self.evidence).assess(
            plan,
            benchmark_plan,
            cards,
            profile=profile,
        )
        self.store.put(
            "material_readiness",
            readiness.readiness_id,
            readiness,
            project_id=plan.project_id,
            partition="projects",
        )
        self.store.append_event(
            "section.readiness_assessed",
            {
                "readiness_id": readiness.readiness_id,
                "plan_id": plan.plan_id,
                "status": readiness.status.value,
            },
            project_id=plan.project_id,
            actor="writing_service",
        )
        return readiness

    def draft_evaluation_section(
        self,
        plan: SectionPlan,
        benchmark_plan: BenchmarkPlan,
        readiness: MaterialReadinessResult,
        *,
        profile: WritingProfile | None = None,
    ) -> SectionDraft:
        if readiness.status == ReadinessStatus.BLOCKED:
            raise PermissionError("evaluation section is blocked by missing required material")
        profile = profile or self.build_writing_profile(plan.project_id)
        claim_lines = []
        for claim in plan.claims:
            evidence_ids = ", ".join(plan.claim_evidence_map.get(claim, [])) or "none"
            claim_lines.append(f"- {claim}\n  - evidence: {evidence_ids}")
        evidence_lines = [
            f"- {evidence_id}"
            for evidence_id in self._unique(
                [*plan.evidence_ids, *readiness.evidence_ids]
            )
        ]
        benchmark_lines = [
            f"- benchmark: {benchmark_plan.benchmark_name}",
            f"- baselines: {', '.join(benchmark_plan.baseline) or 'none'}",
            f"- metrics: {', '.join(benchmark_plan.metrics) or 'none'}",
            f"- required materials: {', '.join(benchmark_plan.required_materials) or 'none'}",
            f"- risks: {', '.join(benchmark_plan.risks) or 'none'}",
            "- result state: planned only",
        ]
        missing_lines = [
            f"- {item}" for item in self._unique(
                [*readiness.missing_required, *readiness.missing_optional, *plan.gaps]
            )
        ]
        if not missing_lines:
            missing_lines = ["- none"]
        unknown_lines = [
            f"- {item}" for item in self._unique(
                [*plan.gaps, *readiness.missing_optional]
            )
        ]
        if not unknown_lines:
            unknown_lines = ["- none"]
        limitation_lines = [
            f"- {item}"
            for item in self._unique(
                plan.gaps or ["No additional limitation captured."]
            )
        ]
        body = "\n".join(
            [
                "# Evaluation",
                "",
                "## Objective",
                "",
                plan.objective,
                "",
                "## Claims",
                "",
                "\n".join(claim_lines) if claim_lines else "- none",
                "",
                "## Evidence",
                "",
                "\n".join(evidence_lines) if evidence_lines else "- none",
                "",
                "## Benchmark Plan",
                "",
                "\n".join(benchmark_lines),
                "",
                "## Missing Materials",
                "",
                "\n".join(missing_lines),
                "",
                "## Unknowns",
                "",
                "\n".join(unknown_lines),
                "",
                "## Limitations",
                "",
                "\n".join(limitation_lines),
                "",
                "## Notes",
                "",
                "This section remains plan-only and does not report measured outcomes.",
            ]
        )
        draft = SectionDraft(
            project_id=plan.project_id,
            section_id=plan.plan_id,
            profile_id=profile.profile_id,
            plan_id=plan.plan_id,
            benchmark_plan_id=benchmark_plan.benchmark_plan_id,
            title=plan.section_name,
            body=body,
            claims=plan.claims,
            claim_evidence_map=plan.claim_evidence_map,
            evidence_ids=self._unique([*plan.evidence_ids, *readiness.evidence_ids]),
            unresolved_gaps=self._unique(
                [*readiness.missing_required, *readiness.missing_optional, *plan.gaps]
            ),
            limitations=self._unique(plan.gaps),
            observed_result_summary=None,
            review_ready=readiness.status != ReadinessStatus.BLOCKED,
            notes=self._unique(readiness.action_items),
        )
        self.store.put(
            "section_draft",
            draft.draft_id,
            draft,
            project_id=plan.project_id,
            partition="projects",
        )
        self.store.append_event(
            "section.drafted",
            {
                "draft_id": draft.draft_id,
                "plan_id": plan.plan_id,
                "review_ready": draft.review_ready,
            },
            project_id=plan.project_id,
            actor="writing_service",
        )
        return draft

    def validate_evaluation_section(
        self,
        plan: SectionPlan,
        benchmark_plan: BenchmarkPlan,
        readiness: MaterialReadinessResult,
        draft: SectionDraft,
        *,
        profile: WritingProfile | None = None,
    ) -> SectionValidationReport:
        report = SectionValidator().validate(
            plan,
            draft,
            readiness,
            benchmark_plan,
            profile=profile,
        )
        self.store.put(
            "section_validation",
            report.report_id,
            report,
            project_id=plan.project_id,
            partition="projects",
        )
        self.store.append_event(
            "section.validated",
            {
                "report_id": report.report_id,
                "plan_id": plan.plan_id,
                "verdict": report.verdict.value,
            },
            project_id=plan.project_id,
            actor="writing_service",
        )
        return report

    def compose_evaluation_section(
        self,
        project_id: str,
        idea: str,
        cards: list[ReadingCard],
        innovations: list[InnovationCandidate] | None = None,
        evidence_ids: list[str] | None = None,
        *,
        profile: WritingProfile | None = None,
    ) -> EvaluationSectionPipelineResult:
        profile = profile or self.build_writing_profile(project_id)
        plan = self.plan_evaluation_section(
            project_id,
            idea,
            cards,
            innovations=innovations,
            evidence_ids=evidence_ids,
            profile=profile,
        )
        benchmark_plan = self.advise_benchmark_plan(
            plan,
            cards,
            innovations=innovations,
        )
        readiness = self.assess_evaluation_readiness(
            plan,
            benchmark_plan,
            cards,
            profile=profile,
        )
        draft: SectionDraft | None = None
        validation: SectionValidationReport | None = None
        if readiness.status != ReadinessStatus.BLOCKED:
            draft = self.draft_evaluation_section(
                plan,
                benchmark_plan,
                readiness,
                profile=profile,
            )
            validation = self.validate_evaluation_section(
                plan,
                benchmark_plan,
                readiness,
                draft,
                profile=profile,
            )
        result = EvaluationSectionPipelineResult(
            profile=profile,
            plan=plan,
            benchmark_plan=benchmark_plan,
            readiness=readiness,
            draft=draft,
            validation=validation,
        )
        self.store.put(
            "evaluation_section_pipeline",
            f"{plan.plan_id}:{readiness.readiness_id}",
            result,
            project_id=project_id,
            partition="projects",
        )
        self.store.append_event(
            "section.pipeline_composed",
            {
                "plan_id": plan.plan_id,
                "readiness_id": readiness.readiness_id,
                "status": readiness.status.value,
                "verdict": validation.verdict.value if validation is not None else None,
            },
            project_id=project_id,
            actor="writing_service",
        )
        return result

    @staticmethod
    def _numbers(text: str) -> set[str]:
        return set(re.findall(r"(?<!\w)\d+(?:\.\d+)?%?(?!\w)", text))

    def revise(
        self,
        manuscript_id: str,
        instructions: str,
        *,
        mode: str,
    ) -> Manuscript:
        raw = self.store.get("manuscript", manuscript_id)
        if raw is None:
            raise KeyError(manuscript_id)
        source = Manuscript.model_validate(raw)
        sections = dict(source.sections)
        revision_note = "Deterministic local revision; no new factual claim was added."

        if self.llm.available:
            try:
                result = self.llm.complete_json(
                    system=(
                        "Revise academic prose only. Preserve section names, evidence strength, "
                        "citation IDs, uncertainty, and all result placeholders. Return JSON with "
                        "a 'sections' object. Do not add numbers, references, or claims."
                    ),
                    user=(
                        f"Mode: {mode}\nInstructions: {instructions}\n"
                        f"Sections: {source.model_dump_json()}"
                    ),
                )
                proposed = result.get("sections") if result else None
                if isinstance(proposed, dict) and set(proposed) == set(sections):
                    before = "\n".join(sections.values())
                    after = "\n".join(str(proposed[key]) for key in sections)
                    if self._numbers(after) - self._numbers(before):
                        raise ValueError("revision introduced unsupported numeric tokens")
                    sections = {key: str(proposed[key]) for key in sections}
                    revision_note = "Managed LLM prose revision passed structural safeguards."
            except Exception as exc:
                revision_note = (
                    f"Managed LLM revision was discarded ({type(exc).__name__}); "
                    "deterministic fallback used."
                )

        sections = {
            heading: "\n".join(line.rstrip() for line in body.splitlines()).strip()
            for heading, body in sections.items()
        }
        sections["Revision Notes"] = (
            f"Mode: {mode}. Requested change: {instructions}. {revision_note}"
        )
        revised = Manuscript(
            project_id=source.project_id,
            title=source.title,
            sections=sections,
            evidence_ids=source.evidence_ids,
            unresolved_gaps=source.unresolved_gaps,
            release_ready=False,
            parent_manuscript_id=source.manuscript_id,
            revision_note=revision_note,
        )
        self.store.put(
            "manuscript",
            revised.manuscript_id,
            revised,
            project_id=revised.project_id,
            partition="projects",
        )
        self.store.append_event(
            "manuscript.revised",
            {
                "manuscript_id": revised.manuscript_id,
                "parent_manuscript_id": source.manuscript_id,
                "mode": mode,
            },
            project_id=revised.project_id,
            actor="writer",
        )
        self.write_project_file(
            revised,
            filename=f"MANUSCRIPT_REVISION_{revised.manuscript_id}.md",
        )
        return revised

    def write_project_file(
        self,
        manuscript: Manuscript,
        *,
        filename: str = "MANUSCRIPT_DRAFT.md",
    ) -> Path | None:
        project_dir = (self.projects_dir / manuscript.project_id).resolve()
        if not project_dir.is_relative_to(self.projects_dir) or not project_dir.is_dir():
            return None
        output = project_dir / "05_writing" / filename
        output.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# {manuscript.title}", ""]
        for heading, body in manuscript.sections.items():
            lines.extend([f"## {heading}", "", body, ""])
        if manuscript.unresolved_gaps:
            lines.extend(
                ["## Unresolved Evidence Gaps", ""]
                + [f"- {gap}" for gap in manuscript.unresolved_gaps]
                + [""]
            )
        output.write_text("\n".join(lines), encoding="utf-8")
        return output
