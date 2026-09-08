from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY_ROOT / "tests"))

from a2_runtime_fixtures import (  # noqa: E402
    run_conflict,
    run_duplicate,
    run_evidence_before_receipt,
    run_partial_write,
    run_process_restart,
    run_timeout,
)

ScenarioRunner = Callable[[Path], dict[str, Any]]


def _business_counts(entry: dict[str, Any], key: str = "durable_facts") -> dict[str, int]:
    facts = entry.get(key) or {}
    return {name: facts.get(name, 0) for name in ("papers", "evidence", "wiki")}


def _scenario_passed(scenario_id: str, entry: dict[str, Any]) -> bool:
    if scenario_id == "timeout":
        return (
            entry["receipt"]["outcome_status"] == "unknown_outcome"
            and entry["replay_status"] == "replayed"
            and entry["durable_record"]["final_status"] == "unknown_outcome"
            and entry["connector_calls"] == 1
        )
    if scenario_id == "process_restart":
        return (
            entry["before"]["phase"] == "service_started"
            and entry["receipt"]["outcome_status"] == "unknown_outcome"
            and entry["durable_record"]["state"] == "finalized"
            and entry["connector_calls"] == 1
        )
    if scenario_id == "evidence_before_receipt":
        return (
            entry["crash"]["returncode"] == 43
            and entry["crash"]["facts_marker"] is True
            and entry["before"]["phase"] == "service_started"
            and entry["receipt"]["outcome_status"] == "unknown_outcome"
            and _business_counts(entry, "durable_facts_before")
            == _business_counts(entry, "durable_facts_after")
        )
    if scenario_id == "partial_write":
        return (
            entry["crash"]["returncode"] == 41
            and entry["before"]["phase"] == "service_returned"
            and entry["before"]["has_staged_result"] is True
            and entry["receipt"]["outcome_status"] == "completed"
            and entry["after"]["state"] == "finalized"
            and _business_counts(entry, "durable_facts_before")
            == _business_counts(entry, "durable_facts_after")
            and entry["connector_calls"] == 1
        )
    if scenario_id == "duplicate_submission":
        return (
            entry["replay_status"] == "replayed"
            and entry["connector_calls"] == 1
            and _business_counts(entry) == {"papers": 1, "evidence": 1, "wiki": 1}
        )
    if scenario_id == "conflicting_fingerprint":
        return (
            entry["rejection"]["exception"] == "InvocationConflictError"
            and entry["connector_calls"] == 1
        )
    return False


def build_report(root: Path) -> dict[str, Any]:
    scenarios: list[tuple[str, ScenarioRunner]] = [
        ("timeout", run_timeout),
        ("process_restart", run_process_restart),
        ("evidence_before_receipt", run_evidence_before_receipt),
        ("partial_write", run_partial_write),
        ("duplicate_submission", run_duplicate),
        ("conflicting_fingerprint", run_conflict),
    ]
    entries = []
    for scenario_id, runner in scenarios:
        entry = runner(root / scenario_id)
        if "durable_facts" not in entry:
            entry["durable_facts"] = entry.get("durable_facts_after", {})
        entry["side_effect_count"] = entry["connector_calls"]
        entry["passed"] = _scenario_passed(scenario_id, entry)
        entries.append(entry)
    return {
        "schema": "p1-a2-fault-matrix/v1",
        "scenarios": entries,
        "overall_passed": all(entry["passed"] for entry in entries),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline A2 runtime fault matrix.")
    parser.add_argument("output", type=Path, help="JSON report path")
    args = parser.parse_args()
    output = args.output.resolve()
    artifact_root = output.parent / f"{output.stem}-artifacts"
    if artifact_root.exists() and any(artifact_root.iterdir()):
        raise SystemExit(f"Refusing to reuse non-empty artifact directory: {artifact_root}")
    output.parent.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)
    report = build_report(artifact_root)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
