"""Deterministic benchmark harness and trust-comparison runtime for AutoResearch.

Two layers live here.

*Scoring layer* (``BenchmarkHarness`` and friends): consumes *observed*
measurements and turns them into scores.  It deliberately keeps *planned*
benchmark definitions separate from *observed* measurements.

*Runtime layer* (``TrustBenchmarkRuntime`` and friends): *produces* those
measurements.  It drives one frozen corpus through the three conditions the
benchmark document describes -- bare LLM, AutoResearch with the gate off, and
AutoResearch with the gate on -- under a frozen per-run resource budget, and
emits a run-level receipt plus a JSON report artifact.

The two receipt kinds stay separate on purpose: one A4
``CapabilityInvocationReceipt`` describes exactly one adapter invocation, while
one ``BenchmarkRunReceipt`` describes a whole comparison run (many cases x many
conditions, plus budget accounting).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from autoresearch.contracts import (
    EvidenceCandidate,
    EvidenceGrade,
    EvidenceItem,
    EvidenceType,
    GateDecision,
    GateRequest,
    GateStatus,
    RiskLevel,
    new_id,
    utc_now,
)
from autoresearch.evidence import EvidenceService
from autoresearch.pipeline_contracts import (
    BenchmarkPlan,
    MaterialReadinessResult,
    ReadinessStatus,
    SectionDraft,
    SectionPlan,
    SectionValidationReport,
    ValidationVerdict,
)
from autoresearch.search_adapters import SearchAdapterRequest
from autoresearch.section_validator import SectionValidator


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


# ===========================================================================
# Runtime layer (S4-A / A5): *execute* the trust comparison, not just score it.
# ===========================================================================
#
# Everything below produces the observations the scoring layer consumes.  The
# runtime drives one frozen corpus through the conditions the benchmark
# document fixes -- bare LLM, AutoResearch with the gate off, AutoResearch with
# the gate on -- under a frozen per-run resource budget, and emits
#
#   * a ``BenchmarkRunReceipt``: the auditable record of what actually ran
#     (per case, per condition, with call accounting), and
#   * a ``BenchmarkRunReport``: the score summary that gets written to the
#     report artifact on disk.
#
# The receipt is deliberately a different object from A4's
# ``CapabilityInvocationReceipt``.  One A4 receipt answers "what did this single
# adapter invocation do"; one benchmark run receipt answers "what did this whole
# comparison run do".


class BenchmarkCondition(StrEnum):
    """The comparison conditions fixed by ``docs/BENCHMARK.md``."""

    BARE_LLM = "bare_llm"
    GATE_OFF = "gate_off"
    GATE_ON = "gate_on"


DEFAULT_CONDITIONS: tuple[BenchmarkCondition, ...] = (
    BenchmarkCondition.BARE_LLM,
    BenchmarkCondition.GATE_OFF,
    BenchmarkCondition.GATE_ON,
)


class BenchmarkRunStatus(StrEnum):
    COMPLETED = "completed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class CaseStatus(StrEnum):
    """Terminal status of one (case, condition) cell."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    DENIED = "denied"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class CaseOutcome(StrEnum):
    """The cell outcome a mechanism metric is judged against.

    ``ACCEPTED`` means the produced content is allowed through; every other
    terminal status collapses to ``BLOCKED`` except a call that never produced a
    trustworthy result (``interrupted`` / ``failed``), which scores as neither.
    """

    ACCEPTED = "accepted"
    BLOCKED = "blocked"


class BenchmarkStopReason(StrEnum):
    NONE = "none"
    CALL_BUDGET_EXHAUSTED = "call_budget_exhausted"
    WALL_CLOCK_EXHAUSTED = "wall_clock_exhausted"


class BenchmarkBudgetExceeded(RuntimeError):
    """Raised *before* a call is issued once a hard budget stop condition holds.

    Nothing is silently skipped: the caller records a ``denied`` cell and the
    report carries the exhausted budget so a truncated run can never be mistaken
    for a complete one.
    """


class BenchmarkCallInterrupted(RuntimeError):
    """Raised when a single call returns after the frozen soft per-call limit.

    This is the recovery path, not a result: the cell is recorded as
    ``interrupted`` and excluded from the ratio means.
    """


class BudgetView(BaseModel):
    """Read-only projection of the frozen budget, for receipts and reports."""

    max_calls: int = Field(ge=1)
    single_call_timeout_seconds: float = Field(gt=0)
    max_wall_clock_seconds: float = Field(gt=0)


class TokenUsageSlot(BaseModel):
    """Reserved token-accounting slot (TASK-SPECS A5 计价衔接注记).

    The provider lane (O12) owns pricing and lands after this package, and the
    frozen spec requires *this* package to reserve the receipt's cost schema so
    the two ends can meet without a later migration.  The slot is therefore
    declared here field-for-field identical to ``contracts.TokenUsage`` and left
    ``None`` until a provider fills it.

    ``None`` means *not measured*, not *zero tokens*: an unfilled slot must never
    be readable as a free run.
    """

    input: int = Field(default=0, ge=0)
    output: int = Field(default=0, ge=0)
    cache_read: int = Field(default=0, ge=0)
    cache_write: int = Field(default=0, ge=0)
    reasoning: int = Field(
        default=0, ge=0, description="Subset of output tokens; never billed twice."
    )


class InvocationCostSlot(BaseModel):
    """Reserved priced-usage slot (TASK-SPECS A5 计价衔接注记).

    Field-for-field mirror of ``contracts.InvocationCost``.  ``price_source`` is
    kept because these figures are estimates from a price snapshot rather than
    the provider's invoice, and ``attempts`` because a retried call can cost more
    than one that succeeded first try.
    """

    input: float = Field(default=0.0, ge=0)
    output: float = Field(default=0.0, ge=0)
    cache_read: float = Field(default=0.0, ge=0)
    cache_write: float = Field(default=0.0, ge=0)
    total: float = Field(default=0.0, ge=0)
    currency: str = Field(default="USD", max_length=8)
    model: str | None = Field(default=None, max_length=200)
    lane_id: str | None = Field(default=None, max_length=200)
    attempts: int = Field(default=1, ge=1)
    price_source: str | None = Field(default=None, max_length=200)


