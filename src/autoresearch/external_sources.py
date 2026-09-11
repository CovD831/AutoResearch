"""S3-B Real Data Sources & Parsing Layer (B5).

Live Crossref verification, docling-first PDF parsing, and the gold-set
evaluation metrics that A5 consumes. This module owns no evidence: every parsed
or fetched item leaves as an
:class:`autoresearch.pipeline_contracts.EvidenceCandidate` and is admitted only
through :class:`autoresearch.evidence.EvidenceService`. Retraction and
correction facts are projected into B3 resolver-snapshot material, never a
direct evidence write and never a claim-truth judgment in this layer.

Selection is frozen by ADR-01 (``docs/coord/adr-01-external-integrations.md``):
Crossref REST is the retraction/correction source. Retraction Watch is merged
into Crossref's relation arrays, where ``updated-by[]`` marks *this* work as the
retracted/corrected target and ``update-to[]`` marks it as the updater (i.e. the
notice); the resolver reads both accordingly. docling (MIT) is the default PDF parser with
pymupdf4llm (AGPL) as a lightweight fallback. Live network calls are now in
scope: the adapter performs real HTTP when a transport is available and falls
back to an offline snapshot, then to ``unknown``, in that order.
"""

from __future__ import annotations

import re
from enum import StrEnum

import httpx
from pydantic import BaseModel, Field

from autoresearch.contracts import (
    EvidenceGrade,
    EvidenceType,
)
from autoresearch.evidence import EvidenceService
from autoresearch.pipeline_contracts import (
    EvidenceAdmissionResult,
    EvidenceCandidate,
)

# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------


