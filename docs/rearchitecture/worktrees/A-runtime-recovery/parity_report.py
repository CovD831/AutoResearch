from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from autoresearch.capability import PaperSearchCapabilityAdapter
from autoresearch.evidence import EvidenceService
from autoresearch.invocation_contracts import InvocationStatus, PaperSearchRequest
from autoresearch.knowledge import KnowledgeService
from autoresearch.search_service import PaperSearchService
from autoresearch.storage import RecordStore

FIXTURE = Path(__file__).parents[4] / "tests" / "fixtures" / "paper_search" / "scenario.json"


class FixtureConnector:
    name = "fixture"

    def __init__(self, paper: dict[str, Any]):
        self.paper = paper

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        del query, limit
        return [self.paper]


def _request() -> PaperSearchRequest:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return PaperSearchRequest(
        project_id=raw["project_id"],
        run_id=raw["run_id"],
        invocation_id=raw["invocation_id"],
        query=raw["query"],
        limit=raw["limit"],
    )


def _paper_projection(papers: list[Any]) -> list[dict[str, Any]]:
    projected = [
        {
            "title": paper.title,
            "abstract": paper.abstract,
            "authors": list(paper.authors),
            "year": paper.year,
            "doi": paper.doi,
            "url": paper.url,
            "source": paper.source,
            "source_record_id": paper.source_record_id,
        }
        for paper in papers
    ]
    return sorted(projected, key=lambda item: json.dumps(item, sort_keys=True))


def _row_projection(store: RecordStore) -> dict[str, Any]:
    evidence = [
        {
            "evidence_type": row["evidence_type"],
            "grade": row["grade"],
            "title": row["title"],
            "claim": row["claim"],
            "locator": row["locator"],
            "independent_source": row["independent_source"],
            "source": row.get("metadata", {}).get("source"),
        }
        for row in store.list("evidence")
    ]
    wiki = [
        {
            "partition": row["partition"],
            "title": row["title"],
            "tags": list(row["tags"]),
            "has_evidence": bool(row["evidence_ids"]),
        }
        for row in store.list("wiki_page")
    ]
    evidence.sort(key=lambda item: json.dumps(item, sort_keys=True))
    wiki.sort(key=lambda item: json.dumps(item, sort_keys=True))
    return {
        "papers": sorted(
            [
                {
                    "title": row["title"],
                    "abstract": row["abstract"],
                    "authors": list(row["authors"]),
                    "year": row["year"],
                    "doi": row["doi"],
                    "url": row["url"],
                    "source": row["source"],
                    "source_record_id": row["source_record_id"],
                }
                for row in store.list("paper")
            ],
            key=lambda item: json.dumps(item, sort_keys=True),
        ),
        "evidence": evidence,
        "wiki": wiki,
    }


def _receipt_projection(invocation: Any) -> dict[str, Any]:
    receipt = invocation.receipt
    return {
        "status": receipt.status.value,
        "outcome_status": (receipt.outcome_status or receipt.status).value,
        "adapter": receipt.adapter,
        "adapter_version": receipt.adapter_version,
        "request_fingerprint": receipt.request_fingerprint,
        "paper_count": len(invocation.papers),
        "diagnostics": list(invocation.diagnostics),
    }


def build_report() -> dict[str, Any]:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))["papers"][0]
    request = _request()
    with tempfile.TemporaryDirectory(prefix="autoresearch-parity-") as temp_dir:
        root = Path(temp_dir)
        legacy_store = RecordStore(root / "legacy.sqlite3")
        target_store = RecordStore(root / "target.sqlite3")
        legacy_service = PaperSearchService(
            legacy_store,
            EvidenceService(legacy_store),
            KnowledgeService(legacy_store),
            network_enabled=True,
            connectors=[FixtureConnector(raw)],
        )
        target_service = PaperSearchService(
            target_store,
            EvidenceService(target_store),
            KnowledgeService(target_store),
            network_enabled=True,
            connectors=[FixtureConnector(raw)],
        )

        legacy = legacy_service.search(
            request.project_id,
            [request.query],
            per_connector_limit=request.limit,
        )
        target = PaperSearchCapabilityAdapter(target_service, target_store).invoke(request)
        target_row = target_store.list_idempotent("paper_search")[0]

        legacy_rows = _row_projection(legacy_store)
        target_rows = _row_projection(target_store)
        target_receipt = _receipt_projection(target)
        idempotency = target_row["record"]
        idempotency_projection = {
            "scope": target_row["scope"],
            "key": target_row["idempotency_key"],
            "state": idempotency["state"],
            "request_fingerprint": idempotency["request_fingerprint"],
            "result_status": idempotency["result"]["receipt"]["status"],
            "result_outcome_status": idempotency["result"]["receipt"]["outcome_status"],
            "result_paper_count": len(idempotency["result"]["papers"]),
        }
        report = {
            "schema": "p1-a-parity-report/v1",
            "paper_result_equal": _paper_projection(legacy.papers)
            == _paper_projection(target.papers),
            "evidence_equal": legacy_rows["evidence"] == target_rows["evidence"],
            "wiki_equal": legacy_rows["wiki"] == target_rows["wiki"],
            "diagnostics_equal": legacy.diagnostics == target.diagnostics,
            "receipt_valid": target_receipt["outcome_status"] == InvocationStatus.COMPLETED.value
            and target_receipt["paper_count"] == len(target.papers),
            "idempotency_valid": (
                idempotency_projection["state"] == "finalized"
                and idempotency_projection["request_fingerprint"]
                == target_receipt["request_fingerprint"]
            ),
            "legacy": {
                "diagnostics": legacy.diagnostics,
                "rows": legacy_rows,
            },
            "target": {
                "diagnostics": target.diagnostics,
                "rows": target_rows,
                "receipt": target_receipt,
                "idempotency": idempotency_projection,
            },
        }
        report["overall_equal"] = all(
            report[key]
            for key in (
                "paper_result_equal",
                "evidence_equal",
                "wiki_equal",
                "diagnostics_equal",
                "receipt_valid",
                "idempotency_valid",
            )
        )
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the P1-A legacy/target parity report")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("parity-report.json"),
        help="JSON output path (default: parity-report.json beside this script)",
    )
    args = parser.parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"overall_equal={report['overall_equal']} output={args.output}")


if __name__ == "__main__":
    main()
