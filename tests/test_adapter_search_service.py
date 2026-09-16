"""A8 mainline retrieval adapter acceptance.

The point of this package is that the **mainline** -- not the benchmark -- stops
using the anonymous bare ``httpx.get`` connector and goes through the A5
retrieval adapters. So the assertions here are the invariants that distinguish
the two paths, and each one is chosen to *fail* on the legacy service:

1. ``abstract`` survives into the persisted record. The candidate-only path
   reduces it to a boolean, and the reader degrades to title-only without it.
2. A missing Semantic Scholar key sends **no request at all** (the legacy
   connector sends an anonymous one and collects HTTP 429).
3. Rate-limit pressure is counted and observable rather than swallowed into a
   diagnostic string.
4. The legacy persistence side effects still happen, because the reader resolves
   papers by id out of the store.

Every test runs offline through an injected transport, so the suite is
re-runnable in CI without network access or credentials.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from autoresearch.adapter_search_service import AdapterBackedPaperSearchService
from autoresearch.config import Settings
from autoresearch.contracts import EvidenceGrade, KnowledgePartition, PaperRecord
from autoresearch.evidence import EvidenceService
from autoresearch.knowledge import KnowledgeService
from autoresearch.search_adapters import (
    SEMANTIC_SCHOLAR_SOURCE,
    RetrievalRateLimited,
    SemanticScholarSearchAdapter,
    TransportResponse,
)
from autoresearch.search_service import PaperSearchService
from autoresearch.storage import RecordStore

SEMANTIC_SCHOLAR_BODY = json.dumps(
    {
        "total": 2,
        "data": [
            {
                "paperId": "S2-0001",
                "title": "Grid cells in the medial entorhinal cortex",
                "abstract": "We report grid-like firing fields in layer II.",
                "authors": [{"name": "A. Researcher"}, {"name": "B. Author"}],
                "year": 2024,
                "externalIds": {"DOI": "10.1000/example.1"},
                "url": "https://www.semanticscholar.org/paper/S2-0001",
            },
        ],
    }
)


class RecordingTransport:
    """Records every call so 'no request was sent' claims stay checkable."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        body: str = "",
        raises: Exception | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
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
    values: dict[str, object] = {"_env_file": None, "AUTORESEARCH_NETWORK_ENABLED": True}
    values.update(overrides)
    return Settings(**values)


@pytest.fixture()
def services(tmp_path):
    store = RecordStore(tmp_path / "db.sqlite")
    return store, EvidenceService(store), KnowledgeService(store)


def build_service(services, transport, *, api_key="test-key", network_enabled=True):
    store, evidence, knowledge = services
    adapter = SemanticScholarSearchAdapter(
        api_key=api_key, transport=transport, timeout=5.0
    )
    service = AdapterBackedPaperSearchService(
        store,
        evidence,
        knowledge,
        adapters={SEMANTIC_SCHOLAR_SOURCE: adapter},
        network_enabled=network_enabled,
    )
    return service, adapter


# --------------------------------------------------------------------------- #
# 1. The abstract survives (the legacy candidate path loses it)
# --------------------------------------------------------------------------- #


def test_mainline_record_carries_the_full_abstract(services):
    """The reader degrades to title-only without an abstract, so this is load-bearing."""

    transport = RecordingTransport(body=SEMANTIC_SCHOLAR_BODY)
    service, _ = build_service(services, transport)

    outcome = service.search("p1", ["grid cells"])

    assert len(outcome.papers) == 1
    paper = outcome.papers[0]
    assert paper.abstract == "We report grid-like firing fields in layer II."
    assert paper.authors == ["A. Researcher", "B. Author"]
    assert paper.year == 2024
    assert paper.doi == "10.1000/example.1"


def test_abstract_reaches_the_store_not_only_the_return_value(services):
    """The reader resolves papers by id out of the store, not from the return value."""

    store, _, _ = services
    transport = RecordingTransport(body=SEMANTIC_SCHOLAR_BODY)
    service, _ = build_service(services, transport)

    outcome = service.search("p1", ["grid cells"])
    stored = store.get("paper", outcome.papers[0].paper_id)

    assert stored is not None
    reloaded = PaperRecord.model_validate(stored)
    assert reloaded.abstract == "We report grid-like firing fields in layer II."


# --------------------------------------------------------------------------- #
# 2. Fail-closed without a key (the legacy connector goes anonymous)
# --------------------------------------------------------------------------- #


def test_missing_key_sends_no_request_at_all(services):
    """The legacy connector would issue an anonymous call and collect HTTP 429."""

    transport = RecordingTransport(body=SEMANTIC_SCHOLAR_BODY)
    service, _ = build_service(services, transport, api_key=None)

    outcome = service.search("p1", ["grid cells"])

    assert transport.calls == [], "no request may be sent without credentials"
    assert outcome.papers == []
    joined = " ".join(outcome.diagnostics).lower()
    assert "credential" in joined or "api_key" in joined


