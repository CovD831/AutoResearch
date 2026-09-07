from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from autoresearch.capability import (
    InvocationConflictError,
    PaperSearchCapabilityAdapter,
    PendingInvocationError,
)
from autoresearch.contracts import PaperRecord
from autoresearch.evidence import EvidenceService
from autoresearch.invocation_contracts import (
    PaperSearchRequest,
    request_fingerprint,
)
from autoresearch.knowledge import KnowledgeService
from autoresearch.search_service import PaperSearchService, SearchOutcome
from autoresearch.storage import RecordStore


def show(title: str, value) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(f"\n=== {title} ===")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def compact_row(row: dict | None) -> dict | None:
    if row is None:
        return None
    result = row.get("result") or {}
    staged = row.get("staged_result") or {}
    return {
        "state": row.get("state"),
        "phase": row.get("phase"),
        "request_fingerprint": row.get("request_fingerprint"),
        "has_staged_result": bool(row.get("staged_result")),
        "staged_status": (staged.get("receipt") or {}).get("outcome_status"),
        "has_final_result": bool(row.get("result")),
        "final_status": (result.get("receipt") or {}).get("outcome_status"),
    }


def show_invocation(title: str, invocation) -> None:
    show(
        title,
        {
            "receipt": invocation.receipt.model_dump(mode="json"),
            "paper_titles": [paper.title for paper in invocation.papers],
            "paper_ids": [paper.paper_id for paper in invocation.papers],
            "diagnostics": invocation.diagnostics,
            "evidence_candidates": [
                candidate.model_dump(mode="json")
                for candidate in invocation.evidence_candidates
            ],
        },
    )


def request(invocation_id: str) -> PaperSearchRequest:
    return PaperSearchRequest(
        project_id="demo",
        run_id="visible-run",
        invocation_id=invocation_id,
        query="evidence-aware agent workflows",
        limit=5,
    )


def paper(project_id: str = "demo") -> PaperRecord:
    return PaperRecord(
        project_id=project_id,
        title="Evidence-aware agent workflows",
        abstract="A fixture paper describing auditable research workflows.",
        authors=["A. Researcher"],
        year=2025,
        doi="10.1000/fixture-a",
        url="https://example.invalid/fixture-a",
        source="fixture",
        source_record_id="fixture-a",
    )


class VisibleSearchService:
    def __init__(self, *, papers=None, diagnostics=None, error=None, on_call=None):
        self.papers = list(papers or [])
        self.diagnostics = list(diagnostics or [])
        self.error = error
        self.on_call = on_call
        self.calls = 0

    def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
        self.calls += 1
        if self.on_call:
            self.on_call()
        if self.error:
            raise self.error
        return SearchOutcome(papers=list(self.papers), diagnostics=list(self.diagnostics))


def scenario_exact_replay(root: Path) -> None:
    store = RecordStore(root / "replay.sqlite3")
    req = request("replay")
    key = f"{req.run_id}:{req.invocation_id}"
    observed = []

    def observe_before_connector():
        observed.append(compact_row(store.get_idempotent("paper_search", key)))

    service = VisibleSearchService(papers=[paper()], on_call=observe_before_connector)
    adapter = PaperSearchCapabilityAdapter(service, store)

    show("request and fingerprint", {"request": req, "fingerprint": request_fingerprint(req)})
    show_invocation("first invoke: actual service call", adapter.invoke(req))
    show("row seen from inside service.search", observed)
    show("service call count after first invoke", service.calls)
    show("durable idempotency row after first invoke", compact_row(store.get_idempotent(adapter.scope, key)))
    show("all idempotency rows", store.list_idempotent(adapter.scope))

    before = service.calls
    replay = adapter.invoke(req)
    show_invocation("second invoke: replay only", replay)
    show("connector call count before/after replay", {"before": before, "after": service.calls})

    conflict = req.model_copy(update={"query": "different query"})
    try:
        adapter.invoke(conflict)
    except InvocationConflictError as exc:
        show("conflicting fingerprint rejected", {"exception": type(exc).__name__, "message": str(exc)})

    show("audit events", store.events(req.project_id))


def scenario_empty_unknown_timeout(root: Path) -> None:
    empty_req = request("empty")
    empty_store = RecordStore(root / "empty.sqlite3")
    empty = PaperSearchCapabilityAdapter(VisibleSearchService(), empty_store).invoke(empty_req)
    show_invocation("empty provider result", empty)

    unknown_req = request("unknown")
    unknown_store = RecordStore(root / "unknown.sqlite3")
    unknown = PaperSearchCapabilityAdapter(
        VisibleSearchService(diagnostics=["provider unavailable"]), unknown_store
    ).invoke(unknown_req)
    show_invocation("empty result with uncertain diagnostic", unknown)

    timeout_req = request("timeout")
    timeout_store = RecordStore(root / "timeout.sqlite3")
    timeout_service = VisibleSearchService(error=TimeoutError("simulated timeout"))
    timeout_adapter = PaperSearchCapabilityAdapter(timeout_service, timeout_store)
    timeout = timeout_adapter.invoke(timeout_req)
    replay = timeout_adapter.invoke(timeout_req)
    show_invocation("timeout first result", timeout)
    show_invocation("timeout replay", replay)
    show("timeout service call count", timeout_service.calls)


