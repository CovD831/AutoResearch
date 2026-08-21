from __future__ import annotations

import re
from pathlib import Path

from autoresearch.contracts import (
    EvidenceGrade,
    EvidenceType,
    InnovationCandidate,
    Manuscript,
    PaperRecord,
    ReadingCard,
)
from autoresearch.evidence import EvidenceService
from autoresearch.llm import LLMService
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