def test_legacy_connector_omits_the_api_key_header_contrast(services):
    """Contrast probe: documents *why* the mainline was moved off the legacy path.

    This asserts the legacy behaviour that motivated ``D-A5-偏离-1`` rather than a
    property we want. It is kept executable so the reason for the migration does
    not decay into a comment someone can mistake for folklore.
    """

    from autoresearch.search_service import SemanticScholarConnector

    legacy_connector = SemanticScholarConnector()
    assert not hasattr(legacy_connector, "api_key"), (
        "the legacy connector carries no credential surface at all"
    )

    adapter_transport = RecordingTransport(body=SEMANTIC_SCHOLAR_BODY)
    adapter = SemanticScholarSearchAdapter(
        api_key="secret", transport=adapter_transport, timeout=5.0
    )
    adapter.retrieve(_request("p1", "grid cells"))
    assert adapter_transport.calls[0]["headers"].get("x-api-key") == "secret"


# --------------------------------------------------------------------------- #
# 3. Rate-limit pressure is counted, not swallowed
# --------------------------------------------------------------------------- #


def test_rate_limit_events_are_counted_and_observable(services):
    transport = RecordingTransport(status_code=429, headers={"Retry-After": "6"})
    service, adapter = build_service(services, transport)

    outcome = service.search("p1", ["grid cells"])

    assert outcome.papers == []
    summary = adapter.rate_limit_summary()
    assert summary["rate_limit_events"] == 1
    assert summary["last_retry_after_seconds"] == 6.0
    assert any("rate limited" in item for item in outcome.diagnostics)


def test_rate_limit_is_not_reported_as_a_legitimate_empty_result(services):
    """D-F8-01 only covers a legal query with genuinely zero hits, not a refused call."""

    transport = RecordingTransport(status_code=429)
    service, _ = build_service(services, transport)

    outcome = service.search("p1", ["grid cells"])

    assert outcome.papers == []
    assert any("rate limited" in item for item in outcome.diagnostics)


def test_retrieve_primitive_raises_so_the_caller_can_classify(services):
    """``retrieve()`` must not swallow the rate-limit signal; the caller classifies."""

    adapter = SemanticScholarSearchAdapter(
        api_key="k", transport=RecordingTransport(status_code=429), timeout=5.0
    )

    with pytest.raises(RetrievalRateLimited):
        adapter.retrieve(_request("p1", "grid cells"))
    assert adapter.rate_limit_summary()["rate_limit_events"] == 1


# --------------------------------------------------------------------------- #
# 4. Legacy persistence semantics are preserved
# --------------------------------------------------------------------------- #


def test_persistence_side_effects_match_the_legacy_contract(services):
    """paper record + E1 evidence + wiki page, exactly as the legacy path wrote them."""

    store, evidence, _ = services
    transport = RecordingTransport(body=SEMANTIC_SCHOLAR_BODY)
    service, _ = build_service(services, transport)

    outcome = service.search("p1", ["grid cells"])
    paper = outcome.papers[0]

    assert store.get("paper", paper.paper_id) is not None
    items = [
        item for item in evidence.list("p1", valid_only=True) if item.source_id == paper.paper_id
    ]
    assert items, "a paper must be backed by an evidence item"
    assert items[0].grade == EvidenceGrade.E1

    page = service.knowledge.get_page(paper.paper_id)
    assert page is not None, "the legacy path wrote a wiki page per paper"
    assert page.partition == KnowledgePartition.PAPERS
    assert page.evidence_ids


def test_duplicate_hits_are_deduped_by_doi(services):
    """Two queries returning the same DOI must not create two paper records."""

    transport = RecordingTransport(body=SEMANTIC_SCHOLAR_BODY)
    service, _ = build_service(services, transport)

    outcome = service.search("p1", ["grid cells", "entorhinal grid"])

    assert len(outcome.papers) == 1


# --------------------------------------------------------------------------- #
# 5. Offline mode is explicit, not a silent degradation
# --------------------------------------------------------------------------- #


def test_network_disabled_contacts_no_provider_and_says_so(services):
    transport = RecordingTransport(body=SEMANTIC_SCHOLAR_BODY)
    service, _ = build_service(services, transport, network_enabled=False)

    outcome = service.search("p1", ["grid cells"])

    assert transport.calls == []
    assert any("disabled" in item.lower() for item in outcome.diagnostics)


def test_seed_papers_still_flow_with_the_network_disabled(services):
    transport = RecordingTransport(body=SEMANTIC_SCHOLAR_BODY)
    service, _ = build_service(services, transport, network_enabled=False)
    seed = PaperRecord(project_id="p1", title="Seed paper", source="manual")

    outcome = service.search("p1", ["grid cells"], seed_papers=[seed])

    assert [paper.title for paper in outcome.papers] == ["Seed paper"]


def test_rate_limit_summary_covers_every_adapter(services):
    transport = RecordingTransport(body=SEMANTIC_SCHOLAR_BODY)
    service, _ = build_service(services, transport)

    service.search("p1", ["grid cells"])

    summary = service.rate_limit_summary()
    assert SEMANTIC_SCHOLAR_SOURCE in summary
    assert "rate_limit_events" in summary[SEMANTIC_SCHOLAR_SOURCE]


