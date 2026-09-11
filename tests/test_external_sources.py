"""B5 S3-B Real Data Sources & Parsing Layer tests.

Live-Crossref-first verdicts over a ``httpx.MockTransport``, offline snapshot
fallback, transport-outcome matrix (rate-limit / timeout / 404 / partial),
ScholarQABench-aligned metrics, and candidate-only egress. No real network is
issued inside tests; the transport is mocked.

Relation direction follows the live Crossref API (verified 2026-09-11):
``updated-by[]`` lists the works that updated *this* one (so a retraction notice
appears here for the retracted article), while ``update-to[]`` lists the works
this one updated (so the notice carries the retracted article's DOI).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from autoresearch.contracts import EvidenceGrade, EvidenceType
from autoresearch.external_sources import (
    CrossrefAdapter,
    CrossrefClient,
    EvalMetrics,
    GoldCitation,
    GoldSetItem,
    ParseEgress,
    ParseResult,
    ParseStatus,
    PdfParser,
    SourceSnapshot,
    SourceStatus,
    TransportOutcome,
    eval_item,
    hallucination_ratio,
    undetermined_ratio,
)
from autoresearch.pipeline_contracts import EvidenceCandidate

FIXTURES = Path(__file__).parent / "fixtures" / "external_sources"

# The two Lancet DOIs are distinct works and must never be conflated:
#   ...(97)11096-0  the 1998 article, retracted in 2010  -> retracted
#   ...(10)60175-4  the 2010 retraction notice itself    -> found
RETRACTED_ARTICLE = "10.1016/S0140-6736(97)11096-0"
RETRACTION_NOTICE = "10.1016/S0140-6736(10)60175-4"
NORMAL_ARTICLE = "10.1038/s41586-025-10072-4"


def _snapshot() -> SourceSnapshot:
    raw = json.loads((FIXTURES / "doi_snapshot.json").read_text(encoding="utf-8"))
    return SourceSnapshot.model_validate(raw)


def _responses() -> dict:
    return json.loads((FIXTURES / "crossref_responses.json").read_text(encoding="utf-8"))


def _mock_transport(mapping: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        doi = request.url.path.removeprefix("/works/")
        entry = mapping.get(doi)
        if entry is None:
            return httpx.Response(404, json={"status": "not_found"})
        status = entry.get("status", 200)
        if status == 429:
            return httpx.Response(429)
        return httpx.Response(status, json=entry["body"])

    return httpx.MockTransport(handler)


def _client(mapping: dict | None = None) -> CrossrefClient:
    transport = _mock_transport(mapping if mapping is not None else _responses())
    return CrossrefClient(transport=transport)


def _adapter(
    mapping: dict | None = None, snapshot: SourceSnapshot | None = None
) -> CrossrefAdapter:
    return CrossrefAdapter(client=_client(mapping), snapshot=snapshot)


# ---------------------------------------------------------------------------
# Live Crossref verdict matrix
# ---------------------------------------------------------------------------


def test_live_retracted_article_is_reported_retracted():
    """The retracted 1998 article must come back ``retracted``.

    This is the assertion whose absence let the original implementation invert
    the Crossref relation direction: it read ``update-to[]`` (the works this one
    updated) instead of ``updated-by[]`` (the works that updated this one), so
    the retracted article resolved as ``found`` and the notice as ``retracted``.
    """

    adapter = _adapter()
    verdict = adapter.resolve(RETRACTED_ARTICLE)
    assert verdict.status is SourceStatus.RETRACTED
    assert RETRACTION_NOTICE.casefold() in [d.casefold() for d in verdict.related_dois]
    assert any("retraction-watch" in r for r in verdict.reasons)


def test_live_retraction_notice_is_found_not_retracted():
    """The notice is itself a published, citable work — not the retracted item."""

    adapter = _adapter()
    verdict = adapter.resolve(RETRACTION_NOTICE)
    assert verdict.status is SourceStatus.FOUND
    assert RETRACTED_ARTICLE.casefold() in [d.casefold() for d in verdict.related_dois]
    assert any("retraction notice" in r for r in verdict.reasons)


def test_live_resolves_normal_article():
    adapter = _adapter()
    found = adapter.resolve(NORMAL_ARTICLE)
    assert found.status is SourceStatus.FOUND
    assert found.title == (
        "Synthesizing scientific literature with retrieval-augmented language models"
    )
    assert found.related_dois == []


def test_other_relation_kinds_are_recorded_without_changing_the_verdict():
    """An expression-of-concern is not a retraction, but must not vanish.

    B5's frozen scope covers only retraction/correction, so the verdict stays
    ``found``; the relation is still surfaced in ``reasons`` so an auditor can
    see the integrity signal instead of it being silently dropped.
    """

    mapping = {
        "10.1000/eoc": {
            "status": 200,
            "body": {
                "status": "ok",
                "message": {
                    "DOI": "10.1000/eoc",
                    "title": ["A paper carrying an expression of concern"],
                    "updated-by": [
                        {"DOI": "10.1000/eoc-notice", "type": "expression-of-concern"}
                    ],
                },
            },
        }
    }
    verdict = _adapter(mapping=mapping).resolve("10.1000/eoc")
    assert verdict.status is SourceStatus.FOUND
    assert any("expression-of-concern" in r for r in verdict.reasons)


def test_live_404_is_deterministic_not_found():
    adapter = _adapter(mapping={})  # empty mapping -> 404 for every DOI
    verdict = adapter.resolve("10.1000/does-not-exist")
    assert verdict.status is SourceStatus.NOT_FOUND
    assert verdict.transport is TransportOutcome.OK


# ---------------------------------------------------------------------------
# Transport outcome matrix (rate-limit / timeout / partial) -> snapshot -> unknown
# ---------------------------------------------------------------------------


def test_rate_limited_falls_back_to_snapshot_then_unknown():
    mapping = {NORMAL_ARTICLE: {"status": 429}}
    # With snapshot: served from snapshot.
    with_snapshot = _adapter(mapping=mapping, snapshot=_snapshot())
    verdict = with_snapshot.resolve(NORMAL_ARTICLE)
    assert verdict.status is SourceStatus.FOUND
    assert verdict.transport is TransportOutcome.RATE_LIMITED

    # Without snapshot: fail-closed unknown.
    without_snapshot = _adapter(mapping=mapping)
    unknown = without_snapshot.resolve(NORMAL_ARTICLE)
    assert unknown.status is SourceStatus.UNKNOWN
    assert unknown.transport is TransportOutcome.RATE_LIMITED


def test_snapshot_keeps_the_article_and_the_notice_apart():
    """Offline fallback must preserve the same distinction as the live path.

    Rate limiting is used rather than a 404: a live 404 is a definitive verdict
    and deliberately short-circuits the snapshot.
    """

    mapping = {RETRACTED_ARTICLE: {"status": 429}, RETRACTION_NOTICE: {"status": 429}}
    adapter = _adapter(mapping=mapping, snapshot=_snapshot())
    assert adapter.resolve(RETRACTED_ARTICLE).status is SourceStatus.RETRACTED
    assert adapter.resolve(RETRACTION_NOTICE).status is SourceStatus.FOUND


def test_timeout_and_unavailable_are_unknown_without_snapshot():
    class _TimeoutTransport(httpx.BaseTransport):
        def handle_request(self, request):
            raise httpx.TimeoutException("timeout")

    adapter_no_snapshot = CrossrefAdapter(client=CrossrefClient(transport=_TimeoutTransport()))
    assert adapter_no_snapshot.resolve("10.1000/x").status is SourceStatus.UNKNOWN

    class _UnavailableTransport(httpx.BaseTransport):
        def handle_request(self, request):
            raise httpx.ConnectError("unavailable")

    adapter_unavail = CrossrefAdapter(client=CrossrefClient(transport=_UnavailableTransport()))
    assert adapter_unavail.resolve("10.1000/x").status is SourceStatus.UNKNOWN


# ---------------------------------------------------------------------------
# Resolver record projection (B3 flow)
# ---------------------------------------------------------------------------


def test_resolver_record_projects_retraction_for_the_retracted_article():
    adapter = _adapter()
    verdict = adapter.resolve(RETRACTED_ARTICLE)
    record = adapter.resolver_record(RETRACTED_ARTICLE, verdict=verdict)
    assert record is not None
    assert record["status"] == "retracted"
    assert RETRACTION_NOTICE.casefold() in [
        d.casefold() for d in record["related_source_ids"]
    ]


def test_resolver_record_for_a_notice_stays_current():
    """B3 reads ``retracted``/``corrected`` off this field; a notice is neither."""

    adapter = _adapter()
    verdict = adapter.resolve(RETRACTION_NOTICE)
    record = adapter.resolver_record(RETRACTION_NOTICE, verdict=verdict)
    assert record is not None
    assert record["status"] == "current"


def test_resolver_record_is_none_when_the_verdict_is_unknown():
    adapter = _adapter(mapping={NORMAL_ARTICLE: {"status": 429}})  # no snapshot
    assert adapter.resolve(NORMAL_ARTICLE).status is SourceStatus.UNKNOWN
    assert adapter.resolver_record(NORMAL_ARTICLE) is None


def test_resolver_record_is_none_for_a_nonexistent_doi():
    """A 404 is a definitive verdict: no resolver record may be produced.

    Projecting a non-existent DOI as ``current`` would let B3 treat a broken
    citation as a live, valid source — fail-open. Raised by the independent
    adversarial review of the owner fix (the original delivery had it too).
    """

    adapter = _adapter(mapping={})  # every DOI 404s
    assert adapter.resolve("10.1000/does-not-exist").status is SourceStatus.NOT_FOUND
    assert adapter.resolver_record("10.1000/does-not-exist") is None


# ---------------------------------------------------------------------------
# PDF parsing (docling-first, optional fallback)
# ---------------------------------------------------------------------------


def test_pdf_parser_unavailable_is_unknown_with_per_backend_reasons(tmp_path):
    """Neither backend can be used -> ``unknown``, with a reason per backend.

    The previous version asserted ``status in {UNKNOWN, OK}``, which every
    outcome satisfies — it could not fail and therefore verified nothing. A
    non-existent path cannot be parsed successfully, so ``OK`` is excluded.
    """

    parser = PdfParser()
    result = parser.parse(str(tmp_path / "missing.pdf"))
    assert result.status is ParseStatus.UNKNOWN
    assert result.parser == "unavailable"
    joined = " | ".join(result.diagnostics)
    assert "docling" in joined
    assert "pymupdf4llm" in joined
    assert "no PDF parser available" in joined


# ---------------------------------------------------------------------------
# Candidate-only egress (sole-writer boundary)
# ---------------------------------------------------------------------------


def test_parse_egress_admits_candidate_not_direct_evidence(runtime, project):
    egress = ParseEgress(runtime.evidence)
    result = ParseResult(
        parser="docling",
        markdown="Extracted claim text that is long enough to be a claim.",
        locators=["p.1"],
        status=ParseStatus.OK,
    )
    candidate = egress.candidate(project_id="demo", source_id="doc-1", result=result)
    assert isinstance(candidate, EvidenceCandidate)
    assert candidate.evidence_type is EvidenceType.PAPER
    assert candidate.grade is EvidenceGrade.E1
    assert candidate.locator == "p.1"

    admission = egress.admit(project_id="demo", source_id="doc-1", result=result)
    assert admission.status.value == "accepted"
    assert runtime.evidence.list("demo")


def test_parse_egress_requires_evidence_for_admit(runtime, project):
    egress = ParseEgress(None)
    result = ParseResult(parser="docling", markdown="x", status=ParseStatus.OK)
    with pytest.raises(ValueError):
        egress.admit(project_id="demo", source_id="doc-1", result=result)


def test_parse_egress_without_locator_fails_closed(runtime, project):
    """A parse result with no locator must be blocked, not admitted.

    pymupdf4llm exposes no page locators; the earlier code papered over that
    with a ``"docling-fallback"`` placeholder, which passed the non-empty
    locator check and admitted evidence that could not be pointed at.
    """

    egress = ParseEgress(runtime.evidence)
    result = ParseResult(
        parser="pymupdf4llm",
        markdown="Parsed text that is long enough to serve as a claim.",
        locators=[],
        status=ParseStatus.OK,
    )
    admission = egress.admit(project_id="demo", source_id="doc-x", result=result)
    assert admission.status.value == "blocked"
    assert runtime.evidence.list("demo") == []


def test_parse_egress_accepts_a_caller_supplied_locator(runtime, project):
    """Provenance the parser cannot supply may come from the caller."""

    egress = ParseEgress(runtime.evidence)
    result = ParseResult(
        parser="pymupdf4llm",
        markdown="Parsed text that is long enough to serve as a claim.",
        locators=[],
        status=ParseStatus.OK,
    )
    admission = egress.admit(
        project_id="demo",
        source_id="doc-y",
        result=result,
        locator="p.7",
        source_uri="https://doi.org/10.1000/example",
    )
    assert admission.status.value == "accepted"
    stored = runtime.evidence.list("demo")
    assert stored
    assert stored[-1].source_uri == "https://doi.org/10.1000/example"


# ---------------------------------------------------------------------------
# Gold set / ScholarQABench-aligned metrics
# ---------------------------------------------------------------------------


def test_hallucination_ratio_counts_only_not_found():
    statuses = [
        SourceStatus.FOUND,
        SourceStatus.FOUND,
        SourceStatus.NOT_FOUND,
        SourceStatus.UNKNOWN,
    ]
    # A transport failure is not a hallucination: it is reported separately so
    # the primary metric cannot move with network conditions.
    assert hallucination_ratio(statuses) == pytest.approx(0.25)
    assert undetermined_ratio(statuses) == pytest.approx(0.25)
    assert hallucination_ratio([]) is None
    assert undetermined_ratio([]) is None


def test_eval_item_separates_hallucination_from_undetermined():
    item = GoldSetItem(
        query_id="q1",
        citations=[
            GoldCitation(citation_id="c1", cited=True),
            GoldCitation(citation_id="c2", cited=True),
        ],
    )
    statuses = {"c1": SourceStatus.FOUND, "c2": SourceStatus.UNKNOWN}
    metrics = eval_item(item, resolver_statuses=statuses)
    assert isinstance(metrics, EvalMetrics)
    assert metrics.total_cited == 2
    assert metrics.resolvable == 1
    assert metrics.hallucinated == 0
    assert metrics.undetermined == 1
    assert metrics.hallucination_ratio == pytest.approx(0.0)
    assert metrics.undetermined_ratio == pytest.approx(0.5)
    assert metrics.citation_recall == pytest.approx(1.0)
    # No NLI judge supplied => precision is None with a note.
    assert metrics.citation_precision is None
    assert "attributable" in metrics.attribution_note


def test_eval_item_recall_and_precision_are_distinct():
    """Recall is gold coverage; precision is the judge-supported share.

    The previous implementation derived both from the same numerator and the
    same denominator, so the two were equal for every possible input.
    """

    item = GoldSetItem(
        query_id="q1",
        citations=[
            GoldCitation(citation_id="c1", cited=True),
            GoldCitation(citation_id="c2", cited=True),
            GoldCitation(citation_id="c3", cited=False),  # expected, not emitted
        ],
    )
    statuses = {key: SourceStatus.FOUND for key in ("c1", "c2", "c3")}
    attributable = {"c1": True, "c2": False}
    metrics = eval_item(item, resolver_statuses=statuses, attributable=attributable)
    assert metrics.citation_recall == pytest.approx(2 / 3)
    assert metrics.citation_precision == pytest.approx(1 / 2)
    assert metrics.citation_recall != metrics.citation_precision
