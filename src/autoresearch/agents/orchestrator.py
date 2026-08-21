from __future__ import annotations

import re

from autoresearch.agents.base import WorkflowState, single_node_subgraph
from autoresearch.contracts import (
    AgentId,
    ArtifactRef,
    EvidenceGrade,
    EvidenceItem,
    EvidenceType,
    HandoffEnvelope,
    LifecycleState,
    ResearchState,
    RunStatus,
    WorkPackage,
    new_id,
    utc_now,
)
from autoresearch.evidence import EvidenceService
from autoresearch.handoffs import HandoffService
from autoresearch.llm import LLMService
from autoresearch.state_machine import StateMachine
from autoresearch.storage import RecordStore


class OrchestratorAgent:
    agent_id = AgentId.ORCHESTRATOR

    def __init__(
        self,
        store: RecordStore,
        evidence: EvidenceService,
        handoffs: HandoffService,
        state_machine: StateMachine,
        llm: LLMService,
    ):
        self.store = store
        self.evidence = evidence
        self.handoffs = handoffs
        self.state_machine = state_machine
        self.llm = llm

    @staticmethod
    def _queries(idea: str) -> list[str]:
        cleaned = re.sub(r"[^\w\u4e00-\u9fff -]+", " ", idea)
        tokens = [token for token in cleaned.split() if len(token) > 1]
        base = " ".join(tokens[:12]) or idea[:120]
        return list(
            dict.fromkeys(
                [
                    base,
                    f"{base} systematic review",
                    f"{base} benchmark evaluation",
                ]
            )
        )

    def scope(self, raw_state: WorkflowState) -> dict:
        state = ResearchState.model_validate(raw_state)
        queries = self._queries(state.idea)
        llm_note = None
        if self.llm.available:
            try:
                result = self.llm.complete_json(
                    system=(
                        "You decompose a research idea. Return JSON with a 'search_queries' "
                        "array only. Do not claim novelty or results."
                    ),
                    user=state.idea,
                )
                candidates = result.get("search_queries", []) if result else []
                if candidates:
                    queries = list(
                        dict.fromkeys([str(item)[:300] for item in candidates if str(item).strip()])
                    )[:8]
                    llm_note = "Managed LLM refined the search query plan."
            except Exception as exc:
                llm_note = f"LLM query refinement unavailable: {type(exc).__name__}; fallback used."

        charter_id = new_id("charter")
        charter = {
            "charter_id": charter_id,
            "project_id": state.project_id,
            "idea": state.idea,
            "research_questions": [
                f"What measurable problem does this idea address: {state.idea[:220]}?",
                "Which prior methods are the strongest baselines and boundary cases?",
                "What result would falsify the proposed contribution?",
            ],
            "success_criteria": [
                "Every material claim links to evidence IDs.",
                "At least two independent sources support manuscript-ready claims.",
                "Results originate from registered execution artifacts, never inference.",
            ],
            "non_goals": [
                "Automatic publication without human approval",
                "Invented papers, data, metrics, or novelty claims",
            ],
        }
        self.store.put(
            "research_charter",
            charter_id,
            charter,
            project_id=state.project_id,
            partition="projects",
        )
        idea_evidence = self.evidence.add(
            EvidenceItem(
                project_id=state.project_id,
                evidence_type=EvidenceType.HUMAN,
                grade=EvidenceGrade.E0,
                title="User-provided research idea",
                claim="The user supplied this idea as the starting research intent.",
                source_id=charter_id,
                locator="research charter: idea",
                independent_source=f"user-intent:{state.project_id}",
            ),
            actor="orchestrator",
        )
        registered_evidence_ids = [
            item.evidence_id for item in self.evidence.list(state.project_id, valid_only=True)
        ]
        all_evidence_ids = list(
            dict.fromkeys(
                [*state.evidence_ids, *registered_evidence_ids, idea_evidence.evidence_id]
            )
        )

        packages = [
            WorkPackage(
                project_id=state.project_id,
                title="WP1 Literature evidence",
                objective="Search, deduplicate, read, and compare relevant papers.",
                tasks=["Run registered queries", "Create reading cards", "Audit locators"],
                expected_artifacts=["search ledger", "paper records", "reading cards"],
                acceptance_checks=["no invented records", "each card has evidence IDs"],
            ),
            WorkPackage(
                project_id=state.project_id,
                title="WP2 Method and implementation",
                objective="Turn the candidate contribution into a reproducible implementation.",
                tasks=["Define interfaces", "Implement baseline", "Implement candidate method"],
                expected_artifacts=["source revision", "environment manifest", "run command"],
                acceptance_checks=["clean install", "reproducible command", "version captured"],
                dependencies=["WP1 Literature evidence"],
            ),
            WorkPackage(
                project_id=state.project_id,
                title="WP3 Evaluation",
                objective="Test the candidate against baselines and falsification criteria.",
                tasks=["Register metrics", "Run baselines", "Run ablations", "Record failures"],
                expected_artifacts=["run manifests", "raw outputs", "analysis tables"],
                acceptance_checks=["lineage complete", "no hand-entered result claims"],
                dependencies=["WP2 Method and implementation"],
            ),
            WorkPackage(
                project_id=state.project_id,
                title="WP4 Manuscript",
                objective="Draft and review only evidence-supported statements.",
                tasks=["Outline", "Draft", "Evidence audit", "Revise"],
                expected_artifacts=["manuscript draft", "review report"],
                acceptance_checks=["all claims traceable", "unresolved gaps visible"],
                dependencies=["WP1 Literature evidence", "WP3 Evaluation"],
            ),
        ]
        for package in packages:
            self.store.put(
                "work_package",
                package.work_package_id,
                package,
                project_id=state.project_id,
                partition="projects",
            )

        target = self.state_machine.transition(state.lifecycle_state, LifecycleState.SCOPED)
        handoff = self.handoffs.issue(
            HandoffEnvelope(
                project_id=state.project_id,
                run_id=state.run_id,
                from_agent=self.agent_id,
                to_agent=AgentId.PAPER_SEARCH,
                objective="Find and register relevant scholarly records for the scoped idea.",
                expected_output="Deduplicated paper IDs with provenance and diagnostics.",
                artifact_refs=[
                    ArtifactRef(
                        artifact_id=charter_id,
                        kind="research_charter",
                        summary=state.idea[:300],
                    )
                ],
                evidence_ids=all_evidence_ids,
                constraints=[
                    "Do not invent papers",
                    "Keep source IDs and URLs",
                    "Stop cleanly if no records are available",
                ],
                bounded_context="\n".join(queries),
            )
        )
        diagnostics = list(state.diagnostics)
        if llm_note:
            diagnostics.append(llm_note)
        return state.model_copy(
            update={
                "lifecycle_state": target,
                "run_status": RunStatus.RUNNING,
                "search_queries": queries,
                "work_package_ids": [package.work_package_id for package in packages],
                "evidence_ids": all_evidence_ids,
                "handoff": handoff.model_dump(mode="json"),
                "diagnostics": diagnostics,
                "last_agent": self.agent_id,
                "updated_at": utc_now(),
            }
        ).model_dump(mode="json")

    def plan_execution(self, raw_state: WorkflowState) -> dict:
        state = ResearchState.model_validate(raw_state)
        self.handoffs.accept(
            state.handoff or {},
            expected_receiver=self.agent_id,
            project_id=state.project_id,
            run_id=state.run_id,
        )
        target = self.state_machine.transition(
            state.lifecycle_state, LifecycleState.EXECUTION_PLANNED
        )
        handoff = self.handoffs.issue(
            HandoffEnvelope(
                project_id=state.project_id,
                run_id=state.run_id,
                from_agent=self.agent_id,
                to_agent=AgentId.WRITER,
                objective=(
                    "Create an internal evidence-bound manuscript draft and expose all missing "
                    "execution results."
                ),
                expected_output="Local manuscript artifact with evidence IDs and unresolved gaps.",
                evidence_ids=state.evidence_ids,
                constraints=[
                    "No fabricated metrics",
                    "Innovation remains a hypothesis until L3 gate passes",
                    "Missing results must stay explicit",
                ],
                bounded_context=(
                    f"idea={state.idea[:600]}; papers={len(state.paper_ids)}; "
                    f"reading_cards={len(state.reading_card_ids)}"
                ),
            )
        )
        return state.model_copy(
            update={
                "lifecycle_state": target,
                "handoff": handoff.model_dump(mode="json"),
                "last_agent": self.agent_id,
                "updated_at": utc_now(),
            }
        ).model_dump(mode="json")

    def build_scope_graph(self):
        return single_node_subgraph("scope", self.scope)

    def build_execution_graph(self):
        return single_node_subgraph("plan_execution", self.plan_execution)
