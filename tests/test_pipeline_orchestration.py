"""I1 pipeline orchestration tests.

Covers the application-level assembly added in I1: the paper-search agent
routes through the A2 reliable invocation boundary, and the evaluation
section pipeline runs as one orchestrated application entry point with
blocked short-circuit semantics.
"""

from __future__ import annotations

from pathlib import Path

from a2_runtime_fixtures import FixtureService, paper

from autoresearch.application import AutoResearchApplication, InvocationBoundedSearchPort
from autoresearch.contracts import (
    EvidenceCandidate,
    EvidenceGrade,
    EvidenceType,
    ReadingCard,
)
from autoresearch.invocation_contracts import request_fingerprint
from autoresearch.pipeline_contracts import (
    ReadinessStatus,
    ValidationVerdict,
)
from autoresearch.storage import RecordStore


class PaperSearchCapabilityAdapterShim:
    """Adapter over a fixture service, mirroring the application wiring."""

    def __init__(self, service, store: RecordStore):
        from autoresearch.capability import PaperSearchCapabilityAdapter

        self.adapter = PaperSearchCapabilityAdapter(service, store)

    def invoke(self, request):
        return self.adapter.invoke(request)

    def recover_pending(self, run_id, invocation_id, *, reason):
        return self.adapter.recover_pending(run_id, invocation_id, reason=reason)


def test_application_wires_search_through_invocation_boundary(runtime: AutoResearchApplication):
    assert isinstance(runtime.search_port, InvocationBoundedSearchPort)
    assert runtime.search_port.adapter is runtime.search_capability
    assert runtime.paper_search_agent.search is runtime.search_port


def test_bounded_search_replays_without_second_connector_call(tmp_path: Path):
    store = RecordStore(tmp_path / "bounded.sqlite3")
    service = FixtureService(papers=[paper()])
    adapter = PaperSearchCapabilityAdapterShim(service, store)
    port = InvocationBoundedSearchPort(adapter)

    first = port.search("demo", ["query one", "query two"])
    second = port.search("demo", ["query one", "query two"])

    assert service.calls == 2  # one connector call per distinct query
    assert [p.paper_id for p in first.papers] == [p.paper_id for p in second.papers]
    assert len(first.papers) == 1  # identical query dedupes its own result


def test_bounded_search_auto_recovers_pending_record(tmp_path: Path):
    store = RecordStore(tmp_path / "pending.sqlite3")
    service = FixtureService(papers=[paper()])
    adapter = PaperSearchCapabilityAdapterShim(service, store)
    port = InvocationBoundedSearchPort(adapter)

    request = port.build_request("demo", "query one", limit=5, seed_papers=None)
    store.reserve_idempotent(
        "paper_search",
        f"{request.run_id}:{request.invocation_id}",
        {
            **request.model_dump(mode="json"),
            "request_fingerprint": request_fingerprint(request),
        },
    )

    outcome = port.search("demo", ["query one"])

    assert outcome.papers == []
    assert any("recovery found reserved" in item for item in outcome.diagnostics)
    assert service.calls == 0  # recovery never re-calls the connector


def test_run_evaluation_section_returns_all_stages(
    runtime: AutoResearchApplication,
    project,
):
    candidate = EvidenceCandidate(
        project_id="demo",
        evidence_type=EvidenceType.PAPER,
        grade=EvidenceGrade.E1,
        title="Composed fixture paper",
        claim="The source supports a bounded evaluation claim.",
        source_uri="https://example.invalid/composed",
        source_id="source-composed",
        locator="section 1",
        checksum="sha256:composed",
        independent_source="source-composed",
    )
    admission = runtime.evidence.admit_candidate(candidate, actor="i1-test")
    card = ReadingCard(
        project_id="demo",
        paper_id="paper-composed",
        research_question="How should orchestrated evaluation claims stay evidence-bound?",
        method="Comparator method",
        data_or_setting="Offline fixture",
        findings=["A bounded claim remains tied to its evidence."],
        limitations=["The second comparator is not available in this fixture."],
        locators=["p.1"],
        evidence_ids=[admission.evidence_id],
        confidence=0.9,
    )

    result = runtime.run_evaluation_section(
        "demo",
        "Evaluate the orchestrated evaluation section pipeline.",
        [card],
        evidence_ids=[admission.evidence_id],
    )

    assert result.readiness.status != ReadinessStatus.BLOCKED
    assert result.draft is not None
    assert result.validation is not None
    assert result.validation.verdict in (ValidationVerdict.VERIFIED, ValidationVerdict.REVISE)


def test_run_evaluation_section_blocks_and_short_circuits(
    runtime: AutoResearchApplication,
    project,
):
    candidate = EvidenceCandidate(
        project_id="demo",
        evidence_type=EvidenceType.PAPER,
        grade=EvidenceGrade.E1,
        title="Blocking fixture paper",
        claim="The source supports a bounded evaluation claim.",
        source_uri="https://example.invalid/blocking",
        source_id="source-blocking",
        locator="section 1",
        checksum="sha256:blocking",
        independent_source="source-blocking",
    )
    admission = runtime.evidence.admit_candidate(candidate, actor="i1-test")
    card = ReadingCard(
        project_id="demo",
        paper_id="paper-blocking",
        research_question="How should blocked readiness short-circuit the pipeline?",
        method="   ",  # blank method -> no concrete baseline -> readiness BLOCKED
        data_or_setting="Offline fixture",
        findings=["A bounded claim remains tied to its evidence."],
        limitations=["The second comparator is not available in this fixture."],
        locators=["p.1"],
        evidence_ids=[admission.evidence_id],
        confidence=0.9,
    )

    result = runtime.run_evaluation_section(
        "demo",
        "Evaluate the blocked short-circuit path.",
        [card],
        evidence_ids=[admission.evidence_id],
    )

    assert result.readiness.status == ReadinessStatus.BLOCKED
    assert result.draft is None
    assert result.validation is None
