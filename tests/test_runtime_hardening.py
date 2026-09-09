from __future__ import annotations

import json
import os
import subprocess
import sys
from multiprocessing import get_context
from pathlib import Path

import pytest
from a2_runtime_fixtures import (
    FixtureService,
    compact_record,
    durable_projection,
    paper,
    request_for,
    run_conflict,
    run_crash_after_service_started,
    run_duplicate,
    run_evidence_before_receipt,
    run_partial_write,
    run_process_restart,
    run_timeout,
    stale_writer_process,
)

from autoresearch.capability import PaperSearchCapabilityAdapter, UnknownProviderError
from autoresearch.invocation_contracts import InvocationPhase, InvocationStatus, request_fingerprint
from autoresearch.storage import RecordStore


def test_crash_after_service_started_is_reproducible(tmp_path: Path):
    first = run_crash_after_service_started(tmp_path / "first")
    second = run_crash_after_service_started(tmp_path / "second")

    assert first["returncode"] == second["returncode"] == 37
    assert durable_projection(first) == durable_projection(second)
    assert first["connector_calls"] == second["connector_calls"] == 1
    assert first["record"]["state"] == "pending"
    assert first["record"]["phase"] == InvocationPhase.SERVICE_STARTED.value


def test_timeout_is_unknown_and_replayable(tmp_path: Path):
    result = run_timeout(tmp_path)

    assert result["receipt"]["status"] == InvocationStatus.UNKNOWN_OUTCOME.value
    assert result["replay_status"] == InvocationStatus.REPLAYED.value
    assert result["durable_record"]["final_status"] == InvocationStatus.UNKNOWN_OUTCOME.value
    assert result["connector_calls"] == 1
    assert "provider timeout" in result["diagnostics"][0]


def test_uncertain_provider_error_is_unknown_with_reason_preserved(tmp_path: Path):
    store = RecordStore(tmp_path / "uncertain.sqlite3")
    adapter = PaperSearchCapabilityAdapter(
        FixtureService(error=UnknownProviderError("connection outcome was lost")),
        store,
    )

    result = adapter.invoke(request_for("uncertain-error"))

    assert result.receipt.outcome_status == InvocationStatus.UNKNOWN_OUTCOME
    assert "UnknownProviderError" in result.diagnostics[0]
    assert "connection outcome was lost" in result.diagnostics[0]


def test_deterministic_provider_failure_remains_failed_with_reason_preserved(tmp_path: Path):
    store = RecordStore(tmp_path / "deterministic.sqlite3")
    adapter = PaperSearchCapabilityAdapter(
        FixtureService(error=RuntimeError("provider rejected request")),
        store,
    )

    result = adapter.invoke(request_for("deterministic-error"))

    assert result.receipt.outcome_status == InvocationStatus.FAILED
    assert "RuntimeError" in result.diagnostics[0]
    assert "provider rejected request" in result.diagnostics[0]


def test_process_restart_recovers_service_started_as_unknown(tmp_path: Path):
    result = run_process_restart(tmp_path)

    assert result["before"]["state"] == InvocationStatus.PENDING.value
    assert result["before"]["phase"] == InvocationPhase.SERVICE_STARTED.value
    assert result["receipt"]["outcome_status"] == InvocationStatus.UNKNOWN_OUTCOME.value
    assert result["durable_record"]["state"] == "finalized"
    assert result["connector_calls"] == 1


def test_partial_write_finalizes_staged_result_without_duplicate_facts(tmp_path: Path):
    result = run_partial_write(tmp_path)

    assert result["crash"]["returncode"] == 41
    assert result["before"]["phase"] == InvocationPhase.SERVICE_RETURNED.value
    assert result["before"]["has_staged_result"] is True
    assert result["receipt"]["outcome_status"] == InvocationStatus.COMPLETED.value
    assert result["after"]["state"] == "finalized"
    assert {
        key: result["durable_facts_before"][key]
        for key in ("papers", "evidence", "wiki")
    } == {
        key: result["durable_facts_after"][key]
        for key in ("papers", "evidence", "wiki")
    }
    assert result["durable_facts_after"]["audit_events"] == (
        result["durable_facts_before"]["audit_events"] + 1
    )
    assert result["connector_calls"] == 1


def test_evidence_before_receipt_recovers_unknown_without_duplicate_facts(tmp_path: Path):
    result = run_evidence_before_receipt(tmp_path)

    assert result["crash"]["returncode"] == 43
    assert result["crash"]["facts_marker"] is True
    assert result["before"]["phase"] == InvocationPhase.SERVICE_STARTED.value
    assert result["before"]["has_final_result"] is False
    assert result["receipt"]["outcome_status"] == InvocationStatus.UNKNOWN_OUTCOME.value
    assert result["after"]["state"] == "finalized"
    assert {
        key: result["durable_facts_before"][key]
        for key in ("papers", "evidence", "wiki")
    } == {
        key: result["durable_facts_after"][key]
        for key in ("papers", "evidence", "wiki")
    }


def test_duplicate_submission_replays_without_second_side_effect(tmp_path: Path):
    result = run_duplicate(tmp_path)

    assert result["replay_status"] == InvocationStatus.REPLAYED.value
    assert result["connector_calls"] == 1
    assert result["durable_facts"]["papers"] == 1
    assert result["durable_facts"]["evidence"] == 1
    assert result["durable_facts"]["wiki"] == 1


