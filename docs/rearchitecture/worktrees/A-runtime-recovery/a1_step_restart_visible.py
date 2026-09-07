from __future__ import annotations

import json
import sys
from pathlib import Path

from autoresearch.capability import PaperSearchCapabilityAdapter
from autoresearch.invocation_contracts import PaperSearchRequest
from autoresearch.storage import RecordStore


class MustNotBeCalledService:
    def __init__(self):
        self.calls = 0

    def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
        self.calls += 1
        raise RuntimeError("connector was called during restart replay")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python a1_step_restart_visible.py <replay.sqlite3>")

    db_path = Path(sys.argv[1]).resolve()
    request = PaperSearchRequest(
        project_id="demo",
        run_id="visible-run",
        invocation_id="replay",
        query="evidence-aware agent workflows",
        limit=5,
    )
    service = MustNotBeCalledService()
    store = RecordStore(db_path)
    adapter = PaperSearchCapabilityAdapter(service, store)
    result = adapter.invoke(request)
    row = store.get_idempotent(adapter.scope, "visible-run:replay")

    print(json.dumps({
        "db_path": str(db_path),
        "new_store_instance": True,
        "receipt_status": result.receipt.status,
        "outcome_status": result.receipt.outcome_status,
        "paper_titles": [paper.title for paper in result.papers],
        "service_calls": service.calls,
        "durable_row": {
            "state": row.get("state") if row else None,
            "phase": row.get("phase") if row else None,
            "has_final_result": bool(row and row.get("result")),
        },
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
