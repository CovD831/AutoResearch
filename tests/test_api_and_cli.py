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
