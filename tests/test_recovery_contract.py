from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_capability_adapter import FakeSearchService, fixture_paper, fixture_request

from autoresearch.capability import PaperSearchCapabilityAdapter, PendingInvocationError
from autoresearch.evidence import EvidenceService
from autoresearch.invocation_contracts import (
    InvocationPhase,
    InvocationStatus,
    request_fingerprint,
)
from autoresearch.knowledge import KnowledgeService
from autoresearch.search_service import PaperSearchService
from autoresearch.storage import RecordStore


def test_pending_requires_explicit_recovery_and_does_not_call_service(tmp_path: Path):
    store = RecordStore(tmp_path / "runtime.sqlite3")
    service = FakeSearchService(papers=[fixture_paper("demo")])
    adapter = PaperSearchCapabilityAdapter(service, store)
    request = fixture_request()
    fingerprint = request_fingerprint(request)
    key = f"{request.run_id}:{request.invocation_id}"
    store.reserve_idempotent(
        adapter.scope,
        key,
        {**request.model_dump(mode="json"), "request_fingerprint": fingerprint},
    )

    with pytest.raises(PendingInvocationError, match="recover explicitly"):
        adapter.invoke(request)

    recovered = adapter.fail_pending(
        request.run_id,
        request.invocation_id,
        reason="process restarted before connector outcome was durable",
    )
    replay = adapter.invoke(request)

    assert recovered.receipt.status == InvocationStatus.FAILED
    assert replay.receipt.status == InvocationStatus.REPLAYED
    assert replay.receipt.outcome_status == InvocationStatus.FAILED
    assert service.calls == 0
    assert any(
        event["event_type"] == "capability.invocation_recovered"
        for event in store.events(request.project_id)
    )


def test_replay_survives_new_store_instance(tmp_path: Path):
    db_path = tmp_path / "runtime.sqlite3"
    request = fixture_request()
    first_store = RecordStore(db_path)
    first_service = FakeSearchService(papers=[fixture_paper("demo")])
    PaperSearchCapabilityAdapter(first_service, first_store).invoke(request)

    second_store = RecordStore(db_path)
    second_service = FakeSearchService(papers=[fixture_paper("demo")])
    replay = PaperSearchCapabilityAdapter(second_service, second_store).invoke(request)

    assert replay.receipt.status == InvocationStatus.REPLAYED
    assert replay.receipt.outcome_status == InvocationStatus.COMPLETED
    assert second_service.calls == 0


def test_storage_lists_pending_and_finalized_rows(tmp_path: Path):
    store = RecordStore(tmp_path / "runtime.sqlite3")
    request = fixture_request()
    key = f"{request.run_id}:{request.invocation_id}"
    store.reserve_idempotent(
        "paper_search",
        key,
        {**request.model_dump(mode="json"), "request_fingerprint": request_fingerprint(request)},
    )

    rows = store.list_idempotent("paper_search")

    assert len(rows) == 1
    assert rows[0]["record"]["state"] == "pending"
    assert rows[0]["record"]["phase"] == InvocationPhase.RESERVED.value


def test_service_returned_result_can_be_recovered_without_second_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = RecordStore(tmp_path / "runtime.sqlite3")
    service = FakeSearchService(papers=[fixture_paper("demo")])
    adapter = PaperSearchCapabilityAdapter(service, store)
    request = fixture_request()
    original_finalize = store.finalize_idempotent

    def crash_before_finalize(scope, key, result):
        raise RuntimeError("simulated crash before finalization")

    monkeypatch.setattr(store, "finalize_idempotent", crash_before_finalize)
    with pytest.raises(RuntimeError, match="simulated crash"):
        adapter.invoke(request)

    pending = store.get_idempotent(adapter.scope, f"{request.run_id}:{request.invocation_id}")
    assert pending["state"] == "pending"
    assert pending["phase"] == InvocationPhase.SERVICE_RETURNED.value
    assert "staged_result" in pending

    monkeypatch.setattr(store, "finalize_idempotent", original_finalize)
    restarted_service = FakeSearchService(papers=[fixture_paper("demo")])
    recovered = PaperSearchCapabilityAdapter(restarted_service, store).recover_pending(
        request.run_id,
        request.invocation_id,
        reason="restart detected a staged service result",
    )

    assert recovered.receipt.outcome_status == InvocationStatus.COMPLETED
    assert restarted_service.calls == 0


