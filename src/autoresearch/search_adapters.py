"""Real scholarly retrieval adapters for the S4 benchmark runtime.

ADR-01 slot 2 fixed the selection as *Semantic Scholar API (free key) primary +
arXiv supplement*. Both adapters below are invoked **only** through the A4
``CapabilityRegistry`` (A5 TASK.md: the adapter must be registered, never called
bypassing the registry), so their hits reach the benchmark as
``EvidenceCandidate``s behind the operator-owned trust tier.

Design notes the acceptance matrix depends on:

* **Credentials stay out of the request.** The Semantic Scholar key is read from
  ``Settings`` and injected as a transport header. It is never part of the
  pydantic request object, so it cannot leak into ``request_fingerprint`` or a
  receipt.
* **Transport is injectable.** Tests drive the rate-limited / offline matrix with
  a fake transport, so the whole matrix runs without touching the network.
* **Outcome labels follow D-F8-01.** A rate-limited provider call is a *known*
  failure -- the query provably did not execute -- so it is ``failed``. A
  transport-level interruption (timeout, DNS failure, connection reset) leaves
  the provider outcome unknown, so it is ``unknown``. A successful call with zero
  hits is a deterministic success: ``completed`` with zero candidates, which is
  the ``completed_empty`` semantics of D-F8-01 (never ``unknown``).
* **Candidate-only by construction.** These adapters emit evidence candidates and
  return no structured value, so they are registered under
  ``CapabilityTrustTier.CANDIDATE_ONLY``. Consumers must read
  ``CapabilityInvocation.admissible_candidates`` -- never ``candidates`` -- per
  the D-S3-01 hard clause.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol
from xml.etree import ElementTree

import httpx
from pydantic import BaseModel, Field, SecretStr

from autoresearch.capability_registry import (
    CapabilityAdapterResult,
    CapabilityExecutionContext,
    CapabilityKind,
    CapabilityManifest,
    CapabilityReceiptStatus,
    CapabilityRegistrationView,
    CapabilityRegistry,
    CapabilityTrustTier,
)
from autoresearch.config import Settings, get_settings
from autoresearch.contracts import EvidenceCandidate

__all__ = [
    "ARXIV_SOURCE",
    "OPENALEX_SOURCE",
    "SEMANTIC_SCHOLAR_SOURCE",
    "ArxivSearchAdapter",
    "HttpxTransport",
    "OpenAlexSearchAdapter",
    "RetrievalCredentialsRequired",
    "RetrievalError",
    "RetrievalRateLimited",
    "RetrievalResponseError",
    "RetrievalTransport",
    "RetrievalUnavailable",
    "RetrievedPaper",
    "SearchAdapterRequest",
    "SemanticScholarSearchAdapter",
    "TransportResponse",
    "build_search_adapters",
    "register_search_adapters",
]

SEMANTIC_SCHOLAR_SOURCE = "semantic_scholar"
ARXIV_SOURCE = "arxiv"
OPENALEX_SOURCE = "openalex"

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_ARXIV_NS = "{http://arxiv.org/schemas/atom}"
_WHITESPACE = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TransportResponse:
    """The only part of an HTTP response the adapters are allowed to depend on."""

    status_code: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)


class RetrievalTransport(Protocol):
    """Minimal seam so the rate-limit / offline matrix needs no network."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> TransportResponse: ...