class BudgetUsage(BaseModel):
    """Per-run accounting written verbatim into the run receipt."""

    calls_used: int = Field(default=0, ge=0)
    calls_denied: int = Field(default=0, ge=0)
    calls_interrupted: int = Field(default=0, ge=0)
    wall_clock_seconds: float = Field(default=0.0, ge=0)
    stop_reason: BenchmarkStopReason = BenchmarkStopReason.NONE
    tokens: TokenUsageSlot | None = None
    cost: InvocationCostSlot | None = None


@dataclass(frozen=True, slots=True)
class ResourceBudget:
    """The frozen per-run budget.

    One of the three karpathy constraints is a *fixed call budget per run*: the
    budget is declared up front, recorded in the receipt, and never inferred
    after the fact from however many calls happened to be made.
    """

    max_calls: int = 240
    single_call_timeout_seconds: float = 20.0
    max_wall_clock_seconds: float = 900.0

    def __post_init__(self) -> None:
        if self.max_calls <= 0:
            raise ValueError("max_calls must be positive")
        if self.single_call_timeout_seconds <= 0:
            raise ValueError("single_call_timeout_seconds must be positive")
        if self.max_wall_clock_seconds <= 0:
            raise ValueError("max_wall_clock_seconds must be positive")

    def view(self) -> BudgetView:
        return BudgetView(
            max_calls=self.max_calls,
            single_call_timeout_seconds=self.single_call_timeout_seconds,
            max_wall_clock_seconds=self.max_wall_clock_seconds,
        )


class CallBudget:
    """Fail-closed enforcement of the frozen resource budget.

    The guarded callable is wrapped, so every call the runtime makes -- retrieval,
    drafting, gate evaluation -- passes through the same accounting.  Two stop
    conditions exist and they behave differently on purpose:

    * **hard** (call cap / wall clock): the next call is denied before it is
      issued.  Denying is observable (``calls_denied`` + ``stop_reason``), so a
      truncated run is never reported as a clean one.
    * **soft** (single-call limit): the call already happened, but its result is
      not trusted as a measurement; the cell is interrupted and routed to
      recovery.
    """

    def __init__(
        self,
        budget: ResourceBudget | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.budget = budget or ResourceBudget()
        self.usage = BudgetUsage()
        self._clock = clock
        self._started = clock()

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self._clock() - self._started)

    @property
    def exhausted(self) -> bool:
        return self.usage.stop_reason is not BenchmarkStopReason.NONE

    def guard(self) -> None:
        """Raise before issuing a call when a hard stop condition holds."""

        if self.usage.calls_used >= self.budget.max_calls:
            self.usage.calls_denied += 1
            self.usage.stop_reason = BenchmarkStopReason.CALL_BUDGET_EXHAUSTED
            raise BenchmarkBudgetExceeded(
                f"call budget exhausted: {self.usage.calls_used}/{self.budget.max_calls} used"
            )
        if self.elapsed_seconds >= self.budget.max_wall_clock_seconds:
            self.usage.calls_denied += 1
            self.usage.stop_reason = BenchmarkStopReason.WALL_CLOCK_EXHAUSTED
            raise BenchmarkBudgetExceeded(
                "wall clock budget exhausted: "
                f"{self.elapsed_seconds:.3f}s/{self.budget.max_wall_clock_seconds:g}s"
            )

    def _accumulate(self, started: float) -> float:
        elapsed = max(0.0, self._clock() - started)
        self.usage.wall_clock_seconds = round(self.usage.wall_clock_seconds + elapsed, 6)
        return elapsed

    def call(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        """Invoke ``fn`` under the budget; raise if it must not or did not count."""

        self.guard()
        self.usage.calls_used += 1
        started = self._clock()
        try:
            value = fn(*args, **kwargs)
        finally:
            elapsed = self._accumulate(started)
        if elapsed > self.budget.single_call_timeout_seconds:
            self.usage.calls_interrupted += 1
            raise BenchmarkCallInterrupted(
                f"single call took {elapsed:.3f}s, over the "
                f"{self.budget.single_call_timeout_seconds:g}s limit"
            )
        return value


# ---------------------------------------------------------------------------
# Frozen corpus
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BenchmarkMaterial:
    """One frozen piece of material a case is allowed to cite.

    ``grade`` / ``evidence_type`` live here and *not* on the candidate: retrieval
    emits unclassified candidates and admission is the layer that classifies
    them (R005).  ``as_candidate`` therefore parks the classification in
    ``candidate.metadata`` for ``EvidenceLedgerAdmission`` to read.
    """

    evidence_id: str
    independent_source: str
    claim: str
    grade: str = "E0"
    evidence_type: str = "system"
    title: str = ""
    source_uri: str | None = None

    def as_candidate(self, *, project_id: str, run_id: str | None = None) -> EvidenceCandidate:
        return EvidenceCandidate(
            evidence_id=self.evidence_id,
            project_id=project_id,
            run_id=run_id,
            title=self.title or None,
            claim=self.claim,
            source_uri=self.source_uri,
            locator="benchmark corpus material",
            independent_source=self.independent_source,
            metadata={
                "benchmark": {
                    "grade": self.grade,
                    "evidence_type": self.evidence_type,
                }
            },
        )


@dataclass(frozen=True, slots=True)
class BenchmarkTask:
    """One frozen case: the question, the frozen draft, and the allowed material."""

    case_id: str
    question: str
    title: str
    body: str
    claims: tuple[str, ...] = ()
    claim_evidence_map: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    materials: tuple[BenchmarkMaterial, ...] = ()
    risk_level: RiskLevel = RiskLevel.L2
    expected_gate: GateStatus = GateStatus.PASS
    expected_outcome: CaseOutcome = CaseOutcome.ACCEPTED
    explicitly_rejected: bool = False
    human_approval: bool = False
    work_closed_loop: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BenchmarkCorpus:
    """A frozen case set plus the digest that pins it."""

    corpus_id: str
    version: str
    cases: tuple[BenchmarkTask, ...]
    digest: str

    def case(self, case_id: str) -> BenchmarkTask:
        for item in self.cases:
            if item.case_id == case_id:
                return item
        raise KeyError(f"unknown benchmark case: {case_id}")


class MetricDefinition(BaseModel):
    """The frozen metric contract.

    Karpathy constraint 1 is "one primary metric".  This object is the single
    place that names it, states its direction, and pins the rule for what counts
    as an unsupported claim.  A run refuses to start against an unfrozen
    definition, so a re-run can never quietly measure a different thing.
    """

    definition_version: str
    primary_metric: str
    direction: str
    formula: str
    unsupported_claim_rule: str
    conditions: list[str]
    case_metrics: list[str]
    report_metrics: list[str]
    frozen: bool = True
    notes: list[str] = Field(default_factory=list)

    def digest(self) -> str:
        return _canonical_digest(self.model_dump(mode="json"))


def _canonical_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_str(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or invalid {key!r} in benchmark corpus entry")
    return value


def _parse_material(case_id: str, row: Any) -> BenchmarkMaterial:
    if not isinstance(row, dict):
        raise ValueError(f"case {case_id}: material must be a JSON object")
    return BenchmarkMaterial(
        evidence_id=_require_str(row, "evidence_id"),
        independent_source=_require_str(row, "independent_source"),
        claim=_require_str(row, "claim"),
        grade=str(row.get("grade", "E0")).upper(),
        evidence_type=str(row.get("evidence_type", "system")).lower(),
        title=str(row.get("title") or ""),
        source_uri=row.get("source_uri") or None,
    )


def _optional_object(row: Mapping[str, Any], key: str, case_id: str) -> dict[str, Any]:
    value = row.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"case {case_id}: {key} must be a JSON object")
    return value


def _optional_list(row: Mapping[str, Any], key: str, case_id: str) -> list[Any]:
    value = row.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"case {case_id}: {key} must be a JSON list")
    return value


