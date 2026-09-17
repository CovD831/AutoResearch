"""R-007 L-03 / M04: K9 outbox, checkpoint-resume safety, migration.

Evidence discipline for the reader:

* The core negative (N-1) asserts the number of *external side effects* (rows in
  a foreign sink), never ``attempts == 1``.  Asserting a counter would test the
  counter, not the idempotency semantics.
* Concurrency claims are only made by the *instrumented* tests.  Each forces the
  interleaving with a :class:`_Gate` and asserts the gate really was reached by
  two distinct threads, so it cannot pass by accidentally serialised threads.
* ``test_uninstrumented_concurrency_is_only_a_regression_guard`` is explicitly
  marked as having **no discriminating power**.
* The discriminating-power control is
  ``test_counterfactual_read_modify_write_counter_loses_an_increment``: it runs
  the *naive* way of spending an attempt budget under the same gate and shows it
  loses an update -- which is what makes ``test_concurrent_attempt_slots_are_never_lost``
  non-vacuous.
"""

from __future__ import annotations

import ast
import os
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

import pytest

from autoresearch.contracts import utc_now
from autoresearch.outbox import (
    ATTEMPT_SCOPE,
    DEFAULT_MAX_ATTEMPTS,
    EFFECT_SCOPE,
    OUTBOX_KIND,
    PAYLOAD_KIND,
    SCHEMA_KIND,
    SCHEMA_VERSION,
    VERSION_RECORD_ID,
    DeliveryOutcome,
    EffectKind,
    Outbox,
    OutboxConflictError,
    OutboxEntry,
    OutboxSchemaError,
    OutboxStatus,
    PayloadRefNotFoundError,
    outbox_id_for,
)
from autoresearch.storage import RecordStore

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
OUTBOX_MODULE = SRC_ROOT / "autoresearch" / "outbox.py"

#: K9 field list, transcribed from ``04-l2-contracts.md`` K9.
K9_FIELDS = {
    "outbox_id",
    "idempotency_key",
    "effect_kind",
    "payload_ref",
    "status",
    "attempts",
    "created_at",
    "delivered_at",
}

SINK_DDL = (
    "CREATE TABLE IF NOT EXISTS effects ("
    "  seq INTEGER PRIMARY KEY AUTOINCREMENT,"
    "  effect_key TEXT NOT NULL,"
    "  payload_ref TEXT NOT NULL,"
    "  at TEXT NOT NULL"
    ")"
)


# --------------------------------------------------------------------------- helpers


