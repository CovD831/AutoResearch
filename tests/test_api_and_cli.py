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


async def _seed_evidence(client: httpx.AsyncClient, project_id: str, claim: str) -> str:
    """Create one evidence item and return its id.

    ``locator`` is required by ``EvidenceService.add`` -- evidence without a
    locator is not admissible, so the test must supply one rather than the
    service relaxing the rule for tests.
    """
    created = await client.post(
        "/evidence",
        json={
            "project_id": project_id,
            "evidence_type": "paper",
            "grade": "E2",
            "title": claim,
            "claim": claim,
            "locator": f"sec:{claim}",
            "independent_source": "unit-test",
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["evidence_id"]


def test_default_evidence_query_reports_when_it_filtered(runtime: AutoResearchApplication):
    """The default `valid_only=true` hides invalidated items -- and says so.

    An invalidated item is a materially different fact from one that was never
    recorded: it means a claim lost its support. A caller receiving N items
    cannot tell "there are N" from "there were N+1 and one was withdrawn"
    unless the response carries a signal. This pins that signal.

    Both directions are asserted, because a header that is *always* present
    proves nothing:
      * nothing invalidated  -> ``Filtered: false`` / ``Omitted: 0``
      * one invalidated      -> ``Filtered: true``  / ``Omitted: 1``, and the
        body really is one item shorter.
    """

    async def scenario():
        transport = httpx.ASGITransport(app=create_api(runtime))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/projects",
                json={
                    "project_id": "evsig",
                    "title": "Evidence filter signal",
                    "idea": "Check that filtering is observable.",
                },
            )
            kept = await _seed_evidence(client, "evsig", "The retained claim")
            dropped = await _seed_evidence(client, "evsig", "The withdrawn claim")

            # --- Direction 1: nothing invalidated yet -----------------------
            before = await client.get("/projects/evsig/evidence")
            assert before.status_code == 200
            assert before.headers["X-Evidence-Filtered"] == "false"
            assert before.headers["X-Evidence-Omitted"] == "0"
            assert len(before.json()) == 2

            # --- invalidate exactly one -------------------------------------
            inv = await client.post(
                f"/evidence/{dropped}/invalidate",
                json={"reason": "source retracted", "actor": "test"},
            )
            assert inv.status_code == 200

            # --- Direction 2: the default query now filters ------------------
            default = await client.get("/projects/evsig/evidence")
            assert default.status_code == 200
            assert default.headers["X-Evidence-Filtered"] == "true"
            assert default.headers["X-Evidence-Omitted"] == "1"
            body = default.json()
            assert len(body) == 1, "the default query must omit the invalidated item"
            assert body[0]["evidence_id"] == kept

            # --- the explicit opt-out still returns everything ---------------
            full = await client.get("/projects/evsig/evidence?valid_only=false")
            assert full.status_code == 200
            assert full.headers["X-Evidence-Filtered"] == "false"
            assert full.headers["X-Evidence-Omitted"] == "0"
            assert len(full.json()) == 2

    asyncio.run(scenario())
