from __future__ import annotations

import json
import sys
from pathlib import Path

from autoresearch.invocation_contracts import PaperSearchRequest, request_fingerprint
from autoresearch.storage import RecordStore


def compact(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "state": row.get("state"),
        "phase": row.get("phase"),
        "request_fingerprint": row.get("request_fingerprint"),
        "has_staged_result": bool(row.get("staged_result")),
        "has_final_result": bool(row.get("result")),
    }


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python a1_step_phase_guard_visible.py <db-dir>")

    db_dir = Path(sys.argv[1]).resolve()
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "phase-guard.sqlite3"
    store = RecordStore(db_path)
    request = PaperSearchRequest(
        project_id="demo",
        run_id="visible-run",
        invocation_id="phase-guard",
        query="evidence-aware agent workflows",
        limit=5,
    )
    scope = "paper_search"
    key = "visible-run:phase-guard"
    store.reserve_idempotent(
        scope,
        key,
        {**request.model_dump(mode="json"), "request_fingerprint": request_fingerprint(request)},
    )
    before = compact(store.get_idempotent(scope, key))

    try:
        store.mark_idempotent_phase(scope, key, "service_returned")
    except Exception as exc:
        illegal_transition = {
            "exception": type(exc).__name__,
            "message": str(exc),
        }
    else:
        illegal_transition = {"unexpected": "illegal transition was accepted"}

    after_rejected = compact(store.get_idempotent(scope, key))
    store.mark_idempotent_phase(scope, key, "service_started")
    after_valid = compact(store.get_idempotent(scope, key))

    print(json.dumps({
        "db_path": str(db_path),
        "before_illegal_transition": before,
        "illegal_transition_result": illegal_transition,
        "after_illegal_transition": after_rejected,
        "after_valid_reserved_to_service_started": after_valid,
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
