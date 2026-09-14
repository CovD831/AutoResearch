from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field, computed_field

from autoresearch.contracts import (
    EvidenceCandidate,
    InvocationCost,
    TokenUsage,
    utc_now,
)
from autoresearch.invocation_contracts import (
    CapabilityLifecycleStatus,
    CapabilityManifest,
)


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


class CapabilityManifestInvalidError(CapabilityRegistrationError):
    """The registry rejected a manifest that violates the L2 contract.

    Subclasses ``CapabilityRegistrationError`` so existing callers that catch the
    registration error keep working; the narrower type exists so a caller can
    distinguish "your manifest is incomplete" from "that name is already taken".
    """


_REF_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def validate_manifest(manifest: CapabilityManifest) -> list[str]:
    """Return the L2-contract violations of ``manifest``; empty means admissible.

    This is the single validation entry point the registration boundary calls. It
    deliberately does **not** do filesystem or import work -- a registry that
    reaches into the filesystem is no longer a pure policy boundary. Fixture
    existence is asserted by the contract test instead.

    The schema refs are checked for shape, not resolved against a central name
    table, on purpose: a central table would be a file every new capability has to
    edit, which is exactly the "plugging in one option touches the core" failure
    the catalog work exists to remove.
    """

    problems: list[str] = []

    if not manifest.name:
        problems.append("manifest.name is required")
    if not manifest.version:
        problems.append("manifest.version is required")
    if not manifest.manifest_id:
        problems.append("manifest.manifest_id is required")
    if not manifest.contract_version:
        problems.append("manifest.contract_version is required")

    for field_name, ref in (
        ("input_schema_ref", manifest.input_schema_ref),
        ("output_schema_ref", manifest.output_schema_ref),
    ):
        if not ref:
            problems.append(f"manifest.{field_name} is required")
        elif not _REF_PATTERN.match(ref):
            problems.append(f"manifest.{field_name} is not a contract name: {ref!r}")

    if manifest.network_required and not manifest.allowed_network_domains:
        problems.append(
            "manifest.network_required=True requires a non-empty "
            "allowed_network_domains (the allowlist must not be empty while egress "
            "is declared)"
        )

    if manifest.kind not in {item.value for item in CapabilityKind}:
        problems.append(f"manifest.kind is not a known adapter kind: {manifest.kind!r}")

    if manifest.lifecycle_status is CapabilityLifecycleStatus.RETIRED:
        problems.append("manifest.lifecycle_status=retired must not be registered")

    if manifest.is_restricted_license and not manifest.selection_restricted_reason:
        problems.append(
            f"manifest.license_spdx={manifest.license_spdx!r} is a restricted "
            "license and requires selection_restricted_reason"
        )

    return problems


