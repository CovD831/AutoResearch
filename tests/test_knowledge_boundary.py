from __future__ import annotations

import json
import socket
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from autoresearch.contracts import (
    BRIDGE_KINDS,
    SAME_PARTITION_KINDS,
    EvidenceItem,
    GraphEdge,
    GraphEdgeKind,
    KnowledgePartition,
    WikiPage,
)
from autoresearch.evidence import EvidenceService
from autoresearch.knowledge import (
    WIKI_PAGE_HEAD_KIND,
    GraphEdgeRelationRegistry,
    KnowledgeService,
)
from autoresearch.storage import RecordStore

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "knowledge_boundary" / "offline_boundary.json"
)


class _TracingRecordStore(RecordStore):
    def __init__(self, path: Path) -> None:
        self.statements: list[str] = []
        super().__init__(path)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with super().connection() as connection:
            connection.set_trace_callback(self.statements.append)
            yield connection


def _page(
    page_id: str,
    *,
    revision: int = 1,
    project_id: str = "demo",
    partition: KnowledgePartition = KnowledgePartition.KNOWLEDGE,
    evidence_ids: list[str] | None = None,
) -> WikiPage:
    return WikiPage(
        page_id=page_id,
        project_id=project_id,
        partition=partition,
        title=f"{page_id} revision {revision}",
        body=f"body for {page_id} revision {revision}",
        evidence_ids=evidence_ids or [],
        revision=revision,
        author="m11_boundary_test",
    )


def _select_statements(store: _TracingRecordStore) -> list[str]:
    return [
        statement
        for statement in store.statements
        if statement.lstrip().upper().startswith("SELECT")
    ]


def _load_offline_fixture() -> dict:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["schema"] == "m11-knowledge-boundary/v1"
    return payload


def _run_offline_fixture(database: Path, payload: dict) -> dict:
    store = RecordStore(database)
    knowledge = KnowledgeService(store)
    EvidenceService(store).add(EvidenceItem.model_validate(payload["evidence"]))
    for raw_page in payload["pages"]:
        knowledge.add_page(WikiPage.model_validate(raw_page))
    for raw_edge in payload["edges"]:
        knowledge.add_edge(GraphEdge.model_validate(raw_edge))

    query = payload["query"]
    hits = knowledge.retrieve(
        query["text"],
        partitions=[KnowledgePartition(value) for value in query["partitions"]],
        level=query["level"],
        limit=query["limit"],
        require_evidence=query["require_evidence"],
    )
    evidence_rows = store.list("evidence", project_id="offline-demo")
    wiki_rows = store.list("wiki_page", project_id="offline-demo")
    edge_rows = store.list("graph_edge", project_id="offline-demo")
    evidence_id = payload["evidence"]["evidence_id"]

    return {
        "evidence_ids": sorted(row["evidence_id"] for row in evidence_rows),
        "wiki_revision_ids": sorted(
            f'{row["page_id"]}:r{row["revision"]}' for row in wiki_rows
        ),
        "graph_edge_ids": sorted(row["edge_id"] for row in edge_rows),
        "retrieval_hit_ids": [hit.record_id for hit in hits],
        "retrieval_partitions": [hit.partition.value for hit in hits],
        "evidence_row_count": len(evidence_rows),
        "wiki_row_count": len(wiki_rows),
        # Kind isolation: no *evidence record* may surface as a wiki row. A wiki
        # page legitimately cites evidence via ``evidence_ids`` (both fixture
        # pages do), so citing is not leakage -- the row's *identity* is what
        # must not collide with the evidence id.
        "evidence_in_wiki_rows": any(
            row.get("record_id") == evidence_id
            or row.get("page_id") == evidence_id
            for row in wiki_rows
        ),
        "evidence_in_retrieval": any(hit.record_id == evidence_id for hit in hits),
    }


def test_wiki_partition_contract_preserves_exact_five_values():
    assert {partition.value for partition in KnowledgePartition} == {
        "papers",
        "experiences",
        "knowledge",
        "profiles",
        "projects",
    }


