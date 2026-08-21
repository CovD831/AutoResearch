from __future__ import annotations

from autoresearch.agents.base import WorkflowState, single_node_subgraph
from autoresearch.contracts import (
    AgentId,
    ArtifactRef,
    HandoffEnvelope,
    LifecycleState,
    PaperRecord,
    ResearchState,
    RunStatus,
    utc_now,
)
from autoresearch.handoffs import HandoffService
from autoresearch.reader_service import PaperReaderService
from autoresearch.state_machine import StateMachine
from autoresearch.storage import RecordStore


class PaperReaderAgent:
    agent_id = AgentId.PAPER_READER

    def __init__(
        self,
        store: RecordStore,
        reader: PaperReaderService,
        handoffs: HandoffService,
        state_machine: StateMachine,
    ):
        self.store = store
        self.reader = reader
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
        papers = []
        for paper_id in state.paper_ids:
            raw = self.store.get("paper", paper_id)
            if raw is not None:
                papers.append(PaperRecord.model_validate(raw))
        if not papers:
            target = self.state_machine.transition(
                state.lifecycle_state, LifecycleState.WAITING_EVIDENCE
            )
            return state.model_copy(
                update={
                    "lifecycle_state": target,
                    "run_status": RunStatus.BLOCKED,
                    "blockers": [*state.blockers, "Paper records disappeared before reading."],
                    "handoff": None,
                    "last_agent": self.agent_id,
                    "updated_at": utc_now(),
                }
            ).model_dump(mode="json")

        cards = []
        reading_evidence_ids = []
        for paper in papers:
            card, evidence = self.reader.read(paper)
            cards.append(card)
            reading_evidence_ids.append(evidence.evidence_id)
        innovations = self.reader.mine_innovations(state.project_id, state.idea, cards)
        target = self.state_machine.transition(
            state.lifecycle_state, LifecycleState.LITERATURE_READ
        )
        combined_evidence = list(dict.fromkeys([*state.evidence_ids, *reading_evidence_ids]))
        handoff = self.handoffs.issue(
            HandoffEnvelope(
                project_id=state.project_id,
                run_id=state.run_id,
                from_agent=self.agent_id,
                to_agent=AgentId.REVIEWER,
                objective=(
                    "Audit reading provenance and decide whether innovation planning may proceed."
                ),
                expected_output="Gate-backed review report with required changes.",
                artifact_refs=[
                    ArtifactRef(
                        artifact_id=card.card_id,
                        kind="reading_card",
                        summary=card.findings[0][:300],
                    )
                    for card in cards
                ]
                + [
                    ArtifactRef(
                        artifact_id=item.innovation_id,
                        kind="innovation_candidate",
                        summary=item.statement[:300],
                    )
                    for item in innovations
                ],
                evidence_ids=combined_evidence,
                constraints=[
                    "A hypothesis is not a novelty finding",
                    "Insufficient evidence must block progression",
                ],
                bounded_context=f"cards={len(cards)}; candidates={len(innovations)}",
            )
        )
        return state.model_copy(
            update={
                "lifecycle_state": target,
                "reading_card_ids": [card.card_id for card in cards],
                "innovation_ids": [item.innovation_id for item in innovations],
                "evidence_ids": combined_evidence,
                "handoff": handoff.model_dump(mode="json"),
                "last_agent": self.agent_id,
                "updated_at": utc_now(),
            }
        ).model_dump(mode="json")

    def build_graph(self):
        return single_node_subgraph("read_and_mine", self.run)
