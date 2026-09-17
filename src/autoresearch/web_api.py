"""L-08 / M13: read-only panel boundary and the K14 ``PanelProjection`` contract.

Scope
-----
This module is the **only** new backend surface for the M13 panels. It never
mutates ``src/autoresearch`` state: every read goes through the same service
accessors that ``api.py``'s 24 endpoints already use, and every write the panels
perform is delegated to an existing endpoint (see ``web/app.js``).

Why a projection layer at all
-----------------------------
M13-04 states: *the panel must never present unfinished work as finished*. A
panel that renders raw payloads cannot honour that, because "the field is empty"
and "we could not read the field" look identical once serialised. ``K14``
introduces ``PanelProjection`` so that **every section carries a verification
state**, and ``K14-3`` forces the unverified/blocked cases to say *why*.

Source-of-truth resolution chain (measured, not assumed)
--------------------------------------------------------
Only two GET endpoints describe a project's research state, and neither links to
the other:

* ``GET /projects/{project_id}`` -> the project record
  ``{project_id, title, idea, path, status}``. **It carries no ``run_id``.**
* ``GET /runs/{run_id}`` -> ``{run_id, project_id, status, state, interrupts}``;
  ``state`` is the ``ResearchState`` (lifecycle, evidence ids, blockers...).

There is no endpoint that lists a project's runs, so the run is resolved from
the audit log: the newest ``run.started`` event payload carries ``run_id``.
That hop is recorded in ``resolve_run_id`` and surfaces in the panel as the
``run_resolution`` fact, so a reader can see *how* the panel found the run.

Gate decisions and review verdicts are likewise not exposed by a dedicated
endpoint; the ``gate.evaluated`` audit event payload **is** the ``GateDecision``
(``gates.py`` appends the decision object itself), so the Gate sections are
resolvable and therefore `verified` — they are not permanently "unknown".

Contract
--------
``K14`` (``04-l2-contracts.md``) defines ``panel_id`` / ``sections`` /
``verification_state`` with ``PanelSection = title / refs / verified /
unknown_reason``. Two additive fields are required to satisfy the contract's own
invariants and are registered in the package L3 (§4) as **D-L08-01/D-L08-02**:

* ``PanelSection.verification_state`` — K14-1 says *every section must be
  marked*. ``verified: bool`` cannot express that, because ``unverified`` and
  ``blocked`` are both ``verified=False``; without the tri-state the M13-04
  requirement that the two be distinguishable is unenforceable in data.
* ``PanelSection.facts`` — M13-04/05/07 require the panel to *display* 阶段,
  Gate status, evidence coverage and 风险 level. Those are bounded scalars, not
  free text. ``refs`` must stay a pure identifier channel (K14-2), so a second,
  strictly bounded channel is needed.

Content discipline (K14-2, strong reading)
------------------------------------------
``refs`` and ``facts`` never carry prose. Evidence ``claim``/``title``, wiki
``body``, manuscript text, gate ``reasons``, review ``findings`` and the
approval ``message`` stay in their own stores; the panel carries the *reference*
that resolves to them. ``_FACT_VALUE_MAX`` bounds every fact value, and
``tests/test_web_panels.py`` asserts mechanically that no evidence claim or
title reaches the projection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VerificationState = Literal["verified", "unverified", "blocked"]

PANEL_IDS: tuple[str, ...] = ("project", "evidence", "files", "approval")

#: K14-2: a ref is an opaque identifier. Prose (spaces, sentence punctuation)
#: never matches, so a content copy cannot be smuggled through ``refs``.
REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:+=-]{0,119}$")

#: Bounded scalar channel. 200 chars fits an enum value, an id, a count or a
#: compact histogram -- not a paragraph.
FACT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
FACT_VALUE_MAX = 200

# --- audit event types this module consumes (measured via append_event sites) ---
GATE_EVENT = "gate.evaluated"
RUN_STARTED_EVENT = "run.started"
EVIDENCE_INVALIDATED_EVENT = "evidence.invalidated"
AUDIT_REPORT_EVENT = "audit.report_created"
HANDOFF_ISSUED_EVENT = "handoff.issued"
HANDOFF_ACCEPTED_EVENT = "handoff.accepted"

#: ``graph.py`` emits exactly this interrupt when a release waits on a human.
APPROVAL_INTERRUPT_TYPE = "human_release_approval"
#: The gate operation used by both the approve and the reject branch of that interrupt.
RELEASE_OPERATION = "external_manuscript_release"

BLOCKING_RUN_STATUSES = frozenset({"blocked", "failed", "interrupted"})
BLOCKING_LIFECYCLE_STATES = frozenset(
    {"waiting_evidence", "waiting_human", "rejected", "failed"}
)

#: Reason strings for the "we could not read the source" case. Kept as constants
#: so tests can assert on them instead of on prose.
UNKNOWN_ENDPOINT_UNAVAILABLE = "endpoint payload not available to the panel"
UNKNOWN_NO_RUN = (
    "no run discovered for this project: GET /projects/{id} carries no run_id "
    "and the audit log has no run.started event"
)


# ---------------------------------------------------------------------------
# K14 types
# ---------------------------------------------------------------------------


class PanelSection(BaseModel):
    """One labelled block of a panel.

    ``verified`` is the K14 field; ``verification_state`` (D-L08-01) is the
    tri-state that K14-1 requires per section and is validated to agree with it.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    refs: list[str] = Field(default_factory=list)
    verified: bool
    unknown_reason: str | None = Field(default=None, max_length=2000)
    verification_state: VerificationState
    facts: dict[str, str] = Field(default_factory=dict)

    @field_validator("refs")
    @classmethod
    def _refs_are_identifiers(cls, value: list[str]) -> list[str]:
        for ref in value:
            if not isinstance(ref, str) or not REF_PATTERN.match(ref):
                raise ValueError(
                    f"K14-2: ref {ref!r} is not an opaque identifier; refs must "
                    "reference content, never carry it"
                )
        return value

    @field_validator("facts")
    @classmethod
    def _facts_are_bounded_scalars(cls, value: dict[str, str]) -> dict[str, str]:
        for key, raw in value.items():
            if not FACT_KEY_PATTERN.match(key):
                raise ValueError(f"fact key {key!r} must be a machine key")
            if not isinstance(raw, str):
                raise ValueError(f"fact {key!r} must be a string scalar")
            if len(raw) > FACT_VALUE_MAX:
                raise ValueError(
                    f"fact {key!r} is {len(raw)} chars (> {FACT_VALUE_MAX}); "
                    "facts are scalars, not content"
                )
            if "\n" in raw:
                raise ValueError(f"fact {key!r} must be single-line")
        return value

    @model_validator(mode="after")
    def _state_agrees_with_verified(self) -> PanelSection:
        if self.verified != (self.verification_state == "verified"):
            raise ValueError(
                "K14-1: verified must be True exactly when "
                "verification_state == 'verified'"
            )
        if self.verified and self.unknown_reason is not None:
            raise ValueError("K14-3: a verified section carries no unknown_reason")
        if not self.verified and not (self.unknown_reason or "").strip():
            raise ValueError(
                "K14-3: a non-verified section must carry a non-empty "
                "unknown_reason explaining whether it is unverified or blocked"
            )
        return self


