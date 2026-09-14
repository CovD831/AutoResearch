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
    #: True when at least one retrieval source failed to answer. Callers must not
    #: infer this from ``diagnostics``: prose is not a contract, and the previous
    #: revision "fixed" a failure/zero-hit confusion by rewording a message that
    #: no consumer read. A caller that treats "no papers" as "go find evidence"
    #: has to branch on this flag, not on text.
    provider_failure: bool = False
    #: How many retrieved records were refused for having no DOI, URL or provider
    #: id (F4). A count rather than a sentence, for the same reason as above: a
    #: record silently disappearing from the run must be visible to the operator,
    #: and a diagnostic string is not a decision input.
    refused_records: int = 0


# --------------------------------------------------------------------------- #
# Bibliographic persistence — one implementation, shared by both search paths
# --------------------------------------------------------------------------- #
#
# The legacy connector path (``PaperSearchService``) and the adapter path
# (``AdapterBackedPaperSearchService``) must produce identical durable facts for
# the same record: A1's parity report asserts ``durable_facts_equal``. That
# invariant was previously maintained by copy-paste, which is how a claim about
# an abstract that did not exist survived in both places. Extracting the single
# implementation makes parity structural instead of a thing two editors have to
# remember.


def evidence_claim_for(paper: PaperRecord) -> str:
    """Claim only what the record actually carries (F4).

    The previous wording asserted "this scholarly record **and its supplied
    abstract** exist in the cited source" for every hit. When a provider supplied
    no abstract, the wiki page written in the same call said ``No abstract was
    supplied.`` -- two contradictory statements about one record. A claim has to
    describe the material at hand.
    """

    if paper.abstract:
        return "This scholarly record and its supplied abstract exist in the cited source."
    return "This scholarly record exists in the cited source."


def independent_source_for(paper: PaperRecord) -> str | None:
    """A provenance string that identifies the record, or ``None``.

    ``f"{source}:{source_record_id}"`` degraded to ``"s:None"`` when a hit carried
    no DOI, URL or provider id -- a provenance string that identifies nothing.
    Returning ``None`` lets the caller refuse the record rather than mint evidence
    whose provenance is a lie.
    """

    if paper.doi:
        return f"doi:{paper.doi}"
    if paper.url:
        return paper.url
    if paper.source_record_id:
        return f"{paper.source}:{paper.source_record_id}"
    return None


