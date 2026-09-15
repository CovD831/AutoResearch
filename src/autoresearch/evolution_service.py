from __future__ import annotations

from pydantic import BaseModel, Field

from autoresearch.contracts import (
    EvidenceGrade,
    EvolutionProposal,
    ExperienceRecord,
    ExperienceStage,
    KnowledgePartition,
    WikiPage,
)
from autoresearch.knowledge import KnowledgeService
from autoresearch.storage import RecordStore

# ---------------------------------------------------------------------------
# Stage-advancement evidence (R-006 L2 / §11.5 / §11.11)
# ---------------------------------------------------------------------------
# The sandbox-reproduction and cross-project records are P3 deliverables; here
# they are modelled explicitly so advance_stage() can mechanically check the
# gates today. P3 will populate the same shape from real reproduction logs.


class ReproductionRecord(BaseModel):
    """A single sandbox reproduction attempt backing a stage advancement."""

    project_id: str
    passed: bool


class StageEvidence(BaseModel):
    """Evidence bundle carried into ``ExperienceService.advance_stage``.

    ``reproductions`` backs the X1->X2 (sandbox passed) and X2->X3 (cross-project
    passed) gates. It is mechanically checkable now; P3 swaps the source from
    fixtures to real reproduction logs (see §11.8 ``【P3 后生效】``).
    """

    reproductions: list[ReproductionRecord] = Field(default_factory=list)


# advance_stage owns X0->X1->X2->X3; X3->X4 is promote()'s transition.
_NEXT_STAGE: dict[ExperienceStage, ExperienceStage] = {
    ExperienceStage.X0_RAW: ExperienceStage.X1_ATTRIBUTED,
    ExperienceStage.X1_ATTRIBUTED: ExperienceStage.X2_REPRODUCED,
    ExperienceStage.X2_REPRODUCED: ExperienceStage.X3_CROSS_PROJECT,
}


def _sandbox_passed(evidence: StageEvidence) -> bool:
    return any(r.passed for r in evidence.reproductions)


def _cross_project_passed(
    experience: ExperienceRecord, evidence: StageEvidence
) -> bool:
    return any(
        r.passed and r.project_id != experience.project_id
        for r in evidence.reproductions
    )


def _check_stage_gate(
    experience: ExperienceRecord,
    evidence: StageEvidence,
    target: ExperienceStage,
) -> None:
    """Verify the §11.5 gate for the current->target transition.

    Raises PermissionError when the gate is not satisfied, matching the failure
    semantics of the existing promote().
    """
    # Bidirectional boundaries are required from X1 onward (carries forward).
    if not (experience.applicable_when and experience.not_applicable_when):
        raise PermissionError(
            "X1+ requires non-empty applicable_when and not_applicable_when"
        )

    if target == ExperienceStage.X1_ATTRIBUTED:
        return

    if not experience.regression_set_id:
        raise PermissionError("X2+ requires a non-empty regression_set_id")
    if not _sandbox_passed(evidence):
        raise PermissionError(
            "X1->X2 requires a passing sandbox reproduction record"
        )

    if target == ExperienceStage.X2_REPRODUCED:
        return

    # X2->X3: cross-project evidence + counterexample_ids (on top of the above).
    if not _cross_project_passed(experience, evidence):
        raise PermissionError(
            "X2->X3 requires a passing cross-project (different project_id) "
            "reproduction record"
        )
    if not experience.counterexample_ids:
        raise PermissionError("X3+ requires non-empty counterexample_ids")


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
        # C1 / §11.9: wiki pages are append-only, so the revision must be
        # DERIVED from the current head -- never passed as a constant. Passing
        # the WikiPage default (revision=1) would make the SECOND record() of the
        # same experience_id raise ValueError against the append-only writer,
        # which is the normal path for experience_sink (dedup + recurrence
        # accumulation re-records the same experience).
        current = self.knowledge.get_page(experience.experience_id)
        next_revision = (current.revision if current is not None else 0) + 1
        self.knowledge.add_page(
            WikiPage(
                page_id=experience.experience_id,
                revision=next_revision,
                # C1: the new revision supersedes the one it replaces.
                supersedes=current.revision_id if current is not None else None,
                author="evolution_service",
                project_id=experience.project_id,
                partition=KnowledgePartition.EXPERIENCES,
                title=experience.problem,
                body=f"Technique: {experience.technique}\nOutcome: {experience.outcome}",
                tags=["experience", experience.grade.value, *experience.tags],
                evidence_ids=experience.evidence_ids,
                level=1 if not experience.promoted else 2,
            )
        )
        return experience

    def advance_stage(
        self,
        experience_id: str,
        *,
        target: ExperienceStage,
        evidence: StageEvidence,
    ) -> ExperienceRecord:
        """Advance an experience by exactly one maturity stage (§11.11).

        Only a single ``+1`` transition is permitted -- ``target`` must equal
        ``current + 1`` -- otherwise ``ValueError`` (no skipping). Each transition
        checks only its own gate from the §11.5 truth table; an unsatisfied gate
        raises ``PermissionError`` (same failure semantics as ``promote``).

        The X3->X4 transition is owned by ``promote`` (which adds the four
        promotion gates), so calling this with ``target == X4_POLICY`` raises
        ``ValueError`` pointing at ``promote``.
        """
        raw = self.store.get("experience", experience_id)
        if raw is None:
            raise KeyError(experience_id)
        experience = ExperienceRecord.model_validate(raw)
        current = experience.stage

        # X3 -> X4 is promote()'s transition (it enforces the four gates).
        if (
            current == ExperienceStage.X3_CROSS_PROJECT
            and target == ExperienceStage.X4_POLICY
        ):
            raise ValueError(
                "X3->X4 promotion must go through promote() "
                "(enforces the four promotion gates)"
            )

        expected = _NEXT_STAGE.get(current)
        if expected is None or target != expected:
            raise ValueError(
                f"advance_stage allows only a single +1 step; "
                f"cannot advance from {current} to {target}"
            )

        _check_stage_gate(experience, evidence, target)

        # model_copy does not re-run validators, so propagate promoted explicitly
        # (the model validator still derives it on every load/construction, which
        # is the authoritative guarantee that stage is the source of truth).
        advanced = experience.model_copy(
            update={
                "stage": target,
                "promoted": target == ExperienceStage.X4_POLICY,
            }
        )
        return self.record(advanced)

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
        # §11.3: promoted is derived from stage; X4_POLICY is the only "promoted"
        # state. Setting the stage drives promoted (model_copy does not re-run the
        # validator, so both fields are set together; loads re-derive on demand).
        promoted = experience.model_copy(
            update={"stage": ExperienceStage.X4_POLICY, "promoted": True}
        )
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
