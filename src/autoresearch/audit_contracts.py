from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from autoresearch.contracts import ArtifactRef, EvidenceCandidate, utc_now


class AuditMode(StrEnum):
    IN_RUNTIME = "in-runtime"
    STANDALONE = "standalone"


class AuditCategory(StrEnum):
    EXISTENCE = "existence"
    LOCATOR = "locator"
    RETRACTION = "retraction"
    CORRECTION = "correction"
    BINDING = "binding"


class AuditVerdictStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class AuditMethod(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"


class AuditReceiptStatus(StrEnum):
    COMPLETED = "completed"
    REPLAYED = "replayed"
    FAILED = "failed"


class AuditClaim(BaseModel):
    claim_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2000)
    citation_ids: list[str] = Field(default_factory=list, max_length=100)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)


class AuditCitation(BaseModel):
    citation_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    doi: str | None = Field(default=None, max_length=300)
    arxiv_id: str | None = Field(default=None, max_length=200)
    source_uri: str | None = Field(default=None, max_length=1000)
    source_id: str | None = Field(default=None, max_length=300)
    locator: str | None = Field(default=None, max_length=300)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditInvocationRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=200)
    run_id: str | None = Field(default=None, max_length=200)
    invocation_id: str = Field(min_length=1, max_length=200)
    manuscript_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_version: str = Field(min_length=1, max_length=100)
    resolver_snapshot_version: str = Field(min_length=1, max_length=100)
    claims: list[AuditClaim] = Field(default_factory=list, max_length=200)
    citations: list[AuditCitation] = Field(default_factory=list, max_length=200)
    categories: list[AuditCategory] = Field(
        default_factory=lambda: [
            AuditCategory.EXISTENCE,
            AuditCategory.LOCATOR,
            AuditCategory.RETRACTION,
            AuditCategory.CORRECTION,
            AuditCategory.BINDING,
        ],
        max_length=10,
    )
    mode: AuditMode = AuditMode.STANDALONE


class AuditInvocationReceipt(BaseModel):
    invocation_id: str
    status: AuditReceiptStatus
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_id: str
    verdict_count: int = Field(ge=0)
    diagnostics: list[str] = Field(default_factory=list, max_length=100)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AuditVerdict(BaseModel):
    verdict_id: str
    category: AuditCategory
    status: AuditVerdictStatus
    target_id: str
    claim_id: str | None = None
    citation_id: str | None = None
    reason_code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)
    method: AuditMethod = AuditMethod.DETERMINISTIC
    confidence: float | None = Field(default=None, ge=0, le=1)
    resolver_snapshot_version: str | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    diagnostics: list[str] = Field(default_factory=list, max_length=50)


class AuditReport(BaseModel):
    report_schema: str = "audit-report/v1"
    report_id: str
    request: AuditInvocationRequest
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt: AuditInvocationReceipt
    artifact: ArtifactRef
    verdicts: list[AuditVerdict] = Field(default_factory=list, max_length=1000)
    candidates: list[EvidenceCandidate] = Field(default_factory=list, max_length=500)
    diagnostics: list[str] = Field(default_factory=list, max_length=100)
    bounded_evidence_count: int = Field(ge=0)
    created_at: datetime = Field(default_factory=utc_now)


def audit_request_fingerprint(request: AuditInvocationRequest) -> str:
    """Hash the audit content and snapshot versions, excluding invocation identity."""

    payload = request.model_dump(mode="json")
    payload.pop("invocation_id", None)
    payload.pop("run_id", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "AuditCategory",
    "AuditCitation",
    "AuditClaim",
    "AuditInvocationReceipt",
    "AuditInvocationRequest",
    "AuditMethod",
    "AuditMode",
    "AuditReceiptStatus",
    "AuditReport",
    "AuditVerdict",
    "AuditVerdictStatus",
    "audit_request_fingerprint",
]
