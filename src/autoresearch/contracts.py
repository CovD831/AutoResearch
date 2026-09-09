from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def utc_now() -> datetime:
    return datetime.now(UTC)


class AgentId(StrEnum):
    ORCHESTRATOR = "orchestrator"
    PAPER_SEARCH = "paper_search"
    PAPER_READER = "paper_reader"
    WRITER = "writer"
    REVIEWER = "reviewer"


class LifecycleState(StrEnum):
    INTAKE = "intake"
    SCOPED = "scoped"
    LITERATURE_SEARCHED = "literature_searched"
    LITERATURE_READ = "literature_read"
    INNOVATION_REVIEWED = "innovation_reviewed"
    EXECUTION_PLANNED = "execution_planned"
    DRAFT_WRITTEN = "draft_written"
    DRAFT_REVIEWED = "draft_reviewed"
    RELEASE_PENDING = "release_pending"
    RELEASED = "released"
    WAITING_EVIDENCE = "waiting_evidence"
    WAITING_HUMAN = "waiting_human"
    REJECTED = "rejected"
    FAILED = "failed"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"


class GateStatus(StrEnum):
    PASS = "pass"
    REVISE = "revise"
    DENY = "deny"
    INTERRUPT = "interrupt"


class RiskLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class EvidenceType(StrEnum):
    HUMAN = "human"
    PAPER = "paper"
    EXPERIMENT = "experiment"
    EXPERIENCE = "experience"
    KNOWLEDGE = "knowledge"
    SYSTEM = "system"


class EvidenceGrade(StrEnum):
    E0 = "E0"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    H3 = "H3"


class KnowledgePartition(StrEnum):
    PAPERS = "papers"
    EXPERIENCES = "experiences"
    KNOWLEDGE = "knowledge"
    PROFILES = "profiles"
    PROJECTS = "projects"


class ClaimStatus(StrEnum):
    UNKNOWN = "unknown"
    HYPOTHESIS = "hypothesis"
    SUPPORTED = "supported"
    REFUTED = "refuted"


class ArtifactRef(BaseModel):
    artifact_id: str
    kind: str
    uri: str | None = None
    checksum: str | None = None
    summary: str = Field(default="", max_length=500)


class EvidenceCandidate(BaseModel):
    """Cross-lane evidence candidate (I0 shared contract, D-I0-01).

    Produced by capability invocation boundaries (runtime lane: provenance
    fields) and consumed by the evidence admission pipeline (evidence lane:
    classification fields). ``evidence_type``/``grade`` stay optional because
    R005 forbids the runtime lane from assigning evidence grades; admission
    rejects candidates that lack the classification it needs.
    """

    candidate_id: str = Field(default_factory=lambda: new_id("evcand"))
    evidence_id: str | None = None
    project_id: str
    run_id: str | None = None
    invocation_id: str | None = None
    evidence_type: EvidenceType | None = None
    grade: EvidenceGrade | None = None
    title: str | None = Field(default=None, max_length=300)
    claim: str = Field(min_length=1, max_length=2000)
    source_uri: str | None = None
    source_id: str | None = None
    locator: str | None = Field(default=None, max_length=300)
    checksum: str | None = None
    independent_source: str = Field(min_length=1, max_length=300)
    adapter: str | None = Field(default=None, max_length=100)
    adapter_version: str | None = Field(default=None, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class EvidenceItem(BaseModel):
    evidence_id: str = Field(default_factory=lambda: new_id("ev"))
    project_id: str
    evidence_type: EvidenceType
    grade: EvidenceGrade
    title: str = Field(min_length=1, max_length=300)
    claim: str = Field(min_length=1, max_length=2000)
    source_uri: str | None = None
    source_id: str | None = None
    locator: str | None = None
    checksum: str | None = None
    independent_source: str = Field(min_length=1, max_length=300)
    valid: bool = True
    supersedes: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceBundle(BaseModel):
    project_id: str
    claim: str
    evidence_ids: list[str] = Field(default_factory=list)


class EvidenceInvalidationRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    actor: str = Field(min_length=1, max_length=200)


class GateRequest(BaseModel):
    project_id: str
    operation: str
    risk_level: RiskLevel
    claim: str
    evidence_ids: list[str] = Field(default_factory=list)
    work_closed_loop: bool = False
    explicitly_rejected: bool = False
    human_approval: bool = False


class GateDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: new_id("gate"))
    project_id: str
    operation: str
    status: GateStatus
    risk_level: RiskLevel
    score: int = Field(ge=0, le=100)
    independent_sources: int = Field(ge=0)
    reasons: list[str]
    qualifying_evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class HandoffEnvelope(BaseModel):
    handoff_id: str = Field(default_factory=lambda: new_id("handoff"))
    project_id: str
    run_id: str
    from_agent: AgentId
    to_agent: AgentId
    objective: str = Field(min_length=1, max_length=500)
    expected_output: str = Field(min_length=1, max_length=500)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list, max_length=20)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    constraints: list[str] = Field(default_factory=list, max_length=20)
    bounded_context: str = Field(default="", max_length=2000)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def agents_must_differ(self) -> HandoffEnvelope:
        if self.from_agent == self.to_agent:
            raise ValueError("handoff sender and receiver must differ")
        return self


class HandoffResult(BaseModel):
    handoff_id: str
    accepted: bool
    output_refs: list[ArtifactRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    summary: str = Field(max_length=1000)
    blockers: list[str] = Field(default_factory=list)


class PaperRecord(BaseModel):
    paper_id: str = Field(default_factory=lambda: new_id("paper"))
    project_id: str
    title: str
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    source: str
    source_record_id: str | None = None
    full_text_path: str | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)


