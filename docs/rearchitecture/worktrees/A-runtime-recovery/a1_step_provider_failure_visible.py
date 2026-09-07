from __future__ import annotations

import json
import sys
from pathlib import Path

from autoresearch.capability import PaperSearchCapabilityAdapter
from autoresearch.invocation_contracts import PaperSearchRequest
from autoresearch.storage import RecordStore


class FailingService:
    def __init__(self):
        self.calls = 0

    def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
        self.calls += 1
        raise RuntimeError("simulated provider failure")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python a1_step_provider_failure_visible.py <db-dir>")

    db_dir = Path(sys.argv[1]).resolve()
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "provider-failure.sqlite3"
    request = PaperSearchRequest(
        project_id="demo",
        run_id="visible-run",
        invocation_id="provider-failure",
        query="evidence-aware agent workflows",
        limit=5,
    )
    service = FailingService()
    store = RecordStore(db_path)
    adapter = PaperSearchCapabilityAdapter(service, store)
    first = adapter.invoke(request)
    replay = adapter.invoke(request)
    row = store.get_idempotent(adapter.scope, "visible-run:provider-failure")

    print(json.dumps({
        "db_path": str(db_path),
        "first": {
            "status": first.receipt.status,
            "outcome_status": first.receipt.outcome_status,
            "diagnostics": first.diagnostics,
        },
        "replay": {
            "status": replay.receipt.status,
            "outcome_status": replay.receipt.outcome_status,
        },
        "service_calls": service.calls,
        "durable_row": {
            "state": row.get("state") if row else None,
            "phase": row.get("phase") if row else None,
            "final_status": ((row or {}).get("result") or {}).get("receipt", {}).get("outcome_status"),
        },
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
