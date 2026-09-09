from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

from autoresearch.capability import PaperSearchCapabilityAdapter
from autoresearch.contracts import PaperRecord
from autoresearch.evidence import EvidenceService
from autoresearch.invocation_contracts import PaperSearchRequest, request_fingerprint
from autoresearch.knowledge import KnowledgeService
from autoresearch.search_service import PaperSearchService, SearchOutcome
from autoresearch.storage import RecordStore

SCENARIO_ID = "a2-crash-after-service-started"
SCOPE = "paper_search"
EXIT_CODE = 37


def scenario_request() -> PaperSearchRequest:
    return PaperSearchRequest(
        project_id="a2-fixture-project",
        run_id="a2-fixture-run",
        invocation_id=SCENARIO_ID,
        query="evidence-aware agent workflows",
        limit=5,
    )


def _child_script() -> str:
    return textwrap.dedent(
        """
        import os
        import sys
        from pathlib import Path

        from autoresearch.capability import PaperSearchCapabilityAdapter
        from autoresearch.invocation_contracts import PaperSearchRequest
        from autoresearch.storage import RecordStore


        class CrashAfterServiceStarted:
            def __init__(self, marker_path: Path):
                self.marker_path = marker_path

            def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
                self.marker_path.write_text("connector-called\\n", encoding="utf-8")
                os._exit(int(sys.argv[3]))


        db_path = Path(sys.argv[1])
        marker_path = Path(sys.argv[2])
        request = PaperSearchRequest(
            project_id="a2-fixture-project",
            run_id="a2-fixture-run",
            invocation_id="a2-crash-after-service-started",
            query="evidence-aware agent workflows",
            limit=5,
        )
        adapter = PaperSearchCapabilityAdapter(
            CrashAfterServiceStarted(marker_path),
            RecordStore(db_path),
        )
        adapter.invoke(request)
        """
    ).strip()


def _partial_write_child_script() -> str:
    return textwrap.dedent(
        """
        import os
        import sys
        from pathlib import Path

        from autoresearch.capability import PaperSearchCapabilityAdapter
        from autoresearch.contracts import PaperRecord
        from autoresearch.evidence import EvidenceService
        from autoresearch.invocation_contracts import PaperSearchRequest
        from autoresearch.knowledge import KnowledgeService
        from autoresearch.search_service import PaperSearchService
        from autoresearch.storage import RecordStore


        class FixtureConnector:
            name = "fixture"

            def search(self, query, limit):
                return [{
                    "paper_id": "paper-fixture-a",
                    "title": "Evidence-aware agent workflows",
                    "abstract": "A fixture paper describing auditable research workflows.",
                    "authors": ["A. Researcher"],
                    "year": 2025,
                    "doi": "10.1000/fixture-a",
                    "url": "https://example.invalid/fixture-a",
                    "source_record_id": "fixture-a",
                }]


        db_path = Path(sys.argv[1])
        store = RecordStore(db_path)
        service = PaperSearchService(
            store,
            EvidenceService(store),
            KnowledgeService(store),
            network_enabled=True,
            connectors=[FixtureConnector()],
        )
        original_finalize = store.finalize_idempotent

        def crash_before_finalize(scope, key, result):
            os._exit(int(sys.argv[2]))

        store.finalize_idempotent = crash_before_finalize
        request = PaperSearchRequest(
            project_id="a2-fixture-project",
            run_id="a2-fixture-run",
            invocation_id="partial-write",
            query="evidence-aware agent workflows",
            limit=5,
        )
        PaperSearchCapabilityAdapter(service, store).invoke(request)
        """
    ).strip()


def _evidence_before_receipt_child_script() -> str:
    return textwrap.dedent(
        """
        import os
        import sys
        from pathlib import Path

        from autoresearch.capability import PaperSearchCapabilityAdapter
        from autoresearch.evidence import EvidenceService
        from autoresearch.invocation_contracts import PaperSearchRequest
        from autoresearch.knowledge import KnowledgeService
        from autoresearch.search_service import PaperSearchService
        from autoresearch.storage import RecordStore


        class FixtureConnector:
            name = "fixture"

            def search(self, query, limit):
                return [{
                    "paper_id": "paper-fixture-a",
                    "title": "Evidence-aware agent workflows",
                    "abstract": "A fixture paper describing auditable research workflows.",
                    "authors": ["A. Researcher"],
                    "year": 2025,
                    "doi": "10.1000/fixture-a",
                    "url": "https://example.invalid/fixture-a",
                    "source_record_id": "fixture-a",
                }]


        class CrashAfterFactsService(PaperSearchService):
            def __init__(self, marker_path, *args, **kwargs):
                self.marker_path = marker_path
                super().__init__(*args, **kwargs)

            def _persist(self, paper):
                result = super()._persist(paper)
                self.marker_path.write_text("durable-facts-written\\n", encoding="utf-8")
                os._exit(int(sys.argv[3]))
                return result


        db_path = Path(sys.argv[1])
        marker_path = Path(sys.argv[2])
        store = RecordStore(db_path)
        service = CrashAfterFactsService(
            marker_path,
            store,
            EvidenceService(store),
            KnowledgeService(store),
            network_enabled=True,
            connectors=[FixtureConnector()],
        )
        request = PaperSearchRequest(
            project_id="a2-fixture-project",
            run_id="a2-fixture-run",
            invocation_id="evidence-before-receipt",
            query="evidence-aware agent workflows",
            limit=5,
        )
        PaperSearchCapabilityAdapter(service, store).invoke(request)
        """
    ).strip()