def persist_bibliographic_record(
    store: RecordStore,
    evidence: EvidenceService,
    knowledge: KnowledgeService,
    paper: PaperRecord,
    *,
    actor: str,
    require_provenance: bool = False,
) -> tuple[PaperRecord, EvidenceItem] | None:
    """Persist a record plus its bibliographic evidence, or refuse it.

    Returns ``None`` when attribution is required and the record has none. A
    retrieved hit with no DOI, URL or provider id cannot support the claim "this
    record exists in the cited source", and minting an E1 item for it would let
    unverifiable material feed the gate (F4).

    ``require_provenance`` defaults to ``False`` because *the caller owns this
    decision*: only ``search`` knows whether a record came from a provider or from
    the user's own seed file, and a user seed's provenance is that file. Callers
    that pass retrieved hits must either pass ``True`` or check
    ``independent_source_for`` themselves; ``search`` does the latter so that
    ``_persist`` keeps the ``(paper)`` signature A2's crash injection patches.
    """

    independent_source = independent_source_for(paper)
    if independent_source is None and require_provenance:
        return None
    if independent_source is None:
        independent_source = f"user_supplied:{paper.source}"
    store.put(
        "paper",
        paper.paper_id,
        paper,
        project_id=paper.project_id,
        partition=KnowledgePartition.PAPERS.value,
    )
    item = evidence.add(
        EvidenceItem(
            project_id=paper.project_id,
            evidence_type=EvidenceType.PAPER,
            grade=EvidenceGrade.E1,
            title=f"Bibliographic record: {paper.title}",
            claim=evidence_claim_for(paper),
            source_uri=paper.url,
            source_id=paper.paper_id,
            locator="bibliographic record/abstract" if paper.abstract else "bibliographic record",
            independent_source=independent_source,
            metadata={
                "paper_id": paper.paper_id,
                "source": paper.source,
                "abstract_present": bool(paper.abstract),
                "user_supplied": independent_source.startswith("user_supplied:"),
            },
        ),
        actor=actor,
    )
    knowledge.add_page(
        WikiPage(
            page_id=paper.paper_id,
            project_id=paper.project_id,
            partition=KnowledgePartition.PAPERS,
            title=paper.title,
            body=paper.abstract or "No abstract was supplied.",
            tags=[paper.source, str(paper.year or "")],
            evidence_ids=[item.evidence_id],
            level=1,
        )
    )
    return paper, item


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

    def _persist(self, paper: PaperRecord) -> tuple[PaperRecord, EvidenceItem] | None:
        """Delegate to the shared bibliographic writer.

        Both search paths must produce identical durable facts (A1 parity:
        ``durable_facts_equal``), so the implementation lives in one place and
        this method only supplies the actor label.

        The provenance requirement is decided by the *caller* (``search``) rather
        than passed in here, so this signature stays ``(paper)``: A2's fault
        matrix overrides ``_persist(self, paper)`` to crash the child process
        after durable facts are written, and widening the signature would make
        that injection silently stop firing.
        """

        return persist_bibliographic_record(
            self.store, self.evidence, self.knowledge, paper, actor="paper_search"
        )

    def search(
        self,
        project_id: str,
        queries: list[str],
        *,
        seed_papers: list[PaperRecord] | None = None,
        per_connector_limit: int = 5,
    ) -> SearchOutcome:
        outcome = SearchOutcome()
        #: Mirrors the adapter path: any connector that did not answer is a fact
        #: the caller must be able to see, whether or not other connectors
        #: returned results (N1). Without this the legacy path recorded failures
        #: only as diagnostic text while the adapter path carried them as data.
        failed = False
        #: (record, user_supplied). A user seed's provenance is the user's own
        #: file, so a missing DOI must not disqualify it -- only retrieved hits
        #: have to be attributable to a source.
        candidates: list[tuple[PaperRecord, bool]] = [
            (paper, True) for paper in (seed_papers or [])
        ]
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
                                (
                                    PaperRecord(
                                        project_id=project_id, source=connector.name, **raw
                                    ),
                                    False,
                                )
                            )
                    except Exception as exc:
                        failed = True
                        outcome.diagnostics.append(
                            f"{connector.name} failed for query {query!r}: {type(exc).__name__}"
                        )

        seen: set[str] = set()
        for paper, user_supplied in candidates:
            if paper.project_id != project_id:
                paper = paper.model_copy(update={"project_id": project_id})
            key = self._dedupe_key(paper)
            if key in seen:
                continue
            seen.add(key)
            # Provenance is required for retrieved hits only (F4). Decided here,
            # not inside _persist, so A2's crash-injection override keeps its
            # ``_persist(self, paper)`` signature and stays live.
            if not user_supplied and independent_source_for(paper) is None:
                outcome.refused_records += 1
                outcome.diagnostics.append(
                    f"record {paper.title!r} was refused: it carries no DOI, URL or "
                    "provider id, so no bibliographic claim can be made about it"
                )
                continue
            persisted = self._persist(paper)
            if persisted is None:
                outcome.refused_records += 1
                outcome.diagnostics.append(
                    f"record {paper.title!r} was refused by the persistence writer"
                )
                continue
            outcome.papers.append(persisted[0])

        if not outcome.papers:
            outcome.diagnostics.append(
                "No papers were found; downstream reading is blocked instead of inventing records."
            )
        outcome.provider_failure = failed
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
