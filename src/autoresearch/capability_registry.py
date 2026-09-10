from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field, computed_field

from autoresearch.contracts import EvidenceCandidate, utc_now
from autoresearch.invocation_contracts import CapabilityManifest, InvocationCost, TokenUsage


class CapabilityTrustTier(StrEnum):
    """Operator-assigned result policy, independent of manifest self-description."""

    CANDIDATE_ONLY = "candidate_only"
    COMPLIANT_STRUCTURED = "compliant_structured"


class CapabilityKind(StrEnum):
    NATIVE = "native"
    MCP = "mcp"
    SKILL = "skill"
    PLUGIN = "plugin"


class CapabilityReceiptStatus(StrEnum):
    COMPLETED = "completed"
    REPLAYED = "replayed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    DENIED = "denied"


class CapabilityRegistryError(RuntimeError):
    """Base error for registration and invocation boundary violations."""


class CapabilityRegistrationError(CapabilityRegistryError):
    """The registry rejected an invalid or duplicate registration."""


class CapabilityNotRegisteredError(CapabilityRegistryError):
    """The caller attempted to invoke a capability absent from the registry."""


class CapabilityAmbiguousReferenceError(CapabilityRegistryError):
    """A bare capability name matched more than one registered version."""


class CapabilityInvocationConflictError(CapabilityRegistryError):
    """An invocation identity was reused with a different request fingerprint."""


class CapabilityBoundaryViolation(CapabilityRegistryError):
    """An adapter attempted to write a project-owned fact through its context."""


@dataclass(slots=True)
class CapabilityAdapterResult:
    """Normalized adapter output before the registry applies trust policy."""

    value: Any = None
    candidates: list[EvidenceCandidate] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    status: CapabilityReceiptStatus = CapabilityReceiptStatus.COMPLETED
    declared_trust_tier: CapabilityTrustTier | None = None


class CapabilityAdapter(Protocol):
    """Common invocation shape for native, MCP, Skill, and Plugin adapters."""

    def invoke(
        self,
        request: Any,
        context: CapabilityExecutionContext,
    ) -> CapabilityAdapterResult: ...


@dataclass(slots=True)
class CapabilityExecutionContext:
    """The only project-facing context an adapter receives.

    It intentionally exposes candidate emission but no Store, EvidenceService, or
    GateService. The two blocked methods make attempted bypasses observable in
    fixtures without granting a write path.
    """

    _candidates: list[EvidenceCandidate] = field(default_factory=list)
    blocked_write_attempts: int = 0

    def emit_candidate(self, candidate: EvidenceCandidate) -> None:
        self._candidates.append(candidate)

    @property
    def candidates(self) -> list[EvidenceCandidate]:
        return list(self._candidates)

    def write_evidence(self, *_args: Any, **_kwargs: Any) -> None:
        self.blocked_write_attempts += 1
        raise CapabilityBoundaryViolation(
            "adapters may emit candidates but cannot write EvidenceItem directly"
        )

    def write_gate_decision(self, *_args: Any, **_kwargs: Any) -> None:
        self.blocked_write_attempts += 1
        raise CapabilityBoundaryViolation("adapters cannot write GateDecision directly")


