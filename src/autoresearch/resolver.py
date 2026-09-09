from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from autoresearch.audit_contracts import AuditCitation
from autoresearch.contracts import utc_now
from autoresearch.storage import RecordStore


class ResolverStatus(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class ResolverRecord(BaseModel):
    resolver_key: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)
    doi: str | None = None
    arxiv_id: str | None = None
    source_uri: str | None = None
    retracted: bool = False
    corrected: bool = False
    version_state: str = "current"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolverResponse(BaseModel):
    status: ResolverStatus
    snapshot_version: str
    record: ResolverRecord | None = None
    diagnostics: list[str] = Field(default_factory=list, max_length=20)


class ResolverSnapshot(BaseModel):
    """Immutable, versioned resolver input that can be replayed locally."""

    snapshot_schema: str = "resolver-snapshot/v1"
    snapshot_version: str = Field(min_length=1, max_length=100)
    records: list[ResolverRecord] = Field(default_factory=list, max_length=100_000)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime = Field(default_factory=utc_now)

    @classmethod
    def from_records(
        cls,
        records: list[ResolverRecord],
        *,
        snapshot_version: str,
    ) -> ResolverSnapshot:
        ordered = sorted(records, key=lambda record: record.resolver_key)
        payload = {
            "snapshot_version": snapshot_version,
            "records": [record.model_dump(mode="json") for record in ordered],
        }
        checksum = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return cls(snapshot_version=snapshot_version, records=ordered, checksum=checksum)

    def verify(self) -> ResolverSnapshot:
        expected = ResolverSnapshot.from_records(
            self.records,
            snapshot_version=self.snapshot_version,
        ).checksum
        if expected != self.checksum:
            raise ValueError(
                f"resolver snapshot checksum mismatch: {self.snapshot_version}"
            )
        return self


class ResolverSnapshotConflictError(ValueError):
    """A snapshot version is immutable and cannot be overwritten with new content."""


class ResolverSnapshotRepository:
    """Persistence boundary for versioned resolver snapshots in the canonical store."""

    kind = "resolver_snapshot"

    def __init__(self, store: RecordStore):
        self.store = store

    def save(self, snapshot: ResolverSnapshot) -> ResolverSnapshot:
        snapshot.verify()
        now = utc_now().isoformat()
        payload = snapshot.model_dump_json()
        # INSERT .. DO NOTHING makes the version immutable even when two
        # processes try to publish the same snapshot at the same time.
        with self.store.connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO records
                    (kind, record_id, project_id, partition_name, payload_json,
                     created_at, updated_at)
                VALUES (?, ?, NULL, ?, ?, ?, ?)
                ON CONFLICT(kind, record_id) DO NOTHING
                """,
                (
                    self.kind,
                    snapshot.snapshot_version,
                    "resolver",
                    payload,
                    now,
                    now,
                ),
            )
            if cursor.rowcount == 1:
                return snapshot
            row = connection.execute(
                "SELECT payload_json FROM records WHERE kind=? AND record_id=?",
                (self.kind, snapshot.snapshot_version),
            ).fetchone()
        if row is None:
            raise RuntimeError("resolver snapshot disappeared after immutable insert")
        existing = ResolverSnapshot.model_validate(json.loads(row["payload_json"])).verify()
        if existing.checksum != snapshot.checksum:
            raise ResolverSnapshotConflictError(
                f"resolver snapshot version already contains different content: "
                f"{snapshot.snapshot_version}"
            )
        return existing

    def load(self, snapshot_version: str) -> ResolverSnapshot | None:
        raw = self.store.get(self.kind, snapshot_version)
        if raw is None:
            return None
        return ResolverSnapshot.model_validate(raw).verify()


class ResolverAdapter(Protocol):
    name: str
    version: str
    snapshot_version: str

    def resolve(self, citation: AuditCitation) -> ResolverResponse: ...


def citation_key(citation: AuditCitation) -> str:
    if citation.doi:
        return f"doi:{citation.doi.strip().lower()}"
    if citation.arxiv_id:
        return f"arxiv:{citation.arxiv_id.strip().lower()}"
    normalized = re.sub(r"\W+", "", citation.title.lower())
    return f"title:{normalized}"


class SnapshotResolverAdapter:
    """Offline resolver backed by a versioned local snapshot."""

    name = "snapshot_resolver"
    version = "1"

    def __init__(
        self,
        records: list[ResolverRecord] | None = None,
        *,
        snapshot_version: str = "snapshot-1",
        available: bool = True,
        store: RecordStore | None = None,
    ):
        self.snapshot_version = snapshot_version
        self.available = available
        self.snapshot: ResolverSnapshot | None = None
        if store is not None and records is None:
            self.snapshot = ResolverSnapshotRepository(store).load(snapshot_version)
            if self.snapshot is not None:
                records = self.snapshot.records
            else:
                self.available = False
        elif records is not None:
            self.snapshot = ResolverSnapshot.from_records(
                records,
                snapshot_version=snapshot_version,
            )
            if store is not None:
                self.snapshot = ResolverSnapshotRepository(store).save(self.snapshot)
                records = self.snapshot.records
        self._records = {record.resolver_key: record for record in records or []}

    @classmethod
    def from_store(
        cls,
        store: RecordStore,
        *,
        snapshot_version: str,
        available: bool = True,
    ) -> SnapshotResolverAdapter:
        return cls(
            None,
            snapshot_version=snapshot_version,
            available=available,
            store=store,
        )

    def resolve(self, citation: AuditCitation) -> ResolverResponse:
        if not self.available:
            return ResolverResponse(
                status=ResolverStatus.UNAVAILABLE,
                snapshot_version=self.snapshot_version,
                diagnostics=["resolver unavailable; verdict must remain unknown"],
            )
        record = self._records.get(citation_key(citation))
        if record is None:
            return ResolverResponse(
                status=ResolverStatus.NOT_FOUND,
                snapshot_version=self.snapshot_version,
                diagnostics=["citation key is absent from resolver snapshot"],
            )
        return ResolverResponse(
            status=ResolverStatus.FOUND,
            snapshot_version=self.snapshot_version,
            record=record,
        )


__all__ = [
    "ResolverAdapter",
    "ResolverRecord",
    "ResolverResponse",
    "ResolverSnapshot",
    "ResolverSnapshotConflictError",
    "ResolverSnapshotRepository",
    "ResolverStatus",
    "SnapshotResolverAdapter",
    "citation_key",
]
