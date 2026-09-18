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


def test_api_experience_promotion_gates_are_caller_declared(runtime: AutoResearchApplication):
    """Regression guard for D-A7-01 -- NOT a defect assertion.

    Every one of ``promote()``'s four gates (``recurrence_count >= 2``,
    ``grade in {E2,E3,H3}``, ``reviewer_approved``, ``human_approved``) is
    supplied by the caller, so two ordinary POSTs still produce a promoted
    experience:

        POST /experiences               {"grade": "H3", "recurrence_count": 2}
        POST /experiences/{id}/promote  {"reviewer_approved": true,
                                         "human_approved": true}

    This is *by design for now*: R006 §11.11 freezes ``promote()``'s signature
    and failure semantics, ``promoted`` is slated to become derived from
    ``stage``, and the stage ladder (``advance_stage``) plus authenticated
    approval writes are the P2 / authentication-layer deliverables.

    **The obvious shortcut is wrong and this test exists to stop it.** Blocking
    a caller-declared ``grade`` at the creation boundary looks like the same fix
    as blocking ``promoted``, but it would make gate 2 unreachable through the
    entire public API: no other code path raises an *experience* record's grade
    (every non-``E0`` write targets ``EvidenceItem``/``EvidenceCandidate``), and
    ``ExperienceSink`` pins ``E0`` by design. That would silently disable
    promotion instead of securing it. Measured: adding such a guard turns the
    ``grade="H3"`` creation below from 201 into 409 / 404.

    **This test has no discriminating power and must not be cited as evidence.**
    It pins today's behaviour so that a future change is a deliberate, visible
    decision rather than a silent one. When P2 lands and ``promoted`` is derived
    from ``stage``, this test is expected to fail -- update it then, do not
    "fix" the code back.
    """

    async def scenario():
        transport = httpx.ASGITransport(app=create_api(runtime))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            # Gate 2 must stay reachable: a caller-declared grade has to be
            # accepted at creation, because nothing else supplies it.
            created = await client.post(
                "/experiences",
                json={
                    "experience_id": "exp-graded",
                    "project_id": "api01",
                    "problem": "carried debt D-A7-01",
                    "technique": "t",
                    "outcome": "o",
                    "grade": "H3",
                    "recurrence_count": 2,
                },
            )
            assert created.status_code == 201, (
                "D-A7-02: if creation now rejects a caller-declared grade, "
                "promotion gate 2 has become unreachable via the public API "
                "(nothing else raises an experience grade). Revert that guard "
                "and fix gate 2 through the P2 stage ladder instead."
            )

            promoted = await client.post(
                "/experiences/exp-graded/promote",
                json={"reviewer_approved": True, "human_approved": True},
            )
            assert promoted.status_code == 200, (
                "D-A7-01: promotion still succeeds on caller-declared gates. "
                "If this now fails, the P2 stage ladder or authenticated "
                "approvals landed -- delete this test and cite that PR instead."
            )
            assert promoted.json()["promoted"] is True
            assert runtime.knowledge.get_page("exp-graded").level == 2

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
