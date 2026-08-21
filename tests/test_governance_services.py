from __future__ import annotations

import pytest

from autoresearch.application import AutoResearchApplication
from autoresearch.contracts import (
    EvidenceGrade,
    EvidenceItem,
    EvidenceType,
    GateRequest,
    GateStatus,
    GraphEdge,
    KnowledgePartition,
    RiskLevel,
    WikiPage,
)


def _evidence(
    project_id: str,
    source: str,
    grade: EvidenceGrade = EvidenceGrade.E2,
) -> EvidenceItem:
    return EvidenceItem(
        project_id=project_id,
        evidence_type=EvidenceType.PAPER,
        grade=grade,
        title=f"Evidence from {source}",
        claim="A locatable source supports the bounded analytical claim.",
        source_id=source,
        locator="section 3",
        independent_source=source,
    )


def test_gate_fails_closed_and_deduplicates_sources(
    runtime: AutoResearchApplication,
    project,
):
    first = runtime.add_evidence(_evidence("demo", "paper-a"))
    duplicate_source = runtime.add_evidence(_evidence("demo", "paper-a"))
    request = GateRequest(
        project_id="demo",
        operation="manuscript_ready",
        risk_level=RiskLevel.L3,
        claim="The result is manuscript ready.",
        evidence_ids=[first.evidence_id, duplicate_source.evidence_id],
        work_closed_loop=True,
    )
    decision = runtime.gates.evaluate(request)
    assert decision.status == GateStatus.REVISE
    assert decision.independent_sources == 1
    assert decision.score == 30

    second = runtime.add_evidence(_evidence("demo", "experiment-b", EvidenceGrade.E3))
    passed = runtime.gates.evaluate(
        request.model_copy(update={"evidence_ids": [first.evidence_id, second.evidence_id]})
    )
    assert passed.status == GateStatus.PASS
    assert passed.score == 75


def test_l4_requires_named_human_approval_even_with_strong_evidence(
    runtime: AutoResearchApplication,
    project,
):
    items = [
        runtime.add_evidence(_evidence("demo", "source-a", EvidenceGrade.E3)),
        runtime.add_evidence(_evidence("demo", "source-b", EvidenceGrade.E3)),
    ]
    decision = runtime.gates.evaluate(
        GateRequest(
            project_id="demo",
            operation="external_release",
            risk_level=RiskLevel.L4,
            claim="Release reviewed manuscript.",
            evidence_ids=[item.evidence_id for item in items],
            work_closed_loop=True,
        )
    )
    assert decision.status == GateStatus.INTERRUPT


def test_explicit_rejection_and_invalidated_evidence_never_pass(
    runtime: AutoResearchApplication,
    project,
):
    item = runtime.add_evidence(_evidence("demo", "source-a", EvidenceGrade.E3))
    runtime.evidence.invalidate(item.evidence_id, "retracted", actor="reviewer")
    invalidated = runtime.gates.evaluate(
        GateRequest(
            project_id="demo",
            operation="analysis",
            risk_level=RiskLevel.L2,
            claim="Use invalidated evidence.",
            evidence_ids=[item.evidence_id],
        )
    )
    assert invalidated.status == GateStatus.REVISE
    assert invalidated.score == 0

    rejected = runtime.gates.evaluate(
        GateRequest(
            project_id="demo",
            operation="analysis",
            risk_level=RiskLevel.L0,
            claim="Reviewer rejected this operation.",
            explicitly_rejected=True,
        )
    )
    assert rejected.status == GateStatus.DENY


def test_partitioned_wiki_graph_retrieval(runtime: AutoResearchApplication, project):
    paper = runtime.knowledge.add_page(
        WikiPage(
            project_id="demo",
            partition=KnowledgePartition.PAPERS,
            title="Evidence gates in research",
            body="A paper about provenance and gates.",
            evidence_ids=["ev-paper"],
        )
    )
    card = runtime.knowledge.add_page(
        WikiPage(
            project_id="demo",
            partition=KnowledgePartition.PAPERS,
            title="Reading card",
            body="Summarizes the evidence gate paper.",
            evidence_ids=["ev-paper"],
        )
    )
    experience = runtime.knowledge.add_page(
        WikiPage(
            project_id="demo",
            partition=KnowledgePartition.EXPERIENCES,
            title="Evidence gate debugging",
            body="An internal technique.",
        )
    )
    runtime.knowledge.add_edge(
        GraphEdge(
            project_id="demo",
            partition=KnowledgePartition.PAPERS,
            source_id=paper.page_id,
            relation="summarized_by",
            target_id=card.page_id,
        )
    )
    with pytest.raises(ValueError):
        runtime.knowledge.add_edge(
            GraphEdge(
                project_id="demo",
                partition=KnowledgePartition.PAPERS,
                source_id=paper.page_id,
                relation="related_to",
                target_id=experience.page_id,
            )
        )

    hits = runtime.knowledge.retrieve(
        "provenance",
        partitions=[KnowledgePartition.PAPERS],
        level=2,
    )
    assert {hit.record_id for hit in hits} == {paper.page_id, card.page_id}
    assert all(hit.partition == KnowledgePartition.PAPERS for hit in hits)
