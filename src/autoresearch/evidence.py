from __future__ import annotations

from autoresearch.contracts import EvidenceItem
from autoresearch.storage import RecordStore


class EvidenceService:
    def __init__(self, store: RecordStore):
        self.store = store

    def add(self, item: EvidenceItem, *, actor: str = "system") -> EvidenceItem:
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

    def get(self, evidence_id: str) -> EvidenceItem | None:
        raw = self.store.get("evidence", evidence_id)
        if raw is None:
            return None
        status = self.store.get("evidence_status", evidence_id)
        if status and not status.get("valid", True):
            raw["valid"] = False
        return EvidenceItem.model_validate(raw)

    def resolve(self, evidence_ids: list[str]) -> list[EvidenceItem]:
        resolved = []
        for evidence_id in dict.fromkeys(evidence_ids):
            item = self.get(evidence_id)
            if item is not None:
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
