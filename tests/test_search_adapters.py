"""A5 retrieval adapter acceptance: ADR-01 slot 2 pair behind the A4 registry.

The central artefact here is the rate-limit / offline matrix required by
TASK-SPECS A5 ("limit/offline matrixing") combined with the D-F8-01 empty-result
ruling and the D-S3-01 candidate-admission hard clause. Every cell runs offline
through an injected transport, so the matrix is re-runnable in CI.
"""

from __future__ import annotations

import json

import httpx
import pytest

from autoresearch.capability_registry import (
    CapabilityReceiptStatus,
    CapabilityRegistry,
)
from autoresearch.config import Settings
from autoresearch.search_adapters import (
    ARXIV_SOURCE,
    OPENALEX_SOURCE,
    SEMANTIC_SCHOLAR_SOURCE,
    ArxivSearchAdapter,
    HttpxTransport,
    OpenAlexSearchAdapter,
    RetrievalUnavailable,
    SearchAdapterRequest,
    SemanticScholarSearchAdapter,
    TransportResponse,
    register_search_adapters,
)

SEMANTIC_SCHOLAR_BODY = json.dumps(
    {
        "total": 2,
        "data": [
            {
                "paperId": "S2-0001",
                "title": "Grid cells in the medial entorhinal cortex",
                "abstract": "We report grid-like firing fields.",
                "authors": [{"name": "A. Researcher"}, {"name": "B. Author"}],
                "year": 2024,
                "externalIds": {"DOI": "10.1000/example.1"},
                "url": "https://www.semanticscholar.org/paper/S2-0001",
            },
            {
                "paperId": "S2-0002",
                "title": "Place cells revisited",
                "abstract": "",
                "authors": [],
                "year": None,
                "externalIds": {},
                "url": None,
            },
        ],
    }
)

ARXIV_BODY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234v2</id>
    <published>2024-01-02T00:00:00Z</published>
    <title>Grid
      cells and the metric of space</title>
    <summary>  A survey of grid cell
      models.  </summary>
    <author><name>C. Physicist</name></author>
    <link href="http://arxiv.org/abs/2401.01234v2" rel="alternate" type="text/html"/>
    <arxiv:doi>10.1000/example.2</arxiv:doi>
  </entry>
</feed>
"""


class FakeTransport:
    """Records the exact call so 'provably did not execute' claims are checkable."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        body: str = "",
        raises: Exception | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self.body = body
        self.raises = raises
        self.headers = headers or {}
        self.calls: list[dict[str, object]] = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if self.raises is not None:
            raise self.raises
        return TransportResponse(
            status_code=self.status_code, text=self.body, headers=dict(self.headers)
        )


def make_settings(**overrides) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "AUTORESEARCH_NETWORK_ENABLED": True,
    }
    values.update(overrides)
    return Settings(**values)


def make_request(**overrides) -> SearchAdapterRequest:
    values: dict[str, object] = {
        "project_id": "demo",
        "run_id": "run-1",
        "invocation_id": "inv-1",
        "query": "grid cells",
        "limit": 3,
    }
    values.update(overrides)
    return SearchAdapterRequest(**values)


def test_registration_declares_the_selected_sources_and_network_policy():
    registry = CapabilityRegistry(allow_network=True)
    views = register_search_adapters(registry, settings=make_settings(), transport=FakeTransport())

    assert set(views) == {SEMANTIC_SCHOLAR_SOURCE, ARXIV_SOURCE, OPENALEX_SOURCE}
    assert views[SEMANTIC_SCHOLAR_SOURCE].allowed_network_domains == ("api.semanticscholar.org",)
    assert views[ARXIV_SOURCE].allowed_network_domains == ("export.arxiv.org",)
    assert views[OPENALEX_SOURCE].allowed_network_domains == ("api.openalex.org",)
    assert all(view.network_required for view in views.values())
    assert {view.manifest.name for view in views.values()} == {
        "semantic_scholar_search",
        "arxiv_search",
        "openalex_search",
    }


