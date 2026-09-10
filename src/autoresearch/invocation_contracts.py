from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from autoresearch.contracts import (
    EvidenceCandidate,
    PaperRecord,
    utc_now,
)

__all__ = [
    "EvidenceCandidate",
    "InvocationPhase",
    "InvocationReceipt",
    "InvocationStatus",
    "PaperSearchInvocation",
    "PaperSearchRequest",
    "CapabilityManifest",
    "request_fingerprint",
    "TokenUsage",
    "InvocationCost",
]


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
    """Backward-compatible manifest; operator trust assignment stays outside it."""

    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(default="native", min_length=1, max_length=50)
    version: str = Field(default="1", min_length=1, max_length=50)
    permissions: list[str] = Field(default_factory=list, max_length=20)
    entrypoint: str | None = Field(default=None, max_length=300)
    inputs: list[str] = Field(default_factory=list, max_length=50)
    outputs: list[str] = Field(default_factory=list, max_length=50)
    evidence_mode: str | None = Field(default=None, max_length=50)
    network_required: bool = False
    allowed_network_domains: list[str] = Field(default_factory=list, max_length=50)


class PaperSearchRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    invocation_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=100)
    seed_papers: list[PaperRecord] = Field(default_factory=list, max_length=100)


class TokenUsage(BaseModel):
    """Provider-reported token usage attached to a receipt (O12, PLAN §4.2 field names)."""

    input: int = Field(default=0, ge=0)
    output: int = Field(default=0, ge=0)
    cache_read: int = Field(default=0, ge=0)
    cache_write: int = Field(default=0, ge=0)
    reasoning: int = Field(
        default=0, ge=0, description="Subset of output tokens; never billed twice."
    )


class InvocationCost(BaseModel):
    """Priced token usage in USD (O12 CostCalculator, pi-ai four-tier semantics).

    Reasoning tokens are a subset of ``output`` and never billed separately; the
    four parts sum to ``total``. ``lane_id``/``model`` make the price traceable to
    the catalog entry that produced it (S3.1 parity accounting).
    """

    input: float = Field(default=0.0, ge=0)
    output: float = Field(default=0.0, ge=0)
    cache_read: float = Field(default=0.0, ge=0)
    cache_write: float = Field(default=0.0, ge=0)
    total: float = Field(default=0.0, ge=0)
    currency: str = Field(default="USD", max_length=8)
    model: str | None = Field(default=None, max_length=200)
    lane_id: str | None = Field(default=None, max_length=200)


class InvocationReceipt(BaseModel):
    invocation_id: str
    status: InvocationStatus
    outcome_status: InvocationStatus | None = None
    adapter: str
    adapter_version: str
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    paper_ids: list[str] = Field(default_factory=list, max_length=100)
    diagnostics: list[str] = Field(default_factory=list, max_length=100)
    tokens: TokenUsage | None = Field(
        default=None,
        description="O12 provider usage. None when the invocation made no LLM call.",
    )
    cost: InvocationCost | None = Field(
        default=None,
        description="O12 priced usage. None when unpriced (no LLM call, or no catalog entry).",
    )
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
