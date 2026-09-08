"""A small, deterministic benchmark harness for AutoResearch.

The harness deliberately keeps *planned* benchmark definitions separate from
*observed* measurements.  It is suitable for regression runs and for producing
an evaluation table for a paper; it does not execute experiments.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MeasurementStatus(StrEnum):
    OBSERVED = "observed"
    PLANNED = "planned"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class MetricSpec:
    """A named metric in the benchmark rubric."""

    name: str
    family: str
    weight: float
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.family:
            raise ValueError("metric name and family are required")
        if self.weight <= 0:
            raise ValueError("metric weight must be positive")


@dataclass(frozen=True)
class MetricObservation:
    spec: MetricSpec
    score: float | None
    status: MeasurementStatus = MeasurementStatus.OBSERVED
    evidence: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.score is not None and not 0 <= self.score <= 100:
            raise ValueError("metric score must be between 0 and 100")
        if self.status == MeasurementStatus.OBSERVED and self.score is None:
            raise ValueError("observed metrics require a score")
        if self.status != MeasurementStatus.OBSERVED and self.score is not None:
            raise ValueError("planned/unavailable metrics cannot carry observed scores")


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    method: str
    observations: tuple[MetricObservation, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.case_id or not self.method:
            raise ValueError("case_id and method are required")
        names = [item.spec.name for item in self.observations]
        if len(names) != len(set(names)):
            raise ValueError("a case cannot contain duplicate metric names")


@dataclass(frozen=True)
class BenchmarkReport:
    benchmark_id: str
    version: str
    case_scores: dict[str, float]
    family_scores: dict[str, float]
    overall_score: float | None
    observed_metric_count: int
    planned_metric_count: int
    unavailable_metric_count: int
    warnings: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        return self.planned_metric_count == 0 and self.unavailable_metric_count == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "version": self.version,
            "case_scores": self.case_scores,
            "family_scores": self.family_scores,
            "overall_score": self.overall_score,
            "observed_metric_count": self.observed_metric_count,
            "planned_metric_count": self.planned_metric_count,
            "unavailable_metric_count": self.unavailable_metric_count,
            "complete": self.is_complete,
            "warnings": list(self.warnings),
        }


class BenchmarkHarness:
    """Score benchmark cases without executing or mutating project state."""

    def __init__(self, benchmark_id: str = "autoresearch-evaluation", version: str = "0.1"):
        self.benchmark_id = benchmark_id
        self.version = version

    @staticmethod
    def _weighted(observations: Iterable[MetricObservation]) -> tuple[float | None, int, int, int]:
        observed = [item for item in observations if item.status == MeasurementStatus.OBSERVED]
        planned = sum(item.status == MeasurementStatus.PLANNED for item in observations)
        unavailable = sum(item.status == MeasurementStatus.UNAVAILABLE for item in observations)
        weight = sum(item.spec.weight for item in observed)
        if not observed or weight == 0:
            return None, 0, planned, unavailable
        score = (
            sum(item.score * item.spec.weight for item in observed if item.score is not None)
            / weight
        )
        return round(score, 2), len(observed), planned, unavailable

    def evaluate(self, cases: Iterable[BenchmarkCase]) -> BenchmarkReport:
        cases = tuple(cases)
        if not cases:
            raise ValueError("at least one benchmark case is required")
        case_scores: dict[str, float] = {}
        family_values: dict[str, list[MetricObservation]] = {}
        warnings: list[str] = []
        observed_count = planned_count = unavailable_count = 0

        for case in cases:
            score, observed, planned, unavailable = self._weighted(case.observations)
            observed_count += observed
            planned_count += planned
            unavailable_count += unavailable
            if score is not None:
                case_scores[case.case_id] = score
            else:
                warnings.append(f"case {case.case_id} has no observed metrics")
            for observation in case.observations:
                family_values.setdefault(observation.spec.family, []).append(observation)

        family_scores: dict[str, float] = {}
        all_observed: list[MetricObservation] = []
        for family, observations in family_values.items():
            score, _, _, _ = self._weighted(observations)
            if score is not None:
                family_scores[family] = score
                all_observed.extend(
                    item for item in observations if item.status == MeasurementStatus.OBSERVED
                )

        overall, _, _, _ = self._weighted(all_observed)
        if planned_count:
            warnings.append("planned metrics are excluded from scores; report is provisional")
        if unavailable_count:
            warnings.append("unavailable metrics are excluded from scores")
        return BenchmarkReport(
            benchmark_id=self.benchmark_id,
            version=self.version,
            case_scores=case_scores,
            family_scores=family_scores,
            overall_score=overall,
            observed_metric_count=observed_count,
            planned_metric_count=planned_count,
            unavailable_metric_count=unavailable_count,
            warnings=tuple(warnings),
        )


def ratio_score(successes: int, total: int) -> float:
    """Convert a count-based mechanism metric to a 0–100 score."""
    if total < 0 or successes < 0 or successes > total:
        raise ValueError("successes and total must satisfy 0 <= successes <= total")
    return 100.0 if total == 0 else round(100 * successes / total, 2)


def safety_score(
    *, expected_blocks: int, actual_blocks: int, false_passes: int, total: int
) -> float:
    """Score fail-closed behavior; false passes are twice as costly as misses."""
    if min(expected_blocks, actual_blocks, false_passes, total) < 0:
        raise ValueError("counts cannot be negative")
    if actual_blocks > expected_blocks or false_passes > total:
        raise ValueError("invalid safety counts")
    if total == 0:
        return 100.0
    misses = max(0, expected_blocks - actual_blocks)
    penalty = (false_passes * 2 + misses) / total
    return round(max(0.0, 100 * (1 - penalty)), 2)
