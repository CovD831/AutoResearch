from __future__ import annotations

import asyncio
import json

import httpx
from typer.testing import CliRunner

from autoresearch.api import create_api
from autoresearch.application import AutoResearchApplication
from autoresearch.cli import app as cli_app
from autoresearch.config import Settings


def test_api_health_project_and_blocked_run(runtime: AutoResearchApplication):
    async def scenario():
        transport = httpx.ASGITransport(app=create_api(runtime))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json()["agent_count"] == 5

            created = await client.post(
                "/projects",
                json={
                    "project_id": "api01",
                    "title": "API project",
                    "idea": "Test the API boundary.",
                },
            )
            assert created.status_code == 201

            run = await client.post(
                "/runs",
                json={
                    "project_id": "api01",
                    "idea": "Test the API boundary.",
                    "seed_papers": [],
                },
            )
            assert run.status_code == 201
            payload = run.json()
            assert payload["status"] == "blocked"
            fetched = await client.get(f"/runs/{payload['run_id']}?include_checkpoint=true")
            assert fetched.status_code == 200
            assert "checkpoint" in fetched.json()

    asyncio.run(scenario())


def test_api_experience_creation_cannot_self_promote(runtime: AutoResearchApplication):
    async def scenario():
        transport = httpx.ASGITransport(app=create_api(runtime))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            promoted_id = "exp-api-promoted"
            promoted = await client.post(
                "/experiences",
                json={
                    "experience_id": promoted_id,
                    "project_id": "api01",
                    "problem": "manual promotion",
                    "technique": "manual",
                    "outcome": "manual",
                    "promoted": True,
                },
            )
            assert promoted.status_code == 409
            assert runtime.store.get("experience", promoted_id) is None
            assert runtime.knowledge.get_page(promoted_id) is None

            staged_id = "exp-api-staged"
            staged = await client.post(
                "/experiences",
                json={
                    "experience_id": staged_id,
                    "project_id": "api01",
                    "problem": "manual stage",
                    "technique": "manual",
                    "outcome": "manual",
                    "stage": "x1_attributed",
                    "applicable_when": ["condition"],
                    "not_applicable_when": ["boundary"],
                },
            )
            assert staged.status_code == 409
            assert runtime.store.get("experience", staged_id) is None
            assert runtime.knowledge.get_page(staged_id) is None

            created_id = "exp-api-raw"
            created = await client.post(
                "/experiences",
                json={
                    "experience_id": created_id,
                    "project_id": "api01",
                    "problem": "raw experience",
                    "technique": "manual",
                    "outcome": "manual",
                },
            )
            assert created.status_code == 201
            assert created.json()["promoted"] is False
            assert created.json()["stage"] == "x0_raw"
            assert runtime.store.get("experience", created_id) is not None
            assert runtime.knowledge.get_page(created_id).level == 1

    asyncio.run(scenario())


def test_cli_doctor_emits_json_without_secrets(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli_app, ["doctor"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["agent_count"] == 5
    assert "llm_api_key" not in payload["settings"]


def test_safe_settings_summary_never_returns_secret_value(tmp_path):
    settings = Settings(
        _env_file=None,
        LLM_PROVIDER="openai-compatible",
        LLM_API_KEY="top-secret-value",
        LLM_BASE_URL="https://example.invalid/v1",
        LLM_MODEL="test-model",
        AUTORESEARCH_DATA_DIR=tmp_path,
    )
    summary = settings.safe_summary()
    assert "top-secret-value" not in json.dumps(summary)
    assert summary["llm_api_key_configured"] is True
