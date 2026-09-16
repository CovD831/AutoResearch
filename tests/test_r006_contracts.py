"""R-006 boundary-contract tests (P0 deliverable).

Covers the 9 data contracts in ``autoresearch.contracts``: the 5 modified
(C1 WikiPage, C3/C4 GraphEdge, C5 ExperienceRecord, C6 UserProfileItem,
C7 RetrievalHit) and the 4 new (C2 Statement, C4 enums, C8 RecallAuditRecord,
C9 ExperienceInjection).

The project hard rule ("discriminating power") is enforced here: every
validator is tested with a *violating* input and asserted to be rejected, not
merely that a legal input passes.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from autoresearch.contracts import (
    BRIDGE_KINDS,
    SAME_PARTITION_KINDS,
    ExperienceInjection,
    ExperienceInjectionItem,
    ExperienceRecord,
    ExperienceStage,
    GraphEdge,
    GraphEdgeKind,
    GraphNodeKind,
    InjectionChannel,
    KnowledgePartition,
    ProfileTier,
    RecallAuditRecord,
    RetrievalChannel,
    RetrievalHit,
    ReviewStatus,
    Statement,
    StatementStatus,
    UserProfileItem,
    WikiPage,
)

# ---------------------------------------------------------------------------
# 1. New enums are instantiable and carry the right string values.
# ---------------------------------------------------------------------------


def test_enums_instantiable():
    assert ReviewStatus.DRAFT == "draft"
    assert StatementStatus.CONTRADICTED == "contradicted"
    assert GraphEdgeKind.SUPPORTS == "supports"
    assert GraphNodeKind.WIKI_PAGE == "wiki_page"
    assert ExperienceStage.X4_POLICY == "x4_policy"
    assert ProfileTier.CONFIRMED == "confirmed"
    # VECTOR is defined but currently unreachable (no vector impl) -- §11.8.
    assert RetrievalChannel.VECTOR == "vector"
    assert InjectionChannel.EXPERIENTIAL == "experiential"


def test_bridge_and_same_partition_kind_partitions():
    assert BRIDGE_KINDS.isdisjoint(SAME_PARTITION_KINDS)
    assert {
        GraphEdgeKind.CITES,
        GraphEdgeKind.SUPPORTS,
        GraphEdgeKind.CONTRADICTS,
        GraphEdgeKind.INVALIDATES,
        GraphEdgeKind.DERIVED_FROM,
        GraphEdgeKind.APPLIES_TO,
        GraphEdgeKind.USES_METHOD,
        GraphEdgeKind.USES_DATASET,
        GraphEdgeKind.EVALUATES_ON,
        GraphEdgeKind.HAS_LIMITATION,
        GraphEdgeKind.EXTENDS,
        GraphEdgeKind.IMPROVES,
        GraphEdgeKind.CREATED_IN,
        GraphEdgeKind.PREFERS,
    } == BRIDGE_KINDS
    assert len(SAME_PARTITION_KINDS) == 3
    assert GraphEdgeKind.CITES in BRIDGE_KINDS
    assert GraphEdgeKind.SUMMARIZED_BY in SAME_PARTITION_KINDS


# ---------------------------------------------------------------------------
# 2. New field defaults are correct.
# ---------------------------------------------------------------------------


def test_wikipage_defaults():
    wp = WikiPage(
        partition=KnowledgePartition.PAPERS, title="t", body="b", author="svc"
    )
    assert wp.revision == 1
    assert wp.supersedes is None
    assert wp.review_status is ReviewStatus.DRAFT
    assert wp.effective_at is None
    assert wp.revision_id == f"{wp.page_id}:r1"


def test_experience_record_defaults():
    er = ExperienceRecord(project_id="p", problem="x", technique="y", outcome="z")
    assert er.stage is ExperienceStage.X0_RAW
    assert er.applicable_when == []
    assert er.not_applicable_when == []
    assert er.counterexample_ids == []
    assert er.raw_trace_refs == []
    assert er.valid_until is None
    assert er.regression_set_id is None
    assert er.valid_from is not None
    # §11.3: promoted is kept as a backward-compatible field for now (P2 derives
    # it from stage); default stays False.
    assert er.promoted is False


def test_user_profile_item_defaults():
    item = UserProfileItem(user_id="u", key="k", value="v", source="s", confidence=0.5)
    assert item.tier is ProfileTier.INFERRED
    assert item.sensitive is False
    assert item.expires_at is None


def test_retrieval_hit_defaults():
    hit = RetrievalHit(
        record_id="r",
        partition=KnowledgePartition.PAPERS,
        title="t",
        snippet="s",
        score=1.0,
        retrieval_level="L1",
    )
    assert hit.score_breakdown == {}
    assert hit.channel is RetrievalChannel.LEXICAL
    assert hit.matched_stage == "L1"


def test_statement_defaults():
    st = Statement(page_id="p", page_revision=1, text="t", status=StatementStatus.SUPPORTED)
    assert st.statement_id.startswith("stmt_")
    assert st.evidence_ids == []
    assert st.status_changed_at is not None


def test_recall_audit_record_defaults():
    rec = RecallAuditRecord(
        project_id="p",
        query="q",
        candidates=["a", "b"],
        deduped=["a", "b"],
        reranked=["a"],
        final_hits=["a"],
    )
    assert rec.audit_id.startswith("recall_")
    assert rec.filters == {}
    assert rec.stage_timings_ms == {}
    assert rec.created_at is not None


def test_experience_injection_defaults():
    item = ExperienceInjectionItem(experience_id="e", stage=ExperienceStage.X1_ATTRIBUTED)
    inj = ExperienceInjection(records=[item])
    # Constant literal type guarantees the channel can only be EXPERIENTIAL.
    assert inj.channel is InjectionChannel.EXPERIENTIAL
    assert inj.rendered_guidance == ""
    assert inj.records[0].tier_weight == 1.0


# ---------------------------------------------------------------------------
# 3. Discriminating power: each validator must reject a violating input.
# ---------------------------------------------------------------------------


def test_wikipage_author_required():
    with pytest.raises(ValidationError):
        WikiPage(partition=KnowledgePartition.PAPERS, title="t", body="b")


def test_wikipage_published_requires_effective_at():
    # Draft without effective_at is fine.
    WikiPage(
        partition=KnowledgePartition.PAPERS,
        title="t",
        body="b",
        author="svc",
        review_status=ReviewStatus.DRAFT,
    )
    # Published without effective_at is rejected.
    with pytest.raises(ValidationError):
        WikiPage(
            partition=KnowledgePartition.PAPERS,
            title="t",
            body="b",
            author="svc",
            review_status=ReviewStatus.PUBLISHED,
        )
    # Published with effective_at is accepted.
    WikiPage(
        partition=KnowledgePartition.PAPERS,
        title="t",
        body="b",
        author="svc",
        review_status=ReviewStatus.PUBLISHED,
        effective_at="2026-09-15T00:00:00+00:00",
    )


def test_graph_edge_relation_is_enum():
    # Existing string call sites must still coerce to the enum.
    ge = GraphEdge(
        project_id="p",
        partition=KnowledgePartition.PAPERS,
        source_id="a",
        relation="summarized_by",
        target_id="b",
    )
    assert ge.relation is GraphEdgeKind.SUMMARIZED_BY
    # An unknown relation string is rejected.
    with pytest.raises(ValidationError):
        GraphEdge(
            project_id="p",
            partition=KnowledgePartition.PAPERS,
            source_id="a",
            relation="related_to",
            target_id="b",
        )


def test_experience_record_stage_gate_discriminating():
    # X0 is allowed to have empty boundaries (the sink's natural output).
    ExperienceRecord(project_id="p", problem="x", technique="y", outcome="z")

    # X1 requires BOTH boundaries non-empty.
    with pytest.raises(ValidationError):
        ExperienceRecord(
            project_id="p",
            problem="x",
            technique="y",
            outcome="z",
            stage=ExperienceStage.X1_ATTRIBUTED,
        )
    with pytest.raises(ValidationError):
        ExperienceRecord(
            project_id="p",
            problem="x",
            technique="y",
            outcome="z",
            stage=ExperienceStage.X1_ATTRIBUTED,
            applicable_when=["a"],  # missing not_applicable_when
        )
    # X1 with both boundaries is accepted.
    ExperienceRecord(
        project_id="p",
        problem="x",
        technique="y",
        outcome="z",
        stage=ExperienceStage.X1_ATTRIBUTED,
        applicable_when=["a"],
        not_applicable_when=["b"],
    )

    # X2 requires a regression_set_id on top of the X1 boundaries.
    with pytest.raises(ValidationError):
        ExperienceRecord(
            project_id="p",
            problem="x",
            technique="y",
            outcome="z",
            stage=ExperienceStage.X2_REPRODUCED,
            applicable_when=["a"],
            not_applicable_when=["b"],
        )
    ExperienceRecord(
        project_id="p",
        problem="x",
        technique="y",
        outcome="z",
        stage=ExperienceStage.X2_REPRODUCED,
        applicable_when=["a"],
        not_applicable_when=["b"],
        regression_set_id="rs1",
    )

    # X3 requires counterexample_ids on top of the X2 requirements.
    with pytest.raises(ValidationError):
        ExperienceRecord(
            project_id="p",
            problem="x",
            technique="y",
            outcome="z",
            stage=ExperienceStage.X3_CROSS_PROJECT,
            applicable_when=["a"],
            not_applicable_when=["b"],
            regression_set_id="rs1",
        )
    ExperienceRecord(
        project_id="p",
        problem="x",
        technique="y",
        outcome="z",
        stage=ExperienceStage.X3_CROSS_PROJECT,
        applicable_when=["a"],
        not_applicable_when=["b"],
        regression_set_id="rs1",
        counterexample_ids=["c1"],
    )


def test_retrieval_hit_fused_requires_breakdown():
    # LEXICAL / GRAPH without a breakdown is fine.
    RetrievalHit(
        record_id="r",
        partition=KnowledgePartition.PAPERS,
        title="t",
        snippet="s",
        score=1.0,
        retrieval_level="L1",
        channel=RetrievalChannel.GRAPH,
    )
    # FUSED without a breakdown is rejected.
    with pytest.raises(ValidationError):
        RetrievalHit(
            record_id="r",
            partition=KnowledgePartition.PAPERS,
            title="t",
            snippet="s",
            score=1.0,
            retrieval_level="L1",
            channel=RetrievalChannel.FUSED,
        )
    # FUSED with a breakdown is accepted.
    RetrievalHit(
        record_id="r",
        partition=KnowledgePartition.PAPERS,
        title="t",
        snippet="s",
        score=1.0,
        retrieval_level="L1",
        channel=RetrievalChannel.FUSED,
        score_breakdown={"lexical": 0.4, "graph": 0.6},
    )


def test_user_profile_item_confirmed_requires_user():
    # INFERRED (default) without confirmation is fine.
    UserProfileItem(user_id="u", key="k", value="v", source="s", confidence=0.5)
    # CONFIRMED without confirmed_by_user is rejected.
    with pytest.raises(ValidationError):
        UserProfileItem(
            user_id="u", key="k", value="v", source="s", confidence=0.5,
            tier=ProfileTier.CONFIRMED,
        )
    # CONFIRMED with confirmed_by_user=True is accepted.
    UserProfileItem(
        user_id="u",
        key="k",
        value="v",
        source="s",
        confidence=0.5,
        tier=ProfileTier.CONFIRMED,
        confirmed_by_user=True,
    )


def test_recall_audit_record_subset_chain():
    # Each link of the chain must hold: final_hits ⊆ reranked ⊆ deduped ⊆ candidates.
    with pytest.raises(ValidationError):
        RecallAuditRecord(
            project_id="p",
            query="q",
            candidates=["a", "b"],
            deduped=["a", "b"],
            reranked=["a"],
            final_hits=["x"],  # not in reranked
        )
    with pytest.raises(ValidationError):
        RecallAuditRecord(
            project_id="p",
            query="q",
            candidates=["a"],
            deduped=["x"],  # not in candidates
            reranked=["x"],
            final_hits=["x"],
        )
    # A valid chain is accepted.
    RecallAuditRecord(
        project_id="p",
        query="q",
        candidates=["a", "b"],
        deduped=["a", "b"],
        reranked=["a"],
        final_hits=["a"],
    )


def test_experience_injection_channel_is_constant():
    # The channel can only be EXPERIENTIAL; the EVIDENCE channel is rejected by
    # the type system itself (C9 / I1).
    with pytest.raises(ValidationError):
        ExperienceInjection(channel=InjectionChannel.EVIDENCE, records=[])
    # JSON round-trip preserves the constant channel.
    inj = ExperienceInjection(
        records=[ExperienceInjectionItem(experience_id="e", stage=ExperienceStage.X2_REPRODUCED)]
    )
    dumped = inj.model_dump(mode="json")
    assert dumped["channel"] == "experiential"
    restored = ExperienceInjection.model_validate(dumped)
    assert restored.channel is InjectionChannel.EXPERIENTIAL
