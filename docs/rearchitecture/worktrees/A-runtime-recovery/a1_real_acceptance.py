from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path


HERE = Path(__file__).resolve().parent
# The acceptance harness lives four directory levels below the worktree root:
# docs/rearchitecture/worktrees/A-runtime-recovery.
ROOT = HERE.parents[3]
TEMP_TEST = ROOT / "tests" / "a1_acceptance_temp.py"
RUN_ROOT = ROOT / ".a1-acceptance-runs"


TEMP_TEST_CONTENT = textwrap.dedent(
    """
    from __future__ import annotations

    from pathlib import Path

    import pytest

    from autoresearch.capability import (
        InvocationConflictError,
        PaperSearchCapabilityAdapter,
        PendingInvocationError,
    )
    from autoresearch.contracts import PaperRecord
    from autoresearch.invocation_contracts import InvocationPhase, InvocationStatus, request_fingerprint
    from autoresearch.storage import RecordStore

    from test_capability_adapter import FakeSearchService, fixture_paper, fixture_request


    def test_required_a1_apis_exist():
        required = [
            (PaperSearchCapabilityAdapter, "invoke"),
            (PaperSearchCapabilityAdapter, "recover_pending"),
            (PaperSearchCapabilityAdapter, "fail_pending"),
            (RecordStore, "get_idempotent"),
            (RecordStore, "reserve_idempotent"),
            (RecordStore, "mark_idempotent_phase"),
            (RecordStore, "finalize_idempotent"),
            (RecordStore, "list_idempotent"),
        ]
        missing = [f"{cls.__name__}.{method}" for cls, method in required if not hasattr(cls, method)]
        assert not missing, f"missing required A1 API: {missing}"


    def test_fingerprint_is_deterministic_and_query_sensitive():
        base = fixture_request()
        assert request_fingerprint(base) == request_fingerprint(base.model_copy())
        changed = base.model_copy(update={"query": "a different query"})
        assert request_fingerprint(base) != request_fingerprint(changed)


    def test_invalid_phase_transition_is_rejected(tmp_path: Path):
        store = RecordStore(tmp_path / "r.sqlite3")
        request = fixture_request()
        key = f"{request.run_id}:{request.invocation_id}"
        store.reserve_idempotent(
            "paper_search",
            key,
            {**request.model_dump(mode="json"), "request_fingerprint": request_fingerprint(request)},
        )
        with pytest.raises(RuntimeError, match="invalid invocation phase transition"):
            store.mark_idempotent_phase("paper_search", key, InvocationPhase.SERVICE_RETURNED.value)


    def test_provider_failure_is_failed_not_completed(tmp_path: Path):
        result = PaperSearchCapabilityAdapter(
            FakeSearchService(error=RuntimeError("boom")), RecordStore(tmp_path / "r.sqlite3")
        ).invoke(fixture_request())
        assert result.receipt.status == InvocationStatus.FAILED
        assert result.receipt.outcome_status == InvocationStatus.FAILED
        assert any("provider failure" in diagnostic for diagnostic in result.diagnostics)


    def test_recover_rejects_non_terminal_outcome(tmp_path: Path):
        store = RecordStore(tmp_path / "r.sqlite3")
        request = fixture_request()
        key = f"{request.run_id}:{request.invocation_id}"
        store.reserve_idempotent(
            "paper_search",
            key,
            {**request.model_dump(mode="json"), "request_fingerprint": request_fingerprint(request)},
        )
        adapter = PaperSearchCapabilityAdapter(FakeSearchService(), store)
        with pytest.raises(ValueError, match="failed or unknown_outcome"):
            adapter.recover_pending(
                request.run_id,
                request.invocation_id,
                reason="x",
                outcome_status=InvocationStatus.COMPLETED,
            )


    def test_recover_unknown_record_raises_keyerror(tmp_path: Path):
        adapter = PaperSearchCapabilityAdapter(FakeSearchService(), RecordStore(tmp_path / "r.sqlite3"))
        with pytest.raises(KeyError):
            adapter.fail_pending("no-such-run", "no-such-invocation", reason="x")


    def test_invocation_emits_audit_events(tmp_path: Path):
        store = RecordStore(tmp_path / "r.sqlite3")
        request = fixture_request()
        PaperSearchCapabilityAdapter(
            FakeSearchService(papers=[fixture_paper("demo")]), store
        ).invoke(request)
        event_types = {event["event_type"] for event in store.events(request.project_id)}
        assert {
            "capability.invocation_reserved",
            "capability.service_started",
            "capability.service_returned",
            "capability.invocation_finalized",
        } <= event_types


    def test_seed_fingerprint_conflict_is_rejected(tmp_path: Path):
        store = RecordStore(tmp_path / "r.sqlite3")
        service = FakeSearchService()
        adapter = PaperSearchCapabilityAdapter(service, store)
        seed = PaperRecord(project_id="demo", title="Seed A", source="fixture")
        request = fixture_request().model_copy(update={"seed_papers": [seed]})
        adapter.invoke(request)
        with pytest.raises(InvocationConflictError):
            adapter.invoke(request.model_copy(update={"seed_papers": []}))


    def test_timeout_unknown_is_replayable(tmp_path: Path):
        store = RecordStore(tmp_path / "r.sqlite3")
        service = FakeSearchService(error=TimeoutError("boom"))
        adapter = PaperSearchCapabilityAdapter(service, store)
        request = fixture_request()
        first = adapter.invoke(request)
        replay = adapter.invoke(request)
        assert first.receipt.outcome_status == InvocationStatus.UNKNOWN_OUTCOME
        assert replay.receipt.status == InvocationStatus.REPLAYED
        assert replay.receipt.outcome_status == InvocationStatus.UNKNOWN_OUTCOME
        assert service.calls == 1


    def test_empty_outcome_is_completed_empty(tmp_path: Path):
        result = PaperSearchCapabilityAdapter(
            FakeSearchService(), RecordStore(tmp_path / "r.sqlite3")
        ).invoke(fixture_request())
        assert result.receipt.outcome_status == InvocationStatus.COMPLETED_EMPTY
    """
).lstrip()