class CapabilityInvocationReceipt(BaseModel):
    invocation_id: str = Field(min_length=1, max_length=200)
    capability: str = Field(min_length=1, max_length=100)
    adapter_kind: CapabilityKind
    adapter_version: str = Field(min_length=1, max_length=50)
    trust_tier: CapabilityTrustTier
    status: CapabilityReceiptStatus
    outcome_status: CapabilityReceiptStatus | None = Field(
        default=None,
        description=(
            "Effective terminal outcome this invocation produced, preserved across replays. "
            "status=REPLAYED only means the result was served from the idempotency record; "
            "outcome_status still carries the original completed/failed/unknown/denied value. "
            "Mirrors the A1 InvocationReceipt convention (capability.py outcome_status)."
        ),
    )
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_count: int = Field(default=0, ge=0)
    structured_result_available: bool = False
    admitted: bool | None = Field(
        default=None,
        description=(
            "Reserved for I3: Evidence Module admission outcome (L2 compensation semantics). "
            "None until admission is wired; A4 records no admission itself."
        ),
    )
    diagnostics: list[str] = Field(default_factory=list, max_length=100)
    tokens: TokenUsage | None = Field(
        default=None,
        description=(
            "O12 provider usage for this invocation. None when the adapter made no LLM call "
            "(native adapters, or a lane that was never dispatched)."
        ),
    )
    cost: InvocationCost | None = Field(
        default=None,
        description=(
            "O12 priced usage (PLAN §4.2 field names, shared with A1 InvocationReceipt). "
            "None when the invocation is unpriced; pricing never blocks admissibility."
        ),
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @computed_field
    @property
    def candidates_admissible(self) -> bool:
        """Whether this invocation's candidates may enter downstream admission.

        Derived, never stored: the boundary is the single writer of this verdict so
        that consumers never have to re-derive it. It is keyed off ``outcome_status``
        rather than ``status`` on purpose -- an invocation served from the idempotency
        record has ``status=REPLAYED`` but must keep the admissibility of its original
        terminal outcome.

        Only ``completed`` is admissible. A ``failed`` / ``unknown`` / ``denied``
        invocation may still carry the candidates its adapter emitted (that list is the
        raw record of what was produced, kept for forensics); those candidates are not
        admissible.
        """

        return self.outcome_status == CapabilityReceiptStatus.COMPLETED


@dataclass(slots=True)
class CapabilityInvocation:
    """The outcome of one registry-mediated adapter invocation.

    ``candidates`` is the raw record of what the adapter produced, including on
    failure paths. Admission must not read it directly: use
    ``admissible_candidates`` (or gate on ``receipt.candidates_admissible``), which
    is empty unless the invocation's terminal outcome is ``completed``.
    """

    receipt: CapabilityInvocationReceipt
    value: Any = None
    candidates: list[EvidenceCandidate] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    @property
    def admissible_candidates(self) -> list[EvidenceCandidate]:
        """Candidates allowed into downstream admission; empty unless completed."""

        return list(self.candidates) if self.receipt.candidates_admissible else []


@dataclass(slots=True, frozen=True)
class CapabilityRegistration:
    manifest: CapabilityManifest
    adapter: CapabilityAdapter
    trust_tier: CapabilityTrustTier
    kind: CapabilityKind
    network_required: bool
    allowed_network_domains: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class CapabilityRegistrationView:
    """Public registration metadata without a raw adapter bypass handle."""

    manifest: CapabilityManifest
    trust_tier: CapabilityTrustTier
    kind: CapabilityKind
    network_required: bool
    allowed_network_domains: tuple[str, ...]


def request_fingerprint(request: Any) -> str:
    """Hash a bounded request without depending on a transport protocol."""

    if hasattr(request, "model_dump"):
        payload = request.model_dump(mode="json")
    elif hasattr(request, "__dict__"):
        payload = request.__dict__
    else:
        payload = request
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _invocation_id(request: Any, explicit: str | None) -> str:
    value = explicit or getattr(request, "invocation_id", None)
    if not value and isinstance(request, dict):
        value = request.get("invocation_id")
    if not isinstance(value, str) or not value:
        raise ValueError("capability invocation requires invocation_id")
    return value


class CapabilityRegistry:
    """Registry and policy boundary for all capability adapter kinds."""

    def __init__(self, *, allow_network: bool = False):
        self.allow_network = allow_network
        self._registrations: dict[str, CapabilityRegistration] = {}
        self._invocations: dict[tuple[str, str], tuple[str, CapabilityInvocation]] = {}

    @staticmethod
    def _key(manifest: CapabilityManifest) -> str:
        return f"{manifest.name}@{manifest.version}"

    def register(
        self,
        manifest: CapabilityManifest,
        adapter: CapabilityAdapter,
        *,
        trust_tier: CapabilityTrustTier,
        kind: CapabilityKind | str | None = None,
        network_required: bool | None = None,
        allowed_network_domains: list[str] | tuple[str, ...] | None = None,
    ) -> CapabilityRegistrationView:
        """Register an adapter with an operator-owned trust assignment."""

        registration_kind = CapabilityKind(kind or manifest.kind)
        key = self._key(manifest)
        if key in self._registrations:
            raise CapabilityRegistrationError(f"duplicate capability registration: {key}")
        if not isinstance(trust_tier, CapabilityTrustTier):
            trust_tier = CapabilityTrustTier(trust_tier)
        domains = tuple(allowed_network_domains or ())
        registration = CapabilityRegistration(
            manifest=manifest,
            adapter=adapter,
            trust_tier=trust_tier,
            kind=registration_kind,
            network_required=(
                manifest.network_required if network_required is None else network_required
            ),
            allowed_network_domains=domains,
        )
        self._registrations[key] = registration
        return CapabilityRegistrationView(
            manifest=manifest,
            trust_tier=trust_tier,
            kind=registration_kind,
            network_required=registration.network_required,
            allowed_network_domains=domains,
        )

    def list(self) -> list[CapabilityRegistrationView]:
        return [
            CapabilityRegistrationView(
                manifest=item.manifest,
                trust_tier=item.trust_tier,
                kind=item.kind,
                network_required=item.network_required,
                allowed_network_domains=item.allowed_network_domains,
            )
            for item in self._registrations.values()
        ]

    def _receipt(
        self,
        registration: CapabilityRegistration,
        invocation_id: str,
        fingerprint: str,
        status: CapabilityReceiptStatus,
        *,
        candidates: list[EvidenceCandidate] | None = None,
        value: Any = None,
        diagnostics: list[str] | None = None,
    ) -> CapabilityInvocationReceipt:
        return CapabilityInvocationReceipt(
            invocation_id=invocation_id,
            capability=registration.manifest.name,
            adapter_kind=registration.kind,
            adapter_version=registration.manifest.version,
            trust_tier=registration.trust_tier,
            status=status,
            outcome_status=status,
            request_fingerprint=fingerprint,
            candidate_count=len(candidates or []),
            structured_result_available=value is not None,
            diagnostics=diagnostics or [],
        )

    def _denied(
        self,
        registration: CapabilityRegistration,
        invocation_id: str,
        fingerprint: str,
    ) -> CapabilityInvocation:
        diagnostics = ["network access denied by default policy"]
        receipt = self._receipt(
            registration,
            invocation_id,
            fingerprint,
            CapabilityReceiptStatus.DENIED,
            diagnostics=diagnostics,
        )
        return CapabilityInvocation(receipt=receipt, diagnostics=diagnostics)

    def invoke(
        self,
        capability: str,
        request: Any,
        *,
        invocation_id: str | None = None,
    ) -> CapabilityInvocation:
        """Invoke only a registered adapter and enforce its operator policy.

        Every path -- success, contract violation, boundary violation, adapter
        exception, denied -- preserves the candidates the adapter actually emitted so
        that the invocation stays an honest record of what was produced. Admission is
        gated separately: only a ``completed`` outcome makes those candidates
        admissible (see ``CapabilityInvocationReceipt.candidates_admissible`` and
        ``CapabilityInvocation.admissible_candidates``).
        """

        matches = [
            item
            for item in self._registrations.values()
            if item.manifest.name == capability or self._key(item.manifest) == capability
        ]
        if not matches:
            raise CapabilityNotRegisteredError(f"capability is not registered: {capability}")
        if len(matches) > 1:
            versions = ", ".join(sorted(self._key(item.manifest) for item in matches))
            raise CapabilityAmbiguousReferenceError(
                f"capability reference is ambiguous, use name@version: {capability} "
                f"matches [{versions}]"
            )
        registration = matches[0]
        resolved_invocation_id = _invocation_id(request, invocation_id)
        fingerprint = request_fingerprint(request)
        replay_key = (self._key(registration.manifest), resolved_invocation_id)
        existing = self._invocations.get(replay_key)
        if existing is not None:
            existing_fingerprint, previous = existing
            if existing_fingerprint != fingerprint:
                raise CapabilityInvocationConflictError(
                    "invocation identity is already bound to another request"
                )
            original_outcome = previous.receipt.outcome_status or previous.receipt.status
            replay_receipt = previous.receipt.model_copy(
                update={
                    "status": CapabilityReceiptStatus.REPLAYED,
                    "outcome_status": original_outcome,
                    "updated_at": utc_now(),
                }
            )
            return replace(previous, receipt=replay_receipt)

        if registration.network_required and not self.allow_network:
            result = self._denied(registration, resolved_invocation_id, fingerprint)
            self._invocations[replay_key] = (fingerprint, result)
            return result

        context = CapabilityExecutionContext()
        try:
            invoke = registration.adapter.invoke
            raw = invoke(request, context)
            if not isinstance(raw, CapabilityAdapterResult):
                raise TypeError("adapter must return CapabilityAdapterResult")
            candidates = [*context.candidates, *raw.candidates]
            diagnostics = [*raw.diagnostics]
            value = raw.value
            status = raw.status
            if (
                raw.declared_trust_tier is not None
                and raw.declared_trust_tier != registration.trust_tier
            ):
                diagnostics.append(
                    "adapter trust tier declaration ignored; operator assignment remains "
                    "authoritative"
                )
            if registration.trust_tier == CapabilityTrustTier.CANDIDATE_ONLY:
                if value is not None and not candidates:
                    diagnostics.append("candidate_only adapter returned no EvidenceCandidate")
                    status = CapabilityReceiptStatus.FAILED
                    value = None
                else:
                    value = None
            elif value is None:
                diagnostics.append("compliant_structured adapter returned no structured result")
                status = CapabilityReceiptStatus.FAILED
            receipt = self._receipt(
                registration,
                resolved_invocation_id,
                fingerprint,
                status,
                candidates=candidates,
                value=value,
                diagnostics=diagnostics,
            )
            result = CapabilityInvocation(
                receipt=receipt,
                value=value,
                candidates=candidates,
                diagnostics=diagnostics,
            )
        except CapabilityBoundaryViolation as exc:
            diagnostics = [str(exc), f"blocked_write_attempts={context.blocked_write_attempts}"]
            candidates = context.candidates
            receipt = self._receipt(
                registration,
                resolved_invocation_id,
                fingerprint,
                CapabilityReceiptStatus.FAILED,
                candidates=candidates,
                diagnostics=diagnostics,
            )
            result = CapabilityInvocation(
                receipt=receipt, candidates=candidates, diagnostics=diagnostics
            )
        except Exception as exc:
            diagnostics = [f"adapter failure: {type(exc).__name__}: {exc}"]
            candidates = context.candidates
            receipt = self._receipt(
                registration,
                resolved_invocation_id,
                fingerprint,
                CapabilityReceiptStatus.FAILED,
                candidates=candidates,
                diagnostics=diagnostics,
            )
            result = CapabilityInvocation(
                receipt=receipt, candidates=candidates, diagnostics=diagnostics
            )
        self._invocations[replay_key] = (fingerprint, result)
        return result


class PaperSearchCapabilityAdapterBridge:
    """Expose the A1 Paper Search adapter through the A4 context boundary."""

    def __init__(self, legacy_adapter: Any):
        self.legacy_adapter = legacy_adapter

    def invoke(
        self,
        request: Any,
        context: CapabilityExecutionContext,
    ) -> CapabilityAdapterResult:
        invocation = self.legacy_adapter.invoke(request)
        for candidate in getattr(invocation, "evidence_candidates", []):
            context.emit_candidate(candidate)
        receipt = invocation.receipt
        outcome = getattr(receipt, "outcome_status", None) or getattr(receipt, "status", None)
        status_map = {
            "completed": CapabilityReceiptStatus.COMPLETED,
            "completed_empty": CapabilityReceiptStatus.COMPLETED,
            "replayed": CapabilityReceiptStatus.REPLAYED,
            "unknown_outcome": CapabilityReceiptStatus.UNKNOWN,
            "failed": CapabilityReceiptStatus.FAILED,
        }
        status = status_map.get(str(outcome), CapabilityReceiptStatus.FAILED)
        papers = list(getattr(invocation, "papers", []))
        return CapabilityAdapterResult(
            value=papers or None,
            diagnostics=[str(item) for item in getattr(invocation, "diagnostics", [])],
            status=status,
        )


__all__ = [
    "CapabilityAdapter",
    "CapabilityAdapterResult",
    "CapabilityAmbiguousReferenceError",
    "CapabilityBoundaryViolation",
    "CapabilityExecutionContext",
    "CapabilityInvocation",
    "CapabilityInvocationConflictError",
    "CapabilityInvocationReceipt",
    "CapabilityKind",
    "CapabilityNotRegisteredError",
    "PaperSearchCapabilityAdapterBridge",
    "CapabilityReceiptStatus",
    "CapabilityRegistration",
    "CapabilityRegistrationView",
    "CapabilityRegistrationError",
    "CapabilityRegistry",
    "CapabilityTrustTier",
    "request_fingerprint",
]
