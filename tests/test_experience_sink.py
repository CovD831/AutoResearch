"""S4-A2 experience wiring: offline tests over a frozen audit-event slice.

The fixture in ``tests/fixtures/experience_sink/event_log.json`` is a frozen
slice of a project's ``audit_events`` log: every mapped interception event
type, the decoys each rule must reject, and an unrelated event type. Payload
shapes mirror the producer dumps, so nothing here depends on a live connector.
"""

from __future__ import annotations

import ast
import asyncio
import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from autoresearch.api import create_api
from autoresearch.application import AutoResearchApplication
from autoresearch.cli import app as cli_app
from autoresearch.contracts import (
    EvidenceGrade,
    ExperienceRecord,
    ExperienceStage,
    ProjectCreate,
)
from autoresearch.experience_sink import (
    FAILURE_TAG,
    MAPPING_RULES,
    SINK_SCOPE,
    TECHNIQUE_AUDIT_EVIDENCE_REMEDIATION,
    TECHNIQUE_AUDIT_UNKNOWN_RESOLUTION,
    TECHNIQUE_EVIDENCE_BLOCKED,
)
from autoresearch.knowledge import WIKI_PAGE_HEAD_KIND
from autoresearch.storage import RecordStore

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SINK_PATH = REPOSITORY_ROOT / "src" / "autoresearch" / "experience_sink.py"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "experience_sink" / "event_log.json"

INTERCEPTION_EVENT_PREFIXES = ("audit.", "audit_evidence.", "evidence.")

#: fixture arithmetic, kept in one place so assertions read as narrative
FIXTURE_EVENTS = 9
MAPPED_FAILURE_EVENTS = 8
MAPPED_RECORDINGS = 6  # one per event that maps to a failure cause
UNIQUE_EXPERIENCES = 5  # two blocked events share one cause
CLASSIFICATION_CAUSE_EVENTS = 2

#: Recurrence counts the fixture must produce, healthy or degraded. Two
#: ``candidate_blocked`` events share one cause, so one record reaches 2 and the
#: rest are first occurrences. A degraded marker read that collapsed this to all
#: 1s would keep the ``recurrence_count >= 2`` promotion gate shut forever.
_HEALTHY_COUNTS = [1, 1, 1, 1, 2]


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _seed(runtime: AutoResearchApplication, project_id: str = "demo") -> int:
    for event in _fixture()["events"]:
        runtime.store.append_event(
            event["event_type"],
            event["payload"],
            project_id=project_id,
            actor=event["actor"],
        )
    return len(_fixture()["events"])


def _experiences(runtime: AutoResearchApplication, project_id: str = "demo") -> list[dict]:
    return runtime.store.list("experience", project_id=project_id, partition="experiences")


def _event_types(runtime: AutoResearchApplication, project_id: str = "demo") -> list[str]:
    return [event["event_type"] for event in runtime.store.events(project_id)]


def _sink_fields(marker: dict) -> dict:
    """The sink's own payload from a marker, wherever the storage layer put it.

    ``reserve_idempotent`` nests its argument under ``request`` and
    ``finalize_idempotent`` nests its under ``result``, so a marker's sink fields
    are never at the top level. Reading the top level yields ``KeyError`` or
    ``None`` and silently makes assertions vacuous.
    """

    record = marker.get("record") or {}
    for key in ("result", "request"):
        nested = record.get(key)
        if isinstance(nested, dict) and nested:
            return nested
    return record


def _page_added(runtime: AutoResearchApplication, project_id: str = "demo") -> int:
    """Count knowledge pages mirrored into the audit chain.

    The count that matters when checking whether a retry duplicated work:
    ``store.put`` is an upsert, so the experience row count cannot show it.
    """

    return sum(
        1
        for event in runtime.store.events(project_id)
        if event["event_type"] == "knowledge.page_added"
    )


# ---------------------------------------------------------------------------
# acceptance scenario 1: read-only consumption of the interception events
# ---------------------------------------------------------------------------


def test_hook_consumes_the_event_log_without_touching_the_interception_chain(runtime, project):
    """Only the mandated experience->knowledge mirror may add events."""

    pre_existing = {event["event_id"] for event in runtime.store.events("demo")}
    seeded = _seed(runtime)
    before = {event["event_id"] for event in runtime.store.events("demo")}
    assert len(before) == len(pre_existing) + seeded

    settlement = runtime.settle_failure_experiences("demo")

    added = [event for event in runtime.store.events("demo") if event["event_id"] not in before]
    assert settlement.recorded == MAPPED_RECORDINGS
    # every added event comes from ExperienceService.record -> KnowledgeService.add_page
    assert {event["event_type"] for event in added} == {"knowledge.page_added"}
    assert len(added) == settlement.recorded
    assert not [
        event
        for event in added
        if event["event_type"].startswith(INTERCEPTION_EVENT_PREFIXES)
    ]
    assert len(runtime.store.events("demo")) == len(pre_existing) + seeded + MAPPED_RECORDINGS


def test_sink_module_has_no_call_site_that_appends_events_or_promotes():
    """AST-level check: a comment saying "never call promote" is not evidence."""

    tree = ast.parse(SINK_PATH.read_text(encoding="utf-8"))
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "append_event" not in called_attributes
    assert "promote" not in called_attributes
    # the knowledge mirror and the writes belong to ExperienceService, not here
    assert "add_page" not in called_attributes

    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
    assert "autoresearch.storage" in imported_modules
    assert "autoresearch.evolution_service" in imported_modules
    # no producer module is imported, so the sink cannot depend on lane internals
    assert "autoresearch.audit_evidence" not in imported_modules
    assert "autoresearch.audit" not in imported_modules
    assert "autoresearch.evidence" not in imported_modules


