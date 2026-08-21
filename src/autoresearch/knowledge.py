from __future__ import annotations

from collections import defaultdict

from autoresearch.contracts import (
    GraphEdge,
    KnowledgePartition,
    RetrievalHit,
    WikiPage,
)
from autoresearch.storage import RecordStore


class KnowledgeService:
    """Partitioned Wiki + graph store with bounded multi-level retrieval."""

    def __init__(self, store: RecordStore):
        self.store = store

    def add_page(self, page: WikiPage) -> WikiPage:
        self.store.put(
            "wiki_page",
            page.page_id,
            page,
            project_id=page.project_id,
            partition=page.partition.value,
        )
        self.store.append_event(
            "knowledge.page_added",
            page,
            project_id=page.project_id,
            actor="knowledge_service",
        )
        return page

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        source = self.store.get("wiki_page", edge.source_id)
        target = self.store.get("wiki_page", edge.target_id)
        if source is None or target is None:
            raise ValueError("graph edge endpoints must exist")
        if source["partition"] != edge.partition or target["partition"] != edge.partition:
            raise ValueError("cross-partition graph edges are not allowed")
        self.store.put(
            "graph_edge",
            edge.edge_id,
            edge,
            project_id=edge.project_id,
            partition=edge.partition.value,
        )
        return edge

    @staticmethod
    def _score(page: dict, terms: list[str]) -> float:
        title = page["title"].lower()
        body = page["body"].lower()
        tag_text = " ".join(page.get("tags", [])).lower()
        return sum(
            (3.0 if term in title else 0.0)
            + (1.0 if term in body else 0.0)
            + (2.0 if term in tag_text else 0.0)
            for term in terms
        )

    def retrieve(
        self,
        query: str,
        *,
        partitions: list[KnowledgePartition],
        level: int = 1,
        limit: int = 10,
        require_evidence: bool = False,
    ) -> list[RetrievalHit]:
        terms = [term for term in query.lower().split() if term]
        if not terms:
            return []

        candidate_pages: dict[str, dict] = {}
        for partition in partitions:
            for raw in self.store.list("wiki_page", partition=partition.value):
                score = self._score(raw, terms)
                if score > 0 and (not require_evidence or raw.get("evidence_ids")):
                    raw["_score"] = score
                    candidate_pages[raw["page_id"]] = raw

        if level >= 2 and candidate_pages:
            neighbors: dict[str, set[str]] = defaultdict(set)
            for partition in partitions:
                for edge in self.store.list("graph_edge", partition=partition.value):
                    neighbors[edge["source_id"]].add(edge["target_id"])
                    neighbors[edge["target_id"]].add(edge["source_id"])
            for page_id in list(candidate_pages):
                for neighbor_id in neighbors[page_id]:
                    neighbor = self.store.get("wiki_page", neighbor_id)
                    if neighbor is None:
                        continue
                    if KnowledgePartition(neighbor["partition"]) not in partitions:
                        continue
                    if require_evidence and not neighbor.get("evidence_ids"):
                        continue
                    neighbor["_score"] = max(candidate_pages[page_id]["_score"] * 0.35, 0.1)
                    candidate_pages.setdefault(neighbor_id, neighbor)

        ordered = sorted(
            candidate_pages.values(),
            key=lambda page: (-page["_score"], page["title"], page["page_id"]),
        )[:limit]
        retrieval_level = "lexical" if level == 1 else "lexical+graph"
        return [
            RetrievalHit(
                record_id=page["page_id"],
                partition=page["partition"],
                title=page["title"],
                snippet=page["body"][:500],
                score=page["_score"],
                evidence_ids=page.get("evidence_ids", []),
                retrieval_level=retrieval_level,
            )
            for page in ordered
        ]
