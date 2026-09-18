from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from autoresearch.acl import AccessPolicyStore
from autoresearch.adapter_search_service import AdapterBackedPaperSearchService
from autoresearch.agents import (
    OrchestratorAgent,
    PaperReaderAgent,
    PaperSearchAgent,
    ReviewerAgent,
    WriterAgent,
)
from autoresearch.capability import (
    PaperSearchCapabilityAdapter,
    PendingInvocationError,
)
from autoresearch.config import Settings, get_settings
from autoresearch.contracts import (
    EvidenceItem,
    EvolutionProposal,
    ExperienceRecord,
    ExperienceStage,
    Manuscript,
    ManuscriptRevisionRequest,
    ProjectCreate,
    ReadingAnswer,
    ReadingCard,
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
from autoresearch.experience_sink import ExperienceSink, SinkSettlement
from autoresearch.gates import GateService
from autoresearch.graph import build_research_graph
from autoresearch.handoffs import HandoffService
from autoresearch.invocation_contracts import (
    InvocationStatus,
    PaperSearchRequest,
    request_fingerprint,
)
from autoresearch.knowledge import KnowledgeService
from autoresearch.knowledge_retrieval import EmbeddingProvider
from autoresearch.llm import LLMService
from autoresearch.pipeline_contracts import (
    EvaluationSectionPipelineResult,
    ReadinessStatus,
)
from autoresearch.profile_service import UserProfileService
from autoresearch.project_service import ProjectService
from autoresearch.reader_service import PaperReaderService
from autoresearch.search_service import SearchOutcome
from autoresearch.state_machine import StateMachine
from autoresearch.storage import RecordStore
from autoresearch.writing_service import WritingService


class InvocationBoundedSearchPort:
    """Route paper-search calls through the reliable invocation boundary (I1).

    Each (project, query, limit, seeds) tuple maps to one deterministic
    idempotent invocation: identical re-invocations replay the durable
    receipt instead of re-calling connectors, and a pending record left by
    a crashed run is auto-recovered through the phase-driven recovery API.
    Failed or unknown receipts stay durable until explicitly recovered
    (A2 semantics); retry policy belongs to the audit lane.
    """

    def __init__(self, adapter: PaperSearchCapabilityAdapter):
        self.adapter = adapter

    def build_request(
        self,
        project_id: str,
        query: str,
        *,
        limit: int,
        seed_papers: list | None = None,
    ) -> PaperSearchRequest:
        request = PaperSearchRequest(
            project_id=project_id,
            run_id=f"app-search:{project_id}",
            invocation_id="derive",
            query=query,
            limit=limit,
            seed_papers=list(seed_papers or []),
        )
        derived = "q-" + request_fingerprint(request)[:16]
        return request.model_copy(update={"invocation_id": derived})

    def search(
        self,
        project_id: str,
        queries: list[str],
        *,
        seed_papers: list | None = None,
        per_connector_limit: int = 5,
    ) -> SearchOutcome:
        papers = []
        seen: set[str] = set()
        diagnostics: list[str] = []
        provider_failure = False
        refused_records = 0
        for query in queries:
            request = self.build_request(
                project_id,
                query,
                limit=per_connector_limit,
                seed_papers=seed_papers,
            )
            try:
                invocation = self.adapter.invoke(request)
            except PendingInvocationError:
                invocation = self.adapter.recover_pending(
                    request.run_id,
                    request.invocation_id,
                    reason="application auto-recovery on pending re-invocation",
                )
            for paper_record in invocation.papers:
                if paper_record.paper_id not in seen:
                    seen.add(paper_record.paper_id)
                    papers.append(paper_record)
            diagnostics.extend(invocation.diagnostics)
            # A failed or unknown invocation is carried upward as a fact, not as
            # diagnostic text. ``receipt.provider_failure`` also covers the
            # *partial* case: a run where the primary source never answered but a
            # secondary one returned papers still reads COMPLETED, and without
            # this flag that would be invisible (N1).
            outcome_status = invocation.receipt.outcome_status or invocation.receipt.status
            if invocation.receipt.provider_failure or outcome_status in (
                InvocationStatus.FAILED,
                InvocationStatus.UNKNOWN_OUTCOME,
            ):
                provider_failure = True
            refused_records += invocation.receipt.refused_records
        return SearchOutcome(
            papers=papers,
            diagnostics=diagnostics,
            provider_failure=provider_failure,
            refused_records=refused_records,
        )


class AutoResearchApplication:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        #: ADR-01 slot 14 / K11. ``None`` means the release path runs in
        #: "no policy enforced" mode, which the gate records rather than leaving
        #: implicit: an absent authorization layer is a mode, not a silent pass.
        self.access_policy = (
            AccessPolicyStore() if self.settings.access_control_enabled else None
        )
        self.settings.ensure_runtime_dirs()
        self.store = RecordStore(self.settings.db_path)
        self.evidence = EvidenceService(self.store)
        self.gates = GateService(self.evidence, self.store)
        # Unscoped write/index handle, shared by search / reader / profile /
        # experiences. It deliberately has no project scope, so ``retrieve`` on it
        # fails closed; retrieval goes through ``knowledge_scope(project_id)``
        # (M11-MVP-02 / ledger D-M11-02-01).
        self.knowledge = KnowledgeService(self.store)
        self.handoffs = HandoffService(self.store)
        self.state_machine = StateMachine()
        self.llm = LLMService(self.settings)
        self.projects = ProjectService(
            self.settings.projects_dir,
            self.settings.template_dir,
            self.store,
        )
        self.search = AdapterBackedPaperSearchService(
            self.store,
            self.evidence,
            self.knowledge,
            settings=self.settings,
            network_enabled=self.settings.network_enabled,
        )
        self.search_capability = PaperSearchCapabilityAdapter(self.search, self.store)
        self.search_port = InvocationBoundedSearchPort(self.search_capability)
        self.reader = PaperReaderService(self.store, self.evidence, self.knowledge)
        self.writing = WritingService(
            self.store,
            self.evidence,
            self.settings.projects_dir,
            self.llm,
        )
        self.profile = UserProfileService(self.store, self.knowledge)
        self.experiences = ExperienceService(self.store, self.knowledge)
        self.experience_sink = ExperienceSink(self.store, self.experiences)
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
            self.search_port,
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
            access_policy=self.access_policy,
        )
        self._graph_lock = threading.RLock()

    def knowledge_scope(
        self,
        project_id: str,
        *,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> KnowledgeService:
        """A ``KnowledgeService`` bound to one project, sharing this app's store.

        Retrieval is project-scoped, so every caller that runs ``retrieve`` must say
        which project it is asking about. ``self.knowledge`` is the unscoped
        write/index handle the other services share; this factory is the only
        sanctioned way to obtain a handle that may retrieve (M11-MVP-02 /
        ledger D-M11-02-01). Passing ``project_id`` positionally is impossible by
        construction -- the scope is not optional and cannot be omitted silently.
        """

        return KnowledgeService(
            self.store,
            project_id=project_id,
            embedding_provider=embedding_provider,
        )

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
            # Lifted to the top level next to ``status`` on purpose. A warning that
            # only lives inside ``state`` is one a caller has to know to look for;
            # promoting it makes "this run completed, but the retrieval was
            # incomplete" a first-class property of the run record (N1).
            "warnings": list(state.get("warnings") or []),
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

    def run_evaluation_section(
        self,
        project_id: str,
        question: str,
        cards: list[ReadingCard],
        *,
        evidence_ids: list[str] | None = None,
        profile: Any = None,
    ) -> EvaluationSectionPipelineResult:
        """Orchestrate the evaluation section pipeline end to end (I1).

        Blocked readiness short-circuits before draft and validation, keeping
        the accepted B1 semantics: a blocked compose produces no draft and no
        validation report.
        """

        if self.projects.get(project_id) is None:
            raise KeyError(f"unknown project: {project_id}")
        writing = self.writing
        resolved_profile = profile or writing.build_writing_profile(project_id)
        plan = writing.plan_evaluation_section(
            project_id,
            question,
            cards,
            evidence_ids=list(evidence_ids or []),
            profile=resolved_profile,
        )
        benchmark_plan = writing.advise_benchmark_plan(plan, cards)
        readiness = writing.assess_evaluation_readiness(
            plan,
            benchmark_plan,
            cards,
            profile=resolved_profile,
        )
        draft = None
        validation = None
        if readiness.status != ReadinessStatus.BLOCKED:
            draft = writing.draft_evaluation_section(
                plan,
                benchmark_plan,
                readiness,
                profile=resolved_profile,
            )
            validation = writing.validate_evaluation_section(
                plan,
                benchmark_plan,
                readiness,
                draft,
                profile=resolved_profile,
            )
        return EvaluationSectionPipelineResult(
            profile=resolved_profile,
            plan=plan,
            benchmark_plan=benchmark_plan,
            readiness=readiness,
            draft=draft,
            validation=validation,
        )

    def add_evidence(self, item: EvidenceItem, *, actor: str = "user") -> EvidenceItem:
        return self.evidence.add(item, actor=actor)

    def record_profile(self, item: UserProfileItem) -> UserProfileItem:
        return self.profile.record(item)

    def record_experience(self, item: ExperienceRecord) -> ExperienceRecord:
        """Create an experience from an external caller.

        The external boundary may only create the sink's natural output: an
        unpromoted ``x0_raw`` record. Both ``promoted`` and ``stage`` feed the
        promotion workflow, so accepting either here would let a caller skip a
        step of it by declaration.

        **Deliberately NOT guarded: ``grade``.** Restricting the creation
        boundary to ``grade=E0`` looks like the same fix, and it is not. Nothing
        else in the repository raises an *experience* record's grade -- every
        non-``E0`` grade write targets ``EvidenceItem`` / ``EvidenceCandidate``
        (verified across ``graph.py``, ``benchmark.py``, ``reader_writer_ports.py``,
        ``external_sources.py``, ``audit_evidence.py``), and ``ExperienceSink``
        pins ``E0`` by design (D-A6-03, ``experience_sink.py``). So an ``E0``-only
        creation guard would make promotion gate 2 (``grade in {E2,E3,H3}``)
        **unreachable through the entire public API** -- silently disabling
        promotion rather than securing it. Raising the grade needs an explicit
        adjudicated path; until that exists, leaving gate 2 caller-declarable is
        the lesser defect. See D-A7-01 / D-A7-02.

        Internal settlement calls ``ExperienceService.record()`` directly and is
        unaffected -- required, because a re-settle must carry an already-promoted
        record's ``grade``/``promoted`` forward (D-A6-03).
        """
        if item.promoted:
            raise PermissionError(
                "experience creation cannot set promoted=True; use the promote endpoint"
            )
        if item.stage is not ExperienceStage.X0_RAW:
            raise PermissionError(
                "experience creation must use stage=x0_raw; use the promotion workflow"
            )
        return self.experiences.record(item)

    def settle_failure_experiences(self, project_id: str) -> SinkSettlement:
        """Consume new failure events and settle them as failure experiences (A6).

        Read-only pull over the persisted audit event log; never touches the
        audit chain and never raises on degraded input.
        """

        if self.projects.get(project_id) is None:
            raise KeyError(f"unknown project: {project_id}")
        return self.experience_sink.settle(project_id)

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
