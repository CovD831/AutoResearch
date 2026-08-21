from __future__ import annotations

from pathlib import Path

import pytest

from autoresearch.application import AutoResearchApplication
from autoresearch.config import Settings
from autoresearch.contracts import ProjectCreate


@pytest.fixture
def runtime(tmp_path: Path):
    repository_root = Path(__file__).resolve().parents[1]
    settings = Settings(
        _env_file=None,
        LLM_PROVIDER="offline",
        AUTORESEARCH_DATA_DIR=tmp_path / "var",
        AUTORESEARCH_DB_PATH=tmp_path / "var" / "autoresearch.sqlite3",
        AUTORESEARCH_CHECKPOINT_PATH=tmp_path / "var" / "checkpoints.sqlite3",
        AUTORESEARCH_PROJECTS_DIR=tmp_path / "paper-projects",
        AUTORESEARCH_TEMPLATE_DIR=repository_root / "paper-projects" / "_template",
        AUTORESEARCH_NETWORK_ENABLED=False,
    )
    application = AutoResearchApplication(settings)
    yield application
    application.close()


@pytest.fixture
def project(runtime: AutoResearchApplication):
    runtime.create_project(
        ProjectCreate(
            project_id="demo",
            title="Demo evidence-governed research",
            idea="Evaluate evidence gates for research agents.",
        )
    )
    return runtime.projects.get("demo")