def test_semantic_scholar_key_travels_in_a_header_and_stays_out_of_the_receipt():
    transport = FakeTransport(body=SEMANTIC_SCHOLAR_BODY)
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry,
        settings=make_settings(SEMANTIC_SCHOLAR_API_KEY="s2-secret-key"),
        transport=transport,
    )

    invocation = registry.invoke("semantic_scholar_search", make_request())

    assert transport.calls[0]["headers"]["x-api-key"] == "s2-secret-key"
    assert invocation.receipt.status == CapabilityReceiptStatus.COMPLETED
    assert invocation.receipt.candidate_count == 2
    # the key must not be reachable from the request, the fingerprint or the receipt
    serialized = json.dumps(
        {
            "fingerprint": invocation.receipt.request_fingerprint,
            "receipt": invocation.receipt.model_dump(mode="json"),
        }
    )
    assert "s2-secret-key" not in serialized
    assert "s2-secret-key" not in make_request().model_dump_json()


def test_semantic_scholar_without_a_key_fails_closed_before_any_call():
    transport = FakeTransport(body=SEMANTIC_SCHOLAR_BODY)
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(registry, settings=make_settings(), transport=transport)

    invocation = registry.invoke("semantic_scholar_search", make_request())

    assert transport.calls == []
    assert invocation.receipt.status == CapabilityReceiptStatus.FAILED
    assert invocation.receipt.outcome_status == CapabilityReceiptStatus.FAILED
    assert not invocation.receipt.candidates_admissible
    assert invocation.admissible_candidates == []
    assert any("SEMANTIC_SCHOLAR_API_KEY" in item for item in invocation.diagnostics)


def test_arxiv_parses_atom_without_any_key_and_normalizes_whitespace():
    transport = FakeTransport(body=ARXIV_BODY)
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(registry, settings=make_settings(), transport=transport)

    invocation = registry.invoke("arxiv_search", make_request())

    assert "x-api-key" not in transport.calls[0]["headers"]
    assert transport.calls[0]["params"]["search_query"] == "all:grid cells"
    assert invocation.receipt.status == CapabilityReceiptStatus.COMPLETED
    candidate = invocation.admissible_candidates[0]
    assert candidate.title == "Grid cells and the metric of space"
    assert candidate.source_id == "2401.01234v2"
    assert candidate.independent_source == "10.1000/example.2"
    assert candidate.metadata["year"] == 2024
    assert candidate.metadata["abstract_present"] is True
    # R005: the runtime lane never assigns an evidence grade
    assert candidate.grade is None
    assert candidate.evidence_type is None


def test_arxiv_malformed_xml_is_a_known_failure():
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry, settings=make_settings(), transport=FakeTransport(body="<feed><oops>")
    )

    invocation = registry.invoke("arxiv_search", make_request())

    assert invocation.receipt.status == CapabilityReceiptStatus.FAILED
    assert invocation.admissible_candidates == []


def test_semantic_scholar_non_json_body_is_a_known_failure():
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry,
        settings=make_settings(SEMANTIC_SCHOLAR_API_KEY="k"),
        transport=FakeTransport(body="<html>gateway</html>"),
    )

    invocation = registry.invoke("semantic_scholar_search", make_request())

    assert invocation.receipt.status == CapabilityReceiptStatus.FAILED
    assert any("non-JSON" in item for item in invocation.diagnostics)


def test_httpx_transport_maps_connection_errors_to_unknown(monkeypatch):
    def boom(*args, **kwargs):
        raise httpx.ConnectError("network is unreachable")

    monkeypatch.setattr(httpx, "get", boom)
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry,
        settings=make_settings(SEMANTIC_SCHOLAR_API_KEY="k"),
        transport=HttpxTransport(),
    )

    invocation = registry.invoke("semantic_scholar_search", make_request())

    assert invocation.receipt.status == CapabilityReceiptStatus.UNKNOWN
    assert invocation.receipt.outcome_status == CapabilityReceiptStatus.UNKNOWN
    assert not invocation.receipt.candidates_admissible
    assert any("unknown" in item for item in invocation.diagnostics)


