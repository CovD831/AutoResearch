from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from autoresearch.agents import (
    OrchestratorAgent,
    PaperReaderAgent,
    PaperSearchAgent,
    ReviewerAgent,
    WriterAgent,
)
from autoresearch.config import Settings, get_settings
from autoresearch.contracts import (
    EvidenceItem,
    EvolutionProposal,
    ExperienceRecord,
    Manuscript,
    ManuscriptRevisionRequest,
    ProjectCreate,
    ReadingAnswer,
    ResearchState,
    ResumeRequest,
    RunRequest,
    RunStatus,
    UserProfileItem,
    WorkPackage,
    WorkPackageUpdate,
    new_id,
)
from autoresearch.evidence import EvidenceService
from autoresearch.evolution_service import EvolutionService, ExperienceService
from autoresearch.execution_service import ExecutionService
from autoresearch.gates import GateService
from autoresearch.graph import build_research_graph
from autoresearch.handoffs import HandoffService
from autoresearch.knowledge import KnowledgeService
from autoresearch.llm import LLMService
from autoresearch.profile_service import UserProfileService
from autoresearch.project_service import ProjectService
from autoresearch.reader_service import PaperReaderService
from autoresearch.search_service import PaperSearchService
from autoresearch.state_machine import StateMachine
from autoresearch.storage import RecordStore
from autoresearch.writing_service import WritingService


