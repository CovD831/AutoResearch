"""L8 recall audit contract for the M11 knowledge lane.

Source: R-006 C8, injected into this package as a contract plus a mechanically
checkable invariant (``TASK-SPECS.md:424``, ``:435-437``, ``:657``).

Every ``KnowledgeService.retrieve()`` call writes exactly one ``RecallAuditRecord``
unless auditing is explicitly switched off (default: on). The record carries the four
stage id-sets, so the subset chain is verifiable straight from the persisted payload:

    final_hits ⊆ reranked ⊆ deduped ⊆ candidates

The invariant is enforced twice on purpose: by the model validator below (so an
ill-formed record cannot even be constructed) and by the persisted-payload assertion
in the package tests (so a future writer change cannot silently drop it).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from autoresearch.contracts import new_id, utc_now

#: Storage kind for recall audit rows. The ``records`` table is kind-generic
#: (``storage.py:138``), so this needs no schema change -- which matters because
#: ``storage.py`` is a forbidden path for this package.
RECALL_AUDIT_KIND = "recall_audit"

#: The subset chain, innermost first: each right-hand set must contain the left one.
SUBSET_CHAIN: tuple[tuple[str, str], ...] = (
    ("deduped", "candidates"),
    ("reranked", "deduped"),
    ("final_hits", "reranked"),
)


class RecallAuditRecord(BaseModel):
    """One recall audit row (R-006 C8 fields, in contract order)."""

    audit_id: str = Field(default_factory=lambda: new_id("recall"))
    project_id: str | None = None
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    candidates: tuple[str, ...] = ()
    deduped: tuple[str, ...] = ()
    reranked: tuple[str, ...] = ()
    final_hits: tuple[str, ...] = ()
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _subset_chain_holds(self) -> RecallAuditRecord:
        for inner, outer in SUBSET_CHAIN:
            leaked = set(getattr(self, inner)) - set(getattr(self, outer))
            if leaked:
                raise ValueError(f"{inner} is not a subset of {outer}: {sorted(leaked)}")
        return self


def build_record(
    *,
    query: str,
    project_id: str | None,
    filters: dict[str, Any],
    candidates: tuple[str, ...],
    deduped: tuple[str, ...],
    reranked: tuple[str, ...],
    final_hits: tuple[str, ...],
    stage_timings_ms: dict[str, float],
) -> RecallAuditRecord:
    """Assemble a validated record from one pipeline run."""

    return RecallAuditRecord(
        project_id=project_id,
        query=query,
        filters=filters,
        candidates=candidates,
        deduped=deduped,
        reranked=reranked,
        final_hits=final_hits,
        stage_timings_ms=stage_timings_ms,
    )


class RecallAuditWriter:
    """Persist recall audit rows; switchable off (``TASK-SPECS.md:435``)."""

    def __init__(self, store: Any, *, enabled: bool = True) -> None:
        self.store = store
        self.enabled = enabled

    def write(self, record: RecallAuditRecord) -> RecallAuditRecord | None:
        if not self.enabled:
            return None
        self.store.put(
            RECALL_AUDIT_KIND,
            record.audit_id,
            record,
            project_id=record.project_id,
        )
        return record

    def list_records(self) -> list[dict[str, Any]]:
        """Read back the audit rows, newest semantics left to the caller."""

        return self.store.list(RECALL_AUDIT_KIND)
