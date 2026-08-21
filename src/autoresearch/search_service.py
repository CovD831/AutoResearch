from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from autoresearch.contracts import (
    EvidenceGrade,
    EvidenceItem,
    EvidenceType,
    KnowledgePartition,
    PaperRecord,
    WikiPage,
)
from autoresearch.evidence import EvidenceService
from autoresearch.knowledge import KnowledgeService
from autoresearch.storage import RecordStore


@dataclass
class SearchOutcome:
    papers: list[PaperRecord] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


class ScholarlyConnector(Protocol):
    name: str

    def search(self, query: str, limit: int) -> list[dict[str, Any]]: ...


class OpenAlexConnector:
    name = "openalex"

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        response = httpx.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": limit},
            timeout=30,
        )
        response.raise_for_status()
        records = []
        for work in response.json().get("results", []):
            abstract_index = work.get("abstract_inverted_index") or {}
            positioned = [
                (position, word)
                for word, positions in abstract_index.items()
                for position in positions
            ]
            abstract = " ".join(word for _, word in sorted(positioned))
            records.append(
                {
                    "title": work.get("display_name") or "Untitled",
                    "abstract": abstract,
                    "authors": [
                        entry.get("author", {}).get("display_name", "")
                        for entry in work.get("authorships", [])
                        if entry.get("author")
                    ],
                    "year": work.get("publication_year"),
                    "doi": (work.get("doi") or "").removeprefix("https://doi.org/") or None,
                    "url": (work.get("primary_location") or {}).get("landing_page_url"),
                    "source_record_id": work.get("id"),
                }
            )
        return records


class CrossrefConnector:
    name = "crossref"

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        response = httpx.get(
            "https://api.crossref.org/works",
            params={"query.bibliographic": query, "rows": limit},
            headers={"User-Agent": "AutoResearch/0.1 (mailto:noreply@example.invalid)"},
            timeout=30,
        )
        response.raise_for_status()
        records = []
        for work in response.json().get("message", {}).get("items", []):
            published = work.get("published-print") or work.get("published-online") or {}
            date_parts = published.get("date-parts") or [[None]]
            records.append(
                {
                    "title": (work.get("title") or ["Untitled"])[0],
                    "abstract": re.sub(r"<[^>]+>", " ", work.get("abstract") or "").strip(),
                    "authors": [
                        " ".join(filter(None, [author.get("given"), author.get("family")]))
                        for author in work.get("author", [])
                    ],
                    "year": date_parts[0][0],
                    "doi": work.get("DOI"),
                    "url": work.get("URL"),
                    "source_record_id": work.get("DOI"),
                }
            )
        return records


class SemanticScholarConnector:
    name = "semantic_scholar"

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        response = httpx.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": limit,
                "fields": "title,abstract,authors,year,externalIds,url",
            },
            timeout=30,
        )
        response.raise_for_status()
        records = []
        for work in response.json().get("data", []):
            records.append(
                {
                    "title": work.get("title") or "Untitled",
                    "abstract": work.get("abstract") or "",
                    "authors": [author.get("name", "") for author in work.get("authors", [])],
                    "year": work.get("year"),
                    "doi": (work.get("externalIds") or {}).get("DOI"),
                    "url": work.get("url"),
                    "source_record_id": work.get("paperId"),
                }
            )
        return records


class PaperSearchService:
    def __init__(
        self,
        store: RecordStore,
        evidence: EvidenceService,
        knowledge: KnowledgeService,
        *,
        network_enabled: bool,
        connectors: list[ScholarlyConnector] | None = None,
    ):
        self.store = store
        self.evidence = evidence
        self.knowledge = knowledge
        self.network_enabled = network_enabled
        self.connectors = connectors or [
            OpenAlexConnector(),
            CrossrefConnector(),
            SemanticScholarConnector(),
        ]

    @staticmethod
    def _dedupe_key(paper: PaperRecord) -> str:
        if paper.doi:
            return "doi:" + paper.doi.lower().strip()
        normalized = re.sub(r"\W+", "", paper.title.lower())
        return "title:" + normalized

    def _persist(self, paper: PaperRecord) -> tuple[PaperRecord, EvidenceItem]:
        self.store.put(
            "paper",
            paper.paper_id,
            paper,
            project_id=paper.project_id,
            partition=KnowledgePartition.PAPERS.value,
        )
        independent_source = paper.doi or paper.url or f"{paper.source}:{paper.source_record_id}"
        evidence = self.evidence.add(
            EvidenceItem(
                project_id=paper.project_id,
                evidence_type=EvidenceType.PAPER,
                grade=EvidenceGrade.E1,
                title=f"Bibliographic record: {paper.title}",
                claim="This scholarly record and its supplied abstract exist in the cited source.",
                source_uri=paper.url,
                source_id=paper.paper_id,
                locator="bibliographic record/abstract",
                independent_source=independent_source,
                metadata={"paper_id": paper.paper_id, "source": paper.source},
            ),
            actor="paper_search",
        )
        self.knowledge.add_page(
            WikiPage(
                page_id=paper.paper_id,
                project_id=paper.project_id,
                partition=KnowledgePartition.PAPERS,
                title=paper.title,
                body=paper.abstract or "No abstract was supplied.",
                tags=[paper.source, str(paper.year or "")],
                evidence_ids=[evidence.evidence_id],
                level=1,
            )
        )
        return paper, evidence

    def search(
        self,
        project_id: str,
        queries: list[str],
        *,
        seed_papers: list[PaperRecord] | None = None,
        per_connector_limit: int = 5,
    ) -> SearchOutcome:
        outcome = SearchOutcome()
        candidates = list(seed_papers or [])
        if not self.network_enabled:
            outcome.diagnostics.append(
                "Network search is disabled; only user-supplied seed papers were processed."
            )
        else:
            for query in queries:
                for connector in self.connectors:
                    try:
                        for raw in connector.search(query, per_connector_limit):
                            candidates.append(
                                PaperRecord(project_id=project_id, source=connector.name, **raw)
                            )
                    except Exception as exc:
                        outcome.diagnostics.append(
                            f"{connector.name} failed for query {query!r}: {type(exc).__name__}"
                        )

        seen: set[str] = set()
        for paper in candidates:
            if paper.project_id != project_id:
                paper = paper.model_copy(update={"project_id": project_id})
            key = self._dedupe_key(paper)
            if key in seen:
                continue
            seen.add(key)
            persisted, _ = self._persist(paper)
            outcome.papers.append(persisted)

        if not outcome.papers:
            outcome.diagnostics.append(
                "No papers were found; downstream reading is blocked instead of inventing records."
            )
        self.store.append_event(
            "papers.search_completed",
            {
                "queries": queries,
                "paper_ids": [paper.paper_id for paper in outcome.papers],
                "diagnostics": outcome.diagnostics,
            },
            project_id=project_id,
            actor="paper_search",
        )
        return outcome
