from __future__ import annotations

import json
from pathlib import Path

import pytest

from autoresearch.audit import AuditRuntime, BoundedEvidenceView
from autoresearch.audit_contracts import (
    AuditCategory,
    AuditCitation,
    AuditReceiptStatus,
    AuditVerdictStatus,
)
from autoresearch.audit_stdio import build_report, selftest_payload
from autoresearch.resolver import (
    ResolverRecord,
    ResolverSnapshot,
    ResolverSnapshotConflictError,
    ResolverSnapshotRepository,
    SnapshotResolverAdapter,
)
from autoresearch.storage import RecordStore

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "audit" / "citations.jsonl"


def _fixtures() -> list[dict]:
    return [json.loads(line) for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines()]


def _run_scenario(scenario: dict, tmp_path: Path):
    request = scenario["request"]
    from autoresearch.audit_contracts import AuditInvocationRequest

    invocation = AuditInvocationRequest.model_validate(request)
    resolver = SnapshotResolverAdapter(
        [ResolverRecord.model_validate(item) for item in scenario.get("resolver_records", [])],
        snapshot_version=invocation.resolver_snapshot_version,
        available=scenario.get("resolver_available", True),
    )
    store = RecordStore(tmp_path / f"{scenario['scenario_id']}.sqlite3")
    view = BoundedEvidenceView.model_validate(scenario.get("evidence_view", {}))
    report = AuditRuntime(store, resolver).invoke(invocation, evidence_view=view)
    return report, store


def test_fixture_deterministic_categories_match_ground_truth(tmp_path: Path):
    for scenario in _fixtures():
        report, _ = _run_scenario(scenario, tmp_path)
        expected = scenario["expected"]
        for category, status in expected.items():
            if category == "candidate_count":
                assert len(report.candidates) == status
                continue
            actual = [
                verdict.status.value
                for verdict in report.verdicts
                if verdict.category == AuditCategory(category)
            ]
            assert status in actual, (scenario["scenario_id"], category, actual)


def test_network_unavailable_is_unknown_not_fail_open(tmp_path: Path):
    scenario = next(item for item in _fixtures() if item["scenario_id"] == "network_unavailable")
    report, _ = _run_scenario(scenario, tmp_path)
    assert report.verdicts
    assert all(verdict.status == AuditVerdictStatus.UNKNOWN for verdict in report.verdicts)
    assert "fail-closed" in " ".join(report.diagnostics)


def test_audit_replay_is_idempotent_and_does_not_write_evidence_or_gate(tmp_path: Path):
    scenario = next(item for item in _fixtures() if item["scenario_id"] == "locator_match")
    report, store = _run_scenario(scenario, tmp_path)
    from autoresearch.audit_contracts import AuditInvocationRequest

    invocation = AuditInvocationRequest.model_validate(scenario["request"])
    resolver = SnapshotResolverAdapter(
        [ResolverRecord.model_validate(item) for item in scenario["resolver_records"]],
        snapshot_version=invocation.resolver_snapshot_version,
    )
    replay = AuditRuntime(store, resolver).invoke(
        invocation.model_copy(update={"invocation_id": "different-invocation"}),
        evidence_view=BoundedEvidenceView.model_validate(scenario["evidence_view"]),
    )
    assert replay.receipt.status == AuditReceiptStatus.REPLAYED
    assert replay.artifact.artifact_id == report.artifact.artifact_id
    assert store.list("evidence") == []
    assert store.list("gate_decision") == []
    assert len(store.list("audit_report")) == 1


def test_audit_returns_candidate_only_in_runtime_mode(tmp_path: Path):
    scenario = next(item for item in _fixtures() if item["scenario_id"] == "locator_match")
    report, store = _run_scenario(scenario, tmp_path)
    assert report.candidates
    assert store.list("evidence") == []
    assert all(candidate.grade is None for candidate in report.candidates)


def test_resolver_snapshot_is_persisted_reloaded_and_immutable(tmp_path: Path):
    store = RecordStore(tmp_path / "snapshots.sqlite3")
    record = ResolverRecord(
        resolver_key="doi:10.1000/fixture-a",
        title="Evidence-aware agent workflows",
        doi="10.1000/fixture-a",
    )
    repository = ResolverSnapshotRepository(store)
    snapshot = ResolverSnapshot.from_records([record], snapshot_version="snapshot-v1")
    repository.save(snapshot)

    reloaded = SnapshotResolverAdapter.from_store(
        store,
        snapshot_version="snapshot-v1",
    )
    assert reloaded.snapshot is not None
    assert reloaded.snapshot.checksum == snapshot.checksum
    assert reloaded.resolve(
        AuditCitation(
            citation_id="citation-1",
            title=record.title,
            doi=record.doi,
        )
    ).record == record

    changed = ResolverSnapshot.from_records(
        [record.model_copy(update={"title": "Changed title"})],
        snapshot_version="snapshot-v1",
    )
    with pytest.raises(ResolverSnapshotConflictError):
        repository.save(changed)


def test_plain_jsonl_stdio_builds_report_from_envelope(tmp_path: Path):
    store = RecordStore(tmp_path / "stdio.sqlite3")
    scenario = next(item for item in _fixtures() if item["scenario_id"] == "existence_present")
    report = build_report(
        {
            "request": scenario["request"],
            "resolver_records": scenario["resolver_records"],
        },
        store,
    )
    assert report.receipt.status.value == "completed"
    assert any(
        verdict.category.value == "existence" and verdict.status.value == "pass"
        for verdict in report.verdicts
    )


def test_selftest_runs_offline_scenario():
    payload = selftest_payload()
    assert payload["selftest"] is True
    assert payload["receipt_status"] == "completed"
    assert payload["verdict_count"] >= 1
    assert payload["report"]["receipt"]["status"] == "completed"
