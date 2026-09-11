"""Runtime-layer tests for the A5 trust benchmark (S4-A)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from autoresearch.benchmark import (
    DEFAULT_CONDITIONS,
    AgentDraft,
    BenchmarkBudgetExceeded,
    BenchmarkCondition,
    BenchmarkMaterial,
    BenchmarkRunStatus,
    BenchmarkStopReason,
    BenchmarkTask,
    BudgetUsage,
    CallBudget,
    CaseOutcome,
    CaseStatus,
    CorpusLabelAdmission,
    EvidenceLedgerAdmission,
    FixtureMaterialsProvider,
    InvocationCostSlot,
    MaterialsOutcome,
    MetricDefinition,
    RecordedAgent,
    RegistryMaterialsProvider,
    ResourceBudget,
    TokenUsageSlot,
    TrustBenchmarkRuntime,
    _ratio,
    hallucination_ratio,
    load_corpus,
    load_metric_definition,
)
from autoresearch.capability_registry import (
    CapabilityAdapterResult,
    CapabilityKind,
    CapabilityReceiptStatus,
    CapabilityRegistry,
    CapabilityTrustTier,
)
from autoresearch.contracts import (
    EvidenceCandidate,
    EvidenceGrade,
    EvidenceType,
    GateDecision,
    GateStatus,
)
from autoresearch.evidence import EvidenceService
from autoresearch.gates import GateService
from autoresearch.invocation_contracts import CapabilityManifest
from autoresearch.storage import RecordStore

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "benchmark"
CORPUS_PATH = FIXTURE_DIR / "corpus.json"
METRIC_PATH = FIXTURE_DIR / "metric-definition.json"

# Frozen numbers for the committed corpus.  They are the regression guard: any
# change to the runtime, the corpus or the metric definition has to update them
# on purpose.
FROZEN_CASE_COUNT = 24
FROZEN_GATE_ON_ACCEPTED = 14
FROZEN_DRAFT_HALLUCINATION = 0.145833
FROZEN_BINDING_RATE = 0.881944
FROZEN_CALLS = 144
FROZEN_CORPUS_DIGEST = "1e4aa96686ffcc2242210b7824ab50d74ef84c7fbdb000a3bc65bc16870609b2"
FROZEN_METRIC_DEFINITION_DIGEST = (
    "01960a93ed5d87cc77afbb174043bf316ce590c24ca0a3005523125bde1c1fe7"
)

_UNSET = object()


class StepClock:
    """Deterministic monotonic clock: one fixed step per read."""

    def __init__(self, step: float = 0.001) -> None:
        self.value = 0.0
        self.step = step

    def __call__(self) -> float:
        self.value = round(self.value + self.step, 9)
        return self.value


def load_fixtures() -> tuple[object, MetricDefinition]:
    return load_corpus(CORPUS_PATH), load_metric_definition(METRIC_PATH)


def build_ledger(tmp_path: Path) -> tuple[EvidenceService, GateService]:
    store = RecordStore(tmp_path / "benchmark.sqlite3")
    evidence = EvidenceService(store)
    return evidence, GateService(evidence, store)


def build_runtime(
    tmp_path: Path,
    *,
    budget: ResourceBudget | None = None,
    materials=_UNSET,
    gate=_UNSET,
    admission=_UNSET,
    agent=None,
    clock=None,
    report_id: str = "benchmark-report",
    limitations=(),
) -> TrustBenchmarkRuntime:
    corpus, definition = load_fixtures()
    evidence, gates = build_ledger(tmp_path)
    return TrustBenchmarkRuntime(
        corpus=corpus,
        metric_definition=definition,
        agent=agent or RecordedAgent(),
        budget=budget
        or ResourceBudget(
            max_calls=500,
            single_call_timeout_seconds=30.0,
            max_wall_clock_seconds=600.0,
        ),
        materials=None if materials is _UNSET else materials,
        admission=EvidenceLedgerAdmission(evidence) if admission is _UNSET else admission,
        gate=gates if gate is _UNSET else gate,
        report_id=report_id,
        limitations=limitations,
        clock=clock or StepClock(),
    )


def run_all(tmp_path: Path, **kwargs):
    return build_runtime(tmp_path, **kwargs).run()


def condition(run, name: BenchmarkCondition):
    return next(item for item in run.report.conditions if item.condition is name)


def with_materials(tmp_path: Path, **kwargs):
    kwargs.setdefault("materials", FixtureMaterialsProvider())
    return run_all(tmp_path, **kwargs)


# ---------------------------------------------------------------------------
# The three conditions actually execute
# ---------------------------------------------------------------------------


def test_all_three_conditions_execute_over_the_frozen_corpus(tmp_path: Path):
    run = with_materials(tmp_path)
    counts = {item.condition: item.cases for item in run.report.conditions}
    assert counts == {
        BenchmarkCondition.BARE_LLM: FROZEN_CASE_COUNT,
        BenchmarkCondition.GATE_OFF: FROZEN_CASE_COUNT,
        BenchmarkCondition.GATE_ON: FROZEN_CASE_COUNT,
    }
    assert len(run.receipt.case_receipts) == 3 * FROZEN_CASE_COUNT
    assert run.report.status is BenchmarkRunStatus.COMPLETED


def test_governance_on_matches_every_frozen_label(tmp_path: Path):
    run = with_materials(tmp_path)
    gate_on = [
        item
        for item in run.receipt.case_receipts
        if item.condition is BenchmarkCondition.GATE_ON
    ]
    mismatched = [
        (item.case_id, item.expected_outcome.value, item.observed_outcome)
        for item in gate_on
        if item.observed_outcome is not item.expected_outcome
    ]
    assert mismatched == []
    metrics = run.report.mechanism_metrics
    assert metrics["fail_closed_block_rate"] == 100.0
    assert metrics["false_passes"] == 0.0
    assert metrics["false_blocks"] == 0.0
    assert metrics["mechanism_safety_score"] == 100.0
    assert metrics["expected_accepts"] == FROZEN_GATE_ON_ACCEPTED


def test_gate_status_is_observed_and_reported_per_cell(tmp_path: Path):
    run = with_materials(tmp_path)
    gate_on = {
        item.case_id: item
        for item in run.receipt.case_receipts
        if item.condition is BenchmarkCondition.GATE_ON
    }
    assert gate_on["case-001"].observed_gate is not None
    assert gate_on["case-001"].gate_matched is True
    assert gate_on["case-018"].observed_gate.value == "revise"
    assert gate_on["case-023"].observed_gate.value == "interrupt"
    assert gate_on["case-024"].observed_gate.value == "deny"
    # A pass from the gate is not enough on its own; governance-on also needs a
    # verified section, which is what blocks case-015..017.
    assert gate_on["case-015"].observed_gate.value == "pass"
    assert gate_on["case-015"].status is CaseStatus.BLOCKED
    # Gate off records no gate verdict at all and blocks nothing.
    gate_off = {
        item.case_id: item
        for item in run.receipt.case_receipts
        if item.condition is BenchmarkCondition.GATE_OFF
    }
    assert gate_off["case-018"].observed_gate is None
    assert gate_off["case-018"].status is CaseStatus.COMPLETED
    assert gate_off["case-018"].validation_verdict is not None


def test_the_only_thing_that_changes_is_enforcement(tmp_path: Path):
    run = with_materials(tmp_path)
    bare = condition(run, BenchmarkCondition.BARE_LLM)
    off = condition(run, BenchmarkCondition.GATE_OFF)
    on = condition(run, BenchmarkCondition.GATE_ON)

    # Same frozen drafts, so the draft-level ratio is identical for the two
    # conditions that retrieve material.
    assert off.hallucination_ratio == FROZEN_DRAFT_HALLUCINATION
    assert on.hallucination_ratio == FROZEN_DRAFT_HALLUCINATION
    assert off.evidence_binding_rate == FROZEN_BINDING_RATE
    assert on.evidence_binding_rate == FROZEN_BINDING_RATE

    # The baseline retrieves nothing, so nothing can be bound.
    assert bare.hallucination_ratio == 1.0
    assert bare.evidence_binding_rate == 0.0
    assert bare.accepted_hallucination_ratio == 1.0
    assert bare.score == 0.0

    # Governance-on accepts none of the unsupported content.
    assert off.accepted_hallucination_ratio == FROZEN_DRAFT_HALLUCINATION
    assert on.accepted_hallucination_ratio == 0.0
    assert on.score == 100.0
    assert bare.score < off.score < on.score
    assert on.acceptance_rate == pytest.approx(FROZEN_GATE_ON_ACCEPTED / FROZEN_CASE_COUNT)


def test_bare_llm_never_retrieves_material(tmp_path: Path):
    counter = CountingMaterials()
    run = with_materials(tmp_path, materials=counter)
    assert counter.calls, "gate_off and gate_on must retrieve"
    assert all(not scope.startswith("bare_llm:") for scope in counter.calls)
    assert len(counter.calls) == 2 * FROZEN_CASE_COUNT
    bare = [
        item
        for item in run.receipt.case_receipts
        if item.condition is BenchmarkCondition.BARE_LLM
    ]
    assert all(item.materials_status is None for item in bare)
    assert all(item.material_count == 0 for item in bare)
    assert all(item.evidence_count == 0 for item in bare)


class CountingMaterials:
    name = "counting-materials"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def materials(self, task, *, project_id: str, run_id: str, scope: str) -> MaterialsOutcome:
        self.calls.append(scope)
        return MaterialsOutcome()


class CountingAgent:
    name = "counting-agent"

    def __init__(self) -> None:
        self.calls = 0

    def draft(self, task: BenchmarkTask) -> AgentDraft:
        self.calls += 1
        return AgentDraft(
            body=task.body,
            title=task.title,
            claims=task.claims,
            claim_evidence_map=task.claim_evidence_map,
        )


class SlowMaterials:
    """Advances the shared clock so one call blows the soft per-call limit."""

    name = "slow-materials"

    def __init__(self, clock: StepClock, advance: float) -> None:
        self.clock = clock
        self.advance = advance
        self.calls = 0

    def materials(self, task, *, project_id: str, run_id: str, scope: str) -> MaterialsOutcome:
        self.calls += 1
        self.clock.value += self.advance
        return MaterialsOutcome()


# ---------------------------------------------------------------------------
# Budget and stop conditions
# ---------------------------------------------------------------------------


def test_hard_call_cap_denies_before_the_call_is_issued(tmp_path: Path):
    agent = CountingAgent()
    run = build_runtime(
        tmp_path,
        budget=ResourceBudget(
            max_calls=2, single_call_timeout_seconds=30.0, max_wall_clock_seconds=600.0
        ),
        agent=agent,
    ).run([BenchmarkCondition.BARE_LLM])

    assert agent.calls == 2, "the guarded callable must not run past the cap"
    assert run.receipt.usage.calls_used == 2
    assert run.receipt.usage.calls_denied == FROZEN_CASE_COUNT - 2
    assert run.receipt.usage.stop_reason is BenchmarkStopReason.CALL_BUDGET_EXHAUSTED
    assert run.report.status is BenchmarkRunStatus.BUDGET_EXHAUSTED
    denied = [item for item in run.receipt.case_receipts if item.status is CaseStatus.DENIED]
    assert len(denied) == FROZEN_CASE_COUNT - 2
    assert all(item.accepted is False for item in denied)
    assert all(item.observed_outcome is CaseOutcome.BLOCKED for item in denied)
    assert run.report.warnings


def test_wall_clock_stop_condition_is_recorded(tmp_path: Path):
    clock = StepClock(step=0.01)
    run = build_runtime(
        tmp_path,
        budget=ResourceBudget(
            max_calls=1_000, single_call_timeout_seconds=30.0, max_wall_clock_seconds=0.05
        ),
        clock=clock,
    ).run([BenchmarkCondition.BARE_LLM])
    assert run.receipt.usage.stop_reason is BenchmarkStopReason.WALL_CLOCK_EXHAUSTED
    assert run.report.status is BenchmarkRunStatus.BUDGET_EXHAUSTED
    assert run.receipt.usage.calls_denied > 0


def test_single_call_timeout_interrupts_and_routes_to_recovery(tmp_path: Path):
    clock = StepClock(step=0.001)
    slow = SlowMaterials(clock, advance=0.5)
    run = build_runtime(
        tmp_path,
        budget=ResourceBudget(
            max_calls=1_000, single_call_timeout_seconds=0.05, max_wall_clock_seconds=1_000.0
        ),
        materials=slow,
        clock=clock,
    ).run([BenchmarkCondition.GATE_OFF])

    assert slow.calls == FROZEN_CASE_COUNT
    summary = condition(run, BenchmarkCondition.GATE_OFF)
    assert summary.interrupted == FROZEN_CASE_COUNT
    assert summary.scored == 0
    # A run that measured nothing must not present itself as a perfect score.
    assert summary.score is None
    assert run.report.status is BenchmarkRunStatus.INTERRUPTED
    assert run.receipt.usage.calls_interrupted == FROZEN_CASE_COUNT
    assert run.receipt.usage.stop_reason is BenchmarkStopReason.NONE
    assert any("soft per-call limit" in item for item in run.report.warnings)
    assert any("no scored cells" in item for item in run.report.warnings)


def test_budget_accounting_is_written_into_the_receipt(tmp_path: Path):
    run = with_materials(tmp_path)
    usage = run.receipt.usage
    assert isinstance(usage, BudgetUsage)
    assert usage.calls_used == FROZEN_CALLS
    assert usage.calls_denied == 0
    assert usage.calls_interrupted == 0
    assert usage.wall_clock_seconds > 0
    assert run.receipt.budget.max_calls == 500
    assert run.receipt.budget.single_call_timeout_seconds == 30.0
    assert sum(item.calls for item in run.receipt.case_receipts) == usage.calls_used


def test_declared_limitations_are_opt_in_and_reach_the_report(tmp_path: Path):
    """A caller-declared limitation must show up verbatim, and only when declared.

    ``--live-retrieval`` uses this channel: a live run cannot bind the frozen
    corpus, so its ratios are structurally 1.0 / 0.0 and the report has to say so
    instead of letting a bare score read like a measurement.
    """

    marker = "live retrieval cannot bind the frozen corpus"

    clean = with_materials(tmp_path)
    assert not any(marker in item for item in clean.report.warnings)

    declared = build_runtime(tmp_path, limitations=[marker]).run(
        [BenchmarkCondition.GATE_OFF]
    )
    assert marker in declared.report.warnings
    assert declared.receipt.notes == [marker]
    # Declaring a limitation must not mask the run's own status.
    assert declared.report.status is BenchmarkRunStatus.COMPLETED


def test_call_budget_guard_is_usable_on_its_own():
    calls: list[str] = []
    budget = CallBudget(ResourceBudget(max_calls=1), clock=StepClock())
    assert budget.call(calls.append, "first") is None
    assert calls == ["first"]
    with pytest.raises(BenchmarkBudgetExceeded) as excinfo:
        budget.call(calls.append, "second")
    assert "budget exhausted" in str(excinfo.value)
    assert budget.usage.calls_used == 1
    assert budget.usage.calls_denied == 1
    assert budget.exhausted
    assert calls == ["first"]


# ---------------------------------------------------------------------------
# The run receipt is its own contract
# ---------------------------------------------------------------------------


def test_run_receipt_is_not_an_a4_capability_receipt(tmp_path: Path):
    run = with_materials(tmp_path)
    payload = run.receipt.model_dump(mode="json")
    for forbidden in (
        "capability",
        "adapter_kind",
        "adapter_version",
        "trust_tier",
        "request_fingerprint",
        "candidate_count",
        "candidates_admissible",
    ):
        assert forbidden not in payload
    for required in (
        "run_id",
        "budget",
        "usage",
        "case_receipts",
        "corpus_digest",
        "metric_definition_digest",
    ):
        assert required in payload


def test_receipt_indexes_cells_by_case_and_condition(tmp_path: Path):
    run = with_materials(tmp_path)
    cell = run.receipt.receipt_for("case-001", BenchmarkCondition.GATE_ON)
    assert cell is not None
    assert cell.expected_outcome is CaseOutcome.ACCEPTED
    assert run.receipt.receipt_for("case-001", BenchmarkCondition.BARE_LLM) is not None
    assert run.receipt.receipt_for("nope", BenchmarkCondition.GATE_ON) is None


# ---------------------------------------------------------------------------
# Report artifact
# ---------------------------------------------------------------------------


def test_report_artifact_round_trips_and_matches_the_receipt(tmp_path: Path):
    run = with_materials(tmp_path)
    target = run.write_report(tmp_path / "reports" / "benchmark-report.json")
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["primary_metric"] == "hallucination_ratio"
    assert payload["primary_metric_direction"] == "lower_is_better"
    assert payload["corpus_id"] == run.receipt.corpus_id
    assert payload["corpus_digest"] == run.receipt.corpus_digest
    assert payload["metric_definition_digest"] == run.receipt.metric_definition_digest
    assert payload["usage"] == run.receipt.usage.model_dump(mode="json")
    assert payload["status"] == "completed"
    assert len(payload["conditions"]) == 3
    assert payload["mechanism_metrics"]["mechanism_safety_score"] == 100.0
    assert payload == run.report.as_dict()


def test_a_second_identical_run_reproduces_the_report(tmp_path: Path):
    first = with_materials(tmp_path / "a")
    second = with_materials(tmp_path / "b")
    left = first.report.as_dict()
    right = second.report.as_dict()
    left.pop("generated_at")
    right.pop("generated_at")
    assert left == right


# ---------------------------------------------------------------------------
# Fail-closed loading of the frozen inputs
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, payload: object, name: str = "corpus.json") -> Path:
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _valid_case() -> dict:
    return {
        "case_id": "case-x",
        "question": "Does it hold?",
        "body": "## Objective\nx",
        "risk_level": "L2",
        "expected_gate": "pass",
        "expected_outcome": "accepted",
        "claims": ["claim"],
        "claim_evidence_map": {"claim": ["ev-x"]},
        "materials": [
            {
                "evidence_id": "ev-x",
                "independent_source": "openalex:W1",
                "claim": "material",
                "grade": "E2",
            }
        ],
    }


def _corpus(case: dict) -> dict:
    return {"corpus_id": "c", "version": "1", "cases": [case]}


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda case: case.pop("case_id"), id="missing-case-id"),
        pytest.param(lambda case: case.update(risk_level="L9"), id="bad-risk-level"),
        pytest.param(lambda case: case.update(expected_gate="maybe"), id="bad-expected-gate"),
        pytest.param(lambda case: case.update(expected_outcome="maybe"), id="bad-outcome"),
        pytest.param(lambda case: case.update(body="   "), id="blank-body"),
        pytest.param(lambda case: case.update(question=""), id="blank-question"),
        pytest.param(lambda case: case.update(claim_evidence_map=[]), id="map-not-object"),
        pytest.param(lambda case: case.update(materials=[1, 2]), id="material-not-object"),
        pytest.param(
            lambda case: case.update(
                materials=[{"evidence_id": "ev-x", "independent_source": "", "claim": "c"}]
            ),
            id="blank-independent-source",
        ),
        pytest.param(lambda case: case.update(metadata="nope"), id="metadata-not-object"),
    ],
)
def test_corpus_loader_rejects_malformed_cases(tmp_path: Path, mutate):
    case = _valid_case()
    mutate(case)
    with pytest.raises(ValueError):
        load_corpus(_write(tmp_path, _corpus(case)))


def test_corpus_loader_rejects_structural_damage(tmp_path: Path):
    with pytest.raises(ValueError):
        load_corpus(tmp_path / "missing.json")
    with pytest.raises(ValueError):
        load_corpus(_write(tmp_path, [1, 2, 3]))
    with pytest.raises(ValueError):
        load_corpus(_write(tmp_path, {"corpus_id": "c", "version": "1", "cases": []}))
    with pytest.raises(ValueError):
        load_corpus(_write(tmp_path, {"version": "1", "cases": [_valid_case()]}))
    case = _valid_case()
    with pytest.raises(ValueError):
        load_corpus(_write(tmp_path, _corpus(case) | {"cases": [case, dict(case)]}))


def test_corpus_loader_accepts_a_minimal_well_formed_case(tmp_path: Path):
    corpus = load_corpus(_write(tmp_path, _corpus(_valid_case())))
    assert corpus.corpus_id == "c"
    assert len(corpus.digest) == 64
    assert corpus.case("case-x").materials[0].grade == "E2"


def test_corpus_digest_tracks_content(tmp_path: Path):
    first = load_corpus(_write(tmp_path / "a", _corpus(_valid_case())))
    second = load_corpus(_write(tmp_path / "b", _corpus(_valid_case())))
    assert first.digest == second.digest
    changed = _valid_case()
    changed["question"] = "Does it still hold?"
    assert load_corpus(_write(tmp_path / "c", _corpus(changed))).digest != first.digest


def test_metric_definition_must_be_frozen_and_well_formed(tmp_path: Path):
    payload = json.loads(METRIC_PATH.read_text(encoding="utf-8"))
    assert load_metric_definition(METRIC_PATH).definition_version == "1.1"
    with pytest.raises(ValueError):
        load_metric_definition(tmp_path / "missing.json")
    with pytest.raises(ValueError):
        load_metric_definition(_write(tmp_path, [1], "metric.json"))
    with pytest.raises(ValueError):
        load_metric_definition(_write(tmp_path, {"frozen": True}, "metric.json"))
    thawed = dict(payload) | {"frozen": False}
    with pytest.raises(ValueError) as excinfo:
        load_metric_definition(_write(tmp_path, thawed, "metric.json"))
    assert "frozen" in str(excinfo.value)


def test_metric_definition_digest_tracks_content(tmp_path: Path):
    payload = json.loads(METRIC_PATH.read_text(encoding="utf-8"))
    baseline = load_metric_definition(METRIC_PATH).digest()
    changed = dict(payload) | {"formula": "something else"}
    assert load_metric_definition(_write(tmp_path, changed, "metric.json")).digest() != baseline


def test_hallucination_ratio_is_frozen_and_fails_closed():
    assert hallucination_ratio(unsupported_claims=0, total_claims=0) == 0.0
    assert hallucination_ratio(unsupported_claims=0, total_claims=4) == 0.0
    assert hallucination_ratio(unsupported_claims=1, total_claims=3) == pytest.approx(1 / 3)
    assert hallucination_ratio(unsupported_claims=4, total_claims=4) == 1.0
    for unsupported, total in ((-1, 2), (3, 2), (1, -1)):
        with pytest.raises(ValueError):
            hallucination_ratio(unsupported_claims=unsupported, total_claims=total)


# ---------------------------------------------------------------------------
# Runtime guards
# ---------------------------------------------------------------------------


def test_gate_on_requires_a_gate_hook(tmp_path: Path):
    runtime = build_runtime(tmp_path, materials=FixtureMaterialsProvider(), gate=None)
    with pytest.raises(ValueError) as excinfo:
        runtime.run([BenchmarkCondition.GATE_ON])
    assert "gate hook" in str(excinfo.value)


def test_conditions_must_be_declared_in_the_frozen_definition(tmp_path: Path):
    corpus, definition = load_fixtures()
    thawed = definition.model_copy(update={"conditions": ["bare_llm"]})
    evidence, gates = build_ledger(tmp_path)
    runtime = TrustBenchmarkRuntime(
        corpus=corpus,
        metric_definition=thawed,
        materials=FixtureMaterialsProvider(),
        admission=EvidenceLedgerAdmission(evidence),
        gate=gates,
        clock=StepClock(),
    )
    with pytest.raises(ValueError) as excinfo:
        runtime.run([BenchmarkCondition.GATE_ON])
    assert "not declared" in str(excinfo.value)


def test_empty_and_unknown_conditions_are_refused(tmp_path: Path):
    runtime = build_runtime(tmp_path, materials=FixtureMaterialsProvider())
    with pytest.raises(ValueError):
        runtime.run([])
    with pytest.raises(ValueError):
        runtime.run(["gate_on_mode"])
    assert DEFAULT_CONDITIONS == (
        BenchmarkCondition.BARE_LLM,
        BenchmarkCondition.GATE_OFF,
        BenchmarkCondition.GATE_ON,
    )


def test_a_runtime_instance_runs_at_most_once(tmp_path: Path):
    runtime = build_runtime(tmp_path, materials=FixtureMaterialsProvider())
    runtime.run([BenchmarkCondition.BARE_LLM])
    with pytest.raises(RuntimeError) as excinfo:
        runtime.run([BenchmarkCondition.BARE_LLM])
    assert "already ran" in str(excinfo.value)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_calls": 0},
        {"single_call_timeout_seconds": 0},
        {"max_wall_clock_seconds": -1},
    ],
)
def test_resource_budget_rejects_nonsense(kwargs):
    with pytest.raises(ValueError):
        ResourceBudget(**kwargs)


# ---------------------------------------------------------------------------
# D-F8-01 and D-S3-01 alignment
# ---------------------------------------------------------------------------


def test_completed_empty_material_is_a_known_outcome(tmp_path: Path):
    run = with_materials(tmp_path)
    for name in (BenchmarkCondition.GATE_OFF, BenchmarkCondition.GATE_ON):
        cell = run.receipt.receipt_for("case-020", name)
        assert cell is not None
        assert cell.materials_status == "completed"
        assert cell.material_count == 0
        assert cell.evidence_count == 0
        assert not any("provider outcome is unknown" in item for item in cell.diagnostics)
    # Gate off records the deterministic empty result as a scored cell; only
    # governance-on turns the missing material into a block.
    assert run.receipt.receipt_for(
        "case-020", BenchmarkCondition.GATE_OFF
    ).status is CaseStatus.COMPLETED
    assert run.receipt.receipt_for(
        "case-020", BenchmarkCondition.GATE_ON
    ).status is CaseStatus.BLOCKED


class StubAdapter:
    """Minimal candidate-only adapter for the registry path."""

    def __init__(self, *, status=None, candidates=()):
        self._status = status or CapabilityReceiptStatus.COMPLETED
        self._candidates = list(candidates)

    def invoke(self, request, context) -> CapabilityAdapterResult:
        for candidate in self._candidates:
            context.emit_candidate(candidate)
        return CapabilityAdapterResult(status=self._status)

    def manifest(self) -> CapabilityManifest:
        return CapabilityManifest(
            name="stub_search",
            kind="native",
            version="1.0",
            inputs=["query"],
            outputs=["evidence_candidate"],
            evidence_mode="candidate_only",
            network_required=False,
        )


def _candidate() -> EvidenceCandidate:
    return EvidenceCandidate(
        project_id="benchmark",
        claim="bibliographic record exists",
        independent_source="openalex:W1",
        title="A retrieved paper",
    )


def _registry_with(adapter) -> CapabilityRegistry:
    registry = CapabilityRegistry(allow_network=True)
    registry.register(
        adapter.manifest(),
        adapter,
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
        kind=CapabilityKind.NATIVE,
        network_required=False,
    )
    return registry


def test_registry_provider_returns_only_admissible_candidates():
    task = BenchmarkTask(case_id="case-r", question="q", title="t", body="## Objective\nx")

    ok = RegistryMaterialsProvider(
        _registry_with(StubAdapter(candidates=[_candidate()])), "stub_search"
    )
    outcome = ok.materials(task, project_id="benchmark", run_id="r", scope="s")
    assert outcome.status == "completed"
    assert outcome.admissible is True
    assert len(outcome.candidates) == 1

    limited = RegistryMaterialsProvider(
        _registry_with(StubAdapter(status=CapabilityReceiptStatus.FAILED)), "stub_search"
    )
    refused = limited.materials(task, project_id="benchmark", run_id="r", scope="s")
    assert refused.status == "failed"
    assert refused.admissible is False
    assert refused.candidates == ()


def test_registry_provider_is_reachable_through_the_runtime_budget(tmp_path: Path):
    provider = RegistryMaterialsProvider(
        _registry_with(StubAdapter(candidates=[_candidate()])), "stub_search"
    )
    agent = CountingAgent()
    run = build_runtime(tmp_path, materials=provider, agent=agent).run(
        [BenchmarkCondition.GATE_OFF]
    )
    # one retrieval plus one draft per case, all through the frozen budget
    assert agent.calls == FROZEN_CASE_COUNT
    assert run.receipt.usage.calls_used == 2 * FROZEN_CASE_COUNT
    summary = condition(run, BenchmarkCondition.GATE_OFF)
    assert summary.cases == FROZEN_CASE_COUNT
    assert summary.scored == FROZEN_CASE_COUNT


def test_registry_provider_rejects_a_non_positive_limit():
    with pytest.raises(ValueError):
        RegistryMaterialsProvider(_registry_with(StubAdapter()), "stub_search", limit=0)


# ---------------------------------------------------------------------------
# Admission
# ---------------------------------------------------------------------------


def test_ledger_admission_classifies_and_is_idempotent(tmp_path: Path):
    evidence, _ = build_ledger(tmp_path)
    admission = EvidenceLedgerAdmission(evidence)
    candidate = EvidenceCandidate(
        evidence_id="ev-keep",
        project_id="benchmark",
        claim="material claim",
        independent_source="openalex:W1",
        locator="benchmark corpus material",
        metadata={"benchmark": {"grade": "E3", "evidence_type": "paper"}},
    )
    first = admission.admit([candidate], project_id="benchmark")
    second = admission.admit([candidate], project_id="benchmark")
    assert first == second == ("ev-keep",)
    stored = evidence.get("ev-keep")
    assert stored is not None
    assert stored.grade is EvidenceGrade.E3
    assert stored.evidence_type is EvidenceType.PAPER
    # The candidate itself stays unclassified: the R005 boundary is intact.
    assert candidate.grade is None
    assert candidate.evidence_type is None


def test_corpus_label_admission_mints_ids_for_unlabelled_candidates():
    admission = CorpusLabelAdmission()
    first = admission.admit(
        [EvidenceCandidate(project_id="p", claim="c", independent_source="s")],
        project_id="p",
    )
    second = admission.admit(
        [
            EvidenceCandidate(project_id="p", claim="c", independent_source="s"),
            EvidenceCandidate(project_id="p", claim="c2", independent_source="s2"),
        ],
        project_id="p",
    )
    assert first == ("ev-0001",)
    assert second == ("ev-0002", "ev-0003")


def test_fixture_materials_leave_classification_to_admission():
    task = BenchmarkTask(
        case_id="case-m",
        question="q",
        title="t",
        body="## Objective\nx",
        materials=(
            BenchmarkMaterial(
                evidence_id="ev-m",
                independent_source="openalex:W1",
                claim="material",
                grade="E3",
                evidence_type="paper",
            ),
        ),
    )
    outcome = FixtureMaterialsProvider().materials(
        task, project_id="p", run_id="r", scope="s"
    )
    candidate = outcome.candidates[0]
    assert candidate.grade is None
    assert candidate.evidence_type is None
    assert candidate.evidence_id == "ev-m"
    assert candidate.metadata["benchmark"] == {"grade": "E3", "evidence_type": "paper"}


def test_fixture_materials_flag_an_empty_corpus_case():
    task = BenchmarkTask(case_id="case-e", question="q", title="t", body="## Objective\nx")
    outcome = FixtureMaterialsProvider().materials(
        task, project_id="p", run_id="r", scope="s"
    )
    assert outcome.candidates == ()
    assert outcome.status == "completed"
    assert any("deterministic empty" in item for item in outcome.diagnostics)


# ---------------------------------------------------------------------------
# A broken or slow step is a recorded cell, not a crashed run
# ---------------------------------------------------------------------------


class BrokenMaterials:
    name = "broken-materials"

    def materials(self, task, *, project_id: str, run_id: str, scope: str):
        raise RuntimeError("retrieval exploded")


class SlowAgent(CountingAgent):
    name = "slow-agent"

    def __init__(self, clock: StepClock, advance: float) -> None:
        super().__init__()
        self.clock = clock
        self.advance = advance

    def draft(self, task: BenchmarkTask) -> AgentDraft:
        self.calls += 1
        self.clock.value += self.advance
        return AgentDraft(
            body=task.body,
            title=task.title,
            claims=task.claims,
            claim_evidence_map=task.claim_evidence_map,
        )


class SlowGate:
    def __init__(self, clock: StepClock, advance: float) -> None:
        self.clock = clock
        self.advance = advance
        self.calls = 0

    def evaluate(self, request):
        # A slow step has to *return* for the soft limit to fire: the budget
        # checks the elapsed time only after the call comes back.  Raising here
        # would be classified as a broken step (FAILED), not an interruption.
        self.calls += 1
        self.clock.value += self.advance
        return GateDecision(
            project_id=request.project_id,
            operation=request.operation,
            status=GateStatus.PASS,
            risk_level=request.risk_level,
            score=0,
            independent_sources=0,
            reasons=["stub: intentionally slow"],
        )


class InadmissibleMaterials:
    name = "inadmissible-materials"

    def materials(self, task, *, project_id: str, run_id: str, scope: str) -> MaterialsOutcome:
        return MaterialsOutcome(
            status="failed",
            admissible=False,
            diagnostics=("stub: rate limited",),
        )


def test_a_broken_step_fails_only_its_own_cell(tmp_path: Path):
    run = build_runtime(tmp_path, materials=BrokenMaterials()).run(
        [BenchmarkCondition.GATE_OFF]
    )
    summary = condition(run, BenchmarkCondition.GATE_OFF)
    assert summary.failed == FROZEN_CASE_COUNT
    assert summary.scored == 0
    assert run.report.status is BenchmarkRunStatus.FAILED
    assert any("failed" in item for item in run.report.warnings)
    cell = run.receipt.receipt_for("case-001", BenchmarkCondition.GATE_OFF)
    assert cell.status is CaseStatus.FAILED
    assert cell.observed_outcome is None
    assert any("RuntimeError" in item for item in cell.diagnostics)


def test_a_slow_draft_interrupts_the_cell(tmp_path: Path):
    clock = StepClock(step=0.001)
    slow = SlowAgent(clock, advance=0.5)
    run = build_runtime(
        tmp_path,
        budget=ResourceBudget(
            max_calls=1_000, single_call_timeout_seconds=0.05, max_wall_clock_seconds=1_000.0
        ),
        agent=slow,
        clock=clock,
    ).run([BenchmarkCondition.BARE_LLM])
    summary = condition(run, BenchmarkCondition.BARE_LLM)
    assert summary.interrupted == FROZEN_CASE_COUNT
    assert slow.calls == FROZEN_CASE_COUNT
    assert run.report.status is BenchmarkRunStatus.INTERRUPTED
    cell = run.receipt.receipt_for("case-001", BenchmarkCondition.BARE_LLM)
    assert any("drafting" in item for item in cell.diagnostics)


def test_a_slow_gate_interrupts_the_cell(tmp_path: Path):
    clock = StepClock(step=0.001)
    slow_gate = SlowGate(clock, advance=0.5)
    run = build_runtime(
        tmp_path,
        budget=ResourceBudget(
            max_calls=1_000, single_call_timeout_seconds=0.05, max_wall_clock_seconds=1_000.0
        ),
        materials=FixtureMaterialsProvider(),
        gate=slow_gate,
        clock=clock,
    ).run([BenchmarkCondition.GATE_ON])
    summary = condition(run, BenchmarkCondition.GATE_ON)
    assert summary.interrupted == FROZEN_CASE_COUNT
    assert slow_gate.calls == FROZEN_CASE_COUNT
    cell = run.receipt.receipt_for("case-001", BenchmarkCondition.GATE_ON)
    assert any("gate" in item for item in cell.diagnostics)


def test_budget_can_run_out_during_retrieval(tmp_path: Path):
    counter = CountingMaterials()
    run = build_runtime(
        tmp_path,
        budget=ResourceBudget(
            max_calls=1, single_call_timeout_seconds=30.0, max_wall_clock_seconds=600.0
        ),
        materials=counter,
    ).run([BenchmarkCondition.GATE_OFF])
    assert len(counter.calls) == 1, "retrieval must stop at the cap"
    summary = condition(run, BenchmarkCondition.GATE_OFF)
    # case-001 spends the only call on retrieval and is then denied at drafting;
    # every later cell is denied before it can even retrieve.  Denials are
    # visible, not silent -- that is the point of a hard stop condition.
    assert summary.denied == FROZEN_CASE_COUNT
    assert run.receipt.usage.stop_reason is BenchmarkStopReason.CALL_BUDGET_EXHAUSTED
    first = run.receipt.receipt_for("case-001", BenchmarkCondition.GATE_OFF)
    assert first.status is CaseStatus.DENIED
    assert any("drafting" in item for item in first.diagnostics)
    dropped = run.receipt.receipt_for("case-002", BenchmarkCondition.GATE_OFF)
    assert dropped.status is CaseStatus.DENIED
    assert any("retrieval" in item for item in dropped.diagnostics)


def test_inadmissible_retrieval_contributes_no_material(tmp_path: Path):
    run = build_runtime(tmp_path, materials=InadmissibleMaterials()).run(
        [BenchmarkCondition.GATE_ON]
    )
    cell = run.receipt.receipt_for("case-001", BenchmarkCondition.GATE_ON)
    assert cell.material_count == 0
    assert cell.evidence_count == 0
    assert cell.materials_status == "failed"
    assert any("not admissible" in item for item in cell.diagnostics)


# ---------------------------------------------------------------------------
# Loader and index edge cases
# ---------------------------------------------------------------------------


def test_optional_case_lists_default_to_empty(tmp_path: Path):
    case = _valid_case()
    case.pop("claims")
    case.pop("materials")
    case.pop("claim_evidence_map")
    corpus = load_corpus(_write(tmp_path, _corpus(case)))
    task = corpus.case("case-x")
    assert task.claims == ()
    assert task.materials == ()
    assert task.claim_evidence_map == {}


def test_corpus_loader_rejects_a_non_object_case(tmp_path: Path):
    with pytest.raises(ValueError):
        load_corpus(_write(tmp_path, {"corpus_id": "c", "version": "1", "cases": [1]}))


def test_corpus_loader_rejects_a_non_list_claims_field(tmp_path: Path):
    case = _valid_case()
    case["claims"] = "not-a-list"
    with pytest.raises(ValueError):
        load_corpus(_write(tmp_path, _corpus(case)))


def test_corpus_case_lookup_fails_closed(tmp_path: Path):
    corpus = load_corpus(_write(tmp_path, _corpus(_valid_case())))
    with pytest.raises(KeyError):
        corpus.case("case-unknown")


def test_label_admission_keeps_an_existing_evidence_id():
    admission = CorpusLabelAdmission()
    admitted = admission.admit(
        [
            EvidenceCandidate(
                evidence_id="ev-labelled",
                project_id="p",
                claim="c",
                independent_source="s",
            ),
            EvidenceCandidate(project_id="p", claim="c2", independent_source="s2"),
        ],
        project_id="p",
    )
    assert admitted == ("ev-labelled", "ev-0001")


# ---------------------------------------------------------------------------
# The re-run command (scripts/benchmark_trust.py)
# ---------------------------------------------------------------------------

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "benchmark_trust.py"


def load_cli():
    """Import the script by path: ``scripts/`` is not an importable package."""

    spec = importlib.util.spec_from_file_location("benchmark_trust_cli", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_rerun_command_writes_the_committed_report(tmp_path: Path):
    cli = load_cli()
    out = tmp_path / "nested" / "benchmark-report.json"

    assert cli.main(["--report", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert [item["condition"] for item in payload["conditions"]] == [
        "bare_llm",
        "gate_off",
        "gate_on",
    ]
    # The report has to pin what it measured, or a later run is uncomparable.
    assert payload["corpus_digest"] == FROZEN_CORPUS_DIGEST
    assert payload["metric_definition_digest"] == FROZEN_METRIC_DEFINITION_DIGEST
    assert payload["primary_metric"] == "hallucination_ratio"
    assert payload["mechanism_metrics"]["mechanism_safety_score"] == 100.0
    by_condition = {item["condition"]: item for item in payload["conditions"]}
    assert by_condition["gate_on"]["accepted_hallucination_ratio"] == 0.0
    # Only the enforcement differs: gate off and gate on score the same drafts.
    assert (
        by_condition["gate_off"]["hallucination_ratio"]
        == by_condition["gate_on"]["hallucination_ratio"]
    )


def test_the_rerun_command_can_run_a_single_condition(tmp_path: Path):
    cli = load_cli()
    out = tmp_path / "report.json"

    assert cli.main(["--report", str(out), "--condition", "gate_on"]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [item["condition"] for item in payload["conditions"]] == ["gate_on"]
    assert payload["conditions"][0]["completed"] == FROZEN_GATE_ON_ACCEPTED


def test_the_rerun_command_fails_closed_when_the_budget_stops_it(tmp_path: Path):
    cli = load_cli()
    out = tmp_path / "report.json"

    # A run that hit a hard stop condition is not a clean comparison, so it must
    # not exit as though it were one -- but it still has to write the report.
    assert cli.main(["--report", str(out), "--max-calls", "1"]) == 1

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "budget_exhausted"
    assert payload["usage"]["stop_reason"] == "call_budget_exhausted"


def test_the_rerun_command_rejects_an_unknown_live_source(tmp_path: Path):
    cli = load_cli()

    with pytest.raises(SystemExit) as excinfo:
        cli.main(
            [
                "--report",
                str(tmp_path / "report.json"),
                "--live-retrieval",
                "--source",
                "not-a-source",
            ]
        )
    assert "not-a-source" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Metric semantics in the degenerate cases (owner integration, 2026-09-11)
#
# Adversarial review found that a condition which accepted nothing still scored
# 100.0, because an unaccepted cell contributes ``accepted_hallucination_ratio
# = 0.0`` and the roll-up averaged over *all* cells.  Blocking a cell therefore
# raised the score.  These tests pin the corrected semantics.
# ---------------------------------------------------------------------------


def _summarize(cells, condition=BenchmarkCondition.GATE_ON):
    runtime = TrustBenchmarkRuntime.__new__(TrustBenchmarkRuntime)
    return runtime._summarize(condition, cells)


def _mechanism_metrics(cells):
    runtime = TrustBenchmarkRuntime.__new__(TrustBenchmarkRuntime)
    return runtime._mechanism_metrics(cells)


def _cells(run, condition=BenchmarkCondition.GATE_ON):
    return [item for item in run.receipt.case_receipts if item.condition is condition]


def test_a_condition_that_accepted_nothing_scores_none(tmp_path: Path):
    """Blocking everything must not read as a perfect score.

    The live run under review reported ``acceptance_rate = 0.0`` next to
    ``score = 100.0``: with every cell unaccepted, the old roll-up averaged 24
    zeroes. There is no released content to score, so the answer is ``None``.
    """

    run = with_materials(tmp_path)
    blocked = [
        item.model_copy(
            update={
                "accepted": False,
                "status": CaseStatus.BLOCKED,
                "observed_outcome": CaseOutcome.BLOCKED,
            }
        )
        for item in _cells(run)
    ]
    summary = _summarize(blocked)
    assert summary.accepted == 0
    assert summary.acceptance_rate == 0.0
    assert summary.accepted_hallucination_ratio is None
    assert summary.score is None


def test_only_accepted_cells_shape_the_score(tmp_path: Path):
    """An unaccepted cell must not enter the score's mean.

    Twelve accepted cells at 0.5 and twelve blocked cells read as 0.5 -> 50.0.
    Averaging over all twenty-four instead (the reviewed behaviour) would fold
    the twelve blocked cells in as zeroes and report 75.0 -- i.e. blocking more
    cells would raise the score.
    """

    run = with_materials(tmp_path)
    cells = _cells(run)
    half = len(cells) // 2
    assert half > 0
    designed = [
        item.model_copy(
            update={
                "accepted": index < half,
                "status": CaseStatus.COMPLETED if index < half else CaseStatus.BLOCKED,
                "accepted_hallucination_ratio": 0.5 if index < half else 0.0,
            }
        )
        for index, item in enumerate(cells)
    ]

    summary = _summarize(designed)
    assert summary.accepted == half
    assert summary.accepted_hallucination_ratio == 0.5
    assert summary.score == 50.0


def test_fail_closed_rate_is_none_when_there_is_nothing_to_block(tmp_path: Path):
    """"Nothing needed blocking" is not "blocking was perfect"."""

    run = with_materials(tmp_path)
    all_accept = [
        item.model_copy(
            update={
                "expected_outcome": CaseOutcome.ACCEPTED,
                "observed_outcome": CaseOutcome.ACCEPTED,
                "accepted": True,
                "status": CaseStatus.COMPLETED,
            }
        )
        for item in _cells(run)
    ]
    metrics = _mechanism_metrics(all_accept)
    assert metrics["expected_blocks"] == 0.0
    assert metrics["fail_closed_block_rate"] is None
    # Here every cell was expected to be accepted, so the false-block
    # denominator is non-empty and 0.0 is a real measurement.
    assert metrics["false_block_rate"] == 0.0
    # The safety score already handles this case: nothing to miss, nothing to
    # falsely pass, so it is legitimately 100.
    assert metrics["mechanism_safety_score"] == 100.0

    all_block = [
        item.model_copy(
            update={
                "expected_outcome": CaseOutcome.BLOCKED,
                "observed_outcome": CaseOutcome.BLOCKED,
                "accepted": False,
                "status": CaseStatus.BLOCKED,
            }
        )
        for item in _cells(run)
    ]
    mirror = _mechanism_metrics(all_block)
    assert mirror["expected_accepts"] == 0.0
    assert mirror["false_block_rate"] is None
    assert mirror["fail_closed_block_rate"] == 100.0


def test_zero_claim_cells_are_reported(tmp_path: Path):
    """An empty draft scores 0.0 on a lower-is-better metric, so the count of
    such cells has to be visible in the roll-up rather than silently perfect."""

    run = with_materials(tmp_path)
    cells = [
        item.model_copy(update={"claims_total": 0, "unsupported_claims": []})
        for item in _cells(run)
    ]
    summary = _summarize(cells)
    assert summary.zero_claim_cells == len(cells)
    assert _summarize(_cells(run)).zero_claim_cells == 0


def test_the_adverse_ratio_refuses_a_nonzero_numerator_over_an_empty_denominator():
    assert _ratio(0, 0) == 0.0
    with pytest.raises(ValueError):
        _ratio(3, 0)


def test_the_live_limitations_cover_every_uninterpretable_metric():
    """Declaring only hall/bind left a reader free to read the collapsed
    mechanism metrics as a measured regression."""

    cli = load_cli()
    text = " ".join(cli.LIVE_RETRIEVAL_LIMITATIONS)
    for token in (
        "mechanism_safety_score",
        "false_block_rate",
        "score",
        "budget_exhausted",
    ):
        assert token in text
    assert cli.LIVE_RETRIEVAL_LIMITATIONS[0] == cli.LIVE_RETRIEVAL_LIMITATION


# ---------------------------------------------------------------------------
# Reserved cost schema (TASK-SPECS A5 计价衔接注记)
#
# A5 lands before the provider lane (O12), and the frozen spec requires *this*
# package to reserve the receipt's cost schema so the two ends can meet without
# a migration.  A reserved slot that defaulted to zero would read as "this run
# was free", so the slot stays ``None`` until a provider fills it.
# ---------------------------------------------------------------------------

TOKEN_SLOT_FIELDS = ("input", "output", "cache_read", "cache_write", "reasoning")
COST_SLOT_FIELDS = (
    "input",
    "output",
    "cache_read",
    "cache_write",
    "total",
    "currency",
    "model",
    "lane_id",
    "attempts",
    "price_source",
)


def test_the_reserved_cost_schema_mirrors_the_provider_lane():
    """Field names are the interface: drift here breaks O12 silently."""

    assert tuple(TokenUsageSlot.model_fields) == TOKEN_SLOT_FIELDS
    assert tuple(InvocationCostSlot.model_fields) == COST_SLOT_FIELDS


def test_unfilled_cost_slots_are_none_not_zero(tmp_path: Path):
    """An unmeasured slot must not be readable as a free run."""

    run = with_materials(tmp_path)
    assert run.receipt.usage.cost is None
    assert run.receipt.usage.tokens is None
    assert all(item.cost is None for item in run.receipt.case_receipts)
    assert all(item.tokens is None for item in run.receipt.case_receipts)
    # The declaration goes in the report's warnings, not the receipt's notes:
    # ``notes`` is the caller's channel and stays exactly the declared
    # limitations (see test_declared_limitations_are_opt_in_and_reach_the_report).
    assert not any("carry no cost" in note for note in run.receipt.notes)
    assert any("carry no cost" in warning for warning in run.report.warnings)


def test_the_cost_slot_reaches_the_report_artifact(tmp_path: Path):
    """The committed report has to expose the slot, not just the receipt."""

    run = with_materials(tmp_path)
    payload = run.report.as_dict()
    assert "cost" in payload["usage"] and payload["usage"]["cost"] is None
    assert "cost" in run.receipt.case_receipts[0].model_dump()


def test_a_provider_filled_slot_round_trips():
    """O12 must be able to populate the slot and have it survive serialization."""

    cost = InvocationCostSlot(
        input=0.0012,
        output=0.0034,
        total=0.0046,
        model="deepseek-v4-flash",
        lane_id="chat",
        attempts=2,
        price_source="catalog 2026-09-11",
    )
    usage = BudgetUsage(
        calls_used=3, tokens=TokenUsageSlot(input=11, output=7), cost=cost
    )
    restored = BudgetUsage.model_validate_json(usage.model_dump_json())
    assert restored == usage
    assert restored.cost is not None and restored.cost.total == 0.0046
    assert restored.tokens is not None and restored.tokens.input == 11
