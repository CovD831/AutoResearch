from __future__ import annotations

from pathlib import Path

from autoresearch.application import AutoResearchApplication
from autoresearch.contracts import (
    EvidenceGrade,
    EvidenceItem,
    EvidenceType,
    LifecycleState,
    ManuscriptRevisionRequest,
    PaperRecord,
    ResumeRequest,
    RunRequest,
    RunStatus,
)


def _abstract_papers(project_id: str) -> list[PaperRecord]:
    return [
        PaperRecord(
            project_id=project_id,
            title="Evidence-aware agent workflows",
            abstract=(
                "We propose a provenance-aware method for research workflows. "
                "The method is evaluated on a controlled benchmark. "
                "Future work should examine durable human review."
            ),
            authors=["A. Researcher"],
            year=2025,
            doi="10.1000/evidence-a",
            url="https://example.invalid/evidence-a",
            source="user_seed",
            source_record_id="seed-a",
        ),
        PaperRecord(
            project_id=project_id,
            title="Structured handoffs for multi-agent systems",
            abstract=(
                "This study evaluates bounded handoffs between specialized agents. "
                "Experiments use a reproducible task suite. "
                "A limitation is incomplete evidence coverage."
            ),
            authors=["B. Researcher"],
            year=2024,
            doi="10.1000/evidence-b",
            url="https://example.invalid/evidence-b",
            source="user_seed",
            source_record_id="seed-b",
        ),
    ]


def test_no_papers_stops_before_reader(
    runtime: AutoResearchApplication,
    project,
):
    result = runtime.run(
        RunRequest(
            project_id="demo",
            idea="Evaluate evidence gates for research agents.",
        )
    )
    assert result["status"] == RunStatus.BLOCKED
    assert result["state"]["lifecycle_state"] == LifecycleState.WAITING_EVIDENCE
    assert result["state"]["paper_ids"] == []
    assert result["state"]["reading_card_ids"] == []
    assert result["state"]["manuscript_id"] is None
    project_dir = Path(runtime.settings.projects_dir) / "demo"
    assert (project_dir / "state" / "RUN_INDEX.jsonl").is_file()
    progress = (project_dir / ".project-to-act" / "PROJECT_PROGRESS.md").read_text(encoding="utf-8")
    assert result["run_id"] in progress
    assert "waiting_evidence" in progress


def test_abstracts_create_draft_but_final_gate_blocks_result_claims(
    runtime: AutoResearchApplication,
    project,
):
    result = runtime.run(
        RunRequest(
            project_id="demo",
            idea="Evaluate evidence gates for research agents.",
            seed_papers=_abstract_papers("demo"),
        )
    )
    state = result["state"]
    assert result["status"] == RunStatus.BLOCKED
    assert state["lifecycle_state"] == LifecycleState.WAITING_EVIDENCE
    assert len(state["reading_card_ids"]) == 2
    assert len(state["innovation_ids"]) == 1
    assert state["manuscript_id"]
    manuscript = runtime.store.get("manuscript", state["manuscript_id"])
    assert manuscript["release_ready"] is False
    assert manuscript["unresolved_gaps"]
    draft = (
        Path(runtime.settings.projects_dir) / "demo" / "05_writing" / "MANUSCRIPT_DRAFT.md"
    ).read_text(encoding="utf-8")
    assert "【待真实实验】" in draft

    answer = runtime.answer_paper(
        state["paper_ids"][0],
        "What method and benchmark does the paper describe?",
    )
    assert answer.unresolved is False
    assert answer.evidence_ids
    assert answer.locators == ["abstract"]

    revised = runtime.revise_manuscript(
        state["manuscript_id"],
        ManuscriptRevisionRequest(
            instructions="Tighten the introduction without changing claims.",
            mode="polish",
        ),
    )
    assert revised.parent_manuscript_id == state["manuscript_id"]
    assert revised.evidence_ids == manuscript["evidence_ids"]
    assert revised.release_ready is False