# --------------------------------------------------------------------------- #
# The required rate-limit / offline matrix
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("scenario", "network_allowed", "status_code", "api_key", "expected"),
    [
        (
            "online with key",
            True,
            200,
            "s2-secret-key",
            CapabilityReceiptStatus.COMPLETED,
        ),
        (
            "online, deterministic empty result",
            True,
            200,
            "s2-secret-key",
            CapabilityReceiptStatus.COMPLETED,
        ),
        (
            "online but rate limited",
            True,
            429,
            "s2-secret-key",
            CapabilityReceiptStatus.FAILED,
        ),
        (
            "online, provider rejected the call",
            True,
            400,
            "s2-secret-key",
            CapabilityReceiptStatus.FAILED,
        ),
        (
            "online but transport interrupted",
            True,
            200,
            "s2-secret-key",
            CapabilityReceiptStatus.UNKNOWN,
        ),
        (
            "no credential configured",
            True,
            200,
            None,
            CapabilityReceiptStatus.FAILED,
        ),
        (
            "network policy disabled",
            False,
            200,
            "s2-secret-key",
            CapabilityReceiptStatus.DENIED,
        ),
    ],
)
def test_rate_limit_and_offline_matrix(
    scenario, network_allowed, status_code, api_key, expected
):
    empty_body = json.dumps({"total": 0, "data": []})
    interrupted = RetrievalUnavailable("transport unavailable: ConnectError")
    if scenario == "online but transport interrupted":
        transport = FakeTransport(raises=interrupted)
    elif scenario == "online, deterministic empty result":
        transport = FakeTransport(status_code=200, body=empty_body)
    else:
        transport = FakeTransport(status_code=status_code, body=SEMANTIC_SCHOLAR_BODY)

    registry = CapabilityRegistry(allow_network=network_allowed)
    register_search_adapters(
        registry,
        settings=make_settings(
            SEMANTIC_SCHOLAR_API_KEY=api_key,
            AUTORESEARCH_NETWORK_ENABLED=network_allowed,
        ),
        transport=transport,
    )

    invocation = registry.invoke("semantic_scholar_search", make_request())

    assert invocation.receipt.status == expected, scenario
    assert invocation.receipt.outcome_status == expected, scenario
    if expected == CapabilityReceiptStatus.DENIED:
        assert transport.calls == [], scenario
    if expected in (
        CapabilityReceiptStatus.FAILED,
        CapabilityReceiptStatus.UNKNOWN,
        CapabilityReceiptStatus.DENIED,
    ):
        assert not invocation.receipt.candidates_admissible, scenario
        assert invocation.admissible_candidates == [], scenario


def test_deterministic_empty_result_is_a_success_not_an_unknown():
    """D-F8-01: a legal query with zero hits is a deterministic terminal success."""

    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry,
        settings=make_settings(SEMANTIC_SCHOLAR_API_KEY="k"),
        transport=FakeTransport(body=json.dumps({"total": 0, "data": []})),
    )

    invocation = registry.invoke("semantic_scholar_search", make_request())

    assert invocation.receipt.status == CapabilityReceiptStatus.COMPLETED
    assert invocation.receipt.candidate_count == 0
    assert invocation.receipt.admitted is None or isinstance(invocation.receipt.admitted, bool)
    assert any("D-F8-01" in item for item in invocation.diagnostics)