@dataclass(frozen=True)
class Mutation:
    name: str
    relative_path: str
    old: str
    new: str
    nodeid: str
    count: int = 1


def mutations() -> list[Mutation]:
    return [
        Mutation(
            "M1 fingerprint constant",
            "src/autoresearch/invocation_contracts.py",
            '    payload: dict[str, Any] = request.model_dump(mode="json")\n    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))\n    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()',
            '    return "0" * 64',
            "tests/a1_acceptance_temp.py::test_fingerprint_is_deterministic_and_query_sensitive",
        ),
        Mutation(
            "M2 service_started marker removed",
            "src/autoresearch/capability.py",
            "        self.store.mark_idempotent_phase(\n            self.scope,\n            key,\n            InvocationPhase.SERVICE_STARTED.value,\n        )\n",
            "",
            "tests/test_capability_adapter.py::test_reservation_exists_before_service_side_effect",
        ),
        Mutation(
            "M3 idempotent lookup disabled",
            "src/autoresearch/storage.py",
            '        with self.connection() as connection:\n            row = connection.execute(\n                "SELECT result_json FROM idempotency WHERE scope=? AND idempotency_key=?",\n                (scope, key),\n            ).fetchone()\n        return json.loads(row["result_json"]) if row else None',
            "        return None",
            "tests/test_capability_adapter.py::test_exact_replay_returns_same_business_result_without_second_call",
        ),
        Mutation(
            "M4 conflict rejection removed",
            "src/autoresearch/capability.py",
            '            if existing_fingerprint != fingerprint:\n                raise InvocationConflictError(\n                    "invocation identity is already bound to another request"\n                )\n',
            "",
            "tests/test_capability_adapter.py::test_conflicting_replay_is_rejected",
        ),
        Mutation(
            "M5 uncertainty markers removed",
            "src/autoresearch/capability.py",
            '        uncertain_markers = (\n            "disabled",\n            "failed",\n            "unavailable",\n            "timeout",\n            "unknown",\n            "error",\n        )',
            "        uncertain_markers = ()",
            "tests/test_capability_adapter.py::test_completed_empty_is_distinct_from_unknown_outcome",
        ),
        Mutation(
            "M6 pending guard removed",
            "src/autoresearch/capability.py",
            '            if existing.get("state") == "pending":\n                raise PendingInvocationError("invocation outcome is unknown; recover explicitly")\n            return self._replay(existing)\n',
            "            return self._replay(existing)\n",
            "tests/test_recovery_contract.py::test_pending_requires_explicit_recovery_and_does_not_call_service",
        ),
        Mutation(
            "M7 illegal phase transition allowed",
            "src/autoresearch/storage.py",
            '            if phase not in transitions.get(current, set()):\n                raise RuntimeError(f"invalid invocation phase transition: {current} -> {phase}")\n',
            "",
            "tests/a1_acceptance_temp.py::test_invalid_phase_transition_is_rejected",
        ),
        Mutation(
            "M8 timeout branch removed",
            "src/autoresearch/capability.py",
            '        except TimeoutError:\n            papers = []\n            diagnostics = ["provider timeout; outcome is unknown"]\n            status = InvocationStatus.UNKNOWN_OUTCOME\n',
            "",
            "tests/test_capability_adapter.py::test_timeout_is_unknown_and_replayable",
        ),
        Mutation(
            "M9 provider exception isolation removed",
            "src/autoresearch/capability.py",
            '        except Exception as exc:\n            papers = []\n            diagnostics = [f"provider failure: {type(exc).__name__}"]\n            status = InvocationStatus.FAILED\n',
            "",
            "tests/a1_acceptance_temp.py::test_provider_failure_is_failed_not_completed",
        ),
        Mutation(
            "M10a staged recovery bypassed",
            "src/autoresearch/capability.py",
            "        if isinstance(staged_result, dict):",
            "        if False and isinstance(staged_result, dict):",
            "tests/test_recovery_contract.py::test_service_returned_result_can_be_recovered_without_second_call",
        ),
        Mutation(
            "M10b fail_pending status changed",
            "src/autoresearch/capability.py",
            "            outcome_status=InvocationStatus.FAILED,",
            "            outcome_status=InvocationStatus.UNKNOWN_OUTCOME,",
            "tests/test_recovery_contract.py::test_pending_requires_explicit_recovery_and_does_not_call_service",
        ),
        Mutation(
            "M10c successful recovery allowed",
            "src/autoresearch/capability.py",
            '        if outcome_status not in (InvocationStatus.FAILED, InvocationStatus.UNKNOWN_OUTCOME):\n            raise ValueError("pending recovery must close as failed or unknown_outcome")\n',
            "",
            "tests/a1_acceptance_temp.py::test_recover_rejects_non_terminal_outcome",
        ),
        Mutation(
            "M10d unknown record guard removed",
            "src/autoresearch/capability.py",
            '        if existing is None:\n            raise KeyError(f"unknown idempotency record: {self.scope}:{key}")\n',
            "",
            "tests/a1_acceptance_temp.py::test_recover_unknown_record_raises_keyerror",
        ),
        Mutation(
            "M11 finalized result omitted",
            "src/autoresearch/storage.py",
            '                "result": result,\n',
            "",
            "tests/test_recovery_contract.py::test_replay_survives_new_store_instance",
        ),
        Mutation(
            "M12 target query omitted",
            "src/autoresearch/capability.py",
            "                [request.query],",
            "                [],",
            "tests/test_recovery_contract.py::test_legacy_and_target_paths_have_parity_report",
        ),
        Mutation(
            "M13 service_started audit event removed",
            "src/autoresearch/capability.py",
            '        self.store.append_event(\n            "capability.service_started",\n            {"invocation_id": request.invocation_id},\n            project_id=request.project_id,\n            actor="capability_adapter",\n        )\n',
            "",
            "tests/a1_acceptance_temp.py::test_invocation_emits_audit_events",
        ),
        Mutation(
            "M14 idempotency listing disabled",
            "src/autoresearch/storage.py",
            '        """List invocation records for parity and diagnostics."""\n\n        query = "SELECT scope, idempotency_key, result_json FROM idempotency"',
            '        """List invocation records for parity and diagnostics."""\n\n        return []\n\n        query = "SELECT scope, idempotency_key, result_json FROM idempotency"',
            "tests/test_recovery_contract.py::test_storage_lists_pending_and_finalized_rows",
        ),
    ]


