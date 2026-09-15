"""K9 ``OutboxEntry``: durable, idempotent delivery of external effects.

The outbox records *intent to perform a side effect* separately from the side
effect itself, so that ``resume``/``retry`` after a crash cannot repeat that
side effect (invariant I7).  ``payload_ref`` is a reference; the payload body
lives in its own record and is never inlined into the entry (K9-2).

Reuse map -- every mechanism below is an *existing* ``RecordStore`` primitive
(``src/autoresearch/storage.py``); this module adds no table, no transaction
manager and no marker vocabulary of its own:

===========================  ===========================================  =====
K9 requirement               primitive actually called                     line
===========================  ===========================================  =====
K9-1 unique idempotency key  ``RecordStore.reserve_idempotent``            272
                             (``INSERT OR IGNORE`` onto the existing
                             ``idempotency`` table, whose primary key is
                             ``(scope, idempotency_key)``)
K9-1 read the marker         ``RecordStore.get_idempotent``                262
K9-3 per-attempt claim/budget ``RecordStore.reserve_idempotent``            272
K9-3 attempt phase ledger    ``RecordStore.mark_idempotent_phase``         338
outcome recording            ``RecordStore.finalize_idempotent``           377
entry + payload persistence  ``RecordStore.put`` / ``.get`` / ``.list``  126/145/153
atomic multi-record rewrite  ``RecordStore.transaction``                    41
                             + ``RecordStore._write_record``                53
===========================  ===========================================  =====

The two-phase vocabulary is A1/A2's, not a new one: an attempt is
``reserved`` -> ``service_started`` -> ``service_returned`` -> ``finalized``
(``storage.py`` ``mark_idempotent_phase`` transition table, line 352).  A
``pending`` attempt left at ``service_started`` means "the effect may have
happened and nobody wrote down the outcome" and is therefore treated as
**unknown**, never as "not attempted" -- see :meth:`Outbox.deliver`.

All audit events written here go through the ``events=`` keyword of
``reserve_idempotent`` / ``mark_idempotent_phase`` / ``finalize_idempotent``,
i.e. they commit in the *same* transaction as the transition that produced
them and are suppressed when that transition loses a race (storage.py:281,
349, 386).  ``append_event`` is deliberately never called: an unconditional
append is not idempotent and would duplicate on retry.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from autoresearch.contracts import utc_now
from autoresearch.storage import RecordStore

#: ``records`` kind holding one row per ``OutboxEntry`` (K9).
OUTBOX_KIND = "outbox"
#: ``records`` kind holding payload bodies; ``payload_ref`` is a record id here.
PAYLOAD_KIND = "outbox_payload"
#: ``records`` kind holding the outbox schema version and migration audits.
SCHEMA_KIND = "outbox_schema"

#: ``idempotency`` scope carrying the K9-1 "this effect happened at most once"
#: marker.  The row key is the caller supplied ``idempotency_key`` verbatim,
#: so uniqueness is enforced by the existing ``(scope, idempotency_key)``
#: primary key of the ``idempotency`` table.
EFFECT_SCOPE = "outbox"
#: ``idempotency`` scope carrying the per-attempt claim/budget rows (K9-3).
ATTEMPT_SCOPE = "outbox_attempt"

VERSION_RECORD_ID = "version"
MIGRATION_FAILURE_RECORD_ID = "migration_failure"

#: Bumped whenever the persisted ``OutboxEntry`` shape changes; ``migrate``
#: brings older databases up to it and refuses newer ones.
SCHEMA_VERSION = 1
DEFAULT_MAX_ATTEMPTS = 3

PHASE_RESERVED = "reserved"
PHASE_SERVICE_STARTED = "service_started"
PHASE_SERVICE_RETURNED = "service_returned"

ATTEMPT_KEY_INFIX = "#a"

AUDIT_ACTOR = "outbox"


class OutboxError(RuntimeError):
    """Base class for outbox failures the caller must observe."""


class OutboxConflictError(OutboxError):
    """An ``idempotency_key`` is already bound to a different effect."""


class PayloadRefNotFoundError(OutboxError):
    """``payload_ref`` does not resolve to a stored payload (K9-2, N-3)."""


class UnreadableEntryError(OutboxError):
    """A persisted/legacy entry cannot be interpreted; never silently coerced."""


class OutboxSchemaError(OutboxError):
    """The persisted schema version is unreadable or newer than this code."""


class EffectKind(StrEnum):
    KNOWLEDGE_WRITE = "knowledge_write"
    EXPERIMENT_RUN = "experiment_run"
    NOTIFICATION = "notification"
    PUBLISH = "publish"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class OutboxEntry(BaseModel):
    """K9 ``OutboxEntry``.

    ``delivered_at`` is ``None`` until the effect has actually been delivered:
    "not delivered yet" must not be recorded as a normal timestamp.
    ``attempts`` is *derived* from the durable per-attempt rows (see
    :meth:`Outbox._attempts`), so a crash between "effect attempted" and
    "attempt counter written" cannot lose the count.
    """

    outbox_id: str
    idempotency_key: str
    effect_kind: EffectKind
    payload_ref: str
    status: OutboxStatus = OutboxStatus.PENDING
    attempts: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    delivered_at: datetime | None = None
    last_error: str | None = None


class DeliveryOutcome(BaseModel):
    """Observable result of one :meth:`Outbox.deliver` call."""

    outbox_id: str
    idempotency_key: str
    status: OutboxStatus
    delivered: bool
    #: True when the effect was *not* run because it had already been delivered
    #: (K9-1).  ``delivered`` stays True: the effect is in place.
    replayed: bool = False
    attempts: int = 0
    reason: str | None = None
    result: dict[str, Any] | None = None


class SchemaMigrationReport(BaseModel):
    """M04-06 audit record for one :meth:`Outbox.migrate` call."""

    from_version: int
    to_version: int
    migrated: int = 0
    skipped: int = 0
    rolled_back: bool = False
    refused: bool = False
    diagnostics: list[str] = Field(default_factory=list)


Effector = Callable[[dict[str, Any]], Mapping[str, Any] | None]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def outbox_id_for(idempotency_key: str) -> str:
    """Deterministic id: one entry per ``idempotency_key``, by construction."""

    return f"outbox_{_digest(idempotency_key)}"


def _attempt_key(idempotency_key: str, attempt: int) -> str:
    return f"{idempotency_key}{ATTEMPT_KEY_INFIX}{attempt}"


def _confirmed_delivery(record: Mapping[str, Any] | None) -> bool:
    """True when an attempt row records a confirmed delivery."""

    return record is not None and (record.get("result") or {}).get("delivered") is True


def _delivered_marker(record: Mapping[str, Any] | None) -> bool:
    """True when the K9-1 effect marker records a finalized delivery."""

    return (
        record is not None
        and record.get("state") == "finalized"
        and _confirmed_delivery(record)
    )


def _normalize_entry_payload(raw: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Map a persisted entry onto the current shape (M04-06).

    Returns ``(payload, None)`` when the row is interpretable and
    ``(None, diagnostic)`` when it is not.  Uninterpretable rows are reported,
    never coerced into a plausible looking entry.
    """

    for field in ("outbox_id", "idempotency_key", "effect_kind", "payload_ref"):
        value = raw.get(field)
        if not isinstance(value, str) or not value:
            return None, f"legacy entry is missing a usable {field!r}"
    payload = dict(raw)
    legacy_status = payload.get("status")
    if legacy_status in (None, ""):
        payload["status"] = OutboxStatus.PENDING.value
    elif legacy_status == "sent":
        payload["status"] = OutboxStatus.DELIVERED.value
    elif legacy_status == "error":
        payload["status"] = OutboxStatus.FAILED.value
    payload.setdefault("attempts", 0)
    payload.setdefault("delivered_at", None)
    payload.setdefault("last_error", None)
    try:
        OutboxEntry.model_validate(payload)
    except Exception as exc:  # pragma: no cover - pydantic message only
        return None, f"legacy entry {payload.get('outbox_id')!r} is not an OutboxEntry: {exc}"
    return payload, None