def scenario_pending_and_recovery(root: Path) -> None:
    store = RecordStore(root / "pending.sqlite3")
    req = request("pending")
    key = f"{req.run_id}:{req.invocation_id}"
    service = VisibleSearchService(papers=[paper()])
    adapter = PaperSearchCapabilityAdapter(service, store)
    store.reserve_idempotent(
        adapter.scope,
        key,
        {**req.model_dump(mode="json"), "request_fingerprint": request_fingerprint(req)},
    )
    show("manually reserved pending row", compact_row(store.get_idempotent(adapter.scope, key)))

    try:
        adapter.invoke(req)
    except PendingInvocationError as exc:
        show(
            "duplicate pending invoke is blocked",
            {"exception": type(exc).__name__, "message": str(exc), "service_calls": service.calls},
        )

    failed = adapter.fail_pending(
        req.run_id,
        req.invocation_id,
        reason="manual recovery after process restart",
    )
    show_invocation("explicit fail_pending recovery", failed)
    show("row after explicit recovery", compact_row(store.get_idempotent(adapter.scope, key)))
    replay = adapter.invoke(req)
    show_invocation("replay after explicit recovery", replay)
    show("service calls stayed at zero", service.calls)


def scenario_staged_recovery(root: Path) -> None:
    store = RecordStore(root / "staged.sqlite3")
    req = request("staged")
    key = f"{req.run_id}:{req.invocation_id}"
    service = VisibleSearchService(papers=[paper()])
    adapter = PaperSearchCapabilityAdapter(service, store)
    original_finalize = store.finalize_idempotent

    def crash_before_finalize(scope, idempotency_key, result):
        raise RuntimeError("simulated crash before finalization")

    store.finalize_idempotent = crash_before_finalize
    try:
        adapter.invoke(req)
    except RuntimeError as exc:
        show("simulated crash after service result was staged", {"exception": type(exc).__name__, "message": str(exc)})
    finally:
        store.finalize_idempotent = original_finalize

    show("pending row after simulated crash", compact_row(store.get_idempotent(adapter.scope, key)))
    recovered = adapter.recover_pending(
        req.run_id,
        req.invocation_id,
        reason="restart found staged result",
    )
    show_invocation("recover_pending uses staged result", recovered)
    show("service calls after staged recovery", service.calls)
    show("row after staged recovery", compact_row(store.get_idempotent(adapter.scope, key)))


class FixtureConnector:
    name = "visible-fixture"

    def __init__(self, record: dict):
        self.record = record
        self.calls = 0

    def search(self, query: str, limit: int) -> list[dict]:
        self.calls += 1
        return [self.record]


def scenario_legacy_target_parity(root: Path) -> None:
    raw = {
        "title": "Evidence-aware agent workflows",
        "abstract": "A fixture paper describing auditable research workflows.",
        "authors": ["A. Researcher"],
        "year": 2025,
        "doi": "10.1000/fixture-a",
        "url": "https://example.invalid/fixture-a",
        "source_record_id": "fixture-a",
    }
    legacy_store = RecordStore(root / "legacy.sqlite3")
    target_store = RecordStore(root / "target.sqlite3")
    legacy_connector = FixtureConnector(raw)
    target_connector = FixtureConnector(raw)
    legacy_service = PaperSearchService(
        legacy_store,
        EvidenceService(legacy_store),
        KnowledgeService(legacy_store),
        network_enabled=True,
        connectors=[legacy_connector],
    )
    target_service = PaperSearchService(
        target_store,
        EvidenceService(target_store),
        KnowledgeService(target_store),
        network_enabled=True,
        connectors=[target_connector],
    )
    req = request("parity")
    legacy = legacy_service.search(req.project_id, [req.query], per_connector_limit=req.limit)
    target = PaperSearchCapabilityAdapter(target_service, target_store).invoke(req)

    report = {
        "legacy_connector_calls": legacy_connector.calls,
        "target_connector_calls": target_connector.calls,
        "legacy": {
            "papers": legacy_store.list("paper"),
            "evidence": legacy_store.list("evidence"),
            "wiki_page": legacy_store.list("wiki_page"),
        },
        "target": {
            "papers": target_store.list("paper"),
            "evidence": target_store.list("evidence"),
            "wiki_page": target_store.list("wiki_page"),
            "idempotency": target_store.list_idempotent("paper_search"),
        },
    }
    show("legacy and target durable facts", report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Visible, user-run A1 acceptance walkthrough")
    parser.add_argument("--db-dir", help="Directory for inspectable SQLite files")
    args = parser.parse_args()
    root = Path(args.db_dir) if args.db_dir else Path(tempfile.mkdtemp(prefix="a1-visible-"))
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"Refusing to reuse non-empty artifact directory: {root}")
    root.mkdir(parents=True, exist_ok=True)
    print(f"A1 visible acceptance artifacts: {root.resolve()}")
    print("This walkthrough prints implementation state; it does not mutate source code.")
    scenario_exact_replay(root)
    scenario_empty_unknown_timeout(root)
    scenario_pending_and_recovery(root)
    scenario_staged_recovery(root)
    scenario_legacy_target_parity(root)
    print("\nDONE: inspect the printed receipts, SQLite rows, service call counts, and audit events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
