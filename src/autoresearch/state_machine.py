from __future__ import annotations

from autoresearch.contracts import LifecycleState

_ALLOWED: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.INTAKE: {LifecycleState.SCOPED, LifecycleState.FAILED},
    LifecycleState.SCOPED: {
        LifecycleState.LITERATURE_SEARCHED,
        LifecycleState.WAITING_EVIDENCE,
        LifecycleState.FAILED,
    },
    LifecycleState.LITERATURE_SEARCHED: {
        LifecycleState.LITERATURE_READ,
        LifecycleState.WAITING_EVIDENCE,
        LifecycleState.FAILED,
    },
    LifecycleState.LITERATURE_READ: {
        LifecycleState.INNOVATION_REVIEWED,
        LifecycleState.WAITING_EVIDENCE,
        LifecycleState.REJECTED,
        LifecycleState.FAILED,
    },
    LifecycleState.INNOVATION_REVIEWED: {
        LifecycleState.EXECUTION_PLANNED,
        LifecycleState.WAITING_EVIDENCE,
        LifecycleState.REJECTED,
    },
    LifecycleState.EXECUTION_PLANNED: {
        LifecycleState.DRAFT_WRITTEN,
        LifecycleState.WAITING_EVIDENCE,
        LifecycleState.FAILED,
    },
    LifecycleState.DRAFT_WRITTEN: {
        LifecycleState.DRAFT_REVIEWED,
        LifecycleState.WAITING_EVIDENCE,
        LifecycleState.REJECTED,
        LifecycleState.FAILED,
    },
    LifecycleState.DRAFT_REVIEWED: {
        LifecycleState.RELEASE_PENDING,
    },
    LifecycleState.RELEASE_PENDING: {
        LifecycleState.WAITING_HUMAN,
        LifecycleState.WAITING_EVIDENCE,
        LifecycleState.RELEASED,
        LifecycleState.REJECTED,
    },
    LifecycleState.WAITING_HUMAN: {
        LifecycleState.RELEASED,
        LifecycleState.REJECTED,
    },
    LifecycleState.WAITING_EVIDENCE: {
        LifecycleState.SCOPED,
        LifecycleState.LITERATURE_SEARCHED,
        LifecycleState.LITERATURE_READ,
        LifecycleState.INNOVATION_REVIEWED,
        LifecycleState.EXECUTION_PLANNED,
    },
    LifecycleState.RELEASED: set(),
    LifecycleState.REJECTED: set(),
    LifecycleState.FAILED: set(),
}


class StateMachine:
    def can_transition(self, current: LifecycleState, target: LifecycleState) -> bool:
        if current == target:
            return True
        return target in _ALLOWED.get(current, set())

    def transition(self, current: LifecycleState, target: LifecycleState) -> LifecycleState:
        if not self.can_transition(current, target):
            raise ValueError(f"invalid lifecycle transition: {current} -> {target}")
        return target