def _parse_task(row: Any) -> BenchmarkTask:
    if not isinstance(row, dict):
        raise ValueError("benchmark case must be a JSON object")
    case_id = _require_str(row, "case_id")
    try:
        risk_level = RiskLevel(_require_str(row, "risk_level").upper())
    except ValueError as exc:  # pragma: no cover - message shape, not the branch
        raise ValueError(f"case {case_id}: invalid risk level: {exc}") from exc
    try:
        expected_gate = GateStatus(_require_str(row, "expected_gate").lower())
    except ValueError as exc:  # pragma: no cover - message shape, not the branch
        raise ValueError(f"case {case_id}: invalid expected gate: {exc}") from exc
    try:
        expected_outcome = CaseOutcome(_require_str(row, "expected_outcome").lower())
    except ValueError as exc:  # pragma: no cover - message shape, not the branch
        raise ValueError(f"case {case_id}: invalid expected outcome: {exc}") from exc

    raw_materials = _optional_list(row, "materials", case_id)
    raw_map = _optional_object(row, "claim_evidence_map", case_id)
    raw_metadata = _optional_object(row, "metadata", case_id)
    raw_claims = _optional_list(row, "claims", case_id)

    return BenchmarkTask(
        case_id=case_id,
        question=_require_str(row, "question"),
        title=str(row.get("title") or ""),
        body=_require_str(row, "body"),
        claims=tuple(str(claim) for claim in raw_claims),
        claim_evidence_map={
            str(claim): tuple(str(item) for item in (ids or []))
            for claim, ids in raw_map.items()
        },
        materials=tuple(_parse_material(case_id, item) for item in raw_materials),
        risk_level=risk_level,
        expected_gate=expected_gate,
        expected_outcome=expected_outcome,
        explicitly_rejected=bool(row.get("explicitly_rejected", False)),
        human_approval=bool(row.get("human_approval", False)),
        work_closed_loop=bool(row.get("work_closed_loop", False)),
        metadata=raw_metadata,
    )


def load_corpus(path: str | Path) -> BenchmarkCorpus:
    """Load and validate a frozen corpus; every malformed shape fails closed."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable benchmark corpus: {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("benchmark corpus must be a JSON object")

    corpus_id = _require_str(payload, "corpus_id")
    version = _require_str(payload, "version")
    rows = payload.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ValueError("benchmark corpus must contain a non-empty cases list")

    cases: list[BenchmarkTask] = []
    seen: set[str] = set()
    for row in rows:
        task = _parse_task(row)
        if task.case_id in seen:
            raise ValueError(f"duplicate benchmark case id: {task.case_id}")
        seen.add(task.case_id)
        cases.append(task)
    return BenchmarkCorpus(
        corpus_id=corpus_id,
        version=version,
        cases=tuple(cases),
        digest=_canonical_digest(payload),
    )


def load_metric_definition(path: str | Path) -> MetricDefinition:
    """Load the frozen metric definition; an unfrozen one is refused."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable metric definition: {source}: {exc}") from exc
    try:
        definition = MetricDefinition.model_validate(payload)
    except ValidationError as exc:  # pragma: no cover - message shape
        raise ValueError(f"invalid metric definition: {source}: {exc}") from exc
    if not definition.frozen:
        raise ValueError(
            "metric definition must be frozen for a comparable run; "
            "flip `frozen` only together with a new definition_version"
        )
    return definition


# ---------------------------------------------------------------------------
# Frozen metric: hallucination ratio
# ---------------------------------------------------------------------------


def hallucination_ratio(*, unsupported_claims: int, total_claims: int) -> float:
    """The frozen primary metric, in ``[0, 1]``; lower is better.

    ``unsupported_claims / total_claims``.  A draft with no claims scores
    ``0.0``: zero claims is a deterministic empty result, not an unknown outcome
    (D-F8-01), and it must not be able to look like a perfect or an undefined
    score by accident.
    """

    if total_claims < 0 or unsupported_claims < 0 or unsupported_claims > total_claims:
        raise ValueError("claims must satisfy 0 <= unsupported_claims <= total_claims")
    if total_claims == 0:
        return 0.0
    return round(unsupported_claims / total_claims, 6)


def _ratio(numerator: int, denominator: int) -> float:
    """Adverse rate; an empty denominator scores 0.0 rather than full credit.

    A *non-zero* numerator over an empty denominator is a modelling error, not a
    perfect score.  Every caller draws the numerator from the denominator's own
    set, so this can only fire if that invariant breaks -- fail loudly instead of
    silently reporting 0.0 for something that provably happened.
    """

    if denominator <= 0:
        if numerator > 0:
            raise ValueError(
                "adverse ratio with a non-zero numerator over an empty "
                f"denominator: {numerator}/{denominator}"
            )
        return 0.0
    return round(numerator / denominator, 6)


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def _fully_bound(evidence_ids: Sequence[str], allowed: set[str]) -> bool:
    return bool(evidence_ids) and set(evidence_ids) <= allowed


# ---------------------------------------------------------------------------
# Injection seams: agent, materials, admission, gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AgentDraft:
    body: str
    title: str = ""
    claims: tuple[str, ...] = ()
    claim_evidence_map: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


class BenchmarkAgent(Protocol):
    """The drafting step under test."""

    name: str

    def draft(self, task: BenchmarkTask) -> AgentDraft: ...


