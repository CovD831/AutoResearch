from __future__ import annotations

from autoresearch.contracts import (
    EvidenceGrade,
    EvolutionProposal,
    ExperienceRecord,
    KnowledgePartition,
    WikiPage,
)
from autoresearch.knowledge import KnowledgeService
from autoresearch.storage import RecordStore


class ExperienceService:
    def __init__(self, store: RecordStore, knowledge: KnowledgeService):
        self.store = store
        self.knowledge = knowledge

    def record(self, experience: ExperienceRecord) -> ExperienceRecord:
        self.store.put(
            "experience",
            experience.experience_id,
            experience,
            project_id=experience.project_id,
            partition=KnowledgePartition.EXPERIENCES.value,
        )
        self.knowledge.add_page(
            WikiPage(
                page_id=experience.experience_id,
                project_id=experience.project_id,
                partition=KnowledgePartition.EXPERIENCES,
                title=experience.problem,
                body=f"Technique: {experience.technique}\nOutcome: {experience.outcome}",
                tags=["experience", experience.grade.value],
                evidence_ids=experience.evidence_ids,
                level=1 if not experience.promoted else 2,
            )
        )
        return experience

    def promote(
        self,
        experience_id: str,
        *,
        reviewer_approved: bool,
        human_approved: bool,
    ) -> ExperienceRecord:
        raw = self.store.get("experience", experience_id)
        if raw is None:
            raise KeyError(experience_id)
        experience = ExperienceRecord.model_validate(raw)
        if (
            experience.recurrence_count < 2
            or experience.grade not in {EvidenceGrade.E2, EvidenceGrade.E3, EvidenceGrade.H3}
            or not reviewer_approved
            or not human_approved
        ):
            raise PermissionError("experience promotion requirements are not satisfied")
        promoted = experience.model_copy(update={"promoted": True})
        return self.record(promoted)


class EvolutionService:
    """Self-evolution produces auditable proposals; it never rewrites policy or code itself."""

    def __init__(self, store: RecordStore):
        self.store = store

    def propose(self, proposal: EvolutionProposal) -> EvolutionProposal:
        self.store.put(
            "evolution_proposal",
            proposal.proposal_id,
            proposal,
            project_id=proposal.project_id,
            partition="governance",
        )
        self.store.append_event(
            "evolution.proposed",
            proposal,
            project_id=proposal.project_id,
            actor="evolution_service",
        )
        return proposal

    def review(
        self,
        proposal_id: str,
        *,
        reviewer_approved: bool,
        human_approved: bool,
        note: str,
    ) -> EvolutionProposal:
        raw = self.store.get("evolution_proposal", proposal_id)
        if raw is None:
            raise KeyError(proposal_id)
        proposal = EvolutionProposal.model_validate(raw)
        if reviewer_approved and human_approved:
            status = "approved_for_manual_application"
        elif reviewer_approved:
            status = "waiting_human_approval"
        else:
            status = "rejected"
        reviewed = proposal.model_copy(update={"status": status})
        self.store.put(
            "evolution_proposal",
            reviewed.proposal_id,
            reviewed,
            project_id=reviewed.project_id,
            partition="governance",
        )
        self.store.append_event(
            "evolution.reviewed",
            {"proposal_id": proposal_id, "status": status, "note": note},
            project_id=reviewed.project_id,
            actor="reviewer",
        )
        return reviewed
