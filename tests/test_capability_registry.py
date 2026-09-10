from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from autoresearch.capability_registry import (
    CapabilityAdapterResult,
    CapabilityAmbiguousReferenceError,
    CapabilityInvocationConflictError,
    CapabilityKind,
    CapabilityNotRegisteredError,
    CapabilityReceiptStatus,
    CapabilityRegistrationError,
    CapabilityRegistry,
    CapabilityTrustTier,
    PaperSearchCapabilityAdapterBridge,
    request_fingerprint,
)
from autoresearch.contracts import EvidenceCandidate
from autoresearch.invocation_contracts import CapabilityManifest, PaperSearchRequest


@dataclass
class Request:
    invocation_id: str
    query: str


def candidate() -> EvidenceCandidate:
    return EvidenceCandidate(
        candidate_id="candidate-1",
        project_id="project-1",
        run_id="run-1",
        invocation_id="invocation-1",
        claim="A fixture candidate exists.",
        source_id="source-1",
        independent_source="fixture:source-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def candidate_named(candidate_id: str) -> EvidenceCandidate:
    return EvidenceCandidate(
        candidate_id=candidate_id,
        project_id="project-1",
        run_id="run-1",
        invocation_id="invocation-1",
        claim="A fixture candidate exists.",
        source_id="source-1",
        independent_source="fixture:source-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class CandidateAdapter:
    def __init__(self, *, declared_tier: CapabilityTrustTier | None = None):
        self.calls = 0
        self.declared_tier = declared_tier

    def invoke(self, request: Request, context):
        self.calls += 1
        context.emit_candidate(candidate())
        return CapabilityAdapterResult(declared_trust_tier=self.declared_tier)


class StructuredAdapter:
    def __init__(self):
        self.calls = 0

    def invoke(self, request: Request, context):
        self.calls += 1
        return CapabilityAdapterResult(value={"query": request.query, "kind": "structured"})


class CandidateOnlyViolationAdapter:
    def __init__(self):
        self.calls = 0

    def invoke(self, request: Request, context):
        self.calls += 1
        context.write_evidence({"forbidden": True})
        return CapabilityAdapterResult()


class GateViolationAdapter:
    def __init__(self):
        self.calls = 0

    def invoke(self, request: Request, context):
        self.calls += 1
        context.write_gate_decision({"forbidden": True})
        return CapabilityAdapterResult()


class NetworkAdapter:
    def __init__(self):
        self.calls = 0

    def invoke(self, request: Request, context):
        self.calls += 1
        return CapabilityAdapterResult(value={"network": True})


class CandidateWithValueAdapter:
    def __init__(self):
        self.calls = 0

    def invoke(self, request: Request, context):
        self.calls += 1
        context.emit_candidate(candidate())
        return CapabilityAdapterResult(value={"leaked": "structured payload"})


class BoomAdapter:
    def __init__(self):
        self.calls = 0

    def invoke(self, request: Request, context):
        self.calls += 1
        raise RuntimeError("provider exploded")


class WrongShapeAdapter:
    def __init__(self):
        self.calls = 0

    def invoke(self, request: Request, context):
        self.calls += 1
        return {"untyped": "payload"}


class EchoRequestAdapter:
    def __init__(self):
        self.calls = 0

    def invoke(self, request, context):
        self.calls += 1
        return CapabilityAdapterResult(value={"echo": request})


class EmitThenBoomAdapter:
    """Emits candidates and then raises: the raw record must survive the failure."""

    def __init__(self, emitted: int = 2):
        self.calls = 0
        self.emitted = emitted

    def invoke(self, request: Request, context):
        self.calls += 1
        for index in range(1, self.emitted + 1):
            context.emit_candidate(candidate_named(f"candidate-{index}"))
        raise RuntimeError("provider exploded after emitting")


class EmitThenViolateAdapter:
    """Emits a candidate and then attempts a forbidden direct write."""

    def __init__(self):
        self.calls = 0

    def invoke(self, request: Request, context):
        self.calls += 1
        context.emit_candidate(candidate())
        context.write_evidence({"forbidden": True})
        return CapabilityAdapterResult()


def manifest(
    name: str,
    *,
    kind: str = "native",
    network_required: bool = False,
    version: str = "1",
):
    return CapabilityManifest(
        name=name,
        kind=kind,
        version=version,
        evidence_mode="compliant_structured",
        network_required=network_required,
    )


def test_candidate_only_positive_is_candidate_and_receipt_is_operator_assigned():
    adapter = CandidateAdapter(declared_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED)
    registry = CapabilityRegistry()
    registry.register(
        manifest("candidate", kind="mcp"),
        adapter,
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
        kind=CapabilityKind.MCP,
    )

    result = registry.invoke("candidate", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.COMPLETED
    assert result.receipt.trust_tier == CapabilityTrustTier.CANDIDATE_ONLY
    assert result.candidates == [candidate()]
    assert result.value is None
    assert any("operator assignment" in item for item in result.diagnostics)
    assert adapter.calls == 1


def test_candidate_only_rejects_direct_evidence_write():
    adapter = CandidateOnlyViolationAdapter()
    registry = CapabilityRegistry()
    registry.register(manifest("candidate"), adapter, trust_tier=CapabilityTrustTier.CANDIDATE_ONLY)

    result = registry.invoke("candidate", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.FAILED
    assert result.candidates == []
    assert any("cannot write EvidenceItem" in item for item in result.diagnostics)
    assert any("blocked_write_attempts=1" in item for item in result.diagnostics)
    assert adapter.calls == 1


def test_adapter_context_blocks_direct_gate_write():
    adapter = GateViolationAdapter()
    registry = CapabilityRegistry()
    registry.register(manifest("candidate"), adapter, trust_tier=CapabilityTrustTier.CANDIDATE_ONLY)

    result = registry.invoke("candidate", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.FAILED
    assert any("cannot write GateDecision" in item for item in result.diagnostics)
    assert any("blocked_write_attempts=1" in item for item in result.diagnostics)
    assert adapter.calls == 1


def test_compliant_structured_positive_returns_typed_boundary_result():
    adapter = StructuredAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("structured", kind="skill"),
        adapter,
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
        kind=CapabilityKind.SKILL,
    )

    result = registry.invoke("structured", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.COMPLETED
    assert result.receipt.trust_tier == CapabilityTrustTier.COMPLIANT_STRUCTURED
    assert result.value == {"query": "query", "kind": "structured"}
    assert result.receipt.structured_result_available is True
    assert adapter.calls == 1


def test_compliant_structured_negative_requires_structured_result():
    adapter = CandidateAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("structured", kind="plugin"),
        adapter,
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
        kind=CapabilityKind.PLUGIN,
    )

    result = registry.invoke("structured", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.FAILED
    assert result.value is None
    assert any("no structured result" in item for item in result.diagnostics)


def test_network_is_denied_before_adapter_call_by_default():
    adapter = NetworkAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("remote", kind="mcp", network_required=True),
        adapter,
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
        kind=CapabilityKind.MCP,
    )

    result = registry.invoke("remote", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.DENIED
    assert "network access denied" in result.diagnostics[0]
    assert adapter.calls == 0


def test_unregistered_capability_invocation_is_rejected():
    registry = CapabilityRegistry()
    with pytest.raises(CapabilityNotRegisteredError, match="not registered"):
        registry.invoke("ghost", Request("invocation-1", "query"))


def test_operator_explicit_allow_network_reaches_adapter():
    adapter = StructuredAdapter()
    registry = CapabilityRegistry(allow_network=True)
    registry.register(
        manifest("remote-structured", kind="mcp", network_required=True),
        adapter,
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
        kind=CapabilityKind.MCP,
    )

    result = registry.invoke("remote-structured", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.COMPLETED
    assert result.value == {"query": "query", "kind": "structured"}
    assert adapter.calls == 1


def test_same_invocation_replays_and_conflicting_fingerprint_is_rejected():
    adapter = StructuredAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("structured"),
        adapter,
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
    )
    first = registry.invoke("structured", Request("invocation-1", "query"))
    replay = registry.invoke("structured", Request("invocation-1", "query"))

    assert first.receipt.status == CapabilityReceiptStatus.COMPLETED
    assert replay.receipt.status == CapabilityReceiptStatus.REPLAYED
    assert replay.value == first.value
    assert adapter.calls == 1

    with pytest.raises(CapabilityInvocationConflictError):
        registry.invoke("structured", Request("invocation-1", "different"))


def test_native_mcp_skill_and_plugin_share_one_registry_boundary():
    for kind in CapabilityKind:
        registry = CapabilityRegistry()
        adapter = StructuredAdapter()
        registry.register(
            manifest(f"{kind.value}-capability", kind=kind.value),
            adapter,
            trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
            kind=kind,
        )

        result = registry.invoke(f"{kind.value}-capability", Request("invocation-1", "query"))

        assert result.receipt.adapter_kind == kind
        assert result.receipt.status == CapabilityReceiptStatus.COMPLETED
        assert result.value["kind"] == "structured"


def test_a1_paper_search_adapter_can_enter_a4_through_explicit_bridge():
    class LegacyAdapter:
        def __init__(self):
            self.calls = 0

        def invoke(self, request):
            self.calls += 1
            return SimpleNamespace(
                receipt=SimpleNamespace(status="completed", outcome_status="completed"),
                papers=[{"title": "normalized paper"}],
                evidence_candidates=[candidate()],
                diagnostics=[],
            )

    legacy = LegacyAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("paper_search", kind="native"),
        PaperSearchCapabilityAdapterBridge(legacy),
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
    )

    result = registry.invoke("paper_search", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.COMPLETED
    assert result.candidates == [candidate()]
    assert result.value is None
    assert legacy.calls == 1


def test_duplicate_registration_is_rejected():
    registry = CapabilityRegistry()
    registry.register(
        manifest("duplicate"),
        StructuredAdapter(),
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
    )
    with pytest.raises(CapabilityRegistrationError, match="duplicate capability registration"):
        registry.register(
            manifest("duplicate"),
            StructuredAdapter(),
            trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
        )


def test_registry_listing_does_not_expose_raw_adapter_bypass():
    registry = CapabilityRegistry()
    registration = registry.register(
        manifest("structured"),
        StructuredAdapter(),
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
    )

    assert not hasattr(registration, "adapter")
    assert not hasattr(registry.list()[0], "adapter")


def test_candidate_only_structured_value_without_candidate_fails():
    adapter = StructuredAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("candidate"),
        adapter,
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
    )

    result = registry.invoke("candidate", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.FAILED
    assert result.receipt.outcome_status == CapabilityReceiptStatus.FAILED
    assert result.value is None
    assert result.candidates == []
    assert any("no EvidenceCandidate" in item for item in result.diagnostics)


def test_candidate_only_drops_structured_value_when_candidate_present():
    adapter = CandidateWithValueAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("candidate"),
        adapter,
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
    )

    result = registry.invoke("candidate", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.COMPLETED
    assert result.receipt.structured_result_available is False
    assert result.value is None
    assert result.candidates == [candidate()]


def test_adapter_exception_is_reported_as_failed_receipt():
    adapter = BoomAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("boom"),
        adapter,
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
    )

    result = registry.invoke("boom", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.FAILED
    assert result.receipt.outcome_status == CapabilityReceiptStatus.FAILED
    assert result.value is None
    assert any("RuntimeError" in item for item in result.diagnostics)
    assert adapter.calls == 1


def test_failed_and_denied_replays_preserve_outcome_status():
    failed_adapter = BoomAdapter()
    failed_registry = CapabilityRegistry()
    failed_registry.register(
        manifest("boom"),
        failed_adapter,
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
    )
    first_failure = failed_registry.invoke("boom", Request("invocation-1", "query"))
    replayed_failure = failed_registry.invoke("boom", Request("invocation-1", "query"))

    assert first_failure.receipt.outcome_status == CapabilityReceiptStatus.FAILED
    assert replayed_failure.receipt.status == CapabilityReceiptStatus.REPLAYED
    assert replayed_failure.receipt.outcome_status == CapabilityReceiptStatus.FAILED
    assert failed_adapter.calls == 1

    network_adapter = NetworkAdapter()
    denied_registry = CapabilityRegistry()
    denied_registry.register(
        manifest("remote", kind="mcp", network_required=True),
        network_adapter,
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
        kind=CapabilityKind.MCP,
    )
    first_denial = denied_registry.invoke("remote", Request("invocation-2", "query"))
    replayed_denial = denied_registry.invoke("remote", Request("invocation-2", "query"))

    assert first_denial.receipt.outcome_status == CapabilityReceiptStatus.DENIED
    assert replayed_denial.receipt.status == CapabilityReceiptStatus.REPLAYED
    assert replayed_denial.receipt.outcome_status == CapabilityReceiptStatus.DENIED
    assert network_adapter.calls == 0


def test_ambiguous_bare_name_requires_version_qualified_invocation():
    registry = CapabilityRegistry()
    for version in ("1", "2"):
        registry.register(
            manifest("paper_search", version=version),
            StructuredAdapter(),
            trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
        )

    with pytest.raises(CapabilityAmbiguousReferenceError, match="paper_search@1, paper_search@2"):
        registry.invoke("paper_search", Request("invocation-1", "query"))

    qualified = registry.invoke("paper_search@2", Request("invocation-2", "query"))
    assert qualified.receipt.status == CapabilityReceiptStatus.COMPLETED
    assert qualified.receipt.adapter_version == "2"


def test_version_qualified_reference_to_unregistered_version_is_rejected():
    registry = CapabilityRegistry()
    with pytest.raises(CapabilityNotRegisteredError):
        registry.invoke("paper_search@9", Request("invocation-1", "query"))


def test_registration_accepts_plain_string_trust_tier():
    registry = CapabilityRegistry()
    view = registry.register(
        manifest("candidate"),
        StructuredAdapter(),
        trust_tier="candidate_only",
    )

    assert view.trust_tier == CapabilityTrustTier.CANDIDATE_ONLY


def test_adapter_returning_untyped_result_is_failed_receipt():
    adapter = WrongShapeAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("untyped"),
        adapter,
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
    )

    result = registry.invoke("untyped", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.FAILED
    assert result.receipt.outcome_status == CapabilityReceiptStatus.FAILED
    assert result.value is None
    assert any("TypeError" in item for item in result.diagnostics)


def test_missing_invocation_id_is_rejected_before_adapter_call():
    adapter = EchoRequestAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("echo"),
        adapter,
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
    )

    with pytest.raises(ValueError, match="invocation_id"):
        registry.invoke("echo", {"query": "no identity"})

    assert adapter.calls == 0


def test_mapping_request_can_supply_invocation_id():
    adapter = EchoRequestAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("echo"),
        adapter,
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
    )

    result = registry.invoke("echo", {"invocation_id": "invocation-7", "query": "q"})

    assert result.receipt.invocation_id == "invocation-7"
    assert result.receipt.status == CapabilityReceiptStatus.COMPLETED


def test_request_fingerprint_handles_pydantic_and_raw_requests():
    typed = PaperSearchRequest(
        project_id="project-1",
        run_id="run-1",
        invocation_id="invocation-1",
        query="typed query",
    )
    typed_fingerprint = request_fingerprint(typed)

    assert len(typed_fingerprint) == 64
    assert typed_fingerprint == request_fingerprint(
        PaperSearchRequest(
            project_id="project-1",
            run_id="run-1",
            invocation_id="invocation-1",
            query="typed query",
        )
    )
    assert typed_fingerprint != request_fingerprint(
        PaperSearchRequest(
            project_id="project-1",
            run_id="run-1",
            invocation_id="invocation-1",
            query="different query",
        )
    )
    assert len(request_fingerprint("raw payload")) == 64


def test_failed_adapter_keeps_raw_candidates_but_marks_them_inadmissible():
    adapter = EmitThenBoomAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("emit-then-boom"),
        adapter,
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
    )

    failure = registry.invoke("emit-then-boom", Request("invocation-1", "query"))

    assert failure.receipt.status == CapabilityReceiptStatus.FAILED
    assert failure.receipt.outcome_status == CapabilityReceiptStatus.FAILED
    assert failure.receipt.candidate_count == 2
    assert failure.candidates == [
        candidate_named("candidate-1"),
        candidate_named("candidate-2"),
    ]
    assert failure.receipt.candidates_admissible is False
    assert failure.admissible_candidates == []

    replay = registry.invoke("emit-then-boom", Request("invocation-1", "query"))

    assert replay.receipt.status == CapabilityReceiptStatus.REPLAYED
    assert replay.receipt.outcome_status == CapabilityReceiptStatus.FAILED
    assert replay.receipt.candidates_admissible is False
    assert replay.admissible_candidates == []
    assert adapter.calls == 1


def test_boundary_violation_keeps_raw_candidates_but_marks_them_inadmissible():
    adapter = EmitThenViolateAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("emit-then-violate"),
        adapter,
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
    )

    result = registry.invoke("emit-then-violate", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.FAILED
    assert result.receipt.candidate_count == 1
    assert result.candidates == [candidate()]
    assert result.receipt.candidates_admissible is False
    assert result.admissible_candidates == []
    assert any("blocked_write_attempts=1" in item for item in result.diagnostics)
    assert adapter.calls == 1


def test_contract_violation_keeps_raw_candidates_but_marks_them_inadmissible():
    adapter = CandidateAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("emit-no-structured"),
        adapter,
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
    )

    result = registry.invoke("emit-no-structured", Request("invocation-1", "query"))

    assert result.receipt.status == CapabilityReceiptStatus.FAILED
    assert result.receipt.candidate_count == 1
    assert result.candidates == [candidate()]
    assert result.receipt.candidates_admissible is False
    assert result.admissible_candidates == []
    assert any("no structured result" in item for item in result.diagnostics)


def test_completed_candidates_are_admissible_and_replay_preserves_admissibility():
    adapter = CandidateAdapter()
    registry = CapabilityRegistry()
    registry.register(
        manifest("candidate"),
        adapter,
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
    )

    first = registry.invoke("candidate", Request("invocation-1", "query"))
    replay = registry.invoke("candidate", Request("invocation-1", "query"))

    assert first.receipt.status == CapabilityReceiptStatus.COMPLETED
    assert first.receipt.candidates_admissible is True
    assert first.admissible_candidates == [candidate()]

    assert replay.receipt.status == CapabilityReceiptStatus.REPLAYED
    assert replay.receipt.outcome_status == CapabilityReceiptStatus.COMPLETED
    assert replay.receipt.candidates_admissible is True
    assert replay.admissible_candidates == [candidate()]
    assert adapter.calls == 1


def test_denied_and_unknown_outcomes_are_not_admissible():
    network_adapter = NetworkAdapter()
    denied_registry = CapabilityRegistry()
    denied_registry.register(
        manifest("remote", kind="mcp", network_required=True),
        network_adapter,
        trust_tier=CapabilityTrustTier.COMPLIANT_STRUCTURED,
        kind=CapabilityKind.MCP,
    )

    denial = denied_registry.invoke("remote", Request("invocation-1", "query"))

    assert denial.receipt.status == CapabilityReceiptStatus.DENIED
    assert denial.receipt.candidate_count == 0
    assert denial.receipt.candidates_admissible is False
    assert denial.admissible_candidates == []

    class UnknownOutcomeLegacyAdapter:
        def __init__(self):
            self.calls = 0

        def invoke(self, request):
            self.calls += 1
            return SimpleNamespace(
                receipt=SimpleNamespace(
                    status="unknown_outcome",
                    outcome_status="unknown_outcome",
                ),
                papers=[],
                evidence_candidates=[candidate()],
                diagnostics=[],
            )

    legacy = UnknownOutcomeLegacyAdapter()
    unknown_registry = CapabilityRegistry()
    unknown_registry.register(
        manifest("paper_search", kind="native"),
        PaperSearchCapabilityAdapterBridge(legacy),
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
    )

    unknown = unknown_registry.invoke("paper_search", Request("invocation-2", "query"))

    assert unknown.receipt.status == CapabilityReceiptStatus.UNKNOWN
    assert unknown.receipt.outcome_status == CapabilityReceiptStatus.UNKNOWN
    assert unknown.receipt.candidate_count == 1
    assert unknown.candidates == [candidate()]
    assert unknown.receipt.candidates_admissible is False
    assert unknown.admissible_candidates == []