class AutoResearchApplication:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.settings.ensure_runtime_dirs()
        self.store = RecordStore(self.settings.db_path)
        self.evidence = EvidenceService(self.store)
        self.gates = GateService(self.evidence, self.store)
        self.knowledge = KnowledgeService(self.store)
        self.handoffs = HandoffService(self.store)
        self.state_machine = StateMachine()
        self.llm = LLMService(self.settings)
        self.projects = ProjectService(
            self.settings.projects_dir,
            self.settings.template_dir,
            self.store,
        )
        self.search = PaperSearchService(
            self.store,
            self.evidence,
            self.knowledge,
            network_enabled=self.settings.network_enabled,
        )
        self.reader = PaperReaderService(self.store, self.evidence, self.knowledge)
        self.writing = WritingService(
            self.store,
            self.evidence,
            self.settings.projects_dir,
            self.llm,
        )
        self.profile = UserProfileService(self.store, self.knowledge)
        self.experiences = ExperienceService(self.store, self.knowledge)
        self.evolution = EvolutionService(self.store)
        self.execution = ExecutionService(self.store, self.evidence)

        self.orchestrator_agent = OrchestratorAgent(
            self.store,
            self.evidence,
            self.handoffs,
            self.state_machine,
            self.llm,
        )
        self.paper_search_agent = PaperSearchAgent(
            self.search,
            self.evidence,
            self.handoffs,
            self.state_machine,
        )
        self.paper_reader_agent = PaperReaderAgent(
            self.store,
            self.reader,
            self.handoffs,
            self.state_machine,
        )
        self.writer_agent = WriterAgent(
            self.store,
            self.writing,
            self.handoffs,
            self.state_machine,
        )
        self.reviewer_agent = ReviewerAgent(
            self.store,
            self.gates,
            self.handoffs,
            self.state_machine,
        )
        self.agents = {
            self.orchestrator_agent.agent_id: self.orchestrator_agent,
            self.paper_search_agent.agent_id: self.paper_search_agent,
            self.paper_reader_agent.agent_id: self.paper_reader_agent,
            self.writer_agent.agent_id: self.writer_agent,
            self.reviewer_agent.agent_id: self.reviewer_agent,
        }

        self._checkpoint_connection = sqlite3.connect(
            self.settings.checkpoint_path,
            check_same_thread=False,
        )
        self._checkpointer = SqliteSaver(self._checkpoint_connection)
        self.graph = build_research_graph(
            orchestrator=self.orchestrator_agent,
            paper_search=self.paper_search_agent,
            paper_reader=self.paper_reader_agent,
            writer=self.writer_agent,
            reviewer=self.reviewer_agent,
            evidence=self.evidence,
            gates=self.gates,
            state_machine=self.state_machine,
            checkpointer=self._checkpointer,
        )
        self._graph_lock = threading.RLock()

    @staticmethod
    def _interrupts(result: dict[str, Any]) -> list[dict[str, Any]]:
        values = result.get("__interrupt__", [])
        output = []
        for value in values:
            payload = getattr(value, "value", value)
            output.append(payload if isinstance(payload, dict) else {"value": str(payload)})
        return output

    def _save_run(
        self,
        state: dict[str, Any],
        *,
        interrupts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        state = {key: value for key, value in state.items() if key != "__interrupt__"}
        interrupted = bool(interrupts)
        status = RunStatus.INTERRUPTED.value if interrupted else state.get("run_status")
        record = {
            "run_id": state["run_id"],
            "project_id": state["project_id"],
            "status": status,
            "state": state,
            "interrupts": interrupts or [],
        }
        self.store.put(
            "run",
            state["run_id"],
            record,
            project_id=state["project_id"],
            partition="runs",
        )
        self.store.append_event(
            "run.checkpointed",
            {
                "run_id": state["run_id"],
                "status": status,
                "lifecycle_state": state.get("lifecycle_state"),
            },
            project_id=state["project_id"],
            actor="application",
        )
        self.projects.sync_run_projection(record)
        return record

    def create_project(self, request: ProjectCreate, *, owner: str = "user") -> dict[str, Any]:
        path = self.projects.create(request, owner=owner)
        return {"project_id": request.project_id, "path": str(path), "status": "active"}

    def run(self, request: RunRequest) -> dict[str, Any]:
        if self.projects.get(request.project_id) is None:
            raise KeyError(f"unknown project: {request.project_id}")
        state = ResearchState(
            project_id=request.project_id,
            idea=request.idea,
            request_release=request.request_release,
            seed_papers=[
                paper.model_copy(update={"project_id": request.project_id}).model_dump(mode="json")
                for paper in request.seed_papers
            ],
            run_status=RunStatus.RUNNING,
        )
        config = {"configurable": {"thread_id": state.run_id}}
        self.store.append_event(
            "run.started",
            {"run_id": state.run_id, "idea": state.idea},
            project_id=state.project_id,
            actor="user",
        )
        with self._graph_lock:
            result = self.graph.invoke(state.model_dump(mode="json"), config=config)
        interrupts = self._interrupts(result)
        return self._save_run(result, interrupts=interrupts)

    def resume(self, run_id: str, request: ResumeRequest) -> dict[str, Any]:
        existing = self.get_run(run_id)
        if existing is None:
            raise KeyError(run_id)
        if not existing["interrupts"]:
            raise ValueError("run is not waiting for a human interrupt")
        config = {"configurable": {"thread_id": run_id}}
        with self._graph_lock:
            result = self.graph.invoke(
                Command(resume=request.model_dump(mode="json")),
                config=config,
            )
        interrupts = self._interrupts(result)
        return self._save_run(result, interrupts=interrupts)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.store.get("run", run_id)

    def graph_state(self, run_id: str) -> dict[str, Any]:
        config = {"configurable": {"thread_id": run_id}}
        with self._graph_lock:
            snapshot = self.graph.get_state(config)
        return {
            "values": dict(snapshot.values),
            "next": list(snapshot.next),
            "checkpoint": snapshot.config,
            "interrupts": [
                getattr(interrupt_item, "value", str(interrupt_item))
                for task in snapshot.tasks
                for interrupt_item in task.interrupts
            ],
        }

    def add_evidence(self, item: EvidenceItem, *, actor: str = "user") -> EvidenceItem:
        return self.evidence.add(item, actor=actor)

    def record_profile(self, item: UserProfileItem) -> UserProfileItem:
        return self.profile.record(item)

    def record_experience(self, item: ExperienceRecord) -> ExperienceRecord:
        return self.experiences.record(item)

    def update_work_package(self, work_package_id: str, update: WorkPackageUpdate) -> WorkPackage:
        return self.execution.update_work_package(work_package_id, update)

    def revise_manuscript(
        self, manuscript_id: str, request: ManuscriptRevisionRequest
    ) -> Manuscript:
        return self.writer_agent.revise(
            manuscript_id,
            request.instructions,
            mode=request.mode,
        )

    def answer_paper(self, paper_id: str, question: str) -> ReadingAnswer:
        return self.reader.answer_question(paper_id, question)

    def propose_evolution(self, proposal: EvolutionProposal) -> EvolutionProposal:
        return self.evolution.propose(proposal)

    def doctor(self) -> dict[str, Any]:
        return {
            "ok": True,
            "version": "0.1.0",
            "python_profile": "3.12+",
            "agents": [agent_id.value for agent_id in self.agents],
            "agent_count": len(self.agents),
            "settings": self.settings.safe_summary(),
            "projects_dir_exists": Path(self.settings.projects_dir).is_dir(),
            "template_dir_exists": Path(self.settings.template_dir).is_dir(),
            "database_ready": self.settings.db_path.is_file(),
            "checkpoint_database_ready": self.settings.checkpoint_path.parent.is_dir(),
            "diagnostic_id": new_id("doctor"),
        }

    def close(self) -> None:
        self._checkpoint_connection.close()
