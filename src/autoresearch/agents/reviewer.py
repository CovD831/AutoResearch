from __future__ import annotations

from autoresearch.agents.base import WorkflowState, single_node_subgraph
from autoresearch.contracts import (
    AgentId,
    GateRequest,
    GateStatus,
    HandoffEnvelope,
    LifecycleState,
    Manuscript,
    ResearchState,
    ReviewReport,
    RiskLevel,
    RunStatus,
    utc_now,
)
from autoresearch.gates import GateService
from autoresearch.handoffs import HandoffService
from autoresearch.state_machine import StateMachine
from autoresearch.storage import RecordStore


class ReviewerAgent:
    agent_id = AgentId.REVIEWER

    def __init__(
        self,
        store: RecordStore,
        gates: GateService,
        handoffs: HandoffService,
        state_machine: StateMachine,
    ):
        self.store = store
        self.gates = gates
        self.handoffs = handoffs
        self.state_machine = state_machine

    def review_innovation(self, raw_state: WorkflowState) -> dict:
        state = ResearchState.model_validate(raw_state)
        self.handoffs.accept(
            state.handoff or {},
            expected_receiver=self.agent_id,
            project_id=state.project_id,
            run_id=state.run_id,
        )
        decision = self.gates.evaluate(
            GateRequest(
                project_id=state.project_id,
                operation="promote_reading_to_innovation_planning",
                risk_level=RiskLevel.L2,
                claim=(
                    "The supplied literature is sufficient to plan a falsifiable innovation "
                    "candidate, not to claim established novelty."
                ),
                evidence_ids=state.evidence_ids,
            )
        )
        report = ReviewReport(
            project_id=state.project_id,
            target_id=state.innovation_ids[0] if state.innovation_ids else state.run_id,
            verdict=decision.status,
            findings=decision.reasons,
            required_changes=[]
            if decision.status == GateStatus.PASS
            else [
                "Add independent paper evidence or a locatable full-text reading.",
                "Re-run reading and evidence audit before execution planning.",
            ],
            checked_evidence_ids=decision.qualifying_evidence_ids,
        )
        self.store.put(
            "review_report",
            report.review_id,
            report,
            project_id=state.project_id,
            partition="governance",
        )
        decision_ids = [*state.gate_decision_ids, decision.decision_id]
        review_ids = [*state.review_ids, report.review_id]
        if decision.status != GateStatus.PASS:
            target = self.state_machine.transition(
                state.lifecycle_state, LifecycleState.WAITING_EVIDENCE
            )
            return state.model_copy(
                update={
                    "lifecycle_state": target,
                    "run_status": RunStatus.BLOCKED,
                    "review_ids": review_ids,
                    "gate_decision_ids": decision_ids,
                    "blockers": [*state.blockers, *decision.reasons],
                    "handoff": None,
                    "last_agent": self.agent_id,
                    "updated_at": utc_now(),
                }
            ).model_dump(mode="json")

        target = self.state_machine.transition(
            state.lifecycle_state, LifecycleState.INNOVATION_REVIEWED
        )
        handoff = self.handoffs.issue(
            HandoffEnvelope(
                project_id=state.project_id,
                run_id=state.run_id,
                from_agent=self.agent_id,
                to_agent=AgentId.ORCHESTRATOR,
                objective="Materialize the accepted hypothesis as execution and writing work.",
                expected_output="Execution-planned state and writer handoff.",
                evidence_ids=decision.qualifying_evidence_ids,
                constraints=[
                    "Gate authorizes planning only",
                    "It does not establish novelty or positive results",
                ],
                bounded_context=f"gate={decision.decision_id}; score={decision.score}",
            )
        )
        return state.model_copy(
            update={
                "lifecycle_state": target,
                "review_ids": review_ids,
                "gate_decision_ids": decision_ids,
                "handoff": handoff.model_dump(mode="json"),
                "last_agent": self.agent_id,
                "updated_at": utc_now(),
            }
        ).model_dump(mode="json")

    def review_manuscript(self, raw_state: WorkflowState) -> dict:
        state = ResearchState.model_validate(raw_state)
        self.handoffs.accept(
            state.handoff or {},
            expected_receiver=self.agent_id,
            project_id=state.project_id,
            run_id=state.run_id,
        )
        raw_manuscript = (
            self.store.get("manuscript", state.manuscript_id) if state.manuscript_id else None
        )
        if raw_manuscript is None:
            raise ValueError("writer handoff did not contain a persisted manuscript")
        manuscript = Manuscript.model_validate(raw_manuscript)
        decision = self.gates.evaluate(
            GateRequest(
                project_id=state.project_id,
                operation="mark_manuscript_evidence_complete",
                risk_level=RiskLevel.L3,
                claim="The manuscript is evidence-complete and its result lineage is closed.",
                evidence_ids=manuscript.evidence_ids,
                work_closed_loop=not manuscript.unresolved_gaps,
            )
        )
        report = ReviewReport(
            project_id=state.project_id,
            target_id=manuscript.manuscript_id,
            verdict=decision.status,
            findings=[
                *decision.reasons,
                *[f"Unresolved: {gap}" for gap in manuscript.unresolved_gaps],
            ],
            required_changes=list(manuscript.unresolved_gaps),
            checked_evidence_ids=decision.qualifying_evidence_ids,
        )
        self.store.put(
            "review_report",
            report.review_id,
            report,
            project_id=state.project_id,
            partition="governance",
        )
        review_ids = [*state.review_ids, report.review_id]
        decision_ids = [*state.gate_decision_ids, decision.decision_id]
        if decision.status != GateStatus.PASS:
            target = self.state_machine.transition(
                state.lifecycle_state, LifecycleState.WAITING_EVIDENCE
            )
            return state.model_copy(
                update={
                    "lifecycle_state": target,
                    "run_status": RunStatus.BLOCKED,
                    "review_ids": review_ids,
                    "gate_decision_ids": decision_ids,
                    "blockers": [*state.blockers, *decision.reasons],
                    "handoff": None,
                    "last_agent": self.agent_id,
                    "updated_at": utc_now(),
                }
            ).model_dump(mode="json")

        target = self.state_machine.transition(state.lifecycle_state, LifecycleState.DRAFT_REVIEWED)
        if state.request_release:
            target = self.state_machine.transition(target, LifecycleState.RELEASE_PENDING)
            run_status = RunStatus.RUNNING
        else:
            run_status = RunStatus.COMPLETED
        return state.model_copy(
            update={
                "lifecycle_state": target,
                "run_status": run_status,
                "review_ids": review_ids,
                "gate_decision_ids": decision_ids,
                "handoff": None,
                "last_agent": self.agent_id,
                "updated_at": utc_now(),
            }
        ).model_dump(mode="json")

    def build_innovation_graph(self):
        return single_node_subgraph("review_innovation", self.review_innovation)

    def build_manuscript_graph(self):
        return single_node_subgraph("review_manuscript", self.review_manuscript)
