from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from autoresearch.agents.base import WorkflowState
from autoresearch.agents.orchestrator import OrchestratorAgent
from autoresearch.agents.paper_reader import PaperReaderAgent
from autoresearch.agents.paper_search import PaperSearchAgent
from autoresearch.agents.reviewer import ReviewerAgent
from autoresearch.agents.writer import WriterAgent
from autoresearch.contracts import (
    AgentId,
    EvidenceGrade,
    EvidenceItem,
    EvidenceType,
    GateRequest,
    GateStatus,
    LifecycleState,
    ResearchState,
    RiskLevel,
    RunStatus,
    utc_now,
)
from autoresearch.evidence import EvidenceService
from autoresearch.gates import GateService
from autoresearch.state_machine import StateMachine


def _is_blocked(state: WorkflowState) -> str:
    return (
        "stop"
        if state.get("run_status")
        in {
            RunStatus.BLOCKED,
            RunStatus.FAILED,
            RunStatus.INTERRUPTED,
            "blocked",
            "failed",
            "interrupted",
        }
        else "continue"
    )


def build_research_graph(
    *,
    orchestrator: OrchestratorAgent,
    paper_search: PaperSearchAgent,
    paper_reader: PaperReaderAgent,
    writer: WriterAgent,
    reviewer: ReviewerAgent,
    evidence: EvidenceService,
    gates: GateService,
    state_machine: StateMachine,
    checkpointer: Any,
):
    """Build the parent workflow from five business-agent subgraphs and one policy node."""

    scope_graph = orchestrator.build_scope_graph()
    search_graph = paper_search.build_graph()
    reader_graph = paper_reader.build_graph()
    innovation_review_graph = reviewer.build_innovation_graph()
    execution_graph = orchestrator.build_execution_graph()
    writer_graph = writer.build_graph()
    manuscript_review_graph = reviewer.build_manuscript_graph()

    def after_final_review(state: WorkflowState) -> str:
        if _is_blocked(state) == "stop":
            return "stop"
        if state.get("lifecycle_state") in {
            LifecycleState.RELEASE_PENDING,
            LifecycleState.RELEASE_PENDING.value,
        }:
            return "release"
        return "stop"

    def release_gate(raw_state: WorkflowState) -> dict:
        state = ResearchState.model_validate(raw_state)
        approval = interrupt(
            {
                "type": "human_release_approval",
                "project_id": state.project_id,
                "run_id": state.run_id,
                "operation": "external_manuscript_release",
                "risk_level": RiskLevel.L4.value,
                "message": (
                    "External release is irreversible enough to require named human approval. "
                    "Review the manuscript and evidence ledger before deciding."
                ),
                "evidence_ids": state.evidence_ids,
            }
        )
        approved = isinstance(approval, dict) and approval.get("approval") is True
        reviewer_name = (
            str(approval.get("reviewer", "unknown"))[:200]
            if isinstance(approval, dict)
            else "unknown"
        )
        if not approved:
            decision = gates.evaluate(
                GateRequest(
                    project_id=state.project_id,
                    operation="external_manuscript_release",
                    risk_level=RiskLevel.L4,
                    claim="A human rejected external release.",
                    evidence_ids=state.evidence_ids,
                    work_closed_loop=True,
                    explicitly_rejected=True,
                )
            )
            target = state_machine.transition(state.lifecycle_state, LifecycleState.REJECTED)
            return state.model_copy(
                update={
                    "lifecycle_state": target,
                    "run_status": RunStatus.BLOCKED,
                    "gate_decision_ids": [
                        *state.gate_decision_ids,
                        decision.decision_id,
                    ],
                    "blockers": [*state.blockers, "Human rejected external release."],
                    "last_agent": AgentId.REVIEWER,
                    "updated_at": utc_now(),
                }
            ).model_dump(mode="json")

        approval_id = f"ev_human_release_{state.run_id}"
        approval_evidence = evidence.get(approval_id)
        if approval_evidence is None:
            approval_evidence = evidence.add(
                EvidenceItem(
                    evidence_id=approval_id,
                    project_id=state.project_id,
                    evidence_type=EvidenceType.HUMAN,
                    grade=EvidenceGrade.H3,
                    title="Named human release approval",
                    claim="A named human approved this specific run for external release.",
                    source_id=state.run_id,
                    locator="LangGraph release interrupt response",
                    independent_source=f"human-reviewer:{reviewer_name}",
                    metadata={
                        "reviewer": reviewer_name,
                        "note": (
                            str(approval.get("note", ""))[:1000]
                            if isinstance(approval, dict)
                            else ""
                        ),
                    },
                ),
                actor=reviewer_name,
            )
        all_evidence = list(dict.fromkeys([*state.evidence_ids, approval_evidence.evidence_id]))
        decision = gates.evaluate(
            GateRequest(
                project_id=state.project_id,
                operation="external_manuscript_release",
                risk_level=RiskLevel.L4,
                claim="The reviewed manuscript may be released externally.",
                evidence_ids=all_evidence,
                work_closed_loop=True,
                human_approval=True,
            )
        )
        if decision.status == GateStatus.PASS:
            target = state_machine.transition(state.lifecycle_state, LifecycleState.RELEASED)
            status = RunStatus.COMPLETED
            blockers = state.blockers
        else:
            target = state_machine.transition(
                state.lifecycle_state, LifecycleState.WAITING_EVIDENCE
            )
            status = RunStatus.BLOCKED
            blockers = [*state.blockers, *decision.reasons]
        return state.model_copy(
            update={
                "lifecycle_state": target,
                "run_status": status,
                "evidence_ids": all_evidence,
                "gate_decision_ids": [*state.gate_decision_ids, decision.decision_id],
                "blockers": blockers,
                "last_agent": AgentId.REVIEWER,
                "updated_at": utc_now(),
            }
        ).model_dump(mode="json")

    builder = StateGraph(WorkflowState)
    builder.add_node("orchestrator_scope", scope_graph)
    builder.add_node("paper_search", search_graph)
    builder.add_node("paper_reader", reader_graph)
    builder.add_node("reviewer_innovation", innovation_review_graph)
    builder.add_node("orchestrator_execution", execution_graph)
    builder.add_node("writer", writer_graph)
    builder.add_node("reviewer_manuscript", manuscript_review_graph)
    builder.add_node("release_gate", release_gate)

    builder.add_edge(START, "orchestrator_scope")
    builder.add_edge("orchestrator_scope", "paper_search")
    builder.add_conditional_edges(
        "paper_search", _is_blocked, {"continue": "paper_reader", "stop": END}
    )
    builder.add_conditional_edges(
        "paper_reader", _is_blocked, {"continue": "reviewer_innovation", "stop": END}
    )
    builder.add_conditional_edges(
        "reviewer_innovation",
        _is_blocked,
        {"continue": "orchestrator_execution", "stop": END},
    )
    builder.add_edge("orchestrator_execution", "writer")
    builder.add_edge("writer", "reviewer_manuscript")
    builder.add_conditional_edges(
        "reviewer_manuscript",
        after_final_review,
        {"release": "release_gate", "stop": END},
    )
    builder.add_edge("release_gate", END)
    return builder.compile(checkpointer=checkpointer)
