"""K5 context assembly (M01-05) and handoff replay (M01-06).

Contract authority: R-007 ``docs/rearchitecture/R007-parallel-modules/04-l2-contracts.md``
§K5 (``ContextBudget`` / ``ContextSlice``) and the M01-06 row of the task table.

Two design constraints drive this module:

* **Graded, not single-tier.** K5 is the prerequisite for M11-04 (tiered
  ``ContextPack`` assembly). The budget is therefore *layered per ``kind``*
  (``max_items_per_kind`` + ``max_tokens_per_kind``) and the assembler iterates
  registered kinds in tier order instead of a single hard-coded list. New kinds
  are added with :meth:`ContextAssembler.register_kind` without editing this
  module.
* **Unmeasured is not zero.** An item whose token cost is unknown
  (``tokens is None``) is never budgeted as if it were free; it is dropped and
  recorded, because "missing recorded as a normal value" is a repeat defect
  family in this repository.

Per item the assembler only ever keeps *references* (``refs`` holds IDs); the
renderable text lives in ``rendered``. Handoff replay reuses the existing
``HandoffEnvelope`` contract and the ``handoffs`` partition written by
``autoresearch.handoffs`` — no second handoff type is introduced.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

from autoresearch.contracts import ArtifactRef, HandoffEnvelope, new_id
from autoresearch.storage import RecordStore

#: A reference is an ID, never the thing it points at (K5-4). The length cap is
#: what makes "refs hold IDs, not full text" mechanically checkable.
MAX_REF_ID_LENGTH = 200

RefId = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=MAX_REF_ID_LENGTH),
]


class ContextKind(StrEnum):
    """Canonical context kinds (K5 table). Extra kinds may be registered."""

    EVIDENCE = "evidence"
    HANDOFF = "handoff"
    KNOWLEDGE = "knowledge"
    GUIDANCE = "guidance"


#: Default tier order. ``guidance`` comes last: per L1 §4.2 A1 guidance must not
#: be presented as a factual claim, and keeping it in its own trailing tier is
#: the structural half of that rule. The rule itself is enforced downstream (on
#: the claim/output side), *not* by a validator here — see the L3 note on K5-3.
DEFAULT_TIER_ORDER: tuple[str, ...] = (
    ContextKind.EVIDENCE,
    ContextKind.HANDOFF,
    ContextKind.KNOWLEDGE,
    ContextKind.GUIDANCE,
)


class ContextBudget(BaseModel):
    """Layered budget (K5). Per-kind ceilings are the "graded" seam for M11-04."""

    max_tokens: int = Field(gt=0)
    max_items_per_kind: dict[str, int] = Field(default_factory=dict)
    reserved_ratio: float = Field(default=0.2, ge=0.0, lt=1.0)
    #: Per-kind token tier. **Extension, not in the K5 field list** (D-L01-02b):
    #: K5 only names the *item-count* dimension (`max_items_per_kind`), so this
    #: field is added, never a re-definition of an existing one. **With the
    #: default ``None`` the behaviour is identical to the K5 text**: every kind
    #: falls back to the global ``usable_tokens``, i.e. exactly what a caller
    #: that only sets ``max_tokens`` + ``reserved_ratio`` gets today.
    max_tokens_per_kind: dict[str, int] | None = None

    @model_validator(mode="after")
    def _ceilings_must_be_usable(self) -> ContextBudget:
        for kind, cap in self.max_items_per_kind.items():
            if cap < 0:
                raise ValueError(f"max_items_per_kind[{kind!r}] must be >= 0, got {cap}")
        for kind, cap in (self.max_tokens_per_kind or {}).items():
            if cap <= 0:
                raise ValueError(f"max_tokens_per_kind[{kind!r}] must be > 0, got {cap}")
        return self

    @property
    def usable_tokens(self) -> int:
        """Tokens available for context once the output reserve is set aside."""

        return max(0, int(self.max_tokens * (1.0 - self.reserved_ratio)))

    def kind_token_ceiling(self, kind: str) -> int:
        """Token tier for ``kind`` (falls back to the global usable budget)."""

        return (self.max_tokens_per_kind or {}).get(kind, self.usable_tokens)

    def kind_item_ceiling(self, kind: str) -> int | None:
        """Item-count tier for ``kind``; ``None`` means "no per-kind cap"."""

        return self.max_items_per_kind.get(kind)


class ContextItem(BaseModel):
    """A budgetable candidate handed to the assembler.

    ``tokens is None`` means *not measured* — never treat it as ``0``.
    """

    ref_id: RefId
    kind: str = Field(min_length=1)
    tokens: int | None = Field(default=None, ge=0)
    text: str | None = None


class ContextSlice(BaseModel):
    """One tier of assembled context (K5)."""

    slice_id: str = Field(default_factory=lambda: new_id("slice"))
    kind: str = Field(min_length=1)
    refs: list[RefId] = Field(default_factory=list)
    rendered: str | None = None
    truncated: bool = False
    dropped_refs: list[RefId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _truncation_must_be_accounted_for(self) -> ContextSlice:
        # K5-2, narrowed to the strict form required by the task card: a cut
        # slice must *record* what it dropped. The contract's softer alternative
        # ("or the rendered text truncation is traceable") is deliberately unused
        # because this assembler never truncates inside an item.
        if self.truncated and not self.dropped_refs:
            raise ValueError(
                "truncated context slice must record dropped_refs (K5-2): "
                "a cut slice may not silently lose references"
            )
        return self


class ContextAssembly(BaseModel):
    """Result of one :meth:`ContextAssembler.assemble` pass."""

    assembly_id: str = Field(default_factory=lambda: new_id("ctx"))
    slices: list[ContextSlice] = Field(default_factory=list)
    total_tokens: int = 0
    dropped_refs: list[RefId] = Field(default_factory=list)

    def slices_of_kind(self, kind: str) -> list[ContextSlice]:
        return [item for item in self.slices if item.kind == kind]


def _render(items: Sequence[ContextItem]) -> str:
    return "\n".join(item.text for item in items if item.text)


class ContextAssembler:
    """Deterministic, budget-bounded assembler with an open set of tiers (K5)."""

    def __init__(self, *, tier_order: Sequence[str] | None = None) -> None:
        order = list(DEFAULT_TIER_ORDER if tier_order is None else tier_order)
        duplicates = sorted({kind for kind in order if order.count(kind) > 1})
        if duplicates:
            raise ValueError(f"duplicate context kinds in tier_order: {duplicates}")
        self._tiers: dict[str, int] = {kind: position for position, kind in enumerate(order)}

    @property
    def kinds(self) -> tuple[str, ...]:
        """Registered kinds in tier order (ties broken by label, for determinism)."""

        return tuple(sorted(self._tiers, key=lambda kind: (self._tiers[kind], kind)))

    def register_kind(self, kind: str, *, tier: int) -> None:
        """Add (or re-tier) a context kind. This is the M11-04 extension seam."""

        if not kind:
            raise ValueError("context kind must be a non-empty label")
        self._tiers[kind] = tier

    def assemble(self, items: Iterable[ContextItem], budget: ContextBudget) -> ContextAssembly:
        """Fit ``items`` into ``budget``, one slice per kind (K5-1).

        Full text is never piled up: items that do not fit the active tier are
        dropped and their IDs recorded in ``dropped_refs``. Items whose token
        cost is unmeasured are dropped for the same reason, never counted as free.
        """

        buckets: dict[str, list[ContextItem]] = {kind: [] for kind in self._tiers}
        for item in items:
            if item.kind not in buckets:
                raise ValueError(
                    f"unregistered context kind {item.kind!r}; "
                    "call ContextAssembler.register_kind() first"
                )
            buckets[item.kind].append(item)

        remaining = budget.usable_tokens
        slices: list[ContextSlice] = []
        all_dropped: list[str] = []
        total = 0
        for kind in self.kinds:
            candidates = buckets.get(kind, [])
            if not candidates:
                continue
            ceiling = min(budget.kind_token_ceiling(kind), remaining)
            item_ceiling = budget.kind_item_ceiling(kind)
            included: list[ContextItem] = []
            dropped: list[str] = []
            used = 0
            for item in candidates:
                if item.tokens is None:
                    dropped.append(item.ref_id)
                    continue
                if item_ceiling is not None and len(included) >= item_ceiling:
                    dropped.append(item.ref_id)
                    continue
                if used + item.tokens > ceiling:
                    dropped.append(item.ref_id)
                    continue
                included.append(item)
                used += item.tokens
            remaining -= used
            total += used
            all_dropped.extend(dropped)
            slices.append(
                ContextSlice(
                    kind=kind,
                    refs=[item.ref_id for item in included],
                    rendered=_render(included) or None,
                    truncated=bool(dropped),
                    dropped_refs=dropped,
                )
            )
        return ContextAssembly(slices=slices, total_tokens=total, dropped_refs=all_dropped)


# --------------------------------------------------------------------------- #
# M01-06: handoff replay
# --------------------------------------------------------------------------- #

HANDOFF_KIND = "handoff"
HANDOFF_PARTITION = "handoffs"
GATE_KIND = "gate_decision"
GATE_PARTITION = "governance"


class HandoffReplay(BaseModel):
    """A run's handoffs plus the references they carry (M01-06).

    ``envelopes`` reuses ``contracts.HandoffEnvelope`` verbatim. ``gate_scope``
    is declared explicitly because ``GateDecision`` (contracts.py) carries no
    ``run_id``: gate references can only be project-scoped, and pretending
    otherwise would be a silent scope leak.
    """

    project_id: str
    run_id: str
    envelopes: list[HandoffEnvelope] = Field(default_factory=list)
    gate_decision_ids: list[str] = Field(default_factory=list)
    gate_scope: str = "project"
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class HandoffReplayService:
    """Export handoff envelopes and their references for a given run."""

    def __init__(self, store: RecordStore) -> None:
        self.store = store

    def by_run(self, *, project_id: str, run_id: str) -> HandoffReplay:
        payloads = self.store.list(
            HANDOFF_KIND, project_id=project_id, partition=HANDOFF_PARTITION
        )
        envelopes = [HandoffEnvelope.model_validate(payload) for payload in payloads]
        matched = sorted(
            (envelope for envelope in envelopes if envelope.run_id == run_id),
            key=lambda envelope: (envelope.created_at, envelope.handoff_id),
        )
        artifacts: dict[str, ArtifactRef] = {}
        evidence_ids: set[str] = set()
        for envelope in matched:
            for ref in envelope.artifact_refs:
                artifacts.setdefault(ref.artifact_id, ref)
            evidence_ids.update(envelope.evidence_ids)
        gate_ids = sorted(
            {
                payload["decision_id"]
                for payload in self.store.list(
                    GATE_KIND, project_id=project_id, partition=GATE_PARTITION
                )
                if payload.get("decision_id")
            }
        )
        return HandoffReplay(
            project_id=project_id,
            run_id=run_id,
            envelopes=matched,
            gate_decision_ids=gate_ids,
            artifact_refs=[artifacts[key] for key in sorted(artifacts)],
            evidence_ids=sorted(evidence_ids),
        )