@dataclass(frozen=True, slots=True)
class RecordedAgent:
    """Replays the draft frozen in the corpus case.

    Fixing the corpus fixes the prompts, which is exactly karpathy constraint 2:
    swapping the writing head must not silently change the measured quantity.
    A live model would be wrapped in the same protocol instead.
    """

    name: str = "recorded-corpus-agent"

    def draft(self, task: BenchmarkTask) -> AgentDraft:
        return AgentDraft(
            body=task.body,
            title=task.title,
            claims=task.claims,
            claim_evidence_map=task.claim_evidence_map,
        )


@dataclass(frozen=True, slots=True)
class MaterialsOutcome:
    """What a material source returned, including its terminal status."""

    candidates: tuple[EvidenceCandidate, ...] = ()
    status: str = "completed"
    admissible: bool = True
    diagnostics: tuple[str, ...] = ()


class MaterialsProvider(Protocol):
    """The retrieval step; may go through the A4 registry or a frozen fixture."""

    name: str

    def materials(
        self,
        task: BenchmarkTask,
        *,
        project_id: str,
        run_id: str,
        scope: str,
    ) -> MaterialsOutcome: ...


@dataclass(frozen=True, slots=True)
class FixtureMaterialsProvider:
    """Offline material source: the frozen corpus *is* the material store."""

    name: str = "fixture-materials"

    def materials(
        self,
        task: BenchmarkTask,
        *,
        project_id: str,
        run_id: str,
        scope: str,
    ) -> MaterialsOutcome:
        candidates = tuple(
            material.as_candidate(project_id=project_id, run_id=run_id)
            for material in task.materials
        )
        diagnostics = [f"fixture materials: {len(candidates)} candidate(s) for {scope}"]
        if not candidates:
            diagnostics.append(
                "deterministic empty result; material absence, not unknown (D-F8-01)"
            )
        return MaterialsOutcome(
            candidates=candidates,
            status="completed",
            diagnostics=tuple(diagnostics),
        )


class InvocationRegistry(Protocol):
    """The slice of the A4 registry the runtime is allowed to use."""

    def invoke(self, capability: str, request: Any, *, invocation_id: str | None = None) -> Any: ...


class RegistryMaterialsProvider:
    """Pulls material through the A4 ``CapabilityRegistry`` surface.

    Honours D-S3-01: only ``invocation.admissible_candidates`` are returned, so a
    rate-limited, unavailable or denied retrieval can never contribute material.
    A ``completed`` retrieval with zero hits stays a *deterministic empty*
    result (D-F8-01), never an unknown outcome.
    """

    def __init__(
        self,
        registry: InvocationRegistry,
        capability: str,
        *,
        limit: int = 10,
        name: str | None = None,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        self.registry = registry
        self.capability = capability
        self.limit = limit
        self.name = name or f"registry:{capability}"

    def materials(
        self,
        task: BenchmarkTask,
        *,
        project_id: str,
        run_id: str,
        scope: str,
    ) -> MaterialsOutcome:
        request = SearchAdapterRequest(
            project_id=project_id,
            run_id=run_id,
            invocation_id=f"bench-{scope}",
            query=task.question,
            limit=self.limit,
        )
        invocation = self.registry.invoke(self.capability, request)
        receipt = invocation.receipt
        outcome = receipt.outcome_status or receipt.status
        return MaterialsOutcome(
            candidates=tuple(invocation.admissible_candidates),
            status=outcome.value,
            admissible=bool(receipt.candidates_admissible),
            diagnostics=tuple(invocation.diagnostics),
        )


class AdmissionPort(Protocol):
    """Turns admissible candidates into the evidence ids a gate can resolve."""

    def admit(
        self, candidates: Sequence[EvidenceCandidate], *, project_id: str
    ) -> tuple[str, ...]: ...


class CorpusLabelAdmission:
    """Offline ledger that keeps the corpus label as the evidence id.

    Used when no store-backed admission is wired.  The ids are real enough to
    score claim binding against, but no gate can resolve them -- which is why
    the default runtime has no gate.
    """

    name = "corpus-label-admission"

    def __init__(self) -> None:
        self._counter = 0

    def admit(
        self, candidates: Sequence[EvidenceCandidate], *, project_id: str
    ) -> tuple[str, ...]:
        admitted: list[str] = []
        for candidate in candidates:
            if candidate.evidence_id:
                admitted.append(candidate.evidence_id)
                continue
            self._counter += 1
            admitted.append(f"ev-{self._counter:04d}")
        return tuple(admitted)


class EvidenceLedgerAdmission:
    """Store-backed admission: materialises candidates into ``EvidenceItem``s.

    This is the only place a benchmark material acquires an evidence grade, so
    the R005 boundary stays intact: retrieval emits unclassified candidates and
    admission classifies them.  The corpus label is reused as the evidence id so
    the frozen drafts stay bound to the material they were written against.
    """

    name = "evidence-ledger-admission"

    def __init__(self, evidence: EvidenceService, *, actor: str = "benchmark_runtime") -> None:
        self.evidence = evidence
        self.actor = actor

    def admit(
        self, candidates: Sequence[EvidenceCandidate], *, project_id: str
    ) -> tuple[str, ...]:
        admitted: list[str] = []
        for candidate in candidates:
            classification = (candidate.metadata or {}).get("benchmark") or {}
            evidence_id = candidate.evidence_id or new_id("ev")
            if self.evidence.get(evidence_id) is not None:
                # Admission is idempotent by evidence id, so the same material
                # reused by a second condition resolves to the same record.
                admitted.append(evidence_id)
                continue
            item = EvidenceItem(
                evidence_id=evidence_id,
                project_id=project_id,
                evidence_type=EvidenceType(
                    classification.get("evidence_type", EvidenceType.SYSTEM.value)
                ),
                grade=EvidenceGrade(classification.get("grade", EvidenceGrade.E0.value)),
                title=(candidate.title or candidate.claim)[:300],
                claim=candidate.claim,
                source_uri=candidate.source_uri,
                source_id=candidate.source_id,
                locator=candidate.locator or "benchmark corpus material",
                independent_source=candidate.independent_source,
            )
            stored = self.evidence.add(item, actor=self.actor)
            admitted.append(stored.evidence_id)
        return tuple(admitted)


class GateHook(Protocol):
    """The gate step; ``autoresearch.gates.GateService`` satisfies it as-is."""

    def evaluate(self, request: GateRequest) -> GateDecision: ...


# ---------------------------------------------------------------------------
# Receipts and report
# ---------------------------------------------------------------------------


class CaseRunReceipt(BaseModel):
    """One (case, condition) cell: what ran, what it produced, what it cost.

    The cost is a *reserved slot* here, not a measurement: A5 runs no provider,
    so ``tokens`` / ``cost`` stay ``None`` until the provider lane fills them.
    """

    case_id: str
    condition: BenchmarkCondition
    status: CaseStatus
    risk_level: RiskLevel
    expected_gate: GateStatus
    expected_outcome: CaseOutcome
    observed_outcome: CaseOutcome | None = None
    observed_gate: GateStatus | None = None
    gate_matched: bool | None = None
    accepted: bool = False
    materials_status: str | None = None
    material_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    claims_total: int = Field(default=0, ge=0)
    claims_supported: int = Field(default=0, ge=0)
    unsupported_claims: list[str] = Field(default_factory=list)
    result_like_numeric_claims: list[str] = Field(default_factory=list)
    hallucination_ratio: float = Field(default=0.0, ge=0, le=1)
    accepted_hallucination_ratio: float = Field(default=0.0, ge=0, le=1)
    evidence_binding_rate: float = Field(default=0.0, ge=0, le=1)
    validation_verdict: ValidationVerdict | None = None
    calls: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0)
    tokens: TokenUsageSlot | None = None
    cost: InvocationCostSlot | None = None
    diagnostics: list[str] = Field(default_factory=list)


