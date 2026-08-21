from __future__ import annotations

from autoresearch.contracts import AgentId, HandoffEnvelope
from autoresearch.storage import RecordStore


class HandoffService:
    def __init__(self, store: RecordStore):
        self.store = store

    def issue(self, envelope: HandoffEnvelope) -> HandoffEnvelope:
        self.store.put(
            "handoff",
            envelope.handoff_id,
            envelope,
            project_id=envelope.project_id,
            partition="handoffs",
        )
        self.store.append_event(
            "handoff.issued",
            envelope,
            project_id=envelope.project_id,
            actor=envelope.from_agent.value,
        )
        return envelope

    def accept(
        self,
        payload: dict,
        *,
        expected_receiver: AgentId,
        project_id: str,
        run_id: str,
    ) -> HandoffEnvelope:
        envelope = HandoffEnvelope.model_validate(payload)
        if envelope.to_agent != expected_receiver:
            raise ValueError(f"handoff addressed to {envelope.to_agent}, not {expected_receiver}")
        if envelope.project_id != project_id or envelope.run_id != run_id:
            raise ValueError("handoff project/run identity mismatch")
        self.store.append_event(
            "handoff.accepted",
            {"handoff_id": envelope.handoff_id, "receiver": expected_receiver.value},
            project_id=project_id,
            actor=expected_receiver.value,
        )
        return envelope
