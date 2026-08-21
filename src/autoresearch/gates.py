from __future__ import annotations

from dataclasses import dataclass

from autoresearch.contracts import (
    EvidenceGrade,
    GateDecision,
    GateRequest,
    GateStatus,
    RiskLevel,
)
from autoresearch.evidence import EvidenceService
from autoresearch.storage import RecordStore


@dataclass(frozen=True)
class GateThreshold:
    score: int
    independent_sources: int
    closed_loop: bool = False
    human_approval: bool = False


GRADE_WEIGHTS = {
    EvidenceGrade.E0: 5,
    EvidenceGrade.E1: 15,
    EvidenceGrade.E2: 30,
    EvidenceGrade.E3: 45,
    EvidenceGrade.H3: 50,
}

THRESHOLDS = {
    RiskLevel.L0: GateThreshold(0, 0),
    RiskLevel.L1: GateThreshold(15, 1),
    RiskLevel.L2: GateThreshold(30, 1),
    RiskLevel.L3: GateThreshold(75, 2, closed_loop=True),
    RiskLevel.L4: GateThreshold(85, 2, closed_loop=True, human_approval=True),
}


class GateService:
    """Deterministic gate. Model output is never accepted as a policy override."""

    def __init__(self, evidence: EvidenceService, store: RecordStore):
        self.evidence = evidence
        self.store = store

    def evaluate(self, request: GateRequest) -> GateDecision:
        threshold = THRESHOLDS[request.risk_level]
        items = [
            item
            for item in self.evidence.resolve(request.evidence_ids)
            if item.valid and item.project_id == request.project_id
        ]

        strongest_by_source: dict[str, tuple[int, str]] = {}
        for item in items:
            weight = GRADE_WEIGHTS[item.grade]
            previous = strongest_by_source.get(item.independent_source)
            if previous is None or weight > previous[0]:
                strongest_by_source[item.independent_source] = (weight, item.evidence_id)

        score = min(100, sum(value[0] for value in strongest_by_source.values()))
        qualifying_ids = [value[1] for value in strongest_by_source.values()]
        sources = len(strongest_by_source)
        reasons: list[str] = []

        if request.explicitly_rejected:
            status = GateStatus.DENY
            reasons.append("reviewer or human explicitly rejected the operation")
        elif request.risk_level == RiskLevel.L4 and not request.human_approval:
            status = GateStatus.INTERRUPT
            reasons.append("L4 operation requires explicit human approval")
        else:
            if score < threshold.score:
                reasons.append(f"evidence score {score} is below required {threshold.score}")
            if sources < threshold.independent_sources:
                reasons.append(
                    f"independent sources {sources} are below required "
                    f"{threshold.independent_sources}"
                )
            if threshold.closed_loop and not request.work_closed_loop:
                reasons.append("required work and result lineage are not closed loop")
            status = GateStatus.PASS if not reasons else GateStatus.REVISE

        if not reasons:
            reasons.append("all deterministic evidence and closure requirements passed")

        decision = GateDecision(
            project_id=request.project_id,
            operation=request.operation,
            status=status,
            risk_level=request.risk_level,
            score=score,
            independent_sources=sources,
            reasons=reasons,
            qualifying_evidence_ids=qualifying_ids,
        )
        self.store.put(
            "gate_decision",
            decision.decision_id,
            decision,
            project_id=request.project_id,
            partition="governance",
        )
        self.store.append_event(
            "gate.evaluated",
            decision,
            project_id=request.project_id,
            actor="gate_service",
        )
        return decision
