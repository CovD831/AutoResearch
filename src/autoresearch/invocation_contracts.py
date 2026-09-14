from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from autoresearch.contracts import (
    EvidenceCandidate,
    InvocationCost,
    PaperRecord,
    TokenUsage,
    utc_now,
)

__all__ = [
    "RESTRICTED_LICENSES",
    "CapabilityLifecycleStatus",
    "CapabilityManifest",
    "CapabilityTrustClass",
    "EvidenceCandidate",
    "InvocationPhase",
    "InvocationReceipt",
    "InvocationStatus",
    "PaperSearchInvocation",
    "PaperSearchRequest",
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


class CapabilityTrustClass(StrEnum):
    """Self-described provenance class of a capability. NOT the operator policy.

    ``CapabilityTrustTier`` (in ``capability_registry``) is the *operator's*
    effective assignment. This enum is what the capability says about *itself*.
    A manifest can never raise its own effective tier by declaring a class, and
    the two dimensions must never be collapsed into one field:

    * ``trust_class``   -> "where did this capability come from" (self-described)
    * ``trust_tier``    -> "how much do we trust its output" (operator-assigned)
    """

    LOCAL = "local"
    REVIEWED_EXTERNAL = "reviewed_external"
    UNREVIEWED_EXTERNAL = "unreviewed_external"


class CapabilityLifecycleStatus(StrEnum):
    """Publication state of a capability manifest."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


#: Licenses that carry distribution obligations, so an option under one may never
#: become a default primary selection. See PLAN-capability-metadata §D2-7.
RESTRICTED_LICENSES = frozenset(
    {"AGPL-3.0", "AGPL-3.0-only", "AGPL-3.0-or-later", "AGPL-1.0", "SSPL-1.0"}
)


class CapabilityManifest(BaseModel):
    """Backward-compatible manifest; operator trust assignment stays outside it.

    Every field added after the S3-A freeze is optional with a default, so A1/A2
    construction sites keep working unchanged. The *registration* boundary is what
    enforces presence: ``validate_manifest`` in ``capability_registry`` rejects a
    manifest that is missing identity or schema refs, and that check runs before
    any adapter is reachable.
    """

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

    # --- identity / contract (S3-A2; closes the L2 "plugin lifecycle" open slot)
    manifest_id: str | None = Field(
        default=None,
        max_length=200,
        description="Stable identity that does NOT change across versions of the same capability.",
    )
    contract_version: str = Field(default="l2", min_length=1, max_length=50)
    input_schema_ref: str | None = Field(
        default=None,
        max_length=200,
        description="Name of the typed request contract this capability accepts.",
    )
    output_schema_ref: str | None = Field(
        default=None,
        max_length=200,
        description="Name of the typed result contract this capability produces.",
    )

    # --- policy / profile
    trust_class: CapabilityTrustClass = Field(
        default=CapabilityTrustClass.LOCAL,
        description="Self-described provenance. Never grants an effective trust tier.",
    )
    license_spdx: str | None = Field(default=None, max_length=100)
    selection_restricted_reason: str | None = Field(
        default=None,
        max_length=300,
        description=(
            "Required when license_spdx is a restricted license. Records why the "
            "option is admissible at all, and is the text a selection layer shows."
        ),
    )
    requires_credentials: list[str] = Field(default_factory=list, max_length=20)
    supports_offline: bool = False
    selection_tags: list[str] = Field(default_factory=list, max_length=30)
    conformance_fixture: str | None = Field(
        default=None,
        max_length=300,
        description="Path to the fixture that pins this manifest's declared contract.",
    )
    lifecycle_status: CapabilityLifecycleStatus = Field(
        default=CapabilityLifecycleStatus.ACTIVE
    )

    @property
    def is_restricted_license(self) -> bool:
        return bool(self.license_spdx) and self.license_spdx in RESTRICTED_LICENSES


class PaperSearchRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    invocation_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=100)
    seed_papers: list[PaperRecord] = Field(default_factory=list, max_length=100)


# ``TokenUsage`` / ``InvocationCost`` are re-exported from ``contracts`` (see
# ``__all__``) so downstream lanes keep importing them from this module while the
# definition lives in the shared contract layer.


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
