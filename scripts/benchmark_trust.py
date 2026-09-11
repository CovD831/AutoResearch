#!/usr/bin/env python3
"""Re-run the A5 trust benchmark and write the comparison report.

    python scripts/benchmark_trust.py --report evidence/benchmark-report.json

The run is **offline by default**: the frozen corpus under
``tests/fixtures/benchmark/`` *is* the material store, so the numbers are
reproducible with no network and no credentials.  ``--live-retrieval`` swaps the
fixture for a real retrieval source invoked through the A4 registry (OpenAlex is
the only source that works without credentials today; Semantic Scholar waits on
an API key).

What the report has to carry (TASK-SPECS/R004-05): the baseline, the sample, and
the explicit limitations.  The receipt pins the corpus digest and the frozen
metric-definition digest, so a later run of a *different* corpus is visibly a
different measurement rather than a silent drift.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from autoresearch.benchmark import (
    DEFAULT_CONDITIONS,
    BenchmarkCondition,
    BenchmarkRunStatus,
    EvidenceLedgerAdmission,
    FixtureMaterialsProvider,
    RegistryMaterialsProvider,
    ResourceBudget,
    TrustBenchmarkRuntime,
    load_corpus,
    load_metric_definition,
)
from autoresearch.capability_registry import CapabilityRegistry
from autoresearch.evidence import EvidenceService
from autoresearch.gates import GateService
from autoresearch.search_adapters import register_search_adapters
from autoresearch.storage import RecordStore

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "benchmark"
DEFAULT_CORPUS = FIXTURE_DIR / "corpus.json"
DEFAULT_METRIC_DEFINITION = FIXTURE_DIR / "metric-definition.json"
DEFAULT_REPORT = REPO_ROOT / "evidence" / "benchmark-report.json"

# OpenAlex is the ADR-01 s5 degraded track and the only source reachable without
# credentials today, so it is the live default.  The primary slot is not changed.
DEFAULT_LIVE_SOURCE = "openalex"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help="where to write the JSON report (default: %(default)s)",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help="frozen corpus JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--metric-definition",
        type=Path,
        default=DEFAULT_METRIC_DEFINITION,
        help="frozen metric-definition JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--condition",
        action="append",
        choices=[item.value for item in DEFAULT_CONDITIONS],
        help="run only this condition (repeatable); default: all three",
    )
    parser.add_argument(
        "--live-retrieval",
        action="store_true",
        help="use a real retrieval source through the A4 registry instead of the fixture",
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_LIVE_SOURCE,
        help="capability name for --live-retrieval (default: %(default)s)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="hits per live retrieval call (default: %(default)s)",
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=240,
        help="hard per-run call budget (default: %(default)s)",
    )
    parser.add_argument(
        "--run-id",
        default="benchmark-run",
        help="run id recorded in the receipt (default: %(default)s)",
    )
    return parser.parse_args(argv)


def build_live_materials(source: str, limit: int):
    """Wire the retrieval step through the A4 registry (never a direct adapter).

    ``source`` is the adapter key (``openalex``); the registry keys capabilities
    by their *manifest* name (``openalex_search``), so the registered view is the
    authoritative name.  Looking it up here is what keeps the script from
    hard-coding a name that the manifest is free to change.
    """

    registry = CapabilityRegistry(allow_network=True)
    views = register_search_adapters(registry)
    if source not in views:
        raise SystemExit(
            f"unknown retrieval source: {source!r} (available: {sorted(views)})"
        )
    return RegistryMaterialsProvider(registry, views[source].manifest.name, limit=limit)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    corpus = load_corpus(args.corpus)
    metric_definition = load_metric_definition(args.metric_definition)

    conditions = (
        [BenchmarkCondition(item) for item in args.condition]
        if args.condition
        else list(DEFAULT_CONDITIONS)
    )

    # The evidence ledger is what lets the deterministic gate resolve the
    # material, so both modes share it.  It lives in a throwaway store: the
    # report is the artifact, not the ledger.
    with tempfile.TemporaryDirectory(prefix="benchmark-trust-") as scratch:
        store = RecordStore(Path(scratch) / "benchmark.sqlite3")
        evidence = EvidenceService(store)
        admission = EvidenceLedgerAdmission(evidence)
        gate = GateService(evidence, store)

        if args.live_retrieval:
            materials = build_live_materials(args.source, args.limit)
        else:
            materials = FixtureMaterialsProvider()

        runtime = TrustBenchmarkRuntime(
            corpus=corpus,
            metric_definition=metric_definition,
            budget=ResourceBudget(max_calls=args.max_calls),
            materials=materials,
            admission=admission,
            gate=gate,
            run_id=args.run_id,
        )
        run = runtime.run(conditions)

    report_path = args.report
    if not report_path.is_absolute():
        report_path = (REPO_ROOT / report_path).resolve()
    run.write_report(report_path)

    _print_summary(run, report_path, live=args.live_retrieval, source=args.source)

    status = run.receipt.status
    if status is BenchmarkRunStatus.COMPLETED:
        return 0
    # Anything else means the comparison is not clean; do not exit as if it were.
    print(f"\nbenchmark did not complete cleanly: {status.value}", file=sys.stderr)
    return 1


def _print_summary(run, report_path: Path, *, live: bool, source: str) -> None:
    report = run.report
    receipt = run.receipt

    print("A5 trust benchmark")
    print(f"  source          : {'live ' + source if live else 'frozen corpus fixture'}")
    print(f"  corpus          : {report.corpus_id} v{report.corpus_version}")
    print(f"  corpus digest   : {report.corpus_digest}")
    print(f"  metric def      : v{report.metric_definition_version} ({report.primary_metric})")
    print(f"  metric digest   : {report.metric_definition_digest}")
    print(f"  status          : {report.status.value}")
    print(
        "  budget          : "
        f"{receipt.usage.calls_used}/{receipt.budget.max_calls} calls, "
        f"{receipt.usage.wall_clock_seconds:.3f}s wall, "
        f"stop={receipt.usage.stop_reason.value}"
    )
    print()
    print(
        f"  {'condition':<10} {'cases':>5} {'acc':>4} {'blk':>4} {'deny':>4} "
        f"{'hall':>9} {'acc_hall':>9} {'bind':>9} {'score':>7}"
    )
    for summary in report.conditions:
        score = "n/a" if summary.score is None else f"{summary.score:.2f}"
        print(
            f"  {summary.condition.value:<10} {summary.cases:>5} "
            f"{summary.completed:>4} {summary.blocked:>4} {summary.denied:>4} "
            f"{summary.hallucination_ratio:>9.6f} "
            f"{summary.accepted_hallucination_ratio:>9.6f} "
            f"{summary.evidence_binding_rate:>9.6f} {score:>7}"
        )
    print()
    print("  mechanism metrics (label agreement)")
    for key, value in sorted(report.mechanism_metrics.items()):
        print(f"    {key:<28} {value:.4f}")
    if report.warnings:
        print()
        print("  warnings")
        for item in report.warnings:
            print(f"    - {item}")
    print()
    print(f"  report written  : {report_path}")


if __name__ == "__main__":
    raise SystemExit(main())
