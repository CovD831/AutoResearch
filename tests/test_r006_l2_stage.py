"""R-006 L2 lane: experience maturity ladder (X0->X4 state machine).

Covers:
- incremental promotion X0->X1->X2->X3->X4 (the full ladder)
- no-skipping (advance_stage is +1 only)
- per-hop gate *discriminating power* (each gate must reject when violated)
- promoted/stage consistency (promoted == (stage == X4_POLICY))

Authority: docs/rearchitecture/R006-knowledge-experience/04-l2-contracts.md
§11.3 / §11.4 / §11.5 / §11.11.
"""

from __future__ import annotations

import pytest

from autoresearch.contracts import (
    EvidenceGrade,
    ExperienceRecord,
    ExperienceStage,
)
from autoresearch.evolution_service import ReproductionRecord, StageEvidence

_BOUND = {"applicable_when": ["when"], "not_applicable_when": ["not when"]}


def _store(runtime, rec: ExperienceRecord) -> ExperienceRecord:
    return runtime.experiences.record(rec)


def _make(runtime, experience_id: str, stage: ExperienceStage, **kw) -> ExperienceRecord:
    return _store(
        runtime,
        ExperienceRecord(
            experience_id=experience_id,
            project_id="demo",
            problem="p",
            technique="t",
            outcome="o",
            stage=stage,
            **kw,
        ),
    )


def _x0(runtime, eid, **kw):
    return _make(runtime, eid, ExperienceStage.X0_RAW, **kw)


def _x1(runtime, eid, **kw):
    return _make(runtime, eid, ExperienceStage.X1_ATTRIBUTED, **_BOUND, **kw)


def _x2(runtime, eid, **kw):
    return _make(
        runtime,
        eid,
        ExperienceStage.X2_REPRODUCED,
        regression_set_id="rs1",
        **_BOUND,
        **kw,
    )


def _x3(runtime, eid, **kw):
    return _make(
        runtime,
        eid,
        ExperienceStage.X3_CROSS_PROJECT,
        regression_set_id="rs1",
        counterexample_ids=["cx1"],
        **_BOUND,
        **kw,
    )


# ---------------------------------------------------------------------------
# full ladder: X0 -> X1 -> X2 -> X3 -> X4
# ---------------------------------------------------------------------------


def test_full_ladder_x0_to_x4(runtime, project):
    rec = _x0(runtime, "exp_ladder")
    rec = _store(runtime, rec.model_copy(update=_BOUND))
    rec = runtime.experiences.advance_stage(
        "exp_ladder", target=ExperienceStage.X1_ATTRIBUTED, evidence=StageEvidence()
    )
    assert rec.stage is ExperienceStage.X1_ATTRIBUTED
    assert rec.promoted is False

    rec = _store(runtime, rec.model_copy(update={"regression_set_id": "rs1"}))
    rec = runtime.experiences.advance_stage(
        "exp_ladder",
        target=ExperienceStage.X2_REPRODUCED,
        evidence=StageEvidence(
            reproductions=[ReproductionRecord(project_id="demo", passed=True)]
        ),
    )
    assert rec.stage is ExperienceStage.X2_REPRODUCED
    assert rec.promoted is False

    rec = _store(runtime, rec.model_copy(update={"counterexample_ids": ["cx1"]}))
    rec = runtime.experiences.advance_stage(
        "exp_ladder",
        target=ExperienceStage.X3_CROSS_PROJECT,
        evidence=StageEvidence(
            reproductions=[
                ReproductionRecord(project_id="demo", passed=True),
                ReproductionRecord(project_id="other", passed=True),
            ]
        ),
    )
    assert rec.stage is ExperienceStage.X3_CROSS_PROJECT
    assert rec.promoted is False

    # X3 -> X4: promote() enforces the four promotion gates (AND).
    rec = _store(
        runtime, rec.model_copy(update={"recurrence_count": 5, "grade": EvidenceGrade.E2})
    )
    rec = runtime.experiences.promote(
        "exp_ladder", reviewer_approved=True, human_approved=True
    )
    assert rec.stage is ExperienceStage.X4_POLICY
    assert rec.promoted is True


