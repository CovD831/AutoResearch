from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from autoresearch.contracts import (
    ClaimStatus,
    EvidenceGrade,
    EvidenceItem,
    EvidenceType,
    GraphEdge,
    InnovationCandidate,
    KnowledgePartition,
    PaperRecord,
    ReadingAnswer,
    ReadingCard,
    WikiPage,
)
from autoresearch.evidence import EvidenceService
from autoresearch.knowledge import KnowledgeService
from autoresearch.storage import RecordStore


class PaperReaderService:
    def __init__(
        self,
        store: RecordStore,
        evidence: EvidenceService,
        knowledge: KnowledgeService,
    ):
        self.store = store
        self.evidence = evidence
        self.knowledge = knowledge

    @staticmethod
    def _read_file(path_value: str | None) -> tuple[str, list[str]]:
        if not path_value:
            return "", []
        path = Path(path_value)
        if not path.is_file():
            return "", [f"missing full text: {path}"]
        if path.suffix.lower() == ".pdf":
            reader = PdfReader(path)
            pages = [(page.extract_text() or "") for page in reader.pages]
            return "\n".join(pages), [f"p.{index + 1}" for index in range(len(pages))]
        text = path.read_text(encoding="utf-8", errors="replace")
        return text, ["local text"]

    @staticmethod
    def _sentences(text: str) -> list[str]:
        compact = re.sub(r"\s+", " ", text).strip()
        return [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?。！？])\s+", compact)
            if len(sentence.strip()) >= 25
        ]

    @staticmethod
    def _pick(sentences: list[str], keywords: tuple[str, ...], fallback: str) -> str:
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in keywords):
                return sentence[:800]
        return fallback

    def read(self, paper: PaperRecord) -> tuple[ReadingCard, EvidenceItem]:
        full_text, locators = self._read_file(paper.full_text_path)
        source_text = full_text or paper.abstract
        if not source_text:
            source_text = paper.title
        sentences = self._sentences(source_text)
        findings = sentences[:3] or ["No extractable finding was present in the supplied text."]
        method = self._pick(
            sentences,
            ("method", "approach", "we propose", "experiment", "方法", "提出"),
            "Method not identifiable from the supplied text.",
        )
        setting = self._pick(
            sentences,
            ("dataset", "benchmark", "participants", "sample", "数据集", "样本"),
            "Data or setting not identifiable from the supplied text.",
        )
        limitations = [
            sentence[:800]
            for sentence in sentences
            if any(
                keyword in sentence.lower()
                for keyword in ("limit", "future work", "however", "局限", "未来工作")
            )
        ][:3]
        if not limitations:
            limitations = ["No explicit limitation was extractable; this is an evidence gap."]

        grade = EvidenceGrade.E2 if full_text else EvidenceGrade.E1
        independent_source = paper.doi or paper.url or f"{paper.source}:{paper.source_record_id}"
        reading_evidence = self.evidence.add(
            EvidenceItem(
                project_id=paper.project_id,
                evidence_type=EvidenceType.PAPER,
                grade=grade,
                title=f"Reading extraction: {paper.title}",
                claim=findings[0],
                source_uri=paper.url or paper.full_text_path,
                source_id=paper.paper_id,
                locator=", ".join(locators[:5]) or "abstract",
                independent_source=independent_source,
                metadata={
                    "paper_id": paper.paper_id,
                    "full_text_used": bool(full_text),
                    "extraction": "deterministic",
                },
            ),
            actor="paper_reader",
        )
        card = ReadingCard(
            project_id=paper.project_id,
            paper_id=paper.paper_id,
            research_question=sentences[0][:800] if sentences else paper.title,
            method=method,
            data_or_setting=setting,
            findings=findings,
            limitations=limitations,
            locators=locators[:20] or ["abstract"],
            evidence_ids=[reading_evidence.evidence_id],
            confidence=0.75 if full_text else 0.45,
        )
        self.store.put(
            "reading_card",
            card.card_id,
            card,
            project_id=paper.project_id,
            partition=KnowledgePartition.PAPERS.value,
        )
        self.knowledge.add_page(
            WikiPage(
                page_id=card.card_id,
                project_id=paper.project_id,
                partition=KnowledgePartition.PAPERS,
                title=f"Reading card: {paper.title}",
                body=(
                    f"Question: {card.research_question}\nMethod: {card.method}\n"
                    f"Findings: {' '.join(card.findings)}\n"
                    f"Limitations: {' '.join(card.limitations)}"
                ),
                tags=["reading-card", paper.source],
                evidence_ids=card.evidence_ids,
                level=2,
            )
        )
        self.knowledge.add_edge(
            GraphEdge(
                project_id=paper.project_id,
                partition=KnowledgePartition.PAPERS,
                source_id=paper.paper_id,
                relation="summarized_by",
                target_id=card.card_id,
                evidence_ids=card.evidence_ids,
            )
        )
        return card, reading_evidence

    def mine_innovations(
        self,
        project_id: str,
        idea: str,
        cards: list[ReadingCard],
    ) -> list[InnovationCandidate]:
        if not cards:
            return []
        evidence_ids = list(dict.fromkeys(eid for card in cards for eid in card.evidence_ids))
        limitations = [
            limitation
            for card in cards
            for limitation in card.limitations
            if "evidence gap" not in limitation.lower()
        ]
        gap = limitations[0] if limitations else "cross-paper boundary conditions remain untested"
        candidate = InnovationCandidate(
            project_id=project_id,
            statement=(
                f"Test whether the proposed idea ({idea[:180]}) closes a documented research gap."
            ),
            rationale=(
                f"Candidate gap derived from structured reading: {gap[:500]}. "
                "This is a hypothesis, not a confirmed novelty claim."
            ),
            differentiators=[
                "Explicit evidence lineage from each comparison paper",
                "Falsifiable evaluation rather than novelty-by-wording",
                "Gate-controlled promotion from hypothesis to supported claim",
            ],
            evidence_ids=evidence_ids,
            status=ClaimStatus.HYPOTHESIS,
            falsification_test=(
                "Run the planned baseline and ablation work packages; reject the candidate "
                "if the claimed benefit is not reproduced or prior work already covers it."
            ),
        )
        self.store.put(
            "innovation",
            candidate.innovation_id,
            candidate,
            project_id=project_id,
            partition=KnowledgePartition.KNOWLEDGE.value,
        )
        self.knowledge.add_page(
            WikiPage(
                page_id=candidate.innovation_id,
                project_id=project_id,
                partition=KnowledgePartition.KNOWLEDGE,
                title="Innovation candidate",
                body=candidate.model_dump_json(indent=2),
                tags=["innovation", "hypothesis"],
                evidence_ids=evidence_ids,
                level=2,
            )
        )
        return [candidate]

    def answer_question(self, paper_id: str, question: str) -> ReadingAnswer:
        raw_paper = self.store.get("paper", paper_id)
        if raw_paper is None:
            raise KeyError(paper_id)
        paper = PaperRecord.model_validate(raw_paper)
        full_text, full_text_locators = self._read_file(paper.full_text_path)
        source_text = full_text or paper.abstract
        question_terms = {
            term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", question) if len(term) > 1
        }
        sentences = self._sentences(source_text)
        ranked = sorted(
            sentences,
            key=lambda sentence: -sum(term in sentence.lower() for term in question_terms),
        )
        selected = [
            sentence
            for sentence in ranked
            if any(term in sentence.lower() for term in question_terms)
        ][:3]
        cards = [
            ReadingCard.model_validate(raw)
            for raw in self.store.list("reading_card", project_id=paper.project_id)
            if raw["paper_id"] == paper_id
        ]
        evidence_ids = list(dict.fromkeys(eid for card in cards for eid in card.evidence_ids))
        unresolved = not bool(selected)
        answer = (
            " ".join(selected)
            if selected
            else "The supplied paper text does not contain enough locatable material to answer."
        )
        locators = full_text_locators[: len(selected)] if full_text else ["abstract"]
        response = ReadingAnswer(
            project_id=paper.project_id,
            paper_id=paper_id,
            question=question,
            answer=answer,
            locators=locators,
            evidence_ids=evidence_ids,
            confidence=0.7 if full_text and selected else (0.45 if selected else 0.0),
            unresolved=unresolved,
        )
        self.store.put(
            "reading_answer",
            response.answer_id,
            response,
            project_id=paper.project_id,
            partition=KnowledgePartition.PAPERS.value,
        )
        self.store.append_event(
            "paper.question_answered",
            {
                "answer_id": response.answer_id,
                "paper_id": paper_id,
                "unresolved": unresolved,
            },
            project_id=paper.project_id,
            actor="paper_reader",
        )
        return response
