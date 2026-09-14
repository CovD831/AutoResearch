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

#: How many paper records this handoff names explicitly (D-A9-01). The envelope
#: is a reference list, so this is an ergonomics bound rather than a capacity
#: limit: ``state.paper_ids`` already carries the full set and the reader resolves
#: every id from the store. Exceeding it is reported in diagnostics, never silent.
HANDOFF_REF_LIMIT = 50


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
            # A retrieval where every provider failed is not the same fact as a
            # query that legitimately returned nothing, and the two call for
            # different actions: the first is an operational failure to surface,
            # the second is "go find evidence". Branch on the flag, never on the
            # wording of a diagnostic -- a reworded message changes no decision.
            target = self.state_machine.transition(
                state.lifecycle_state, LifecycleState.WAITING_EVIDENCE
            )
            blocker = (
                "Retrieval failed across every source; the literature search did not run."
                if outcome.provider_failure
                else "No real paper records are available for reading."
            )
            return state.model_copy(
                update={
                    "lifecycle_state": target,
                    "run_status": RunStatus.BLOCKED,
                    "blockers": [*state.blockers, blocker],
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
                # Reference list, not a payload (D-A9-01). The title used to be
                # copied into ``summary``, which is capped at 500 characters while
                # ``PaperRecord.title`` is unbounded -- a long title would have
                # rejected the envelope for no reason. The reader resolves records
                # from the store by id anyway.
                artifact_refs=[
                    ArtifactRef(artifact_id=paper.paper_id, kind="paper_record", uri=paper.url)
                    for paper in outcome.papers[:HANDOFF_REF_LIMIT]
                ],
                evidence_ids=paper_evidence,
                constraints=[
                    "Use supplied full text or abstract only",
                    "Attach locators",
                    "Label innovation as hypothesis, not established novelty",
                ],
                bounded_context=(
                    f"papers={len(paper_ids)}; "
                    f"refs_attached={min(len(paper_ids), HANDOFF_REF_LIMIT)}"
                ),
            )
        )
        # A silent truncation is a fail-open: downstream would believe it received
        # every record. The state already carries the full ``paper_ids`` list, so
        # the truncation only affects this reference list, and it must be visible.
        if len(paper_ids) > HANDOFF_REF_LIMIT:
            diagnostics.append(
                f"handoff lists the first {HANDOFF_REF_LIMIT} of {len(paper_ids)} paper "
                f"records; the reader resolves the full set from state.paper_ids"
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