# ---------------------------------------------------------------------------
# no skipping: only +1 is allowed
# ---------------------------------------------------------------------------


def test_skip_level_rejected(runtime, project):
    _store(runtime, _x0(runtime, "exp_skip").model_copy(update=_BOUND))
    with pytest.raises(ValueError):
        runtime.experiences.advance_stage(
            "exp_skip", target=ExperienceStage.X2_REPRODUCED, evidence=StageEvidence()
        )


def test_x3_x4_must_use_promote(runtime, project):
    rec = _x3(runtime, "exp_prom")
    assert rec.stage is ExperienceStage.X3_CROSS_PROJECT
    # advance_stage must NOT perform X3->X4; that is promote()'s job.
    with pytest.raises(ValueError):
        runtime.experiences.advance_stage(
            "exp_prom", target=ExperienceStage.X4_POLICY, evidence=StageEvidence()
        )


# ---------------------------------------------------------------------------
# per-hop gate discriminating power (violation -> PermissionError)
# ---------------------------------------------------------------------------


def test_x0_x1_empty_boundary_rejected(runtime, project):
    _x0(runtime, "exp_x01")  # X0 with empty boundaries
    with pytest.raises(PermissionError):
        runtime.experiences.advance_stage(
            "exp_x01", target=ExperienceStage.X1_ATTRIBUTED, evidence=StageEvidence()
        )


def test_x1_x2_no_regression_rejected(runtime, project):
    _x1(runtime, "exp_x12a")  # boundaries present, no regression_set_id
    with pytest.raises(PermissionError):
        runtime.experiences.advance_stage(
            "exp_x12a",
            target=ExperienceStage.X2_REPRODUCED,
            evidence=StageEvidence(),
        )


def test_x1_x2_sandbox_not_passed_rejected(runtime, project):
    _x1(runtime, "exp_x12b", regression_set_id="rs1")
    # regression present, but sandbox reproduction failed.
    with pytest.raises(PermissionError):
        runtime.experiences.advance_stage(
            "exp_x12b",
            target=ExperienceStage.X2_REPRODUCED,
            evidence=StageEvidence(
                reproductions=[ReproductionRecord(project_id="demo", passed=False)]
            ),
        )


def test_x2_x3_no_cross_project_rejected(runtime, project):
    _x2(runtime, "exp_x23a", counterexample_ids=["cx1"])
    # sandbox passed, but only within the same project (no cross-project record).
    with pytest.raises(PermissionError):
        runtime.experiences.advance_stage(
            "exp_x23a",
            target=ExperienceStage.X3_CROSS_PROJECT,
            evidence=StageEvidence(
                reproductions=[ReproductionRecord(project_id="demo", passed=True)]
            ),
        )


def test_x2_x3_no_counterexample_rejected(runtime, project):
    _x2(runtime, "exp_x23b")  # cross-project passed, but no counterexample_ids
    with pytest.raises(PermissionError):
        runtime.experiences.advance_stage(
            "exp_x23b",
            target=ExperienceStage.X3_CROSS_PROJECT,
            evidence=StageEvidence(
                reproductions=[
                    ReproductionRecord(project_id="demo", passed=True),
                    ReproductionRecord(project_id="other", passed=True),
                ]
            ),
        )


def test_x3_x4_four_gates_rejected(runtime, project):
    rec = _x3(runtime, "exp_x34", recurrence_count=5, grade=EvidenceGrade.E2)
    # break one of the four gates: downgrade grade below the allowed set.
    rec = _store(runtime, rec.model_copy(update={"grade": EvidenceGrade.E0}))
    with pytest.raises(PermissionError):
        runtime.experiences.promote(
            "exp_x34", reviewer_approved=True, human_approved=True
        )


# ---------------------------------------------------------------------------
# promoted / stage consistency (§11.3)
# ---------------------------------------------------------------------------