def test_identically_retried_invocation_replays_with_the_same_fingerprint():
    registry = CapabilityRegistry(allow_network=True)
    transport = FakeTransport(body=SEMANTIC_SCHOLAR_BODY)
    register_search_adapters(
        registry, settings=make_settings(SEMANTIC_SCHOLAR_API_KEY="k"), transport=transport
    )

    first = registry.invoke("semantic_scholar_search", make_request())
    second = registry.invoke("semantic_scholar_search", make_request())

    assert first.receipt.request_fingerprint == second.receipt.request_fingerprint
    assert second.receipt.status == CapabilityReceiptStatus.REPLAYED
    assert second.receipt.outcome_status == CapabilityReceiptStatus.COMPLETED
    assert second.receipt.candidates_admissible
    assert len(transport.calls) == 1


def test_adapter_instances_are_reusable_across_requests():
    transport = FakeTransport(body=SEMANTIC_SCHOLAR_BODY)
    adapter = SemanticScholarSearchAdapter(api_key="k", transport=transport)
    registry = CapabilityRegistry(allow_network=True)
    registry.register(
        adapter.manifest(),
        adapter,
        trust_tier="candidate_only",
        kind="native",
        network_required=True,
        allowed_network_domains=list(adapter.allowed_network_domains),
    )
    first = registry.invoke("semantic_scholar_search", make_request(invocation_id="inv-a"))
    second = registry.invoke("semantic_scholar_search", make_request(invocation_id="inv-b"))
    assert first.receipt.candidate_count == second.receipt.candidate_count == 2
    assert first.receipt.request_fingerprint != second.receipt.request_fingerprint


def test_arxiv_adapter_can_be_used_standalone_for_probes():
    adapter = ArxivSearchAdapter(transport=FakeTransport(body=ARXIV_BODY))
    assert adapter.allowed_network_domains == ("export.arxiv.org",)
    assert adapter.manifest().evidence_mode == "candidate_only"


# --------------------------------------------------------------------------- #
# OpenAlex: the ADR-01 s5 degraded track
# --------------------------------------------------------------------------- #

OPENALEX_BODY = json.dumps(
    {
        "meta": {"count": 1, "cost_usd": 0.001},
        "results": [
            {
                "id": "https://openalex.org/W123",
                "display_name": "Perineuronal nets stabilize the grid cell network",
                "abstract_inverted_index": {"Grid": [0], "cells": [1], "stabilize": [2]},
                "authorships": [{"author": {"display_name": "D. Neuroscientist"}}],
                "publication_year": 2023,
                "doi": "https://doi.org/10.1000/example.3",
                "primary_location": {"landing_page_url": "https://example.org/w123"},
            }
        ],
    }
)

# Measured on 2026-09-11: OpenAlex answers HTTP 200 with this body when throttled.
OPENALEX_THROTTLED_BODY = json.dumps(
    {
        "error": "Rate limit exceeded",
        "message": (
            "Anonymous search is temporarily rate-limited while the search cluster is under "
            "elevated load. Please retry in 11s, or use a free API key for uninterrupted access."
        ),
        "retryAfter": 11,
    }
)


def test_openalex_reconstructs_the_inverted_abstract_index():
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry, settings=make_settings(), transport=FakeTransport(body=OPENALEX_BODY)
    )

    invocation = registry.invoke("openalex_search", make_request())

    assert invocation.receipt.status == CapabilityReceiptStatus.COMPLETED
    candidate = invocation.admissible_candidates[0]
    assert candidate.source_id == "https://openalex.org/W123"
    assert candidate.independent_source == "10.1000/example.3"
    assert candidate.metadata["abstract_present"] is True
    assert candidate.metadata["year"] == 2023


def test_openalex_throttling_arrives_as_http_200_and_is_still_a_known_failure():
    adapter = OpenAlexSearchAdapter(transport=FakeTransport(body=OPENALEX_THROTTLED_BODY))
    registry = CapabilityRegistry(allow_network=True)
    registry.register(
        adapter.manifest(),
        adapter,
        trust_tier="candidate_only",
        kind="native",
        network_required=True,
        allowed_network_domains=list(adapter.allowed_network_domains),
    )

    invocation = registry.invoke("openalex_search", make_request())

    assert invocation.receipt.status == CapabilityReceiptStatus.FAILED
    assert invocation.receipt.outcome_status == CapabilityReceiptStatus.FAILED
    assert not invocation.receipt.candidates_admissible
    assert any("retry after 11s" in item for item in invocation.diagnostics)
    assert adapter.rate_limit_events == 1
    assert adapter.last_retry_after_seconds == 11.0


