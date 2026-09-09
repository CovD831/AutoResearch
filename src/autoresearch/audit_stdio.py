from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from autoresearch.audit import AuditRuntime, BoundedEvidenceView
from autoresearch.audit_contracts import AuditCitation, AuditClaim, AuditInvocationRequest
from autoresearch.resolver import (
    ResolverRecord,
    ResolverSnapshot,
    ResolverSnapshotRepository,
    SnapshotResolverAdapter,
)
from autoresearch.storage import RecordStore


def build_report(arguments: dict[str, Any], store: RecordStore):
    """Build an ``AuditReport`` from a transport-agnostic envelope.

    ``arguments`` accepts either a bare ``AuditInvocationRequest`` payload or an
    envelope with ``request`` plus optional ``resolver_snapshot`` /
    ``resolver_records`` / ``resolver_available`` / ``evidence_view``. This is
    the transport-agnostic invocation boundary; no MCP or JSON-RPC envelope is
    involved.
    """
    request_payload = arguments.get("request", arguments)
    request = AuditInvocationRequest.model_validate(request_payload)
    snapshots = ResolverSnapshotRepository(store)
    snapshot_payload = arguments.get("resolver_snapshot")
    if snapshot_payload is not None:
        snapshot = ResolverSnapshot.model_validate(snapshot_payload).verify()
        if snapshot.snapshot_version != request.resolver_snapshot_version:
            raise ValueError("resolver snapshot version does not match audit request")
        snapshots.save(snapshot)
    elif "resolver_records" in arguments:
        records = [ResolverRecord.model_validate(item) for item in arguments["resolver_records"]]
        snapshots.save(
            ResolverSnapshot.from_records(
                records,
                snapshot_version=request.resolver_snapshot_version,
            )
        )
    snapshot_present = snapshots.load(request.resolver_snapshot_version) is not None
    resolver = SnapshotResolverAdapter.from_store(
        store,
        snapshot_version=request.resolver_snapshot_version,
        available=bool(arguments.get("resolver_available", snapshot_present))
        and snapshot_present,
    )
    view = BoundedEvidenceView.model_validate(arguments.get("evidence_view", {}))
    return AuditRuntime(store, resolver).invoke(request, evidence_view=view)


def selftest_payload() -> dict[str, Any]:
    """Run one offline audit scenario and return the report plus minimal metadata."""
    request = AuditInvocationRequest(
        invocation_id="audit-selftest",
        manuscript_hash="a" * 64,
        corpus_version="fixture-corpus-1",
        resolver_snapshot_version="fixture-snapshot-1",
        citations=[
            AuditCitation(
                citation_id="citation-1",
                title="Evidence-aware agent workflows",
                doi="10.1000/fixture-a",
            )
        ],
        claims=[
            AuditClaim(
                claim_id="claim-1",
                text="The cited record exists.",
                citation_ids=["citation-1"],
            )
        ],
    )
    with tempfile.TemporaryDirectory(prefix="autoresearch-audit-selftest-") as directory:
        store = RecordStore(Path(directory) / "audit.sqlite3")
        report = build_report(
            {
                "request": request.model_dump(mode="json"),
                "resolver_records": [
                    {
                        "resolver_key": "doi:10.1000/fixture-a",
                        "title": "Evidence-aware agent workflows",
                        "doi": "10.1000/fixture-a",
                    }
                ],
            },
            store,
        )
        return {
            "selftest": True,
            "report_schema": report.report_schema,
            "receipt_status": report.receipt.status.value,
            "verdict_count": len(report.verdicts),
            "report": report.model_dump(mode="json"),
        }


def run_stdio() -> int:
    """Plain JSON-lines stdio runtime: one JSON envelope per line, one report per line."""
    parser = argparse.ArgumentParser(description="Local Audit JSON-lines stdio runtime")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        print(json.dumps(selftest_payload(), ensure_ascii=False, indent=2))
        return 0
    with tempfile.TemporaryDirectory(prefix="autoresearch-audit-stdio-") as directory:
        store = RecordStore(Path(directory) / "audit.sqlite3")
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    result = {"error": "JSON-lines message must be an object"}
                else:
                    result = build_report(payload, store).model_dump(mode="json")
            except json.JSONDecodeError as exc:
                result = {"error": f"parse error: {exc.msg}"}
            except Exception as exc:
                result = {"error": f"{type(exc).__name__}: {exc}"}
            print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_stdio())
