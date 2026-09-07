from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from autoresearch.contracts import new_id, utc_now


class RecordStore:
    """SQLite repository with append-only audit events and generic typed records."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    project_id TEXT,
                    partition_name TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (kind, record_id)
                );
                CREATE INDEX IF NOT EXISTS idx_records_project
                    ON records(project_id, kind);
                CREATE INDEX IF NOT EXISTS idx_records_partition
                    ON records(partition_name, kind);
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_project
                    ON audit_events(project_id, created_at);
                CREATE TABLE IF NOT EXISTS idempotency (
                    scope TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (scope, idempotency_key)
                );
                """
            )

    @staticmethod
    def _json(value: BaseModel | dict[str, Any]) -> str:
        if isinstance(value, BaseModel):
            return value.model_dump_json()
        return json.dumps(value, ensure_ascii=False, default=str)

    def put(
        self,
        kind: str,
        record_id: str,
        value: BaseModel | dict[str, Any],
        *,
        project_id: str | None = None,
        partition: str | None = None,
    ) -> None:
        now = utc_now().isoformat()
        payload = self._json(value)
        with self._lock, self.connection() as connection:
            connection.execute(
                """
                INSERT INTO records
                    (kind, record_id, project_id, partition_name, payload_json,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(kind, record_id) DO UPDATE SET
                    project_id=excluded.project_id,
                    partition_name=excluded.partition_name,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (kind, record_id, project_id, partition, payload, now, now),
            )

    def get(self, kind: str, record_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM records WHERE kind=? AND record_id=?",
                (kind, record_id),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list(
        self,
        kind: str,
        *,
        project_id: str | None = None,
        partition: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["kind=?"]
        params: list[Any] = [kind]
        if project_id is not None:
            clauses.append("project_id=?")
            params.append(project_id)
        if partition is not None:
            clauses.append("partition_name=?")
            params.append(partition)
        query = "SELECT payload_json FROM records WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at, record_id"
        with self.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def search(
        self,
        *,
        partition: str,
        query: str,
        kinds: tuple[str, ...] = ("wiki_page",),
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in kinds)
        sql = (
            "SELECT payload_json FROM records WHERE partition_name=? "
            f"AND kind IN ({placeholders}) AND lower(payload_json) LIKE ? "
            "ORDER BY updated_at DESC LIMIT ?"
        )
        params: list[Any] = [partition, *kinds, f"%{query.lower()}%", limit]
        with self.connection() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def append_event(
        self,
        event_type: str,
        payload: BaseModel | dict[str, Any],
        *,
        project_id: str | None = None,
        actor: str = "system",
    ) -> str:
        event_id = new_id("event")
        with self._lock, self.connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_events
                    (event_id, project_id, event_type, actor, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    project_id,
                    event_type,
                    actor,
                    self._json(payload),
                    utc_now().isoformat(),
                ),
            )
        return event_id

    def events(self, project_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT event_id, event_type, actor, payload_json, created_at
                FROM audit_events WHERE project_id=? ORDER BY created_at, event_id
                """,
                (project_id,),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "actor": row["actor"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def remember_idempotent(self, scope: str, key: str, result: dict[str, Any]) -> bool:
        with self._lock, self.connection() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO idempotency
                    (scope, idempotency_key, result_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (scope, key, self._json(result), utc_now().isoformat()),
            )
        return cursor.rowcount == 1

    def get_idempotent(self, scope: str, key: str) -> dict[str, Any] | None:
        """Return the durable invocation record, including pending state."""

        with self.connection() as connection:
            row = connection.execute(
                "SELECT result_json FROM idempotency WHERE scope=? AND idempotency_key=?",
                (scope, key),
            ).fetchone()
        return json.loads(row["result_json"]) if row else None

    def reserve_idempotent(self, scope: str, key: str, request: dict[str, Any]) -> bool:
        """Atomically reserve an invocation before any connector side effect."""

        now = utc_now().isoformat()
        record = {
            "state": "pending",
            "phase": "reserved",
            "request": request,
            "request_fingerprint": request.get("request_fingerprint"),
            "created_at": now,
            "updated_at": now,
        }
        with self._lock, self.connection() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO idempotency
                    (scope, idempotency_key, result_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (scope, key, self._json(record), now),
            )
        return cursor.rowcount == 1

    def mark_idempotent_phase(
        self,
        scope: str,
        key: str,
        phase: str,
        *,
        staged_result: dict[str, Any] | None = None,
    ) -> None:
        """Record progress within a pending invocation before finalization."""

        transitions = {
            "reserved": {"service_started"},
            "service_started": {"service_returned"},
            "service_returned": set(),
        }
        with self._lock, self.connection() as connection:
            row = connection.execute(
                "SELECT result_json FROM idempotency WHERE scope=? AND idempotency_key=?",
                (scope, key),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown idempotency record: {scope}:{key}")
            record = json.loads(row["result_json"])
            if record.get("state") != "pending":
                raise RuntimeError("idempotency record is already finalized")
            current = record.get("phase", "reserved")
            if phase not in transitions.get(current, set()):
                raise RuntimeError(f"invalid invocation phase transition: {current} -> {phase}")
            record["phase"] = phase
            if staged_result is not None:
                record["staged_result"] = staged_result
            record["updated_at"] = utc_now().isoformat()
            connection.execute(
                """
                UPDATE idempotency SET result_json=?, created_at=created_at
                WHERE scope=? AND idempotency_key=?
                """,
                (self._json(record), scope, key),
            )

    def finalize_idempotent(self, scope: str, key: str, result: dict[str, Any]) -> None:
        """Finalize a pending invocation without changing its identity."""

        with self._lock, self.connection() as connection:
            row = connection.execute(
                "SELECT result_json FROM idempotency WHERE scope=? AND idempotency_key=?",
                (scope, key),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown idempotency record: {scope}:{key}")
            existing = json.loads(row["result_json"])
            if existing.get("state") != "pending":
                raise RuntimeError("idempotency record is already finalized")
            now = utc_now().isoformat()
            record = {
                **existing,
                "state": "finalized",
                "phase": "finalized",
                "result": result,
                "updated_at": now,
            }
            connection.execute(
                """
                UPDATE idempotency SET result_json=?, created_at=created_at
                WHERE scope=? AND idempotency_key=?
                """,
                (self._json(record), scope, key),
            )

    def list_idempotent(self, scope: str | None = None) -> list[dict[str, Any]]:
        """List invocation records for parity and diagnostics."""

        query = "SELECT scope, idempotency_key, result_json FROM idempotency"
        params: tuple[Any, ...] = ()
        if scope is not None:
            query += " WHERE scope=?"
            params = (scope,)
        query += " ORDER BY created_at, scope, idempotency_key"
        with self.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            {
                "scope": row["scope"],
                "idempotency_key": row["idempotency_key"],
                "record": json.loads(row["result_json"]),
            }
            for row in rows
        ]
