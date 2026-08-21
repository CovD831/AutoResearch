from __future__ import annotations

from autoresearch.contracts import WorkPackage, WorkPackageUpdate
from autoresearch.evidence import EvidenceService
from autoresearch.storage import RecordStore


class ExecutionService:
    def __init__(self, store: RecordStore, evidence: EvidenceService):
        self.store = store
        self.evidence = evidence

    def list_work_packages(self, project_id: str) -> list[WorkPackage]:
        return [
            WorkPackage.model_validate(raw)
            for raw in self.store.list("work_package", project_id=project_id)
        ]

    def update_work_package(
        self,
        work_package_id: str,
        update: WorkPackageUpdate,
    ) -> WorkPackage:
        raw = self.store.get("work_package", work_package_id)
        if raw is None:
            raise KeyError(work_package_id)
        package = WorkPackage.model_validate(raw)
        valid_evidence = [
            item.evidence_id
            for item in self.evidence.resolve(update.evidence_ids)
            if item.valid and item.project_id == package.project_id
        ]
        if update.status == "completed" and not valid_evidence:
            raise PermissionError(
                "a completed work package requires at least one valid project evidence item"
            )
        revised = package.model_copy(
            update={
                "status": update.status,
                "evidence_ids": list(dict.fromkeys([*package.evidence_ids, *valid_evidence])),
                "notes": [*package.notes, *([update.note] if update.note else [])],
            }
        )
        self.store.put(
            "work_package",
            revised.work_package_id,
            revised,
            project_id=revised.project_id,
            partition="projects",
        )
        self.store.append_event(
            "work_package.updated",
            {
                "work_package_id": revised.work_package_id,
                "status": revised.status,
                "evidence_ids": revised.evidence_ids,
            },
            project_id=revised.project_id,
            actor="execution_service",
        )
        return revised