class HttpxTransport:
    """Default transport. Provider-unreachable conditions become ``unknown``."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> TransportResponse:
        try:
            response = httpx.get(url, params=params, headers=headers, timeout=timeout)
        except httpx.HTTPError as exc:
            raise RetrievalUnavailable(
                f"transport unavailable: {type(exc).__name__}"
            ) from exc
        return TransportResponse(
            status_code=response.status_code,
            text=response.text,
            headers={key.lower(): value for key, value in response.headers.items()},
        )


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class RetrievalError(RuntimeError):
    """Base class for retrieval failures that map onto a receipt status."""


class RetrievalCredentialsRequired(RetrievalError):
    """The provider needs an API key and none is configured; nothing was sent."""


class RetrievalRateLimited(RetrievalError):
    """The provider refused the call; the query did not execute.

    ``retry_after_seconds`` carries the provider's own back-off hint when it
    publishes one (OpenAlex and arXiv both do), which the limit monitor surfaces.
    """

    def __init__(self, message: str, *, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds



class RetrievalUnavailable(RetrievalError):
    """The provider outcome cannot be proven (timeout, DNS, 5xx, reset)."""


class RetrievalResponseError(RetrievalError):
    """The provider answered, but the response is not usable."""


# --------------------------------------------------------------------------- #
# Request / record shapes
# --------------------------------------------------------------------------- #


class SearchAdapterRequest(BaseModel):
    """Pydantic request so ``request_fingerprint`` stays deterministic (D-S3-01)."""

    project_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    invocation_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=100)


@dataclass(frozen=True, slots=True)
class RetrievedPaper:
    """Normalized hit, shared by both providers before candidate conversion."""

    title: str
    abstract: str = ""
    authors: tuple[str, ...] = ()
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    source_record_id: str | None = None

    def independent_source(self, provider: str) -> str:
        """Reproducible provenance string; never empty (contract requires >= 1)."""

        for value in (self.doi, self.url, self.source_record_id):
            if value:
                return str(value)
        return f"{provider}:{self.title}"


def _collapse(value: str | None) -> str:
    return _WHITESPACE.sub(" ", value or "").strip()


def _inverted_index_to_text(index: Any) -> str:
    """OpenAlex ships abstracts as {word: [positions]}; rebuild the plain text."""

    if not isinstance(index, dict):
        return ""
    positioned = [
        (position, word)
        for word, positions in index.items()
        for position in positions
        if isinstance(position, int)
    ]
    return _collapse(" ".join(word for _, word in sorted(positioned)))


def _send(
    transport: RetrievalTransport,
    url: str,
    *,
    params: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> TransportResponse:
    """One GET, mapped onto the fail-closed error taxonomy."""

    response = transport.get(url, params=params, headers=headers, timeout=timeout)
    response = TransportResponse(
        status_code=response.status_code,
        text=response.text,
        headers={key.lower(): value for key, value in response.headers.items()},
    )
    if response.status_code == 429:
        raise RetrievalRateLimited(
            f"provider rate limited the request: {url}",
            retry_after_seconds=_retry_after_seconds(response.headers),
        )
    if response.status_code >= 500:
        raise RetrievalUnavailable(f"provider returned {response.status_code}: {url}")
    if response.status_code >= 400:
        raise RetrievalResponseError(
            f"provider rejected the request with {response.status_code}: {url}"
        )
    return response


def _retry_after_seconds(headers: dict[str, str]) -> float | None:
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _limit_monitor_fields(headers: dict[str, str]) -> dict[str, str]:
    """OpenAlex publishes its own quota counters; keep them for the limit monitor."""

    fields: dict[str, str] = {}
    for header, label in (
        ("x-ratelimit-remaining", "quota_remaining"),
        ("x-ratelimit-limit", "quota_limit"),
        ("x-ratelimit-reset", "quota_reset_seconds"),
        ("x-ratelimit-cost-usd", "last_query_cost_usd"),
        ("x-ratelimit-remaining-usd", "quota_remaining_usd"),
    ):
        value = headers.get(header)
        if value is not None:
            fields[label] = value
    return fields


class _CandidateOnlyAdapter:
    """Shared A4 adapter shape: fetch -> candidates, never a structured value.

    ``rate_limit_events`` / ``last_retry_after_seconds`` are the limit-monitor
    surface ADR-01 s5 asks A5 to add next to the degradation path. They are
    process-local counters, deliberately kept out of the receipt (the receipt
    records the outcome of one invocation; this records provider pressure).
    """

    capability_name: str = ""
    capability_version: str = "1"
    source: str = ""
    network_required: bool = True
    allowed_network_domains: tuple[str, ...] = ()
    manifest_permissions: tuple[str, ...] = ("network:read",)

    def __init__(self) -> None:
        self.rate_limit_events = 0
        self.last_retry_after_seconds: float | None = None
        self.provider_quota: dict[str, str] = {}

    #: subclasses implement
    def _fetch(self, request: SearchAdapterRequest) -> list[RetrievedPaper]:
        raise NotImplementedError

    def _extra_diagnostics(self) -> list[str]:
        """Optional per-adapter limit-monitor notes for the next receipt."""

        return []

    def rate_limit_summary(self) -> dict[str, object]:
        return {
            "source": self.source,
            "rate_limit_events": self.rate_limit_events,
            "last_retry_after_seconds": self.last_retry_after_seconds,
            "provider_quota": dict(self.provider_quota),
        }

    def invoke(
        self,
        request: SearchAdapterRequest,
        context: CapabilityExecutionContext,
    ) -> CapabilityAdapterResult:
        try:
            papers = self._fetch(request)
        except RetrievalRateLimited as exc:
            self.rate_limit_events += 1
            self.last_retry_after_seconds = exc.retry_after_seconds
            diagnostics = [f"{self.source}: {exc}"]
            if exc.retry_after_seconds is not None:
                diagnostics.append(f"{self.source}: retry after {exc.retry_after_seconds:g}s")
            diagnostics.append("query did not execute; no candidates were produced")
            return CapabilityAdapterResult(
                status=CapabilityReceiptStatus.FAILED,
                diagnostics=diagnostics,
            )
        except RetrievalUnavailable as exc:
            return CapabilityAdapterResult(
                status=CapabilityReceiptStatus.UNKNOWN,
                diagnostics=[f"{self.source}: {exc}", "provider outcome is unknown"],
            )
        except RetrievalError as exc:
            return CapabilityAdapterResult(
                status=CapabilityReceiptStatus.FAILED,
                diagnostics=[f"{self.source}: {exc}"],
            )
        except Exception as exc:  # pragma: no cover - defensive, registry also guards
            return CapabilityAdapterResult(
                status=CapabilityReceiptStatus.FAILED,
                diagnostics=[f"{self.source}: adapter failure: {type(exc).__name__}: {exc}"],
            )

        candidates = [self._candidate(request, paper) for paper in papers]
        for candidate in candidates:
            context.emit_candidate(candidate)
        diagnostics = [f"{self.source}: {len(papers)} hits for query {request.query!r}"]
        diagnostics.extend(self._extra_diagnostics())
        if not papers:
            diagnostics.append(
                "deterministic empty result; treated as material absence, not unknown (D-F8-01)"
            )
        return CapabilityAdapterResult(
            value=None,
            status=CapabilityReceiptStatus.COMPLETED,
            diagnostics=diagnostics,
        )

    def _candidate(self, request: SearchAdapterRequest, paper: RetrievedPaper) -> EvidenceCandidate:
        return EvidenceCandidate(
            project_id=request.project_id,
            run_id=request.run_id,
            invocation_id=request.invocation_id,
            title=paper.title[:300],
            claim=f"Bibliographic record exists for: {paper.title}",
            source_id=paper.source_record_id,
            source_uri=paper.url,
            locator="bibliographic record/abstract",
            independent_source=paper.independent_source(self.source)[:300],
            adapter=self.capability_name,
            adapter_version=self.capability_version,
            metadata={
                "source": self.source,
                "year": paper.year,
                "doi": paper.doi,
                "abstract_present": bool(paper.abstract),
                "authors": list(paper.authors),
            },
        )

    def manifest(self) -> CapabilityManifest:
        return CapabilityManifest(
            name=self.capability_name,
            kind=CapabilityKind.NATIVE.value,
            version=self.capability_version,
            permissions=list(self.manifest_permissions),
            inputs=["query", "limit"],
            outputs=["evidence_candidate"],
            evidence_mode="candidate_only",
            network_required=True,
            allowed_network_domains=list(self.allowed_network_domains),
        )


# --------------------------------------------------------------------------- #
# Semantic Scholar (ADR-01 slot 2 primary; free API key required)
# --------------------------------------------------------------------------- #


class SemanticScholarSearchAdapter(_CandidateOnlyAdapter):
    """Primary retrieval source. The API key travels in a header, never in the request.

    A key is required by policy (ADR-01 s1.1: "modules that need an API apply for
    the free tier and do not avoid registering a key"). Without one the adapter
    fails closed *before* any network call, instead of silently degrading into the
    anonymous shared pool that returns HTTP 429.
    ``allow_anonymous`` exists only so the request path can be exercised in tests
    and probes; it is never the default.
    """

    capability_name = "semantic_scholar_search"
    source = SEMANTIC_SCHOLAR_SOURCE
    allowed_network_domains = ("api.semanticscholar.org",)
    endpoint = "https://api.semanticscholar.org/graph/v1/paper/search"
    fields = "title,abstract,authors,year,externalIds,url"

    def __init__(
        self,
        *,
        api_key: str | SecretStr | None = None,
        transport: RetrievalTransport | None = None,
        timeout: float = 30.0,
        allow_anonymous: bool = False,
    ):
        super().__init__()
        self._api_key = api_key
        self.transport = transport or HttpxTransport()
        self.timeout = timeout
        self.allow_anonymous = allow_anonymous

    @property
    def api_key_present(self) -> bool:
        return bool(self.secret_value)

    @property
    def secret_value(self) -> str | None:
        key = self._api_key
        if key is None:
            return None
        if isinstance(key, SecretStr):
            return key.get_secret_value()
        return key

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "AutoResearch/0.1 (scholarly retrieval adapter)"}
        secret = self.secret_value
        if secret:
            headers["x-api-key"] = secret
        return headers

    def _fetch(self, request: SearchAdapterRequest) -> list[RetrievedPaper]:
        if not self.api_key_present and not self.allow_anonymous:
            raise RetrievalCredentialsRequired(
                "SEMANTIC_SCHOLAR_API_KEY is not configured; the anonymous shared pool is "
                "rate limited (HTTP 429), so no request was sent"
            )
        body = _send(
            self.transport,
            self.endpoint,
            params={"query": request.query, "limit": request.limit, "fields": self.fields},
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._parse(body.text)

    @staticmethod
    def _parse(body: str) -> list[RetrievedPaper]:
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise RetrievalResponseError(f"provider returned non-JSON body: {exc}") from exc
        if not isinstance(payload, dict):
            raise RetrievalResponseError("provider payload is not an object")
        data = payload.get("data")
        if data is None:
            raise RetrievalResponseError("provider payload has no 'data' field")
        if not isinstance(data, list):
            raise RetrievalResponseError("provider 'data' field is not a list")
        papers: list[RetrievedPaper] = []
        for work in data:
            if not isinstance(work, dict):
                raise RetrievalResponseError("provider returned a non-object hit")
            external = work.get("externalIds") or {}
            papers.append(
                RetrievedPaper(
                    title=_collapse(work.get("title")) or "Untitled",
                    abstract=_collapse(work.get("abstract")),
                    authors=tuple(
                        _collapse(author.get("name"))
                        for author in work.get("authors") or []
                        if isinstance(author, dict)
                    ),
                    year=work.get("year") if isinstance(work.get("year"), int) else None,
                    doi=(external.get("DOI") if isinstance(external, dict) else None),
                    url=work.get("url"),
                    source_record_id=work.get("paperId"),
                )
            )
        return papers


# --------------------------------------------------------------------------- #
# arXiv (ADR-01 slot 2 supplement; no key, HTTPS only)
# --------------------------------------------------------------------------- #


class ArxivSearchAdapter(_CandidateOnlyAdapter):
    """Supplement source: arXiv needs no key, but it is HTTPS-only and slow.

    Measured on 2026-09-11 from this host: successful responses took ~31s and
    repeated calls answered HTTP 429, so the default timeout is deliberately
    larger than the Semantic Scholar one and rate limiting must be expected
    rather than treated as an anomaly.
    """

    capability_name = "arxiv_search"
    source = ARXIV_SOURCE
    allowed_network_domains = ("export.arxiv.org",)
    endpoint = "https://export.arxiv.org/api/query"

    def __init__(
        self,
        *,
        transport: RetrievalTransport | None = None,
        timeout: float = 60.0,
    ):
        super().__init__()
        self.transport = transport or HttpxTransport()
        self.timeout = timeout

    def _fetch(self, request: SearchAdapterRequest) -> list[RetrievedPaper]:
        body = _send(
            self.transport,
            self.endpoint,
            params={
                "search_query": f"all:{request.query}",
                "start": 0,
                "max_results": request.limit,
                "sortBy": "relevance",
            },
            headers={"User-Agent": "AutoResearch/0.1 (scholarly retrieval adapter)"},
            timeout=self.timeout,
        )
        return self._parse(body.text)

    @staticmethod
    def _parse(body: str) -> list[RetrievedPaper]:
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError as exc:
            raise RetrievalResponseError(f"provider returned malformed Atom XML: {exc}") from exc
        papers: list[RetrievedPaper] = []
        for entry in root.findall(f"{_ATOM_NS}entry"):
            entry_id = _collapse(entry.findtext(f"{_ATOM_NS}id"))
            published = _collapse(entry.findtext(f"{_ATOM_NS}published"))
            year = int(published[:4]) if published[:4].isdigit() else None
            alternate = next(
                (
                    link.get("href")
                    for link in entry.findall(f"{_ATOM_NS}link")
                    if link.get("rel") == "alternate"
                ),
                None,
            )
            papers.append(
                RetrievedPaper(
                    title=_collapse(entry.findtext(f"{_ATOM_NS}title")) or "Untitled",
                    abstract=_collapse(entry.findtext(f"{_ATOM_NS}summary")),
                    authors=tuple(
                        _collapse(author.findtext(f"{_ATOM_NS}name"))
                        for author in entry.findall(f"{_ATOM_NS}author")
                    ),
                    year=year,
                    doi=_collapse(entry.findtext(f"{_ARXIV_NS}doi")) or None,
                    url=alternate or entry_id or None,
                    source_record_id=entry_id.rsplit("/", 1)[-1] or None,
                )
            )
        return papers


# --------------------------------------------------------------------------- #
# OpenAlex (ADR-01 s5 degraded track; "OpenAlex optional track takes over")
# --------------------------------------------------------------------------- #


class OpenAlexSearchAdapter(_CandidateOnlyAdapter):
    """The degraded track ADR-01 s5 pre-authorises A5 to implement.

    ADR-01 s5 asks A5 for "rate-limit monitoring and a degradation path (the
    OpenAlex optional track takes over)". OpenAlex is therefore implemented here
    as a third candidate-only adapter, not as a replacement for the primary.

    Two provider quirks are handled explicitly, both measured on 2026-09-11:

    * a throttled search answers **HTTP 200 with an ``error`` body**, so status
      code alone is not a sufficient health signal;
    * it publishes its own quota counters in ``X-RateLimit-*`` headers, which the
      limit monitor forwards into diagnostics.
    """

    capability_name = "openalex_search"
    source = OPENALEX_SOURCE
    allowed_network_domains = ("api.openalex.org",)
    endpoint = "https://api.openalex.org/works"

    def __init__(
        self,
        *,
        api_key: str | SecretStr | None = None,
        transport: RetrievalTransport | None = None,
        timeout: float = 30.0,
        polite_mailto: str | None = None,
    ):
        super().__init__()
        self._api_key = api_key
        self.transport = transport or HttpxTransport()
        self.timeout = timeout
        self.polite_mailto = polite_mailto

    @property
    def secret_value(self) -> str | None:
        key = self._api_key
        if key is None:
            return None
        if isinstance(key, SecretStr):
            return key.get_secret_value()
        return key

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "AutoResearch/0.1 (scholarly retrieval adapter)"}
        secret = self.secret_value
        if secret:
            # OpenAlex expects the credential as a bearer token.
            headers["Authorization"] = f"Bearer {secret}"
        return headers

    def _fetch(self, request: SearchAdapterRequest) -> list[RetrievedPaper]:
        params: dict[str, Any] = {"search": request.query, "per-page": request.limit}
        if self.polite_mailto:
            params["mailto"] = self.polite_mailto
        response = _send(
            self.transport,
            self.endpoint,
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        self.provider_quota = _limit_monitor_fields(response.headers)
        return self._parse(response.text)

    def _extra_diagnostics(self) -> list[str]:
        if not self.provider_quota:
            return []
        rendered = ", ".join(f"{key}={value}" for key, value in self.provider_quota.items())
        return [f"{self.source}: limit monitor {rendered}"]

    def _parse(self, body: str) -> list[RetrievedPaper]:
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise RetrievalResponseError(f"provider returned non-JSON body: {exc}") from exc
        if not isinstance(payload, dict):
            raise RetrievalResponseError("provider payload is not an object")
        error = payload.get("error")
        if error is not None:
            message = str(payload.get("message") or error)
            retry_after = payload.get("retryAfter")
            # the provider writes both "rate limit" and "rate-limited"
            normalized = message.lower().replace("-", " ")
            if "rate limit" in normalized or "throttl" in normalized:
                raise RetrievalRateLimited(
                    f"provider refused the search: {message}",
                    retry_after_seconds=(
                        float(retry_after) if isinstance(retry_after, int | float) else None
                    ),
                )
            raise RetrievalResponseError(f"provider returned an error: {message}")
        results = payload.get("results")
        if results is None:
            raise RetrievalResponseError("provider payload has no 'results' field")
        if not isinstance(results, list):
            raise RetrievalResponseError("provider 'results' field is not a list")
        papers: list[RetrievedPaper] = []
        for work in results:
            if not isinstance(work, dict):
                raise RetrievalResponseError("provider returned a non-object hit")
            papers.append(
                RetrievedPaper(
                    title=_collapse(work.get("display_name")) or "Untitled",
                    abstract=_inverted_index_to_text(work.get("abstract_inverted_index")),
                    authors=tuple(
                        _collapse(entry.get("author", {}).get("display_name"))
                        for entry in work.get("authorships") or []
                        if isinstance(entry, dict) and isinstance(entry.get("author"), dict)
                    ),
                    year=(
                        work.get("publication_year")
                        if isinstance(work.get("publication_year"), int)
                        else None
                    ),
                    doi=(work.get("doi") or "").removeprefix("https://doi.org/") or None,
                    url=(work.get("primary_location") or {}).get("landing_page_url"),
                    source_record_id=work.get("id"),
                )
            )
        return papers


# --------------------------------------------------------------------------- #
# Registration through the A4 registry (the only supported entry point)
# --------------------------------------------------------------------------- #


def build_search_adapters(
    *,
    settings: Settings | None = None,
    transport: RetrievalTransport | None = None,
    allow_anonymous_semantic_scholar: bool = False,
) -> dict[str, _CandidateOnlyAdapter]:
    """Instantiate the ADR-01 slot 2 pair plus the s5 degraded track.

    ``semantic_scholar`` is the primary selection, ``arxiv`` the supplement, and
    ``openalex`` the optional degraded track that s5 explicitly hands to A5. Extra
    sources are additive: the primary slot is never silently rewritten, because
    ADR-01 s1 forbids a member package from changing a selection on its own.
    """

    active = settings or get_settings()
    return {
        SEMANTIC_SCHOLAR_SOURCE: SemanticScholarSearchAdapter(
            api_key=active.semantic_scholar_api_key,
            transport=transport,
            timeout=active.semantic_scholar_timeout_seconds,
            allow_anonymous=allow_anonymous_semantic_scholar,
        ),
        ARXIV_SOURCE: ArxivSearchAdapter(transport=transport),
        OPENALEX_SOURCE: OpenAlexSearchAdapter(
            api_key=active.openalex_api_key,
            transport=transport,
            polite_mailto=active.openalex_mailto,
        ),
    }


def register_search_adapters(
    registry: CapabilityRegistry,
    *,
    settings: Settings | None = None,
    transport: RetrievalTransport | None = None,
    allow_anonymous_semantic_scholar: bool = False,
) -> dict[str, CapabilityRegistrationView]:
    """Register every retrieval adapter as a candidate-only capability.

    ``CANDIDATE_ONLY`` is not a downgrade here: a retrieval adapter emits evidence
    candidates and has no structured result to return, which is exactly what that
    tier describes. It also keeps the deterministic empty result on the success
    path (D-F8-01) instead of being rewritten into a failure.
    """

    adapters = build_search_adapters(
        settings=settings,
        transport=transport,
        allow_anonymous_semantic_scholar=allow_anonymous_semantic_scholar,
    )
    views: dict[str, CapabilityRegistrationView] = {}
    for name, adapter in adapters.items():
        views[name] = registry.register(
            adapter.manifest(),
            adapter,
            trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
            kind=CapabilityKind.NATIVE,
            network_required=True,
            allowed_network_domains=list(adapter.allowed_network_domains),
        )
    return views