class PanelProjection(BaseModel):
    """K14 ``PanelProjection`` -- what the UI receives for one panel."""

    model_config = ConfigDict(extra="forbid")

    panel_id: str
    sections: list[PanelSection] = Field(min_length=1)
    verification_state: VerificationState

    @field_validator("panel_id")
    @classmethod
    def _known_panel(cls, value: str) -> str:
        if value not in PANEL_IDS:
            raise ValueError(f"panel_id {value!r} not in {PANEL_IDS}")
        return value

    @model_validator(mode="after")
    def _state_is_worst_section(self) -> PanelProjection:
        if self.verification_state != aggregate_state(self.sections):
            raise ValueError(
                "K14-1: panel verification_state must be the worst section state"
            )
        return self


def aggregate_state(sections: list[PanelSection]) -> VerificationState:
    """Worst-case roll-up: any blocker blocks; else any unknown makes it unknown.

    Empty section lists resolve to ``unverified`` rather than ``verified`` so an
    accidentally-empty panel can never read as "all good" (K14-1).
    """
    if not sections:
        return "unverified"
    if any(section.verification_state == "blocked" for section in sections):
        return "blocked"
    if any(section.verification_state == "unverified" for section in sections):
        return "unverified"
    return "verified"


# ---------------------------------------------------------------------------
# Section constructors
# ---------------------------------------------------------------------------


def verified_section(
    title: str,
    refs: list[str],
    facts: dict[str, str] | None = None,
) -> PanelSection:
    return PanelSection(
        title=title,
        refs=_dedupe(refs),
        verified=True,
        unknown_reason=None,
        verification_state="verified",
        facts=facts or {},
    )


def unverified_section(
    title: str,
    reason: str,
    refs: list[str] | None = None,
    facts: dict[str, str] | None = None,
) -> PanelSection:
    return PanelSection(
        title=title,
        refs=_dedupe(refs or []),
        verified=False,
        unknown_reason=reason,
        verification_state="unverified",
        facts=facts or {},
    )


def blocked_section(
    title: str,
    reason: str,
    refs: list[str] | None = None,
    facts: dict[str, str] | None = None,
) -> PanelSection:
    return PanelSection(
        title=title,
        refs=_dedupe(refs or []),
        verified=False,
        unknown_reason=reason,
        verification_state="blocked",
        facts=facts or {},
    )


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        if raw and raw not in seen:
            seen.add(raw)
            out.append(raw)
    return out


# ---------------------------------------------------------------------------
# Source payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PanelSources:
    """Raw endpoint payloads for one project.

    ``None`` means *the panel could not read that endpoint* -- a different fact
    from an empty list, which means *the endpoint answered and the list is
    empty*. Conflating the two is exactly the failure mode K14-1 exists to stop.
    """

    project_id: str
    project: dict[str, Any] | None = None
    run: dict[str, Any] | None = None
    work_packages: list[dict[str, Any]] | None = None
    evidence: list[dict[str, Any]] | None = None
    audit_events: list[dict[str, Any]] | None = None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _string(row: dict[str, Any], key: str) -> str | None:
    raw = row.get(key)
    return raw if isinstance(raw, str) and raw else None


def resolve_run_id(sources: PanelSources) -> tuple[str | None, str]:
    """Return ``(run_id, resolution)``.

    ``resolution`` is one of ``run-payload`` / ``audit:run.started`` /
    ``unresolved`` and is published as a panel fact so the hop is auditable.
    """
    run = _dict(sources.run)
    direct = _string(run, "run_id")
    if direct:
        return direct, "run-payload"
    for event in reversed(_rows(sources.audit_events)):
        if _string(event, "event_type") == RUN_STARTED_EVENT:
            candidate = _string(_dict(event.get("payload")), "run_id")
            if candidate:
                return candidate, "audit:run.started"
    return None, "unresolved"


def _run_state(sources: PanelSources) -> dict[str, Any] | None:
    state = _dict(sources.run).get("state")
    return state if isinstance(state, dict) else None


def _events_of(sources: PanelSources, event_type: str) -> list[dict[str, Any]]:
    return [
        event
        for event in _rows(sources.audit_events)
        if _string(event, "event_type") == event_type
    ]


def _gate_decisions(sources: PanelSources) -> list[dict[str, Any]]:
    return [_dict(event.get("payload")) for event in _events_of(sources, GATE_EVENT)]


def _evidence_ids(sources: PanelSources) -> list[str]:
    return [
        eid
        for item in _rows(sources.evidence)
        if (eid := _string(item, "evidence_id"))
    ]


