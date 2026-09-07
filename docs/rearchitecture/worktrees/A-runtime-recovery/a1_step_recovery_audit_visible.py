from __future__ import annotations

import json
import sys
from pathlib import Path

from autoresearch.capability import PaperSearchCapabilityAdapter
from autoresearch.invocation_contracts import PaperSearchRequest, request_fingerprint
from autoresearch.storage import RecordStore


class MustNotBeCalledService:
    def __init__(self):
        self.calls = 0

    def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
        self.calls += 1
        raise RuntimeError("service must not run during explicit recovery")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python a1_step_recovery_audit_visible.py <db-dir>")

    db_dir = Path(sys.argv[1]).resolve()
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "recovery-audit.sqlite3"
    store = RecordStore(db_path)
    service = MustNotBeCalledService()
    adapter = PaperSearchCapabilityAdapter(service, store)
    request = PaperSearchRequest(
        project_id="demo",
        run_id="visible-run",
        invocation_id="recovery-audit",
        query="evidence-aware agent workflows",
        limit=5,
    )
    key = "visible-run:recovery-audit"
    store.reserve_idempotent(
        adapter.scope,
        key,
        {**request.model_dump(mode="json"), "request_fingerprint": request_fingerprint(request)},
    )
    recovered = adapter.fail_pending(
        request.run_id,
        request.invocation_id,
        reason="manual recovery after process restart",
    )
    row = store.get_idempotent(adapter.scope, key)

    print(json.dumps({
        "db_path": str(db_path),
        "recovered_receipt": recovered.receipt.model_dump(mode="json"),
        "service_calls": service.calls,
        "durable_row": {
            "state": row.get("state") if row else None,
            "phase": row.get("phase") if row else None,
            "final_status": ((row or {}).get("result") or {}).get("receipt", {}).get("outcome_status"),
        },
        "audit_events": store.events(request.project_id),
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
