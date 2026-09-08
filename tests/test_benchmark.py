from __future__ import annotations

import pytest

from autoresearch.benchmark import (
    BenchmarkCase,
    BenchmarkHarness,
    MeasurementStatus,
    MetricObservation,
    MetricSpec,
    ratio_score,
    safety_score,
)


def metric(
    name: str,
    family: str,
    weight: float,
    score: float | None,
    status=MeasurementStatus.OBSERVED,
):
    return MetricObservation(MetricSpec(name, family, weight), score, status)


def test_report_separates_paper_and_mechanism_families():
    report = BenchmarkHarness(version="2026.09").evaluate(
        [
            BenchmarkCase(
                "case-1",
                "gate-on",
                (
                    metric("claim_evidence", "paper", 2, 80),
                    metric("reproducibility", "paper", 1, 60),
                    metric("gate_safety", "mechanism", 2, 100),
                ),
            )
        ]
    )
    assert report.overall_score == 84.0
    assert report.family_scores == {"paper": 73.33, "mechanism": 100.0}
    assert report.is_complete


def test_planned_metrics_are_not_presented_as_results():
    report = BenchmarkHarness().evaluate(
        [
            BenchmarkCase(
                "case-1",
                "baseline",
                (metric("citation", "paper", 1, None, MeasurementStatus.PLANNED),),
            )
        ]
    )
    assert report.overall_score is None
    assert report.planned_metric_count == 1
    assert not report.is_complete
    assert "provisional" in " ".join(report.warnings)


def test_duplicate_metrics_and_invalid_counts_fail_closed():
    spec = MetricSpec("x", "paper", 1)
    with pytest.raises(ValueError):
        BenchmarkCase("case", "method", (MetricObservation(spec, 50), MetricObservation(spec, 60)))
    assert ratio_score(3, 4) == 75.0
    assert safety_score(expected_blocks=4, actual_blocks=3, false_passes=0, total=4) == 75.0
    assert safety_score(expected_blocks=4, actual_blocks=4, false_passes=1, total=4) == 50.0