def test_openalex_quota_headers_reach_the_limit_monitor_and_never_the_fingerprint():
    transport = FakeTransport(
        body=OPENALEX_BODY,
        headers={
            "X-RateLimit-Remaining": "690",
            "X-RateLimit-Limit": "1000",
            "X-RateLimit-Cost-USD": "0.001",
        },
    )
    adapter = OpenAlexSearchAdapter(transport=transport)
    registry = CapabilityRegistry(allow_network=True)
    registry.register(
        adapter.manifest(),
        adapter,
        trust_tier="candidate_only",
        kind="native",
        network_required=True,
        allowed_network_domains=list(adapter.allowed_network_domains),
    )

    invocation = registry.invoke("openalex_search", make_request())

    assert any("limit monitor" in item for item in invocation.diagnostics)
    summary = adapter.rate_limit_summary()
    assert summary["provider_quota"]["quota_remaining"] == "690"
    assert summary["provider_quota"]["last_query_cost_usd"] == "0.001"
    # quota counters are monitoring data: they ride along in diagnostics but must
    # never enter the request fingerprint, which is what replay identity depends on
    assert "690" not in invocation.receipt.request_fingerprint
    assert "690" not in make_request().model_dump_json()


def test_openalex_non_rate_limit_error_body_is_a_known_failure():
    body = json.dumps({"error": "Invalid query", "message": "per-page must be <= 200"})
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry, settings=make_settings(), transport=FakeTransport(body=body)
    )

    invocation = registry.invoke("openalex_search", make_request())

    assert invocation.receipt.status == CapabilityReceiptStatus.FAILED
    assert any("per-page must be <= 200" in item for item in invocation.diagnostics)


def test_openalex_uses_the_bearer_credential_only_when_configured():
    transport = FakeTransport(body=OPENALEX_BODY)
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry,
        settings=make_settings(OPENALEX_API_KEY="oa-secret"),
        transport=transport,
    )
    registry.invoke("openalex_search", make_request())
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer oa-secret"

    transport.calls.clear()
    registry_anon = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry_anon, settings=make_settings(), transport=transport
    )
    registry_anon.invoke("openalex_search", make_request())
    assert "Authorization" not in transport.calls[0]["headers"]


def test_rate_limit_monitor_counts_events_without_touching_the_receipt():
    transport = FakeTransport(status_code=429, headers={"Retry-After": "3"})
    adapter = ArxivSearchAdapter(transport=transport)
    registry = CapabilityRegistry(allow_network=True)
    registry.register(
        adapter.manifest(),
        adapter,
        trust_tier="candidate_only",
        kind="native",
        network_required=True,
        allowed_network_domains=list(adapter.allowed_network_domains),
    )

    first = registry.invoke("arxiv_search", make_request(invocation_id="rl-1"))
    second = registry.invoke("arxiv_search", make_request(invocation_id="rl-2"))

    assert first.receipt.status == CapabilityReceiptStatus.FAILED
    assert second.receipt.status == CapabilityReceiptStatus.FAILED
    assert adapter.rate_limit_events == 2
    assert adapter.rate_limit_summary()["last_retry_after_seconds"] == 3.0
    assert any("retry after 3s" in item for item in second.diagnostics)
    assert "rate_limit_events" not in second.receipt.model_dump_json()