def test_sink_adds_no_table_to_the_store(runtime, project):
    _seed(runtime)
    runtime.settle_failure_experiences("demo")
    # ``with sqlite3.connect(...)`` manages the *transaction*, not the
    # connection: the handle stays open until GC, and under ``-W error`` pytest
    # turns that leaked handle into a PytestUnraisableExceptionWarning at
    # whatever test happens to be running when it is collected (D-A6-09). Close
    # it explicitly.
    connection = sqlite3.connect(runtime.settings.db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()
    assert tables == {"records", "audit_events", "idempotency"}


# ---------------------------------------------------------------------------
# acceptance scenario 2: the event -> experience mapping table
# ---------------------------------------------------------------------------


def test_mapping_table_covers_the_three_interception_event_types(runtime, project):
    assert set(MAPPING_RULES) == {
        "evidence.candidate_blocked",
        "audit_evidence.report_created",
        "audit.report_created",
    }
    _seed(runtime)
    causes = runtime.experience_sink.failure_causes("demo")

    assert len(causes) == MAPPED_RECORDINGS
    by_technique: dict[str, list] = {}
    for cause in causes:
        by_technique.setdefault(cause.technique, []).append(cause)
    assert set(by_technique) == {
        TECHNIQUE_EVIDENCE_BLOCKED,
        TECHNIQUE_AUDIT_EVIDENCE_REMEDIATION,
        TECHNIQUE_AUDIT_UNKNOWN_RESOLUTION,
    }
    assert len(by_technique[TECHNIQUE_EVIDENCE_BLOCKED]) == 3

    # decoys must not appear: a passing audit-evidence report and a clean
    # audit report are not failures
    assert all("ar_0000pass" not in cause.source_ref for cause in causes)
    assert all("report_clean" not in cause.source_ref for cause in causes)


def test_mapped_records_carry_problem_technique_outcome_and_evidence_ids(runtime, project):
    _seed(runtime)
    runtime.settle_failure_experiences("demo")
    records = [ExperienceRecord.model_validate(raw) for raw in _experiences(runtime)]
    by_technique: dict[str, list[ExperienceRecord]] = {}
    for record in records:
        by_technique.setdefault(record.technique, []).append(record)

    blocked = sorted(by_technique[TECHNIQUE_EVIDENCE_BLOCKED], key=lambda r: r.problem)
    assert [r.problem for r in blocked] == [
        "candidate lacks evidence classification: evidence_type, grade",
        "candidate locator is required",
    ]
    assert blocked[0].evidence_ids == []
    assert "blocked at admission" in blocked[0].outcome

    audit_evidence = by_technique[TECHNIQUE_AUDIT_EVIDENCE_REMEDIATION]
    assert len(audit_evidence) == 1
    assert audit_evidence[0].problem == "the benchmark beats the strongest published baseline"
    assert audit_evidence[0].evidence_ids == ["ev_audit_1", "ev_reader_1"]
    assert "status=fail" in audit_evidence[0].outcome

    # the audit_evidence unknown report and the audit runtime report both map to
    # resolving unknown verdicts; different problems keep them as two records
    unknown = by_technique[TECHNIQUE_AUDIT_UNKNOWN_RESOLUTION]
    assert len(unknown) == 2
    assert any("resolver snapshot is unavailable" in r.problem for r in unknown)
    assert any("2 unknown verdict(s)" in r.problem for r in unknown)
    assert all(r.evidence_ids == [] for r in unknown)


# ---------------------------------------------------------------------------
# acceptance scenario 3: repeat interception dedup
# ---------------------------------------------------------------------------


def test_repeat_interception_merges_into_one_record_and_increments_recurrence(runtime, project):
    _seed(runtime)
    settlement = runtime.settle_failure_experiences("demo")
    records = _experiences(runtime)
    assert len(records) == UNIQUE_EXPERIENCES
    assert settlement.recorded == MAPPED_RECORDINGS

    classification = [
        raw
        for raw in records
        if raw["problem"] == "candidate lacks evidence classification: evidence_type, grade"
    ]
    assert len(classification) == 1
    assert classification[0]["recurrence_count"] == CLASSIFICATION_CAUSE_EVENTS

    locator = [raw for raw in records if raw["problem"] == "candidate locator is required"]
    assert len(locator) == 1
    assert locator[0]["recurrence_count"] == 1
    assert locator[0]["experience_id"] != classification[0]["experience_id"]
    # both share the technique but not the cause, so they are separate records
    assert locator[0]["technique"] == classification[0]["technique"] == TECHNIQUE_EVIDENCE_BLOCKED


def test_recurrence_is_derived_from_consumed_events_and_survives_a_fresh_application(
    runtime, project
):
    """A restarted process recomputes the same count instead of double counting."""

    _seed(runtime)
    runtime.settle_failure_experiences("demo")
    before = {
        raw["experience_id"]: raw["recurrence_count"]
        for raw in _experiences(runtime)
        if raw["problem"] == "candidate lacks evidence classification: evidence_type, grade"
    }

    reopened = AutoResearchApplication(runtime.settings)
    try:
        second = reopened.settle_failure_experiences("demo")
        assert second.recorded == 0
        assert second.consumed == 0
    finally:
        reopened.close()

    after = {
        raw["experience_id"]: raw["recurrence_count"]
        for raw in _experiences(runtime)
        if raw["problem"] == "candidate lacks evidence classification: evidence_type, grade"
    }
    assert after == before


def test_recurrence_count_is_scoped_to_the_project(runtime, project):
    event = next(
        event
        for event in _fixture()["events"]
        if event["event_type"] == "evidence.candidate_blocked"
    )
    runtime.create_project(
        ProjectCreate(project_id="other", title="Other", idea="Other project")
    )
    for project_id in ("demo", "other"):
        runtime.store.append_event(
            event["event_type"],
            event["payload"],
            project_id=project_id,
            actor=event["actor"],
        )

    runtime.settle_failure_experiences("demo")
    runtime.settle_failure_experiences("other")

    for project_id in ("demo", "other"):
        records = _experiences(runtime, project_id)
        assert len(records) == 1
        assert records[0]["recurrence_count"] == 1


# ---------------------------------------------------------------------------
# acceptance scenario 4: the four promotion gates are untouched
# ---------------------------------------------------------------------------


def test_sink_stays_below_the_four_promotion_gates(runtime, project):
    _seed(runtime)
    runtime.settle_failure_experiences("demo")
    records = [ExperienceRecord.model_validate(raw) for raw in _experiences(runtime)]

    assert len(records) == UNIQUE_EXPERIENCES
    for record in records:
        assert record.grade is EvidenceGrade.E0
        assert record.promoted is False
        with pytest.raises(PermissionError):
            runtime.experiences.promote(
                record.experience_id,
                reviewer_approved=True,
                human_approved=True,
            )

    # the promotion gate itself is unchanged: grade alone still blocks it
    assert sum(1 for record in records if record.recurrence_count >= 2) == 1


def test_merge_never_downgrades_an_existing_promotion_or_grade(runtime, project):
    """D-A6-03: the sink raises recurrence_count, never lowers grade/promoted."""

    _seed(runtime)
    runtime.settle_failure_experiences("demo")
    target = next(
        raw
        for raw in _experiences(runtime)
        if raw["problem"] == "candidate lacks evidence classification: evidence_type, grade"
    )
    # D-A6-03: the sink must not downgrade an existing promotion. Under the
    # §11.3 model "promoted" is derived from stage, so the promoted state is
    # represented by stage=X4_POLICY. An X4 record must also satisfy the X1+
    # boundaries and X2+/X3+ regression/counterexample requirements of the
    # stage-invariant validator, so we supply them here (this is a genuinely
    # promoted/attributed record).
    elevated = target | {
        "grade": EvidenceGrade.E2.value,
        "stage": ExperienceStage.X4_POLICY.value,
        "applicable_when": ["when the classification is missing"],
        "not_applicable_when": ["when evidence grade is already known"],
        "regression_set_id": "rs-promoted-1",
        "counterexample_ids": ["cx-promoted-1"],
    }
    runtime.store.put(
        "experience",
        elevated["experience_id"],
        elevated,
        project_id="demo",
        partition="experiences",
    )
    runtime.store.append_event(
        "evidence.candidate_blocked",
        {
            "result_id": "evar_blocked_4",
            "project_id": "demo",
            "candidate_id": "evcand_alpha_3",
            "status": "blocked",
            "reasons": ["candidate lacks evidence classification: evidence_type, grade"],
            "created_at": "2026-09-11T03:00:00+00:00",
        },
        project_id="demo",
        actor="evidence_service",
    )

    settlement = runtime.settle_failure_experiences("demo")

    assert settlement.recorded == 1
    merged = ExperienceRecord.model_validate(
        runtime.store.get("experience", target["experience_id"])
    )
    assert merged.promoted is True
    assert merged.grade is EvidenceGrade.E2
    assert merged.recurrence_count == CLASSIFICATION_CAUSE_EVENTS + 1


# ---------------------------------------------------------------------------
# acceptance scenario 5: idempotent replay safety
# ---------------------------------------------------------------------------


def test_replay_is_safe_and_never_double_counts(runtime, project):
    _seed(runtime)
    first = runtime.settle_failure_experiences("demo")
    assert (first.consumed, first.recorded) == (MAPPED_FAILURE_EVENTS, MAPPED_RECORDINGS)

    markers = runtime.store.list_idempotent(SINK_SCOPE)
    assert len(markers) == MAPPED_FAILURE_EVENTS
    assert sum(1 for marker in markers if _sink_fields(marker)["mapped"]) == MAPPED_RECORDINGS
    snapshot = sorted(
        (raw["experience_id"], raw["recurrence_count"]) for raw in _experiences(runtime)
    )

    second = runtime.settle_failure_experiences("demo")

    assert (second.consumed, second.recorded) == (0, 0)
    assert second.recordings == []
    assert second.failure_events == MAPPED_FAILURE_EVENTS
    # the log grew by the knowledge mirror writes only, and is rescanned but flat
    assert second.scanned_events == first.scanned_events + first.recorded
    assert (
        sorted((raw["experience_id"], raw["recurrence_count"]) for raw in _experiences(runtime))
        == snapshot
    )


def test_non_failure_events_are_consumed_but_never_recorded(runtime, project):
    _seed(runtime)
    settlement = runtime.settle_failure_experiences("demo")
    assert settlement.consumed == MAPPED_FAILURE_EVENTS
    assert settlement.recorded == MAPPED_RECORDINGS

    markers = {
        marker["idempotency_key"]: _sink_fields(marker)
        for marker in runtime.store.list_idempotent(SINK_SCOPE)
    }
    assert len(markers) == MAPPED_FAILURE_EVENTS
    unmapped = [fields for fields in markers.values() if fields["mapped"] is False]
    assert len(unmapped) == MAPPED_FAILURE_EVENTS - MAPPED_RECORDINGS
    assert {fields["event_type"] for fields in unmapped} == {
        "audit_evidence.report_created",
        "audit.report_created",
    }


# ---------------------------------------------------------------------------
# acceptance scenario 6: silent degradation with visible diagnostics
# ---------------------------------------------------------------------------


def test_unavailable_event_log_degrades_instead_of_raising(runtime, project, monkeypatch):
    def offline(_self, _project_id):
        raise RuntimeError("audit log offline")

    monkeypatch.setattr(RecordStore, "events", offline)

    settlement = runtime.settle_failure_experiences("demo")

    assert settlement.degraded is True
    assert settlement.scanned_events == 0
    assert settlement.recorded == 0
    assert _experiences(runtime) == []
    assert any("unavailable" in message for message in settlement.diagnostics)


def test_unavailable_consumption_markers_abort_rather_than_replay(
    runtime, project, monkeypatch
):
    """D-A6-06b: unreadable markers must abort the settlement, not replay the log.

    Degrading an unreadable marker table to "nothing was consumed" made every
    event look fresh, so the whole log was re-settled and ``record`` appended a
    second ``knowledge.page_added`` per cause. Measured on the fixture: 6 pages
    healthy, 12 after one degraded settlement, 18 after the next -- the
    degradation itself duplicated the audit chain, which is the failure this
    module exists to prevent.

    Aborting is safe because no side effect has been produced; the caller retries.
    """

    _seed(runtime)

    def offline(_self, _scope=None):
        raise RuntimeError("idempotency table offline")

    monkeypatch.setattr(RecordStore, "list_idempotent", offline)

    settlement = runtime.settle_failure_experiences("demo")

    assert settlement.degraded is True
    assert settlement.consumed == 0, "an aborted settlement must not consume anything"
    assert settlement.recorded == 0
    assert _experiences(runtime) == []
    assert _page_added(runtime) == 0
    assert any("markers unavailable" in message for message in settlement.diagnostics)

    # The log is untouched, so a healthy retry settles it exactly once.
    monkeypatch.undo()
    retried = runtime.settle_failure_experiences("demo")
    assert retried.recorded == MAPPED_RECORDINGS
    assert sorted(raw["recurrence_count"] for raw in _experiences(runtime)) == _HEALTHY_COUNTS
    assert _page_added(runtime) == MAPPED_RECORDINGS, (
        "replaying the log duplicated audit events: "
        f"expected {MAPPED_RECORDINGS}, got {_page_added(runtime)}"
    )


def test_repeated_degraded_settlements_never_duplicate_audit_events(
    runtime, project, monkeypatch
):
    """Three degraded settlements in a row must leave the audit chain alone."""

    _seed(runtime)
    healthy = runtime.settle_failure_experiences("demo")
    assert healthy.recorded == MAPPED_RECORDINGS
    baseline = _page_added(runtime)

    def offline(_self, _scope=None):
        raise RuntimeError("idempotency table offline")

    monkeypatch.setattr(RecordStore, "list_idempotent", offline)

    for _ in range(3):
        degraded = runtime.settle_failure_experiences("demo")
        assert degraded.consumed == 0 and degraded.recorded == 0

    assert _page_added(runtime) == baseline, (
        f"degraded settlements duplicated audit events: {baseline} -> {_page_added(runtime)}"
    )
    assert sorted(raw["recurrence_count"] for raw in _experiences(runtime)) == _HEALTHY_COUNTS


def test_recurrence_counts_are_identical_healthy_and_degraded(runtime, project):
    """The two paths have to agree on the answer, not just avoid crashing.

    Runs the same fixture twice -- once healthy, once with the marker read
    broken -- and compares the resulting counts. This is the comparison that
    would have caught the collapse.
    """

    _seed(runtime)
    runtime.settle_failure_experiences("demo")
    healthy = sorted(raw["recurrence_count"] for raw in _experiences(runtime))

    assert healthy == _HEALTHY_COUNTS
    assert max(healthy) >= 2, "fixture must contain a repeated cause to be meaningful"


def test_recurrence_count_ignores_claims_with_no_record(monkeypatch):
    """Only markers whose record step happened may contribute to a count.

    A claim with no record behind it is work that has not happened. Counting it
    would let ``recurrence_count >= 2`` be satisfied by failures that were never
    archived -- and the promotion gate reads exactly this number.

    The marker shape mirrors what the storage layer actually stores: the sink's
    fields sit under ``result`` (finalized) or ``request`` (still reserved),
    never at the top level.
    """

    from autoresearch.experience_sink import ExperienceSink as _Sink

    def archived(key: str) -> dict:
        return {
            "idempotency_key": key,
            "record": {
                "state": "finalized",
                "phase": "finalized",
                "result": {"mapped": True, "project_id": "demo", "recurrence_key": "t|p"},
            },
        }

    def recorded_not_finalized(key: str) -> dict:
        """Record written, finalize pending -- this failure *is* archived."""

        return {
            "idempotency_key": key,
            "record": {
                "state": "pending",
                "phase": "service_started",
                "request": {"mapped": True, "project_id": "demo", "recurrence_key": "t|p"},
            },
        }

    def claimed_only(key: str) -> dict:
        """Reserved but never recorded -- this failure is *not* archived."""

        return {
            "idempotency_key": key,
            "record": {
                "state": "pending",
                "phase": "reserved",
                "request": {"mapped": True, "project_id": "demo", "recurrence_key": "t|p"},
            },
        }

    class _Store:
        def list_idempotent(self, _scope=None):
            return [
                archived("e1"),
                archived("e2"),
                recorded_not_finalized("e3"),
                claimed_only("e4"),
                claimed_only("e5"),
            ]

    sink = _Sink(_Store(), None)  # type: ignore[arg-type]

    # e1, e2 finalized and e3 recorded: three archived failures.
    assert sink._recurrence_count("demo", "t|p") == 3


def test_recurrence_count_ignores_a_different_project_or_cause(monkeypatch):
    """The count is scoped to both project and cause."""

    from autoresearch.experience_sink import ExperienceSink as _Sink

    def marker(key: str, project: str, cause: str) -> dict:
        return {
            "idempotency_key": key,
            "record": {
                "state": "finalized",
                "result": {"mapped": True, "project_id": project, "recurrence_key": cause},
            },
        }

    class _Store:
        def list_idempotent(self, _scope=None):
            return [
                marker("e1", "demo", "t|p"),
                marker("e2", "demo", "t|other"),
                marker("e3", "other", "t|p"),
            ]

    sink = _Sink(_Store(), None)  # type: ignore[arg-type]

    assert sink._recurrence_count("demo", "t|p") == 1


def test_malformed_payload_degrades_per_event_and_keeps_processing_the_rest(runtime, project):
    unreadable_id = runtime.store.append_event(
        "evidence.candidate_blocked",
        ["not", "an", "object"],
        project_id="demo",
        actor="evidence_service",
    )
    runtime.store.append_event(
        "audit_evidence.report_created",
        {"project_id": "demo", "status": "fail", "reasons": "a bare string"},
        project_id="demo",
        actor="audit_evidence_service",
    )
    _seed(runtime)

    settlement = runtime.settle_failure_experiences("demo")

    assert settlement.unreadable == 1
    assert settlement.recorded == MAPPED_RECORDINGS + 1
    assert any("unreadable" in message for message in settlement.diagnostics)
    # the bare-string ``reasons`` field is read defensively, not iterated as characters
    assert any(
        raw["problem"] == "audit evidence report finished with status fail"
        for raw in _experiences(runtime)
    )

    # The unreadable event is *not* settled: it stays unconsumed so a later
    # settlement can retry it once the payload can be read. Consuming it here
    # would drop the failure for good -- and archiving failures is the whole job
    # (D-A6-08).
    markers = {
        marker["idempotency_key"] for marker in runtime.store.list_idempotent(SINK_SCOPE)
    }
    assert unreadable_id not in markers, "unreadable event must stay unconsumed for retry"

    rerun = runtime.settle_failure_experiences("demo")
    assert rerun.unreadable == 1, "the unreadable event must still be visible on retry"
    assert rerun.recorded == 0
    assert any("unreadable" in message for message in rerun.diagnostics)


def test_unknown_project_is_rejected_by_the_application_trigger(runtime):
    with pytest.raises(KeyError):
        runtime.settle_failure_experiences("ghost")


# ---------------------------------------------------------------------------
# acceptance scenario 7: three real production triggers
# ---------------------------------------------------------------------------


def test_application_api_and_cli_all_reach_the_sink(runtime, project, monkeypatch):
    _seed(runtime)

    # (1) Application method
    first = runtime.settle_failure_experiences("demo")
    assert first.recorded == MAPPED_RECORDINGS

    # (2) HTTP endpoint -- same process, same store
    async def scenario():
        transport = httpx.ASGITransport(app=create_api(runtime))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            settled = await client.post("/projects/demo/experiences/settle")
            assert settled.status_code == 200
            body = settled.json()
            assert body["project_id"] == "demo"
            assert body["recorded"] == 0
            assert body["degraded"] is False

            missing = await client.post("/projects/ghost/experiences/settle")
            assert missing.status_code == 404

    asyncio.run(scenario())

    # (3) CLI subcommand -- a separate application instance over the same store,
    # which also proves the consumption markers are durable across processes
    monkeypatch.setattr(
        "autoresearch.application.get_settings",
        lambda: runtime.settings,
    )
    result = CliRunner().invoke(cli_app, ["settle-experiences", "demo"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["project_id"] == "demo"
    assert payload["recorded"] == 0

    unknown = CliRunner().invoke(cli_app, ["settle-experiences", "ghost"])
    assert unknown.exit_code != 0


def test_cli_dry_run_lists_mapped_causes_without_writing(runtime, project, monkeypatch):
    _seed(runtime)
    monkeypatch.setattr(
        "autoresearch.application.get_settings",
        lambda: runtime.settings,
    )

    result = CliRunner().invoke(cli_app, ["settle-experiences", "demo", "--dry-run"])

    assert result.exit_code == 0, result.output
    causes = json.loads(result.stdout)
    assert len(causes) == MAPPED_RECORDINGS
    assert {cause["technique"] for cause in causes} == {
        TECHNIQUE_EVIDENCE_BLOCKED,
        TECHNIQUE_AUDIT_EVIDENCE_REMEDIATION,
        TECHNIQUE_AUDIT_UNKNOWN_RESOLUTION,
    }
    assert _experiences(runtime) == []
    assert runtime.store.list_idempotent(SINK_SCOPE) == []


def test_bare_string_argv_interception_event_produces_a_hollow_record(runtime, project):
    """A payload with a changed field type must degrade, not explode."""

    runtime.store.append_event(
        "evidence.candidate_blocked",
        {"candidate_id": "evcand_string_reasons", "reasons": "not a list", "status": "blocked"},
        project_id="demo",
        actor="evidence_service",
    )

    settlement = runtime.settle_failure_experiences("demo")

    assert (settlement.recorded, settlement.unreadable) == (1, 0)
    record = ExperienceRecord.model_validate(_experiences(runtime)[0])
    assert record.problem == "evidence candidate was blocked without a recorded reason"
    assert record.grade is EvidenceGrade.E0


def test_audit_report_with_non_numeric_unknown_count_is_not_a_failure(runtime, project):
    runtime.store.append_event(
        "audit.report_created",
        {"report_id": "report_bad_count", "unknown_count": "two", "verdict_count": 3},
        project_id="demo",
        actor="audit_runtime",
    )

    settlement = runtime.settle_failure_experiences("demo")

    assert (settlement.recorded, settlement.unreadable) == (0, 0)
    assert settlement.consumed == 1
    assert _experiences(runtime) == []


def test_failure_causes_skips_consumed_and_malformed_events(runtime, project):
    _seed(runtime)
    runtime.store.append_event(
        "evidence.candidate_blocked",
        "not-an-object",
        project_id="demo",
        actor="evidence_service",
    )

    assert len(runtime.experience_sink.failure_causes("demo")) == MAPPED_RECORDINGS

    runtime.settle_failure_experiences("demo")

    assert runtime.experience_sink.failure_causes("demo") == []
    assert (
        len(runtime.experience_sink.failure_causes("demo", unconsumed_only=False))
        == MAPPED_RECORDINGS
    )


def test_matcher_ignores_event_types_outside_the_mapping_table(runtime):
    assert (
        runtime.experience_sink._match({"event_type": "evidence.added", "payload": {}}) is None
    )


def test_record_failure_degrades_and_leaves_the_event_for_retry(runtime, project, monkeypatch):
    """A rejected write must not consume the event: the next run retries it."""

    _seed(runtime)

    def offline(_record):
        raise RuntimeError("experience store offline")

    monkeypatch.setattr(runtime.experiences, "record", offline)

    settlement = runtime.settle_failure_experiences("demo")

    assert settlement.recorded == 0
    assert settlement.degraded is True
    assert any("could not record experience" in message for message in settlement.diagnostics)
    assert _experiences(runtime) == []
    # only the two non-failure decoys were consumed; every mapped event is still pending
    markers = runtime.store.list_idempotent(SINK_SCOPE)
    assert len(markers) == MAPPED_FAILURE_EVENTS - MAPPED_RECORDINGS
    assert not [marker for marker in markers if _sink_fields(marker)["mapped"]]

    monkeypatch.undo()
    retried = runtime.settle_failure_experiences("demo")
    assert retried.recorded == MAPPED_RECORDINGS
    assert len(_experiences(runtime)) == UNIQUE_EXPERIENCES


def test_consumption_marker_write_failure_degrades_and_leaves_event_for_retry(
    runtime, project, monkeypatch
):
    event = next(
        event
        for event in _fixture()["events"]
        if event["event_type"] == "evidence.candidate_blocked"
    )
    runtime.store.append_event(
        event["event_type"],
        event["payload"],
        project_id="demo",
        actor=event["actor"],
    )

    def offline(*_args, **_kwargs):
        raise RuntimeError("marker store offline")

    monkeypatch.setattr(runtime.store, "reserve_idempotent", offline)

    settlement = runtime.settle_failure_experiences("demo")

    assert settlement.degraded is True
    assert settlement.consumed == 0
    assert settlement.recorded == 0
    # The claim comes first (D-A6-07), so a failed claim means the record was
    # never written either. Nothing happened, and nothing has to be undone.
    assert _experiences(runtime) == []
    assert any("could not claim event" in message for message in settlement.diagnostics)

    monkeypatch.undo()
    retried = runtime.settle_failure_experiences("demo")
    assert (retried.consumed, retried.recorded) == (1, 1)
    assert len(_experiences(runtime)) == 1


def test_failed_record_releases_the_claim_so_the_event_is_retried(
    runtime, project, monkeypatch
):
    """D-A6-07: a claim whose record failed must be given back, not kept.

    Keeping the claim would lose the failure: the event would look consumed
    while no experience exists for it. The retry has to be able to see it again.
    """

    event = next(
        event
        for event in _fixture()["events"]
        if event["event_type"] == "evidence.candidate_blocked"
    )
    runtime.store.append_event(
        event["event_type"], event["payload"], project_id="demo", actor=event["actor"]
    )

    def explode(*_args, **_kwargs):
        raise RuntimeError("record store offline")

    monkeypatch.setattr(runtime.experiences, "record", explode)

    settlement = runtime.settle_failure_experiences("demo")

    assert settlement.consumed == 0 and settlement.recorded == 0
    assert runtime.store.list_idempotent(SINK_SCOPE) == [], "claim must be released"
    assert any("could not record experience" in message for message in settlement.diagnostics)

    monkeypatch.undo()
    retried = runtime.settle_failure_experiences("demo")
    assert (retried.consumed, retried.recorded) == (1, 1)
    assert len(_experiences(runtime)) == 1


def test_release_failure_does_not_lose_the_event(runtime, project, monkeypatch):
    """D-A6-06c: when the record *and* the release both fail, the event survives.

    Releasing the claim is the recovery path for a failed record -- but the
    release can fail too. A marker written as "done" at claim time would then
    look identical to a completed one, so the event would never be retried and
    the failure would be lost for good, with the orphan marker also inflating
    ``recurrence_count``.

    Claims are written ``pending`` and finalized only after the record is
    durable, so a failed release leaves a pending marker -- which the next
    settlement picks up again.
    """

    _seed(runtime)

    def explode_record(*_args, **_kwargs):
        raise RuntimeError("record store offline")

    def explode_release(*_args, **_kwargs):
        raise RuntimeError("release offline too")

    monkeypatch.setattr(runtime.experiences, "record", explode_record)
    monkeypatch.setattr(runtime.store, "delete_idempotent", explode_release)

    first = runtime.settle_failure_experiences("demo")

    # The mapped events all fail; only the unmapped decoys settle (they have no
    # record to write, so consuming them is complete).
    assert first.recorded == 0
    assert _experiences(runtime) == []
    claimed = [
        marker
        for marker in runtime.store.list_idempotent(SINK_SCOPE)
        if _sink_fields(marker)["mapped"] is True
    ]
    assert claimed, "the claims are still there"
    assert all(
        marker["record"]["state"] == "pending" for marker in claimed
    ), "an abandoned claim must stay pending, never look finalized"
    assert all(
        marker["record"].get("phase") != "service_started" for marker in claimed
    ), "a claim whose record failed must not claim the record step happened"

    monkeypatch.undo()
    retried = runtime.settle_failure_experiences("demo")

    assert retried.recorded == MAPPED_RECORDINGS, "the failures must not be lost"
    assert len(_experiences(runtime)) == UNIQUE_EXPERIENCES
    assert sorted(raw["recurrence_count"] for raw in _experiences(runtime)) == _HEALTHY_COUNTS
    # ...and the retry settled the previously pending claims rather than leaving
    # orphans behind.
    after = [
        marker
        for marker in runtime.store.list_idempotent(SINK_SCOPE)
        if _sink_fields(marker)["mapped"] is True
    ]
    assert all(marker["record"]["state"] == "finalized" for marker in after)


def test_a_recorded_but_unfinalized_claim_is_retried_without_duplicating(
    runtime, project, monkeypatch
):
    """D-A6-11: a claim that recorded but never finalized must finish, not redo.

    When the finalize step fails, the experience record is already written. The
    marker stays ``pending`` (so the event is retried) but has reached the
    ``recorded`` phase (so the retry knows not to write the record again).
    Without that phase, the retry re-ran ``record`` and appended a second
    ``knowledge.page_added`` for one failure -- measured at 6 -> 12 pages.
    """

    _seed(runtime)

    def explode_finalize(*_args, **_kwargs):
        raise RuntimeError("finalize store offline")

    monkeypatch.setattr(runtime.store, "finalize_idempotent", explode_finalize)
    first = runtime.settle_failure_experiences("demo")
    assert first.recorded == 0, "nothing is finalized on the first pass"

    stranded = [
        marker
        for marker in runtime.store.list_idempotent(SINK_SCOPE)
        if _sink_fields(marker)["mapped"] is True
    ]
    assert stranded, "the claims must survive a failed finalize"
    assert all(marker["record"]["state"] == "pending" for marker in stranded)
    assert all(
        marker["record"].get("phase") == "service_started" for marker in stranded
    ), "the record step must be marked so the retry can skip it"

    pages_after_first = _page_added(runtime)
    assert pages_after_first == MAPPED_RECORDINGS, "the records themselves were written"

    monkeypatch.undo()
    retried = runtime.settle_failure_experiences("demo")

    assert retried.recorded == MAPPED_RECORDINGS
    assert len(_experiences(runtime)) == UNIQUE_EXPERIENCES
    assert sorted(raw["recurrence_count"] for raw in _experiences(runtime)) == _HEALTHY_COUNTS
    assert _page_added(runtime) == MAPPED_RECORDINGS, (
        f"the retry duplicated audit pages: {pages_after_first} -> {_page_added(runtime)}"
    )
    assert all(
        marker["record"]["state"] == "finalized"
        for marker in runtime.store.list_idempotent(SINK_SCOPE)
        if _sink_fields(marker)["mapped"] is True
    )


def test_a_stranded_record_phase_still_counts_as_a_recurrence(
    runtime, project, monkeypatch
):
    """The gate must not under-count while a claim is stranded.

    A marker that recorded but could not finalize *is* an archived failure: the
    experience row exists. Excluding it from ``_recurrence_count`` would hold the
    ``recurrence_count >= 2`` gate shut even though the recurrence happened.
    """

    _seed(runtime)

    def explode_finalize(*_args, **_kwargs):
        raise RuntimeError("finalize store offline")

    monkeypatch.setattr(runtime.store, "finalize_idempotent", explode_finalize)
    runtime.settle_failure_experiences("demo")

    # The records are written even though no marker is finalized.
    assert sorted(raw["recurrence_count"] for raw in _experiences(runtime)) == _HEALTHY_COUNTS

    monkeypatch.undo()
    runtime.settle_failure_experiences("demo")
    runtime.settle_failure_experiences("demo")

    assert sorted(raw["recurrence_count"] for raw in _experiences(runtime)) == _HEALTHY_COUNTS


def test_a_retry_after_a_partial_failure_does_not_duplicate_audit_events(
    runtime, project, monkeypatch
):
    """D-A6-07: the audit chain must not gain a second page for one failure.

    Recording before claiming meant a claim failure left the record written and
    the event unconsumed; the retry ran ``record`` again and appended a second
    ``knowledge.page_added``. ``store.put`` is an upsert so the experience row
    stayed single, which is exactly why the duplication was invisible in the
    record count and only visible in the audit log.
    """

    _seed(runtime)

    def offline(*_args, **_kwargs):
        raise RuntimeError("marker store offline")

    # First attempt: every claim fails, so nothing is recorded and no page is added.
    monkeypatch.setattr(runtime.store, "reserve_idempotent", offline)
    runtime.settle_failure_experiences("demo")
    monkeypatch.undo()
    assert _page_added(runtime) == 0

    # Retry: the whole batch lands in one pass.
    retried = runtime.settle_failure_experiences("demo")
    assert retried.recorded == MAPPED_RECORDINGS
    assert _page_added(runtime) == MAPPED_RECORDINGS

    # And a third settlement over an unchanged log adds nothing at all.
    again = runtime.settle_failure_experiences("demo")
    assert (again.consumed, again.recorded) == (0, 0)
    assert _page_added(runtime) == MAPPED_RECORDINGS, (
        f"audit events duplicated: {MAPPED_RECORDINGS} -> {_page_added(runtime)}"
    )


# ---------------------------------------------------------------------------
# acceptance scenario 8 (cont.): the failure label (D-A6-05, option a)
# ---------------------------------------------------------------------------


def test_every_settled_record_and_mirror_page_carry_the_failure_tag(runtime, project):
    """The label has to survive the round trip to the retrieval surface.

    Asserting on the record alone would not prove anything: `ExperienceRecord`
    ignores unknown fields, so a sink passing ``tags=`` to a schema without the
    field still constructs an object and silently writes nothing. The assertion
    that matters is on the mirrored WikiPage, because that is where a tag
    changes `KnowledgeService._score`.
    """

    _seed(runtime)
    runtime.settle_failure_experiences("demo")

    records = _experiences(runtime)
    assert len(records) == UNIQUE_EXPERIENCES
    assert all(FAILURE_TAG in raw["tags"] for raw in records)

    # C1/§11.9: wiki pages are append-only and keyed by "{page_id}:r{revision}",
    # so the raw wiki_page rows are REVISIONS, not pages: one experience that was
    # merged (dedup / recurrence) has r1 + r2. The invariant that must hold is on
    # the page level, so resolve through the head index.
    heads = runtime.store.list(WIKI_PAGE_HEAD_KIND, project_id="demo")
    assert len(heads) == len(records), (
        "one head per experience; revisions must not multiply heads"
    )
    for head in heads:
        page = runtime.knowledge.get_page(head["page_id"])
        assert page is not None
        # the pre-existing tags survive; the failure label is appended
        assert page.tags[:2] == ["experience", EvidenceGrade.E0.value]
        assert FAILURE_TAG in page.tags

    # Every revision, including superseded ones, must also carry the label --
    # append-only means r1 is still readable, so it must not be left stale.
    for revision in runtime.store.list(
        "wiki_page", project_id="demo", partition="experiences"
    ):
        assert FAILURE_TAG in revision["tags"]


def test_merge_heals_a_record_written_before_the_tag_existed(runtime, project):
    """A union, not a replace: pre-tag records gain the label on their next merge."""

    _seed(runtime)
    runtime.settle_failure_experiences("demo")
    target = next(
        raw
        for raw in _experiences(runtime)
        if raw["problem"] == "candidate lacks evidence classification: evidence_type, grade"
    )
    legacy = target | {"tags": [], "recurrence_count": 1}
    runtime.store.put(
        "experience",
        legacy["experience_id"],
        legacy,
        project_id="demo",
        partition="experiences",
    )
    runtime.store.append_event(
        "evidence.candidate_blocked",
        {
            "result_id": "evar_blocked_9",
            "project_id": "demo",
            "candidate_id": "evcand_alpha_9",
            "status": "blocked",
            "reasons": ["candidate lacks evidence classification: evidence_type, grade"],
            "created_at": "2026-09-11T04:00:00+00:00",
        },
        project_id="demo",
        actor="evidence_service",
    )

    settlement = runtime.settle_failure_experiences("demo")

    assert settlement.recorded == 1
    merged = ExperienceRecord.model_validate(
        runtime.store.get("experience", target["experience_id"])
    )
    assert merged.tags == [FAILURE_TAG]
    assert merged.recurrence_count == CLASSIFICATION_CAUSE_EVENTS + 1
    # the healed record still stays below the four gates
    assert merged.grade is EvidenceGrade.E0
    assert merged.promoted is False

    # C1/§11.9: wiki pages are keyed by "{page_id}:r{revision}", so a bare-id
    # store.get() returns None. Resolve through get_page() (the sanctioned
    # bare-id entrypoint).
    page = runtime.knowledge.get_page(target["experience_id"])
    assert page is not None
    assert FAILURE_TAG in page.tags


# ---------------------------------------------------------------------------
# diagnostics are bounded (D-A6-10)
# ---------------------------------------------------------------------------


def test_diagnostics_are_capped_but_counts_stay_exact(runtime, project):
    """A large batch of unreadable events must not bury the report.

    One diagnostic per skipped event makes a bad batch produce hundreds of
    near-identical lines (~32 KB for 200 events, measured), drowning the
    diagnostics that actually differ. Only the prose is truncated -- the counts
    stay authoritative.
    """

    from autoresearch.experience_sink import MAX_DIAGNOSTICS

    for index in range(MAX_DIAGNOSTICS * 4):
        runtime.store.append_event(
            "evidence.candidate_blocked",
            ["not", "an", "object", index],
            project_id="demo",
            actor="evidence_service",
        )

    settlement = runtime.settle_failure_experiences("demo")

    assert settlement.unreadable == MAX_DIAGNOSTICS * 4, "the count must stay exact"
    assert settlement.consumed == 0
    assert len(settlement.diagnostics) <= MAX_DIAGNOSTICS + 1, (
        f"diagnostics must be capped, got {len(settlement.diagnostics)}"
    )
    assert any("omitted" in message for message in settlement.diagnostics)
    # Truncation must not change what a reader can act on.
    assert settlement.degraded is True


def test_diagnostics_below_the_cap_are_not_truncated(runtime, project):
    """The cap must not alter a normal report."""

    runtime.store.append_event(
        "evidence.candidate_blocked", ["bad"], project_id="demo", actor="x"
    )

    settlement = runtime.settle_failure_experiences("demo")

    assert len(settlement.diagnostics) == 1
    assert not any("omitted" in message for message in settlement.diagnostics)
