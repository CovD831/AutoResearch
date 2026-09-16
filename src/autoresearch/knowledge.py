from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from enum import StrEnum

from autoresearch.contracts import (
    BRIDGE_KINDS,
    SAME_PARTITION_KINDS,
    GraphEdge,
    GraphEdgeKind,
    KnowledgePartition,
    RetrievalHit,
    WikiPage,
)
from autoresearch.storage import RecordStore

# R-006 L1 / §11.9: a bare page_id is resolved through a dedicated head index
# record rather than through the versioned ``wiki_page`` table. The version
# table is append-only (one row per revision_id), so a bare id never matches.
WIKI_PAGE_HEAD_KIND = "wiki_page_head"


class GraphEdgeRelationPolicy(StrEnum):
    BRIDGE = "bridge"
    SAME_PARTITION = "same_partition"


class GraphEdgeRelationRegistry:
    """Classify typed graph relations without hard-coding policy in add_edge."""

    def __init__(
        self,
        *,
        bridge_kinds: Iterable[GraphEdgeKind] = (),
        same_partition_kinds: Iterable[GraphEdgeKind] = (),
    ) -> None:
        self._policies: dict[GraphEdgeKind, GraphEdgeRelationPolicy] = {}
        for relation in bridge_kinds:
            self.register_bridge(relation)
        for relation in same_partition_kinds:
            self.register_same_partition(relation)

    @classmethod
    def core(cls) -> GraphEdgeRelationRegistry:
        return cls(
            bridge_kinds=BRIDGE_KINDS,
            same_partition_kinds=SAME_PARTITION_KINDS,
        )

    def register(
        self,
        relation: GraphEdgeKind,
        policy: GraphEdgeRelationPolicy,
    ) -> None:
        existing = self._policies.get(relation)
        if existing is not None and existing is not policy:
            raise ValueError(
                f"graph edge relation {relation.value} is already registered as {existing.value}"
            )
        self._policies[relation] = policy

    def register_bridge(self, relation: GraphEdgeKind) -> None:
        self.register(relation, GraphEdgeRelationPolicy.BRIDGE)

    def register_same_partition(self, relation: GraphEdgeKind) -> None:
        self.register(relation, GraphEdgeRelationPolicy.SAME_PARTITION)

    def policy_for(self, relation: GraphEdgeKind) -> GraphEdgeRelationPolicy | None:
        return self._policies.get(relation)


class KnowledgeService:
    """Partitioned Wiki + graph store with bounded multi-level retrieval.

    Page storage is append-only (R-006 L1 / §11.9): every page revision is
    written under ``record_id = f"{page_id}:r{revision}"`` and the current
    revision for a bare ``page_id`` is tracked by a ``wiki_page_head`` index
    record. ``get_page`` / ``list_pages`` are the only sanctioned ways to read
    a page by its bare id; the raw ``wiki_page`` table enumerates *versions*
    and is only for audit / migration.
    """

    def __init__(
        self,
        store: RecordStore,
        relation_registry: GraphEdgeRelationRegistry | None = None,
    ):
        self.store = store
        self.relation_registry = (
            relation_registry
            if relation_registry is not None
            else GraphEdgeRelationRegistry.core()
        )

    def add_page(self, page: WikiPage) -> WikiPage:
        # The head read, contiguous-revision check, immutable version insert,
        # and head update share one immediate transaction. A concurrent writer
        # therefore validates against the committed head, never a stale one.
        revision_id = page.revision_id
        head_payload = {
            "page_id": page.page_id,
            "current_revision_id": revision_id,
            "revision": page.revision,
        }
        with self.store.transaction() as connection:
            head = self.store._read_record(connection, WIKI_PAGE_HEAD_KIND, page.page_id)
            current_max = head["revision"] if head else 0
            expected_revision = current_max + 1
            if page.revision != expected_revision:
                raise ValueError(
                    f"expected revision {expected_revision} for page {page.page_id}, "
                    f"got {page.revision}"
                )
            self.store._insert_record(
                connection,
                "wiki_page",
                revision_id,
                page,
                project_id=page.project_id,
                partition=page.partition.value,
            )
            self.store._write_record(
                connection,
                WIKI_PAGE_HEAD_KIND,
                page.page_id,
                head_payload,
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

    def get_page(self, page_id: str) -> WikiPage | None:
        """Resolve a bare page_id to its current revision (§11.9 head index)."""

        head = self.store.get(WIKI_PAGE_HEAD_KIND, page_id)
        if head is None:
            return None
        version = self.store.get("wiki_page", head["current_revision_id"])
        if version is None:
            # Crash / corruption left the head pointing at a missing version.
            # The head is authoritative: we never surface a dangling version,
            # and a missing version means the page is effectively absent.
            return None
        return WikiPage(**version)

    def list_pages(
        self,
        project_id: str | None = None,
        partition: KnowledgePartition | None = None,
    ) -> list[WikiPage]:
        """Enumerate pages, de-duplicated by page_id and resolved to head.

        This is the page-level analogue of ``store.list("wiki_page")``; the raw
        ``wiki_page`` table enumerates *versions* (one row per revision) and is
        only for audit / migration (§11.9).
        """

        versions = self.store.list_current_wiki_pages(
            project_id=project_id,
            partition=partition.value if partition is not None else None,
        )
        return [WikiPage(**version) for version in versions]

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        # Endpoints must be resolved through the head index, not the versioned
        # table (§11.9: a bare page_id no longer matches a wiki_page row).
        source = self.get_page(edge.source_id)
        target = self.get_page(edge.target_id)
        if source is None or target is None:
            raise ValueError("graph edge endpoints must exist")
        if source.partition != edge.partition:
            raise ValueError("graph edge partition must match the source partition")
        policy = self.relation_registry.policy_for(edge.relation)
        if policy is None:
            raise ValueError(f"graph edge relation {edge.relation.value} is not registered")
        if (
            policy is GraphEdgeRelationPolicy.SAME_PARTITION
            and target.partition != source.partition
        ):
            raise ValueError(
                f"same-partition graph edge relation {edge.relation.value} cannot cross partitions"
            )
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
            for page in self.list_pages(partition=partition):
                raw = page.model_dump()
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
                    neighbor = self.get_page(neighbor_id)
                    if neighbor is None:
                        continue
                    nraw = neighbor.model_dump()
                    if KnowledgePartition(nraw["partition"]) not in partitions:
                        continue
                    if require_evidence and not nraw.get("evidence_ids"):
                        continue
                    nraw["_score"] = max(candidate_pages[page_id]["_score"] * 0.35, 0.1)
                    candidate_pages.setdefault(neighbor_id, nraw)

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
