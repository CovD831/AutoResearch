"""K5 (``ContextBudget`` / ``ContextSlice``) and M01-06 handoff replay tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from autoresearch.context_assembler import (
    DEFAULT_TIER_ORDER,
    MAX_REF_ID_LENGTH,
    ContextAssembler,
    ContextAssembly,
    ContextBudget,
    ContextItem,
    ContextSlice,
    HandoffReplayService,
)
from autoresearch.contracts import AgentId, ArtifactRef, HandoffEnvelope
from autoresearch.handoffs import HandoffService
from autoresearch.storage import RecordStore


def _item(
    ref_id: str,
    *,
    kind: str = "evidence",
    tokens: int | None = 10,
    text: str | None = None,
) -> ContextItem:
    return ContextItem(ref_id=ref_id, kind=kind, tokens=tokens, text=text)


def _shape(assembly: ContextAssembly) -> list[tuple[str, list[str], str | None, bool, list[str]]]:
    return [
        (item.kind, item.refs, item.rendered, item.truncated, item.dropped_refs)
        for item in assembly.slices
    ]


# --------------------------------------------------------------------------- #
# K5-1: over budget -> fall back to splitting, never pile up full text
# --------------------------------------------------------------------------- #


def test_budget_with_room_keeps_every_reference() -> None:
    assembly = ContextAssembler().assemble(
        [
            _item("ev1", tokens=10, text="alpha"),
            _item("ev2", tokens=10, text="beta"),
        ],
        ContextBudget(max_tokens=100),
    )
    slice_ = assembly.slices_of_kind("evidence")[0]
    assert slice_.refs == ["ev1", "ev2"]
    assert slice_.truncated is False
    assert slice_.dropped_refs == []
    assert slice_.rendered == "alpha\nbeta"
    assert assembly.total_tokens == 20
    assert assembly.dropped_refs == []


def test_over_budget_falls_back_to_splitting_and_records_dropped_refs() -> None:
    """N-1: the dropped reference is *named*, not merely "non-empty"."""

    assembly = ContextAssembler().assemble(
        [
            _item("ev1", tokens=40, text="first"),
            _item("ev2", tokens=40, text="second"),
            _item("ev3", tokens=40, text="third"),
        ],
        ContextBudget(max_tokens=100),  # usable = 100 * (1 - 0.2) = 80
    )
    slice_ = assembly.slices_of_kind("evidence")[0]
    assert slice_.refs == ["ev1", "ev2"]
    assert slice_.truncated is True
    assert slice_.dropped_refs == ["ev3"]
    assert assembly.dropped_refs == ["ev3"]
    # K5-1: the overflow is split off, not concatenated into `rendered`.
    assert "third" not in (slice_.rendered or "")
    assert assembly.total_tokens == 80


def test_every_input_reference_lands_in_exactly_one_bucket() -> None:
    assembly = ContextAssembler().assemble(
        [
            _item("ev1", tokens=40),
            _item("ev2", tokens=40),
            _item("ev3", tokens=40),
        ],
        ContextBudget(max_tokens=100),
    )
    slice_ = assembly.slices_of_kind("evidence")[0]
    assert sorted(slice_.refs + slice_.dropped_refs) == ["ev1", "ev2", "ev3"]


# --------------------------------------------------------------------------- #
# K5-2: truncated => dropped_refs recorded
# --------------------------------------------------------------------------- #


def test_truncated_slice_must_record_dropped_refs() -> None:
    with pytest.raises(ValidationError, match="dropped_refs"):
        ContextSlice(kind="evidence", refs=["ev1"], truncated=True)
    # Control: untruncated slices need nothing, and the recorded form is accepted.
    assert ContextSlice(kind="evidence", refs=["ev1"], truncated=False).truncated is False
    recorded = ContextSlice(
        kind="evidence", refs=["ev1"], truncated=True, dropped_refs=["ev2"]
    )
    assert recorded.dropped_refs == ["ev2"]


# --------------------------------------------------------------------------- #
# K5-4: refs hold reference IDs (type + length), never full text
# --------------------------------------------------------------------------- #


def test_refs_reject_non_string_and_over_long_ids() -> None:
    with pytest.raises(ValidationError):
        ContextSlice(kind="evidence", refs=[123])
    with pytest.raises(ValidationError):
        ContextSlice(kind="evidence", refs=["x" * (MAX_REF_ID_LENGTH + 1)])
    with pytest.raises(ValidationError):
        ContextSlice(kind="evidence", refs=[""])


def test_refs_hold_ids_not_full_text() -> None:
    long_text = "lorem ipsum dolor sit amet " * 40
    assembly = ContextAssembler().assemble(
        [_item("ev1", tokens=5, text=long_text)],
        ContextBudget(max_tokens=100),
    )
    slice_ = assembly.slices_of_kind("evidence")[0]
    assert slice_.refs == ["ev1"]
    assert slice_.rendered == long_text
    assert all(len(ref) <= MAX_REF_ID_LENGTH for ref in slice_.refs)


# --------------------------------------------------------------------------- #
# Graded budget: the interface M11-04 depends on
# --------------------------------------------------------------------------- #


def test_default_assembler_registers_the_four_contract_kinds() -> None:
    assert ContextAssembler().kinds == tuple(DEFAULT_TIER_ORDER)
    assert set(DEFAULT_TIER_ORDER) == {"evidence", "handoff", "knowledge", "guidance"}


def test_per_kind_item_tier_caps_each_kind_independently() -> None:
    assembly = ContextAssembler().assemble(
        [
            _item("ev1", tokens=1),
            _item("ev2", tokens=1),
            _item("ho1", kind="handoff", tokens=1),
            _item("ho2", kind="handoff", tokens=1),
        ],
        ContextBudget(max_tokens=100, max_items_per_kind={"evidence": 1}),
    )
    evidence = assembly.slices_of_kind("evidence")[0]
    handoff = assembly.slices_of_kind("handoff")[0]
    assert evidence.refs == ["ev1"]
    assert evidence.dropped_refs == ["ev2"]
    assert handoff.refs == ["ho1", "ho2"]
    assert handoff.truncated is False


def test_per_kind_token_tier_is_honoured() -> None:
    assembly = ContextAssembler().assemble(
        [
            _item("ev1", tokens=5),
            _item("ev2", tokens=5),
            _item("ho1", kind="handoff", tokens=50),
        ],
        ContextBudget(max_tokens=1000, max_tokens_per_kind={"evidence": 5}),
    )
    assert assembly.slices_of_kind("evidence")[0].dropped_refs == ["ev2"]
    assert assembly.slices_of_kind("handoff")[0].refs == ["ho1"]


def test_max_tokens_per_kind_is_optional_and_none_is_k5_equivalent() -> None:
    """D-L01-02b: omitted, explicit ``None`` and ``{}`` must behave identically.

    With the default the budget must reproduce exactly what the K5 field list
    describes — every kind on the global usable budget, no per-kind token tier.
    """

    assembler = ContextAssembler()
    items = [
        _item("ev1", tokens=40, text="first"),
        _item("ev2", tokens=40, text="second"),
        _item("ev3", tokens=40, text="third"),
        _item("ho1", kind="handoff", tokens=10, text="hand off"),
    ]
    omitted = ContextBudget(max_tokens=100)
    explicit_none = ContextBudget(max_tokens=100, max_tokens_per_kind=None)
    empty = ContextBudget(max_tokens=100, max_tokens_per_kind={})

    assert omitted.max_tokens_per_kind is None
    shapes = [
        _shape(assembler.assemble(items, budget))
        for budget in (omitted, explicit_none, empty)
    ]
    assert shapes[0] == shapes[1] == shapes[2]

    for budget in (omitted, explicit_none, empty):
        assert budget.usable_tokens == 80
        for kind in DEFAULT_TIER_ORDER:
            assert budget.kind_token_ceiling(kind) == budget.usable_tokens

    # Control: once a tier *is* given, the per-kind ceiling really differs.
    tiered = ContextBudget(max_tokens=1000, max_tokens_per_kind={"evidence": 5})
    assert tiered.kind_token_ceiling("evidence") == 5
    assert tiered.kind_token_ceiling("handoff") == tiered.usable_tokens == 800


def test_per_kind_token_tier_rejects_non_positive_ceilings() -> None:
    for bad in (0, -1):
        with pytest.raises(ValidationError, match="must be > 0"):
            ContextBudget(max_tokens=100, max_tokens_per_kind={"evidence": bad})


def test_reserved_ratio_holds_tokens_back_for_output() -> None:
    assembly = ContextAssembler().assemble(
        [_item("ev1", tokens=60)],
        ContextBudget(max_tokens=100, reserved_ratio=0.5),  # usable = 50
    )
    assert assembly.slices_of_kind("evidence")[0].dropped_refs == ["ev1"]
    assert assembly.total_tokens == 0


def test_unused_output_reserve_does_not_fabricate_dropped_refs() -> None:
    """The reserve shrinks what fits; it must not itself be booked as a drop."""

    assembly = ContextAssembler().assemble(
        [_item("ev1", tokens=40), _item("ev2", tokens=40)],  # 80 == usable
        ContextBudget(max_tokens=100, reserved_ratio=0.2),
    )
    slice_ = assembly.slices_of_kind("evidence")[0]
    assert slice_.refs == ["ev1", "ev2"]
    assert slice_.dropped_refs == []
    assert slice_.truncated is False
    assert assembly.total_tokens == 80


def test_output_reserve_excludes_an_item_by_naming_it() -> None:
    """Reserve-induced exclusion is a real exclusion, so it is named (not hidden)."""

    budget = ContextBudget(max_tokens=100, reserved_ratio=0.5)
    assembly = ContextAssembler().assemble(
        [_item("ev1", tokens=50, text="fits"), _item("ev2", tokens=50, text="reserved away")],
        budget,
    )
    slice_ = assembly.slices_of_kind("evidence")[0]
    assert slice_.refs == ["ev1"]
    assert slice_.dropped_refs == ["ev2"]
    assert slice_.truncated is True
    assert assembly.total_tokens == 50
    assert (budget.max_tokens, budget.usable_tokens) == (100, 50)


def test_register_kind_extends_the_tier_order() -> None:
    assembler = ContextAssembler()
    assembler.register_kind("telemetry", tier=-1)
    assert assembler.kinds[0] == "telemetry"
    assembly = assembler.assemble(
        [_item("t1", kind="telemetry", tokens=1)], ContextBudget(max_tokens=100)
    )
    assert assembly.slices_of_kind("telemetry")[0].refs == ["t1"]


def test_unregistered_kind_is_rejected_explicitly() -> None:
    with pytest.raises(ValueError, match="unregistered"):
        ContextAssembler().assemble(
            [_item("t1", kind="telemetry", tokens=1)], ContextBudget(max_tokens=100)
        )


def test_unmeasured_token_cost_is_not_treated_as_free() -> None:
    """Missing cost must not be read as zero (the "unmeasured == normal" family)."""

    assembly = ContextAssembler().assemble(
        [_item("ev1", tokens=None)],
        ContextBudget(max_tokens=100),
    )
    slice_ = assembly.slices_of_kind("evidence")[0]
    assert slice_.refs == []
    assert slice_.dropped_refs == ["ev1"]
    assert slice_.truncated is True
    assert assembly.total_tokens == 0


def test_assembly_is_replayable() -> None:
    assembler = ContextAssembler()
    items = [
        _item("ev1", tokens=40, text="first"),
        _item("ev2", tokens=40, text="second"),
        _item("ev3", tokens=40, text="third"),
        _item("ho1", kind="handoff", tokens=5, text="hand off"),
    ]
    budget = ContextBudget(max_tokens=100)
    assert _shape(assembler.assemble(items, budget)) == _shape(assembler.assemble(items, budget))


# --------------------------------------------------------------------------- #
# M01-06: handoff replay (reuses HandoffEnvelope + the handoffs partition)
# --------------------------------------------------------------------------- #


def _envelope(
    *,
    handoff_id: str,
    run_id: str,
    artifact_id: str,
    evidence_ids: list[str],
    minute: int,
    project_id: str = "p1",
) -> HandoffEnvelope:
    return HandoffEnvelope(
        handoff_id=handoff_id,
        project_id=project_id,
        run_id=run_id,
        from_agent=AgentId.ORCHESTRATOR,
        to_agent=AgentId.WRITER,
        objective="carry the evaluation section forward",
        expected_output="a reviewed section draft",
        artifact_refs=[ArtifactRef(artifact_id=artifact_id, kind="section")],
        evidence_ids=evidence_ids,
        created_at=datetime(2026, 1, 1, 0, minute, tzinfo=UTC),
    )


def _seeded_store(tmp_path) -> RecordStore:
    store = RecordStore(tmp_path / "store.sqlite3")
    service = HandoffService(store)
    service.issue(
        _envelope(
            handoff_id="h_run_a",
            run_id="run-a",
            artifact_id="art-a",
            evidence_ids=["ev-a1", "ev-a2"],
            minute=1,
        )
    )
    service.issue(
        _envelope(
            handoff_id="h_run_b",
            run_id="run-b",
            artifact_id="art-b",
            evidence_ids=["ev-b1"],
            minute=2,
        )
    )
    return store


def test_handoff_replay_exports_only_the_requested_run(tmp_path) -> None:
    replay = HandoffReplayService(_seeded_store(tmp_path)).by_run(
        project_id="p1", run_id="run-a"
    )
    assert [envelope.handoff_id for envelope in replay.envelopes] == ["h_run_a"]
    assert [ref.artifact_id for ref in replay.artifact_refs] == ["art-a"]
    assert replay.evidence_ids == ["ev-a1", "ev-a2"]
    assert replay.run_id == "run-a"


def test_handoff_replay_reuses_the_contract_envelope_type(tmp_path) -> None:
    replay = HandoffReplayService(_seeded_store(tmp_path)).by_run(
        project_id="p1", run_id="run-b"
    )
    assert isinstance(replay.envelopes[0], HandoffEnvelope)
    # GateDecision (contracts.py) carries no run_id, so gate refs are project-scoped.
    assert replay.gate_scope == "project"


def test_handoff_replay_is_deterministic(tmp_path) -> None:
    store = _seeded_store(tmp_path)
    service = HandoffReplayService(store)
    assert service.by_run(project_id="p1", run_id="run-a") == service.by_run(
        project_id="p1", run_id="run-a"
    )


def test_handoff_replay_of_an_unknown_run_is_empty(tmp_path) -> None:
    replay = HandoffReplayService(_seeded_store(tmp_path)).by_run(
        project_id="p1", run_id="run-missing"
    )
    assert replay.envelopes == []
    assert replay.artifact_refs == []
    assert replay.evidence_ids == []


def test_handoff_replay_lists_project_scoped_gate_references(tmp_path) -> None:
    store = _seeded_store(tmp_path)
    store.put(
        "gate_decision",
        "gate-1",
        {"decision_id": "gate-1"},
        project_id="p1",
        partition="governance",
    )
    replay = HandoffReplayService(store).by_run(project_id="p1", run_id="run-a")
    assert replay.gate_decision_ids == ["gate-1"]
