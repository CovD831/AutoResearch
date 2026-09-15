"""K7 ``PrefetchRecord`` -- evidence prefetch gate for L2+ actions (M02-07).

Scope
-----
This module owns exactly two things:

1. the :class:`PrefetchRecord` schema plus its mechanically checkable invariants
   (K7-2 fail-closed decision, K7-3 bundle foreign key), and
2. :class:`EvidencePrefetchService`, the single write path for prefetch records
   and the mandatory entry for L2+ actions.

K7-1 ("an L2+ action must have a prefetch record written before it") is a
*temporal* constraint: a validator examines fields, never "what happened
before what". L2 §K7 says so explicitly (corrected in review pass 1, B1). The
compensation lives in code structure, not in a validator -- see
``EvidencePrefetchService.execute_l2_action``.

Run identity
------------
``PrefetchRecord.run_id`` references K1 ``RunManifest.run_id``, which is owned
by L-05 in ``run_manifest.py``. This module *never* mints a run identifier: it
does not define one, does not call ``new_id("run")``, and does not import any
run abstraction. ``run_id`` stays ``None`` until a caller supplies a K1 run id.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from autoresearch.contracts import new_id, utc_now

# ``action_level`` mirrors the existing ``RiskLevel`` ladder (L0..L4). The K7
# contract types it as ``int``, so it stays an int with explicit bounds rather
# than re-deriving a second risk enum.
MIN_ACTION_LEVEL = 0
MAX_ACTION_LEVEL = 4
L2_LOWEST_GATED_LEVEL = 2

PREFETCH_RECORD_KIND = "prefetch_record"
EVIDENCE_BUNDLE_KIND = "evidence_bundle"


class PrefetchDecision(StrEnum):
    PROCEED = "proceed"
    BLOCKED = "blocked"


class PrefetchContractError(ValueError):
    """Base class for K7 contract violations raised by this module."""


class MissingBundleError(PrefetchContractError):
    """K7-3: ``final_bundle_id`` does not resolve to an existing bundle."""


class L0L1NotGatedError(PrefetchContractError):
    """``execute_l2_action`` was called below L2 (it is the L2+ entry only)."""


class PrefetchRecord(BaseModel):
    """One prefetch fact: what was asked, what was found, what was decided."""

    prefetch_id: str = Field(default_factory=lambda: new_id("prefetch"))
    action_level: int = Field(ge=MIN_ACTION_LEVEL, le=MAX_ACTION_LEVEL)
    query: str = Field(min_length=1, max_length=2000)
    candidates: list[str] = Field(default_factory=list)
    final_bundle_id: str | None = None
    decision: PrefetchDecision
    # D-L02-01: references K1 ``RunManifest.run_id``. Optional and never minted
    # here -- see the module docstring.
    run_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _fail_closed_bundle_consistency(self) -> PrefetchRecord:
        """K7-2: the decision and the evidence it claims must agree.

        The mechanically checkable face of "no evidence -> blocked" is: you
        cannot *proceed* while pointing at nothing, and you cannot be *blocked*
        while carrying the bundle you supposedly refused. Either half alone
        would let a "proceed with no evidence" record exist.
        """

        if self.decision is PrefetchDecision.PROCEED:
            if self.final_bundle_id is None:
                raise ValueError(
                    "decision='proceed' requires final_bundle_id "
                    "(K7-2 fail-closed: absent evidence must be 'blocked')"
                )
            if not self.candidates:
                raise ValueError(
                    "decision='proceed' requires at least one candidate "
                    "(K7-2 fail-closed: an empty candidate set is not evidence)"
                )
        elif self.final_bundle_id is not None:
            raise ValueError(
                "decision='blocked' must not carry a final_bundle_id "
                f"(got {self.final_bundle_id!r})"
            )
        return self


class BundleRegistry(Protocol):
    """Existence oracle for K7-3 (see deviation D-L02-02)."""

    def exists(self, bundle_id: str) -> bool: ...


class StoreBundleRegistry:
    """Default bundle oracle: reads ``evidence_bundle`` records from the store.

    Note (D-L02-02): nothing in the repository persists ``EvidenceBundle`` yet,
    so this oracle currently answers ``False`` for every id -- which makes the
    foreign key *fail closed* rather than silently succeed. Callers that hold a
    bundle registry elsewhere should inject their own ``BundleRegistry``.
    """

    def __init__(self, store) -> None:  # noqa: ANN001 - duck-typed RecordStore
        self.store = store

    def exists(self, bundle_id: str) -> bool:
        return self.store.get(EVIDENCE_BUNDLE_KIND, bundle_id) is not None


def validate_final_bundle(record: PrefetchRecord, *, bundles: BundleRegistry) -> None:
    """K7-3: ``final_bundle_id`` must point at a bundle that exists."""

    if record.final_bundle_id is None:
        return
    if not bundles.exists(record.final_bundle_id):
        raise MissingBundleError(
            f"final_bundle_id {record.final_bundle_id!r} does not resolve to an "
            "existing bundle (K7-3 foreign key)"
        )


@dataclass(frozen=True)
class PrefetchOutcome[T]:
    """What the L2+ entry did: the record it wrote, and whether it ran."""

    record: PrefetchRecord
    executed: bool
    result: T | None = None


class EvidencePrefetchService:
    """K7: unique writer of prefetch records + unique entry for L2+ actions."""

    def __init__(self, store, *, bundles: BundleRegistry | None = None) -> None:  # noqa: ANN001
        self.store = store
        self.bundles = bundles if bundles is not None else StoreBundleRegistry(store)

    @staticmethod
    def decide(*, candidates: list[str], bundle_id: str | None) -> PrefetchDecision:
        """K7-2 decision function: nothing found -> ``blocked``."""

        if not candidates or bundle_id is None:
            return PrefetchDecision.BLOCKED
        return PrefetchDecision.PROCEED

    def write_prefetch(
        self,
        *,
        action_level: int,
        query: str,
        candidates: list[str],
        bundle_id: str | None = None,
        run_id: str | None = None,
    ) -> PrefetchRecord:
        """The single write path for ``prefetch_record`` (AST-guarded).

        Writes unconditionally -- including when the decision is ``blocked``:
        the blocked attempt is itself the audit fact worth keeping. The K7-3
        foreign key is checked *before* the write, so an unresolvable bundle
        never lands in the store.
        """

        decision = self.decide(candidates=candidates, bundle_id=bundle_id)
        record = PrefetchRecord(
            action_level=action_level,
            query=query,
            candidates=list(candidates),
            final_bundle_id=bundle_id if decision is PrefetchDecision.PROCEED else None,
            decision=decision,
            run_id=run_id,
        )
        validate_final_bundle(record, bundles=self.bundles)
        self.store.put(PREFETCH_RECORD_KIND, record.prefetch_id, record, partition="prefetch")
        return record

    def write_prefetch_for_run(
        self,
        manifest,  # noqa: ANN001 - K1 RunManifest, duck-typed on purpose
        *,
        action_level: int,
        query: str,
        candidates: list[str],
        bundle_id: str | None = None,
    ) -> PrefetchRecord:
        """K1 integration point: ``run_id`` comes from ``manifest.run_id``.

        The manifest is duck-typed rather than imported. K1
        (``run_manifest.py``) is owned by L-05 and is not in ``main`` yet, so a
        runtime import would make this module unimportable on its own branch --
        exactly the stacked-branch failure R-006 hit. Reading ``.run_id`` is the
        whole contract (K1's own docstring states it for this type), so duck
        typing costs nothing and keeps this lane independently mergeable.
        """

        return self.write_prefetch(
            action_level=action_level,
            query=query,
            candidates=candidates,
            bundle_id=bundle_id,
            run_id=manifest.run_id,
        )

    def execute_l2_action(
        self,
        *,
        action_level: int,
        query: str,
        candidates: list[str],
        action: Callable[[PrefetchRecord], object],
        bundle_id: str | None = None,
        run_id: str | None = None,
    ) -> PrefetchOutcome:
        """Mandatory entry for any L2+ action (K7-1 structural compensation).

        Three structural properties, in one place:

        1. it refuses to be the entry for L0/L1 (``action_level < 2`` raises),
           so there is no second, gated-looking path at low levels;
        2. the record is written *before* ``action`` exists as a call -- and
           ``action`` receives that very record, so an action body cannot be
           shaped without one;
        3. a ``blocked`` decision short-circuits: ``action`` is never invoked.

        What this does NOT do: it cannot stop a *different* module from
        performing an L2+ action without calling this entry. That remainder is
        the architectural-intent part of K7-1 and is explicitly not claimed as
        verified.
        """

        if action_level < L2_LOWEST_GATED_LEVEL:
            raise L0L1NotGatedError(
                f"execute_l2_action is the L2+ entry; got action_level={action_level}. "
                "Use write_prefetch() for L0/L1 actions."
            )
        record = self.write_prefetch(
            action_level=action_level,
            query=query,
            candidates=candidates,
            bundle_id=bundle_id,
            run_id=run_id,
        )
        if record.decision is not PrefetchDecision.PROCEED:
            return PrefetchOutcome(record=record, executed=False, result=None)
        return PrefetchOutcome(record=record, executed=True, result=action(record))