def run_pytest(*nodes: str, label: str) -> tuple[int, str]:
    base = RUN_ROOT / label
    if base.exists():
        shutil.rmtree(base)
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", *nodes, "-q", "--basetemp", str(base)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def apply_mutation(item: Mutation) -> bytes:
    path = ROOT / item.relative_path
    original = path.read_bytes()
    text = original.decode("utf-8").replace("\r\n", "\n")
    if text.count(item.old) < item.count:
        raise AssertionError(f"{item.name}: mutation target not found")
    path.write_bytes(text.replace(item.old, item.new, item.count).encode("utf-8"))
    return original


def main() -> int:
    target_paths = [
        "src/autoresearch/capability.py",
        "src/autoresearch/invocation_contracts.py",
        "src/autoresearch/storage.py",
    ]
    clean = subprocess.run(
        ["git", "diff", "--quiet", "--", *target_paths], cwd=ROOT
    ).returncode == 0
    if not clean:
        print("REFUSED: target production files already have local modifications")
        return 2

    if RUN_ROOT.exists():
        shutil.rmtree(RUN_ROOT)
    RUN_ROOT.mkdir(parents=True)
    TEMP_TEST.write_text(TEMP_TEST_CONTENT, encoding="utf-8", newline="\n")
    nodes = (
        "tests/test_capability_adapter.py",
        "tests/test_recovery_contract.py",
        "tests/a1_acceptance_temp.py",
    )
    results: list[dict[str, object]] = []
    try:
        baseline_code, baseline_output = run_pytest(*nodes, label="baseline")
        if baseline_code != 0:
            print("BASELINE_FAIL")
            print(baseline_output)
            return 1
        for number, item in enumerate(mutations(), start=1):
            path = ROOT / item.relative_path
            original = path.read_bytes()
            broken_code = 0
            restore_code = 1
            error = None
            try:
                apply_mutation(item)
                broken_code, broken_output = run_pytest(item.nodeid, label=f"m{number:02d}-broken")
            except Exception as exc:  # pragma: no cover - acceptance harness reporting
                broken_output = f"{type(exc).__name__}: {exc}"
                error = broken_output
            finally:
                path.write_bytes(original)
            if error is None:
                restore_code, restore_output = run_pytest(item.nodeid, label=f"m{number:02d}-restored")
            else:
                restore_output = ""
            mutation_failed = broken_code != 0 and error is None
            restored = restore_code == 0 and error is None
            results.append(
                {
                    "name": item.name,
                    "mutation_failed": mutation_failed,
                    "restored": restored,
                    "broken_output": broken_output[-1000:],
                    "restore_output": restore_output[-500:],
                    "error": error,
                }
            )
            print(
                f"{number:02d} {item.name}: mutation_failed={mutation_failed} restored={restored}",
                flush=True,
            )
        final_code, final_output = run_pytest(*nodes, label="final")
        env = os.environ.copy()
        env["TEMP"] = str(RUN_ROOT / "parity-temp")
        env["TMP"] = env["TEMP"]
        parity = subprocess.run(
            [sys.executable, "docs/rearchitecture/worktrees/A-runtime-recovery/parity_report.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=env,
        )
        summary = {
            "baseline_passed": True,
            "mutation_count": len(results),
            "mutation_failures_as_expected": sum(item["mutation_failed"] for item in results),
            "restores_passed": sum(item["restored"] for item in results),
            "final_passed": final_code == 0,
            "parity_passed": parity.returncode == 0 and "overall_equal=True" in parity.stdout,
        }
        print("SUMMARY " + json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
        if final_code != 0:
            print(final_output)
        if parity.returncode != 0:
            print(parity.stdout + parity.stderr)
        return 0 if all(summary.values()) and summary["mutation_count"] == 17 else 1
    finally:
        if TEMP_TEST.exists():
            TEMP_TEST.unlink()
        if RUN_ROOT.exists():
            shutil.rmtree(RUN_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
