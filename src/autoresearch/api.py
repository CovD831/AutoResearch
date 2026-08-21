from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from autoresearch.application import AutoResearchApplication
from autoresearch.contracts import (
    EvidenceInvalidationRequest,
    EvidenceItem,
    EvolutionProposal,
    EvolutionReviewRequest,
    ExperiencePromotionRequest,
    ExperienceRecord,
    GraphEdge,
    KnowledgePartition,
    ManuscriptRevisionRequest,
    PaperQuestion,
    ProjectCreate,
    ResumeRequest,
    RunRequest,
    UserProfileItem,
    WikiPage,
    WorkPackageUpdate,
)


def create_api(application: AutoResearchApplication | None = None) -> FastAPI:
    runtime = application or AutoResearchApplication()
    app = FastAPI(
        title="AutoResearch API",
        version="0.1.0",
        description="Evidence-governed five-agent research workflow",
    )
    app.state.runtime = runtime

    @app.get("/health")
    def health():
        return runtime.doctor()

    @app.post("/projects", status_code=201)
    def create_project(request: ProjectCreate):
        try:
            return runtime.create_project(request)
        except (FileExistsError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/projects/{project_id}")
    def get_project(project_id: str):
        project = runtime.projects.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        return project

    @app.post("/runs", status_code=201)
    def start_run(request: RunRequest):
        try:
            return runtime.run(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/runs/{run_id}")
    def get_run(run_id: str, include_checkpoint: bool = False):
        run = runtime.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        if include_checkpoint:
            run = {**run, "checkpoint": runtime.graph_state(run_id)}
        return run

    @app.post("/runs/{run_id}/resume")
    def resume_run(run_id: str, request: ResumeRequest):
        try:
            return runtime.resume(run_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/evidence", status_code=201)
    def add_evidence(item: EvidenceItem):
        try:
            return runtime.add_evidence(item)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/projects/{project_id}/evidence")
    def list_evidence(project_id: str, valid_only: bool = True):
        return runtime.evidence.list(project_id, valid_only=valid_only)

    @app.post("/evidence/{evidence_id}/invalidate")
    def invalidate_evidence(evidence_id: str, request: EvidenceInvalidationRequest):
        try:
            runtime.evidence.invalidate(
                evidence_id,
                request.reason,
                actor=request.actor,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="evidence not found") from exc
        return {"evidence_id": evidence_id, "valid": False}

    @app.post("/papers/{paper_id}/questions", status_code=201)
    def ask_paper(paper_id: str, request: PaperQuestion):
        try:
            return runtime.answer_paper(paper_id, request.question)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="paper not found") from exc

    @app.post("/manuscripts/{manuscript_id}/revisions", status_code=201)
    def revise_manuscript(
        manuscript_id: str,
        request: ManuscriptRevisionRequest,
    ):
        try:
            return runtime.revise_manuscript(manuscript_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="manuscript not found") from exc

    @app.get("/projects/{project_id}/work-packages")
    def list_work_packages(project_id: str):
        return runtime.execution.list_work_packages(project_id)

    @app.patch("/work-packages/{work_package_id}")
    def update_work_package(work_package_id: str, request: WorkPackageUpdate):
        try:
            return runtime.update_work_package(work_package_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="work package not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/knowledge/pages", status_code=201)
    def add_wiki_page(page: WikiPage):
        return runtime.knowledge.add_page(page)

    @app.post("/knowledge/edges", status_code=201)
    def add_graph_edge(edge: GraphEdge):
        try:
            return runtime.knowledge.add_edge(edge)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/knowledge/search")
    def search_knowledge(
        q: str = Query(min_length=1),
        partitions: str = "papers,knowledge,experiences",
        level: int = Query(default=1, ge=1, le=2),
        limit: int = Query(default=10, ge=1, le=100),
        require_evidence: bool = False,
    ):
        try:
            selected = [
                KnowledgePartition(value.strip())
                for value in partitions.split(",")
                if value.strip()
            ]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return runtime.knowledge.retrieve(
            q,
            partitions=selected,
            level=level,
            limit=limit,
            require_evidence=require_evidence,
        )

    @app.post("/profiles", status_code=201)
    def add_profile_item(item: UserProfileItem):
        return runtime.record_profile(item)

    @app.get("/profiles/{user_id}")
    def get_profile(user_id: str):
        return runtime.profile.list(user_id)

    @app.post("/experiences", status_code=201)
    def add_experience(item: ExperienceRecord):
        return runtime.record_experience(item)

    @app.post("/experiences/{experience_id}/promote")
    def promote_experience(
        experience_id: str,
        request: ExperiencePromotionRequest,
    ):
        try:
            return runtime.experiences.promote(
                experience_id,
                reviewer_approved=request.reviewer_approved,
                human_approved=request.human_approved,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="experience not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/evolution/proposals", status_code=201)
    def add_evolution_proposal(item: EvolutionProposal):
        return runtime.propose_evolution(item)

    @app.post("/evolution/proposals/{proposal_id}/review")
    def review_evolution(proposal_id: str, request: EvolutionReviewRequest):
        try:
            return runtime.evolution.review(
                proposal_id,
                reviewer_approved=request.reviewer_approved,
                human_approved=request.human_approved,
                note=request.note,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="proposal not found") from exc

    @app.get("/projects/{project_id}/audit-events")
    def audit_events(project_id: str):
        return runtime.store.events(project_id)

    return app


app = create_api()