class BenchmarkRunReceipt(BaseModel):
    """Run-level accounting for one whole comparison run.

    Kept separate from A4's ``CapabilityInvocationReceipt`` on purpose: this one
    spans many cases and conditions and owns the budget ledger, while an A4
    receipt describes exactly one adapter invocation.
    """

    run_id: str
    benchmark_id: str
    version: str
    corpus_id: str
    corpus_version: str
    corpus_digest: str
    metric_definition_version: str
    metric_definition_digest: str
    primary_metric: str
    conditions: list[BenchmarkCondition]
    budget: BudgetView
    usage: BudgetUsage
    case_receipts: list[CaseRunReceipt] = Field(default_factory=list)
    status: BenchmarkRunStatus = BenchmarkRunStatus.COMPLETED
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)
    notes: list[str] = Field(default_factory=list)

    def receipt_for(
        self, case_id: str, condition: BenchmarkCondition
    ) -> CaseRunReceipt | None:
        for item in self.case_receipts:
            if item.case_id == case_id and item.condition is condition:
                return item
        return None


class ConditionSummary(BaseModel):
    """Per-condition roll-up.

    ``hallucination_ratio`` covers *scored* cells (completed + blocked) and so
    measures the frozen drafts themselves.  ``accepted_hallucination_ratio``
    covers *accepted* cells only and measures what survived governance -- that
    is the number the gate is expected to move.

    An *unaccepted* cell contributes nothing to that measure: blocking a cell
    means no content was released, not that clean content was released.  Folding
    unaccepted cells in as ``0.0`` makes the score rise the more the mechanism
    blocks, which is the opposite of what the score is for (adversarial review
    2026-09-11: a live run with ``acceptance_rate = 0.0`` reported
    ``score = 100.0``).  When a condition accepted nothing there is no released
    content to score, so both ``accepted_hallucination_ratio`` and ``score`` are
    ``None`` -- the same reason ``score`` is ``None`` when nothing was scored,
    and it can never present itself as a perfect score.
    """

    condition: BenchmarkCondition
    cases: int = Field(ge=0)
    scored: int = Field(ge=0)
    completed: int = Field(ge=0)
    blocked: int = Field(ge=0)
    denied: int = Field(ge=0)
    interrupted: int = Field(ge=0)
    failed: int = Field(ge=0)
    accepted: int = Field(ge=0)
    zero_claim_cells: int = Field(ge=0)
    acceptance_rate: float = Field(ge=0, le=1)
    hallucination_ratio: float = Field(ge=0, le=1)
    accepted_hallucination_ratio: float | None = Field(default=None, ge=0, le=1)
    evidence_binding_rate: float = Field(ge=0, le=1)
    score: float | None = Field(default=None, ge=0, le=100)


class BenchmarkRunReport(BaseModel):
    """The report artifact written to ``evidence/benchmark-report.json``."""

    report_id: str
    benchmark_id: str
    version: str
    corpus_id: str
    corpus_version: str
    corpus_digest: str
    metric_definition_version: str
    metric_definition_digest: str
    primary_metric: str
    primary_metric_direction: str
    conditions: list[ConditionSummary]
    mechanism_metrics: dict[str, float | None]
    budget: BudgetView
    usage: BudgetUsage
    status: BenchmarkRunStatus
    generated_at: datetime = Field(default_factory=utc_now)
    warnings: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True, default=str
        )
        target.write_text(payload + "\n", encoding="utf-8")
        return target


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    """Receipt + report from one run."""

    receipt: BenchmarkRunReceipt
    report: BenchmarkRunReport

    def write_report(self, path: str | Path) -> Path:
        return self.report.write(path)


# ---------------------------------------------------------------------------
# Section contracts rebuilt from a frozen case
# ---------------------------------------------------------------------------


def _section_plan(
    *,
    project_id: str,
    task: BenchmarkTask,
    plan_id: str,
    evidence_ids: Sequence[str],
    profile_id: str,
) -> SectionPlan:
    return SectionPlan(
        plan_id=plan_id,
        project_id=project_id,
        section_name="Evaluation",
        objective=task.question[:1000],
        claims=list(task.claims),
        claim_evidence_map={
            claim: list(ids) for claim, ids in task.claim_evidence_map.items()
        },
        evidence_ids=list(evidence_ids),
        profile_id=profile_id,
    )


def _benchmark_plan(*, project_id: str, task: BenchmarkTask, plan_id: str) -> BenchmarkPlan:
    return BenchmarkPlan(
        project_id=project_id,
        section_id=plan_id,
        benchmark_name=f"benchmark:{task.case_id}",
        baseline=["the frozen corpus case defines the reported baseline"],
        metrics=["claim_evidence_consistency"],
    )