def _request(project_id: str, query: str):
    from autoresearch.search_adapters import SearchAdapterRequest

    return SearchAdapterRequest(
        project_id=project_id,
        run_id="r1",
        invocation_id="i1",
        query=query,
        limit=5,
    )


# --------------------------------------------------------------------------- #
# 6. Wiring: the mainline actually uses this service
# --------------------------------------------------------------------------- #

def test_mainline_application_wires_the_adapter_backed_service(runtime):
    """The whole point of the package: the mainline must not keep the legacy path.

    Without this assertion every other test here can pass while ``application.py``
    still assembles ``PaperSearchService`` -- the module would exist, be tested,
    and be dead code. Verified by construction: on the pre-fix tree (new module
    present, ``application.py`` untouched) the other twelve tests pass and this
    one fails.
    """

    from autoresearch.application import AutoResearchApplication

    assert isinstance(runtime, AutoResearchApplication)
    assert isinstance(runtime.search, AdapterBackedPaperSearchService)
    assert not isinstance(runtime.search, PaperSearchService)


def test_the_a4_reliable_boundary_still_wraps_the_new_service(runtime):
    """Swapping the port implementation must not drop idempotency/replay/recovery."""

    from autoresearch.application import InvocationBoundedSearchPort
    from autoresearch.capability import PaperSearchCapabilityAdapter

    assert isinstance(runtime.search_port, InvocationBoundedSearchPort)
    assert isinstance(runtime.search_capability, PaperSearchCapabilityAdapter)
    assert isinstance(runtime.search_capability.service, AdapterBackedPaperSearchService)


def test_query_id_fragments_do_not_collide(services):
    """Distinct queries must not share an ``invocation_id``.

    A naive slug (``re.sub(r"\\W+", "-", ...)``) maps ``"a b"`` and ``"a-b"`` to
    the same fragment, which would make the A4 ledger replay the second query as
    the first. Found by self-review before commit; this test keeps it fixed.
    """

    from autoresearch.adapter_search_service import _fingerprint_text

    pairs = [("a b", "a-b"), ("!!!", "???"), ("grid cells", "grid  cells")]
    for left, right in pairs:
        assert _fingerprint_text(left) != _fingerprint_text(right), (left, right)
    assert _fingerprint_text("grid cells") == _fingerprint_text("grid cells")


def test_end_to_end_the_agent_reaches_the_retrieval_adapter(runtime, monkeypatch):
    """Asserts the *whole* chain, not just one link.

    ``runtime.search`` being the new type is necessary but not sufficient: the
    agent's real entry point is ``search_port``, which reaches the service through
    ``PaperSearchCapabilityAdapter``. A wiring mistake that replaced only one of
    those objects would leave the agent on the old path while a service-level
    assertion still passed.

    The probe counts calls on the adapter the mainline actually reaches, and
    replaces its transport so the assertion stays offline and re-runnable. An
    earlier version of this test let the real transport run and hit the live
    provider -- it passed, but a test that depends on the network is not evidence
    in CI.
    """

    from autoresearch.agents.paper_search import PaperSearchAgent
    from autoresearch.search_adapters import (
        SEMANTIC_SCHOLAR_SOURCE,
        SemanticScholarSearchAdapter,
    )

    agent = runtime.paper_search_agent
    assert isinstance(agent, PaperSearchAgent)
    assert agent.search is runtime.search_port

    service = runtime.search_capability.service
    assert isinstance(service, AdapterBackedPaperSearchService)

    # Swap in an offline adapter of the same class so the reached object is still
    # identifiable while no provider is contacted.
    offline_transport = RecordingTransport(body=SEMANTIC_SCHOLAR_BODY)
    offline = SemanticScholarSearchAdapter(
        api_key="probe-key", transport=offline_transport, timeout=5.0
    )
    # Replace the whole adapter map, not just the Semantic Scholar entry: the
    # arxiv / openalex adapters built by ``build_search_adapters`` carry real
    # transports, and leaving them in place makes this test contact live providers
    # (it took 17s of network time before this was fixed).
    service.adapters = {SEMANTIC_SCHOLAR_SOURCE: offline}
    service.network_enabled = True

    # A unique query keeps the A4 idempotency ledger from replaying a previous
    # invocation of the same identity (that replay is itself correct behaviour and
    # is asserted separately below).
    unique_query = f"probe-{uuid4().hex}"
    outcome = runtime.search_port.search("probe-project", [unique_query])

    assert offline_transport.calls, "the mainline did not reach the retrieval adapter"
    assert [paper.title for paper in outcome.papers] == [
        "Grid cells in the medial entorhinal cortex"
    ]

    # The same invocation identity must now replay instead of re-contacting the
    # provider: this is the A4 boundary still doing its job through the new service.
    calls_before = len(offline_transport.calls)
    replayed = runtime.search_port.search("probe-project", [unique_query])
    assert len(offline_transport.calls) == calls_before, "replay must not re-fetch"
    assert [paper.title for paper in replayed.papers] == [
        "Grid cells in the medial entorhinal cortex"
    ]


# --------------------------------------------------------------------------- #
# 7. Failure reporting: unknown must not be recorded as a normal value
# --------------------------------------------------------------------------- #


