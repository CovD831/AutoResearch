from __future__ import annotations

import json
import sys
from pathlib import Path

from autoresearch.capability import PaperSearchCapabilityAdapter
from autoresearch.evidence import EvidenceService
from autoresearch.invocation_contracts import PaperSearchRequest
from autoresearch.knowledge import KnowledgeService
from autoresearch.search_service import PaperSearchService
from autoresearch.storage import RecordStore


class CountingConnector:
    name = "fixture"

    def __init__(self):
        self.calls = 0

    def search(self, query: str, limit: int) -> list[dict]:
        self.calls += 1
        return [{
            "title": "Evidence-aware agent workflows",
            "abstract": "A fixture paper describing auditable research workflows.",
            "authors": ["A. Researcher"],
            "year": 2025,
            "doi": "10.1000/fixture-a",
            "url": "https://example.invalid/fixture-a",
            "source_record_id": "fixture-a",
        }]


def durable_snapshot(store: RecordStore) -> dict:
    return {
        "paper": store.list("paper"),
        "evidence": store.list("evidence"),
        "wiki_page": store.list("wiki_page"),
    }


def counts(snapshot: dict) -> dict:
    return {kind: len(rows) for kind, rows in snapshot.items()}


def service(store: RecordStore, connector: CountingConnector) -> PaperSearchService:
    return PaperSearchService(
        store,
        EvidenceService(store),
        KnowledgeService(store),
        network_enabled=True,
        connectors=[connector],
    )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: python a1_step_recovery_no_duplicate_facts_visible.py <db-dir>"
        )
    root = Path(sys.argv[1]).resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"Refusing to reuse non-empty artifact directory: {root}")
    root.mkdir(parents=True, exist_ok=True)

    store = RecordStore(root / "recovery-no-duplicates.sqlite3")
    first_connector = CountingConnector()
    first_adapter = PaperSearchCapabilityAdapter(service(store, first_connector), store)
    request = PaperSearchRequest(
        project_id="demo",
        run_id="visible-run",
        invocation_id="recovery-no-duplicates",
        query="evidence-aware agent workflows",
        limit=5,
    )
    key = "visible-run:recovery-no-duplicates"
    original_finalize = store.finalize_idempotent

    def crash_before_finalize(scope, idempotency_key, result):
        raise RuntimeError("simulated crash after durable facts and staged result")

    store.finalize_idempotent = crash_before_finalize
    try:
        first_adapter.invoke(request)
    except RuntimeError as exc:
        crash = {"exception": type(exc).__name__, "message": str(exc)}
    finally:
        store.finalize_idempotent = original_finalize

    before = durable_snapshot(store)
    row_before = store.get_idempotent(first_adapter.scope, key)

    recovery_connector = CountingConnector()
    recovery_adapter = PaperSearchCapabilityAdapter(service(store, recovery_connector), store)
    recovered = recovery_adapter.recover_pending(
        request.run_id,
        request.invocation_id,
        reason="restart found staged result and existing durable facts",
    )

    after = durable_snapshot(store)
    row_after = store.get_idempotent(recovery_adapter.scope, key)
    print(json.dumps({
        "db_path": str(store.path.resolve()),
        "crash": crash,
        "before_recovery": {
            "idempotency_state": row_before.get("state") if row_before else None,
            "idempotency_phase": row_before.get("phase") if row_before else None,
            "has_staged_result": bool(row_before and row_before.get("staged_result")),
            "durable_counts": counts(before),
            "first_connector_calls": first_connector.calls,
        },
        "recovery": {
            "receipt_status": recovered.receipt.status,
            "outcome_status": recovered.receipt.outcome_status,
            "recovery_connector_calls": recovery_connector.calls,
        },
        "after_recovery": {
            "idempotency_state": row_after.get("state") if row_after else None,
            "idempotency_phase": row_after.get("phase") if row_after else None,
            "durable_counts": counts(after),
            "durable_facts_unchanged": before == after,
        },
        "durable_facts_after_recovery": after,
        "audit_events": store.events(request.project_id),
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