def manifest_warnings(manifest: CapabilityManifest) -> list[str]:
    """Non-fatal notices about a manifest that is nevertheless admissible.

    Kept separate from ``validate_manifest`` on purpose: a warning must never be
    able to reject a registration, or the two channels blur and callers start
    treating deprecation as an error.
    """

    notices: list[str] = []
    if manifest.lifecycle_status is CapabilityLifecycleStatus.DEPRECATED:
        notices.append(
            "manifest.lifecycle_status=deprecated: this option is registered but "
            "should not be selected for new work"
        )
    if manifest.supports_offline and manifest.network_required:
        notices.append(
            "manifest declares supports_offline=True while network_required=True: "
            "the offline claim is only meaningful if the network path is optional"
        )
    return notices


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

    # --- manifest identity, carried so a durable receipt never needs the manifest
    manifest_id: str | None = Field(default=None, max_length=200)
    contract_version: str = Field(default="l2", max_length=50)
    input_schema_ref: str | None = Field(default=None, max_length=200)
    output_schema_ref: str | None = Field(default=None, max_length=200)
    license_spdx: str | None = Field(default=None, max_length=100)

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
    overridden_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class CapabilityRegistrationView:
    """Public registration metadata without a raw adapter bypass handle.

    ``overridden_fields`` names every place a caller passed an explicit value that
    disagreed with the manifest's own declaration. It exists so the two sources of
    truth cannot silently diverge: an override is allowed, but it is never quiet.

    ``warnings`` carries non-fatal manifest notices (e.g. deprecated). It is
    separate from ``overridden_fields`` because it describes the manifest itself,
    not the registration call.
    """

    manifest: CapabilityManifest
    trust_tier: CapabilityTrustTier
    kind: CapabilityKind
    network_required: bool
    allowed_network_domains: tuple[str, ...]
    overridden_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def manifest_id(self) -> str | None:
        return self.manifest.manifest_id

    @property
    def contract_version(self) -> str:
        return self.manifest.contract_version

    @property
    def input_schema_ref(self) -> str | None:
        return self.manifest.input_schema_ref

    @property
    def output_schema_ref(self) -> str | None:
        return self.manifest.output_schema_ref

    @property
    def license_spdx(self) -> str | None:
        return self.manifest.license_spdx

    @property
    def supports_offline(self) -> bool:
        return self.manifest.supports_offline


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
        """Register an adapter with an operator-owned trust assignment.

        The manifest is validated **before** anything else, so an incomplete
        manifest never reaches an adapter and never takes a registry slot.

        ``kind`` / ``network_required`` / ``allowed_network_domains`` default to the
        manifest's own declaration. Passing them explicitly is still supported, but
        a value that disagrees with the manifest is recorded in
        ``overridden_fields`` instead of silently winning -- the manifest stays the
        single source of truth and the divergence stays visible.
        """

        problems = validate_manifest(manifest)
        if problems:
            raise CapabilityManifestInvalidError(
                f"capability manifest is not admissible ({manifest.name}@"
                f"{manifest.version}): " + "; ".join(problems)
            )

        registration_kind = (
            CapabilityKind(manifest.kind) if kind is None else CapabilityKind(kind)
        )

        if not isinstance(trust_tier, CapabilityTrustTier):
            trust_tier = CapabilityTrustTier(trust_tier)

        if network_required is None:
            resolved_network_required = manifest.network_required
        else:
            resolved_network_required = network_required

        if allowed_network_domains is None:
            domains = tuple(manifest.allowed_network_domains)
        else:
            domains = tuple(allowed_network_domains)

        overridden = tuple(
            name
            for name, declared, supplied in (
                ("kind", manifest.kind, registration_kind.value),
                ("network_required", manifest.network_required, resolved_network_required),
                ("allowed_network_domains", tuple(manifest.allowed_network_domains), domains),
            )
            if supplied != declared
        )

        key = self._key(manifest)
        if key in self._registrations:
            raise CapabilityRegistrationError(f"duplicate capability registration: {key}")

        registration = CapabilityRegistration(
            manifest=manifest,
            adapter=adapter,
            trust_tier=trust_tier,
            kind=registration_kind,
            network_required=resolved_network_required,
            allowed_network_domains=domains,
            overridden_fields=overridden,
            warnings=tuple(manifest_warnings(manifest)),
        )
        self._registrations[key] = registration
        return CapabilityRegistrationView(
            manifest=manifest,
            trust_tier=trust_tier,
            kind=registration_kind,
            network_required=resolved_network_required,
            allowed_network_domains=domains,
            overridden_fields=overridden,
            warnings=registration.warnings,
        )

    def list(self) -> list[CapabilityRegistrationView]:
        return [
            CapabilityRegistrationView(
                manifest=item.manifest,
                trust_tier=item.trust_tier,
                kind=item.kind,
                network_required=item.network_required,
                allowed_network_domains=item.allowed_network_domains,
                overridden_fields=item.overridden_fields,
                warnings=item.warnings,
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
            manifest_id=registration.manifest.manifest_id,
            contract_version=registration.manifest.contract_version,
            input_schema_ref=registration.manifest.input_schema_ref,
            output_schema_ref=registration.manifest.output_schema_ref,
            license_spdx=registration.manifest.license_spdx,
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
    "CapabilityManifestInvalidError",
    "CapabilityNotRegisteredError",
    "PaperSearchCapabilityAdapterBridge",
    "CapabilityReceiptStatus",
    "CapabilityRegistration",
    "CapabilityRegistrationView",
    "CapabilityRegistrationError",
    "CapabilityRegistry",
    "CapabilityTrustTier",
    "manifest_warnings",
    "request_fingerprint",
    "validate_manifest",
]
