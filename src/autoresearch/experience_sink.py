"""S4-A2 experience wiring: failure events -> failure-experience records.

Design note D-A6-01 -- why this is a pull and not a subscription hook
--------------------------------------------------------------------
The package specification asks for an event *hook* over interception events.
The interception events that matter here are appended inside paths this
package may not touch:

* ``evidence.candidate_blocked``  -> ``autoresearch/audit_evidence.py`` (B lane)
* ``audit_evidence.report_created`` -> ``autoresearch/audit_evidence.py`` (B lane)
* ``audit.report_created``        -> ``autoresearch/audit.py`` (A3 runtime)

No producer can host a hook owned by this package, so the hook is implemented
as a **read-only pull over the persisted audit event log**
(``RecordStore.events(project_id)``). The sink never writes to the audit
chain, never edits a producer, and never raises into its caller: an
unavailable event log or a malformed payload degrades into a diagnostic.

The event log is therefore the interface. Event names and payload keys read
here are treated as the frozen contract, so this module imports no producer
module (only ``contracts``, ``storage`` and the ``ExperienceService`` type).

Design note D-A6-02 -- consumption markers
-----------------------------------------
There is no event-level replay/subscribe abstraction in the repository; the
only durable ledger is the A1/A2 ``idempotency`` table. Consumption markers
are stored there under scope ``experience_sink`` keyed by ``event_id``, so a
second ``settle`` call over an unchanged log records nothing.

``recurrence_count`` is *derived*, never incremented: it is
``1 + (consumed markers sharing this cause)``. Deriving it makes a crashed
run self-healing -- an experience damaged by a crash is rewritten with the
same count instead of being counted twice.

Design note D-A6-03 -- stays below the four promotion gates
----------------------------------------------------------
The sink writes ``grade=EvidenceGrade.E0`` for every record it creates, never
calls ``ExperienceService.promote``, and carries an existing record's
``grade``/``promoted`` values forward unchanged when it merges into one. The
four gates (``recurrence_count >= 2`` AND ``grade in {E2, E3, H3}`` AND
``reviewer_approved`` AND ``human_approved``) remain the only way up.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from autoresearch.contracts import EvidenceGrade, ExperienceRecord
from autoresearch.evolution_service import ExperienceService
from autoresearch.storage import RecordStore

SINK_SCOPE = "experience_sink"

TECHNIQUE_EVIDENCE_BLOCKED = "evidence_admission_blocked"
TECHNIQUE_AUDIT_EVIDENCE_REMEDIATION = "audit_evidence_remediation"
TECHNIQUE_AUDIT_UNKNOWN_RESOLUTION = "audit_unknown_resolution"

# The interception->experience mapping tags every record it writes (TASK-SPECS
# A6). It is the shared vocabulary for "this record is an archived failure":
# B6 archives rejected / blind-reviewed-back drafts as failure experiences too,
# so the word lives in the shared schema and both producers fill it in.
FAILURE_TAG = "failure"

# Frozen event-log contract for `audit_evidence.report_created` payloads
# (producer enum `audit_evidence.AuditStatus`: pass / fail / unknown).
_AUDIT_EVIDENCE_FAILURE_STATUSES = frozenset({"fail", "unknown"})


class MalformedEventPayload(ValueError):
    """A mapped interception event carries a payload this sink cannot read."""


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def _string_list(value: Any) -> list[str]:
    """Read a list-of-strings payload field defensively.

    A producer that changes the field to a bare string, a dict or ``None``
    must not turn into per-character garbage or a crash.
    """

    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if str(item).strip()]


def _recurrence_key(technique: str, problem: str) -> str:
    """Cause identity. Frozen fields only -- never the event id or a counter."""

    return f"{technique}|{_normalize(problem)}"


def _experience_id(project_id: str, recurrence_key: str) -> str:
    digest = hashlib.sha256(f"{project_id}|{recurrence_key}".encode()).hexdigest()
    return f"exp_{digest[:16]}"


@dataclass(frozen=True)
class _RuleMatch:
    technique: str
    problem: str
    outcome: str
    source_ref: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class FailureCause:
    """A mapped failure event, before any write happens."""

    event_id: str
    event_type: str
    technique: str
    problem: str
    outcome: str
    source_ref: str = ""
    evidence_ids: tuple[str, ...] = ()

    @property
    def recurrence_key(self) -> str:
        return _recurrence_key(self.technique, self.problem)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "technique": self.technique,
            "problem": self.problem,
            "outcome": self.outcome,
            "source_ref": self.source_ref,
            "evidence_ids": list(self.evidence_ids),
            "recurrence_key": self.recurrence_key,
        }


@dataclass(frozen=True)
class SinkSettlement:
    """Outcome of one ``settle`` call."""

    project_id: str
    scanned_events: int = 0
    failure_events: int = 0
    consumed: int = 0
    recorded: int = 0
    unreadable: int = 0
    recordings: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    @property
    def degraded(self) -> bool:
        return bool(self.diagnostics)

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "scanned_events": self.scanned_events,
            "failure_events": self.failure_events,
            "consumed": self.consumed,
            "recorded": self.recorded,
            "unreadable": self.unreadable,
            "recordings": list(self.recordings),
            "diagnostics": list(self.diagnostics),
            "degraded": self.degraded,
        }


def _iter_verdicts(payload: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    for key in ("deterministic_verdicts", "model_assisted_verdicts"):
        for verdict in payload.get(key) or []:
            if isinstance(verdict, Mapping):
                yield verdict


def _report_evidence_ids(payload: Mapping[str, Any]) -> tuple[str, ...]:
    collected: set[str] = set()
    for admission in payload.get("admission_results") or []:
        if isinstance(admission, Mapping) and admission.get("evidence_id"):
            collected.add(str(admission["evidence_id"]))
    for verdict in _iter_verdicts(payload):
        for evidence_id in _string_list(verdict.get("evidence_ids")):
            collected.add(evidence_id)
    return tuple(sorted(collected))


def _parse_candidate_blocked(payload: Mapping[str, Any]) -> _RuleMatch | None:
    candidate_id = str(payload.get("candidate_id") or "")
    reasons = _string_list(payload.get("reasons"))
    return _RuleMatch(
        technique=TECHNIQUE_EVIDENCE_BLOCKED,
        problem="; ".join(reasons) or "evidence candidate was blocked without a recorded reason",
        outcome=(
            f"evidence candidate {candidate_id or 'unknown'} blocked at admission "
            f"({len(reasons)} reason(s))"
        ),
        source_ref=candidate_id,
    )


def _parse_audit_evidence_report(payload: Mapping[str, Any]) -> _RuleMatch | None:
    status = _normalize(str(payload.get("status") or ""))
    if status not in _AUDIT_EVIDENCE_FAILURE_STATUSES:
        return None
    report_id = str(payload.get("report_id") or "")
    unverified = _string_list(payload.get("unverified_claims"))
    verdict_reasons = [
        str(reason)
        for verdict in _iter_verdicts(payload)
        for reason in _string_list(verdict.get("reasons"))
    ]
    problem = (
        unverified[0]
        if unverified
        else (
            verdict_reasons[0]
            if verdict_reasons
            else f"audit evidence report finished with status {status}"
        )
    )
    technique = (
        TECHNIQUE_AUDIT_EVIDENCE_REMEDIATION
        if status == "fail"
        else TECHNIQUE_AUDIT_UNKNOWN_RESOLUTION
    )
    return _RuleMatch(
        technique=technique,
        problem=problem,
        outcome=(
            f"audit evidence report {report_id or 'unknown'} status={status} "
            f"({len(unverified)} unverified claim(s))"
        ),
        source_ref=report_id,
        evidence_ids=_report_evidence_ids(payload),
    )


def _parse_audit_report(payload: Mapping[str, Any]) -> _RuleMatch | None:
    try:
        unknown_count = int(payload.get("unknown_count") or 0)
    except (TypeError, ValueError):
        unknown_count = 0
    if unknown_count <= 0:
        return None
    report_id = str(payload.get("report_id") or "")
    return _RuleMatch(
        technique=TECHNIQUE_AUDIT_UNKNOWN_RESOLUTION,
        problem=f"audit runtime produced {unknown_count} unknown verdict(s) that need evidence",
        outcome=(
            f"audit report {report_id or 'unknown'} finished with {unknown_count} unknown "
            f"verdict(s) of {payload.get('verdict_count')}"
        ),
        source_ref=report_id or str(payload.get("artifact_id") or ""),
    )


#: Mapping table from interception event type to failure cause (the deliverable).
MAPPING_RULES: dict[str, Callable[[Mapping[str, Any]], _RuleMatch | None]] = {
    "evidence.candidate_blocked": _parse_candidate_blocked,
    "audit_evidence.report_created": _parse_audit_evidence_report,
    "audit.report_created": _parse_audit_report,
}


class ExperienceSink:
    """Consume failure events from the audit log and settle them as experiences."""

    def __init__(self, store: RecordStore, experiences: ExperienceService):
        self.store = store
        self.experiences = experiences

    # -- observation ----------------------------------------------------

    def failure_causes(
        self,
        project_id: str,
        *,
        unconsumed_only: bool = True,
    ) -> list[FailureCause]:
        """Map failure events to causes without writing anything."""

        consumed = self._consumed_event_ids() if unconsumed_only else set()
        causes: list[FailureCause] = []
        for event in self._events(project_id):
            if event["event_type"] not in MAPPING_RULES:
                continue
            if event["event_id"] in consumed:
                continue
            try:
                match = self._match(event)
            except MalformedEventPayload:
                continue
            if match is None:
                continue
            causes.append(
                FailureCause(
                    event_id=event["event_id"],
                    event_type=event["event_type"],
                    technique=match.technique,
                    problem=match.problem,
                    outcome=match.outcome,
                    source_ref=match.source_ref,
                    evidence_ids=match.evidence_ids,
                )
            )
        return causes

    # -- settlement -----------------------------------------------------

    def settle(self, project_id: str) -> SinkSettlement:
        """Consume new failure events and merge them into experience records.

        Never raises: an unavailable log, a malformed payload or a rejected
        write becomes a diagnostic and the remaining events are still handled.
        """

        diagnostics: list[str] = []
        try:
            events = self._events(project_id)
        except Exception as exc:  # noqa: BLE001 - degradation is the contract
            return SinkSettlement(
                project_id=project_id,
                diagnostics=[
                    "experience sink degraded: audit event log unavailable for "
                    f"{project_id} ({exc.__class__.__name__}: {exc})"
                ],
            )

        consumed: set[str] = set()
        try:
            consumed = self._consumed_event_ids()
        except Exception as exc:  # noqa: BLE001 - degradation is the contract
            diagnostics.append(
                "experience sink degraded: consumption markers unavailable "
                f"({exc.__class__.__name__}: {exc})"
            )

        failure_events = [event for event in events if event["event_type"] in MAPPING_RULES]
        fresh = [event for event in failure_events if event["event_id"] not in consumed]

        settlement = SinkSettlement(
            project_id=project_id,
            scanned_events=len(events),
            failure_events=len(failure_events),
        )
        recordings: list[str] = []
        for event in fresh:
            event_id = event["event_id"]
            event_type = event["event_type"]
            try:
                match = self._match(event)
            except MalformedEventPayload as exc:
                diagnostics.append(
                    f"experience sink degraded: unreadable {event_type} payload "
                    f"{event_id} ({exc})"
                )
                self._consume(event_id, event_type, project_id, None)
                settlement = _replace(
                    settlement,
                    consumed=settlement.consumed + 1,
                    unreadable=settlement.unreadable + 1,
                )
                continue
            if match is None:
                self._consume(event_id, event_type, project_id, None)
                settlement = _replace(settlement, consumed=settlement.consumed + 1)
                continue
            recurrence_key = _recurrence_key(match.technique, match.problem)
            experience_id = _experience_id(project_id, recurrence_key)
            recurrence = self._recurrence_count(recurrence_key) + 1
            record = self._merge_records(
                project_id=project_id,
                experience_id=experience_id,
                match=match,
                recurrence=recurrence,
            )
            try:
                self.experiences.record(record)
            except Exception as exc:  # noqa: BLE001 - degradation is the contract
                diagnostics.append(
                    "experience sink degraded: could not record experience "
                    f"{experience_id} for {event_type} {event_id} "
                    f"({exc.__class__.__name__}: {exc})"
                )
                continue
            self._consume(
                event_id,
                event_type,
                project_id,
                {
                    "recurrence_key": recurrence_key,
                    "recurrence_count": recurrence,
                    "technique": match.technique,
                    "experience_id": experience_id,
                },
            )
            if experience_id not in recordings:
                recordings.append(experience_id)
            settlement = _replace(
                settlement,
                consumed=settlement.consumed + 1,
                recorded=settlement.recorded + 1,
            )

        return _replace(
            settlement,
            recordings=recordings,
            diagnostics=diagnostics,
        )

    # -- internals ------------------------------------------------------

    def _events(self, project_id: str) -> list[dict[str, Any]]:
        return [
            {
                "event_id": str(event.get("event_id") or ""),
                "event_type": str(event.get("event_type") or ""),
                "payload": event.get("payload"),
            }
            for event in self.store.events(project_id)
        ]

    def _match(self, event: Mapping[str, Any]) -> _RuleMatch | None:
        """Return the mapped cause, ``None`` when the event is not a failure.

        Raises ``MalformedEventPayload`` when a *mapped* event carries a payload
        the rule cannot read; callers decide whether that degrades or skips.
        """

        parser = MAPPING_RULES.get(str(event.get("event_type")))
        if parser is None:
            return None
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            raise MalformedEventPayload(
                f"payload is {type(payload).__name__}, expected a JSON object"
            )
        return parser(payload)

    def _consumed_event_ids(self) -> set[str]:
        return {
            str(entry.get("idempotency_key") or "")
            for entry in self.store.list_idempotent(SINK_SCOPE)
        }

    def _recurrence_count(self, recurrence_key: str) -> int:
        """Count consumed events sharing this cause.

        Unreadable markers degrade to 0 (cause treated as a first occurrence)
        instead of aborting the settlement: the count is derived, so the next
        healthy settlement recomputes the true value.
        """

        try:
            entries = self.store.list_idempotent(SINK_SCOPE)
        except Exception:  # noqa: BLE001 - degradation is the contract
            return 0
        count = 0
        for entry in entries:
            record = entry.get("record")
            if (
                isinstance(record, Mapping)
                and record.get("mapped") is True
                and record.get("recurrence_key") == recurrence_key
            ):
                count += 1
        return count

    def _consume(
        self,
        event_id: str,
        event_type: str,
        project_id: str,
        marker: Mapping[str, Any] | None,
    ) -> None:
        payload: dict[str, Any] = {
            "event_id": event_id,
            "event_type": event_type,
            "project_id": project_id,
            "mapped": marker is not None,
        }
        payload.update(marker or {})
        self.store.remember_idempotent(SINK_SCOPE, event_id, payload)

    def _merge_records(
        self,
        *,
        project_id: str,
        experience_id: str,
        match: _RuleMatch,
        recurrence: int,
    ) -> ExperienceRecord:
        raw = self.store.get("experience", experience_id)
        if raw is None:
            return ExperienceRecord(
                experience_id=experience_id,
                project_id=project_id,
                problem=match.problem,
                technique=match.technique,
                outcome=match.outcome,
                grade=EvidenceGrade.E0,
                recurrence_count=max(1, recurrence),
                evidence_ids=list(match.evidence_ids),
                tags=[FAILURE_TAG],
                promoted=False,
            )
        existing = ExperienceRecord.model_validate(raw)
        # grade and promoted are carried over untouched (D-A6-03): the sink can
        # raise recurrence_count, never a promotion or an evidence grade.
        return existing.model_copy(
            update={
                "problem": match.problem,
                "technique": match.technique,
                "outcome": match.outcome,
                "recurrence_count": max(existing.recurrence_count, recurrence),
                "evidence_ids": sorted({*existing.evidence_ids, *match.evidence_ids}),
                # union, not replace: a merge also heals a record written before
                # the tag existed, and never drops a tag someone else added.
                "tags": sorted({*existing.tags, FAILURE_TAG}),
            }
        )


def _replace(settlement: SinkSettlement, **changes: Any) -> SinkSettlement:
    return SinkSettlement(
        project_id=changes.get("project_id", settlement.project_id),
        scanned_events=changes.get("scanned_events", settlement.scanned_events),
        failure_events=changes.get("failure_events", settlement.failure_events),
        consumed=changes.get("consumed", settlement.consumed),
        recorded=changes.get("recorded", settlement.recorded),
        unreadable=changes.get("unreadable", settlement.unreadable),
        recordings=changes.get("recordings", settlement.recordings),
        diagnostics=changes.get("diagnostics", settlement.diagnostics),
    )


__all__ = [
    "FAILURE_TAG",
    "MAPPING_RULES",
    "SINK_SCOPE",
    "TECHNIQUE_AUDIT_EVIDENCE_REMEDIATION",
    "TECHNIQUE_AUDIT_UNKNOWN_RESOLUTION",
    "TECHNIQUE_EVIDENCE_BLOCKED",
    "ExperienceSink",
    "FailureCause",
    "MalformedEventPayload",
    "SinkSettlement",
]
