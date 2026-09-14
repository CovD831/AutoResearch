"""Mainline paper search backed by the A5 real retrieval adapters.

Why this module exists
----------------------
The mainline used to search through ``search_service.PaperSearchService``, whose
Semantic Scholar connector is a bare ``httpx.get`` with no headers and no API
key. Anonymous access to that endpoint answers HTTP 429, so the primary source
failed on every real run while the failure was swallowed into diagnostics
(``D-A5-偏离-1``). The A5 package delivered a proper adapter -- API key in a
header, explicit rate-limit accounting, fail-closed when credentials are
missing -- but could not wire it in, because ``application.py`` and
``search_service.py`` are both listed in its ``forbidden_paths``.

This service closes that gap. It satisfies the same ``PaperSearchServicePort``
the mainline already consumes, so ``PaperSearchCapabilityAdapter`` (the A4
idempotency/replay/recovery boundary) keeps working unchanged.

Two deliberate design points
----------------------------
1. **It calls ``retrieve()``, not ``invoke()``.** The candidate-only contract
   boundary reduces the abstract to an ``abstract_present`` boolean, and the
   reader degrades to title-only without an abstract (``reader_service.py``:
   ``source_text = full_text or paper.abstract`` then falls back to the title).
   Routing the mainline through candidates would silently degrade every reading
   card, which is exactly the "record an unknown/absent input as a normal value"
   defect family this project keeps tripping over. The raw primitive is the
   correct seam for a caller that needs the material.

2. **It reproduces the legacy persistence side effects.** ``PaperReaderAgent``
   resolves papers by ``paper_id`` out of the store, so a service that only
   returned records without persisting them would break the mainline one hop
   later. Paper record + E1 evidence item + wiki page are all written here, with
   the same shapes the legacy path used.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

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
from autoresearch.search_adapters import (
    RetrievalError,
    RetrievalRateLimited,
    RetrievalUnavailable,
    SearchAdapterRequest,
    build_search_adapters,
)
from autoresearch.search_service import SearchOutcome
from autoresearch.storage import RecordStore


class AdapterBackedPaperSearchService:
    """``PaperSearchServicePort`` implementation over the A5 retrieval adapters.

    The constructor signature mirrors the legacy service so the swap in
    ``application.py`` stays a one-line change; ``adapters`` is an injection seam
    for tests and for callers that already built a registry.
    """

    def __init__(
        self,
        store: RecordStore,
        evidence: EvidenceService,
        knowledge: KnowledgeService,
        *,
        settings: Any | None = None,
        adapters: dict[str, Any] | None = None,
        network_enabled: bool = False,
        actor: str = "paper_search",
    ) -> None:
        self.store = store
        self.evidence = evidence
        self.knowledge = knowledge
        self.actor = actor
        #: Mirrors the legacy service: when the network is disabled the caller
        #: still gets its seed papers processed, but no provider is contacted.
        #: This is a deliberate offline mode, not a silent degradation -- the
        #: diagnostic below states which mode ran.
        self.network_enabled = network_enabled
        self.adapters = (
            adapters if adapters is not None else build_search_adapters(settings=settings)
        )

    # -- persistence (mirrors PaperSearchService._persist) ------------------ #

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
                claim=(
                    "This scholarly record and its supplied abstract exist in the cited source."
                ),
                source_uri=paper.url,
                source_id=paper.paper_id,
                locator="bibliographic record/abstract",
                independent_source=independent_source,
                metadata={"paper_id": paper.paper_id, "source": paper.source},
            ),
            actor=self.actor,
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

    def _to_record(self, project_id: str, source: str, hit: Any) -> PaperRecord:
        """``RetrievedPaper`` -> ``PaperRecord``.

        Every field maps one-to-one; nothing is dropped, and the abstract travels
        with the record so the reader is not reduced to title-only.
        """

        return PaperRecord(
            project_id=project_id,
            title=hit.title,
            abstract=hit.abstract,
            authors=list(hit.authors),
            year=hit.year,
            doi=hit.doi,
            url=hit.url,
            source=source,
            source_record_id=hit.source_record_id,
        )

    # -- PaperSearchServicePort -------------------------------------------- #

    def search(
        self,
        project_id: str,
        queries: list[str],
        *,
        seed_papers: list[PaperRecord] | None = None,
        per_connector_limit: int = 5,
    ) -> SearchOutcome:
        outcome = SearchOutcome()
        candidates: list[tuple[str, Any]] = [
            (paper.source, paper) for paper in (seed_papers or [])
        ]
        #: Any provider call that did not complete. Tracked separately from "no
        #: hits" because reporting a failed retrieval as an empty result makes the
        #: downstream WAITING_EVIDENCE decision indistinguishable from a genuine
        #: zero-hit outcome (the "unknown recorded as a normal value" family).
        failed = False
        if not self.network_enabled:
            outcome.diagnostics.append(
                "Network search is disabled; only user-supplied seed papers were processed."
            )
        else:
            # The source set is a behaviour, not an implementation detail: the
            # legacy path queried openalex + crossref + semantic_scholar while the
            # adapter path queries semantic_scholar + arxiv + openalex (ADR-01
            # slot 2, A5's D-A5-03). Crossref is no longer queried. Recording the
            # set makes a silent composition change visible in the run's own
            # diagnostics instead of only in a diff.
            outcome.diagnostics.append(
                f"Retrieval sources for this run: {', '.join(sorted(self.adapters))}"
            )
            for query in queries:
                for source, adapter in self.adapters.items():
                    request = SearchAdapterRequest(
                        project_id=project_id,
                        run_id=f"mainline-search:{project_id}",
                        invocation_id=f"q-{source}-{_fingerprint_text(query)}",
                        query=query,
                        limit=per_connector_limit,
                    )
                    try:
                        for hit in adapter.retrieve(request):
                            candidates.append((source, hit))
                    except RetrievalRateLimited as exc:
                        failed = True
                        outcome.diagnostics.append(
                            f"{source} rate limited for query {query!r}: {_safe_exc(exc)}"
                        )
                    except RetrievalUnavailable as exc:
                        failed = True
                        outcome.diagnostics.append(
                            f"{source} outcome unknown for query {query!r}: {_safe_exc(exc)}"
                        )
                    except RetrievalError as exc:
                        failed = True
                        outcome.diagnostics.append(
                            f"{source} failed for query {query!r}: {_safe_exc(exc)}"
                        )
                    except Exception as exc:
                        # Only non-fatal exceptions are absorbed. A MemoryError or a
                        # KeyboardInterrupt-shaped control-flow error is not a
                        # provider failure and must not be recorded as one.
                        if _is_fatal(exc):
                            raise
                        failed = True
                        outcome.diagnostics.append(
                            f"{source} failed for query {query!r}: {_safe_exc(exc)}"
                        )

        seen: set[str] = set()
        for source, item in candidates:
            if isinstance(item, PaperRecord):
                paper = item
                if paper.project_id != project_id:
                    paper = paper.model_copy(update={"project_id": project_id})
            else:
                paper = self._to_record(project_id, source, item)
            key = self._dedupe_key(paper)
            if key in seen:
                continue
            seen.add(key)
            persisted, _ = self._persist(paper)
            outcome.papers.append(persisted)

        if not outcome.papers:
            # Two different situations must not collapse into one decision. The
            # flag is what a caller branches on; the wording is for humans. An
            # earlier revision changed only the wording and asserted on it, which
            # left the actual decision unaffected -- see
            # ``test_provider_failure_flag_drives_the_agent_decision``.
            if failed:
                outcome.provider_failure = True
                outcome.diagnostics.append(
                    "No papers were registered because every provider call failed; "
                    "this is not a zero-hit result."
                )
            else:
                outcome.diagnostics.append(
                    "No papers were found; downstream reading is blocked instead of inventing "
                    "records."
                )
        else:
            outcome.provider_failure = failed
        self.store.append_event(
            "papers.search_completed",
            {
                "queries": queries,
                "paper_ids": [paper.paper_id for paper in outcome.papers],
                "diagnostics": outcome.diagnostics,
            },
            project_id=project_id,
            actor=self.actor,
        )
        return outcome

    def rate_limit_summary(self) -> dict[str, object]:
        """Per-source limit monitor across every adapter the mainline used."""

        return {source: adapter.rate_limit_summary() for source, adapter in self.adapters.items()}


def _safe_exc(exc: BaseException) -> str:
    """Exception summary safe to persist into the audit trail.

    Only the type name travels. The legacy connector did exactly this and the
    reason is worth keeping: an exception message is attacker-influenced text
    that routinely carries an echoed request -- API keys in a header, tokens in a
    URL -- and diagnostics are written to ``audit_events.payload_json``, which is
    durable. An earlier revision of this module interpolated ``{exc}`` and a probe
    showed a credential string reaching the database.
    """

    return type(exc).__name__


def _is_fatal(exc: BaseException) -> bool:
    """Errors that must never be absorbed as a provider failure.

    ``MemoryError`` and ``RecursionError`` mean the process is in a state where
    the remaining work is not trustworthy; recording them as "the provider
    failed" would let a broken run finish as a plausible empty result.

    ``KeyboardInterrupt`` / ``SystemExit`` are deliberately **not** listed: they
    derive from ``BaseException``, not ``Exception``, so the ``except Exception``
    clause that calls this can never receive one. Listing them was dead code that
    read as protection without being any.
    """

    return isinstance(exc, (MemoryError, RecursionError))


def _fingerprint_text(query: str) -> str:
    """Stable, collision-resistant id fragment for one query.

    A plain ``re.sub(r"\\W+", "-", ...)`` is *not* injective -- ``"a b"`` and
    ``"a-b"`` collapse to the same string, as do ``"!!!"`` and ``"??"`` -- and a
    collision here means two different queries share an ``invocation_id``, so the
    A4 idempotency ledger replays the second query as the first. Hashing the raw
    query keeps distinct inputs distinct.
    """

    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
    slug = re.sub(r"\W+", "-", query.strip().lower())[:24].strip("-") or "query"
    return f"{slug}-{digest}"


__all__ = ["AdapterBackedPaperSearchService"]
