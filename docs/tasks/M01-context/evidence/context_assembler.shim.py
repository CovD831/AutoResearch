"""SHIM: symbols + field declarations only; no validators, no algorithm bodies.

Used once to measure discriminating power of tests/test_m01_*.py on the
pre-implementation baseline (R-007 lane kickoff convention: a brand new module
needs a symbol-only shim before judgment-type failures are obtainable).
NOT part of the deliverable.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

MAX_REF_ID_LENGTH = 200
RefId = Annotated[
    str, StringConstraints(strict=True, min_length=1, max_length=MAX_REF_ID_LENGTH)
]


class ContextKind(StrEnum):
    EVIDENCE = "evidence"
    HANDOFF = "handoff"
    KNOWLEDGE = "knowledge"
    GUIDANCE = "guidance"


DEFAULT_TIER_ORDER: tuple[str, ...] = (
    ContextKind.EVIDENCE,
    ContextKind.HANDOFF,
    ContextKind.KNOWLEDGE,
    ContextKind.GUIDANCE,
)


class ContextBudget(BaseModel):
    max_tokens: int
    max_items_per_kind: dict[str, int] = Field(default_factory=dict)
    reserved_ratio: float = 0.2
    max_tokens_per_kind: dict[str, int] = Field(default_factory=dict)


class ContextItem(BaseModel):
    ref_id: RefId
    kind: str
    tokens: int | None = None
    text: str | None = None


class ContextSlice(BaseModel):
    slice_id: str = "shim"
    kind: str
    refs: list[RefId] = Field(default_factory=list)
    rendered: str | None = None
    truncated: bool = False
    dropped_refs: list[RefId] = Field(default_factory=list)


class ContextAssembly(BaseModel):
    assembly_id: str = "shim"
    slices: list[ContextSlice] = Field(default_factory=list)
    total_tokens: int = 0
    dropped_refs: list[RefId] = Field(default_factory=list)

    def slices_of_kind(self, kind: str) -> list[ContextSlice]:
        raise NotImplementedError("shim")


class ContextAssembler:
    def __init__(self, *, tier_order: Sequence[str] | None = None) -> None:
        self._order = list(tier_order or DEFAULT_TIER_ORDER)

    @property
    def kinds(self) -> tuple[str, ...]:
        raise NotImplementedError("shim")

    def register_kind(self, kind: str, *, tier: int) -> None:
        raise NotImplementedError("shim")

    def assemble(self, items: Iterable[ContextItem], budget: ContextBudget):
        raise NotImplementedError("shim")


class HandoffReplay(BaseModel):
    project_id: str
    run_id: str
    gate_scope: str = "project"


class HandoffReplayService:
    def __init__(self, store) -> None:
        self.store = store

    def by_run(self, *, project_id: str, run_id: str):
        raise NotImplementedError("shim")
