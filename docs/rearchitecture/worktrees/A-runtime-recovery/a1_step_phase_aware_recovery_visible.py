from __future__ import annotations

import json
import sys
from pathlib import Path

from autoresearch.capability import PaperSearchCapabilityAdapter
from autoresearch.contracts import PaperRecord
from autoresearch.invocation_contracts import (
    InvocationStatus,
    PaperSearchRequest,
    request_fingerprint,
)
from autoresearch.search_service import SearchOutcome
from autoresearch.storage import RecordStore


def compact(row: dict | None) -> dict | None:
    if row is None:
        return None
    staged = row.get("staged_result") or {}
    result = row.get("result") or {}
    return {
        "state": row.get("state"),
        "phase": row.get("phase"),
        "has_staged_result": bool(row.get("staged_result")),
        "staged_status": (staged.get("receipt") or {}).get("outcome_status"),
        "has_final_result": bool(row.get("result")),
        "final_status": (result.get("receipt") or {}).get("outcome_status"),
    }


def request(invocation_id: str) -> PaperSearchRequest:
    return PaperSearchRequest(
        project_id="demo",
        run_id="visible-run",
        invocation_id=invocation_id,
        query="evidence-aware agent workflows",
        limit=5,
    )


class VisibleService:
    def __init__(self, papers=None):
        self.papers = list(papers or [])
        self.calls = 0

    def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
        self.calls += 1
        return SearchOutcome(papers=list(self.papers), diagnostics=[])


def paper() -> PaperRecord:
    return PaperRecord(
        project_id="demo",
        title="Evidence-aware agent workflows",
        abstract="A fixture paper describing auditable research workflows.",
        authors=["A. Researcher"],
        year=2025,
        doi="10.1000/fixture-a",
        url="https://example.invalid/fixture-a",
        source="fixture",
        source_record_id="fixture-a",
    )


def started_case(root: Path) -> dict:
    store = RecordStore(root / "service-started.sqlite3")
    req = request("service-started")
    key = "visible-run:service-started"
    adapter = PaperSearchCapabilityAdapter(VisibleService(), store)
    store.reserve_idempotent(
        adapter.scope,
        key,
        {**req.model_dump(mode="json"), "request_fingerprint": request_fingerprint(req)},
    )
    store.mark_idempotent_phase(adapter.scope, key, "service_started")
    before = compact(store.get_idempotent(adapter.scope, key))
    recovered = adapter.recover_pending(
        req.run_id,
        req.invocation_id,
        reason="restart found service_started without durable provider result",
        outcome_status=InvocationStatus.UNKNOWN_OUTCOME,
    )
    return {
        "before_recovery": before,
        "recovered_receipt": recovered.receipt.model_dump(mode="json"),
        "after_recovery": compact(store.get_idempotent(adapter.scope, key)),
        "audit_events": store.events(req.project_id),
    }


def returned_case(root: Path) -> dict:
    store = RecordStore(root / "service-returned.sqlite3")
    req = request("service-returned")
    key = "visible-run:service-returned"
    service = VisibleService(papers=[paper()])
    adapter = PaperSearchCapabilityAdapter(service, store)
    original_finalize = store.finalize_idempotent

    def crash_before_finalize(scope, idempotency_key, result):
        raise RuntimeError("simulated crash after service_returned")

    store.finalize_idempotent = crash_before_finalize
    try:
        adapter.invoke(req)
    except RuntimeError as exc:
        crash = {"exception": type(exc).__name__, "message": str(exc)}
    finally:
        store.finalize_idempotent = original_finalize

    before = compact(store.get_idempotent(adapter.scope, key))
    recovered = adapter.recover_pending(
        req.run_id,
        req.invocation_id,
        reason="restart found staged service result",
        outcome_status=InvocationStatus.FAILED,
    )
    return {
        "crash": crash,
        "before_recovery": before,
        "recovered_receipt": recovered.receipt.model_dump(mode="json"),
        "after_recovery": compact(store.get_idempotent(adapter.scope, key)),
        "service_calls": service.calls,
        "audit_events": store.events(req.project_id),
    }


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python a1_step_phase_aware_recovery_visible.py <db-dir>")
    root = Path(sys.argv[1]).resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"Refusing to reuse non-empty artifact directory: {root}")
    root.mkdir(parents=True, exist_ok=True)
    print(json.dumps({
        "db_dir": str(root),
        "service_started_case": started_case(root),
        "service_returned_case": returned_case(root),
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