def _grades(rows: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        grade = _string(row, "grade") or "?"
        counts[grade] = counts.get(grade, 0) + 1
    return ",".join(f"{key}={counts[key]}" for key in sorted(counts))


def _truth(value: bool) -> str:
    return "true" if value else "false"


# ---------------------------------------------------------------------------
# Panel: project (M13-04 -- 阶段 / Gate / 证据覆盖 / handoff / 任务 / 阻塞)
# ---------------------------------------------------------------------------


def build_project_panel(sources: PanelSources) -> PanelProjection:
    state = _run_state(sources)
    sections = [
        _stage_section(sources, state),
        _gate_section(sources),
        _coverage_section(sources, state),
        _handoff_section(sources, state),
        _work_package_section(sources, state),
        _blocker_section(sources, state),
    ]
    return PanelProjection(
        panel_id="project",
        sections=sections,
        verification_state=aggregate_state(sections),
    )


def _stage_section(sources: PanelSources, state: dict[str, Any] | None) -> PanelSection:
    run_id, resolution = resolve_run_id(sources)
    refs = [ref for ref in (sources.project_id, run_id) if ref]
    if sources.run is None:
        return unverified_section(
            "阶段 / stage",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: GET /runs/{{run_id}} "
            f"(run resolution: {resolution})",
            refs=[sources.project_id],
            facts={"run_resolution": resolution},
        )
    if state is None:
        return unverified_section(
            "阶段 / stage",
            "run payload has no 'state' object; lifecycle cannot be read",
            refs=refs,
            facts={"run_resolution": resolution},
        )
    lifecycle = _string(state, "lifecycle_state")
    run_status = _string(state, "run_status") or _string(_dict(sources.run), "status")
    if lifecycle is None and run_status is None:
        return unverified_section(
            "阶段 / stage",
            "neither lifecycle_state nor run_status is present in the run payload",
            refs=refs,
            facts={"run_resolution": resolution},
        )
    return verified_section(
        "阶段 / stage",
        refs,
        facts={
            "run_resolution": resolution,
            "lifecycle_state": lifecycle or "unknown",
            "run_status": run_status or "unknown",
            "updated_at": _string(state, "updated_at") or "unknown",
        },
    )


def _gate_section(sources: PanelSources) -> PanelSection:
    decisions = _gate_decisions(sources)
    refs = [did for d in decisions if (did := _string(d, "decision_id"))]
    if sources.audit_events is None:
        return unverified_section(
            "Gate 裁决 / gate decisions",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: GET /projects/{{id}}/audit-events",
        )
    if not decisions:
        return unverified_section(
            "Gate 裁决 / gate decisions",
            "no gate.evaluated event in the audit log: the project has not "
            "reached a gate decision yet, or the decision was never persisted",
            refs=[sources.project_id],
            facts={"gate_decision_count": "0"},
        )
    latest = decisions[-1]
    return verified_section(
        "Gate 裁决 / gate decisions",
        refs,
        facts={
            "gate_decision_count": str(len(decisions)),
            "latest_decision_id": _string(latest, "decision_id") or "unknown",
            "latest_operation": _string(latest, "operation") or "unknown",
            "latest_status": _string(latest, "status") or "unknown",
            "latest_risk_level": _string(latest, "risk_level") or "unknown",
            "latest_score": str(latest.get("score", "unknown")),
            "latest_independent_sources": str(
                latest.get("independent_sources", "unknown")
            ),
            "latest_qualifying_evidence_ids": ",".join(
                str(x) for x in latest.get("qualifying_evidence_ids", []) if x
            )
            or "none",
            "source": "audit:gate.evaluated",
        },
    )


def _coverage_section(
    sources: PanelSources, state: dict[str, Any] | None
) -> PanelSection:
    if sources.evidence is None:
        return unverified_section(
            "证据覆盖 / evidence coverage",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: "
            "GET /projects/{id}/evidence?valid_only=false",
        )
    recorded = [eid for eid in (_dict(state).get("evidence_ids") or []) if eid]
    resolved = set(_evidence_ids(sources))
    invalid = [
        eid
        for item in _rows(sources.evidence)
        if item.get("valid") is False and (eid := _string(item, "evidence_id"))
    ]
    unresolved = [eid for eid in recorded if eid not in resolved]
    facts = {
        # named so that the two counts cannot be read as contradicting each other:
        # refs recorded on the run state vs rows present in the evidence store.
        "state_evidence_ref_count": str(len(recorded)),
        "store_evidence_count": str(len(resolved)),
        "resolved_ref_count": str(len(recorded) - len(unresolved)),
        "invalid_count": str(len(invalid)),
        "grades": _grades(_rows(sources.evidence)) or "none",
    }
    if not recorded and not sources.evidence:
        return unverified_section(
            "证据覆盖 / evidence coverage",
            "no evidence recorded for this project: ResearchState.evidence_ids is "
            "empty and GET /projects/{id}/evidence returned []",
            refs=[sources.project_id],
            facts=facts,
        )
    if unresolved:
        return unverified_section(
            "证据覆盖 / evidence coverage",
            "ResearchState references evidence ids that the evidence endpoint does "
            "not resolve: " + ",".join(unresolved[:10]),
            refs=[sources.project_id, *recorded],
            facts={**facts, "unresolved_count": str(len(unresolved))},
        )
    if state is None:
        return unverified_section(
            "证据覆盖 / evidence coverage",
            "evidence is readable but the run state is not, so coverage against "
            "ResearchState.evidence_ids cannot be computed",
            refs=resolved_refs(sources),
            facts=facts,
        )
    return verified_section(
        "证据覆盖 / evidence coverage",
        [sources.project_id, *recorded],
        facts={**facts, "unresolved_count": "0"},
    )


def resolved_refs(sources: PanelSources) -> list[str]:
    return _evidence_ids(sources)


def _handoff_section(
    sources: PanelSources, state: dict[str, Any] | None
) -> PanelSection:
    issued = _events_of(sources, HANDOFF_ISSUED_EVENT)
    accepted = _events_of(sources, HANDOFF_ACCEPTED_EVENT)
    refs: list[str] = []
    for event in issued + accepted:
        payload = _dict(event.get("payload"))
        refs.extend(
            ref
            for ref in (
                _string(payload, "handoff_id"),
                _string(payload, "run_id"),
                _string(payload, "from_agent"),
                _string(payload, "to_agent") or _string(payload, "receiver"),
            )
            if ref
        )
    embedded = _dict(state).get("handoff") if state else None
    embedded_id = _string(_dict(embedded), "handoff_id") if embedded else None
    if embedded_id:
        refs.append(embedded_id)
    facts = {
        "handoff_issued": str(len(issued)),
        "handoff_accepted": str(len(accepted)),
        "state_handoff_present": _truth(bool(embedded_id)),
        "source": "audit:handoff.issued,audit:handoff.accepted"
        + (",state:handoff" if embedded_id else ""),
    }
    if sources.audit_events is None:
        return unverified_section(
            "handoff",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: GET /projects/{{id}}/audit-events",
        )
    if not issued and not accepted and not embedded_id:
        return unverified_section(
            "handoff",
            "no handoff.issued / handoff.accepted event in the audit log and "
            "ResearchState.handoff is null",
            refs=[sources.project_id],
            facts=facts,
        )
    return verified_section("handoff", refs, facts=facts)


WORK_PACKAGE_STATUSES = ("planned", "in_progress", "blocked", "completed")


def _work_package_section(
    sources: PanelSources, state: dict[str, Any] | None
) -> PanelSection:
    if sources.work_packages is None:
        return unverified_section(
            "任务 / work packages",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: GET /projects/{{id}}/work-packages",
        )
    rows = _rows(sources.work_packages)
    refs = [wid for row in rows if (wid := _string(row, "work_package_id"))]
    recorded = [
        wid for wid in (_dict(state).get("work_package_ids") or []) if wid
    ]
    facts: dict[str, str] = {"work_package_count": str(len(rows))}
    for status in WORK_PACKAGE_STATUSES:
        facts[f"status_{status}"] = str(
            sum(1 for row in rows if _string(row, "status") == status)
        )
    if not rows:
        return unverified_section(
            "任务 / work packages",
            "no work packages recorded for this project",
            refs=[sources.project_id],
            facts=facts,
        )
    missing = [wid for wid in recorded if wid not in set(refs)]
    if missing:
        return unverified_section(
            "任务 / work packages",
            "ResearchState references work package ids the endpoint does not "
            "return: " + ",".join(missing[:10]),
            refs=[*recorded, *refs],
            facts={**facts, "unresolved_count": str(len(missing))},
        )
    return verified_section(
        "任务 / work packages",
        _dedupe([*recorded, *refs]),
        facts={**facts, "unresolved_count": "0"},
    )


def _blocker_section(
    sources: PanelSources, state: dict[str, Any] | None
) -> PanelSection:
    if sources.run is None and sources.work_packages is None:
        return unverified_section(
            "阻塞 / blockers",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: GET /runs/{{run_id}} and "
            "GET /projects/{id}/work-packages",
            refs=[sources.project_id],
        )
    blockers = [
        text for text in (_dict(state).get("blockers") or []) if isinstance(text, str)
    ]
    diagnostics = [
        text
        for text in (_dict(state).get("diagnostics") or [])
        if isinstance(text, str)
    ]
    lifecycle = _string(_dict(state), "lifecycle_state")
    run_status = _string(_dict(state), "run_status")
    blocked_packages = [
        row
        for row in _rows(sources.work_packages)
        if _string(row, "status") == "blocked"
    ]
    blocked_refs = [
        wp for row in blocked_packages if (wp := _string(row, "work_package_id"))
    ]
    facts = {
        "blocker_count": str(len(blockers)),
        "blocked_work_package_count": str(len(blocked_packages)),
        "run_status": run_status or "unknown",
        "lifecycle_state": lifecycle or "unknown",
        "diagnostic_count": str(len(diagnostics)),
    }
    reasons = list(blockers)
    if run_status in BLOCKING_RUN_STATUSES:
        reasons.append(f"run_status={run_status}")
    if lifecycle in BLOCKING_LIFECYCLE_STATES:
        reasons.append(f"lifecycle_state={lifecycle}")
    if blocked_packages:
        reasons.append(f"{len(blocked_packages)} work package(s) with status=blocked")
    if reasons:
        detail = "; ".join(reasons)
        if diagnostics:
            detail = f"{detail} | diagnostics: " + "; ".join(diagnostics[:5])
        return blocked_section(
            "阻塞 / blockers",
            detail,
            refs=[sources.project_id, *blocked_refs],
            facts=facts,
        )
    if state is None:
        # No ResearchState means the blocker list was never read, which is a very
        # different fact from "read it and it was empty". Reporting `verified`
        # here would claim "no blockers" for a project that never ran at all --
        # exactly the false completion M13-04 forbids.
        return unverified_section(
            "阻塞 / blockers",
            "ResearchState is not readable (no run for this project), so "
            "blockers/diagnostics were never read; only the "
            f"{len(_rows(sources.work_packages))} work package(s) could be checked "
            "and none is blocked",
            refs=[sources.project_id],
            facts={**facts, "read_scope": "work-packages-only"},
        )
    return verified_section(
        "阻塞 / blockers",
        [sources.project_id],
        facts={**facts, "read_scope": "run-state+work-packages"},
    )


# ---------------------------------------------------------------------------
# Panel: evidence (M13-05 -- evidence / Gate / 审查意见 / 回退入口)
# ---------------------------------------------------------------------------


def build_evidence_panel(sources: PanelSources) -> PanelProjection:
    state = _run_state(sources)
    sections = [
        _evidence_items_section(sources),
        _evidence_claim_grouping_section(sources),
        _evidence_run_link_section(sources),
        _gate_section(sources),
        _review_section(sources, state),
        build_review_report_section(state),
        _retraction_section(sources),
    ]
    return PanelProjection(
        panel_id="evidence",
        sections=sections,
        verification_state=aggregate_state(sections),
    )


def _evidence_items_section(sources: PanelSources) -> PanelSection:
    if sources.evidence is None:
        return unverified_section(
            "证据项 / evidence items",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: "
            "GET /projects/{id}/evidence?valid_only=false",
        )
    rows = _rows(sources.evidence)
    if not rows:
        return unverified_section(
            "证据项 / evidence items",
            "GET /projects/{id}/evidence returned [] for this project",
            refs=[sources.project_id],
            facts={"evidence_count": "0"},
        )
    invalid = [row for row in rows if row.get("valid") is False]
    return verified_section(
        "证据项 / evidence items",
        _evidence_ids(sources),
        facts={
            "evidence_count": str(len(rows)),
            "valid_count": str(len(rows) - len(invalid)),
            "invalid_count": str(len(invalid)),
            "grades": _grades(rows) or "none",
            "evidence_types": ",".join(
                sorted({_string(row, "evidence_type") or "?" for row in rows})
            ),
            "note": "K14-2: claim/title text is not copied into the panel",
        },
    )


def _evidence_claim_grouping_section(sources: PanelSources) -> PanelSection:
    if sources.evidence is None:
        return unverified_section(
            "按 claim 归类 / grouped by claim",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: "
            "GET /projects/{id}/evidence?valid_only=false",
        )
    rows = _rows(sources.evidence)
    distinct = {_string(row, "claim") for row in rows}
    distinct.discard(None)
    if not rows:
        return unverified_section(
            "按 claim 归类 / grouped by claim",
            "no evidence items to group",
            refs=[sources.project_id],
            facts={"claim_group_count": "0"},
        )
    return unverified_section(
        "按 claim 归类 / grouped by claim",
        "grouping key is the evidence claim text; K14-2 forbids copying claim "
        "content into the panel and there is no endpoint that resolves a claim, "
        "so only the group count and the evidence refs are shown",
        refs=_evidence_ids(sources),
        facts={
            "claim_group_count": str(len(distinct)),
            "evidence_count": str(len(rows)),
            "gap": "G-3 no GET /evidence/{id} and no claim-level read model",
        },
    )


def _evidence_run_link_section(sources: PanelSources) -> PanelSection:
    """M13-05 asks to read evidence *by run* and *by action*; neither is readable."""
    if sources.evidence is None:
        return unverified_section(
            "按 run·action 归属 / grouped by run·action",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: "
            "GET /projects/{id}/evidence?valid_only=false",
        )
    return unverified_section(
        "按 run·action 归属 / grouped by run·action",
        "EvidenceItem carries no run_id / invocation_id / action field, and no GET "
        "endpoint links evidence to a run or to the action that produced it "
        "(EvidenceCandidate has run_id but is not exposed by any GET endpoint)",
        refs=_evidence_ids(sources),
        facts={
            "gap": "G-4 evidence->run/action link not readable",
            "available_grouping": "claim,evidence_type,grade",
        },
    )


def _review_section(
    sources: PanelSources, state: dict[str, Any] | None
) -> PanelSection:
    if sources.audit_events is None:
        return unverified_section(
            "审查与裁决 / reviews & verdicts",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: GET /projects/{{id}}/audit-events",
        )
    reports = _events_of(sources, AUDIT_REPORT_EVENT)
    gate_events = _events_of(sources, GATE_EVENT)
    reviewer_accepts = [
        event
        for event in _events_of(sources, HANDOFF_ACCEPTED_EVENT)
        if _string(event, "actor") == "reviewer"
    ]
    refs = [
        eid
        for event in [*reports, *gate_events, *reviewer_accepts]
        if (eid := _string(event, "event_id"))
    ]
    refs.extend(
        did
        for event in gate_events
        if (did := _string(_dict(event.get("payload")), "decision_id"))
    )
    facts = {
        "audit_report_count": str(len(reports)),
        "gate_verdict_count": str(len(gate_events)),
        "reviewer_accept_count": str(len(reviewer_accepts)),
        "note": "verdict text (reasons/findings) is not copied; refs resolve it",
    }
    if not refs:
        return unverified_section(
            "审查与裁决 / reviews & verdicts",
            "no audit.report_created / gate.evaluated / reviewer handoff.accepted "
            "event for this project",
            refs=[sources.project_id],
            facts={**facts, "review_ref_count": "0"},
        )
    return verified_section(
        "审查与裁决 / reviews & verdicts",
        refs,
        facts={**facts, "review_ref_count": str(len(refs))},
    )


def build_review_report_section(state: dict[str, Any] | None) -> PanelSection:
    """``ResearchState.review_ids`` -> ReviewReport has no read endpoint."""
    review_ids = [
        rid for rid in (_dict(state).get("review_ids") or []) if isinstance(rid, str)
    ]
    if not review_ids:
        return unverified_section(
            "评审报告 / ReviewReport",
            "ResearchState.review_ids is empty: no ReviewReport recorded",
            facts={"review_report_count": "0"},
        )
    return unverified_section(
        "评审报告 / ReviewReport",
        "ResearchState.review_ids is non-empty but no read endpoint returns a "
        "ReviewReport; only the ids are available",
        refs=review_ids,
        facts={
            "review_report_count": str(len(review_ids)),
            "gap": "G-5 no GET /reviews/{id}",
        },
    )


def _retraction_section(sources: PanelSources) -> PanelSection:
    """M13-05 回退入口: invalidated evidence + the endpoint that performs it."""
    if sources.evidence is None:
        return unverified_section(
            "回退入口 / retraction",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: "
            "GET /projects/{id}/evidence?valid_only=false "
            "(NOTE: the endpoint default valid_only=true hides invalidated items)",
        )
    invalid = [
        row for row in _rows(sources.evidence) if row.get("valid") is False
    ]
    events = _events_of(sources, EVIDENCE_INVALIDATED_EVENT)
    refs = [eid for row in invalid if (eid := _string(row, "evidence_id"))]
    refs.extend(
        eid
        for event in events
        if (eid := _string(_dict(event.get("payload")), "evidence_id"))
    )
    facts = {
        "invalid_evidence_count": str(len(invalid)),
        "retraction_event_count": str(len(events)),
        "write_endpoint": "POST /evidence/{evidence_id}/invalidate",
        "query": "GET /projects/{id}/evidence?valid_only=false",
    }
    if sources.audit_events is None:
        return unverified_section(
            "回退入口 / retraction",
            "evidence is readable but the audit log is not, so retraction events "
            "cannot be confirmed",
            refs=refs,
            facts=facts,
        )
    if not refs:
        if not _rows(sources.evidence):
            return unverified_section(
                "回退入口 / retraction",
                "no evidence is recorded for this project, so no retraction can "
                "exist yet; the retraction state was never observed",
                refs=[sources.project_id],
                facts=facts,
            )
        return verified_section(
            "回退入口 / retraction",
            [sources.project_id],
            facts={**facts, "state": "no retraction recorded"},
        )
    return verified_section("回退入口 / retraction", refs, facts=facts)


# ---------------------------------------------------------------------------
# Panel: approval (M13-07 -- 范围 / 风险 / 证据 / 待决策 / 审批历史)
# ---------------------------------------------------------------------------


def build_approval_panel(sources: PanelSources) -> PanelProjection:
    state = _run_state(sources)
    sections = [
        _approval_scope_section(sources, state),
        _approval_risk_section(sources),
        _approval_evidence_section(sources),
        _pending_decision_section(sources),
        _approval_history_section(sources),
    ]
    return PanelProjection(
        panel_id="approval",
        sections=sections,
        verification_state=aggregate_state(sections),
    )


def _pending_interrupt(sources: PanelSources) -> dict[str, Any] | None:
    run = _dict(sources.run)
    interrupts = _rows(run.get("interrupts"))
    for interrupt in interrupts:
        if _string(interrupt, "type") == APPROVAL_INTERRUPT_TYPE:
            return interrupt
    # Only a genuine human-release-approval interrupt counts as a pending decision.
    # A non-approval interrupt (e.g. an inline user message) must NOT be treated as
    # one, otherwise the approval panel would falsely report "pending = true".
    return None


def _approval_scope_section(
    sources: PanelSources, state: dict[str, Any] | None
) -> PanelSection:
    run_id, resolution = resolve_run_id(sources)
    interrupt = _pending_interrupt(sources)
    refs = [ref for ref in (sources.project_id, run_id) if ref]
    if sources.run is None:
        return unverified_section(
            "审批范围 / scope",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: GET /runs/{{run_id}} "
            f"(run resolution: {resolution})",
            refs=[sources.project_id],
            facts={"run_resolution": resolution},
        )
    if interrupt is None:
        return unverified_section(
            "审批范围 / scope",
            "run carries no pending interrupt, so there is no approval scope to "
            "show (scope is defined by the interrupt payload)",
            refs=refs,
            facts={
                "run_resolution": resolution,
                "run_id": run_id or "unknown",
                "pending_interrupt": "false",
            },
        )
    operation = _string(interrupt, "operation")
    return verified_section(
        "审批范围 / scope",
        [*refs, *([operation] if operation else [])],
        facts={
            "run_resolution": resolution,
            "run_id": run_id or "unknown",
            "pending_interrupt": "true",
            "interrupt_type": _string(interrupt, "type") or "unknown",
            "operation": operation or "unknown",
            "risk_level": _string(interrupt, "risk_level") or "unknown",
            "message_ref": "GET /runs/{run_id} -> interrupts[0].message",
        },
    )


def _approval_risk_section(sources: PanelSources) -> PanelSection:
    """Risk level: from the pending interrupt, else from the newest gate decision."""
    interrupt = _pending_interrupt(sources)
    interrupt_risk = _string(_dict(interrupt), "risk_level") if interrupt else None
    decisions = _gate_decisions(sources)
    latest = decisions[-1] if decisions else None
    gate_risk = _string(_dict(latest), "risk_level") if latest else None
    if interrupt_risk:
        return verified_section(
            "风险等级 / risk level",
            [ref for ref in (_string(_dict(interrupt), "run_id"),) if ref],
            facts={
                "risk_level": interrupt_risk,
                "source": "run:interrupts[].risk_level",
                "basis": "pending human approval request",
            },
        )
    if gate_risk and latest is not None:
        decision_id = _string(latest, "decision_id") or ""
        return verified_section(
            "风险等级 / risk level",
            [decision_id] if decision_id else [],
            facts={
                "risk_level": gate_risk,
                "gate_status": _string(latest, "status") or "unknown",
                "gate_score": str(latest.get("score", "unknown")),
                "source": "audit:gate.evaluated",
                "basis": "no pending interrupt; newest gate decision shown instead",
            },
        )
    if sources.audit_events is None:
        return unverified_section(
            "风险等级 / risk level",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: GET /projects/{{id}}/audit-events "
            "(RiskLevel is only reachable through the gate.evaluated payload)",
        )
    return unverified_section(
        "风险等级 / risk level",
        "no pending interrupt and no gate.evaluated event: RiskLevel is not "
        "exposed by any other read endpoint",
        refs=[sources.project_id],
        facts={"gap": "G-6 RiskLevel only readable via gate.evaluated"},
    )


HIGH_TRUST_GRADES = ("H3",)


def _approval_evidence_section(sources: PanelSources) -> PanelSection:
    if sources.evidence is None:
        return unverified_section(
            "支撑证据 / backing evidence",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: "
            "GET /projects/{id}/evidence?valid_only=false",
        )
    rows = _rows(sources.evidence)
    high = [
        row for row in rows if _string(row, "grade") in HIGH_TRUST_GRADES
    ]
    decisions = _gate_decisions(sources)
    qualifying = [
        str(eid)
        for decision in decisions
        for eid in (decision.get("qualifying_evidence_ids") or [])
        if eid
    ]
    refs = [*_evidence_ids(sources), *qualifying]
    facts = {
        "evidence_count": str(len(rows)),
        "h3_count": str(len(high)),
        "valid_count": str(sum(1 for row in rows if row.get("valid") is not False)),
        "grades": _grades(rows) or "none",
        "qualifying_evidence_count": str(len(_dedupe(qualifying))),
        "note": "H3 = human-graded; claim text is not copied (K14-2)",
    }
    if not rows:
        return unverified_section(
            "支撑证据 / backing evidence",
            "no evidence recorded, so no evidence backs any approval request",
            refs=[sources.project_id],
            facts={**facts, "evidence_count": "0"},
        )
    return verified_section("支撑证据 / backing evidence", refs, facts=facts)


def _pending_decision_section(sources: PanelSources) -> PanelSection:
    if sources.run is None:
        return unverified_section(
            "待人工决策 / pending human decision",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: GET /runs/{{run_id}}",
            refs=[sources.project_id],
        )
    interrupt = _pending_interrupt(sources)
    run_id = _string(_dict(sources.run), "run_id")
    base = {
        "run_id": run_id or "unknown",
        "approve_endpoint": "POST /runs/{run_id}/resume",
    }
    if interrupt is None:
        return unverified_section(
            "待人工决策 / pending human decision",
            "no pending human interrupt on this run: POST /runs/{run_id}/resume "
            "would return 409 ('run is not waiting for a human interrupt')",
            refs=[ref for ref in (run_id,) if ref],
            facts={
                **base,
                "pending": "false",
                "interrupt_count": str(
                    len(_rows(_dict(sources.run).get("interrupts")))
                ),
            },
        )
    return verified_section(
        "待人工决策 / pending human decision",
        [ref for ref in (run_id,) if ref],
        facts={
            **base,
            "pending": "true",
            "interrupt_count": str(len(_rows(_dict(sources.run).get("interrupts")))),
            "reject_endpoint": "POST /evidence/{evidence_id}/invalidate",
        },
    )


def _is_human_decision(event: dict[str, Any]) -> bool:
    """Is this audit event a recorded human approve/reject/retract decision?

    Measured against the writers, not guessed:

    * ``evidence.invalidated`` -- the 打回 path (``evidence.py``), actor = human.
    * ``evidence.added`` with ``evidence_type=human`` **and** ``grade=H3``
      **and** a ``source_id`` -- the approve path. ``graph.py:132`` writes an H3
      approval record with ``actor=reviewer`` and ``source_id=run_id``.
    * ``gate.evaluated`` with ``operation=external_manuscript_release`` -- the
      reject path; ``graph.py:103`` evaluates with ``explicitly_rejected=True``,
      which lands here as ``status=deny``.

    The ``grade=H3`` + ``source_id`` conjuncts matter: the orchestrator also
    records the *research idea* as ``evidence_type=human`` but at grade ``E0``
    with no ``source_id``. Matching on ``evidence_type`` alone reported that idea
    as an approval and inflated the history (regression test
    ``test_approval_history_counts_only_real_decisions``).

    Limit: an approval is recognised only through these three event shapes. An
    approval recorded by some future writer that does not emit one of them will
    show up as "no decision recorded" -- a visible under-report rather than a
    silent over-report.
    """
    event_type = _string(event, "event_type")
    payload = _dict(event.get("payload"))
    if event_type == EVIDENCE_INVALIDATED_EVENT:
        return True
    if event_type == "evidence.added":
        return (
            _string(payload, "evidence_type") == "human"
            and _string(payload, "grade") == "H3"
            and _string(payload, "source_id") is not None
        )
    if event_type == GATE_EVENT:
        return _string(payload, "operation") == RELEASE_OPERATION
    return False


def _approval_history_section(sources: PanelSources) -> PanelSection:
    if sources.audit_events is None:
        return unverified_section(
            "审批历史 / approval history",
            f"{UNKNOWN_ENDPOINT_UNAVAILABLE}: GET /projects/{{id}}/audit-events",
        )
    decisions = [
        event for event in _rows(sources.audit_events) if _is_human_decision(event)
    ]
    refs: list[str] = []
    for event in decisions:
        payload = _dict(event.get("payload"))
        for ref in (
            _string(event, "event_id"),
            _string(payload, "evidence_id"),
            _string(payload, "decision_id"),
        ):
            if ref:
                refs.append(ref)
    human_actors = sorted(
        {_string(event, "actor") for event in decisions} - {None, "orchestrator"}
    )
    facts = {
        "human_decision_count": str(len(decisions)),
        "decision_event_types": ",".join(
            sorted({_string(event, "event_type") or "?" for event in decisions})
        )
        or "none",
        "actors": ",".join(human_actors) or "none",
        "attribution": "approve -> evidence.added(human,H3,actor=reviewer); "
        "reject -> gate.evaluated(operation=external_manuscript_release); "
        "retract -> evidence.invalidated",
    }
    if not refs:
        return unverified_section(
            "审批历史 / approval history",
            "no human approve / reject / retract decision is recorded for this "
            "project (looked for evidence.invalidated, evidence.added with "
            "evidence_type=human, and gate.evaluated on "
            f"{RELEASE_OPERATION})",
            refs=[sources.project_id],
            facts={**facts, "human_decision_count": "0"},
        )
    return verified_section(
        "审批历史 / approval history",
        refs,
        facts={**facts, "human_decision_count": str(len(decisions))},
    )


# ---------------------------------------------------------------------------
# Panel: files (M13-06 -- deliberately out of scope for this package)
# ---------------------------------------------------------------------------


def build_files_panel() -> PanelProjection:
    """M13-06 is *not* implemented in this package.

    Rendered as ``blocked`` rather than omitted: K14 declares ``files`` as one of
    the four ``panel_id`` values, so silently dropping it would itself be a way
    of hiding unfinished work (M13-04 / A5).
    """
    return PanelProjection(
        panel_id="files",
        sections=[
            blocked_section(
                "项目文件夹浏览与导出 / project file browser & export",
                "M13-06 is not implemented in the R-007 L-08 package: it requires "
                "K11 AccessPolicy (L-09 acl.py) to decide what may be exported. "
                "No file list and no export button are shown, because showing "
                "either without the ACL would misrepresent the export surface.",
                facts={
                    "blocked_by": "K11 AccessPolicy (L-09)",
                    "this_package": "M13-04,M13-05,M13-07",
                    "export_endpoint": "none",
                },
            )
        ],
        verification_state="blocked",
    )


BUILDERS = {
    "project": build_project_panel,
    "evidence": build_evidence_panel,
    "approval": build_approval_panel,
}


def build_panel(panel_id: str, sources: PanelSources) -> PanelProjection:
    if panel_id == "files":
        return build_files_panel()
    try:
        builder = BUILDERS[panel_id]
    except KeyError as exc:
        raise ValueError(f"unknown panel_id: {panel_id!r}") from exc
    return builder(sources)


# ---------------------------------------------------------------------------
# Read-only source collection (mirrors the 24 endpoints, mutates nothing)
# ---------------------------------------------------------------------------


@dataclass
class PanelReader:
    """Collects ``PanelSources`` from the runtime using read-only accessors.

    Every call below has a one-to-one ``api.py`` counterpart; ``PanelReader``
    exists only to batch those reads behind one object. It is deliberately thin
    so the builders stay pure and unit-testable without a server.
    """

    runtime: Any
    warnings: list[str] = field(default_factory=list)

    def collect(self, project_id: str) -> PanelSources:
        del self.warnings[:]
        project = self._safe(lambda: self.runtime.projects.get(project_id), "project")
        audit_events = self._safe(
            lambda: self.runtime.store.events(project_id), "audit-events"
        )
        run_id: str | None = None
        if isinstance(audit_events, list):
            probe = PanelSources(project_id=project_id, audit_events=audit_events)
            run_id, _ = resolve_run_id(probe)
        run = (
            self._safe(lambda: self.runtime.get_run(run_id), "run")
            if run_id
            else None
        )
        work_packages = self._safe(
            lambda: [
                item.model_dump(mode="json")
                for item in self.runtime.execution.list_work_packages(project_id)
            ],
            "work-packages",
        )
        evidence = self._safe(
            lambda: [
                item.model_dump(mode="json")
                # valid_only=False: the endpoint default hides invalidated items,
                # which the retraction section must show.
                for item in self.runtime.evidence.list(project_id, valid_only=False)
            ],
            "evidence",
        )
        return PanelSources(
            project_id=project_id,
            project=project if isinstance(project, dict) else None,
            run=run if isinstance(run, dict) else None,
            work_packages=work_packages
            if isinstance(work_packages, list)
            else None,
            evidence=evidence if isinstance(evidence, list) else None,
            audit_events=audit_events if isinstance(audit_events, list) else None,
        )

    def _safe(self, call: Any, label: str) -> Any:
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - a failed read is data, not a crash
            self.warnings.append(f"{label}: {type(exc).__name__}: {exc}")
            return None


# ---------------------------------------------------------------------------
# ASGI surface
# ---------------------------------------------------------------------------


def default_web_root() -> Path:
    return Path(__file__).resolve().parents[2] / "web"


def create_web_api(
    runtime: Any,
    *,
    web_root: Path | None = None,
) -> FastAPI:
    """Return an ASGI app serving the M13 panels and re-mounting the 24 endpoints.

    The existing API is mounted under ``/api`` so the browser talks to one
    origin: reads for the panels, writes for M13-07. ``src/autoresearch/api.py``
    and every other existing module are untouched.
    """
    from autoresearch.api import create_api

    app = FastAPI(
        title="AutoResearch M13 panel boundary",
        version="0.1.0",
        description="K14 PanelProjection over the read-only API surface",
    )
    reader = PanelReader(runtime=runtime)

    @app.get("/ui/panels")
    def list_panels(project_id: str | None = None) -> dict[str, Any]:
        """Panel inventory, plus each panel's real state when a project is given.

        ``states`` exists so the tab bar can be truthful: a tab marker has to be
        written from the same ``PanelProjection.verification_state`` the panel
        itself renders. Without it the client can only guess, and guessing a
        status is exactly what M13-04 / A5 forbid. The values come from the same
        builders the panel endpoint uses -- computed once, never re-derived.
        """
        payload: dict[str, Any] = {
            "panel_ids": list(PANEL_IDS),
            "implemented": ["project", "evidence", "approval"],
            "blocked": ["files"],
        }
        if project_id:
            sources = reader.collect(project_id)
            payload["project_id"] = project_id
            payload["states"] = {
                panel_id: build_panel(panel_id, sources).verification_state
                for panel_id in PANEL_IDS
            }
            payload["warnings"] = list(reader.warnings)
        return payload

    @app.get("/ui/panels/{panel_id}")
    def get_panel(panel_id: str, project_id: str) -> dict[str, Any]:
        if panel_id not in PANEL_IDS:
            raise HTTPException(status_code=404, detail=f"unknown panel: {panel_id}")
        sources = reader.collect(project_id)
        projection = build_panel(panel_id, sources)
        payload = projection.model_dump(mode="json")
        payload["warnings"] = list(reader.warnings)
        return payload

    @app.get("/ui/review-report")
    def review_report(project_id: str) -> dict[str, Any]:
        sources = reader.collect(project_id)
        state = _run_state(sources)
        section = build_review_report_section(state)
        return {
            "project_id": project_id,
            "section": section.model_dump(mode="json"),
        }

    app.mount("/api", create_api(runtime))

    root = web_root or default_web_root()
    if root.is_dir():
        app.mount("/", StaticFiles(directory=str(root), html=True), name="web")
    return app