def test_conflicting_fingerprint_is_rejected_without_second_side_effect(tmp_path: Path):
    result = run_conflict(tmp_path)

    assert result["rejection"]["exception"] == "InvocationConflictError"
    assert result["connector_calls"] == 1


def test_recovery_uses_reserved_phase_for_deterministic_failure(tmp_path: Path):
    store = RecordStore(tmp_path / "reserved.sqlite3")
    service = FixtureService(papers=[paper()])
    adapter = PaperSearchCapabilityAdapter(service, store)
    request = request_for("reserved-recovery")
    key = f"{request.run_id}:{request.invocation_id}"
    store.reserve_idempotent(
        adapter.scope,
        key,
        {**request.model_dump(mode="json"), "request_fingerprint": request_fingerprint(request)},
    )

    recovered = adapter.recover_pending(
        request.run_id,
        request.invocation_id,
        reason="restart before connector start",
        outcome_status=InvocationStatus.UNKNOWN_OUTCOME,
    )

    assert recovered.receipt.outcome_status == InvocationStatus.FAILED
    assert service.calls == 0
    assert "reserved" in recovered.diagnostics[0]
    event = store.events(request.project_id)[-1]
    assert event["payload"]["phase"] == InvocationPhase.RESERVED.value
    assert event["payload"]["recovery_action"] == "close_pending"


def test_recovery_uses_service_started_phase_for_unknown(tmp_path: Path):
    store = RecordStore(tmp_path / "started.sqlite3")
    adapter = PaperSearchCapabilityAdapter(FixtureService(), store)
    request = request_for("started-recovery")
    key = f"{request.run_id}:{request.invocation_id}"
    store.reserve_idempotent(
        adapter.scope,
        key,
        {**request.model_dump(mode="json"), "request_fingerprint": request_fingerprint(request)},
    )
    store.mark_idempotent_phase(adapter.scope, key, InvocationPhase.SERVICE_STARTED.value)

    recovered = adapter.recover_pending(
        request.run_id,
        request.invocation_id,
        reason="restart after connector start",
        outcome_status=InvocationStatus.FAILED,
    )

    assert recovered.receipt.outcome_status == InvocationStatus.UNKNOWN_OUTCOME
    assert "service_started" in recovered.diagnostics[0]
    event = store.events(request.project_id)[-1]
    assert event["payload"]["phase"] == InvocationPhase.SERVICE_STARTED.value
    assert event["payload"]["recovery_action"] == "close_pending"


def test_invalid_phase_transition_is_in_pytest_regression(tmp_path: Path):
    store = RecordStore(tmp_path / "phase.sqlite3")
    request = request_for("phase-guard")
    key = f"{request.run_id}:{request.invocation_id}"
    store.reserve_idempotent(
        "paper_search",
        key,
        {**request.model_dump(mode="json"), "request_fingerprint": request_fingerprint(request)},
    )

    with pytest.raises(RuntimeError, match="invalid invocation phase transition"):
        store.mark_idempotent_phase("paper_search", key, InvocationPhase.SERVICE_RETURNED.value)


def test_cross_process_stale_writer_cannot_overwrite_finalized_record(tmp_path: Path):
    db_path = tmp_path / "toctou.sqlite3"
    store = RecordStore(db_path)
    request = request_for("toctou")
    key = f"{request.run_id}:{request.invocation_id}"
    store.reserve_idempotent(
        "paper_search",
        key,
        {**request.model_dump(mode="json"), "request_fingerprint": request_fingerprint(request)},
    )
    context = get_context("spawn")
    ready = context.Event()
    finalized = context.Event()
    result_queue = context.Queue()
    process = context.Process(
        target=stale_writer_process,
        args=(str(db_path), ready, finalized, result_queue),
    )
    process.start()
    assert ready.wait(timeout=30)

    store.finalize_idempotent(
        "paper_search",
        key,
        {"receipt": {"outcome_status": InvocationStatus.FAILED.value}},
    )
    finalized.set()
    process.join(timeout=30)

    assert process.exitcode == 0
    assert result_queue.get(timeout=5)["exception"] == "RuntimeError"
    final_record = store.get_idempotent("paper_search", key)
    assert compact_record(final_record)["state"] == "finalized"
    assert compact_record(final_record)["phase"] == InvocationPhase.FINALIZED.value


def test_fault_matrix_command_writes_diagnostic_report(tmp_path: Path):
    script = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "rearchitecture"
        / "worktrees"
        / "A-runtime-hardening"
        / "a2_fault_matrix.py"
    )
    output = tmp_path / "fault-matrix.json"
    env = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (source_root, env.get("PYTHONPATH")) if value
    )
    completed = subprocess.run(
        [sys.executable, str(script), str(output)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema"] == "p1-a2-fault-matrix/v1"
    assert report["overall_passed"] is True
    assert {entry["scenario_id"] for entry in report["scenarios"]} == {
        "timeout",
        "process_restart",
        "evidence_before_receipt",
        "partial_write",
        "duplicate_submission",
        "conflicting_fingerprint",
    }
    for entry in report["scenarios"]:
        assert entry["passed"] is True
        assert len(entry["request_fingerprint"]) == 64
        assert "connector_calls" in entry
        assert entry["side_effect_count"] == entry["connector_calls"]
        assert "durable_facts" in entry