def _readiness(
    *,
    project_id: str,
    plan_id: str,
    benchmark_plan_id: str,
    profile_id: str,
    evidence_ids: Sequence[str],
) -> MaterialReadinessResult:
    """Readiness is out of scope for this slice; the corpus is always ready.

    Material *sufficiency* is judged by the gate, not by readiness, so that the
    three conditions differ only in the mechanism under test.  The admitted ids
    still have to travel through readiness: that list is what the validator uses
    as the allowed evidence set.
    """

    return MaterialReadinessResult(
        project_id=project_id,
        section_id=plan_id,
        status=ReadinessStatus.READY,
        evidence_ids=list(evidence_ids),
        benchmark_plan_id=benchmark_plan_id,
        profile_id=profile_id,
    )


def _section_draft(
    *, project_id: str, task: BenchmarkTask, plan_id: str, benchmark_plan_id: str, profile_id: str
) -> SectionDraft:
    return SectionDraft(
        project_id=project_id,
        section_id=plan_id,
        profile_id=profile_id,
        plan_id=plan_id,
        benchmark_plan_id=benchmark_plan_id,
        title=task.title or f"Evaluation: {task.case_id}",
        body=task.body,
        claims=list(task.claims),
        claim_evidence_map={
            claim: list(ids) for claim, ids in task.claim_evidence_map.items()
        },
        evidence_ids=sorted(
            {item for ids in task.claim_evidence_map.values() for item in ids}
        ),
    )


# ---------------------------------------------------------------------------
# The runtime
# ---------------------------------------------------------------------------


