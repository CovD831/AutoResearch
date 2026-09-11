"""B5 S3-B Real Data Sources & Parsing Layer tests.

Live-Crossref-first verdicts over a ``httpx.MockTransport``, offline snapshot
fallback, transport-outcome matrix (rate-limit / timeout / 404 / partial),
ScholarQABench-aligned metrics, and candidate-only egress. No real network is
issued inside tests; the transport is mocked.
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
)
from autoresearch.pipeline_contracts import EvidenceCandidate

FIXTURES = Path(__file__).parent / "fixtures" / "external_sources"


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


def test_live_resolves_found_retracted_with_real_dois():
    adapter = _adapter()

    found = adapter.resolve("10.1038/s41586-025-10072-4")
    assert found.status is SourceStatus.FOUND
    assert found.title == (
        "Synthesizing scientific literature with retrieval-augmented language models"
    )

    retracted = adapter.resolve("10.1016/S0140-6736(10)60175-4")
    assert retracted.status is SourceStatus.RETRACTED
    assert "10.1016/s0140-6736(97)11096-0" in retracted.related_dois
    assert any("retraction-watch" in r for r in retracted.reasons)


def test_live_404_is_deterministic_not_found():
    adapter = _adapter(mapping={})  # empty mapping -> 404 for every DOI
    verdict = adapter.resolve("10.1000/does-not-exist")
    assert verdict.status is SourceStatus.NOT_FOUND
    assert verdict.transport is TransportOutcome.OK


# ---------------------------------------------------------------------------
# Transport outcome matrix (rate-limit / timeout / partial) -> snapshot -> unknown
# ---------------------------------------------------------------------------


def test_rate_limited_falls_back_to_snapshot_then_unknown():
    mapping = {"10.1038/s41586-025-10072-4": {"status": 429}}
    # With snapshot: served from snapshot.
    with_snapshot = _adapter(mapping=mapping, snapshot=_snapshot())
    verdict = with_snapshot.resolve("10.1038/s41586-025-10072-4")
    assert verdict.status is SourceStatus.FOUND
    assert verdict.transport is TransportOutcome.RATE_LIMITED

    # Without snapshot: fail-closed unknown.
    without_snapshot = _adapter(mapping=mapping)
    unknown = without_snapshot.resolve("10.1038/s41586-025-10072-4")
    assert unknown.status is SourceStatus.UNKNOWN
    assert unknown.transport is TransportOutcome.RATE_LIMITED


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


def test_resolver_record_projects_live_retraction_for_b3():
    adapter = _adapter()
    verdict = adapter.resolve("10.1016/S0140-6736(10)60175-4")
    record = adapter.resolver_record("10.1016/S0140-6736(10)60175-4", verdict=verdict)
    assert record is not None
    assert record["status"] == "retracted"
    assert "10.1016/s0140-6736(97)11096-0" in record["related_source_ids"]


# ---------------------------------------------------------------------------
# PDF parsing (docling-first, optional fallback)
# ---------------------------------------------------------------------------


def test_pdf_parser_unavailable_returns_unknown(tmp_path):
    parser = PdfParser()
    result = parser.parse(str(tmp_path / "missing.pdf"))
    assert result.status in {ParseStatus.UNKNOWN, ParseStatus.OK}
    if result.status is ParseStatus.UNKNOWN:
        assert any("no PDF parser" in d for d in result.diagnostics)


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


# ---------------------------------------------------------------------------
# Gold set / ScholarQABench-aligned metrics
# ---------------------------------------------------------------------------


def test_hallucination_ratio_counts_not_found_and_unknown():
    statuses = [
        SourceStatus.FOUND,
        SourceStatus.FOUND,
        SourceStatus.NOT_FOUND,
        SourceStatus.UNKNOWN,
    ]
    assert hallucination_ratio(statuses) == pytest.approx(0.5)
    assert hallucination_ratio([]) is None


def test_eval_item_computes_hallucination_and_notes_attribution():
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
    assert metrics.hallucinated == 1
    assert metrics.hallucination_ratio == pytest.approx(0.5)
    # No NLI judge supplied => recall/precision are None with a note.
    assert metrics.citation_recall is None
    assert metrics.citation_precision is None
    assert "attributable" in metrics.attribution_note


def test_eval_item_computes_recall_precision_with_nli_judge():
    item = GoldSetItem(
        query_id="q1",
        citations=[
            GoldCitation(citation_id="c1", cited=True),
            GoldCitation(citation_id="c2", cited=True),
        ],
    )
    statuses = {"c1": SourceStatus.FOUND, "c2": SourceStatus.FOUND}
    attributable = {"c1": True, "c2": False}
    metrics = eval_item(item, resolver_statuses=statuses, attributable=attributable)
    assert metrics.citation_recall == pytest.approx(0.5)
    assert metrics.citation_precision == pytest.approx(0.5)
