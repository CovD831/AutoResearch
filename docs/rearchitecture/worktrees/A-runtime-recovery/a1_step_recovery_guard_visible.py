from __future__ import annotations

import json
import sys
from pathlib import Path

from autoresearch.capability import PaperSearchCapabilityAdapter
from autoresearch.invocation_contracts import (
    InvocationStatus,
    PaperSearchRequest,
    request_fingerprint,
)
from autoresearch.storage import RecordStore


def compact(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "state": row.get("state"),
        "phase": row.get("phase"),
        "has_staged_result": bool(row.get("staged_result")),
        "has_final_result": bool(row.get("result")),
    }


class UnusedService:
    def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
        raise RuntimeError("service must not be called in recovery guard checks")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python a1_step_recovery_guard_visible.py <db-dir>")
    root = Path(sys.argv[1]).resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"Refusing to reuse non-empty artifact directory: {root}")
    root.mkdir(parents=True, exist_ok=True)

    store = RecordStore(root / "recovery-guard.sqlite3")
    adapter = PaperSearchCapabilityAdapter(UnusedService(), store)
    request = PaperSearchRequest(
        project_id="demo",
        run_id="visible-run",
        invocation_id="recovery-guard",
        query="evidence-aware agent workflows",
        limit=5,
    )
    key = "visible-run:recovery-guard"
    store.reserve_idempotent(
        adapter.scope,
        key,
        {**request.model_dump(mode="json"), "request_fingerprint": request_fingerprint(request)},
    )
    before = compact(store.get_idempotent(adapter.scope, key))
    try:
        adapter.recover_pending(
            request.run_id,
            request.invocation_id,
            reason="invalid success recovery attempt",
            outcome_status=InvocationStatus.COMPLETED,
        )
    except Exception as exc:
        completed_attempt = {"exception": type(exc).__name__, "message": str(exc)}
    else:
        completed_attempt = {"unexpected": "completed recovery was accepted"}
    after_completed_attempt = compact(store.get_idempotent(adapter.scope, key))

    unknown_store = RecordStore(root / "unknown-record.sqlite3")
    unknown_adapter = PaperSearchCapabilityAdapter(UnusedService(), unknown_store)
    try:
        unknown_adapter.fail_pending(
            "missing-run",
            "missing-invocation",
            reason="unknown record check",
        )
    except Exception as exc:
        unknown_attempt = {"exception": type(exc).__name__, "message": str(exc)}
    else:
        unknown_attempt = {"unexpected": "unknown record was accepted"}

    print(json.dumps({
        "completed_recovery_attempt": {
            "before": before,
            "result": completed_attempt,
            "after": after_completed_attempt,
        },
        "unknown_record_attempt": {
            "result": unknown_attempt,
            "remaining_rows": unknown_store.list_idempotent("paper_search"),
        },
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
