from __future__ import annotations

import re
from datetime import UTC, datetime

from autoresearch.contracts import EvidenceItem
from autoresearch.pipeline_contracts import (
    EvidenceAdmissionResult,
    EvidenceAdmissionStatus,
    EvidenceCandidate,
)
from autoresearch.storage import RecordStore


class EvidenceService:
    def __init__(self, store: RecordStore):
        self.store = store

    def add(self, item: EvidenceItem, *, actor: str = "system") -> EvidenceItem:
        if not item.locator or not item.locator.strip():
            raise ValueError("evidence locator is required")
        existing = self.store.get("evidence", item.evidence_id)
        if existing is not None and existing != item.model_dump(mode="json"):
            raise ValueError(f"evidence is immutable: {item.evidence_id}")
        if existing is None:
            self.store.put(
                "evidence",
                item.evidence_id,
                item,
                project_id=item.project_id,
                partition="evidence",
            )
            self.store.append_event("evidence.added", item, project_id=item.project_id, actor=actor)
        return item

    @staticmethod
    def _normalize(value: str | None) -> str:
        return re.sub(r"\s+", " ", value or "").strip().casefold()

    @classmethod
    def _duplicate_key(
        cls,
        item: EvidenceItem | EvidenceCandidate,
    ) -> tuple[str, str, str, str, str, str]:
        return (
            cls._normalize(item.independent_source),
            cls._normalize(item.source_uri),
            cls._normalize(item.source_id),
            cls._normalize(item.locator),
            cls._normalize(item.checksum),
            cls._normalize(item.claim),
        )

    @classmethod
    def _source_key(cls, item: EvidenceItem | EvidenceCandidate) -> tuple[str, str, str]:
        return (
            cls._normalize(item.independent_source),
            cls._normalize(item.source_uri or item.source_id),
            cls._normalize(item.locator),
        )

    @staticmethod
    def _expiry_reason(item: EvidenceItem) -> str | None:
        expires_at = item.metadata.get("expires_at")
        if expires_at is None:
            return None
        if not isinstance(expires_at, str) or not expires_at.strip():
            return "evidence expiry metadata is malformed"
        try:
            parsed = datetime.fromisoformat(expires_at.strip().replace("Z", "+00:00"))
        except ValueError:
            return "evidence expiry metadata is malformed"
        if parsed.tzinfo is None:
            return "evidence expiry metadata must include a timezone"
        if parsed <= datetime.now(UTC):
            return f"evidence expired at {expires_at}"
        return None

    def validity_reason(self, evidence_id: str) -> str | None:
        raw = self.store.get("evidence", evidence_id)
        if raw is None:
            return None
        item = EvidenceItem.model_validate(raw)
        status = self.store.get("evidence_status", evidence_id)
        if not item.valid:
            return "evidence is marked invalid"
        if status and not status.get("valid", True):
            return str(status.get("reason") or "evidence was invalidated")
        return self._expiry_reason(item)

    def admit_candidate(
        self,
        candidate: EvidenceCandidate,
        *,
        actor: str = "system",
    ) -> EvidenceAdmissionResult:
        if not candidate.locator or not candidate.locator.strip():
            result = EvidenceAdmissionResult(
                project_id=candidate.project_id,
                candidate_id=candidate.candidate_id,
                status=EvidenceAdmissionStatus.BLOCKED,
                reasons=["candidate locator is required"],
            )
            self.store.append_event(
                "evidence.candidate_blocked",
                result,
                project_id=candidate.project_id,
                actor=actor,
            )
            return result
        existing_items = self.list(candidate.project_id)
        candidate_duplicate_key = self._duplicate_key(candidate)
        candidate_source_key = self._source_key(candidate)

        for item in existing_items:
            if self._duplicate_key(item) == candidate_duplicate_key:
                result = EvidenceAdmissionResult(
                    project_id=candidate.project_id,
                    candidate_id=candidate.candidate_id,
                    status=EvidenceAdmissionStatus.DUPLICATE,
                    existing_evidence_id=item.evidence_id,
                    reasons=["an equivalent evidence item already exists"],
                )
                self.store.append_event(
                    "evidence.candidate_duplicate",
                    result,
                    project_id=candidate.project_id,
                    actor=actor,
                )
                return result
            if (
                self._source_key(item) == candidate_source_key
                and self._duplicate_key(item) != candidate_duplicate_key
            ):
                result = EvidenceAdmissionResult(
                    project_id=candidate.project_id,
                    candidate_id=candidate.candidate_id,
                    status=EvidenceAdmissionStatus.CONFLICT,
                    existing_evidence_id=item.evidence_id,
                    reasons=[
                        "the same source locator already exists with different content",
                    ],
                )
                self.store.append_event(
                    "evidence.candidate_conflict",
                    result,
                    project_id=candidate.project_id,
                    actor=actor,
                )
                return result

        admitted = self.add(
            EvidenceItem(
                project_id=candidate.project_id,
                evidence_type=candidate.evidence_type,
                grade=candidate.grade,
                title=candidate.title,
                claim=candidate.claim,
                source_uri=candidate.source_uri,
                source_id=candidate.source_id,
                locator=candidate.locator,
                checksum=candidate.checksum,
                independent_source=candidate.independent_source,
                metadata={
                    **candidate.metadata,
                    "candidate_id": candidate.candidate_id,
                },
            ),
            actor=actor,
        )
        result = EvidenceAdmissionResult(
            project_id=candidate.project_id,
            candidate_id=candidate.candidate_id,
            status=EvidenceAdmissionStatus.ACCEPTED,
            evidence_id=admitted.evidence_id,
        )
        self.store.append_event(
            "evidence.candidate_accepted",
            result,
            project_id=candidate.project_id,
            actor=actor,
        )
        return result

    def get(self, evidence_id: str) -> EvidenceItem | None:
        raw = self.store.get("evidence", evidence_id)
        if raw is None:
            return None
        if self.validity_reason(evidence_id) is not None:
            raw["valid"] = False
        return EvidenceItem.model_validate(raw)

    def resolve(
        self,
        evidence_ids: list[str],
        *,
        valid_only: bool = False,
    ) -> list[EvidenceItem]:
        resolved = []
        for evidence_id in dict.fromkeys(evidence_ids):
            item = self.get(evidence_id)
            if item is not None and (not valid_only or item.valid):
                resolved.append(item)
        return resolved

    def list(self, project_id: str, *, valid_only: bool = False) -> list[EvidenceItem]:
        items = [
            item
            for raw in self.store.list("evidence", project_id=project_id)
            if (item := self.get(raw["evidence_id"])) is not None
        ]
        if valid_only:
            return [item for item in items if item.valid]
        return items

    def invalidate(self, evidence_id: str, reason: str, *, actor: str) -> None:
        item = self.get(evidence_id)
        if item is None:
            raise KeyError(evidence_id)
        status = {"valid": False, "reason": reason, "actor": actor}
        self.store.put(
            "evidence_status",
            evidence_id,
            status,
            project_id=item.project_id,
            partition="evidence",
        )
        self.store.append_event(
            "evidence.invalidated",
            {"evidence_id": evidence_id, **status},
            project_id=item.project_id,
            actor=actor,
        )