def test_promoted_stage_consistency(runtime, project):
    # X4 -> promoted is True.
    rec = _x3(runtime, "exp_px", recurrence_count=5, grade=EvidenceGrade.E2)
    rec = runtime.experiences.promote(
        "exp_px", reviewer_approved=True, human_approved=True
    )
    assert rec.stage is ExperienceStage.X4_POLICY
    assert rec.promoted is True

    # X3 -> promoted is False (promoted is a projection of stage, not settable).
    rec3 = _x3(runtime, "exp_py")
    assert rec3.stage is ExperienceStage.X3_CROSS_PROJECT
    assert rec3.promoted is False

    # A raw record carrying promoted=True but no X4 stage is re-derived to False
    # on load (the illegal "promoted but not X4" state can no longer exist).
    raw = ExperienceRecord.model_validate(
        {
            "experience_id": "exp_pz",
            "project_id": "demo",
            "problem": "p",
            "technique": "t",
            "outcome": "o",
            "promoted": True,
        }
    )
    assert raw.stage is ExperienceStage.X0_RAW
    assert raw.promoted is False  # derived from default stage X0_RAW


# ---------------------------------------------------------------------------
# §10.5 cross-lane hard conflict: record() must derive the wiki revision
#
# These tests only have discriminating power when L-06 (append-only wiki writer,
# C1 / §11.9) and L-07 (maturity ladder) are BOTH present. On either branch
# alone the `revision` handling is not exercised the same way:
#   - on L-06 alone, ExperienceService.record() does not exist yet;
#   - on L-07 alone, add_page is an upsert and silently overwrites, so the
#     duplicate write "succeeds" for the wrong reason.
# Therefore this file must be run on the stacked (L-06 <- L-07) branch.
# ---------------------------------------------------------------------------


def test_record_same_experience_twice_appends_two_revisions(runtime):
    """§10.5: re-recording the same experience must append, not crash.

    experience_sink re-records the same experience_id on dedup / recurrence
    accumulation (experience_sink.py:547, :755). Under append-only that is a
    second write to the same page_id, so record() must derive the next revision.
    """
    from autoresearch.knowledge import KnowledgeService

    _x0(runtime, "exp_rr")

    # Same experience_id recorded a second time (recurrence accumulation).
    stored = runtime.store.get("experience", "exp_rr")
    again = ExperienceRecord.model_validate(stored).model_copy(
        update={"recurrence_count": 2}
    )
    runtime.experiences.record(again)

    # Two distinct revisions must exist -- the write appended, it did not
    # overwrite and it did not raise.
    versions = [
        row
        for row in runtime.store.list("wiki_page")
        if row["page_id"] == "exp_rr"
    ]
    assert len(versions) == 2, f"expected 2 revisions, got {len(versions)}"
    assert sorted(v["revision"] for v in versions) == [1, 2]

    # The head resolves to r2 and r1 is still readable (never overwritten).
    head = runtime.knowledge.get_page("exp_rr")
    assert head is not None
    assert head.revision == 2
    r1 = runtime.store.get("wiki_page", "exp_rr:r1")
    assert r1 is not None, "r1 must remain readable after r2 is written"
    assert r1["revision"] == 1

    # The new revision declares what it supersedes (C1).
    assert head.supersedes == "exp_rr:r1"

    # sanity: the service under test is the wired one
    assert isinstance(runtime.knowledge, KnowledgeService)


def test_record_derives_revision_not_constant(runtime):
    """§10.5: revision must be derived from the head, never a constant 1.

    A constant would make the third write fail as well; deriving keeps N writes
    working for any N.
    """
    _x0(runtime, "exp_n3")
    for i in range(2, 5):
        stored = runtime.store.get("experience", "exp_n3")
        runtime.experiences.record(
            ExperienceRecord.model_validate(stored).model_copy(
                update={"recurrence_count": i}
            )
        )

    versions = [
        row for row in runtime.store.list("wiki_page") if row["page_id"] == "exp_n3"
    ]
    assert sorted(v["revision"] for v in versions) == [1, 2, 3, 4]
    assert runtime.knowledge.get_page("exp_n3").revision == 4
