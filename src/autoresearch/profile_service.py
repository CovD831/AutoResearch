from __future__ import annotations

from autoresearch.contracts import KnowledgePartition, UserProfileItem, WikiPage
from autoresearch.knowledge import KnowledgeService
from autoresearch.storage import RecordStore


class UserProfileService:
    def __init__(self, store: RecordStore, knowledge: KnowledgeService):
        self.store = store
        self.knowledge = knowledge

    def record(self, item: UserProfileItem) -> UserProfileItem:
        if not item.confirmed_by_user and item.confidence > 0.6:
            item = item.model_copy(update={"confidence": 0.6})
        self.store.put(
            "profile_item",
            item.profile_item_id,
            item,
            partition=KnowledgePartition.PROFILES.value,
        )
        self.knowledge.add_page(
            WikiPage(
                page_id=item.profile_item_id,
                partition=KnowledgePartition.PROFILES,
                title=f"{item.user_id}: {item.key}",
                body=item.value,
                tags=["user-profile", "confirmed" if item.confirmed_by_user else "inferred"],
                evidence_ids=item.evidence_ids,
                level=2 if item.confirmed_by_user else 1,
            )
        )
        return item

    def list(self, user_id: str) -> list[UserProfileItem]:
        return [
            UserProfileItem.model_validate(raw)
            for raw in self.store.list("profile_item", partition=KnowledgePartition.PROFILES.value)
            if raw["user_id"] == user_id
        ]
