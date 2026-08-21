from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from autoresearch.application import AutoResearchApplication
from autoresearch.contracts import (
    EvolutionProposal,
    ProjectCreate,
    RunRequest,
    UserProfileItem,
    WorkPackageUpdate,
)


def test_project_template_is_instantiated_once(runtime: AutoResearchApplication):
    result = runtime.create_project(
        ProjectCreate(
            project_id="paper01",
            title="A real project folder",
            idea="Study structured handoffs.",
        ),
        owner="researcher",
    )
    path = Path(result["path"])
    manifest = yaml.safe_load((path / "PROJECT_MANIFEST.yaml").read_text(encoding="utf-8"))
    assert manifest["project_id"] == "paper01"
    assert manifest["status"] == "active"
    assert "Study structured handoffs" in (path / "00_intake" / "IDEA.md").read_text(
        encoding="utf-8"
    )
    assert (path / ".project-to-act").is_dir()

    with pytest.raises(FileExistsError):
        runtime.create_project(ProjectCreate(project_id="paper01", title="No overwrite"))


def test_profile_inference_is_capped_until_user_confirms(
    runtime: AutoResearchApplication,
):
    item = runtime.record_profile(
        UserProfileItem(
            user_id="u1",
            key="preferred_venue",
            value="ICLR",
            confidence=0.95,
            source="inferred from one run",
        )
    )
    assert item.confidence == 0.6
    assert not item.confirmed_by_user


def test_self_evolution_is_proposal_only(runtime: AutoResearchApplication, project):
    proposal = runtime.propose_evolution(
        EvolutionProposal(
            project_id="demo",
            problem="Search query recall was low.",
            proposed_change="Add a reviewed synonym expansion policy.",
            expected_benefit="Improve recall without changing gate policy.",
            risks=["query drift"],
            evidence_ids=[],
        )
    )
    assert proposal.status == "proposed"
    stored = runtime.store.get("evolution_proposal", proposal.proposal_id)
    assert stored["status"] == "proposed"
    assert stored["human_approval_required"] is True


def test_work_package_cannot_complete_without_evidence(
    runtime: AutoResearchApplication,
    project,
):
    run = runtime.run(
        RunRequest(
            project_id="demo",
            idea="Plan evidence-governed work packages.",
        )
    )
    work_package_id = run["state"]["work_package_ids"][0]
    with pytest.raises(PermissionError):
        runtime.update_work_package(
            work_package_id,
            WorkPackageUpdate(status="completed"),
        )