class FixtureConnector:
    name = "fixture"

    def __init__(self, paper):
        self.paper = paper
        self.calls = 0

    def search(self, query: str, limit: int):
        self.calls += 1
        return [self.paper]


def _paper_projection(papers):
    return sorted(
        (
            paper.title,
            paper.abstract,
            tuple(paper.authors),
            paper.year,
            paper.doi,
            paper.url,
            paper.source,
            paper.source_record_id,
        )
        for paper in papers
    )


def _paper_row_projection(rows):
    return sorted(
        (
            row["title"],
            row["abstract"],
            tuple(row["authors"]),
            row["year"],
            row["doi"],
            row["url"],
            row["source"],
            row["source_record_id"],
        )
        for row in rows
    )


def _durable_projection(store: RecordStore):
    evidence = sorted(
        (
            row["evidence_type"],
            row["grade"],
            row["title"],
            row["claim"],
            row["locator"],
            row["independent_source"],
            row.get("metadata", {}).get("source"),
        )
        for row in store.list("evidence")
    )
    wiki = sorted(
        (
            row["partition"],
            row["title"],
            tuple(row["tags"]),
            bool(row["evidence_ids"]),
        )
        for row in store.list("wiki_page")
    )
    return {
        "papers": _paper_row_projection(store.list("paper")),
        "evidence": evidence,
        "wiki": wiki,
    }


def test_legacy_and_target_paths_have_parity_report(tmp_path: Path):
    raw_paper = {
        "title": "Evidence-aware agent workflows",
        "abstract": "A fixture paper describing auditable research workflows.",
        "authors": ["A. Researcher"],
        "year": 2025,
        "doi": "10.1000/fixture-a",
        "url": "https://example.invalid/fixture-a",
        "source_record_id": "fixture-a",
    }
    legacy_store = RecordStore(tmp_path / "legacy.sqlite3")
    target_store = RecordStore(tmp_path / "target.sqlite3")
    legacy_connector = FixtureConnector(raw_paper)
    target_connector = FixtureConnector(raw_paper)
    legacy_service = PaperSearchService(
        legacy_store,
        EvidenceService(legacy_store),
        KnowledgeService(legacy_store),
        network_enabled=True,
        connectors=[legacy_connector],
    )
    target_service = PaperSearchService(
        target_store,
        EvidenceService(target_store),
        KnowledgeService(target_store),
        network_enabled=True,
        connectors=[target_connector],
    )
    request = fixture_request()

    legacy = legacy_service.search(
        request.project_id, [request.query], per_connector_limit=request.limit
    )
    target = PaperSearchCapabilityAdapter(target_service, target_store).invoke(request)

    report = {
        "paper_result_equal": _paper_projection(legacy.papers) == _paper_projection(target.papers),
        "durable_facts_equal": (
            _durable_projection(legacy_store) == _durable_projection(target_store)
        ),
        "legacy_paper_count": len(legacy_store.list("paper")),
        "target_paper_count": len(target_store.list("paper")),
        "legacy_evidence_count": len(legacy_store.list("evidence")),
        "target_evidence_count": len(target_store.list("evidence")),
        "legacy_wiki_count": len(legacy_store.list("wiki_page")),
        "target_wiki_count": len(target_store.list("wiki_page")),
        "target_invocation_status": target.receipt.outcome_status,
        "target_idempotency_state": target_store.list_idempotent("paper_search")[0][
            "record"
        ]["state"],
    }
    report_path = tmp_path / "parity-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    assert report["paper_result_equal"] is True
    assert report["durable_facts_equal"] is True
    assert report["legacy_paper_count"] == report["target_paper_count"] == 1
    assert report["legacy_evidence_count"] == report["target_evidence_count"] == 1
    assert report["legacy_wiki_count"] == report["target_wiki_count"] == 1
    assert report["target_invocation_status"] == InvocationStatus.COMPLETED
    assert report["target_idempotency_state"] == "finalized"
    assert report_path.is_file()
