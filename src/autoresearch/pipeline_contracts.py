from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from autoresearch.contracts import (
    ArtifactRef,
    new_id,
    utc_now,
)
from autoresearch.contracts import (
    EvidenceCandidate as EvidenceCandidate,
)
from autoresearch.contracts import (
    EvidenceGrade as EvidenceGrade,
)
from autoresearch.contracts import (
    EvidenceType as EvidenceType,
)


class SectionKind(StrEnum):
    EVALUATION = "evaluation"


class EvidenceAdmissionStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    BLOCKED = "blocked"


class ReadinessStatus(StrEnum):
    READY = "ready"
    NEEDS_MATERIAL = "needs_material"
    BLOCKED = "blocked"


class ValidationVerdict(StrEnum):
    VERIFIED = "verified"
    REVISE = "revise"
    BLOCKED = "blocked"


class EvidenceAdmissionResult(BaseModel):
    result_id: str = Field(default_factory=lambda: new_id("evar"))
    project_id: str
    candidate_id: str
    status: EvidenceAdmissionStatus
    evidence_id: str | None = None
    existing_evidence_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class WritingProfile(BaseModel):
    profile_id: str = Field(default_factory=lambda: new_id("wprof"))
    project_id: str
    section_kind: SectionKind = SectionKind.EVALUATION
    section_name: str = "Evaluation"
    version: str = "v1"
    voice: str = "evidence-first"
    citation_style: str = "inline-id"
    preserve_unknowns: bool = True
    preserve_limitations: bool = True
    preserve_failures: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class SectionPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: new_id("splan"))
    project_id: str
    section_kind: SectionKind = SectionKind.EVALUATION
    section_name: str = "Evaluation"
    objective: str = Field(min_length=1, max_length=1000)
    claims: list[str] = Field(default_factory=list)
    claim_evidence_map: dict[str, list[str]] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    experiment_dependencies: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    profile_id: str | None = None
    status: str = "planned"
    created_at: datetime = Field(default_factory=utc_now)


class BenchmarkPlan(BaseModel):
    benchmark_plan_id: str = Field(default_factory=lambda: new_id("bplan"))
    project_id: str
    section_id: str
    benchmark_name: str = Field(min_length=1, max_length=500)
    baseline: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    required_materials: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    planned_only: bool = True
    observed_result_summary: str | None = None
    status: str = "planned"
    created_at: datetime = Field(default_factory=utc_now)


class MaterialReadinessResult(BaseModel):
    readiness_id: str = Field(default_factory=lambda: new_id("mready"))
    project_id: str
    section_id: str
    status: ReadinessStatus
    missing_required: list[str] = Field(default_factory=list)
    missing_optional: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    benchmark_plan_id: str | None = None
    profile_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class SectionDraft(BaseModel):
    draft_id: str = Field(default_factory=lambda: new_id("sdraft"))
    project_id: str
    section_id: str
    profile_id: str
    plan_id: str
    benchmark_plan_id: str
    section_name: str = "Evaluation"
    title: str
    body: str
    claims: list[str] = Field(default_factory=list)
    claim_evidence_map: dict[str, list[str]] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    observed_result_summary: str | None = None
    review_ready: bool = False
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class SectionValidationReport(BaseModel):
    report_id: str = Field(default_factory=lambda: new_id("sval"))
    project_id: str
    section_id: str
    plan_id: str
    draft_id: str
    benchmark_plan_id: str
    profile_id: str
    verdict: ValidationVerdict
    issues: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    checked_evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class EvaluationSectionPipelineResult(BaseModel):
    profile: WritingProfile
    plan: SectionPlan
    benchmark_plan: BenchmarkPlan
    readiness: MaterialReadinessResult
    draft: SectionDraft | None = None
    validation: SectionValidationReport | None = None