def test_list_pages_uses_one_join_query_independent_of_page_count(tmp_path: Path):
    store = _TracingRecordStore(tmp_path / "records.sqlite3")
    service = KnowledgeService(store)
    for index in range(25):
        service.add_page(_page(f"page-{index:02d}"))

    store.statements.clear()
    pages = service.list_pages(
        project_id="demo",
        partition=KnowledgePartition.KNOWLEDGE,
    )

    selects = _select_statements(store)
    assert len(pages) == 25
    assert len(selects) == 1
    assert " JOIN " in selects[0].upper()


def test_list_pages_join_preserves_filters_latest_revision_and_dangling_head_skip(
    tmp_path: Path,
):
    store = _TracingRecordStore(tmp_path / "records.sqlite3")
    service = KnowledgeService(store)
    service.add_page(_page("target", revision=1, evidence_ids=["ev-old"]))
    service.add_page(_page("target", revision=2, evidence_ids=["ev-current"]))
    service.add_page(
        _page(
            "paper-page",
            partition=KnowledgePartition.PAPERS,
        )
    )
    service.add_page(_page("other-project", project_id="other"))
    store.put(
        WIKI_PAGE_HEAD_KIND,
        "dangling",
        {
            "page_id": "dangling",
            "current_revision_id": "dangling:r9",
            "revision": 9,
        },
        project_id="demo",
        partition=KnowledgePartition.KNOWLEDGE.value,
    )

    pages = service.list_pages(
        project_id="demo",
        partition=KnowledgePartition.KNOWLEDGE,
    )

    assert [page.page_id for page in pages] == ["target"]
    assert pages[0].revision == 2
    assert pages[0].evidence_ids == ["ev-current"]


def test_page_and_edge_traceability_round_trip(tmp_path: Path):
    store = RecordStore(tmp_path / "records.sqlite3")
    service = KnowledgeService(store)
    page = service.add_page(
        _page(
            "trace-page",
            project_id="trace-project",
            partition=KnowledgePartition.PAPERS,
            evidence_ids=["ev-page-1", "ev-page-2"],
        )
    )
    service.add_page(
        _page(
            "trace-target",
            project_id="trace-project",
            partition=KnowledgePartition.EXPERIENCES,
            evidence_ids=["ev-target"],
        )
    )
    edge = service.add_edge(
        GraphEdge(
            edge_id="edge-trace",
            project_id="trace-project",
            partition=KnowledgePartition.PAPERS,
            source_id="trace-page",
            relation=GraphEdgeKind.CITES,
            target_id="trace-target",
            evidence_ids=["ev-edge"],
        )
    )

    loaded_page = service.get_page("trace-page")
    stored_page = store.get("wiki_page", page.revision_id)
    stored_edge = store.get("graph_edge", edge.edge_id)

    assert loaded_page is not None
    assert loaded_page.project_id == "trace-project"
    assert loaded_page.partition is KnowledgePartition.PAPERS
    assert loaded_page.evidence_ids == ["ev-page-1", "ev-page-2"]
    assert loaded_page.revision_id == "trace-page:r1"
    assert loaded_page.author == "m11_boundary_test"
    assert stored_page is not None
    assert stored_page["project_id"] == "trace-project"
    assert stored_page["partition"] == KnowledgePartition.PAPERS.value
    assert stored_page["evidence_ids"] == ["ev-page-1", "ev-page-2"]
    assert stored_page["author"] == "m11_boundary_test"
    assert [
        item["page_id"]
        for item in store.list(
            "wiki_page",
            project_id="trace-project",
            partition=KnowledgePartition.PAPERS.value,
        )
    ] == ["trace-page"]

    assert stored_edge is not None
    assert stored_edge["edge_id"] == "edge-trace"
    assert stored_edge["project_id"] == "trace-project"
    assert stored_edge["partition"] == KnowledgePartition.PAPERS.value
    assert stored_edge["evidence_ids"] == ["ev-edge"]
    assert [
        item["edge_id"]
        for item in store.list(
            "graph_edge",
            project_id="trace-project",
            partition=KnowledgePartition.PAPERS.value,
        )
    ] == ["edge-trace"]