class Sink:
    """A foreign downstream system: append-only, deliberately NOT deduplicating.

    Deduplication is the outbox's job.  A deduplicating sink would make a
    duplicated side effect invisible, and N-1 could not be tested at all.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(SINK_DDL)
            connection.commit()

    def write(self, effect_key: str, payload_ref: str) -> None:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                "INSERT INTO effects (effect_key, payload_ref, at) VALUES (?, ?, ?)",
                (effect_key, payload_ref, "2026-09-15T00:00:00+00:00"),
            )
            connection.commit()

    def count(self) -> int:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT COUNT(*) FROM effects").fetchone()
        return int(row[0])


def _store(tmp_path: Path, name: str = "outbox.sqlite3") -> RecordStore:
    return RecordStore(tmp_path / name)


def _sink_effector(sink: Sink, key: str, *, record_calls: list[str] | None = None):
    def effector(payload: dict) -> dict:
        if record_calls is not None:
            record_calls.append(key)
        sink.write(key, payload.get("payload_ref", "?"))
        return {"sink_rows": sink.count()}

    return effector


def _failing_effector(record_calls: list[str], message: str = "downstream said no"):
    def effector(payload: dict) -> dict:  # noqa: ARG001
        record_calls.append("called")
        raise RuntimeError(message)

    return effector


class _Gate:
    """Instrumentation: hold threads until ``parties`` distinct threads arrive.

    Used to force the interleavings that natural races cannot reliably produce
    under the GIL.  ``threads`` records which threads actually reached the gate,
    so a test can assert the instrumentation was effective.
    """

    def __init__(self, parties: int = 2, timeout: float = 10.0):
        self._lock = threading.Lock()
        self._parties = parties
        self._arrivals = 0
        self._released = threading.Event()
        self._timeout = timeout
        self.threads: set[int] = set()

    def arrive(self) -> None:
        with self._lock:
            self.threads.add(threading.get_ident())
            self._arrivals += 1
            if self._arrivals >= self._parties:
                self._released.set()
        self._released.wait(self._timeout)


def _run_threads(targets: list) -> list:
    results: list = [None] * len(targets)
    errors: list = [None] * len(targets)

    def wrap(index: int, fn) -> None:
        try:
            results[index] = fn()
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors[index] = exc

    threads = [threading.Thread(target=wrap, args=(i, fn)) for i, fn in enumerate(targets)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert all(not thread.is_alive() for thread in threads), "worker thread did not finish"
    if any(errors):
        raise AssertionError(f"worker thread raised: {errors}")
    return results


def _prepared(tmp_path: Path, *, max_attempts: int = DEFAULT_MAX_ATTEMPTS):
    store = _store(tmp_path)
    outbox = Outbox(store, max_attempts=max_attempts)
    outbox.register_payload("payload-1", {"payload_ref": "payload-1"})
    entry, _ = outbox.enqueue(
        effect_kind=EffectKind.KNOWLEDGE_WRITE,
        idempotency_key="key-1",
        payload_ref="payload-1",
    )
    return store, outbox, entry


def _legacy_entry(index: int, **overrides) -> dict:
    row = {
        "outbox_id": f"outbox_old{index}",
        "idempotency_key": f"k{index}",
        "effect_kind": "publish",
        "payload_ref": f"p{index}",
        "status": "sent",
        "created_at": f"2026-01-0{index}T00:00:00+00:00",
    }
    row.update(overrides)
    return row


def _outbox_events(tmp_path: Path, name: str = "outbox.sqlite3") -> list[tuple[str, str]]:
    with closing(sqlite3.connect(tmp_path / name)) as connection:
        rows = connection.execute(
            "SELECT event_type, payload_json FROM audit_events ORDER BY created_at, event_id"
        ).fetchall()
    return [(row[0], row[1]) for row in rows]


# --------------------------------------------------------------- K9 field contract


def test_outbox_entry_covers_every_k9_field() -> None:
    fields = set(OutboxEntry.model_fields)
    assert fields >= K9_FIELDS, f"missing K9 fields: {sorted(K9_FIELDS - fields)}"
    # The only extension is the auditable reason an entry is stuck (documented).
    assert fields - K9_FIELDS == {"last_error"}


def test_k9_enum_domains_match_the_contract() -> None:
    assert [kind.value for kind in EffectKind] == [
        "knowledge_write",
        "experiment_run",
        "notification",
        "publish",
    ]
    assert [status.value for status in OutboxStatus] == ["pending", "delivered", "failed"]


def test_every_effect_kind_round_trips(tmp_path: Path) -> None:
    store = _store(tmp_path)
    outbox = Outbox(store)
    sink = Sink(tmp_path / "sink.sqlite3")
    for kind in EffectKind:
        key = f"k-{kind.value}"
        outbox.register_payload(f"p-{kind.value}", {"payload_ref": f"p-{kind.value}"})
        entry, created = outbox.enqueue(
            effect_kind=kind, idempotency_key=key, payload_ref=f"p-{kind.value}"
        )
        assert created is True
        assert entry.effect_kind is kind
        outcome = outbox.deliver(entry.outbox_id, _sink_effector(sink, key))
        assert outcome.delivered is True
    assert sink.count() == 4


# ------------------------------------------------------------------- K9-2 reference


def test_payload_body_is_never_inlined_in_the_entry(tmp_path: Path) -> None:
    store = _store(tmp_path)
    outbox = Outbox(store)
    marker = "PAYLOAD-BODY-MARKER-6f2a1c"
    outbox.register_payload("payload-1", {"payload_ref": "payload-1", "body": marker})
    entry, _ = outbox.enqueue(
        effect_kind=EffectKind.KNOWLEDGE_WRITE,
        idempotency_key="key-1",
        payload_ref="payload-1",
    )

    stored = store.get(OUTBOX_KIND, entry.outbox_id)
    assert stored is not None
    assert "payload" not in stored
    assert marker not in repr(stored)
    assert store.get(PAYLOAD_KIND, "payload-1")["body"] == marker
    assert stored["payload_ref"] == "payload-1"


def test_delivery_resolves_the_body_through_the_reference(tmp_path: Path) -> None:
    outbox = Outbox(_store(tmp_path))
    seen: list[dict] = []
    outbox.register_payload("payload-1", {"payload_ref": "payload-1", "body": "hello"})
    entry, _ = outbox.enqueue(
        effect_kind=EffectKind.NOTIFICATION,
        idempotency_key="key-1",
        payload_ref="payload-1",
    )
    outcome = outbox.deliver(entry.outbox_id, lambda payload: seen.append(payload) or {"ok": True})
    assert seen == [{"payload_ref": "payload-1", "body": "hello"}]
    assert outcome.delivered is True


# ------------------------------------------------------------------ K9-1 / N-1 core


def test_duplicate_delivery_is_rejected_and_the_effect_happens_once(tmp_path: Path) -> None:
    """N-1, the core判据.

    Asserts the count of **external side effects** (rows in a foreign sink), not
    ``attempts == 1``: the latter would test the attempt counter rather than the
    idempotency semantics.
    """

    store = _store(tmp_path)
    outbox = Outbox(store)
    sink = Sink(tmp_path / "sink.sqlite3")
    calls: list[str] = []
    outbox.register_payload("payload-1", {"payload_ref": "payload-1"})
    entry, _ = outbox.enqueue(
        effect_kind=EffectKind.KNOWLEDGE_WRITE,
        idempotency_key="key-1",
        payload_ref="payload-1",
    )
    effector = _sink_effector(sink, "key-1", record_calls=calls)

    first = outbox.deliver(entry.outbox_id, effector)
    second = outbox.deliver(entry.outbox_id, effector)

    assert first.delivered is True and first.replayed is False
    assert second.delivered is True and second.replayed is True
    assert calls == ["key-1"], "the effector must be invoked exactly once"
    assert sink.count() == 1, "the external side effect must have happened exactly once"

    reopened = Outbox(_store(tmp_path)).entry(entry.outbox_id)
    assert reopened is not None
    assert reopened.status is OutboxStatus.DELIVERED
    assert reopened.delivered_at is not None


def test_duplicate_enqueue_collapses_to_the_single_existing_entry(tmp_path: Path) -> None:
    outbox = Outbox(_store(tmp_path))
    outbox.register_payload("payload-1", {"payload_ref": "payload-1"})
    first, created = outbox.enqueue(
        effect_kind=EffectKind.PUBLISH, idempotency_key="key-1", payload_ref="payload-1"
    )
    second, created_again = outbox.enqueue(
        effect_kind=EffectKind.PUBLISH, idempotency_key="key-1", payload_ref="payload-1"
    )
    assert (created, created_again) == (True, False)
    assert first.outbox_id == second.outbox_id == outbox_id_for("key-1")
    assert len(outbox.entries()) == 1


def test_rebinding_a_key_to_a_different_effect_is_a_conflict(tmp_path: Path) -> None:
    outbox = Outbox(_store(tmp_path))
    outbox.register_payload("payload-1", {"payload_ref": "payload-1"})
    outbox.enqueue(effect_kind=EffectKind.PUBLISH, idempotency_key="key-1", payload_ref="payload-1")
    with pytest.raises(OutboxConflictError):
        outbox.enqueue(
            effect_kind=EffectKind.NOTIFICATION,
            idempotency_key="key-1",
            payload_ref="payload-1",
        )


def test_a_duplicate_delivery_writes_no_new_audit_events(tmp_path: Path) -> None:
    """A rejected duplicate must not grow the audit chain (D-A6-07 defect family)."""

    store = _store(tmp_path)
    outbox = Outbox(store)
    sink = Sink(tmp_path / "sink.sqlite3")
    outbox.register_payload("payload-1", {"payload_ref": "payload-1"})
    entry, _ = outbox.enqueue(
        effect_kind=EffectKind.PUBLISH, idempotency_key="key-1", payload_ref="payload-1"
    )
    effector = _sink_effector(sink, "key-1")
    outbox.deliver(entry.outbox_id, effector)
    before = _outbox_events(tmp_path)
    assert before, "the first delivery must be auditable"
    outbox.deliver(entry.outbox_id, effector)
    assert _outbox_events(tmp_path) == before, "a rejected duplicate must be a no-op"


# --------------------------------------------------------------------- K9-3 / N-2


def test_attempt_budget_is_capped_and_the_entry_turns_failed(tmp_path: Path) -> None:
    """N-2: once the budget is spent, the effect is never attempted again."""

    store = _store(tmp_path)
    outbox = Outbox(store, max_attempts=3)
    calls: list[str] = []
    outbox.register_payload("payload-1", {"payload_ref": "payload-1"})
    entry, _ = outbox.enqueue(
        effect_kind=EffectKind.EXPERIMENT_RUN,
        idempotency_key="key-1",
        payload_ref="payload-1",
    )
    effector = _failing_effector(calls)

    outcomes = [outbox.deliver(entry.outbox_id, effector) for _ in range(3)]

    assert [outcome.status for outcome in outcomes[:2]] == [
        OutboxStatus.PENDING,
        OutboxStatus.PENDING,
    ], "a spent-but-not-exhausted budget stays retriable"
    assert len(calls) == 3
    assert outcomes[2].status is OutboxStatus.FAILED
    assert outcomes[2].reason is not None and "budget exhausted" in outcomes[2].reason

    again = outbox.deliver(entry.outbox_id, effector)
    assert again.status is OutboxStatus.FAILED
    assert len(calls) == 3, "a failed entry must not be retried"
    stored = outbox.entry(entry.outbox_id)
    assert stored is not None and stored.status is OutboxStatus.FAILED
    assert stored.attempts == 3


def test_the_budget_is_durable_across_a_fresh_outbox_instance(tmp_path: Path) -> None:
    first = Outbox(_store(tmp_path), max_attempts=2)
    calls: list[str] = []
    first.register_payload("payload-1", {"payload_ref": "payload-1"})
    entry, _ = first.enqueue(
        effect_kind=EffectKind.EXPERIMENT_RUN,
        idempotency_key="key-1",
        payload_ref="payload-1",
    )
    effector = _failing_effector(calls)
    first.deliver(entry.outbox_id, effector)
    first.deliver(entry.outbox_id, effector)

    restarted = Outbox(_store(tmp_path), max_attempts=2)
    outcome = restarted.deliver(entry.outbox_id, effector)
    assert outcome.status is OutboxStatus.FAILED
    assert len(calls) == 2, "a fresh process must not restart the budget"
    assert restarted.entry(entry.outbox_id).attempts == 2


def test_attempts_is_derived_from_the_durable_attempt_rows(tmp_path: Path) -> None:
    """A lost counter cannot lose the budget: ``attempts`` is derived, not stored."""

    store = _store(tmp_path)
    outbox = Outbox(store, max_attempts=3)
    calls: list[str] = []
    outbox.register_payload("payload-1", {"payload_ref": "payload-1"})
    entry, _ = outbox.enqueue(
        effect_kind=EffectKind.EXPERIMENT_RUN,
        idempotency_key="key-1",
        payload_ref="payload-1",
    )
    outbox.deliver(entry.outbox_id, _failing_effector(calls))
    outbox.deliver(entry.outbox_id, _failing_effector(calls))
    # The stored counter is clobbered to 0; the ledger still holds two attempts.
    store.put(OUTBOX_KIND, entry.outbox_id, entry.model_copy(update={"attempts": 0}))
    assert outbox.entry(entry.outbox_id).attempts == 0
    assert outbox.deliver(entry.outbox_id, _failing_effector(calls)).attempts == 3


# --------------------------------------------------------------------- K9-2 / N-3


def test_enqueue_rejects_a_dangling_payload_ref(tmp_path: Path) -> None:
    """N-3: a reference that does not resolve fails observably at the boundary."""

    outbox = Outbox(_store(tmp_path))
    with pytest.raises(PayloadRefNotFoundError):
        outbox.enqueue(
            effect_kind=EffectKind.PUBLISH,
            idempotency_key="key-1",
            payload_ref="never-registered",
        )
    assert outbox.entries() == []


def test_a_payload_ref_that_disappears_becomes_an_observable_failure(tmp_path: Path) -> None:
    store = _store(tmp_path)
    outbox = Outbox(store)
    sink = Sink(tmp_path / "sink.sqlite3")
    outbox.register_payload("payload-1", {"payload_ref": "payload-1"})
    entry, _ = outbox.enqueue(
        effect_kind=EffectKind.PUBLISH, idempotency_key="key-1", payload_ref="payload-1"
    )
    # Simulate the payload being purged between enqueue and delivery.
    with closing(sqlite3.connect(tmp_path / "outbox.sqlite3")) as connection:
        connection.execute(
            "DELETE FROM records WHERE kind=? AND record_id=?", (PAYLOAD_KIND, "payload-1")
        )
        connection.commit()

    outcome = outbox.deliver(entry.outbox_id, _sink_effector(sink, "key-1"))
    assert outcome.delivered is False
    assert outcome.status is OutboxStatus.PENDING
    assert outcome.reason is not None and "PayloadRefNotFoundError" in outcome.reason
    assert sink.count() == 0, "no side effect may happen without its payload"
    stored = outbox.entry(entry.outbox_id)
    assert stored is not None and stored.last_error is not None
    assert "PayloadRefNotFoundError" in stored.last_error


# --------------------------------------------------- crash windows / I7 fail-closed


def _fabricate_pending_attempt(store: RecordStore, entry: OutboxEntry, phase: str,
                               staged: dict | None = None) -> None:
    """Leave exactly the durable state a crash at ``phase`` would leave.

    Built with the same primitives a real run uses (including the store's own
    transition table -- reaching ``service_returned`` requires stepping through
    ``service_started``), so the fabricated state is the state the engine
    actually produces.
    """

    from autoresearch.outbox import _attempt_key

    key = _attempt_key(entry.idempotency_key, 1)
    store.reserve_idempotent(EFFECT_SCOPE, entry.idempotency_key, {"outbox_id": entry.outbox_id})
    store.reserve_idempotent(ATTEMPT_SCOPE, key, {"attempt": 1})
    store.mark_idempotent_phase(ATTEMPT_SCOPE, key, "service_started", staged_result=staged)
    if phase == "service_returned":
        store.mark_idempotent_phase(ATTEMPT_SCOPE, key, "service_returned", staged_result=staged)


def test_an_attempt_stuck_at_service_started_is_never_rerun(tmp_path: Path) -> None:
    """The effect may have happened; the honest answer is 'unknown', not 'retry'."""

    store, outbox, entry = _prepared(tmp_path)
    _fabricate_pending_attempt(store, entry, "service_started", {"attempt": 1})
    sink = Sink(tmp_path / "sink.sqlite3")
    calls: list[str] = []

    outcome = outbox.deliver(entry.outbox_id, _sink_effector(sink, "key-1", record_calls=calls))

    assert outcome.delivered is False
    assert outcome.status is OutboxStatus.FAILED
    assert outcome.reason is not None and "unknown outcome" in outcome.reason
    assert calls == [], "a fail-closed outcome must not run the effect"
    assert sink.count() == 0


def test_resolving_an_unknown_outcome_unblocks_a_retry(tmp_path: Path) -> None:
    store, outbox, entry = _prepared(tmp_path)
    _fabricate_pending_attempt(store, entry, "service_started", {"attempt": 1})
    sink = Sink(tmp_path / "sink.sqlite3")
    calls: list[str] = []

    outbox.deliver(entry.outbox_id, _sink_effector(sink, "key-1", record_calls=calls))
    released = outbox.resolve_unknown(
        entry.outbox_id, delivered=False, reason="operator: no effect"
    )
    assert released.delivered is False and released.status is OutboxStatus.PENDING

    retried = outbox.deliver(entry.outbox_id, _sink_effector(sink, "key-1", record_calls=calls))
    assert retried.delivered is True
    assert sink.count() == 1
    assert len(calls) == 1


def test_resolving_as_delivered_never_runs_the_effect_again(tmp_path: Path) -> None:
    store, outbox, entry = _prepared(tmp_path)
    _fabricate_pending_attempt(store, entry, "service_started", {"attempt": 1})
    sink = Sink(tmp_path / "sink.sqlite3")
    calls: list[str] = []

    closed = outbox.resolve_unknown(
        entry.outbox_id, delivered=True, reason="operator: sink already had it"
    )
    assert closed.delivered is True
    second = outbox.deliver(entry.outbox_id, _sink_effector(sink, "key-1", record_calls=calls))
    assert second.replayed is True
    assert calls == [] and sink.count() == 0


def test_a_staged_result_is_finalized_instead_of_rerun(tmp_path: Path) -> None:
    """I7: the effect already ran; only the bookkeeping was lost."""

    store, outbox, entry = _prepared(tmp_path)
    _fabricate_pending_attempt(store, entry, "service_returned", {"attempt": 1, "sink_rows": 7})
    sink = Sink(tmp_path / "sink.sqlite3")
    calls: list[str] = []

    outcome = outbox.deliver(entry.outbox_id, _sink_effector(sink, "key-1", record_calls=calls))

    assert outcome.delivered is True and outcome.replayed is False
    assert outcome.result == {"attempt": 1, "sink_rows": 7}
    assert calls == [], "a staged result must be finalized, not re-run"
    assert sink.count() == 0


def test_delivered_at_is_none_until_the_effect_actually_runs(tmp_path: Path) -> None:
    """Discipline: 'not delivered' must not be recorded as a normal value."""

    outbox = Outbox(_store(tmp_path), max_attempts=1)
    outbox.register_payload("payload-1", {"payload_ref": "payload-1"})
    entry, _ = outbox.enqueue(
        effect_kind=EffectKind.NOTIFICATION, idempotency_key="key-1", payload_ref="payload-1"
    )
    assert outbox.entry(entry.outbox_id).delivered_at is None
    outcome = outbox.deliver(entry.outbox_id, _failing_effector([]))
    assert outcome.status is OutboxStatus.FAILED
    stored = outbox.entry(entry.outbox_id)
    assert stored is not None and stored.delivered_at is None


# ------------------------------------------------------------------------- concurrency


def test_instrumented_concurrent_delivery_runs_the_effect_once(tmp_path: Path) -> None:
    """Instrumented: both workers are forced past the pre-check before either claims.

    Instrumentation = the gate inside ``get_idempotent``.  The assertion on
    ``len(gate.threads) == 2`` proves the interleaving really happened, so this
    test does not pass merely because the threads happened to be serialised.
    """

    store, outbox, entry = _prepared(tmp_path, max_attempts=1)
    sink = Sink(tmp_path / "sink.sqlite3")
    calls: list[str] = []
    gate = _Gate(parties=2)
    real_get = store.get_idempotent
    seen: set[int] = set()

    def gated_get(scope: str, key: str):
        record = real_get(scope, key)
        if scope == EFFECT_SCOPE and key == entry.idempotency_key:
            ident = threading.get_ident()
            if ident not in seen:
                seen.add(ident)
                gate.arrive()
        return record

    store.get_idempotent = gated_get  # type: ignore[method-assign]
    effector = _sink_effector(sink, "key-1", record_calls=calls)
    outcomes = _run_threads(
        [
            lambda: outbox.deliver(entry.outbox_id, effector),
            lambda: outbox.deliver(entry.outbox_id, effector),
        ]
    )

    assert len(gate.threads) == 2, "instrumentation did not actually overlap the workers"
    assert sink.count() == 1, "exactly one external side effect"
    assert len(calls) == 1, "the effector ran exactly once"
    assert any(outcome.delivered for outcome in outcomes)
    assert outbox.entry(entry.outbox_id).status is OutboxStatus.DELIVERED


def test_concurrent_delivery_with_multiple_attempts_runs_the_effect_once(tmp_path: Path) -> None:
    """Instrumented: with max_attempts > 1, two racers still run the effect once.

    Regression guard for a K9-1 at-most-once hole.  The per-attempt claim is
    atomic, so the second worker wins a *distinct* slot (slot 2); its re-check
    then only sees its own slot still at ``phase="reserved"`` and proceeds to
    run the effector -- duplicating the side effect unless attempts are kept
    strictly sequential.
    """

    store, outbox, entry = _prepared(tmp_path, max_attempts=2)
    sink = Sink(tmp_path / "sink.sqlite3")
    calls: list[str] = []
    gate = _Gate(parties=2)
    real_reserve = store.reserve_idempotent
    seen: set[int] = set()

    def gated_reserve(scope, key, request, events=None):  # noqa: ANN001
        if scope == EFFECT_SCOPE and key == entry.idempotency_key:
            ident = threading.get_ident()
            if ident not in seen:
                seen.add(ident)
                gate.arrive()
        return real_reserve(scope, key, request, events)

    store.reserve_idempotent = gated_reserve  # type: ignore[method-assign]
    effector = _sink_effector(sink, "key-1", record_calls=calls)
    outcomes = _run_threads(
        [
            lambda: outbox.deliver(entry.outbox_id, effector),
            lambda: outbox.deliver(entry.outbox_id, effector),
        ]
    )
    assert len(gate.threads) == 2, "instrumentation did not actually overlap the workers"
    assert sink.count() == 1, "exactly one external side effect under concurrency"
    assert len(calls) == 1, "the effector ran exactly once"
    assert any(outcome.delivered for outcome in outcomes)
    assert outbox.entry(entry.outbox_id).status is OutboxStatus.DELIVERED


def test_instrumented_concurrent_retries_cannot_exceed_the_attempt_budget(tmp_path: Path) -> None:
    """Instrumented: the attempt slot is arbitrated atomically, so none is overspent."""

    store, outbox, entry = _prepared(tmp_path, max_attempts=1)
    calls: list[str] = []
    gate = _Gate(parties=2)
    real_reserve = store.reserve_idempotent
    seen: set[int] = set()

    def gated_reserve(scope, key, request, events=None):  # noqa: ANN001
        if scope == ATTEMPT_SCOPE:
            ident = threading.get_ident()
            if ident not in seen:
                seen.add(ident)
                gate.arrive()
        return real_reserve(scope, key, request, events)

    store.reserve_idempotent = gated_reserve  # type: ignore[method-assign]
    outcomes = _run_threads(
        [
            lambda: outbox.deliver(entry.outbox_id, _failing_effector(calls)),
            lambda: outbox.deliver(entry.outbox_id, _failing_effector(calls)),
        ]
    )
    assert len(gate.threads) == 2, "instrumentation did not actually overlap the workers"
    assert len(calls) <= 1, "a budget of one attempt must admit at most one effect attempt"
    assert all(outcome.delivered is False for outcome in outcomes)


def test_concurrent_attempt_slots_are_never_lost(tmp_path: Path) -> None:
    """Instrumented: two racers get distinct slots, never the same one."""

    store, outbox, entry = _prepared(tmp_path, max_attempts=2)
    gate = _Gate(parties=2)
    real_reserve = store.reserve_idempotent
    seen: set[int] = set()

    def gated_reserve(scope, key, request, events=None):  # noqa: ANN001
        if scope == ATTEMPT_SCOPE:
            ident = threading.get_ident()
            if ident not in seen:
                seen.add(ident)
                gate.arrive()
        return real_reserve(scope, key, request, events)

    store.reserve_idempotent = gated_reserve  # type: ignore[method-assign]
    slots = _run_threads(
        [
            lambda: outbox._claim_attempt(entry),  # noqa: SLF001
            lambda: outbox._claim_attempt(entry),  # noqa: SLF001
        ]
    )
    assert len(gate.threads) == 2, "instrumentation did not actually overlap the workers"
    assert sorted(slots) == [1, 2], f"an attempt slot was lost: {slots}"


def test_counterfactual_read_modify_write_counter_loses_an_increment(tmp_path: Path) -> None:
    """Discriminating-power control, **not** a test of production behaviour.

    Runs the *naive* way of spending an attempt budget (read the counter, then
    write it back) under the same gate as
    ``test_concurrent_attempt_slots_are_never_lost``.  The naive version loses an
    increment -- which is exactly why the production claim goes through
    ``RecordStore.reserve_idempotent``.  If that production test were vacuous,
    this control would show a correct counter instead of a lost update.
    """

    store = _store(tmp_path)
    gate = _Gate(parties=2)
    observed: list[int] = []
    lock = threading.Lock()

    def naive_claim() -> int:
        current = store.get("naive_counter", "key-1") or {"n": 0}
        gate.arrive()  # both callers have read the same snapshot by now
        claimed = int(current["n"]) + 1
        with lock:
            observed.append(claimed)
        store.put("naive_counter", "key-1", {"n": claimed})
        return claimed

    _run_threads([naive_claim, naive_claim])
    assert len(gate.threads) == 2, "instrumentation did not actually overlap the workers"
    assert observed == [1, 1], f"the naive counter did not lose an update: {observed}"
    assert store.get("naive_counter", "key-1") == {"n": 1}


class _LedgerFreeOutbox(Outbox):
    """COUNTERFACTUAL control: budget and delivered flag kept in the entry record.

    This is the shape you get when an outbox does its own read-modify-write
    bookkeeping instead of reusing the store's idempotency primitives.  It exists
    only to prove that the instrumented delivery test is **not vacuous**: under
    this control the very same scenario produces two external side effects.
    """

    def _resolve_existing(self, entry, *, claimed_attempt=None):  # noqa: ANN001
        return None

    def _claim_attempt(self, entry):  # noqa: ANN001
        stored = self.entry(entry.outbox_id)
        assert stored is not None
        if stored.attempts >= self.max_attempts:
            return None
        return stored.attempts + 1

    def _spend_budget(self, entry):  # noqa: ANN001
        self._write_entry(entry, status=OutboxStatus.FAILED, last_error="budget exhausted")
        return DeliveryOutcome(
            outbox_id=entry.outbox_id,
            idempotency_key=entry.idempotency_key,
            status=OutboxStatus.FAILED,
            delivered=False,
            attempts=self.max_attempts,
            reason="budget exhausted",
        )

    def _run_attempt(self, entry, attempt, effector):  # noqa: ANN001
        produced = effector(self.payload(entry.payload_ref))
        result = dict(produced) if isinstance(produced, Mapping) else {}
        self._write_entry(
            entry, status=OutboxStatus.DELIVERED, delivered_at=utc_now(), last_error=None
        )
        return self._delivered(entry, result=result)


def test_counterfactual_a_ledger_free_outbox_duplicates_the_effect(tmp_path: Path) -> None:
    """Discriminating-power control: proves the instrumented delivery test bites.

    Same scenario and same instrumentation as
    ``test_instrumented_concurrent_delivery_runs_the_effect_once``, but with an
    outbox that keeps its budget in the entry record instead of the store's
    idempotency ledger.  The control yields **two** side effects where the
    production path yields one -- it is a *judgement-type* failure (a duplicate
    effect), not a missing-symbol failure.  If the production test were vacuous,
    this control would report a single row instead.
    """

    store, outbox, entry = _prepared(tmp_path, max_attempts=1)
    control = _LedgerFreeOutbox(store, max_attempts=1)
    sink = Sink(tmp_path / "sink.sqlite3")
    gate = _Gate(parties=2)
    original_claim = control._claim_attempt  # noqa: SLF001

    def gated_claim(target):  # noqa: ANN001
        gate.arrive()
        return original_claim(target)

    control._claim_attempt = gated_claim  # type: ignore[method-assign]
    effector = _sink_effector(sink, "key-1")
    _run_threads(
        [
            lambda: control.deliver(entry.outbox_id, effector),
            lambda: control.deliver(entry.outbox_id, effector),
        ]
    )

    assert len(gate.threads) == 2, "instrumentation did not actually overlap the workers"
    assert sink.count() == 2, (
        "the control must duplicate the side effect, otherwise the production "
        "assertion of == 1 proves nothing"
    )


def test_uninstrumented_concurrency_is_only_a_regression_guard(tmp_path: Path) -> None:
    """**This test has no discriminating power.**

    It starts two threads against the *unpatched* store, so under the GIL the
    second worker normally starts after the first has already finalized.  It
    passes whether or not the claim is atomic, so it can only serve as a
    regression guard (it would catch a crash or a plainly broken critical
    section).  The claim that concurrency is handled rests on the instrumented
    tests above, never on this one.
    """

    store, outbox, entry = _prepared(tmp_path, max_attempts=1)
    sink = Sink(tmp_path / "sink.sqlite3")
    calls: list[str] = []
    effector = _sink_effector(sink, "key-1", record_calls=calls)
    _run_threads(
        [
            lambda: outbox.deliver(entry.outbox_id, effector),
            lambda: outbox.deliver(entry.outbox_id, effector),
        ]
    )
    assert sink.count() == 1


# --------------------------------------------------------------------- M04-06 migration


def test_migrate_on_an_empty_database_only_writes_the_version(tmp_path: Path) -> None:
    outbox = Outbox(_store(tmp_path))
    assert outbox.schema_version() == 0
    report = outbox.migrate()
    assert (report.from_version, report.to_version) == (0, SCHEMA_VERSION)
    assert report.migrated == 0 and report.rolled_back is False
    assert outbox.schema_version() == SCHEMA_VERSION
    assert outbox.entries() == []


def test_migrate_normalizes_a_legacy_database(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.put(
        OUTBOX_KIND,
        "outbox_old1",
        _legacy_entry(1, status="sent"),
    )
    store.put(
        OUTBOX_KIND,
        "outbox_old2",
        _legacy_entry(2, status="error", attempts=1),
    )
    store.put(OUTBOX_KIND, "outbox_old3", _legacy_entry(3, status="pending"))

    outbox = Outbox(store)
    report = outbox.migrate()

    assert (report.from_version, report.to_version) == (0, SCHEMA_VERSION)
    assert report.migrated == 3 and report.skipped == 0 and report.rolled_back is False
    assert outbox.schema_version() == SCHEMA_VERSION
    assert outbox.entry("outbox_old1").status is OutboxStatus.DELIVERED
    assert outbox.entry("outbox_old1").delivered_at is None, "nothing may invent a delivery time"
    assert outbox.entry("outbox_old2").status is OutboxStatus.FAILED
    assert outbox.entry("outbox_old2").attempts == 1
    assert outbox.entry("outbox_old3").status is OutboxStatus.PENDING


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.put(OUTBOX_KIND, "outbox_old1", _legacy_entry(1))
    outbox = Outbox(store)
    outbox.migrate()
    second = outbox.migrate()
    assert second.migrated == 0
    assert second.from_version == second.to_version == SCHEMA_VERSION
    assert any("already at version" in line for line in second.diagnostics)


def test_migrate_reports_unreadable_legacy_rows_instead_of_coercing_them(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.put(
        OUTBOX_KIND,
        "outbox_broken",
        {"effect_kind": "publish", "payload_ref": "p1", "status": "pending"},
    )
    outbox = Outbox(store)
    report = outbox.migrate()
    assert report.skipped == 1
    assert any("missing a usable" in line for line in report.diagnostics), report.diagnostics
    assert report.to_version == SCHEMA_VERSION
    # The unreadable row is left exactly as it was found.
    assert store.get(OUTBOX_KIND, "outbox_broken")["payload_ref"] == "p1"


def test_migrate_rolls_back_a_partial_failure_and_stays_auditable(tmp_path: Path) -> None:
    """N-4: a half-written migration rolls back *and* leaves an audit trail."""

    store = _store(tmp_path)
    for index in range(1, 4):
        store.put(OUTBOX_KIND, f"outbox_old{index}", _legacy_entry(index))

    outbox = Outbox(store)
    real_write = RecordStore._write_record  # noqa: SLF001
    rewritten: list[str] = []

    def flaky_write(self, connection, kind, record_id, value, **kwargs):  # noqa: ANN001
        if kind == OUTBOX_KIND:
            rewritten.append(record_id)
            if record_id == "outbox_old3":
                raise sqlite3.OperationalError("disk I/O error")
        return real_write(self, connection, kind, record_id, value, **kwargs)

    RecordStore._write_record = flaky_write  # type: ignore[method-assign]
    try:
        report = outbox.migrate()
    finally:
        RecordStore._write_record = real_write  # type: ignore[method-assign]

    assert rewritten == ["outbox_old1", "outbox_old2", "outbox_old3"], (
        "the failure must have happened part way through"
    )
    assert report.rolled_back is True
    assert report.to_version == report.from_version == 0
    assert outbox.schema_version() == 0, "the version record must have been rolled back"
    for index in range(1, 4):
        row = store.get(OUTBOX_KIND, f"outbox_old{index}")
        assert row is not None and row["status"] == "sent", "a legacy row was left mutated"

    failure = outbox.migration_failure()
    assert failure is not None
    assert "disk I/O error" in failure["reason"]
    assert failure["attempted_version"] == SCHEMA_VERSION

    # A healthy retry afterwards succeeds.
    retry = outbox.migrate()
    assert retry.rolled_back is False
    assert outbox.schema_version() == SCHEMA_VERSION


def test_migrate_refuses_a_newer_schema(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.put(SCHEMA_KIND, VERSION_RECORD_ID, {"version": SCHEMA_VERSION + 7})
    outbox = Outbox(store)
    report = outbox.migrate()
    assert report.refused is True
    assert report.to_version == SCHEMA_VERSION + 7
    assert report.migrated == 0
    assert [line for line in report.diagnostics if "refusing" in line]


def test_an_unreadable_schema_version_is_not_coerced_to_zero(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.put(SCHEMA_KIND, VERSION_RECORD_ID, {"version": "one"})
    outbox = Outbox(store)
    with pytest.raises(OutboxSchemaError):
        outbox.schema_version()
    with pytest.raises(OutboxSchemaError):
        outbox.migrate()


# ------------------------------------------------------- structural / store surface


def test_outbox_uses_no_api_outside_the_existing_store() -> None:
    """The module must not invent a second writer, a table, or a marker vocabulary."""

    tree = ast.parse(OUTBOX_MODULE.read_text())
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                called.add(func.attr)
            elif isinstance(func, ast.Name):
                called.add(func.id)
    assert "append_event" not in called, "audit events must ride the atomic transitions"
    assert "connection" not in called and "_initialize" not in called
    assert "reserve_idempotent" in called
    assert "mark_idempotent_phase" in called
    assert "finalize_idempotent" in called
    assert "transaction" in called and "_write_record" in called


def test_outbox_adds_no_table_to_the_store(tmp_path: Path) -> None:
    store = _store(tmp_path)
    outbox = Outbox(store)
    sink = Sink(tmp_path / "sink.sqlite3")
    outbox.register_payload("payload-1", {"payload_ref": "payload-1"})
    entry, _ = outbox.enqueue(
        effect_kind=EffectKind.PUBLISH, idempotency_key="key-1", payload_ref="payload-1"
    )
    outbox.deliver(entry.outbox_id, _sink_effector(sink, "key-1"))
    outbox.migrate()
    with closing(sqlite3.connect(tmp_path / "outbox.sqlite3")) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert tables == {"records", "audit_events", "idempotency"}


# ------------------------------------------------------- cross-process crash (M04-04)


CHILD_SOURCE = '''
import os, sqlite3, sys
from contextlib import closing

sys.path.insert(0, {src!r})

from autoresearch.outbox import Outbox
from autoresearch.storage import RecordStore

db_path, sink_path, mode = sys.argv[1], sys.argv[2], sys.argv[3]

with closing(sqlite3.connect(sink_path)) as connection:
    connection.execute({sink_ddl!r})
    connection.commit()


def write_sink(payload):
    with closing(sqlite3.connect(sink_path)) as connection:
        connection.execute(
            "INSERT INTO effects (effect_key, payload_ref, at) VALUES (?, ?, ?)",
            ("key-1", payload["payload_ref"], "2026-09-15T00:00:00+00:00"),
        )
        connection.commit()


store = RecordStore(db_path)
outbox = Outbox(store, max_attempts=3)
outbox.register_payload("payload-1", {{"payload_ref": "payload-1"}})
entry, _ = outbox.enqueue(
    effect_kind="knowledge_write", idempotency_key="key-1", payload_ref="payload-1"
)


def effect(payload):
    write_sink(payload)
    if mode == "crash_mid_effect":
        sys.stdout.flush()
        os._exit(2)
    return {{"sink_rows": 1}}


if mode == "crash_after_effect":
    def boom(*args, **kwargs):
        sys.stdout.flush()
        os._exit(3)

    store.finalize_idempotent = boom

outbox.deliver(entry.outbox_id, effect)
print("no crash happened")
'''


def _run_child(tmp_path: Path, mode: str) -> subprocess.CompletedProcess:
    source = CHILD_SOURCE.format(src=str(SRC_ROOT), sink_ddl=SINK_DDL)
    env = {**os.environ, "PYTHONPATH": str(SRC_ROOT), "PYTHONWARNINGS": "default"}
    return subprocess.run(
        [
            sys.executable,
            "-c",
            source,
            str(tmp_path / "outbox.sqlite3"),
            str(tmp_path / "sink.sqlite3"),
            mode,
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        check=False,
    )


def test_a_crashed_process_that_may_have_run_the_effect_is_not_rerun(tmp_path: Path) -> None:
    """M04-04/I7: real process death, real resume, in a fresh interpreter."""

    child = _run_child(tmp_path, "crash_mid_effect")
    assert child.returncode == 2, child.stderr
    sink = Sink(tmp_path / "sink.sqlite3")
    assert sink.count() == 1, "the crashed child did perform the side effect"

    # A fresh process reopens the durable state.
    restarted = Outbox(_store(tmp_path), max_attempts=3)
    entry = restarted.entries()[0]
    assert entry.status is OutboxStatus.PENDING
    calls: list[str] = []

    def effector(payload: dict) -> dict:  # noqa: ARG001
        calls.append("called")
        return {}

    outcome = restarted.deliver(entry.outbox_id, effector)
    assert outcome.delivered is False
    assert outcome.reason is not None and "unknown outcome" in outcome.reason
    assert calls == [], "a possibly-completed effect must not be run again"
    assert sink.count() == 1


def test_a_crash_after_the_effect_finalizes_without_repeating_it(tmp_path: Path) -> None:
    child = _run_child(tmp_path, "crash_after_effect")
    assert child.returncode == 3, child.stderr
    sink = Sink(tmp_path / "sink.sqlite3")
    assert sink.count() == 1

    restarted = Outbox(_store(tmp_path), max_attempts=3)
    entry = restarted.entries()[0]
    calls: list[str] = []

    def effector(payload: dict) -> dict:  # noqa: ARG001
        calls.append("called")
        return {}

    outcome = restarted.deliver(entry.outbox_id, effector)
    assert outcome.delivered is True
    assert calls == [], "the effect already happened in the crashed process"
    assert sink.count() == 1, "resume must not duplicate the side effect"
    assert restarted.entry(entry.outbox_id).delivered_at is not None