class ReadingCard(BaseModel):
    card_id: str = Field(default_factory=lambda: new_id("card"))
    project_id: str
    paper_id: str
    research_question: str
    method: str
    data_or_setting: str
    findings: list[str]
    limitations: list[str]
    locators: list[str]
    evidence_ids: list[str]
    confidence: float = Field(ge=0, le=1)


class PaperQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ReadingAnswer(BaseModel):
    answer_id: str = Field(default_factory=lambda: new_id("answer"))
    project_id: str
    paper_id: str
    question: str
    answer: str
    locators: list[str]
    evidence_ids: list[str]
    confidence: float = Field(ge=0, le=1)
    unresolved: bool = False


class InnovationCandidate(BaseModel):
    innovation_id: str = Field(default_factory=lambda: new_id("innovation"))
    project_id: str
    statement: str
    rationale: str
    differentiators: list[str]
    evidence_ids: list[str]
    status: ClaimStatus = ClaimStatus.UNKNOWN
    falsification_test: str


class WorkPackage(BaseModel):
    work_package_id: str = Field(default_factory=lambda: new_id("wp"))
    project_id: str
    title: str
    objective: str
    tasks: list[str]
    expected_artifacts: list[str]
    acceptance_checks: list[str]
    dependencies: list[str] = Field(default_factory=list)
    status: str = "planned"
    evidence_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WorkPackageUpdate(BaseModel):
    status: str = Field(pattern=r"^(planned|in_progress|blocked|completed)$")
    evidence_ids: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=2000)


class Manuscript(BaseModel):
    manuscript_id: str = Field(default_factory=lambda: new_id("manuscript"))
    project_id: str
    title: str
    sections: dict[str, str]
    evidence_ids: list[str]
    unresolved_gaps: list[str] = Field(default_factory=list)
    release_ready: bool = False
    parent_manuscript_id: str | None = None
    revision_note: str | None = None


class ManuscriptRevisionRequest(BaseModel):
    instructions: str = Field(min_length=1, max_length=5000)
    mode: str = Field(default="revise", pattern=r"^(revise|polish)$")


class ReviewReport(BaseModel):
    review_id: str = Field(default_factory=lambda: new_id("review"))
    project_id: str
    target_id: str
    verdict: GateStatus
    findings: list[str]
    required_changes: list[str]
    checked_evidence_ids: list[str]


class WikiPage(BaseModel):
    page_id: str = Field(default_factory=lambda: new_id("wiki"))
    project_id: str | None = None
    partition: KnowledgePartition
    title: str
    body: str
    tags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    level: int = Field(default=1, ge=0, le=3)
    created_at: datetime = Field(default_factory=utc_now)


class GraphEdge(BaseModel):
    edge_id: str = Field(default_factory=lambda: new_id("edge"))
    project_id: str | None = None
    partition: KnowledgePartition
    source_id: str
    relation: str
    target_id: str
    evidence_ids: list[str] = Field(default_factory=list)


class RetrievalHit(BaseModel):
    record_id: str
    partition: KnowledgePartition
    title: str
    snippet: str
    score: float
    evidence_ids: list[str] = Field(default_factory=list)
    retrieval_level: str


class UserProfileItem(BaseModel):
    profile_item_id: str = Field(default_factory=lambda: new_id("profile"))
    user_id: str
    key: str
    value: str
    confidence: float = Field(ge=0, le=1)
    source: str
    confirmed_by_user: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class ExperienceRecord(BaseModel):
    experience_id: str = Field(default_factory=lambda: new_id("exp"))
    project_id: str
    problem: str
    technique: str
    outcome: str
    grade: EvidenceGrade = EvidenceGrade.E0
    recurrence_count: int = Field(default=1, ge=1)
    evidence_ids: list[str] = Field(default_factory=list)
    promoted: bool = False


class EvolutionProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: new_id("evo"))
    project_id: str
    problem: str
    proposed_change: str
    expected_benefit: str
    risks: list[str]
    evidence_ids: list[str]
    status: str = "proposed"
    human_approval_required: bool = True


class EvolutionReviewRequest(BaseModel):
    reviewer_approved: bool
    human_approved: bool = False
    note: str = Field(default="", max_length=2000)


class ExperiencePromotionRequest(BaseModel):
    reviewer_approved: bool
    human_approved: bool


class ProjectCreate(BaseModel):
    project_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$")
    title: str = Field(min_length=1, max_length=200)
    idea: str = Field(default="", max_length=5000)


class ResearchState(BaseModel):
    schema_version: int = 1
    project_id: str
    run_id: str = Field(default_factory=lambda: new_id("run"))
    idea: str
    lifecycle_state: LifecycleState = LifecycleState.INTAKE
    run_status: RunStatus = RunStatus.PENDING
    request_release: bool = False
    search_queries: list[str] = Field(default_factory=list)
    seed_papers: list[dict[str, Any]] = Field(default_factory=list)
    paper_ids: list[str] = Field(default_factory=list)
    reading_card_ids: list[str] = Field(default_factory=list)
    innovation_ids: list[str] = Field(default_factory=list)
    work_package_ids: list[str] = Field(default_factory=list)
    manuscript_id: str | None = None
    review_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    gate_decision_ids: list[str] = Field(default_factory=list)
    handoff: dict[str, Any] | None = None
    diagnostics: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    last_agent: AgentId | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class RunRequest(BaseModel):
    project_id: str
    idea: str = Field(min_length=1, max_length=5000)
    seed_papers: list[PaperRecord] = Field(default_factory=list)
    request_release: bool = False


class ResumeRequest(BaseModel):
    approval: bool
    reviewer: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=1000)
