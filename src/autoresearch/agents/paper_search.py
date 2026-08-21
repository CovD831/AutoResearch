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
from autoresearch.evidence import EvidenceService
from autoresearch.handoffs import HandoffService
from autoresearch.search_service import PaperSearchService
from autoresearch.state_machine import StateMachine


class PaperSearchAgent:
    agent_id = AgentId.PAPER_SEARCH

    def __init__(
        self,
        search: PaperSearchService,
        evidence: EvidenceService,
        handoffs: HandoffService,
        state_machine: StateMachine,
    ):
        self.search = search
        self.evidence = evidence
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
        seeds = [PaperRecord.model_validate(raw) for raw in state.seed_papers]
        outcome = self.search.search(
            state.project_id,
            state.search_queries,
            seed_papers=seeds,
        )
        diagnostics = [*state.diagnostics, *outcome.diagnostics]
        if not outcome.papers:
            target = self.state_machine.transition(
                state.lifecycle_state, LifecycleState.WAITING_EVIDENCE
            )
            return state.model_copy(
                update={
                    "lifecycle_state": target,
                    "run_status": RunStatus.BLOCKED,
                    "blockers": [
                        *state.blockers,
                        "No real paper records are available for reading.",
                    ],
                    "diagnostics": diagnostics,
                    "handoff": None,
                    "last_agent": self.agent_id,
                    "updated_at": utc_now(),
                }
            ).model_dump(mode="json")

        paper_ids = [paper.paper_id for paper in outcome.papers]
        paper_evidence = [
            item.evidence_id
            for item in self.evidence.list(state.project_id, valid_only=True)
            if item.source_id in paper_ids
        ]
        target = self.state_machine.transition(
            state.lifecycle_state, LifecycleState.LITERATURE_SEARCHED
        )
        handoff = self.handoffs.issue(
            HandoffEnvelope(
                project_id=state.project_id,
                run_id=state.run_id,
                from_agent=self.agent_id,
                to_agent=AgentId.PAPER_READER,
                objective="Read registered papers, create structured cards, and mine hypotheses.",
                expected_output="Reading-card IDs and evidence-bounded innovation candidates.",
                artifact_refs=[
                    ArtifactRef(
                        artifact_id=paper.paper_id,
                        kind="paper_record",
                        uri=paper.url,
                        summary=paper.title,
                    )
                    for paper in outcome.papers[:20]
                ],
                evidence_ids=paper_evidence,
                constraints=[
                    "Use supplied full text or abstract only",
                    "Attach locators",
                    "Label innovation as hypothesis, not established novelty",
                ],
                bounded_context=f"papers={len(paper_ids)}",
            )
        )
        return state.model_copy(
            update={
                "lifecycle_state": target,
                "paper_ids": paper_ids,
                "evidence_ids": list(dict.fromkeys([*state.evidence_ids, *paper_evidence])),
                "handoff": handoff.model_dump(mode="json"),
                "diagnostics": diagnostics,
                "last_agent": self.agent_id,
                "updated_at": utc_now(),
            }
        ).model_dump(mode="json")

    def build_graph(self):
        return single_node_subgraph("search", self.run)
