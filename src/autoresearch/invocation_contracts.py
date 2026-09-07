from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from autoresearch.contracts import PaperRecord, new_id, utc_now


class InvocationStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    COMPLETED_EMPTY = "completed_empty"
    FAILED = "failed"
    UNKNOWN_OUTCOME = "unknown_outcome"
    REPLAYED = "replayed"


class InvocationPhase(StrEnum):
    """Durable progress markers inside a still-pending invocation."""

    RESERVED = "reserved"
    SERVICE_STARTED = "service_started"
    SERVICE_RETURNED = "service_returned"
    FINALIZED = "finalized"


class CapabilityManifest(BaseModel):
    """Minimal S1 manifest; trust assignment remains outside the adapter."""

    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(default="native", min_length=1, max_length=50)
    version: str = Field(default="1", min_length=1, max_length=50)
    permissions: list[str] = Field(default_factory=list, max_length=20)


class PaperSearchRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    invocation_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=100)
    seed_papers: list[PaperRecord] = Field(default_factory=list, max_length=100)


class EvidenceCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: new_id("candidate"))
    evidence_id: str | None = None
    project_id: str
    run_id: str
    invocation_id: str
    claim: str = Field(min_length=1, max_length=2000)
    source_id: str | None = None
    source_uri: str | None = None
    locator: str = Field(default="bibliographic record/abstract", max_length=300)
    independent_source: str = Field(min_length=1, max_length=300)
    checksum: str | None = None
    adapter: str = Field(min_length=1, max_length=100)
    adapter_version: str = Field(min_length=1, max_length=50)


class InvocationReceipt(BaseModel):
    invocation_id: str
    status: InvocationStatus
    outcome_status: InvocationStatus | None = None
    adapter: str
    adapter_version: str
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    paper_ids: list[str] = Field(default_factory=list, max_length=100)
    diagnostics: list[str] = Field(default_factory=list, max_length=100)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PaperSearchInvocation(BaseModel):
    request: PaperSearchRequest
    receipt: InvocationReceipt
    papers: list[PaperRecord] = Field(default_factory=list, max_length=100)
    diagnostics: list[str] = Field(default_factory=list, max_length=100)
    evidence_candidates: list[EvidenceCandidate] = Field(default_factory=list, max_length=100)


def request_fingerprint(request: PaperSearchRequest) -> str:
    """Hash only bounded request data so exact replay is deterministic."""

    payload: dict[str, Any] = request.model_dump(mode="json")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def now() -> datetime:
    return utc_now()
