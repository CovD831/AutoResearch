"""The closure requirement is a three-state fact, not a boolean.

Before this contract, ``GateRequest.work_closed_loop`` was a ``bool`` and
``review_manuscript`` derived it as ``not manuscript.unresolved_gaps``. With the
experiment lane not enabled there is never experiment-graded evidence, so the L3
gate's closure requirement *always* failed: the run parked in ``WAITING_EVIDENCE``
and could never reach the release gate. A pipeline that was merely **scoped** to
literature evidence was reported as **broken**, and there was no value a caller
could pass to say "this stage is not enabled yet" — ``False`` meant both
"not enabled" and "ran and stayed open".

These tests pin the distinction:

* the scoped pipeline reaches the human release gate (this is the one that fails
  on the pre-change code, with a *criterion* failure — see the work-package
  L3/HANDOFF for the recorded pre-fix run);
* an actually-open loop still blocks, so the tri-state cannot be used as a bypass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autoresearch.application import AutoResearchApplication
from autoresearch.contracts import (
    LifecycleState,
    LoopClosure,
    PaperRecord,
    ProjectCreate,
    RunRequest,
    RunStatus,
)

IDEA = "Evaluate evidence gates for research agents."

#: Three independent sources so the L3 gate clears its score and source count on
#: their own terms — what is under test is the closure requirement, not the rest
#: of the threshold.
SEED_PAPERS = [
    PaperRecord(
        project_id="demo",
        title=title,
        abstract=(
            "Evidence admission gates require traceable identifiers and provenance. "
            "Metric definitions must be registered before results are reported so "
            "that every number can be traced to a supporting evidence record."
        ),
        year=year,
        source=source,
        source_record_id=f"seed-{index}",
        doi=f"10.1000/seed{index}",
    )
    for index, (title, year, source) in enumerate(
        [
            ("Evidence gates for automated research", 2024, "openalex"),
            ("Provenance-aware manuscript assembly", 2023, "semantic_scholar"),
            ("Traceable metric definitions in agent pipelines", 2024, "crossref"),
        ],
        start=1,
    )
]


@pytest.fixture
def seeded_runtime(tmp_path: Path):
    """A runtime whose project has an idea and citable seed papers.

    Offline by construction: the point is the closure gate, not retrieval.
    """
    repository_root = Path(__file__).resolve().parents[1]
    from autoresearch.config import Settings

    settings = Settings(
        _env_file=None,
        LLM_PROVIDER="offline",
        AUTORESEARCH_DATA_DIR=tmp_path / "var",
        AUTORESEARCH_DB_PATH=tmp_path / "var" / "autoresearch.sqlite3",
        AUTORESEARCH_CHECKPOINT_PATH=tmp_path / "var" / "checkpoints.sqlite3",
        AUTORESEARCH_PROJECTS_DIR=tmp_path / "paper-projects",
        AUTORESEARCH_TEMPLATE_DIR=repository_root / "paper-projects" / "_template",
        AUTORESEARCH_NETWORK_ENABLED=False,
    )
    application = AutoResearchApplication(settings)
    application.create_project(ProjectCreate(project_id="demo", title="Demo", idea=IDEA))
    try:
        yield application
    finally:
        application.close()


def test_a_scoped_run_reaches_the_release_gate(seeded_runtime):
    """With the experiment lane not enabled, the run still reaches L4 approval.

    This is the criterion test. On the pre-change code the L3 decision came back
    ``REVISE`` ("required work and result lineage are not closed loop"), the run
    parked in ``WAITING_EVIDENCE``, and the assertion below failed on
    ``lifecycle_state`` — no experiment stage was ever going to close that loop,
    so the pipeline could not be exercised end to end at all.
    """
    result = seeded_runtime.run(
        RunRequest(project_id="demo", idea=IDEA, seed_papers=SEED_PAPERS, request_release=True)
    )
    state = result["state"]

    assert state["lifecycle_state"] in {
        LifecycleState.RELEASE_PENDING,
        LifecycleState.RELEASE_PENDING.value,
    }, f"run did not reach the release gate; ended at {state['lifecycle_state']!r}"
    assert not state["blockers"], state["blockers"]
    # Parked at the human gate: not finished, not failed.
    assert result["status"] in {
        RunStatus.INTERRUPTED,
        RunStatus.INTERRUPTED.value,
    }, f"expected the run to be parked at L4, got {result['status']!r}"

    # The human gate is what stops it, and it is the *only* thing that stops it.
    assert any(
        item.get("type") == "human_release_approval" for item in result["interrupts"]
    ), result["interrupts"]


def test_a_scoped_pass_is_recorded_as_scoped(seeded_runtime):
    """Passing must not read like a verified closure.

    The whole risk of the tri-state is that "not applicable" becomes a silent
    bypass. The decision therefore carries the state *and* restates the scope, so
    the ledger distinguishes "we verified a result lineage" from "no result
    lineage was in scope".
    """
    result = seeded_runtime.run(
        RunRequest(project_id="demo", idea=IDEA, seed_papers=SEED_PAPERS, request_release=True)
    )
    state = result["state"]

    decisions = [
        seeded_runtime.store.get("gate_decision", decision_id)
        for decision_id in state["gate_decision_ids"]
    ]
    closure_decisions = [
        decision
        for decision in decisions
        if decision and decision.get("operation") == "mark_manuscript_evidence_complete"
    ]
    assert closure_decisions, "the closure-requiring gate never ran"

    decision = closure_decisions[-1]
    assert decision["status"] == "pass"
    assert decision["loop_closure"] == LoopClosure.NOT_APPLICABLE.value, (
        "a scoped pass must not be recorded as a closed loop"
    )
    assert any(
        "not applicable" in reason for reason in decision["reasons"]
    ), decision["reasons"]


def test_an_open_loop_still_blocks(seeded_runtime):
    """``OPEN`` is the only value that blocks — the tri-state is not a bypass.

    This one passes before *and* after the change (a ``False`` previously blocked
    too); it is kept as a regression guard so the new third state cannot quietly
    widen into "anything that is not CLOSED is fine".
    """
    from autoresearch.contracts import GateRequest, RiskLevel

    evidence_ids = [
        item["evidence_id"]
        for item in seeded_runtime.evidence.list("demo", valid_only=True)
    ]
    request = GateRequest(
        project_id="demo",
        operation="mark_manuscript_evidence_complete",
        risk_level=RiskLevel.L3,
        claim="The manuscript is evidence-complete and its result lineage is closed.",
        evidence_ids=evidence_ids,
        loop_closure=LoopClosure.OPEN,
    )
    decision = seeded_runtime.gates.evaluate(request)

    assert decision.status.value == "revise"
    assert any("not closed loop" in reason for reason in decision.reasons), decision.reasons