class TrustBenchmarkRuntime:
    """Execute the frozen corpus through the comparison conditions."""

    def __init__(
        self,
        *,
        corpus: BenchmarkCorpus,
        metric_definition: MetricDefinition,
        agent: BenchmarkAgent | None = None,
        budget: ResourceBudget | None = None,
        materials: MaterialsProvider | None = None,
        admission: AdmissionPort | None = None,
        gate: GateHook | None = None,
        validator: SectionValidator | None = None,
        benchmark_id: str = "autoresearch-trust-benchmark",
        version: str = "1.0",
        project_id: str = "benchmark",
        run_id: str = "benchmark-run",
        report_id: str = "benchmark-report",
        profile_id: str = "benchmark-profile",
        limitations: Sequence[str] = (),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.corpus = corpus
        self.metric_definition = metric_definition
        self.agent = agent or RecordedAgent()
        self.budget = budget or ResourceBudget()
        self.materials = materials
        self.admission = admission or CorpusLabelAdmission()
        self.gate = gate
        self.validator = validator or SectionValidator()
        self.benchmark_id = benchmark_id
        self.version = version
        self.project_id = project_id
        self.run_id = run_id
        self.report_id = report_id
        self.profile_id = profile_id
        # Limitations declared by the caller (e.g. "this run used live retrieval")
        # are carried into the report's warnings, so a reader can never mistake a
        # measurement for one that was actually comparable.
        self._limitations = tuple(limitations)
        self._clock = clock
        self._ledger = CallBudget(self.budget, clock=clock)
        self._ran = False

    # -- public ------------------------------------------------------------

    def run(self, conditions: Sequence[BenchmarkCondition] | None = None) -> BenchmarkRun:
        if self._ran:
            raise RuntimeError(
                "this runtime instance already ran; build a new runtime for a new run "
                "so the budget ledger cannot be carried across runs"
            )
        requested = tuple(
            BenchmarkCondition(item)
            for item in (DEFAULT_CONDITIONS if conditions is None else conditions)
        )
        if not requested:
            raise ValueError("at least one benchmark condition is required")
        if BenchmarkCondition.GATE_ON in requested and self.gate is None:
            raise ValueError(
                "the gate_on condition needs a gate hook; pass gate=... (GateService fits)"
            )
        declared = {str(item) for item in self.metric_definition.conditions}
        undeclared = sorted({item.value for item in requested} - declared)
        if undeclared:
            raise ValueError(
                f"conditions not declared in the frozen metric definition: {undeclared}"
            )

        self._ran = True
        started_at = utc_now()
        cells: list[CaseRunReceipt] = [
            self._run_case(task, condition)
            for task in self.corpus.cases
            for condition in requested
        ]
        finished_at = utc_now()

        status = BenchmarkRunStatus.COMPLETED
        notes: list[str] = list(self._limitations)
        if any(item.status is CaseStatus.FAILED for item in cells):
            status = BenchmarkRunStatus.FAILED
            notes.append("at least one cell failed; the comparison is not clean")
        if any(item.status is CaseStatus.INTERRUPTED for item in cells):
            if status is BenchmarkRunStatus.COMPLETED:
                status = BenchmarkRunStatus.INTERRUPTED
            notes.append("at least one call exceeded the soft per-call limit")
        if self._ledger.usage.stop_reason is not BenchmarkStopReason.NONE:
            status = BenchmarkRunStatus.BUDGET_EXHAUSTED
            notes.append(
                f"hard stop condition reached: {self._ledger.usage.stop_reason.value}"
            )

        receipt = BenchmarkRunReceipt(
            run_id=self.run_id,
            benchmark_id=self.benchmark_id,
            version=self.version,
            corpus_id=self.corpus.corpus_id,
            corpus_version=self.corpus.version,
            corpus_digest=self.corpus.digest,
            metric_definition_version=self.metric_definition.definition_version,
            metric_definition_digest=self.metric_definition.digest(),
            primary_metric=self.metric_definition.primary_metric,
            conditions=list(requested),
            budget=self._ledger.budget.view(),
            usage=self._ledger.usage.model_copy(deep=True),
            case_receipts=cells,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            notes=notes,
        )
        return BenchmarkRun(receipt=receipt, report=self._report(receipt))

    # -- one cell ----------------------------------------------------------

    def _terminal(
        self,
        task: BenchmarkTask,
        condition: BenchmarkCondition,
        status: CaseStatus,
        *,
        calls_before: int,
        started: float,
        message: str,
    ) -> CaseRunReceipt:
        return CaseRunReceipt(
            case_id=task.case_id,
            condition=condition,
            status=status,
            risk_level=task.risk_level,
            expected_gate=task.expected_gate,
            expected_outcome=task.expected_outcome,
            observed_outcome=(
                CaseOutcome.BLOCKED if status is CaseStatus.DENIED else None
            ),
            accepted=False,
            calls=self._ledger.usage.calls_used - calls_before,
            duration_seconds=round(max(0.0, self._clock() - started), 6),
            diagnostics=[message],
        )

    def _step(
        self,
        task: BenchmarkTask,
        condition: BenchmarkCondition,
        label: str,
        fn: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: Mapping[str, Any] | None = None,
        *,
        calls_before: int,
        started: float,
    ) -> tuple[Any, CaseRunReceipt | None]:
        """Run one budgeted step, turning any stop condition into a receipt.

        Returns ``(value, None)`` on success and ``(None, receipt)`` when the step
        was denied, interrupted or blew up.  A single broken step must not take
        the whole comparison run down with it: the cell is recorded and the run
        keeps going, so the report can say exactly which cells are missing.
        """

        try:
            return self._ledger.call(fn, *args, **(dict(kwargs or {}))), None
        except BenchmarkBudgetExceeded as exc:
            return None, self._terminal(
                task,
                condition,
                CaseStatus.DENIED,
                calls_before=calls_before,
                started=started,
                message=f"{label}: {exc}",
            )
        except BenchmarkCallInterrupted as exc:
            return None, self._terminal(
                task,
                condition,
                CaseStatus.INTERRUPTED,
                calls_before=calls_before,
                started=started,
                message=f"{label}: {exc}",
            )
        except Exception as exc:  # a broken step is a failed cell, not a crash
            return None, self._terminal(
                task,
                condition,
                CaseStatus.FAILED,
                calls_before=calls_before,
                started=started,
                message=f"{label}: {type(exc).__name__}: {exc}",
            )

    def _run_case(self, task: BenchmarkTask, condition: BenchmarkCondition) -> CaseRunReceipt:
        scope = f"{condition.value}:{task.case_id}"
        calls_before = self._ledger.usage.calls_used
        started = self._clock()
        diagnostics: list[str] = []
        budget_kwargs = {"calls_before": calls_before, "started": started}

        materials_status: str | None = None
        candidates: tuple[EvidenceCandidate, ...] = ()
        if condition is not BenchmarkCondition.BARE_LLM and self.materials is not None:
            outcome, failure = self._step(
                task,
                condition,
                "retrieval",
                self.materials.materials,
                (task,),
                {
                    "project_id": self.project_id,
                    "run_id": self.run_id,
                    "scope": scope,
                },
                **budget_kwargs,
            )
            if failure is not None:
                return failure
            materials_status = outcome.status
            candidates = outcome.candidates
            diagnostics.extend(outcome.diagnostics)
            if not outcome.admissible:
                diagnostics.append(
                    "retrieval outcome is not admissible; no material entered this cell "
                    "(D-S3-01)"
                )

        evidence_ids: tuple[str, ...] = ()
        if candidates:
            evidence_ids = tuple(self.admission.admit(candidates, project_id=self.project_id))

        draft, failure = self._step(
            task,
            condition,
            "drafting",
            self.agent.draft,
            (task,),
            None,
            **budget_kwargs,
        )
        if failure is not None:
            return failure

        verdict: ValidationVerdict | None = None
        if condition is not BenchmarkCondition.BARE_LLM:
            verdict = self._validate(task, evidence_ids)

        gate_status: GateStatus | None = None
        if condition is BenchmarkCondition.GATE_ON:
            assert self.gate is not None  # guarded in run()
            request = GateRequest(
                project_id=self.project_id,
                operation=f"benchmark:{task.case_id}",
                risk_level=task.risk_level,
                claim=task.question[:2000],
                evidence_ids=list(evidence_ids),
                work_closed_loop=task.work_closed_loop,
                explicitly_rejected=task.explicitly_rejected,
                human_approval=task.human_approval,
            )
            decision, failure = self._step(
                task,
                condition,
                "gate",
                self.gate.evaluate,
                (request,),
                None,
                **budget_kwargs,
            )
            if failure is not None:
                return failure
            gate_status = decision.status
            diagnostics.append(f"gate {decision.status.value}: {'; '.join(decision.reasons)}")

        allowed = set(evidence_ids)
        unsupported = [
            claim
            for claim in draft.claims
            if not _fully_bound(draft.claim_evidence_map.get(claim, ()), allowed)
        ]
        numeric = SectionValidator._result_like_numeric_claims(draft.body)
        claims_total = len(draft.claims) + len(numeric)
        unsupported_total = len(unsupported) + len(numeric)
        supported = len(draft.claims) - len(unsupported)

        if condition is BenchmarkCondition.GATE_ON:
            # Governance-on enforces both layers: the deterministic gate decides
            # whether the evidence is sufficient, and the section validator
            # decides whether the draft itself is admissible.
            accepted = gate_status is GateStatus.PASS and verdict is ValidationVerdict.VERIFIED
            if gate_status is GateStatus.PASS and not accepted:
                diagnostics.append(
                    "gate passed but the section validator asked for a revision; "
                    "governance-on enforces both"
                )
        else:
            # Gate off: retrieval, admission and validation all still run and are
            # recorded, but nothing blocks.  That is what makes the comparison a
            # comparison -- only the enforcement differs.
            accepted = True
        accepted_unsupported = 0 if not accepted else unsupported_total

        return CaseRunReceipt(
            case_id=task.case_id,
            condition=condition,
            status=CaseStatus.COMPLETED if accepted else CaseStatus.BLOCKED,
            risk_level=task.risk_level,
            expected_gate=task.expected_gate,
            expected_outcome=task.expected_outcome,
            observed_outcome=CaseOutcome.ACCEPTED if accepted else CaseOutcome.BLOCKED,
            observed_gate=gate_status,
            gate_matched=None if gate_status is None else gate_status is task.expected_gate,
            accepted=accepted,
            materials_status=materials_status,
            material_count=len(candidates),
            evidence_count=len(evidence_ids),
            claims_total=claims_total,
            claims_supported=supported,
            unsupported_claims=unsupported,
            result_like_numeric_claims=numeric,
            hallucination_ratio=hallucination_ratio(
                unsupported_claims=unsupported_total, total_claims=claims_total
            ),
            accepted_hallucination_ratio=hallucination_ratio(
                unsupported_claims=accepted_unsupported, total_claims=claims_total
            ),
            evidence_binding_rate=_ratio(supported, len(draft.claims)),
            validation_verdict=verdict,
            calls=self._ledger.usage.calls_used - calls_before,
            duration_seconds=round(max(0.0, self._clock() - started), 6),
            diagnostics=diagnostics,
        )

    def _validate(
        self, task: BenchmarkTask, evidence_ids: Sequence[str]
    ) -> ValidationVerdict:
        plan_id = f"splan-{task.case_id}"
        benchmark_plan_id = f"bplan-{task.case_id}"
        report: SectionValidationReport = self.validator.validate(
            _section_plan(
                project_id=self.project_id,
                task=task,
                plan_id=plan_id,
                evidence_ids=evidence_ids,
                profile_id=self.profile_id,
            ),
            _section_draft(
                project_id=self.project_id,
                task=task,
                plan_id=plan_id,
                benchmark_plan_id=benchmark_plan_id,
                profile_id=self.profile_id,
            ),
            _readiness(
                project_id=self.project_id,
                plan_id=plan_id,
                benchmark_plan_id=benchmark_plan_id,
                profile_id=self.profile_id,
                evidence_ids=evidence_ids,
            ),
            _benchmark_plan(project_id=self.project_id, task=task, plan_id=plan_id),
        )
        return report.verdict

    # -- roll-up -----------------------------------------------------------

    def _summarize(
        self, condition: BenchmarkCondition, cells: Sequence[CaseRunReceipt]
    ) -> ConditionSummary:
        scored = [
            item
            for item in cells
            if item.status in (CaseStatus.COMPLETED, CaseStatus.BLOCKED)
        ]
        # Only an accepted cell released content, so only an accepted cell can be
        # scored for how clean the released content is.  Counting a blocked cell
        # as 0.0 would make the score climb the more the mechanism blocks.
        accepted = [item for item in cells if item.accepted]
        accepted_ratios = [item.accepted_hallucination_ratio for item in accepted]
        return ConditionSummary(
            condition=condition,
            cases=len(cells),
            scored=len(scored),
            completed=sum(item.status is CaseStatus.COMPLETED for item in cells),
            blocked=sum(item.status is CaseStatus.BLOCKED for item in cells),
            denied=sum(item.status is CaseStatus.DENIED for item in cells),
            interrupted=sum(item.status is CaseStatus.INTERRUPTED for item in cells),
            failed=sum(item.status is CaseStatus.FAILED for item in cells),
            accepted=len(accepted),
            zero_claim_cells=sum(item.claims_total == 0 for item in scored),
            acceptance_rate=_ratio(len(accepted), len(cells)),
            hallucination_ratio=_mean([item.hallucination_ratio for item in scored]),
            accepted_hallucination_ratio=(
                _mean(accepted_ratios) if accepted_ratios else None
            ),
            evidence_binding_rate=_mean([item.evidence_binding_rate for item in scored]),
            score=(
                round(100.0 * (1.0 - _mean(accepted_ratios)), 2)
                if accepted_ratios
                else None
            ),
        )

    def _mechanism_metrics(self, cells: Sequence[CaseRunReceipt]) -> dict[str, float | None]:
        """Fail-closed behaviour of governance-on, measured against corpus labels.

        A rate whose denominator is empty is ``None``, not ``100.0``: "there was
        nothing to block" is not "blocking was perfect".  Same rule as
        ``ConditionSummary.score`` (D-A5-10).
        """

        gate_on = [item for item in cells if item.condition is BenchmarkCondition.GATE_ON]
        if not gate_on:
            return {}
        total = len(gate_on)
        should_block = [
            item for item in gate_on if item.expected_outcome is CaseOutcome.BLOCKED
        ]
        should_accept = [
            item for item in gate_on if item.expected_outcome is CaseOutcome.ACCEPTED
        ]
        true_blocks = sum(
            item.observed_outcome is CaseOutcome.BLOCKED for item in should_block
        )
        false_passes = sum(
            item.observed_outcome is CaseOutcome.ACCEPTED for item in should_block
        )
        false_blocks = sum(
            item.observed_outcome is CaseOutcome.BLOCKED for item in should_accept
        )
        unscored = sum(item.observed_outcome is None for item in gate_on)
        penalty = (2.0 * false_passes + false_blocks) / total if total else 0.0
        return {
            "cases": float(total),
            "expected_blocks": float(len(should_block)),
            "expected_accepts": float(len(should_accept)),
            "true_blocks": float(true_blocks),
            "false_passes": float(false_passes),
            "false_blocks": float(false_blocks),
            "unscored_cells": float(unscored),
            "fail_closed_block_rate": (
                ratio_score(true_blocks, len(should_block)) if should_block else None
            ),
            "false_pass_rate": round(_ratio(false_passes, total) * 100, 2),
            "false_block_rate": (
                round(_ratio(false_blocks, len(should_accept)) * 100, 2)
                if should_accept
                else None
            ),
            "mechanism_safety_score": round(max(0.0, 100.0 * (1.0 - penalty)), 2),
        }

    def _report(self, receipt: BenchmarkRunReceipt) -> BenchmarkRunReport:
        summaries = [
            self._summarize(
                condition,
                [item for item in receipt.case_receipts if item.condition is condition],
            )
            for condition in receipt.conditions
        ]
        warnings = list(receipt.notes)
        unpriced = sum(item.cost is None for item in receipt.case_receipts)
        if unpriced:
            warnings.append(
                f"{unpriced}/{len(receipt.case_receipts)} cell(s) carry no cost: the receipt "
                "reserves the cost schema (TASK-SPECS A5 计价衔接注记) but this package "
                "calls no provider, so tokens/cost stay None until the O12 provider lane "
                "fills them"
            )
        unscored = sum(item.denied + item.interrupted for item in summaries)
        if unscored:
            warnings.append(
                f"{unscored} cell(s) were denied or interrupted; the ratio means cover "
                "scored cells only, and a condition that accepted nothing reports no "
                "accepted ratio (the means never treat a blocked cell as clean)"
            )
        if any(item.failed for item in summaries):
            warnings.append("failed cells are recorded in the receipt and excluded from scoring")
        if any(item.scored == 0 for item in summaries):
            warnings.append(
                "at least one condition has no scored cells; its score is None and the "
                "comparison is incomplete"
            )
        return BenchmarkRunReport(
            report_id=self.report_id,
            benchmark_id=self.benchmark_id,
            version=self.version,
            corpus_id=receipt.corpus_id,
            corpus_version=receipt.corpus_version,
            corpus_digest=receipt.corpus_digest,
            metric_definition_version=receipt.metric_definition_version,
            metric_definition_digest=receipt.metric_definition_digest,
            primary_metric=self.metric_definition.primary_metric,
            primary_metric_direction=self.metric_definition.direction,
            conditions=summaries,
            mechanism_metrics=self._mechanism_metrics(receipt.case_receipts),
            budget=receipt.budget,
            usage=receipt.usage,
            status=receipt.status,
            warnings=warnings,
        )

