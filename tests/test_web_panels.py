"""L-08 / M13 panel contract tests: K14 ``PanelProjection``, negative cases, read-only guard.

Coverage map
------------
* K14-1  every section carries a ``verification_state`` and it agrees with ``verified``
* K14-2  ``refs`` are opaque identifiers and carry no content (N-3)
* K14-3  non-verified sections must name *why*, and never blank-fill (N-1 / N-2)
* D-L08-01/D-L08-02  the two additive fields behave as documented
* read-only guarantee: the module has no call site that mutates runtime state
* endpoint parity: the builders consume exactly what the 24 endpoints return
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from autoresearch.api import create_api
from autoresearch.application import AutoResearchApplication
from autoresearch.contracts import PaperRecord, ProjectCreate, RunRequest
from autoresearch.web_api import (
    PANEL_IDS,
    PanelProjection,
    PanelReader,
    PanelSection,
    PanelSources,
    build_files_panel,
    build_panel,
    create_web_api,
    resolve_run_id,
)

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "autoresearch" / "web_api.py"

TWO_SEEDS = [
    PaperRecord(
        project_id="panels",
        title="Retrieval Augmented Research Agents",
        abstract="We study RAG for literature review automation.",
        authors=["A. Researcher"],
        year=2024,
        source="user_seed",
    ),
    PaperRecord(
        project_id="panels",
        title="Evidence-Graded Claim Verification",
        abstract="Grading evidence for claim support in automated review.",
        authors=["B. Author"],
        year=2023,
        source="user_seed",
    ),
]


def _seeded(runtime: AutoResearchApplication) -> AutoResearchApplication:
    """A project with a real offline run, real work packages and real audit events."""
    runtime.create_project(
        ProjectCreate(project_id="panels", title="Panels", idea="Panel contract demo")
    )
    runtime.run(
        RunRequest(
            project_id="panels",
            idea="Panel contract demo",
            seed_papers=TWO_SEEDS,
            request_release=True,
        )
    )
    return runtime


def _collect(runtime: AutoResearchApplication) -> PanelSources:
    return PanelReader(runtime=runtime).collect("panels")


# ---------------------------------------------------------------------------
# K14-1 -- no false completion
# ---------------------------------------------------------------------------


def test_section_requires_explicit_verification_state():
    """K14-1: the state is a required field, not a default that can be forgotten."""
    with pytest.raises(ValidationError):
        PanelSection(title="t", refs=[], verified=True)  # type: ignore[call-arg]


def test_verified_flag_must_agree_with_state():
    with pytest.raises(ValidationError):
        PanelSection(
            title="t",
            refs=[],
            verified=True,
            verification_state="unverified",
            unknown_reason="nope",
        )


def test_panel_without_sections_is_rejected():
    """An empty panel must not be constructible: it would read as 'nothing wrong'."""
    with pytest.raises(ValidationError):
        PanelProjection(panel_id="project", sections=[], verification_state="verified")


def test_panel_state_is_the_worst_section():
    ok = build_files_panel()
    assert ok.verification_state == "blocked"
    with pytest.raises(ValidationError):
        PanelProjection(
            panel_id="files",
            sections=ok.sections,
            verification_state="verified",
        )


def test_real_project_panel_marks_every_section(runtime):
    projection = build_panel("project", _collect(_seeded(runtime)))
    assert projection.panel_id == "project"
    assert projection.sections
    for section in projection.sections:
        assert section.verification_state in {"verified", "unverified", "blocked"}
        assert section.verified == (section.verification_state == "verified")


# ---------------------------------------------------------------------------
# K14-3 / N-1 -- missing data is declared, never left blank
# ---------------------------------------------------------------------------


def test_unverified_section_must_carry_a_reason():
    with pytest.raises(ValidationError):
        PanelSection(title="t", refs=[], verified=False, verification_state="unverified")
    with pytest.raises(ValidationError):
        PanelSection(
            title="t",
            refs=[],
            verified=False,
            verification_state="unverified",
            unknown_reason="   ",
        )


def test_verified_section_cannot_carry_an_unknown_reason():
    with pytest.raises(ValidationError):
        PanelSection(
            title="t",
            refs=[],
            verified=True,
            verification_state="verified",
            unknown_reason="but also unknown",
        )


def test_N1_missing_endpoint_payload_is_unverified_with_a_reason(runtime):
    """N-1: work-packages unavailable -> declared unverified, not silently empty."""
    sources = _collect(_seeded(runtime))
    without = PanelSources(
        project_id=sources.project_id,
        project=sources.project,
        run=sources.run,
        work_packages=None,
        evidence=sources.evidence,
        audit_events=sources.audit_events,
    )
    projection = build_panel("project", without)
    section = next(s for s in projection.sections if "work packages" in s.title)
    assert section.verification_state == "unverified"
    assert section.verified is False
    assert section.unknown_reason and section.unknown_reason.strip()
    assert "work-packages" in section.unknown_reason


def test_N1_none_and_empty_are_different_facts(runtime):
    """A failed read (None) must not be reported the same way as an empty answer."""
    sources = _collect(_seeded(runtime))
    failed = PanelSources(
        project_id=sources.project_id,
        audit_events=sources.audit_events,
        evidence=None,
        work_packages=None,
    )
    answered = PanelSources(
        project_id=sources.project_id,
        audit_events=sources.audit_events,
        evidence=[],
        work_packages=[],
    )
    failed_projection = build_panel("project", failed)
    answered_projection = build_panel("project", answered)
    assert failed_projection.verification_state == "unverified"
    assert answered_projection.verification_state == "unverified"
    for title in ("证据覆盖", "任务"):
        left = next(s for s in failed_projection.sections if title in s.title)
        right = next(s for s in answered_projection.sections if title in s.title)
        assert left.unknown_reason != right.unknown_reason
        assert "not available" in left.unknown_reason


def test_every_non_verified_section_in_real_panels_has_a_reason(runtime):
    sources = _collect(_seeded(runtime))
    for panel_id in ("project", "evidence", "approval", "files"):
        for section in build_panel(panel_id, sources).sections:
            if section.verification_state != "verified":
                assert section.unknown_reason
                assert section.unknown_reason.strip()


# ---------------------------------------------------------------------------
# Regressions found by looking at the rendered page (ui-skeleton-first step 1)
# ---------------------------------------------------------------------------


def test_never_run_project_does_not_claim_verified_no_blockers(runtime):
    """Defect found by the `bare` screenshot.

    With no run there is no ``ResearchState``, so ``blockers``/``diagnostics``
    were never read. The first implementation fell through to
    ``verified("no blockers")`` -- claiming the absence of blockers for a project
    that never ran, which is precisely the false completion M13-04 forbids.
    """
    runtime.create_project(
        ProjectCreate(project_id="barep", title="Bare", idea="never run")
    )
    projection = build_panel("project", PanelReader(runtime=runtime).collect("barep"))
    blockers = next(s for s in projection.sections if "阻塞" in s.title)
    assert blockers.verification_state == "unverified"
    assert blockers.facts["read_scope"] == "work-packages-only"
    assert "never read" in (blockers.unknown_reason or "")


def test_no_evidence_means_the_retraction_section_is_unverified(runtime):
    """Same class as above: 'no retraction recorded' is not knowable without evidence."""
    runtime.create_project(
        ProjectCreate(project_id="bareq", title="Bare", idea="never run")
    )
    projection = build_panel("evidence", PanelReader(runtime=runtime).collect("bareq"))
    retraction = next(s for s in projection.sections if "retraction" in s.title)
    assert retraction.verification_state == "unverified"
    assert "never observed" in (retraction.unknown_reason or "")


def test_approval_history_counts_only_real_decisions(runtime):
    """`project.created` / `run.started` are human actions but not approvals."""
    runtime.create_project(
        ProjectCreate(project_id="barer", title="Bare", idea="never run")
    )
    projection = build_panel("approval", PanelReader(runtime=runtime).collect("barer"))
    history = next(s for s in projection.sections if "approval history" in s.title)
    assert history.verification_state == "unverified"
    assert history.facts["human_decision_count"] == "0"


def test_approval_history_is_verified_when_a_retraction_is_recorded(runtime):
    """The retraction write path is a real human decision and must be attributable."""
    seeded = _seeded(runtime)
    evidence = seeded.evidence.list("panels")
    assert evidence
    seeded.evidence.invalidate(
        evidence[-1].evidence_id, "review board withdrew the source", actor="dr-who"
    )
    projection = build_panel("approval", PanelReader(runtime=seeded).collect("panels"))
    history = next(s for s in projection.sections if "approval history" in s.title)
    assert history.verification_state == "verified"
    # exactly one: the retraction. The run's own human-typed E0 "research idea"
    # evidence must NOT be counted as an approval decision.
    assert history.facts["human_decision_count"] == "1"
    assert history.facts["decision_event_types"] == "evidence.invalidated"
    assert "dr-who" in history.facts["actors"]
    idea = [
        item
        for item in seeded.evidence.list("panels")
        if item.evidence_type == "human" and item.grade == "E0"
    ]
    assert idea, "the fixture relies on the orchestrator recording the idea as E0/human"
    assert idea[0].evidence_id not in history.refs

    retraction = next(
        s
        for s in build_panel("evidence", PanelReader(runtime=seeded).collect("panels")).sections
        if "retraction" in s.title
    )
    assert retraction.verification_state == "verified"
    assert retraction.facts["invalid_evidence_count"] == "1"
    assert evidence[-1].evidence_id in retraction.refs


# ---------------------------------------------------------------------------
# N-2 -- blocked is distinguishable from unverified, in data not just in CSS
# ---------------------------------------------------------------------------


def test_N2_blocked_run_is_blocked_and_distinct_from_unverified(runtime):
    """N-2: a genuinely blocked project yields `blocked`, and it differs in data."""
    projection = build_panel("project", _collect(_seeded(runtime)))
    states = {s.verification_state for s in projection.sections}
    assert "blocked" in states
    assert "verified" in states, "not every section may collapse to 'unknown'"
    blocked = next(s for s in projection.sections if s.verification_state == "blocked")
    assert blocked.title.startswith("阻塞")
    assert blocked.verified is False
    assert blocked.unknown_reason and blocked.unknown_reason.strip()
    assert projection.verification_state == "blocked"
    # The two non-verified states carry different literals, so the UI cannot
    # render them identically by accident.
    assert {s.verification_state for s in projection.sections} != {"unverified"}


def test_N2_blocked_section_is_never_marked_verified(runtime):
    projection = build_panel("project", _collect(_seeded(runtime)))
    blocked = [s for s in projection.sections if s.verification_state == "blocked"]
    assert blocked
    for section in blocked:
        assert section.verified is False


def test_no_pending_interrupt_is_unverified_not_blocked(runtime):
    """Absence of a pending decision is 'unknown', not 'blocked' -- they differ."""
    projection = build_panel("approval", _collect(_seeded(runtime)))
    pending = next(s for s in projection.sections if "pending human decision" in s.title)
    assert pending.verification_state == "unverified"
    assert pending.facts["pending"] == "false"
    assert "409" in (pending.unknown_reason or "")


# ---------------------------------------------------------------------------
# K14-2 / N-3 -- refs are references, the panel copies no content
# ---------------------------------------------------------------------------


def test_refs_reject_prose():
    with pytest.raises(ValidationError):
        PanelSection(
            title="t",
            refs=["the user supplied this idea as the starting research intent"],
            verified=True,
            verification_state="verified",
        )


def test_facts_are_bounded_scalars():
    with pytest.raises(ValidationError):
        PanelSection(
            title="t",
            refs=[],
            verified=True,
            verification_state="verified",
            facts={"claim": "x" * 500},
        )
    with pytest.raises(ValidationError):
        PanelSection(
            title="t",
            refs=[],
            verified=True,
            verification_state="verified",
            facts={"NotAMachineKey": "v"},
        )


def test_N3_no_evidence_content_reaches_the_projection(runtime):
    """N-3: every ref is an id, and no evidence claim/title text is copied."""
    seeded = _seeded(runtime)
    sources = _collect(seeded)
    assert sources.evidence, "the fixture must contain real evidence to be meaningful"

    payloads = {
        panel_id: json.dumps(
            build_panel(panel_id, sources).model_dump(mode="json"), ensure_ascii=False
        )
        for panel_id in PANEL_IDS
    }
    for item in sources.evidence:
        for field in ("claim", "title"):
            text = item[field]
            assert len(text) > 20, "a short string could collide by accident"
            for panel_id, blob in payloads.items():
                assert text not in blob, (
                    f"{panel_id} panel copied evidence {field!r}; K14-2 forbids "
                    "content copies"
                )

    # ...and the ids *are* present, so they are genuinely referenced.
    sample = sources.evidence[0]["evidence_id"]
    assert sample in payloads["evidence"]
    assert sample in payloads["project"]


def test_N3_all_refs_are_identifiers(runtime):
    sources = _collect(_seeded(runtime))
    for panel_id in PANEL_IDS:
        projection = build_panel(panel_id, sources)
        for section in projection.sections:
            for ref in section.refs:
                assert ref == ref.strip()
                assert " " not in ref
                assert len(ref) <= 120


# ---------------------------------------------------------------------------
# Read-only guarantee (the module's own AST, mirroring the A6 precedent)
# ---------------------------------------------------------------------------

FORBIDDEN_CALLS = {
    "append_event",
    "put",
    "delete_idempotent",
    "remember_idempotent",
    "finalize_idempotent",
    "create",
    "create_project",
    "run",
    "resume",
    "add_evidence",
    "invalidate",
    "update_work_package",
    "add_page",
    "add_edge",
    "promote",
    "record",
    "record_profile",
    "record_experience",
    "settle_failure_experiences",
    "propose_evolution",
    "revise_manuscript",
    "answer_paper",
    "review",
}


def _called_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def test_panel_module_has_no_mutating_call_site():
    """The boundary is read-only by construction, not by convention."""
    offenders = _called_names(MODULE_PATH) & FORBIDDEN_CALLS
    assert not offenders, f"web_api.py must not mutate runtime state: {offenders}"


def test_panel_module_never_imports_writer_modules():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    writers = {
        "autoresearch.evidence",
        "autoresearch.knowledge",
        "autoresearch.gates",
        "autoresearch.execution_service",
        "autoresearch.project_service",
        "autoresearch.storage",
    }
    assert not (imported & writers), f"unexpected writer import: {imported & writers}"


# ---------------------------------------------------------------------------
# Endpoint parity -- the builders consume exactly what the 24 endpoints return
# ---------------------------------------------------------------------------


async def _http_payloads(runtime: AutoResearchApplication) -> dict[str, Any]:
    transport = httpx.ASGITransport(app=create_api(runtime))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        project = (await c.get("/projects/panels")).json()
        audit = (await c.get("/projects/panels/audit-events")).json()
        packages = (await c.get("/projects/panels/work-packages")).json()
        evidence = (
            await c.get("/projects/panels/evidence?valid_only=false")
        ).json()
        run_id = next(
            event["payload"]["run_id"]
            for event in audit
            if event["event_type"] == "run.started"
        )
        run = (await c.get(f"/runs/{run_id}")).json()
    return {
        "project": project,
        "run": run,
        "work_packages": packages,
        "evidence": evidence,
        "audit_events": audit,
    }


def test_reader_payloads_match_the_real_endpoints(runtime):
    """If an endpoint shape changes, the panel boundary fails here, not in the UI."""
    seeded = _seeded(runtime)
    sources = _collect(seeded)

    async def scenario() -> dict[str, Any]:
        return await _http_payloads(seeded)

    import asyncio

    http = asyncio.run(scenario())

    assert sources.project == http["project"]
    assert sources.run == http["run"]
    assert sources.work_packages == http["work_packages"]
    assert sources.evidence == http["evidence"]
    assert sources.audit_events == http["audit_events"]


def test_run_resolution_uses_the_audit_log_when_project_has_no_run_id(runtime):
    sources = _collect(_seeded(runtime))
    assert "run_id" not in sources.project
    run_id, resolution = resolve_run_id(sources)
    assert run_id == sources.run["run_id"]
    assert resolution == "run-payload"

    audit_only = PanelSources(
        project_id=sources.project_id, audit_events=sources.audit_events
    )
    assert resolve_run_id(audit_only) == (run_id, "audit:run.started")

    assert resolve_run_id(PanelSources(project_id="nothing"))[0] is None


# ---------------------------------------------------------------------------
# ASGI surface
# ---------------------------------------------------------------------------


def test_web_api_serves_panels_and_keeps_the_original_endpoints(runtime):
    import asyncio

    seeded = _seeded(runtime)
    app = create_web_api(seeded, web_root=Path("/nonexistent-web-root"))

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            listing = await client.get("/ui/panels")
            assert listing.status_code == 200
            assert listing.json()["panel_ids"] == list(PANEL_IDS)

            panel = await client.get("/ui/panels/project?project_id=panels")
            assert panel.status_code == 200
            body = panel.json()
            assert body["panel_id"] == "project"
            assert body["sections"]
            assert body["warnings"] == []

            files = await client.get("/ui/panels/files?project_id=panels")
            assert files.json()["verification_state"] == "blocked"

            missing = await client.get("/ui/panels/nope?project_id=panels")
            assert missing.status_code == 404

            health = await client.get("/api/health")
            assert health.status_code == 200
            assert health.json()["agent_count"] == 5

    asyncio.run(scenario())


def test_reader_reports_a_failed_read_as_a_warning_not_an_exception():
    class Broken:
        class projects:  # noqa: N801
            @staticmethod
            def get(_project_id: str) -> dict:
                raise RuntimeError("boom")

        store = None

    reader = PanelReader(runtime=Broken())
    sources = reader.collect("x")
    assert sources.project is None
    assert reader.warnings and "boom" in reader.warnings[0]
    assert sources.audit_events is None


# ---------------------------------------------------------------------------
# Approval fixture shape parity with the graph that emits it
# ---------------------------------------------------------------------------


def _interrupt_keys(path: Path) -> set[str]:
    """Keys of the dict literal passed to ``interrupt(...)`` in graph.py."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "interrupt" and node.args:
            literal = node.args[0]
            if isinstance(literal, ast.Dict):
                return {
                    key.value
                    for key in literal.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
    raise AssertionError("no interrupt({...}) call found in graph.py")


def test_approval_panel_reads_the_keys_the_graph_actually_emits(runtime):
    """Guards the BFF against upstream drift in the human-approval payload."""
    graph = Path(__file__).resolve().parents[1] / "src" / "autoresearch" / "graph.py"
    keys = _interrupt_keys(graph)
    assert {"type", "operation", "risk_level", "evidence_ids"} <= keys

    interrupt = {
        "type": "human_release_approval",
        "project_id": "panels",
        "run_id": "run_fixture",
        "operation": "external_manuscript_release",
        "risk_level": "L4",
        "message": "x" * 40,
        "evidence_ids": ["ev_one", "ev_two"],
    }
    sources = PanelSources(
        project_id="panels",
        run={"run_id": "run_fixture", "interrupts": [interrupt]},
        evidence=[],
        audit_events=[],
        work_packages=[],
    )
    projection = build_panel("approval", sources)
    scope = next(s for s in projection.sections if "scope" in s.title)
    risk = next(s for s in projection.sections if "risk level" in s.title)
    pending = next(s for s in projection.sections if "pending human decision" in s.title)

    assert scope.verification_state == "verified"
    assert scope.facts["operation"] == "external_manuscript_release"
    assert scope.facts["interrupt_type"] == "human_release_approval"
    assert risk.verification_state == "verified"
    assert risk.facts["risk_level"] == "L4"
    assert risk.facts["source"] == "run:interrupts[].risk_level"
    assert pending.facts["pending"] == "true"
    # the approval message is prose: it stays behind a ref (K14-2)
    assert interrupt["message"] not in json.dumps(projection.model_dump(mode="json"))


def test_files_panel_is_blocked_with_a_named_dependency():
    projection = build_files_panel()
    assert projection.panel_id == "files"
    section = projection.sections[0]
    assert section.verification_state == "blocked"
    assert section.facts["blocked_by"] == "K11 AccessPolicy (L-09)"
    assert "M13-06" in (section.unknown_reason or "")


# ---------------------------------------------------------------------------
# tab-bar truthfulness (defect found by adversarial review, L3 §9.2)
# ---------------------------------------------------------------------------

WEB_JS = Path(__file__).resolve().parents[1] / "web" / "app.js"


def _dot_class_literal_counts(source: str) -> Counter:
    """How many times each `tab__dot--<state>` literal appears."""
    return Counter(re.findall(r'"tab__dot--(\w+)"', source))


def _dot_class_map_keys(source: str) -> set[str]:
    """State keys of the object literal that maps states to dot classes.

    Located by its *values*, not by the variable it is assigned to, so renaming
    the map is not a false failure.
    """
    match = re.search(r"\{[^{}]*\"tab__dot--verified\"[^{}]*\}", source)
    if not match:
        return set()
    return set(re.findall(r"(\w+):\s*\"tab__dot--\w+\"", match.group(0)))


def _state_function_body(source: str) -> str:
    """Body of the `function <name>(value) { ... }` that reads ``STATE_LABEL[value]``.

    Located by what it *does* rather than by its name, so renaming it is not a
    false failure.
    """
    for match in re.finditer(r"function \w+\(value\) \{([^{}]*)\}", source):
        body = match.group(1)
        if "STATE_LABEL[value]" in body:
            return body
    return ""


def test_tab_dot_class_is_never_hardcoded():
    """The audited defect: `tab__dot--unverified` was a literal, so the tab bar
    showed '?' for every panel -- disagreeing with the panel's own chip.

    Strengthened twice: (1) falsification R4 -- matching only the original
    whole-string form let a semantically identical rewrite through; (2) the first
    strengthening anchored on the identifier `TAB_DOT_CLASS`, so *renaming* that
    (a behaviour-preserving refactor) produced a noisy `ValueError` while telling
    us nothing. This version is name-independent: every dot-class literal must
    appear **exactly once**, so a fallback copy such as
    `cls || "tab__dot--unverified"` is rejected, and a rename is simply fine.

    Known blind spot (measured, L3 §10.7): string concatenation
    (`"tab__dot--" + "unverified"`) hides the literal from this guard. The
    behavioural Node guard is what bounds that case.
    """
    source = WEB_JS.read_text(encoding="utf-8")
    counts = _dot_class_literal_counts(source)
    assert set(counts) == {"verified", "unverified", "blocked"}, (
        f"expected exactly the three K14 dot classes to be declared, got {sorted(counts)}"
    )
    duplicated = {name: n for name, n in counts.items() if n > 1}
    assert not duplicated, (
        "a dot class literal is declared more than once -- that is a fallback copy, "
        f"i.e. the dot is being defaulted to a state instead of derived: {duplicated}"
    )
    assert "syncTabState" in source


def test_dot_class_map_covers_exactly_the_three_k14_states():
    """Name-independent: locate the object literal by its *values*, not by the
    variable it is assigned to, so renaming the map does not break the guard."""
    keys = _dot_class_map_keys(WEB_JS.read_text(encoding="utf-8"))
    assert keys == {"verified", "unverified", "blocked"}, keys


def test_renderer_does_not_coerce_an_unknown_state_into_a_real_one():
    """Second instance of the same defect family: `stateOf()` defaults any
    unrecognised value to `unverified`, i.e. invents a legitimate state.

    Strengthened after falsification finding R4: asserting the absence of the *old
    literal* let an equivalent rewrite through. Now the function body itself may
    not return any of the three real state literals.

    Known blind spot (measured, L3 §10.7): concatenation such as
    `"unverifie" + "d"` is invisible here; the behavioural Node guard catches it.
    """
    body = _state_function_body(WEB_JS.read_text(encoding="utf-8"))
    assert "return" in body, "the state function body was not located"
    for state in ("verified", "unverified", "blocked"):
        assert f'"{state}"' not in body, (
            f"the state function must not name the real state {state!r}: an "
            "unrecognised verification_state has to stay unrecognised, not be "
            f"laundered into a real one. body={body.strip()!r}"
        )


#: Behaviour-preserving rewrites the guards must survive without a false failure.
#: Falsification-adjacent defect class found while answering team-lead: the first
#: R4 fix anchored on identifiers, so a legal rename raised `ValueError` -- a
#: *false failure* (the guard went red although no behaviour regressed).
BEHAVIOUR_PRESERVING_RENAMES: dict[str, tuple[tuple[str, str], ...]] = {
    "rename the dot-class map": (("TAB_DOT_CLASS", "DOT_CLASSES"),),
    "rename the state function": (("stateOf", "renderKeyFor"),),
    "rename both (map -> m, fn -> stateToRenderKey)": (
        ("TAB_DOT_CLASS", "m"),
        ("stateOf", "stateToRenderKey"),
    ),
    "rename both and collapse the map to one line": (
        ("TAB_DOT_CLASS", "m"),
        ("stateOf", "stateToRenderKey"),
    ),
}


def _apply_renames(source: str, pairs: tuple[tuple[str, str], ...]) -> str:
    for old, new in pairs:
        assert old in source, f"rename anchor {old!r} not found"
        source = source.replace(old, new)
    return source


def _collapse_dot_map(source: str) -> str:
    """Rewrite the three-entry dot map as a single line (a formatting-only change)."""
    match = re.search(
        r"\{\s*verified:\s*\"tab__dot--verified\".*?"
        r'blocked:\s*"tab__dot--blocked"\s*\}',
        source,
        re.S,
    )
    assert match, "dot-class map literal not found"
    keys = ["verified", "unverified", "blocked"]
    collapsed = "{" + ",".join(
        f'{key}:"tab__dot--{key}"' for key in keys
    ) + "}"
    return source[: match.start()] + collapsed + source[match.end() :]


def test_guards_are_name_independent_and_do_not_false_fail():
    """Regression for the *false failure* defect class.

    A behaviour-preserving rename must not make a source guard error. The first
    R4 fix anchored on the literal identifiers `TAB_DOT_CLASS` and
    `function stateOf(value) {`, so renaming either raised `ValueError` -- a red
    guard with no regression behind it. Guards must be anchored to *semantics*,
    not to *names*: otherwise a future refactor is either blocked by noise or,
    worse, someone "fixes" the guard by relaxing it.
    """
    source = WEB_JS.read_text(encoding="utf-8")
    baseline = (
        _dot_class_literal_counts(source),
        _dot_class_map_keys(source),
        _state_function_body(source).strip(),
    )
    assert baseline[1] == {"verified", "unverified", "blocked"}
    assert baseline[2], "baseline state-function body was not located"

    for label, pairs in BEHAVIOUR_PRESERVING_RENAMES.items():
        renamed = _apply_renames(source, pairs)
        if "one line" in label:
            renamed = _collapse_dot_map(renamed)
        assert renamed != source, label
        # must not raise, and must reach the same verdict as on the real source
        assert _dot_class_literal_counts(renamed) == baseline[0], label
        assert _dot_class_map_keys(renamed) == baseline[1], label
        assert _state_function_body(renamed).strip() == baseline[2], label


def test_renamed_renderer_is_behaviourally_equivalent(tmp_path):
    """Proves the renames above are genuinely benign -- by running the *real*
    renderer on the renamed source in the DOM stub.

    Without this, "the guards must not false-fail on a rename" would rest on an
    unverified assumption that the rename changes nothing. A negative control is
    included so this test cannot pass vacuously.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node is unavailable; cannot execute the renderer variant")
    script = REPO_ROOT / "web" / "dev" / "render_contract_check.mjs"
    source = WEB_JS.read_text(encoding="utf-8")

    def run(text: str, name: str) -> subprocess.CompletedProcess:
        target = tmp_path / name
        target.write_text(text, encoding="utf-8")
        return subprocess.run(
            [node, str(script), f"--app={target}"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            check=False,
        )

    for index, (label, pairs) in enumerate(BEHAVIOUR_PRESERVING_RENAMES.items()):
        renamed = _apply_renames(source, pairs)
        if "one line" in label:
            renamed = _collapse_dot_map(renamed)
        proc = run(renamed, f"renamed-{index}.js")
        assert proc.returncode == 0, (
            f"a behaviour-preserving rename ({label}) changed the rendered "
            f"behaviour, so it is not a valid no-false-failure case:\n"
            f"{proc.stdout}{proc.stderr}"
        )

    # negative control: the same harness must still fail on a real regression,
    # otherwise "returncode == 0" above proves nothing.
    broken = source.replace(
        'blocked: "tab__dot--blocked"', 'blocked: "tab__dot--unverified"', 1
    )
    assert broken != source
    control = run(broken, "broken.js")
    assert control.returncode != 0, (
        "the negative control passed, so this test's harness is not actually "
        f"checking behaviour:\n{control.stdout}"
    )


def test_renderer_contract_holds_without_a_browser():
    """Falsification finding R2: every other renderer guard here either needs a
    browser (skipped in a browser-less CI) or only fingerprints the source text
    (defeated by an equivalent rewrite). This one executes the real
    ``web/app.js`` against a DOM stub under Node and asserts the observable
    classes, so the renderer keeps a guard that fires with no browser at all.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node is unavailable; the no-browser renderer guard cannot run")
    script = REPO_ROOT / "web" / "dev" / "render_contract_check.mjs"
    assert script.is_file(), f"missing {script}"
    proc = subprocess.run(
        [node, str(script)], capture_output=True, text=True, cwd=str(REPO_ROOT), check=False
    )
    assert proc.returncode == 0, (
        "no-browser renderer contract check failed:\n" + proc.stdout + proc.stderr
    )
    assert "PASS" in proc.stdout


def test_panels_endpoint_reports_real_states_from_the_same_builders(runtime):
    """The tab bar's only truthful source. Must equal the panel endpoint's value."""
    import asyncio

    seeded = _seeded(runtime)
    app = create_web_api(seeded, web_root=Path("/nonexistent-web-root"))
    sources = PanelReader(runtime=seeded).collect("panels")
    expected = {
        panel_id: build_panel(panel_id, sources).verification_state
        for panel_id in PANEL_IDS
    }

    async def scenario() -> dict:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            meta = (await client.get("/ui/panels?project_id=panels")).json()
            per_panel = {
                panel_id: (
                    await client.get(f"/ui/panels/{panel_id}?project_id=panels")
                ).json()["verification_state"]
                for panel_id in PANEL_IDS
            }
        return {"meta": meta, "per_panel": per_panel}

    result = asyncio.run(scenario())
    assert result["meta"]["states"] == expected
    # the tab source and the panel body must agree, panel for panel
    assert result["meta"]["states"] == result["per_panel"]
    assert set(result["meta"]["states"]) == set(PANEL_IDS)
    assert all(
        state in {"verified", "unverified", "blocked"}
        for state in result["meta"]["states"].values()
    )


def test_panels_endpoint_without_project_id_omits_states(runtime):
    """No project selected means no state is known -- so none may be reported."""
    import asyncio

    app = create_web_api(_seeded(runtime), web_root=Path("/nonexistent-web-root"))

    async def scenario() -> dict:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return (await client.get("/ui/panels")).json()

    meta = asyncio.run(scenario())
    assert meta["panel_ids"] == list(PANEL_IDS)
    assert "states" not in meta, (
        "reporting panel states without a project would mean inventing them"
    )


# ---------------------------------------------------------------------------
# Rendered-DOM assertions (needs Chrome; skipped where Playwright is absent)
# ---------------------------------------------------------------------------

SHOTS = Path(__file__).resolve().parents[1] / "docs/tasks/M13-ui/tasks/screenshots"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _snapshots():
    """Load ``web/dev/build_snapshots.py`` by path.

    ``web/`` is served as static files, not installed as a package, so it cannot
    be imported by name. Loading the real module keeps ``render_page`` as the one
    source of truth for the page markup instead of duplicating it in the test.
    """
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "web" / "dev" / "build_snapshots.py"
    spec = importlib.util.spec_from_file_location("_l08_build_snapshots", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def browser():
    """A headless Chrome, entered once for the module.

    Skips -- never fails -- when Playwright or Chrome is unavailable, so the
    Python suite stays runnable without a browser. ``importorskip`` only converts
    ``ModuleNotFoundError`` into a skip, so a *broken* install (an ``ImportError``
    of another kind, e.g. an ABI mismatch) is caught explicitly here too
    (falsification finding P3: the earlier docstring claimed this but the code
    turned it into two errors).
    """
    try:
        import playwright.sync_api as playwright_api
    except ImportError as exc:
        pytest.skip(f"Playwright unavailable ({type(exc).__name__}: {exc})")
    with playwright_api.sync_playwright() as pw:
        try:
            launched = pw.chromium.launch(channel="chrome")
        except Exception as exc:  # noqa: BLE001 - missing browser must skip, not fail
            pytest.skip(f"headless Chrome unavailable: {exc}")
        try:
            yield launched
        finally:
            launched.close()


def _render_current_page(project_id: str, initial: str, tmp_dir: Path) -> Path:
    """A page built from the CURRENT assets + the REAL captured projections.

    The delivered snapshot HTML inlines a *copy* of ``app.js``, so asserting on
    those files would only ever test the copy that was baked in at generation
    time -- a mutation to ``web/app.js`` would not be seen (confirmed: mutation
    M7 was initially missed for exactly this reason). Rendering through
    ``render_page`` with freshly read assets closes that gap while still driving
    the renderer with real captured endpoint data.
    """
    snap = _snapshots()
    built = {}
    for panel_id in PANEL_IDS:
        path = SHOTS / "projections" / f"{project_id}-{panel_id}.json"
        projection = json.loads(path.read_text(encoding="utf-8"))
        projection["project_id"] = project_id
        built[panel_id] = projection
    css, js = snap.read_assets()
    html = snap.render_page(
        title=f"DOM assert · {project_id} · {initial}",
        subtitle=f"test-rendered · {project_id}",
        project_input=project_id,
        banner="test-rendered from current web/ assets.",
        footer="",
        css=css,
        js=js,
        payload={"initial": initial, "panels": built},
    )
    target = tmp_dir / f"dom-{project_id}-{initial}.html"
    target.write_text(html, encoding="utf-8")
    return target


def _observed(page, panel_id: str) -> dict[str, str | None]:
    return page.evaluate(
        """(panel) => {
          const tab = document.querySelector('.tab[data-panel="' + panel + '"]');
          const dot = tab ? tab.querySelector('.tab__dot') : null;
          const chip = document.querySelector('.panel__head > .chip');
          const cls = (node, prefix) => node
            ? (node.className.match(new RegExp(prefix + '--(\\\\w+)')) || [null, null])[1]
            : null;
          return {
            dotState: tab && tab.dataset.dotState ? tab.dataset.dotState : null,
            dotClass: cls(dot, 'tab__dot'),
            chipClass: cls(chip, 'chip'),
            chipWord: chip ? chip.textContent : null,
          };
        }""",
        panel_id,
    )


def test_rendered_tab_dots_match_the_projection_state(browser, tmp_path):
    """The negative assertion the reviewer asked for: a tab dot and the panel's
    own header chip can never disagree, because both are written from
    `projection.verification_state` -- and both are checked against the stored
    projection, so neither can drift on its own."""
    from autoresearch.web_api import PANEL_IDS

    projects = sorted(
        {p.name.rsplit("-", 1)[0] for p in (SHOTS / "projections").glob("*.json")}
    )
    assert projects, f"no projections under {SHOTS}/projections"
    checked = 0
    observed_states = set()
    for project_id in projects:
        for initial in PANEL_IDS:
            page = browser.new_page()
            try:
                page.goto(_render_current_page(project_id, initial, tmp_path).as_uri())
                page.wait_for_selector(".section")
                for panel_id in PANEL_IDS:
                    expected = json.loads(
                        (SHOTS / "projections" / f"{project_id}-{panel_id}.json").read_text(
                            encoding="utf-8"
                        )
                    )["verification_state"]
                    page.click(f'.tab[data-panel="{panel_id}"]')
                    page.wait_for_selector(".panel__head > .chip")
                    seen = _observed(page, panel_id)
                    # PRIMARY: the class actually applied to the rendered dot.
                    assert seen["dotClass"] == expected, (
                        f"{project_id}/{panel_id}: rendered dot class "
                        f"{seen['dotClass']!r} != projection {expected!r}"
                    )
                    # PRIMARY: the panel's own chip, written from the same value.
                    assert seen["chipClass"] == expected, (
                        f"{project_id}/{panel_id}: chip {seen['chipClass']!r} "
                        f"!= rendered dot class {seen['dotClass']!r} -- same-source "
                        "rule broken"
                    )
                    # SECONDARY: `data-dot-state` is an attribute the renderer
                    # writes itself, so on its own it is circular evidence and must
                    # not be the only thing asserted (falsification finding R6:
                    # asserting it alone passed under a dot-hardcoding mutation).
                    assert seen["dotState"] == expected, (
                        f"{project_id}/{panel_id}: data-dot-state {seen['dotState']!r} "
                        f"!= {expected!r} (renderer bookkeeping drifted from the class)"
                    )
                    observed_states.add(expected)
                    checked += 1
            finally:
                page.close()
    assert checked >= 36, f"expected at least 36 panel checks, got {checked}"
    assert {"unverified", "blocked"} <= observed_states, (
        f"the real data no longer exercises both non-verified states: {observed_states}"
    )


def test_delivered_snapshots_are_not_stale():
    """Shipped snapshots inline a copy of `app.js`/`styles.css`. If the source
    moves on without regenerating them, the delivered evidence describes a
    renderer that no longer exists -- a silent drift worth failing on.

    **Split-aware**: the rendered snapshots ship in a separate PR from the code
    that produces them (the code PR carries the renderer, the tests and the
    generator; the snapshots PR carries the regenerated artefacts). When the
    snapshots are absent this test has nothing to compare, so it skips **and
    says so** rather than passing silently -- an empty glob must never look
    like a green drift check.
    """
    css, js = _snapshots().read_assets()
    snapshots = sorted(SHOTS.glob("snapshot-*.html"))
    if not snapshots:
        pytest.skip(
            "no delivered snapshots in this tree -- they ship in the snapshots "
            "PR (see the M13-UI task package); this drift check only has "
            "meaning once web/dev/build_snapshots.py has been run"
        )
    stale = []
    for html in snapshots:
        text = html.read_text(encoding="utf-8")
        if js not in text or css not in text:
            stale.append(html.name)
    assert not stale, (
        "delivered snapshot(s) inline an out-of-date app.js/styles.css "
        f"(re-run web/dev/build_snapshots.py): {stale}"
    )


def test_rendered_fixture_covers_all_three_states_and_rejects_a_bad_one(browser, tmp_path):
    """`verified` is unreachable from real data in this environment, so the
    fixture is what proves the third dot is actually applied -- and that a
    malformed state gets no dot and is labelled INVALID-STATE."""
    snap = _snapshots()
    css, js = snap.read_assets()
    html = tmp_path / "fixture.html"
    html.write_text(
        snap.render_page(
            title="fixture",
            subtitle="synthetic",
            project_input="_rendering-fixture",
            banner=snap.FIXTURE_BANNER,
            footer=snap.FIXTURE_FOOTER,
            css=css,
            js=js,
            payload=snap.fixture_payloads(),
        ),
        encoding="utf-8",
    )
    page = browser.new_page()
    try:
        page.goto(html.as_uri())
        page.wait_for_selector(".section")
        for panel_id, expected in (
            ("project", "verified"),
            ("evidence", "unverified"),
            ("files", "blocked"),
            ("approval", None),
        ):
            seen = _observed(page, panel_id)
            assert seen["dotClass"] == expected, (panel_id, seen, expected)
        page.click('.tab[data-panel="approval"]')
        page.wait_for_selector(".panel__head > .chip")
        chip = _observed(page, "approval")
        assert chip["chipClass"] == "invalid"
        assert "INVALID-STATE" in chip["chipWord"]
        assert "VERIFIED" not in chip["chipWord"] and "UNVERIFIED" not in chip["chipWord"]
    finally:
        page.close()