class _BoomAdapter:
    """Fails every call with the exception it was handed."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    def retrieve(self, request):
        raise self.exc

    def rate_limit_summary(self) -> dict:
        return {"source": "boom"}


def _fail_service(services, exc):
    store, evidence, knowledge = services
    service = AdapterBackedPaperSearchService(
        store,
        evidence,
        knowledge,
        adapters={"boom": _BoomAdapter(exc)},
        network_enabled=True,
    )
    return store, service


def test_provider_exception_messages_never_reach_the_audit_trail(services, tmp_path):
    """A diagnostic is durable, and an exception message is attacker-influenced.

    Found by an author-side probe: an earlier revision interpolated ``{exc}``, and
    a simulated provider error carrying a credential string was found verbatim in
    ``audit_events.payload_json``. Only the type name may be recorded.
    """

    import json
    import sqlite3

    secret = "SECRET-KEY-abcdef123456"
    _, service = _fail_service(services, RuntimeError(f"{secret} rejected by provider"))

    outcome = service.search("p1", ["q"])

    assert secret not in " ".join(outcome.diagnostics)
    assert "RuntimeError" in " ".join(outcome.diagnostics)

    connection = sqlite3.connect(tmp_path / "db.sqlite")
    try:
        rows = [row[0] for row in connection.execute("select payload_json from audit_events")]
    finally:
        connection.close()
    assert rows, "the run must have been audited"
    assert not any(secret in json.dumps(row) for row in rows), (
        "a provider exception message reached the durable audit trail"
    )


def test_zero_hits_and_provider_failure_are_distinguishable_by_the_caller(services):
    """The distinction must be machine-readable, not a matter of wording.

    An earlier revision "fixed" this by rewording a diagnostic and asserting on
    the text. That left the actual decision untouched: ``paper_search.py`` only
    branches on ``if not outcome.papers``, so both cases still landed in
    ``WAITING_EVIDENCE`` with the same blocker. A reworded message changes no
    decision. Independent review caught that; this test pins the flag instead.
    """

    class Empty:
        def retrieve(self, request):
            return []

        def rate_limit_summary(self):
            return {}

    store, evidence, knowledge = services
    healthy = AdapterBackedPaperSearchService(
        store, evidence, knowledge, adapters={"e": Empty()}, network_enabled=True
    )
    _, failing = _fail_service(services, RuntimeError("down"))

    healthy_outcome = healthy.search("p1", ["q"])
    failing_outcome = failing.search("p1", ["q"])

    assert healthy_outcome.provider_failure is False
    assert failing_outcome.provider_failure is True


def test_fatal_errors_are_not_absorbed_as_provider_failures(services):
    """MemoryError means the run is untrustworthy, not that the provider failed."""

    _, service = _fail_service(services, MemoryError("out of memory"))

    with pytest.raises(MemoryError):
        service.search("p1", ["q"])


def test_keyboard_interrupt_is_not_listed_as_a_caught_fatal_error():
    """It cannot be: it derives from BaseException, not Exception.

    Listing it inside a guard called from ``except Exception`` reads like
    protection that does not exist -- dead code pretending to be a safety net.
    """

    assert not issubclass(KeyboardInterrupt, Exception)
    assert not issubclass(SystemExit, Exception)

    from autoresearch.adapter_search_service import _is_fatal

    assert _is_fatal(MemoryError()) is True
    assert _is_fatal(RuntimeError()) is False


def test_the_agent_branches_on_the_flag_not_on_the_wording(runtime):
    """End-to-end: the two outcomes must produce different blockers."""

    from autoresearch.agents.paper_search import PaperSearchAgent
    from autoresearch.search_service import SearchOutcome

    class _StubSearch:
        def __init__(self, outcome):
            self._outcome = outcome

        def search(self, *_args, **_kwargs):
            return self._outcome

    class _StubHandoffs:
        def accept(self, *_args, **_kwargs):
            return None

    class _Permissive:
        def transition(self, _current, target):
            return target

    base_state = {
        "project_id": "demo",
        "run_id": "run-1",
        "idea": "x",
        "evidence_ids": [],
        "diagnostics": [],
        "lifecycle_state": "intake",
        "seed_papers": [],
        "search_queries": ["q"],
        "handoff": None,
        "last_agent": None,
    }

    zero_hits = PaperSearchAgent(
        search=_StubSearch(SearchOutcome(diagnostics=["No papers were found."])),
        evidence=None,
        handoffs=_StubHandoffs(),
        state_machine=_Permissive(),
    )
    failed = PaperSearchAgent(
        search=_StubSearch(
            SearchOutcome(diagnostics=["... failed"], provider_failure=True)
        ),
        evidence=None,
        handoffs=_StubHandoffs(),
        state_machine=_Permissive(),
    )

    zero_blocker = zero_hits.run(dict(base_state))["blockers"][-1]
    failed_blocker = failed.run(dict(base_state))["blockers"][-1]

    assert zero_blocker != failed_blocker
    assert "Retrieval failed" in failed_blocker
    assert "Retrieval failed" not in zero_blocker


def test_source_composition_is_reported_in_the_run(services):
    """Switching the wiring changed which providers are queried.

    The legacy path queried openalex + crossref + semantic_scholar; the adapter
    path queries semantic_scholar + arxiv + openalex. A composition change is a
    behaviour change, so it must be visible in the run rather than only in a diff.
    """

    class Empty:
        def retrieve(self, request):
            return []

        def rate_limit_summary(self):
            return {}

    store, evidence, knowledge = services
    service = AdapterBackedPaperSearchService(
        store,
        evidence,
        knowledge,
        adapters={"semantic_scholar": Empty(), "arxiv": Empty(), "openalex": Empty()},
        network_enabled=True,
    )

    outcome = service.search("p1", ["q"])

    joined = " ".join(outcome.diagnostics)
    assert "Retrieval sources for this run" in joined
    assert "semantic_scholar" in joined and "arxiv" in joined and "openalex" in joined
    assert "crossref" not in joined


# --------------------------------------------------------------------------- #
# 8. F4: a claim must describe the material, and unverifiable hits are refused
# --------------------------------------------------------------------------- #


def _single_hit_service(services, hit, *, source="s"):
    store, evidence, knowledge = services

    class Hits:
        def retrieve(self, request):
            return [hit]

        def rate_limit_summary(self):
            return {}

    return (
        AdapterBackedPaperSearchService(
            store, evidence, knowledge, adapters={source: Hits()}, network_enabled=True
        ),
        store,
        evidence,
        knowledge,
    )


def test_claim_does_not_assert_an_abstract_that_is_absent(services):
    """The claim and the wiki body describe one record; they must not contradict.

    Before this, a hit without an abstract produced a claim saying "and its
    supplied abstract exist" while the wiki page written in the same call said
    "No abstract was supplied."
    """

    from autoresearch.search_adapters import RetrievedPaper

    service, _, evidence, knowledge = _single_hit_service(
        services, RetrievedPaper(title="No abstract here", source_record_id="s1")
    )

    outcome = service.search("p1", ["q"])
    item = evidence.list("p1", valid_only=True)[0]
    page = knowledge.get_page(outcome.papers[0].paper_id)

    assert "abstract" not in item.claim.lower()
    assert page.body == "No abstract was supplied."
    assert item.metadata["abstract_present"] is False


def test_claim_asserts_the_abstract_when_one_is_present(services):
    from autoresearch.search_adapters import RetrievedPaper

    service, _, evidence, _ = _single_hit_service(
        services, RetrievedPaper(title="Has abstract", abstract="Body text.", source_record_id="s1")
    )

    service.search("p1", ["q"])
    item = evidence.list("p1", valid_only=True)[0]

    assert "abstract" in item.claim.lower()
    assert item.metadata["abstract_present"] is True


def test_a_hit_with_no_identifiers_is_refused_instead_of_minted_as_evidence(services):
    """No DOI, URL or provider id means no bibliographic claim is possible.

    Minting an E1 for it would let unverifiable material reach the gate.
    """

    from autoresearch.search_adapters import RetrievedPaper

    service, store, evidence, _ = _single_hit_service(
        services, RetrievedPaper(title="Untitled")
    )

    outcome = service.search("p1", ["q"])

    assert outcome.papers == []
    assert store.list("paper", partition="papers") == []
    assert evidence.list("p1", valid_only=True) == []
    assert any("refused" in item for item in outcome.diagnostics)


def test_a_user_seed_without_identifiers_is_still_accepted(services):
    """A seed's provenance is the user's own file, so a missing DOI is not a defect.

    The first version of the F4 fix refused these too, silently dropping
    legitimate input; the seed-paper test caught the over-correction.
    """

    service_us, evidence_us = _seed_service(services)
    seed = PaperRecord(project_id="p1", title="User seed", source="manual")

    outcome = service_us.search("p1", ["q"], seed_papers=[seed])

    assert [paper.title for paper in outcome.papers] == ["User seed"]
    items = evidence_us.list("p1", valid_only=True)
    assert items[0].independent_source == "user_supplied:manual"
    assert items[0].metadata["user_supplied"] is True


def _seed_service(services):
    store, evidence, knowledge = services
    return (
        AdapterBackedPaperSearchService(
            store, evidence, knowledge, adapters={}, network_enabled=True
        ),
        evidence,
    )


def test_empty_provenance_no_longer_degrades_to_a_placeholder():
    """``"s:None"`` used to be produced when every identifier was missing."""

    from autoresearch.search_service import independent_source_for

    assert independent_source_for(PaperRecord(project_id="p", title="T", source="s")) is None
    assert independent_source_for(
        PaperRecord(project_id="p", title="T", source="s", doi="10.1/x")
    ) == "doi:10.1/x"


# --------------------------------------------------------------------------- #
# 9. N1: a partially failed retrieval must not look fully healthy
# --------------------------------------------------------------------------- #


def test_partial_provider_failure_is_recorded_even_with_papers(services):
    """One source down, another returning papers: the run must say so.

    The receipt is COMPLETED as soon as any paper exists, so without the flag a
    run whose primary source never answered is indistinguishable from a healthy
    one.
    """

    from autoresearch.search_adapters import RetrievalCredentialsRequired, RetrievedPaper

    store, evidence, knowledge = services

    class Failing:
        def retrieve(self, request):
            raise RetrievalCredentialsRequired("no key configured")

        def rate_limit_summary(self):
            return {}

    class Working:
        def retrieve(self, request):
            return [RetrievedPaper(title="From secondary", source_record_id="s1")]

        def rate_limit_summary(self):
            return {}

    service = AdapterBackedPaperSearchService(
        store,
        evidence,
        knowledge,
        adapters={"semantic_scholar": Failing(), "openalex": Working()},
        network_enabled=True,
    )

    outcome = service.search("p1", ["q"])

    assert len(outcome.papers) == 1, "the secondary source did return a paper"
    assert outcome.provider_failure is True, (
        "the primary source never answered and that fact must survive alongside the results"
    )


def test_partial_failure_survives_the_a4_boundary(services):
    """The receipt keeps the fact even though its status stays COMPLETED."""

    from autoresearch.capability import PaperSearchCapabilityAdapter
    from autoresearch.invocation_contracts import InvocationStatus, PaperSearchRequest
    from autoresearch.search_adapters import RetrievalCredentialsRequired, RetrievedPaper

    store, evidence, knowledge = services

    class Failing:
        def retrieve(self, request):
            raise RetrievalCredentialsRequired("no key configured")

        def rate_limit_summary(self):
            return {}

    class Working:
        def retrieve(self, request):
            return [RetrievedPaper(title="From secondary", source_record_id="s1")]

        def rate_limit_summary(self):
            return {}

    service = AdapterBackedPaperSearchService(
        store,
        evidence,
        knowledge,
        adapters={"semantic_scholar": Failing(), "openalex": Working()},
        network_enabled=True,
    )
    adapter = PaperSearchCapabilityAdapter(service, store)

    invocation = adapter.invoke(
        PaperSearchRequest(
            project_id="p1", run_id="r1", invocation_id="i1", query="q", limit=5
        )
    )

    assert invocation.receipt.outcome_status is InvocationStatus.COMPLETED
    assert invocation.receipt.provider_failure is True


def test_a_healthy_run_does_not_claim_a_failure(services):
    """The flag must discriminate, not always fire."""

    from autoresearch.search_adapters import RetrievedPaper

    store, evidence, knowledge = services

    class Working:
        def retrieve(self, request):
            return [RetrievedPaper(title="Fine", source_record_id="s1")]

        def rate_limit_summary(self):
            return {}

    service = AdapterBackedPaperSearchService(
        store, evidence, knowledge, adapters={"openalex": Working()}, network_enabled=True
    )

    outcome = service.search("p1", ["q"])

    assert outcome.provider_failure is False


# --------------------------------------------------------------------------- #
# 10. N1 (decision level): the fact must reach a consumer, not just the receipt
# --------------------------------------------------------------------------- #


def _agent_with_outcome(outcome):
    from autoresearch.agents.paper_search import PaperSearchAgent

    class StubSearch:
        def search(self, *_args, **_kwargs):
            return outcome

    class StubEvidence:
        def list(self, *_args, **_kwargs):
            return []

    class StubHandoffs:
        def accept(self, *_args, **_kwargs):
            return None

        def issue(self, envelope):
            class Issued:
                handoff_id = envelope.handoff_id

                def model_dump(self, **_kwargs):
                    return envelope.model_dump(mode="json")

            return Issued()

    class Permissive:
        def transition(self, _current, target):
            return target

    return PaperSearchAgent(
        search=StubSearch(),
        evidence=StubEvidence(),
        handoffs=StubHandoffs(),
        state_machine=Permissive(),
    )


_BASE_STATE = {
    "project_id": "demo",
    "run_id": "r",
    "idea": "x",
    "evidence_ids": [],
    "diagnostics": [],
    "warnings": [],
    "lifecycle_state": "intake",
    "seed_papers": [],
    "search_queries": ["q"],
    "handoff": None,
    "last_agent": None,
}


def test_refused_records_reach_the_agent_as_a_warning():
    """A silently shrinking paper set must be visible, not just logged."""

    from autoresearch.contracts import PaperRecord
    from autoresearch.search_service import SearchOutcome

    outcome = SearchOutcome(
        papers=[PaperRecord(project_id="demo", title="Kept", source="openalex")],
        refused_records=3,
    )

    result = _agent_with_outcome(outcome).run(dict(_BASE_STATE))

    assert any("3 retrieved record" in w for w in result["warnings"])


def test_refused_records_are_counted_and_survive_the_a4_boundary(services):
    from autoresearch.capability import PaperSearchCapabilityAdapter
    from autoresearch.invocation_contracts import PaperSearchRequest
    from autoresearch.search_adapters import RetrievedPaper

    store, evidence, knowledge = services

    class Mixed:
        def retrieve(self, request):
            return [
                RetrievedPaper(title="Kept", source_record_id="s1"),
                RetrievedPaper(title="No identifiers"),
            ]

        def rate_limit_summary(self):
            return {}

    service = AdapterBackedPaperSearchService(
        store, evidence, knowledge, adapters={"s": Mixed()}, network_enabled=True
    )
    adapter = PaperSearchCapabilityAdapter(service, store)

    invocation = adapter.invoke(
        PaperSearchRequest(project_id="p1", run_id="r", invocation_id="i", query="q", limit=5)
    )

    assert invocation.receipt.refused_records == 1


# --------------------------------------------------------------------------- #
# 11. The warning channel must survive the graph and reach the run record
# --------------------------------------------------------------------------- #


def test_workflow_state_declares_warnings():
    """langgraph keeps only the keys the state schema declares.

    Without this declaration a node that writes ``warnings`` has its value
    silently dropped when the graph runs -- the fact is not merely unread, it
    never exists. The earlier tests drove the agent directly, so they could not
    observe this.
    """

    from autoresearch.agents.base import WorkflowState, single_node_subgraph

    assert "warnings" in WorkflowState.__annotations__

    def node(state):
        out = dict(state)
        out["warnings"] = ["incomplete retrieval"]
        return out

    result = single_node_subgraph("n", node).invoke({"project_id": "x"})

    assert result.get("warnings") == ["incomplete retrieval"]


def test_incomplete_retrieval_warning_survives_the_graph():
    """End to end through langgraph, not a direct agent call.

    This is the shape the third review found missing: the headline behaviour was
    asserted only against a directly-constructed agent, so deleting the warning
    code left the whole suite green.
    """

    from autoresearch.agents.base import single_node_subgraph
    from autoresearch.agents.paper_search import PaperSearchAgent
    from autoresearch.contracts import PaperRecord
    from autoresearch.search_service import SearchOutcome

    class StubSearch:
        def search(self, *_args, **_kwargs):
            return SearchOutcome(
                papers=[PaperRecord(project_id="demo", title="From secondary", source="openalex")],
                provider_failure=True,
            )

    class StubEvidence:
        def list(self, *_args, **_kwargs):
            return []

    class StubHandoffs:
        def accept(self, *_args, **_kwargs):
            return None

        def issue(self, envelope):
            class _Issued:
                handoff_id = envelope.handoff_id

                def model_dump(self, **_kwargs):
                    return envelope.model_dump(mode="json")

            return _Issued()

    class Permissive:
        def transition(self, _current, target):
            return target

    agent = PaperSearchAgent(
        search=StubSearch(),
        evidence=StubEvidence(),
        handoffs=StubHandoffs(),
        state_machine=Permissive(),
    )
    graph = single_node_subgraph("search", agent.run)

    result = graph.invoke(
        {"project_id": "demo", "run_id": "r", "idea": "x", "lifecycle_state": "intake"}
    )

    assert result.get("warnings"), "the incomplete-retrieval fact must survive the graph"
    assert any("incomplete" in w.lower() for w in result["warnings"])


def test_run_record_lifts_warnings_to_the_top_level(runtime, project):
    """A caller reading a run must see the warning without opening ``state``."""

    record = runtime._save_run(
        {
            "run_id": "r1",
            "project_id": "demo",
            "run_status": "pending",
            "lifecycle_state": "literature_searched",
            "warnings": ["retrieval was incomplete"],
        }
    )

    assert record["warnings"] == ["retrieval was incomplete"]
    assert record["status"] == "pending"


def test_a_run_without_warnings_reports_an_empty_list(runtime, project):
    """The field is always present, so a caller never has to guard for its absence."""

    record = runtime._save_run(
        {
            "run_id": "r2",
            "project_id": "demo",
            "run_status": "pending",
            "lifecycle_state": "literature_searched",
        }
    )

    assert record["warnings"] == []


# --------------------------------------------------------------------------- #
# 12. The warning must be surfaced, not only stored
# --------------------------------------------------------------------------- #


def test_cli_status_surfaces_warnings_on_stderr(runtime, project, monkeypatch):
    """A non-blocking warning reads as a successful run, so it must be shown.

    stdout stays a parseable JSON document; the human-readable notice goes to
    stderr.
    """

    from typer.testing import CliRunner

    from autoresearch import cli as cli_module

    monkeypatch.setattr(cli_module, "AutoResearchApplication", lambda: runtime)
    runtime._save_run(
        {
            "run_id": "run-with-warning",
            "project_id": "demo",
            "run_status": "pending",
            "lifecycle_state": "literature_searched",
            "warnings": ["Retrieval was incomplete: at least one source failed to answer."],
        }
    )

    result = CliRunner().invoke(cli_module.app, ["status", "run-with-warning"])

    assert result.exit_code == 0
    # Assert on stderr alone. An earlier version of this assertion also accepted
    # the string appearing in stdout, which made it vacuously true: the JSON
    # document carries the same sentence as the warning value. Deleting the CLI
    # notice left this test green -- the classic tautological assertion.
    assert "warning: Retrieval was incomplete" in result.stderr
    assert '"warnings"' in result.stdout, "the JSON document must still carry the field"


def test_cli_status_is_quiet_when_there_are_no_warnings(runtime, project, monkeypatch):
    from typer.testing import CliRunner

    from autoresearch import cli as cli_module

    monkeypatch.setattr(cli_module, "AutoResearchApplication", lambda: runtime)
    runtime._save_run(
        {
            "run_id": "run-quiet",
            "project_id": "demo",
            "run_status": "pending",
            "lifecycle_state": "literature_searched",
        }
    )

    result = CliRunner().invoke(cli_module.app, ["status", "run-quiet"])

    assert result.exit_code == 0
    assert "warning:" not in result.stderr
    assert "warning:" not in result.stdout


def test_warning_survives_the_full_production_graph(runtime, project):
    """The single-node subgraph is not the production graph.

    ``application.py`` builds an 8-node graph, and a warning only reaches the end
    if every downstream agent preserves the key. That invariant was previously
    untested: the earlier test used ``single_node_subgraph``, so a downstream
    agent that rebuilt its state dict would drop the warning with the suite green.
    """

    from autoresearch.contracts import PaperRecord, RunRequest
    from autoresearch.search_service import SearchOutcome

    class InjectedPartialFailure:
        """One source failed; a secondary one still returned a paper."""

        def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
            return SearchOutcome(
                papers=[
                    PaperRecord(
                        project_id=project_id,
                        title="From secondary",
                        abstract="Body text about evidence gates and provenance.",
                        source="openalex",
                        source_record_id="s1",
                    )
                ],
                diagnostics=["semantic_scholar failed"],
                provider_failure=True,
            )

        def build_request(self, *_args, **_kwargs):
            return runtime.search_port.build_request(
                "demo", "q", limit=5, seed_papers=None
            )

    original = runtime.paper_search_agent.search
    runtime.paper_search_agent.search = InjectedPartialFailure()
    try:
        record = runtime.run(RunRequest(project_id="demo", idea="test idea"))
    finally:
        runtime.paper_search_agent.search = original

    assert record["warnings"], "the incomplete retrieval must reach the run record"
    assert any("incomplete" in w.lower() for w in record["warnings"])


def test_the_warning_never_disappears_between_nodes(runtime, project):
    """A warning must not be dropped by an intermediate node.

    The eight-node graph only preserves ``warnings`` because every agent keeps it
    implicitly, via ``model_copy(update=...)``. None of them names the field, so a
    refactor that rebuilds the state explicitly -- a normal-looking change --
    would silently drop it again. This walks the graph node by node and asserts
    the field survives from the moment it appears.
    """

    from autoresearch.contracts import PaperRecord, ResearchState
    from autoresearch.search_service import SearchOutcome

    class InjectedPartialFailure:
        def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
            return SearchOutcome(
                papers=[
                    PaperRecord(
                        project_id=project_id,
                        title="From secondary",
                        abstract="Body text about evidence gates and provenance.",
                        source="openalex",
                        source_record_id="s1",
                    )
                ],
                provider_failure=True,
            )

        def build_request(self, *_args, **_kwargs):
            return runtime.search_port.build_request("demo", "q", limit=5, seed_papers=None)

    original = runtime.paper_search_agent.search
    runtime.paper_search_agent.search = InjectedPartialFailure()
    try:
        state = ResearchState(project_id="demo", idea="test idea")
        trace: list[tuple[str, list[str]]] = []
        for chunk in runtime.graph.stream(
            state.model_dump(mode="json"),
            config={"configurable": {"thread_id": "warning-trace"}},
        ):
            for node, update in chunk.items():
                if isinstance(update, dict) and "warnings" in update:
                    trace.append((node, list(update["warnings"])))
    finally:
        runtime.paper_search_agent.search = original

    nodes_with_warning = [node for node, warnings in trace if warnings]
    assert nodes_with_warning, "the injected partial failure never produced a warning"

    # Once the warning appears it must be present in every later node that
    # reports the key at all.
    first = next(i for i, (_, w) in enumerate(trace) if w)
    for node, warnings in trace[first:]:
        assert warnings, f"node {node!r} dropped the warning it should have carried"


def test_run_index_projection_carries_warnings(runtime, project):
    """The run index is where runs are summarised; it must not hide them.

    It already listed ``blockers``. Listing blocking problems while omitting the
    non-blocking ones is exactly the asymmetry that made this defect survive.
    """

    import json

    from autoresearch.contracts import PaperRecord, RunRequest
    from autoresearch.search_service import SearchOutcome

    class InjectedPartialFailure:
        def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
            return SearchOutcome(
                papers=[
                    PaperRecord(
                        project_id=project_id,
                        title="From secondary",
                        abstract="Body text about evidence gates and provenance.",
                        source="openalex",
                        source_record_id="s1",
                    )
                ],
                provider_failure=True,
            )

        def build_request(self, *_args, **_kwargs):
            return runtime.search_port.build_request("demo", "q", limit=5, seed_papers=None)

    original = runtime.paper_search_agent.search
    runtime.paper_search_agent.search = InjectedPartialFailure()
    try:
        runtime.run(RunRequest(project_id="demo", idea="test idea"))
    finally:
        runtime.paper_search_agent.search = original

    index_path = runtime.settings.projects_dir / "demo" / "state" / "RUN_INDEX.jsonl"
    entries = [
        json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line
    ]

    assert entries, "the run index must have an entry"
    assert entries[-1].get("warnings"), "the projection must not hide a non-blocking warning"