def test_bare_page_id_resolves_only_through_head(tmp_path: Path):
    store = RecordStore(tmp_path / "records.sqlite3")
    service = KnowledgeService(store)
    service.add_page(_page("bare-page", revision=1, evidence_ids=["ev-r1"]))
    service.add_page(_page("bare-page", revision=2, evidence_ids=["ev-r2"]))

    current = service.get_page("bare-page")

    assert store.get("wiki_page", "bare-page") is None
    assert current is not None
    assert current.revision_id == "bare-page:r2"
    assert current.evidence_ids == ["ev-r2"]
    assert store.get("wiki_page", "bare-page:r1")["evidence_ids"] == ["ev-r1"]
    assert store.get("wiki_page", "bare-page:r2")["evidence_ids"] == ["ev-r2"]


@pytest.mark.parametrize("missing_endpoint", ["source", "target"])
def test_missing_graph_edge_endpoint_is_rejected_without_a_write(
    tmp_path: Path,
    missing_endpoint: str,
):
    store = RecordStore(tmp_path / "records.sqlite3")
    service = KnowledgeService(store)
    service.add_page(_page("existing"))
    edge = GraphEdge(
        edge_id=f"edge-missing-{missing_endpoint}",
        project_id="demo",
        partition=KnowledgePartition.KNOWLEDGE,
        source_id="missing" if missing_endpoint == "source" else "existing",
        relation=GraphEdgeKind.SUMMARIZED_BY,
        target_id="missing" if missing_endpoint == "target" else "existing",
        evidence_ids=["ev-edge"],
    )

    with pytest.raises(ValueError, match="graph edge endpoints must exist"):
        service.add_edge(edge)

    assert store.get("graph_edge", edge.edge_id) is None
    assert store.list("graph_edge", project_id="demo") == []


def test_evidence_kind_isolated_from_wiki_retrieval(tmp_path: Path):
    payload = _load_offline_fixture()

    result = _run_offline_fixture(tmp_path / "isolation.sqlite3", payload)

    assert result == payload["expected"]
    assert result["evidence_row_count"] == 1
    assert result["wiki_row_count"] == 2
    assert result["evidence_in_wiki_rows"] is False
    assert result["evidence_in_retrieval"] is False
    assert result["retrieval_hit_ids"] == ["wiki-visible"]


def test_offline_fixture_is_deterministic_across_fresh_stores(
    tmp_path: Path,
    monkeypatch,
):
    payload = _load_offline_fixture()

    def reject_network(*args, **kwargs):
        raise AssertionError("offline knowledge-boundary fixture attempted network access")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    first = _run_offline_fixture(tmp_path / "first.sqlite3", payload)
    second = _run_offline_fixture(tmp_path / "second.sqlite3", payload)

    assert first == payload["expected"]
    assert second == payload["expected"]
    assert first == second


def test_whitelisted_bridge_edge_can_cross_partitions(tmp_path: Path):
    store = RecordStore(tmp_path / "records.sqlite3")
    service = KnowledgeService(store)
    service.add_page(_page("paper", partition=KnowledgePartition.PAPERS))
    service.add_page(_page("experience", partition=KnowledgePartition.EXPERIENCES))

    edge = service.add_edge(
        GraphEdge(
            project_id="demo",
            partition=KnowledgePartition.PAPERS,
            source_id="paper",
            relation=GraphEdgeKind.CITES,
            target_id="experience",
        )
    )

    assert edge.relation is GraphEdgeKind.CITES
    assert store.get("graph_edge", edge.edge_id) is not None


@pytest.mark.parametrize("relation", sorted(BRIDGE_KINDS, key=str), ids=str)
def test_every_managed_bridge_kind_can_cross_partitions(
    tmp_path: Path,
    relation: GraphEdgeKind,
):
    store = RecordStore(tmp_path / "records.sqlite3")
    service = KnowledgeService(store)
    service.add_page(_page("source", partition=KnowledgePartition.PAPERS))
    service.add_page(_page("target", partition=KnowledgePartition.EXPERIENCES))

    edge = service.add_edge(
        GraphEdge(
            project_id="demo",
            partition=KnowledgePartition.PAPERS,
            source_id="source",
            relation=relation,
            target_id="target",
        )
    )

    saved = store.get("graph_edge", edge.edge_id)
    assert saved is not None
    assert saved["relation"] == relation.value


