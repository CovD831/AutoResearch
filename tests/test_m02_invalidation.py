"""M02-09 / K8 ``InvalidationPropagation`` tests (L-02 lane).

See ``tests/test_m02_prefetch.py`` for why discriminating power is established
by mutation rather than by a pre-fix baseline run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from autoresearch.contracts import GraphEdge, GraphEdgeKind, KnowledgePartition
from autoresearch.external_sources import SourceStatus
from autoresearch.invalidation import (
    INVALIDATION_KIND,
    PERMANENT_BLOCK_REASONS,
    BrokenPropagationError,
    InvalidationAction,
    InvalidationContractError,
    InvalidationPropagation,
    InvalidationReason,
    InvalidationService,
    action_for_reason,
    reason_from_source_status,
)
from autoresearch.storage import RecordStore

PERMANENT_REASONS = (
    InvalidationReason.FORGED,
    InvalidationReason.PAYWALL_BYPASS,
    InvalidationReason.UNAPPROVED_EGRESS,
)


def _service(tmp_path: Path) -> InvalidationService:
    return InvalidationService(RecordStore(tmp_path / "invalidation.sqlite3"))


def _edge(source: str, target: str, evidence_ids: list[str] | None = None) -> GraphEdge:
    return GraphEdge(
        partition=KnowledgePartition.PAPERS,
        source_id=source,
        target_id=target,
        relation=GraphEdgeKind.CITES,
        evidence_ids=evidence_ids or [],
    )


def _wire_dependency(service: InvalidationService, evidence_id: str) -> None:
    """evidence -> claim -> gate, declared through graph edges."""

    service.store.put(
        "graph_edge",
        "e1",
        _edge("claim_alpha", "gate_release", evidence_ids=[evidence_id]),
        partition="papers",
    )


# ---------------------------------------------------------------------------
# K8-1 permanent block is not exemptible (N-3)
# ---------------------------------------------------------------------------


def test_permanent_block_table_contains_exactly_the_three_reasons() -> None:
    assert frozenset(PERMANENT_REASONS) == PERMANENT_BLOCK_REASONS


@pytest.mark.parametrize("reason", PERMANENT_REASONS)
def test_n3_permanent_reason_with_recompute_is_rejected(reason: InvalidationReason) -> None:
    """N-3: ``forged`` + ``recompute`` must be refused, not quietly recorded."""

    with pytest.raises(ValidationError):
        InvalidationPropagation(
            source_evidence_id="ev-forged",
            reason=reason,
            affected_claims=["claim_alpha"],
            action=InvalidationAction.RECOMPUTE,
        )


@pytest.mark.parametrize("reason", PERMANENT_REASONS)
def test_service_maps_a_permanent_reason_to_permanent_block(
    tmp_path: Path, reason: InvalidationReason
) -> None:
    """The service derives ``action`` from the table, so no request can downgrade it."""

    service = _service(tmp_path)
    _wire_dependency(service, "ev-1")
    record = service.propagate(source_evidence_id="ev-1", reason=reason)
    assert record.action is InvalidationAction.PERMANENT_BLOCK


@pytest.mark.parametrize(
    "reason", (InvalidationReason.RETRACTED, InvalidationReason.EXPIRED)
)
def test_recomputable_reasons_map_to_recompute(reason: InvalidationReason) -> None:
    assert action_for_reason(reason) is InvalidationAction.RECOMPUTE


@pytest.mark.parametrize("reason", PERMANENT_REASONS)
def test_permanent_reasons_map_to_permanent_block(reason: InvalidationReason) -> None:
    assert action_for_reason(reason) is InvalidationAction.PERMANENT_BLOCK


# ---------------------------------------------------------------------------
# K8-3 empty propagation is a broken chain (N-4)
# ---------------------------------------------------------------------------


def test_n4_empty_affected_claims_raises_on_the_model() -> None:
    """N-4: an empty claim set must raise, not return an empty success."""

    with pytest.raises(ValidationError):
        InvalidationPropagation(
            source_evidence_id="ev-1",
            reason=InvalidationReason.RETRACTED,
            affected_claims=[],
            action=InvalidationAction.RECOMPUTE,
        )


def test_n4_broken_chain_raises_instead_of_returning_nothing(tmp_path: Path) -> None:
    """A source with no dependent claim is a broken chain, not a no-op."""

    service = _service(tmp_path)
    with pytest.raises(BrokenPropagationError):
        service.propagate(
            source_evidence_id="ev-orphan",
            reason=InvalidationReason.RETRACTED,
        )
    assert service.store.list(INVALIDATION_KIND) == []


# ---------------------------------------------------------------------------
# K8-2 propagation walks to claims and gates
# ---------------------------------------------------------------------------


def test_k8_2_propagation_reaches_claims_and_gates(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _wire_dependency(service, "ev-1")
    record = service.propagate(source_evidence_id="ev-1", reason=InvalidationReason.RETRACTED)
    assert record.affected_claims == ["claim_alpha"]
    assert record.affected_gates == ["gate_release"]


def test_k8_2_propagation_is_persisted_and_audited(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _wire_dependency(service, "ev-1")
    record = service.propagate(
        source_evidence_id="ev-1",
        reason=InvalidationReason.EXPIRED,
        actor="tester",
    )
    stored = service.store.get(INVALIDATION_KIND, record.propagation_id)
    assert stored is not None
    assert stored["affected_claims"] == ["claim_alpha"]
    with service.store.connection() as connection:
        rows = connection.execute(
            "SELECT actor FROM audit_events WHERE event_type='invalidation.propagated'"
        ).fetchall()
    assert [row["actor"] for row in rows] == ["tester"]


def test_gates_may_be_empty_when_no_gate_depends_on_the_claim(tmp_path: Path) -> None:
    """K8-3 constrains claims only (deviation D-L02-03)."""

    service = _service(tmp_path)
    service.store.put("graph_edge", "e1", _edge("ev-1", "claim_beta"), partition="papers")
    record = service.propagate(source_evidence_id="ev-1", reason=InvalidationReason.RETRACTED)
    assert record.affected_claims == ["claim_beta"]
    assert record.affected_gates == []


def test_gate_ids_are_not_mistaken_for_claims(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.store.put(
        "graph_edge",
        "e1",
        _edge("ev-1", "gate_release"),
        partition="papers",
    )
    with pytest.raises(BrokenPropagationError):
        service.propagate(source_evidence_id="ev-1", reason=InvalidationReason.RETRACTED)


def test_traversal_is_scoped_to_the_requested_partitions(tmp_path: Path) -> None:
    """Without scoping, one partition's invalidation would reach another's claims.

    The unscoped mode is a documented hazard (see StoreClaimGraph); this test
    pins the *scoped* behaviour, which is what production wiring must use.
    """

    store = RecordStore(tmp_path / "invalidation.sqlite3")
    store.put(
        "graph_edge",
        "eA",
        _edge("ev-1", "claim_here"),
        partition="papers",
    )
    store.put(
        "graph_edge",
        "eB",
        _edge("ev-1", "claim_elsewhere"),
        partition="experiences",
    )
    service = InvalidationService(store, partitions=["papers"])
    record = service.propagate(source_evidence_id="ev-1", reason=InvalidationReason.RETRACTED)
    assert record.affected_claims == ["claim_here"]


# ---------------------------------------------------------------------------
# K8-2 derivation seam: plan (no side effects) vs record (persists)
# ---------------------------------------------------------------------------


def _count_audit_events(service: InvalidationService) -> int:
    with service.store.connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM audit_events WHERE event_type='invalidation.propagated'"
        ).fetchone()
    return row["n"]


def test_plan_derives_the_blast_radius_without_writing_anything(tmp_path: Path) -> None:
    """plan() must be side-effect free, so callers can validate before persisting."""

    service = _service(tmp_path)
    _wire_dependency(service, "ev-1")
    plan = service.plan(source_evidence_id="ev-1", reason=InvalidationReason.RETRACTED)
    assert plan.affected_claims == ["claim_alpha"]
    assert plan.affected_gates == ["gate_release"]
    assert plan.action is InvalidationAction.RECOMPUTE
    assert service.store.list(INVALIDATION_KIND) == []
    assert _count_audit_events(service) == 0


def test_record_persists_a_plan_and_audits_it(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _wire_dependency(service, "ev-1")
    plan = service.plan(source_evidence_id="ev-1", reason=InvalidationReason.RETRACTED)
    stored = service.record(plan, actor="tester")
    assert stored is plan
    assert service.store.get(INVALIDATION_KIND, plan.propagation_id) is not None
    assert _count_audit_events(service) == 1


def test_propagate_is_record_of_plan(tmp_path: Path) -> None:
    """The one-shot form keeps working; it is now a shorthand."""

    service = _service(tmp_path)
    _wire_dependency(service, "ev-1")
    record = service.propagate(source_evidence_id="ev-1", reason=InvalidationReason.EXPIRED)
    assert record.affected_claims == ["claim_alpha"]
    assert _count_audit_events(service) == 1


def test_plan_refuses_a_broken_chain_before_anything_is_written(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(BrokenPropagationError):
        service.plan(source_evidence_id="ev-orphan", reason=InvalidationReason.RETRACTED)
    assert service.store.list(INVALIDATION_KIND) == []
    assert _count_audit_events(service) == 0


def test_recording_the_same_plan_twice_does_not_duplicate_audit_events(tmp_path: Path) -> None:
    """``append_event`` is not idempotent, so the seam must guard it."""

    service = _service(tmp_path)
    _wire_dependency(service, "ev-1")
    plan = service.plan(source_evidence_id="ev-1", reason=InvalidationReason.RETRACTED)
    service.record(plan)
    service.record(plan)
    assert len(service.store.list(INVALIDATION_KIND)) == 1
    assert _count_audit_events(service) == 1


def test_a_caller_can_validate_the_blast_radius_before_any_write(tmp_path: Path) -> None:
    """The seam that L-04's adapter needs: reject pre-write, leave no residue.

    Validating *after* the one-shot ``propagate`` would already have persisted a
    record and an audit event for a propagation the caller meant to reject.
    """

    service = _service(tmp_path)
    _wire_dependency(service, "ev-1")
    plan = service.plan(source_evidence_id="ev-1", reason=InvalidationReason.RETRACTED)
    asserted_claims = ["claim_someone_else_said"]
    if plan.affected_claims != asserted_claims:
        # caller rejects the propagation here, having written nothing
        assert service.store.list(INVALIDATION_KIND) == []
        assert _count_audit_events(service) == 0
    else:  # pragma: no cover - the assertion above is the path under test
        raise AssertionError("expected the mismatch branch")


def test_a_caller_supplied_identity_folds_a_retry_onto_one_record(tmp_path: Path) -> None:
    """K8 fixes no idempotency key, so the caller supplies identity.

    Without a stable id, a retry loop re-plans (fresh id) and duplicates the
    audit fact -- see ``record()``'s docstring for the exact scope of the guard.
    """

    service = _service(tmp_path)
    _wire_dependency(service, "ev-1")
    stable_id = "inval_retry_stable"
    first = service.plan(
        source_evidence_id="ev-1",
        reason=InvalidationReason.RETRACTED,
        propagation_id=stable_id,
    )
    service.record(first)
    retry = service.plan(
        source_evidence_id="ev-1",
        reason=InvalidationReason.RETRACTED,
        propagation_id=stable_id,
    )
    service.record(retry)
    assert len(service.store.list(INVALIDATION_KIND)) == 1
    assert _count_audit_events(service) == 1


def test_re_planning_without_an_identity_is_a_new_fact(tmp_path: Path) -> None:
    """The documented default: each ``plan()`` mints its own identity."""

    service = _service(tmp_path)
    _wire_dependency(service, "ev-1")
    service.record(service.plan(source_evidence_id="ev-1", reason=InvalidationReason.EXPIRED))
    service.record(service.plan(source_evidence_id="ev-1", reason=InvalidationReason.EXPIRED))
    assert len(service.store.list(INVALIDATION_KIND)) == 2
    assert _count_audit_events(service) == 2


def test_reusing_an_identity_for_a_different_blast_radius_is_refused(tmp_path: Path) -> None:
    """A wider blast radius under the same id is a deliberate refusal, not a merge."""

    service = _service(tmp_path)
    service.store.put("graph_edge", "e1", _edge("ev-1", "claim_one"), partition="papers")
    service.record(
        service.plan(
            source_evidence_id="ev-1",
            reason=InvalidationReason.RETRACTED,
            propagation_id="inval_fixed",
        )
    )
    service.store.put("graph_edge", "e2", _edge("ev-1", "claim_two"), partition="papers")
    with pytest.raises(InvalidationContractError):
        service.record(
            service.plan(
                source_evidence_id="ev-1",
                reason=InvalidationReason.RETRACTED,
                propagation_id="inval_fixed",
            )
        )


def test_propagate_accepts_a_caller_supplied_identity_too(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _wire_dependency(service, "ev-1")
    service.propagate(
        source_evidence_id="ev-1",
        reason=InvalidationReason.RETRACTED,
        propagation_id="inval_fixed",
    )
    service.propagate(
        source_evidence_id="ev-1",
        reason=InvalidationReason.RETRACTED,
        propagation_id="inval_fixed",
    )
    assert len(service.store.list(INVALIDATION_KIND)) == 1
    assert _count_audit_events(service) == 1


# ---------------------------------------------------------------------------
# B5 reuse
# ---------------------------------------------------------------------------


def test_retraction_reason_reuses_b5_source_status() -> None:
    assert reason_from_source_status(SourceStatus.RETRACTED) is InvalidationReason.RETRACTED


@pytest.mark.parametrize(
    "status",
    (
        SourceStatus.FOUND,
        SourceStatus.CORRECTED,
        SourceStatus.NOT_FOUND,
        SourceStatus.UNKNOWN,
    ),
)
def test_undecidable_source_status_is_not_read_as_a_retraction(status: SourceStatus) -> None:
    """'We could not tell' is neither a retraction nor a clean bill of health."""

    assert reason_from_source_status(status) is None