class Outbox:
    """Outbox over the existing :class:`RecordStore` (K9).

    Deliberately *not* a new store: it composes the repository's existing
    idempotency primitives instead of adding a table or a second writer.
    """

    def __init__(self, store: RecordStore, *, max_attempts: int = DEFAULT_MAX_ATTEMPTS):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.store = store
        self.max_attempts = max_attempts

    # ------------------------------------------------------------------ write

    def register_payload(self, payload_ref: str, payload: Mapping[str, Any]) -> None:
        """Store a payload body; ``payload_ref`` is the id an entry points at."""

        if not payload_ref:
            raise ValueError("payload_ref must be a non-empty string")
        self.store.put(PAYLOAD_KIND, payload_ref, dict(payload))

    def payload(self, payload_ref: str) -> dict[str, Any]:
        value = self.store.get(PAYLOAD_KIND, payload_ref)
        if value is None:
            raise PayloadRefNotFoundError(f"no payload registered for ref {payload_ref!r}")
        return value

    def enqueue(
        self,
        *,
        effect_kind: EffectKind | str,
        idempotency_key: str,
        payload_ref: str,
    ) -> tuple[OutboxEntry, bool]:
        """Record the intent to perform ``effect_kind``; returns ``(entry, created)``.

        K9-2: there is no parameter that would accept a payload body, so an
        entry cannot inline one.  A duplicate ``idempotency_key`` resolves to
        the *same* entry (``created=False``) because the id is derived from the
        key; a key rebound to a different effect is a hard conflict.
        """

        if not idempotency_key:
            raise ValueError("idempotency_key must be a non-empty string")
        kind = EffectKind(effect_kind)
        outbox_id = outbox_id_for(idempotency_key)
        existing = self.entry(outbox_id)
        if existing is not None:
            if (existing.effect_kind, existing.payload_ref) != (kind, payload_ref):
                raise OutboxConflictError(
                    f"idempotency_key {idempotency_key!r} is already bound to "
                    f"{existing.effect_kind.value}/{existing.payload_ref!r}"
                )
            return existing, False
        # Raises PayloadRefNotFoundError (N-3) instead of accepting a dangling ref.
        self.payload(payload_ref)
        entry = OutboxEntry(
            outbox_id=outbox_id,
            idempotency_key=idempotency_key,
            effect_kind=kind,
            payload_ref=payload_ref,
        )
        self.store.put(OUTBOX_KIND, outbox_id, entry)
        return entry, True

    # ------------------------------------------------------------------- read

    def entry(self, outbox_id: str) -> OutboxEntry | None:
        raw = self.store.get(OUTBOX_KIND, outbox_id)
        if raw is None:
            return None
        return OutboxEntry.model_validate(raw)

    def entries(self) -> list[OutboxEntry]:
        rows = [OutboxEntry.model_validate(raw) for raw in self.store.list(OUTBOX_KIND)]
        rows.sort(key=lambda item: (item.created_at, item.outbox_id))
        return rows

    def pending(self) -> list[OutboxEntry]:
        """Entries still awaiting a confirmed delivery (``pending`` only)."""

        return [entry for entry in self.entries() if entry.status is OutboxStatus.PENDING]

    # -------------------------------------------------------------- delivery

    def deliver(self, outbox_id: str, effector: Effector) -> DeliveryOutcome:
        """Run the effect at most once, recording every attempt durably.

        Crash-safe shape, using the existing two-phase vocabulary:

        * an attempt that is ``pending`` at ``service_started`` means the effect
          may have run and its outcome was never written down -> the answer is
          **unknown** and nothing is re-run (fail closed).  Resolve it with
          :meth:`resolve_unknown`.
        * an attempt that is ``pending`` at ``service_returned`` means the
          effect ran and only the bookkeeping was lost -> the staged result is
          finalized, and the effect is **not** run again (I7 resume).
        * an attempt that is finalized with ``delivered=False`` is a *definite*
          failure: the effect provably did not happen, so a retry is allowed
          until the ``max_attempts`` budget is spent (K9-3).
        """

        entry = self.entry(outbox_id)
        if entry is None:
            raise KeyError(f"unknown outbox entry: {outbox_id}")

        pre = self._resolve_existing(entry)
        if pre is not None:
            return pre

        attempt = self._claim_attempt(entry)
        if attempt is None:
            return self._spend_budget(entry)

        # Re-check after claiming: another worker may have finished the effect
        # between the pre-check and the claim.  The transition guards in
        # storage.py only protect phase writes, so this window is ours to close.
        raced = self._resolve_existing(entry, claimed_attempt=attempt)
        if raced is not None:
            return raced

        return self._run_attempt(entry, attempt, effector)

    def _resolve_existing(
        self, entry: OutboxEntry, *, claimed_attempt: int | None = None
    ) -> DeliveryOutcome | None:
        """Return an outcome when no effect may run, else ``None``."""

        key = entry.idempotency_key
        effect_marker = self.store.get_idempotent(EFFECT_SCOPE, key)
        if _delivered_marker(effect_marker):
            return self._replayed(entry)
        latest = self._latest_attempt(key)
        if latest is None:
            return None
        number, record = latest
        if record.get("state") == "finalized":
            if _confirmed_delivery(record):
                return self._replayed(entry)
            return None  # a definite failure: a retry is allowed
        phase = record.get("phase", PHASE_RESERVED)
        if phase == PHASE_SERVICE_RETURNED:
            staged = record.get("staged_result")
            staged_result = dict(staged) if isinstance(staged, dict) else {}
            self._finalize_attempt(
                entry, number, delivered=True, result=staged_result, reason="resumed"
            )
            # A peer may have finalized first; report what the ledger actually
            # holds rather than what we were about to write.
            settled = self.store.get_idempotent(ATTEMPT_SCOPE, _attempt_key(key, number)) or {}
            recorded = (settled.get("result") or {}).get("result")
            return self._delivered(
                entry,
                result=recorded if isinstance(recorded, dict) else staged_result,
                reason="finalized a staged result",
            )
        if phase == PHASE_SERVICE_STARTED:
            reason = (
                "unknown outcome: a previous attempt started this effect without "
                "recording a result; refusing to run it again"
            )
            # An in-flight worker and a crashed worker are indistinguishable
            # from the durable state, so both fail closed.
            if claimed_attempt is None:
                self._mark_unknown(entry, reason)
                return DeliveryOutcome(
                    outbox_id=entry.outbox_id,
                    idempotency_key=key,
                    status=OutboxStatus.FAILED,
                    delivered=False,
                    attempts=self._attempts(key),
                    reason=reason,
                )
            return DeliveryOutcome(
                outbox_id=entry.outbox_id,
                idempotency_key=key,
                status=entry.status,
                delivered=False,
                attempts=self._attempts(key),
                reason="another worker currently holds this attempt",
            )
        return None

    def _run_attempt(self, entry: OutboxEntry, attempt: int, effector: Effector) -> DeliveryOutcome:
        key = entry.idempotency_key
        self.store.reserve_idempotent(
            EFFECT_SCOPE,
            key,
            {"outbox_id": entry.outbox_id, "effect_kind": entry.effect_kind.value},
            events=[
                (
                    "outbox.effect_reserved",
                    {"outbox_id": entry.outbox_id, "idempotency_key": key},
                    None,
                    AUDIT_ACTOR,
                )
            ],
        )
        self.store.mark_idempotent_phase(
            ATTEMPT_SCOPE,
            _attempt_key(key, attempt),
            PHASE_SERVICE_STARTED,
            staged_result={"outbox_id": entry.outbox_id, "attempt": attempt},
            events=[
                (
                    "outbox.delivery_started",
                    {
                        "outbox_id": entry.outbox_id,
                        "idempotency_key": key,
                        "attempt": attempt,
                    },
                    None,
                    AUDIT_ACTOR,
                )
            ],
        )
        try:
            # K9-2 / N-3: the body is resolved through the reference, and a ref
            # that stopped resolving is an observable failure, not a no-op.
            body = self.payload(entry.payload_ref)
            produced = effector(body)
        except Exception as exc:
            # A raised effector is a *definite* failure of this attempt: nothing
            # was confirmed, so the slot is spent and a retry is allowed (K9-3).
            reason = f"{type(exc).__name__}: {exc}"
            self._finalize_attempt(entry, attempt, delivered=False, reason=reason)
            attempts = self._attempts(key)
            spent = attempts >= self.max_attempts
            if spent:
                reason = f"{reason}; attempt budget exhausted after {attempts} attempt(s)"
            status = OutboxStatus.FAILED if spent else OutboxStatus.PENDING
            self._write_entry(entry, status=status, last_error=reason)
            return DeliveryOutcome(
                outbox_id=entry.outbox_id,
                idempotency_key=key,
                status=status,
                delivered=False,
                attempts=attempts,
                reason=reason,
            )
        result = dict(produced) if isinstance(produced, Mapping) else {}
        self.store.mark_idempotent_phase(
            ATTEMPT_SCOPE,
            _attempt_key(key, attempt),
            PHASE_SERVICE_RETURNED,
            staged_result={**result, "outbox_id": entry.outbox_id, "attempt": attempt},
            events=[
                (
                    "outbox.delivery_returned",
                    {"outbox_id": entry.outbox_id, "attempt": attempt},
                    None,
                    AUDIT_ACTOR,
                )
            ],
        )
        self._finalize_attempt(entry, attempt, delivered=True, result=result)
        return self._delivered(entry, result=result)

    def resolve_unknown(self, outbox_id: str, *, delivered: bool, reason: str) -> DeliveryOutcome:
        """Close an attempt that is stuck at ``service_started``.

        The caller supplies the knowledge the database cannot: whether the
        effect actually happened.  ``delivered=False`` releases the attempt as a
        definite failure so a retry becomes possible again.
        """

        entry = self.entry(outbox_id)
        if entry is None:
            raise KeyError(f"unknown outbox entry: {outbox_id}")
        key = entry.idempotency_key
        latest = self._latest_attempt(key)
        if latest is None:
            raise OutboxError(f"no attempt to resolve for {outbox_id}")
        number, record = latest
        if record.get("state") == "finalized":
            raise OutboxError(f"attempt {number} of {outbox_id} is already finalized")
        if not delivered:
            self._finalize_attempt(entry, number, delivered=False, reason=reason)
            self._write_entry(entry, status=OutboxStatus.PENDING, last_error=reason)
            return DeliveryOutcome(
                outbox_id=outbox_id,
                idempotency_key=key,
                status=OutboxStatus.PENDING,
                delivered=False,
                attempts=self._attempts(key),
                reason=reason,
            )
        staged = record.get("staged_result")
        result = dict(staged) if isinstance(staged, dict) else {}
        self._finalize_attempt(entry, number, delivered=True, result=result, reason=reason)
        return self._delivered(entry, result=result, reason=reason)

    # --------------------------------------------------------------- internals

    def _latest_attempt(self, key: str) -> tuple[int, dict[str, Any]] | None:
        for number in range(self.max_attempts, 0, -1):
            record = self.store.get_idempotent(ATTEMPT_SCOPE, _attempt_key(key, number))
            if record is not None:
                return number, record
        return None

    def _attempts(self, key: str) -> int:
        return sum(
            1
            for number in range(1, self.max_attempts + 1)
            if self.store.get_idempotent(ATTEMPT_SCOPE, _attempt_key(key, number)) is not None
        )

    def _claim_attempt(self, entry: OutboxEntry) -> int | None:
        """Reserve the lowest free attempt slot; ``None`` when the budget is spent.

        Concurrency: the slot is taken by ``reserve_idempotent``, whose
        ``INSERT OR IGNORE`` + ``rowcount`` decides the winner against the
        ``(scope, idempotency_key)`` primary key of the existing ``idempotency``
        table.  Two workers racing for the same slot therefore cannot both win,
        and the budget can never be lost by a read-modify-write race.
        """

        for number in range(1, self.max_attempts + 1):
            if self.store.reserve_idempotent(
                ATTEMPT_SCOPE,
                _attempt_key(entry.idempotency_key, number),
                {"outbox_id": entry.outbox_id, "attempt": number},
                events=[
                    (
                        "outbox.attempt_claimed",
                        {
                            "outbox_id": entry.outbox_id,
                            "idempotency_key": entry.idempotency_key,
                            "attempt": number,
                        },
                        None,
                        AUDIT_ACTOR,
                    )
                ],
            ):
                return number
        return None

    def _finalize_attempt(
        self,
        entry: OutboxEntry,
        attempt: int,
        *,
        delivered: bool,
        result: Mapping[str, Any] | None = None,
        reason: str | None = None,
    ) -> bool:
        """Finalize an attempt; ``False`` when a peer got there first.

        ``RecordStore.finalize_idempotent`` is *not* idempotent -- it raises on an
        already finalized record -- so two workers that both observe
        ``service_returned`` (one finishing, one resuming) would collide.  The
        re-check plus the tolerated ``already finalized`` rejection make the
        transition safe to attempt from both.
        """

        key = _attempt_key(entry.idempotency_key, attempt)
        current = self.store.get_idempotent(ATTEMPT_SCOPE, key)
        if current is not None and current.get("state") == "finalized":
            return False
        payload: dict[str, Any] = {
            "delivered": delivered,
            "outbox_id": entry.outbox_id,
            "attempt": attempt,
        }
        if result:
            payload["result"] = dict(result)
        if reason:
            payload["reason"] = reason
        try:
            self.store.finalize_idempotent(
                ATTEMPT_SCOPE,
                key,
                payload,
                events=[
                    (
                        "outbox.delivered" if delivered else "outbox.delivery_failed",
                        {
                            "outbox_id": entry.outbox_id,
                            "attempt": attempt,
                            "reason": reason,
                        },
                        None,
                        AUDIT_ACTOR,
                    )
                ],
            )
        except RuntimeError as exc:
            if "already finalized" not in str(exc):
                raise
            return False
        if delivered:
            # The K9-1 marker: finalized + delivered=True means the effect is
            # in place, so every later delivery with this key is rejected.
            marker = self.store.get_idempotent(EFFECT_SCOPE, entry.idempotency_key)
            if marker is not None and marker.get("state") != "finalized":
                try:
                    self.store.finalize_idempotent(
                        EFFECT_SCOPE,
                        entry.idempotency_key,
                        {"delivered": True, "outbox_id": entry.outbox_id, "attempt": attempt},
                    )
                except RuntimeError as exc:
                    if "already finalized" not in str(exc):
                        raise
            self._write_entry(
                entry,
                status=OutboxStatus.DELIVERED,
                delivered_at=utc_now(),
                last_error=None,
            )
        return True

    def _spend_budget(self, entry: OutboxEntry) -> DeliveryOutcome:
        """K9-3: no attempt slot left -> ``failed``, and never retried again.

        The ``failed`` label is written only when the whole attempt ledger is
        terminal and undelivered.  A worker that merely lost the race for a slot
        must not label the entry: a peer may still be mid-effect, and a losing
        writer cannot see whether that peer has finished.
        """

        key = entry.idempotency_key
        marker = self.store.get_idempotent(EFFECT_SCOPE, key)
        if _delivered_marker(marker):
            return self._replayed(entry)
        claimed = [
            record
            for record in (
                self.store.get_idempotent(ATTEMPT_SCOPE, _attempt_key(key, number))
                for number in range(1, self.max_attempts + 1)
            )
            if record is not None
        ]
        if not claimed or any(record.get("state") != "finalized" for record in claimed):
            return DeliveryOutcome(
                outbox_id=entry.outbox_id,
                idempotency_key=key,
                status=entry.status,
                delivered=False,
                attempts=len(claimed),
                reason="attempt budget spent; a peer attempt is still open, no label written",
            )
        if any(_confirmed_delivery(record) for record in claimed):
            return self._replayed(entry)
        reason = f"attempt budget exhausted after {len(claimed)} attempt(s)"
        self._write_entry(entry, status=OutboxStatus.FAILED, last_error=reason)
        return DeliveryOutcome(
            outbox_id=entry.outbox_id,
            idempotency_key=key,
            status=OutboxStatus.FAILED,
            delivered=False,
            attempts=len(claimed),
            reason=reason,
        )

    def _mark_unknown(self, entry: OutboxEntry, reason: str) -> None:
        """Label a stuck attempt ``failed`` -- unless it was resolved meanwhile."""

        marker = self.store.get_idempotent(EFFECT_SCOPE, entry.idempotency_key)
        if _delivered_marker(marker):
            return
        latest = self._latest_attempt(entry.idempotency_key)
        if latest is None or latest[1].get("state") == "finalized":
            return
        if latest[1].get("phase") != PHASE_SERVICE_STARTED:
            return
        self._write_entry(entry, status=OutboxStatus.FAILED, last_error=reason)

    def _write_entry(
        self,
        entry: OutboxEntry,
        *,
        status: OutboxStatus | None = None,
        delivered_at: datetime | None = None,
        last_error: str | None = None,
    ) -> OutboxEntry:
        updated = entry.model_copy(
            update={
                "status": status if status is not None else entry.status,
                "attempts": self._attempts(entry.idempotency_key),
                # "not delivered yet" must never be recorded as a normal value,
                # so an unset delivered_at is carried over, never invented.
                "delivered_at": delivered_at if delivered_at is not None else entry.delivered_at,
                "last_error": last_error,
            }
        )
        self.store.put(OUTBOX_KIND, updated.outbox_id, updated)
        return updated

    def _replayed(self, entry: OutboxEntry) -> DeliveryOutcome:
        return DeliveryOutcome(
            outbox_id=entry.outbox_id,
            idempotency_key=entry.idempotency_key,
            status=OutboxStatus.DELIVERED,
            delivered=True,
            replayed=True,
            attempts=self._attempts(entry.idempotency_key),
            reason="duplicate delivery rejected: this idempotency_key was already delivered",
        )

    def _delivered(
        self,
        entry: OutboxEntry,
        *,
        result: Mapping[str, Any] | None = None,
        reason: str | None = None,
    ) -> DeliveryOutcome:
        return DeliveryOutcome(
            outbox_id=entry.outbox_id,
            idempotency_key=entry.idempotency_key,
            status=OutboxStatus.DELIVERED,
            delivered=True,
            attempts=self._attempts(entry.idempotency_key),
            reason=reason,
            result=dict(result) if result else None,
        )

    # ------------------------------------------------------------- migration

    def schema_version(self) -> int:
        """Persisted outbox schema version; ``0`` means "not versioned yet".

        An *unreadable* version record raises instead of degrading to ``0``:
        "missing" and "unparseable" must not collapse into the same value.
        """

        record = self.store.get(SCHEMA_KIND, VERSION_RECORD_ID)
        if record is None:
            return 0
        version = record.get("version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise OutboxSchemaError(f"outbox schema version record is unreadable: {record!r}")
        return version

    def migrate(self) -> SchemaMigrationReport:
        """Bring an empty/legacy outbox database up to :data:`SCHEMA_VERSION`.

        The rewrite is all-or-nothing: every normalized entry and the version
        record are written on one :meth:`RecordStore.transaction` connection, so
        a failure part way through leaves the database exactly as it was and
        records the failure (``outbox_schema/migration_failure``) for audit --
        M04-06's "partial failure rolls back and stays auditable".
        """

        current = self.schema_version()
        if current > SCHEMA_VERSION:
            diagnostic = (
                f"refusing to migrate: database is at version {current}, this code "
                f"understands up to {SCHEMA_VERSION}"
            )
            return SchemaMigrationReport(
                from_version=current, to_version=current, refused=True, diagnostics=[diagnostic]
            )

        normalized: list[tuple[str, dict[str, Any]]] = []
        skipped = 0
        diagnostics: list[str] = []
        for raw in self.store.list(OUTBOX_KIND):
            payload, diagnostic = _normalize_entry_payload(raw)
            if payload is None:
                skipped += 1
                diagnostics.append(diagnostic or "unreadable legacy entry")
                continue
            normalized.append((payload["outbox_id"], payload))

        already = current == SCHEMA_VERSION
        rewritten = 0 if already else len(normalized)
        version_record = {
            "version": SCHEMA_VERSION,
            "migrated_at": utc_now().isoformat(),
            "from_version": current,
            "entries": len(normalized),
        }
        try:
            with self.store.transaction() as connection:
                for record_id, payload in normalized:
                    if already:
                        continue
                    self.store._write_record(connection, OUTBOX_KIND, record_id, payload)
                if not already:
                    self.store._write_record(
                        connection, SCHEMA_KIND, VERSION_RECORD_ID, version_record
                    )
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            self._record_migration_failure(current, reason)
            return SchemaMigrationReport(
                from_version=current,
                to_version=current,
                skipped=skipped,
                rolled_back=True,
                diagnostics=[*diagnostics, f"migration rolled back: {reason}"],
            )

        if already:
            diagnostics.append(f"already at version {SCHEMA_VERSION}; nothing rewritten")
        elif not normalized:
            diagnostics.append("empty outbox database; wrote schema version only")
        return SchemaMigrationReport(
            from_version=current,
            to_version=SCHEMA_VERSION,
            migrated=rewritten,
            skipped=skipped,
            diagnostics=diagnostics,
        )

    def _record_migration_failure(self, from_version: int, reason: str) -> None:
        """Audit a rolled back migration -- written outside the aborted transaction."""

        self.store.put(
            SCHEMA_KIND,
            MIGRATION_FAILURE_RECORD_ID,
            {
                "from_version": from_version,
                "attempted_version": SCHEMA_VERSION,
                "reason": reason,
                "failed_at": utc_now().isoformat(),
            },
        )

    def migration_failure(self) -> dict[str, Any] | None:
        return self.store.get(SCHEMA_KIND, MIGRATION_FAILURE_RECORD_ID)