def test_strong_lineage_reaches_reviewed_draft(
    runtime: AutoResearchApplication,
    project,
    tmp_path: Path,
):
    first = tmp_path / "paper-a.txt"
    second = tmp_path / "paper-b.txt"
    first.write_text(
        "We propose an evidence-aware method for agent workflows. "
        "The method uses a deterministic policy and an auditable benchmark. "
        "Experiments compare failure rates against a baseline. "
        "A limitation is evaluation in only one domain.",
        encoding="utf-8",
    )
    second.write_text(
        "This paper studies structured handoffs in multi-agent systems. "
        "The approach stores artifact identifiers instead of full chat histories. "
        "The benchmark evaluates recovery and provenance. "
        "Future work should test additional research domains.",
        encoding="utf-8",
    )
    papers = _abstract_papers("demo")
    papers[0] = papers[0].model_copy(update={"full_text_path": str(first)})
    papers[1] = papers[1].model_copy(update={"full_text_path": str(second)})
    experiment = runtime.add_evidence(
        EvidenceItem(
            project_id="demo",
            evidence_type=EvidenceType.EXPERIMENT,
            grade=EvidenceGrade.E3,
            title="Registered evaluation run",
            claim="The registered evaluation completed and produced traceable raw outputs.",
            source_uri="artifact://runs/eval-001",
            source_id="eval-001",
            locator="run manifest and raw outputs",
            checksum="sha256:test-eval-001",
            independent_source="experiment:eval-001",
        )
    )

    result = runtime.run(
        RunRequest(
            project_id="demo",
            idea="Evaluate evidence gates for research agents.",
            seed_papers=papers,
        )
    )
    state = result["state"]
    assert result["status"] == RunStatus.COMPLETED
    assert state["lifecycle_state"] == LifecycleState.DRAFT_REVIEWED
    assert experiment.evidence_id in state["evidence_ids"]
    assert not runtime.store.get("manuscript", state["manuscript_id"])["unresolved_gaps"]


def test_release_pauses_and_resumes_with_human_approval(
    runtime: AutoResearchApplication,
    project,
    tmp_path: Path,
):
    text_a = tmp_path / "a.txt"
    text_b = tmp_path / "b.txt"
    text_a.write_text(
        "We propose a method with a reproducible experiment and benchmark. "
        "The approach records provenance for every result and states its limitation.",
        encoding="utf-8",
    )
    text_b.write_text(
        "This study evaluates an independent baseline and ablation. "
        "The method reports raw artifacts and discusses a future work limitation.",
        encoding="utf-8",
    )
    papers = _abstract_papers("demo")
    papers[0] = papers[0].model_copy(update={"full_text_path": str(text_a)})
    papers[1] = papers[1].model_copy(update={"full_text_path": str(text_b)})
    runtime.add_evidence(
        EvidenceItem(
            project_id="demo",
            evidence_type=EvidenceType.EXPERIMENT,
            grade=EvidenceGrade.E3,
            title="Closed-loop evaluation",
            claim="Evaluation artifacts are complete for the registered run.",
            source_id="eval-release",
            locator="run manifest",
            checksum="sha256:release",
            independent_source="experiment:release",
        )
    )
    interrupted = runtime.run(
        RunRequest(
            project_id="demo",
            idea="Evaluate evidence gates for research agents.",
            seed_papers=papers,
            request_release=True,
        )
    )
    assert interrupted["status"] == RunStatus.INTERRUPTED
    assert interrupted["interrupts"][0]["type"] == "human_release_approval"

    resumed = runtime.resume(
        interrupted["run_id"],
        ResumeRequest(
            approval=True,
            reviewer="principal-investigator",
            note="Evidence ledger and manuscript reviewed.",
        ),
    )
    assert resumed["status"] == RunStatus.COMPLETED
    assert resumed["state"]["lifecycle_state"] == LifecycleState.RELEASED
