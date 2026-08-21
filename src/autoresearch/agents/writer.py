from __future__ import annotations

from autoresearch.agents.base import WorkflowState, single_node_subgraph
from autoresearch.contracts import (
    AgentId,
    ArtifactRef,
    HandoffEnvelope,
    InnovationCandidate,
    LifecycleState,
    PaperRecord,
    ReadingCard,
    ResearchState,
    utc_now,
)
from autoresearch.handoffs import HandoffService
from autoresearch.state_machine import StateMachine
from autoresearch.storage import RecordStore
from autoresearch.writing_service import WritingService


class WriterAgent:
    agent_id = AgentId.WRITER

    def __init__(
        self,
        store: RecordStore,
        writing: WritingService,
        handoffs: HandoffService,
        state_machine: StateMachine,
    ):
        self.store = store
        self.writing = writing
        self.handoffs = handoffs
        self.state_machine = state_machine

    def run(self, raw_state: WorkflowState) -> dict:
        state = ResearchState.model_validate(raw_state)
        self.handoffs.accept(
            state.handoff or {},
            expected_receiver=self.agent_id,
            project_id=state.project_id,
            run_id=state.run_id,
        )
        papers = [
            PaperRecord.model_validate(raw)
            for paper_id in state.paper_ids
            if (raw := self.store.get("paper", paper_id)) is not None
        ]
        cards = [
            ReadingCard.model_validate(raw)
            for card_id in state.reading_card_ids
            if (raw := self.store.get("reading_card", card_id)) is not None
        ]
        innovations = [
            InnovationCandidate.model_validate(raw)
            for innovation_id in state.innovation_ids
            if (raw := self.store.get("innovation", innovation_id)) is not None
        ]
        manuscript = self.writing.draft(
            state.project_id,
            state.idea,
            papers,
            cards,
            innovations,
            state.evidence_ids,
        )
        target = self.state_machine.transition(state.lifecycle_state, LifecycleState.DRAFT_WRITTEN)
        handoff = self.handoffs.issue(
            HandoffEnvelope(
                project_id=state.project_id,
                run_id=state.run_id,
                from_agent=self.agent_id,
                to_agent=AgentId.REVIEWER,
                objective="Audit manuscript claims, evidence lineage, gaps, and release readiness.",
                expected_output="Review report and deterministic L3 gate decision.",
                artifact_refs=[
                    ArtifactRef(
                        artifact_id=manuscript.manuscript_id,
                        kind="manuscript",
                        uri=f"paper-projects/{state.project_id}/05_writing/MANUSCRIPT_DRAFT.md",
                        summary=f"gaps={len(manuscript.unresolved_gaps)}",
                    )
                ],
                evidence_ids=manuscript.evidence_ids,
                constraints=[
                    "A readable draft is not equivalent to a validated paper result",
                    "Any unresolved result gap blocks manuscript-ready status",
                ],
                bounded_context=f"sections={len(manuscript.sections)}",
            )
        )
        return state.model_copy(
            update={
                "lifecycle_state": target,
                "manuscript_id": manuscript.manuscript_id,
                "handoff": handoff.model_dump(mode="json"),
                "last_agent": self.agent_id,
                "updated_at": utc_now(),
            }
        ).model_dump(mode="json")

    def build_graph(self):
        return single_node_subgraph("draft", self.run)

    def revise(self, manuscript_id: str, instructions: str, *, mode: str):
        """Writing-agent boundary for non-release-ready revision or polishing."""
        return self.writing.revise(manuscript_id, instructions, mode=mode)