@pytest.mark.parametrize("relation", sorted(SAME_PARTITION_KINDS, key=str), ids=str)
def test_same_partition_kinds_allow_same_partition_edges(
    tmp_path: Path,
    relation: GraphEdgeKind,
):
    store = RecordStore(tmp_path / "records.sqlite3")
    service = KnowledgeService(store)
    service.add_page(_page("source"))
    service.add_page(_page("target"))

    edge = service.add_edge(
        GraphEdge(
            project_id="demo",
            partition=KnowledgePartition.KNOWLEDGE,
            source_id="source",
            relation=relation,
            target_id="target",
        )
    )

    assert store.get("graph_edge", edge.edge_id) is not None


@pytest.mark.parametrize("relation", sorted(SAME_PARTITION_KINDS, key=str), ids=str)
def test_same_partition_kinds_reject_cross_partition_edges(
    tmp_path: Path,
    relation: GraphEdgeKind,
):
    store = RecordStore(tmp_path / "records.sqlite3")
    service = KnowledgeService(store)
    service.add_page(_page("source", partition=KnowledgePartition.PAPERS))
    service.add_page(_page("target", partition=KnowledgePartition.EXPERIENCES))

    with pytest.raises(ValueError, match="same-partition graph edge relation"):
        service.add_edge(
            GraphEdge(
                project_id="demo",
                partition=KnowledgePartition.PAPERS,
                source_id="source",
                relation=relation,
                target_id="target",
            )
        )


def test_edge_partition_must_match_source_partition(tmp_path: Path):
    store = RecordStore(tmp_path / "records.sqlite3")
    service = KnowledgeService(store)
    service.add_page(_page("source", partition=KnowledgePartition.PAPERS))
    service.add_page(_page("target", partition=KnowledgePartition.EXPERIENCES))

    with pytest.raises(ValueError, match="must match the source partition"):
        service.add_edge(
            GraphEdge(
                project_id="demo",
                partition=KnowledgePartition.PROFILES,
                source_id="source",
                relation=GraphEdgeKind.CITES,
                target_id="target",
            )
        )


def test_relation_registry_extends_policy_without_changing_add_edge(tmp_path: Path):
    store = RecordStore(tmp_path / "records.sqlite3")
    registry = GraphEdgeRelationRegistry()
    service = KnowledgeService(store, relation_registry=registry)
    service.add_page(_page("source", partition=KnowledgePartition.PAPERS))
    service.add_page(_page("target", partition=KnowledgePartition.EXPERIENCES))
    edge = GraphEdge(
        project_id="demo",
        partition=KnowledgePartition.PAPERS,
        source_id="source",
        relation=GraphEdgeKind.CITES,
        target_id="target",
    )

    with pytest.raises(ValueError, match="is not registered"):
        service.add_edge(edge)

    registry.register_bridge(GraphEdgeKind.CITES)

    assert service.add_edge(edge) == edge


def test_relation_registry_rejects_conflicting_policy_registration():
    registry = GraphEdgeRelationRegistry()
    registry.register_bridge(GraphEdgeKind.CITES)

    with pytest.raises(ValueError, match="already registered as bridge"):
        registry.register_same_partition(GraphEdgeKind.CITES)


def test_bridge_edge_does_not_bypass_explicit_partition_selection(tmp_path: Path):
    store = RecordStore(tmp_path / "records.sqlite3")
    service = KnowledgeService(store)
    service.add_page(
        _page("experience", partition=KnowledgePartition.EXPERIENCES)
    )
    service.add_page(_page("method", partition=KnowledgePartition.KNOWLEDGE))
    service.add_edge(
        GraphEdge(
            project_id="demo",
            partition=KnowledgePartition.EXPERIENCES,
            source_id="experience",
            relation=GraphEdgeKind.APPLIES_TO,
            target_id="method",
        )
    )

    hits = service.retrieve(
        "experience",
        partitions=[KnowledgePartition.EXPERIENCES],
        level=2,
    )

    assert [hit.record_id for hit in hits] == ["experience"]