def test_unparseable_retry_after_header_does_not_break_the_receipt():
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry,
        settings=make_settings(),
        transport=FakeTransport(status_code=429, headers={"Retry-After": "in 5 minutes"}),
    )

    invocation = registry.invoke("arxiv_search", make_request())

    assert invocation.receipt.status == CapabilityReceiptStatus.FAILED
    assert not any("retry after" in item for item in invocation.diagnostics)


def test_server_error_is_unknown_because_the_provider_outcome_is_unprovable():
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry, settings=make_settings(), transport=FakeTransport(status_code=503)
    )

    invocation = registry.invoke("arxiv_search", make_request())

    assert invocation.receipt.status == CapabilityReceiptStatus.UNKNOWN


def test_openalex_forwards_the_polite_pool_contact_when_configured():
    transport = FakeTransport(body=OPENALEX_BODY)
    openalex = OpenAlexSearchAdapter(transport=transport, polite_mailto="team@example.org")
    registry = CapabilityRegistry(allow_network=True)
    registry.register(
        openalex.manifest(),
        openalex,
        trust_tier="candidate_only",
        kind="native",
        network_required=True,
        allowed_network_domains=list(openalex.allowed_network_domains),
    )

    registry.invoke("openalex_search", make_request())

    assert transport.calls[0]["params"]["mailto"] == "team@example.org"


@pytest.mark.parametrize(
    ("source", "body"),
    [
        (SEMANTIC_SCHOLAR_SOURCE, "not json"),
        (SEMANTIC_SCHOLAR_SOURCE, "[]"),
        (SEMANTIC_SCHOLAR_SOURCE, '{"total": 0}'),
        (SEMANTIC_SCHOLAR_SOURCE, '{"data": {"not": "a list"}}'),
        (SEMANTIC_SCHOLAR_SOURCE, '{"data": ["not an object"]}'),
        (OPENALEX_SOURCE, "not json"),
        (OPENALEX_SOURCE, "[]"),
        (OPENALEX_SOURCE, '{"meta": {}}'),
        (OPENALEX_SOURCE, '{"results": {"not": "a list"}}'),
        (OPENALEX_SOURCE, '{"results": ["not an object"]}'),
    ],
)
def test_malformed_provider_payloads_never_become_a_pass(source, body):
    """A garbage payload must land on `failed`, never on `completed`."""

    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry,
        settings=make_settings(SEMANTIC_SCHOLAR_API_KEY="k"),
        transport=FakeTransport(body=body),
    )

    invocation = registry.invoke(f"{source}_search", make_request())

    assert invocation.receipt.status == CapabilityReceiptStatus.FAILED, (source, body)
    assert invocation.admissible_candidates == [], (source, body)
    assert any("provider" in item for item in invocation.diagnostics), (source, body)


def test_candidate_falls_back_to_a_usable_independent_source_when_nothing_else_exists():
    body = json.dumps(
        {
            "total": 1,
            "data": [
                {
                    "paperId": None,
                    "title": "Untitled but real",
                    "abstract": "",
                    "authors": [],
                    "year": None,
                    "externalIds": {},
                    "url": None,
                }
            ],
        }
    )
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry,
        settings=make_settings(SEMANTIC_SCHOLAR_API_KEY="k"),
        transport=FakeTransport(body=body),
    )

    invocation = registry.invoke("semantic_scholar_search", make_request())

    candidate = invocation.admissible_candidates[0]
    assert candidate.independent_source == "semantic_scholar:Untitled but real"
    assert candidate.source_uri is None


def test_openalex_abstract_index_that_is_not_a_mapping_is_treated_as_absent():
    body = json.dumps({"results": [{"display_name": "No abstract here",
                                    "abstract_inverted_index": None}]})
    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(
        registry, settings=make_settings(), transport=FakeTransport(body=body)
    )

    invocation = registry.invoke("openalex_search", make_request())

    assert invocation.receipt.status == CapabilityReceiptStatus.COMPLETED
    assert invocation.admissible_candidates[0].metadata["abstract_present"] is False