class SourceStatus(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    RETRACTED = "retracted"
    CORRECTED = "corrected"
    UNKNOWN = "unknown"


class TransportOutcome(StrEnum):
    """Why a live lookup could not produce a definitive verdict."""

    OK = "ok"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"


class ParseStatus(StrEnum):
    OK = "ok"
    UNKNOWN = "unknown"
    EMPTY = "completed_empty"


# ---------------------------------------------------------------------------
# Offline resolver snapshots (fallback before unknown)
# ---------------------------------------------------------------------------


class SourceRecord(BaseModel):
    doi: str
    title: str | None = Field(default=None, max_length=300)
    status: SourceStatus = SourceStatus.FOUND
    related_dois: list[str] = Field(default_factory=list)
    year: int | None = None
    source_uri: str | None = None


class SourceSnapshot(BaseModel):
    version: str = Field(min_length=1, max_length=100)
    available: bool = True
    records: list[SourceRecord] = Field(default_factory=list)
    provider: str = "local-snapshot"


class DoiVerdict(BaseModel):
    doi: str
    status: SourceStatus
    title: str | None = None
    related_dois: list[str] = Field(default_factory=list)
    year: int | None = None
    source_uri: str | None = None
    transport: TransportOutcome = TransportOutcome.OK
    reasons: list[str] = Field(default_factory=list)


def _normalize_doi(value: str) -> str:
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", value.strip()).strip().casefold()


def _lookup(doi: str, snapshot: SourceSnapshot | None) -> SourceRecord | None:
    if snapshot is None:
        return None
    normalized = _normalize_doi(doi)
    for record in snapshot.records:
        if _normalize_doi(record.doi) == normalized:
            return record
    return None


# ---------------------------------------------------------------------------
# Live Crossref client (transport-neutral)
# ---------------------------------------------------------------------------


class CrossrefClient:
    """Thin httpx wrapper around the Crossref REST works endpoint.

    Polite-pool etiquette: a ``User-Agent`` with a contact ``mailto`` and no
    burst request rate. ``mailto`` defaults to the reserved invalid domain so
    no real address is required; callers may pass a real one.
    """

    def __init__(
        self,
        *,
        mailto: str = "b5@example.invalid",
        timeout_seconds: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.mailto = mailto
        self.timeout_seconds = timeout_seconds
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout_seconds,
            headers={"User-Agent": f"AutoResearch-B5/0.1 (mailto:{mailto})"},
        )

    def get_work(self, doi: str) -> tuple[TransportOutcome, dict | None]:
        url = f"https://api.crossref.org/works/{doi}"
        try:
            response = self._client.get(url)
        except httpx.TimeoutException:
            return TransportOutcome.TIMEOUT, None
        except httpx.RequestError:
            return TransportOutcome.UNAVAILABLE, None
        if response.status_code == 429:
            return TransportOutcome.RATE_LIMITED, None
        if response.status_code == 404:
            # Crossref returns 404 for an unknown DOI: deterministic not-found.
            return TransportOutcome.OK, {"status": "not_found"}
        if response.status_code != 200:
            return TransportOutcome.UNAVAILABLE, None
        try:
            message = response.json().get("message", {})
        except ValueError:
            return TransportOutcome.PARTIAL, None
        return TransportOutcome.OK, message


class CrossrefAdapter:
    """DOI verdict resolver: live Crossref first, offline snapshot fallback.

    A live 404 is deterministic ``not_found``. A partial or missing message
    field is ``partial`` and downgrades to the snapshot. Rate-limit, timeout,
    and unavailable results downgrade to the snapshot, then to ``unknown`` so
    the caller never receives a fabricated verdict.
    """

    def __init__(
        self,
        *,
        client: CrossrefClient | None = None,
        snapshot: SourceSnapshot | None = None,
    ):
        self.client = client
        self.snapshot = snapshot

    def resolve(self, doi: str) -> DoiVerdict:
        live: tuple[TransportOutcome, dict | None] | None = None
        if self.client is not None:
            outcome, message = self.client.get_work(doi)
            live = (outcome, message)
            verdict = self._from_live(doi, outcome, message)
            if verdict is not None:
                return verdict
        return self._from_fallback(doi, live)

    def _from_live(
        self, doi: str, outcome: TransportOutcome, message: dict | None
    ) -> DoiVerdict | None:
        if outcome is not TransportOutcome.OK or message is None:
            return None
        if message.get("status") == "not_found":
            return DoiVerdict(
                doi=doi,
                status=SourceStatus.NOT_FOUND,
                transport=TransportOutcome.OK,
                reasons=["crossref 404: doi does not exist"],
            )

        # Crossref relation direction (verified against the live API, 2026-09-11):
        #   update-to[]  -> the works *this* work updated  (this work is the updater)
        #   updated-by[] -> the works that updated *this* work (this work is the target)
        # "This DOI has been retracted" therefore lives in updated-by[], NOT
        # update-to[]. Reading update-to[] inverted the verdict: a retraction
        # notice was reported as `retracted` while the retracted article itself was
        # reported as `found` -- the exact failure this layer exists to prevent.
        updated_by = message.get("updated-by") or []
        update_to = message.get("update-to") or []
        retracted_by = [item for item in updated_by if item.get("type") == "retraction"]
        corrected_by = [item for item in updated_by if item.get("type") == "correction"]
        # Relation neighbourhood in either direction is provenance B3 may keep.
        related = _related_dois(updated_by, update_to)

        if retracted_by:
            first = retracted_by[0]
            return DoiVerdict(
                doi=doi,
                status=SourceStatus.RETRACTED,
                title=_first(message.get("title")),
                related_dois=related,
                year=_year(message),
                source_uri=_doi_uri(doi),
                reasons=[
                    "retraction recorded against this doi by "
                    f"{(first.get('source') or 'crossref')} ({first.get('DOI') or 'unknown doi'})"
                ],
            )
        if corrected_by:
            first = corrected_by[0]
            return DoiVerdict(
                doi=doi,
                status=SourceStatus.CORRECTED,
                title=_first(message.get("title")),
                related_dois=related,
                year=_year(message),
                source_uri=_doi_uri(doi),
                reasons=[
                    "correction recorded against this doi by "
                    f"{(first.get('source') or 'crossref')} ({first.get('DOI') or 'unknown doi'})"
                ],
            )

        # A work whose own update-to[] carries a retraction/correction is the
        # *notice*, not the affected article: it exists and is citable, so it
        # stays `found`, with the relation recorded as a reason.
        reasons: list[str] = []
        notices = [
            item for item in update_to if item.get("type") in {"retraction", "correction"}
        ]
        if notices:
            notice = notices[0]
            reasons.append(
                f"this work is a {notice.get('type')} notice for "
                f"{notice.get('DOI') or 'unknown doi'}"
            )
        # Relation kinds outside the frozen B5 scope (retraction/correction) --
        # e.g. expression-of-concern, removal -- do not change the verdict, but
        # they are research-integrity signals and must not vanish silently.
        other_kinds = sorted(
            {
                str(item.get("type"))
                for item in (updated_by + update_to)
                if item.get("type") not in {"retraction", "correction"}
            }
        )
        if other_kinds:
            reasons.append("other update relations present: " + ", ".join(other_kinds))
        return DoiVerdict(
            doi=doi,
            status=SourceStatus.FOUND,
            title=_first(message.get("title")),
            related_dois=related,
            year=_year(message),
            source_uri=_doi_uri(doi),
            reasons=reasons,
        )

    def _from_fallback(
        self, doi: str, live: tuple[TransportOutcome, dict | None] | None
    ) -> DoiVerdict:
        if self.snapshot is not None and self.snapshot.available:
            record = _lookup(doi, self.snapshot)
            if record is not None:
                return DoiVerdict(
                    doi=record.doi,
                    status=record.status,
                    title=record.title,
                    related_dois=record.related_dois,
                    year=record.year,
                    source_uri=record.source_uri,
                    transport=(live[0] if live else TransportOutcome.OK),
                    reasons=(
                        [f"live transport {live[0].value}; served from snapshot"] if live else []
                    ),
                )
        return DoiVerdict(
            doi=doi,
            status=SourceStatus.UNKNOWN,
            transport=(live[0] if live else TransportOutcome.UNAVAILABLE),
            reasons=[
                f"live transport {live[0].value}; no snapshot record" if live else "no resolver"
            ],
        )

    def resolver_record(
        self, doi: str, verdict: DoiVerdict | None = None
    ) -> dict[str, object] | None:
        """Project a DOI verdict into B3 ResolverRecord territory.

        Reuses an already-resolved ``verdict`` when supplied (avoids a second
        network call); otherwise resolves once. A verdict that is undecidable
        (``unknown``) or provably non-existent (``not_found``) yields ``None`` so
        callers stay fail-closed: projecting a 404 as ``current`` would let B3
        read a broken citation as a live, valid source.
        """

        if verdict is None:
            verdict = self.resolve(doi)
        if verdict.status in {SourceStatus.UNKNOWN, SourceStatus.NOT_FOUND}:
            return None
        return {
            "source_id": doi,
            "source_uri": verdict.source_uri,
            "title": verdict.title,
            "status": (
                "retracted"
                if verdict.status is SourceStatus.RETRACTED
                else "corrected"
                if verdict.status is SourceStatus.CORRECTED
                else "current"
            ),
            "related_source_ids": verdict.related_dois,
        }


def _related_dois(*relation_groups: list) -> list[str]:
    """Collect related DOIs from Crossref relation arrays.

    Retraction relations come first: for a retracted article the strongest
    provenance is the notice that retracted it, and B3 consumes this order.
    Within a priority the API order is preserved (``sort`` is stable).
    """

    items = [item for group in relation_groups for item in (group or [])]
    items.sort(key=lambda item: 0 if item.get("type") == "retraction" else 1)
    seen: list[str] = []
    for item in items:
        value = str(item.get("DOI", "")).strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def _first(values: object) -> str:
    if isinstance(values, list) and values:
        return str(values[0])
    return ""


def _year(message: dict) -> int | None:
    issued = message.get("issued") or {}
    parts = issued.get("date-parts") or []
    if parts and parts[0]:
        return int(parts[0][0])
    return None


def _doi_uri(doi: str) -> str:
    return f"https://doi.org/{re.sub(r'^https?://(dx\\.)?doi\\.org/', '', doi.strip())}"


# ---------------------------------------------------------------------------
# PDF parsing layer (docling-first, pymupdf4llm fallback)
# ---------------------------------------------------------------------------


class ParseResult(BaseModel):
    parser: str
    markdown: str = ""
    locators: list[str] = Field(default_factory=list)
    status: ParseStatus = ParseStatus.UNKNOWN
    diagnostics: list[str] = Field(default_factory=list)


def _try_docling(path_value: str) -> tuple[tuple[str, list[str]] | None, str | None]:
    """Attempt docling. Returns ``(payload, diagnostic)``.

    A ``None`` payload with a diagnostic distinguishes "package absent" from
    "package present but parsing failed" -- the latter must reach the caller
    instead of disappearing into an unconditional fallback.
    """

    try:
        from docling.document_converter import DocumentConverter  # type: ignore
    except Exception as exc:
        return None, f"docling unavailable ({type(exc).__name__})"
    try:
        result = DocumentConverter().convert(path_value)
        markdown = result.document.export_to_markdown()
        pages = list(result.document.pages.keys()) if result.document.pages else []
        return (markdown, [f"p.{page}" for page in pages]), None
    except Exception as exc:
        return None, f"docling failed ({type(exc).__name__}: {str(exc)[:200]})"


def _try_pymupdf4llm(
    path_value: str,
) -> tuple[tuple[str, list[str]] | None, str | None]:
    try:
        import pymupdf4llm  # type: ignore
    except Exception as exc:
        return None, f"pymupdf4llm unavailable ({type(exc).__name__})"
    try:
        markdown = pymupdf4llm.to_markdown(path_value)
        # pymupdf4llm exposes no page locators. Returning none is deliberate:
        # an invented locator would sail past the admission check, whereas an
        # empty locator list makes the downstream admission fail closed.
        return (markdown, []), None
    except Exception as exc:
        return None, f"pymupdf4llm failed ({type(exc).__name__}: {str(exc)[:200]})"


class PdfParser:
    """docling-first, pymupdf4llm-fallback parser.

    Both backends are optional imports. Unavailability yields ``unknown``,
    never fabricated text. Every unavailable/failed attempt contributes a
    diagnostic, so using the AGPL pymupdf4llm fallback records *why* the
    permissive default was not used (receipt trail requirement).
    """

    def parse(self, path_value: str) -> ParseResult:
        docling_payload, docling_diag = _try_docling(path_value)
        if docling_payload is not None:
            markdown, locators = docling_payload
            return ParseResult(
                parser="docling",
                markdown=markdown,
                locators=locators,
                status=ParseStatus.OK if markdown else ParseStatus.EMPTY,
            )

        pymupdf_payload, pymupdf_diag = _try_pymupdf4llm(path_value)
        if pymupdf_payload is not None:
            markdown, locators = pymupdf_payload
            diagnostics = [f"AGPL fallback enabled for {path_value}"]
            if docling_diag is not None:
                diagnostics.append(docling_diag)
            return ParseResult(
                parser="pymupdf4llm",
                markdown=markdown,
                locators=locators,
                status=ParseStatus.OK if markdown else ParseStatus.EMPTY,
                diagnostics=diagnostics,
            )

        diagnostics = [d for d in (docling_diag, pymupdf_diag) if d]
        diagnostics.append(f"no PDF parser available for {path_value}")
        return ParseResult(
            parser="unavailable",
            status=ParseStatus.UNKNOWN,
            diagnostics=diagnostics,
        )


# ---------------------------------------------------------------------------
# Candidate-only egress
# ---------------------------------------------------------------------------


class ParseEgress:
    """Bridge a ParseResult into the candidate channel.

    The sole path from parsing to evidence: constructs an ``EvidenceCandidate``
    (never an ``EvidenceItem``) and delegates admission to the passed
    ``evidence`` service, which owns the actual write.
    """

    def __init__(self, evidence: EvidenceService | None = None):
        self.evidence = evidence

    def candidate(
        self,
        *,
        project_id: str,
        source_id: str,
        result: ParseResult,
        locator: str | None = None,
        source_uri: str | None = None,
    ) -> EvidenceCandidate:
        """Build the candidate for a parse result.

        ``locator``/``source_uri`` let the caller supply real provenance (for
        example a ``LocalDocument`` page map or the resolved DOI landing page)
        when the parser yields none. When neither is available the locator stays
        ``None`` so admission fails closed -- an unlocatable item must not be
        admitted by inventing a placeholder locator.
        """

        status = result.status
        resolved_locator = locator or (result.locators[0] if result.locators else None)
        return EvidenceCandidate(
            project_id=project_id,
            evidence_type=EvidenceType.PAPER,
            grade=EvidenceGrade.E1,
            title=f"Parsed document: {source_id}",
            claim=result.markdown[:500] if result.markdown else "",
            source_id=source_id,
            source_uri=source_uri,
            locator=resolved_locator,
            checksum=None,
            independent_source=source_id,
            adapter=f"pdf_parser.{result.parser}",
            adapter_version="0.1",
            metadata={
                "parser": result.parser,
                "status": status.value,
                "diagnostics": result.diagnostics,
                "locator_count": len(result.locators),
            },
        )

    def admit(
        self,
        *,
        project_id: str,
        source_id: str,
        result: ParseResult,
        actor: str = "data_sources",
        locator: str | None = None,
        source_uri: str | None = None,
    ) -> EvidenceAdmissionResult:
        if self.evidence is None:
            raise ValueError("admission requires EvidenceService")
        return self.evidence.admit_candidate(
            self.candidate(
                project_id=project_id,
                source_id=source_id,
                result=result,
                locator=locator,
                source_uri=source_uri,
            ),
            actor=actor,
        )


# ---------------------------------------------------------------------------
# Gold set and ScholarQABench-aligned metrics
# ---------------------------------------------------------------------------


class GoldCitation(BaseModel):
    citation_id: str
    doi: str | None = None
    cited: bool = False  # whether the system emitted this citation
    expected: bool = True  # whether the gold set expects this citation


class GoldSetItem(BaseModel):
    query_id: str
    citations: list[GoldCitation] = Field(default_factory=list)


class EvalMetrics(BaseModel):
    query_id: str
    total_cited: int = 0
    resolvable: int = 0
    hallucinated: int = 0  # cited works that provably do not exist
    undetermined: int = 0  # cited works the resolver could not decide
    hallucination_ratio: float | None = None
    undetermined_ratio: float | None = None
    citation_recall: float | None = None
    citation_precision: float | None = None
    attribution_note: str = ""


def _ratio(numerator: int, denominator: int) -> float | None:
    return (numerator / denominator) if denominator else None


def hallucination_ratio(resolved_statuses: list[SourceStatus]) -> float | None:
    """Share of cited papers that provably do not exist (ScholarQABench).

    Only ``not_found`` counts as a hallucination. ``unknown`` -- rate limit,
    timeout, unavailability -- is reported separately by
    :func:`undetermined_ratio`, because folding an infrastructure failure into
    this figure would let network weather move the primary metric A5 adjudicates
    on. The NLI "attributable" judge remains a separate model-assisted layer.
    """

    if not resolved_statuses:
        return None
    missing = sum(1 for status in resolved_statuses if status is SourceStatus.NOT_FOUND)
    return float(missing) / len(resolved_statuses)


def undetermined_ratio(resolved_statuses: list[SourceStatus]) -> float | None:
    """Share of cited papers the resolver could not decide (transport failure)."""

    if not resolved_statuses:
        return None
    undecided = sum(1 for status in resolved_statuses if status is SourceStatus.UNKNOWN)
    return float(undecided) / len(resolved_statuses)


def eval_item(
    item: GoldSetItem,
    *,
    resolver_statuses: dict[str, SourceStatus],
    attributable: dict[str, bool] | None = None,
) -> EvalMetrics:
    """Compute the ScholarQABench-aligned metrics for one query.

    ``resolver_statuses`` maps citation id to the Crossref verdict status.
    ``attributable`` is an optional NLI judge output: ``True`` means the cited
    passage supports the claim it is attached to.

    The metrics measure different things and are not interchangeable:

    - ``hallucination_ratio`` counts only cited works that provably do not exist
      (``not_found``); transport failures are reported separately as
      ``undetermined_ratio``, keeping the primary metric independent of network
      conditions.
    - ``citation_recall`` is coverage of the gold set: of the citations the gold
      set expects, how many did the system actually emit. It needs no judge.
    - ``citation_precision`` is the share of the system's citations that the NLI
      judge found attributable, and is ``None`` without that judgment.
    """

    cited = [c for c in item.citations if c.cited]
    total_cited = len(cited)
    statuses = [resolver_statuses.get(c.citation_id, SourceStatus.NOT_FOUND) for c in cited]
    resolvable = sum(
        1
        for s in statuses
        if s in {SourceStatus.FOUND, SourceStatus.CORRECTED, SourceStatus.RETRACTED}
    )
    hallucinated = sum(1 for s in statuses if s is SourceStatus.NOT_FOUND)
    undetermined = sum(1 for s in statuses if s is SourceStatus.UNKNOWN)

    expected = [c for c in item.citations if c.expected]
    recall = _ratio(sum(1 for c in expected if c.cited), len(expected))

    precision: float | None = None
    note = ""
    if attributable is not None and cited:
        precision = _ratio(
            sum(1 for c in cited if attributable.get(c.citation_id, False)),
            total_cited,
        )
    else:
        note = (
            "citation precision requires an NLI 'attributable' judgment; "
            "supply `attributable` to compute it"
        )

    return EvalMetrics(
        query_id=item.query_id,
        total_cited=total_cited,
        resolvable=resolvable,
        hallucinated=hallucinated,
        undetermined=undetermined,
        hallucination_ratio=_ratio(hallucinated, total_cited),
        undetermined_ratio=_ratio(undetermined, total_cited),
        citation_recall=recall,
        citation_precision=precision,
        attribution_note=note,
    )
