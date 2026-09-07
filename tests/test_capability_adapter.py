from __future__ import annotations

import json
from pathlib import Path

import pytest

from autoresearch.capability import InvocationConflictError, PaperSearchCapabilityAdapter
from autoresearch.contracts import PaperRecord
from autoresearch.invocation_contracts import InvocationPhase, InvocationStatus, PaperSearchRequest
from autoresearch.search_service import SearchOutcome
from autoresearch.storage import RecordStore

FIXTURE = Path(__file__).parent / "fixtures" / "paper_search" / "scenario.json"


def fixture_request() -> PaperSearchRequest:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return PaperSearchRequest(
        project_id=raw["project_id"],
        run_id=raw["run_id"],
        invocation_id=raw["invocation_id"],
        query=raw["query"],
        limit=raw["limit"],
    )


def fixture_paper(project_id: str) -> PaperRecord:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))["papers"][0]
    return PaperRecord(project_id=project_id, source="fixture", **raw)


class FakeSearchService:
    def __init__(
        self,
        *,
        papers: list[PaperRecord] | None = None,
        diagnostics: list[str] | None = None,
        error: Exception | None = None,
        on_call=None,
    ):
        self.papers = papers or []
        self.diagnostics = diagnostics or []
        self.error = error
        self.on_call = on_call
        self.calls = 0

    def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
        self.calls += 1
        if self.on_call:
            self.on_call()
        if self.error:
            raise self.error
        return SearchOutcome(papers=list(self.papers), diagnostics=list(self.diagnostics))


def test_exact_replay_returns_same_business_result_without_second_call(tmp_path: Path):
    store = RecordStore(tmp_path / "runtime.sqlite3")
    service = FakeSearchService(papers=[fixture_paper("demo")])
    adapter = PaperSearchCapabilityAdapter(service, store)
    request = fixture_request()

    first = adapter.invoke(request)
    durable_counts = {
        kind: len(store.list(kind)) for kind in ("paper", "evidence", "wiki_page")
    }
    replay = adapter.invoke(request)

    assert first.receipt.status == InvocationStatus.COMPLETED
    assert replay.receipt.status == InvocationStatus.REPLAYED
    assert replay.receipt.outcome_status == InvocationStatus.COMPLETED
    assert replay.papers == first.papers
    assert replay.evidence_candidates == first.evidence_candidates
    assert durable_counts == {
        kind: len(store.list(kind)) for kind in ("paper", "evidence", "wiki_page")
    }
    assert service.calls == 1


def test_conflicting_replay_is_rejected(tmp_path: Path):
    store = RecordStore(tmp_path / "runtime.sqlite3")
    service = FakeSearchService(papers=[fixture_paper("demo")])
    adapter = PaperSearchCapabilityAdapter(service, store)
    request = fixture_request()
    adapter.invoke(request)

    conflict = request.model_copy(update={"query": "different query"})
    with pytest.raises(InvocationConflictError):
        adapter.invoke(conflict)
    assert service.calls == 1


def test_completed_empty_is_distinct_from_unknown_outcome(tmp_path: Path):
    empty_store = RecordStore(tmp_path / "empty.sqlite3")
    empty = PaperSearchCapabilityAdapter(
        FakeSearchService(),
        empty_store,
    ).invoke(fixture_request())
    assert empty.receipt.status == InvocationStatus.COMPLETED_EMPTY
    assert empty.receipt.outcome_status == InvocationStatus.COMPLETED_EMPTY

    unknown_request = fixture_request().model_copy(update={"invocation_id": "invocation-unknown"})
    unknown_store = RecordStore(tmp_path / "unknown.sqlite3")
    unknown = PaperSearchCapabilityAdapter(
        FakeSearchService(diagnostics=["provider unavailable"]),
        unknown_store,
    ).invoke(unknown_request)
    assert unknown.receipt.status == InvocationStatus.UNKNOWN_OUTCOME
    assert unknown.receipt.outcome_status == InvocationStatus.UNKNOWN_OUTCOME


def test_reservation_exists_before_service_side_effect(tmp_path: Path):
    store = RecordStore(tmp_path / "runtime.sqlite3")
    request = fixture_request()
    observed = []

    def inspect_reservation():
        record = store.get_idempotent("paper_search", f"{request.run_id}:{request.invocation_id}")
        observed.append((record["state"], record["phase"]) if record else None)

    service = FakeSearchService(papers=[fixture_paper("demo")], on_call=inspect_reservation)
    PaperSearchCapabilityAdapter(service, store).invoke(request)

    assert observed == [("pending", InvocationPhase.SERVICE_STARTED.value)]


def test_timeout_is_unknown_and_replayable(tmp_path: Path):
    store = RecordStore(tmp_path / "runtime.sqlite3")
    service = FakeSearchService(error=TimeoutError())
    adapter = PaperSearchCapabilityAdapter(service, store)
    request = fixture_request()

    result = adapter.invoke(request)
    replay = adapter.invoke(request)

    assert result.receipt.status == InvocationStatus.UNKNOWN_OUTCOME
    assert replay.receipt.status == InvocationStatus.REPLAYED
    assert replay.receipt.outcome_status == InvocationStatus.UNKNOWN_OUTCOME
    assert service.calls == 1