def run_crash_after_service_started(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "runtime.sqlite3"
    marker_path = root / "connector-calls.log"
    env = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (source_root, env.get("PYTHONPATH")) if value
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _child_script(),
            str(db_path),
            str(marker_path),
            str(EXIT_CODE),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    store = RecordStore(db_path)
    request = scenario_request()
    key = f"{request.run_id}:{request.invocation_id}"
    record = store.get_idempotent(SCOPE, key)
    marker_lines = (
        marker_path.read_text(encoding="utf-8").splitlines()
        if marker_path.exists()
        else []
    )
    return {
        "scenario_id": SCENARIO_ID,
        "request_fingerprint": request_fingerprint(request),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "record": record,
        "connector_calls": marker_lines.count("connector-called"),
    }


def _run_child(root: Path, script: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (source_root, env.get("PYTHONPATH")) if value
    )
    return subprocess.run(
        [sys.executable, "-c", script, *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def durable_projection(result: dict[str, Any]) -> dict[str, Any]:
    record = result["record"]
    return {
        "scenario_id": result["scenario_id"],
        "request_fingerprint": result["request_fingerprint"],
        "returncode": result["returncode"],
        "state": record["state"] if record else None,
        "phase": record["phase"] if record else None,
        "has_staged_result": bool(record and record.get("staged_result")),
        "has_final_result": bool(record and record.get("result")),
        "connector_calls": result["connector_calls"],
    }


def diagnostic_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    record = result["record"]
    return {
        **durable_projection(result),
        "durable_record": record,
        "child_stdout": result["stdout"],
        "child_stderr": result["stderr"],
    }


def paper(project_id: str = "a2-fixture-project") -> PaperRecord:
    return PaperRecord(
        paper_id="paper-fixture-a",
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


class FixtureService:
    def __init__(
        self,
        *,
        papers: list[PaperRecord] | None = None,
        error: Exception | None = None,
    ):
        self.papers = list(papers or [])
        self.error = error
        self.calls = 0

    def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return SearchOutcome(papers=list(self.papers), diagnostics=[])


def request_for(invocation_id: str) -> PaperSearchRequest:
    return scenario_request().model_copy(update={"invocation_id": invocation_id})


def compact_record(record: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "state": record.get("state") if record else None,
        "phase": record.get("phase") if record else None,
        "has_staged_result": bool(record and record.get("staged_result")),
        "has_final_result": bool(record and record.get("result")),
        "final_status": (
            ((record or {}).get("result") or {}).get("receipt", {}).get("outcome_status")
        ),
    }


def durable_counts(store: RecordStore) -> dict[str, int]:
    return {
        "papers": len(store.list("paper")),
        "evidence": len(store.list("evidence")),
        "wiki": len(store.list("wiki_page")),
        "audit_events": len(store.events("a2-fixture-project")),
    }


def run_timeout(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    store = RecordStore(root / "timeout.sqlite3")
    service = FixtureService(error=TimeoutError("fixture timeout"))
    adapter = PaperSearchCapabilityAdapter(service, store)
    request = request_for("timeout")
    first = adapter.invoke(request)
    replay = adapter.invoke(request)
    record = store.get_idempotent(adapter.scope, f"{request.run_id}:{request.invocation_id}")
    return {
        "scenario_id": "timeout",
        "request_fingerprint": first.receipt.request_fingerprint,
        "receipt": first.receipt.model_dump(mode="json"),
        "replay_status": replay.receipt.status.value,
        "durable_facts": durable_counts(store),
        "durable_record": compact_record(record),
        "connector_calls": service.calls,
        "diagnostics": first.diagnostics,
    }


def run_process_restart(root: Path) -> dict[str, Any]:
    crashed = run_crash_after_service_started(root / "crash")
    store = RecordStore(root / "crash" / "runtime.sqlite3")
    service = FixtureService(papers=[paper()])
    adapter = PaperSearchCapabilityAdapter(service, store)
    request = scenario_request()
    recovered = adapter.recover_pending(
        request.run_id,
        request.invocation_id,
        reason="restart found service_started without durable provider result",
    )
    record = store.get_idempotent(adapter.scope, f"{request.run_id}:{request.invocation_id}")
    return {
        "scenario_id": "process_restart",
        "request_fingerprint": crashed["request_fingerprint"],
        "receipt": recovered.receipt.model_dump(mode="json"),
        "before": durable_projection(crashed),
        "durable_facts": durable_counts(store),
        "durable_record": compact_record(record),
        "connector_calls": crashed["connector_calls"] + service.calls,
        "diagnostics": recovered.diagnostics,
    }


def run_partial_write(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "partial-write.sqlite3"
    completed = _run_child(root, _partial_write_child_script(), [str(db_path), "41"])
    store = RecordStore(db_path)
    request = request_for("partial-write")
    before = store.get_idempotent("paper_search", f"{request.run_id}:{request.invocation_id}")
    before_counts = durable_counts(store)
    recovered = PaperSearchCapabilityAdapter(FixtureService(), store).recover_pending(
        request.run_id,
        request.invocation_id,
        reason="restart finalized staged service result",
    )
    after = store.get_idempotent("paper_search", f"{request.run_id}:{request.invocation_id}")
    return {
        "scenario_id": "partial_write",
        "request_fingerprint": recovered.receipt.request_fingerprint,
        "crash": {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        },
        "receipt": recovered.receipt.model_dump(mode="json"),
        "before": compact_record(before),
        "after": compact_record(after),
        "durable_facts_before": before_counts,
        "durable_facts_after": durable_counts(store),
        "connector_calls": 1,
        "diagnostics": recovered.diagnostics,
    }


def run_evidence_before_receipt(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "evidence-before-receipt.sqlite3"
    marker_path = root / "durable-facts.log"
    completed = _run_child(
        root,
        _evidence_before_receipt_child_script(),
        [str(db_path), str(marker_path), "43"],
    )
    store = RecordStore(db_path)
    request = request_for("evidence-before-receipt")
    key = f"{request.run_id}:{request.invocation_id}"
    before = store.get_idempotent("paper_search", key)
    before_counts = durable_counts(store)
    recovered = PaperSearchCapabilityAdapter(FixtureService(), store).recover_pending(
        request.run_id,
        request.invocation_id,
        reason="restart found durable evidence before receipt",
    )
    after = store.get_idempotent("paper_search", key)
    return {
        "scenario_id": "evidence_before_receipt",
        "request_fingerprint": recovered.receipt.request_fingerprint,
        "crash": {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "facts_marker": marker_path.exists(),
        },
        "receipt": recovered.receipt.model_dump(mode="json"),
        "before": compact_record(before),
        "after": compact_record(after),
        "durable_facts_before": before_counts,
        "durable_facts_after": durable_counts(store),
        "connector_calls": 1,
        "diagnostics": recovered.diagnostics,
    }


def run_duplicate(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    store = RecordStore(root / "duplicate.sqlite3")
    connector = FixtureConnector(paper())
    service = PaperSearchService(
        store,
        EvidenceService(store),
        KnowledgeService(store),
        network_enabled=True,
        connectors=[connector],
    )
    adapter = PaperSearchCapabilityAdapter(service, store)
    request = request_for("duplicate")
    first = adapter.invoke(request)
    replay = adapter.invoke(request)
    return {
        "scenario_id": "duplicate_submission",
        "request_fingerprint": first.receipt.request_fingerprint,
        "receipt": first.receipt.model_dump(mode="json"),
        "replay_status": replay.receipt.status.value,
        "durable_facts": durable_counts(store),
        "connector_calls": connector.calls,
    }


def run_conflict(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    store = RecordStore(root / "conflict.sqlite3")
    service = FixtureService(papers=[paper()])
    adapter = PaperSearchCapabilityAdapter(service, store)
    request = request_for("conflict")
    first = adapter.invoke(request)
    conflict = request.model_copy(update={"query": "different fixture query"})
    try:
        adapter.invoke(conflict)
    except Exception as exc:
        rejection = {"exception": type(exc).__name__, "message": str(exc)}
    else:
        rejection = {"unexpected": "conflicting request was accepted"}
    return {
        "scenario_id": "conflicting_fingerprint",
        "request_fingerprint": first.receipt.request_fingerprint,
        "receipt": first.receipt.model_dump(mode="json"),
        "rejection": rejection,
        "durable_facts": durable_counts(store),
        "connector_calls": service.calls,
    }


class FixtureConnector:
    name = "fixture"

    def __init__(self, fixture_paper: PaperRecord):
        self.fixture_paper = fixture_paper
        self.calls = 0

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        self.calls += 1
        return [
            self.fixture_paper.model_dump(
                exclude={"project_id", "source"}
            )
        ]


def stale_writer_process(db_path: str, ready: Any, finalized: Any, result_queue: Any) -> None:
    store = RecordStore(db_path)
    key = "a2-fixture-run:toctou"
    old_record = store.get_idempotent("paper_search", key)
    if old_record is None:
        result_queue.put({"error": "missing initial record"})
        return
    previous_json = store._json(old_record)
    stale_record = {**old_record, "phase": "service_started"}
    ready.set()
    finalized.wait(timeout=30)
    try:
        store._update_idempotent_if_current(
            "paper_search", key, previous_json, stale_record
        )
    except Exception as exc:
        result_queue.put({"exception": type(exc).__name__, "message": str(exc)})
    else:
        result_queue.put({"unexpected": "stale writer was accepted"})
