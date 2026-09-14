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

#: Consumption-marker lifecycle, matching the A1/A2 idempotency vocabulary
#: (``reserve_idempotent`` writes ``pending``, ``finalize_idempotent`` promotes
#: to ``finalized``). Only ``finalized`` markers count as consumed or contribute
#: to ``recurrence_count``; a ``pending`` marker means "retry me", which is what
#: keeps a failed release (or a crash between claim and record) from losing an
#: event (D-A6-06c).
PENDING_STATE = "pending"
FINALIZED_STATE = "finalized"

#: Phase written once the experience record exists but before the claim is
#: finalized. Its presence is proof that ``record`` already ran, so a retry can
#: promote the claim without recording again (D-A6-11). This mirrors the A1/A2
#: ``reserved -> service_started -> service_returned`` vocabulary, where
#: ``service_started`` means "the external call was made".
RECORDED_PHASE = "service_started"

#: Upper bound on ``SinkSettlement.diagnostics`` detail. Counts stay exact; only
#: the prose is truncated, so a batch of unreadable payloads cannot bury the
#: diagnostics that actually differ (D-A6-10).
MAX_DIAGNOSTICS = 50

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


def _marker_fields(record: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return the sink's own payload from a marker record, wherever it sits.

    ``reserve_idempotent`` stores its argument under ``request`` and
    ``finalize_idempotent`` stores its argument under ``result`` while keeping the
    reservation's other keys. A marker describing an archived failure therefore
    has its sink fields in ``result``; a marker whose finalize never ran has them
    in ``request``. Reading only one of the two silently yields ``None`` for every
    field -- which is how the recurrence counter came back as all-first-
    occurrences while looking perfectly healthy (D-A6-11).
    """

    if not isinstance(record, Mapping):
        return {}
    for key in ("result", "request"):
        nested = record.get(key)
        if isinstance(nested, Mapping) and nested:
            return nested
    return record


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

        # Unreadable consumption markers must **abort the settlement**, not
        # degrade to "nothing was consumed".
        #
        # Treating an unreadable marker table as an empty one makes every event
        # look fresh, so the whole log is replayed: ``record`` runs again for
        # every cause and appends another ``knowledge.page_added`` per event.
        # Measured on the fixture: a healthy settlement adds 6 pages, one
        # degraded settlement takes the total to 12, the next to 18 -- i.e. the
        # degradation *itself* duplicates the audit chain, which is the exact
        # failure this module was hardened against (D-A6-06b).
        #
        # Aborting is safe here in a way it is not for the event log: the caller
        # simply retries, and no side effect has been produced.
        try:
            markers = self.store.list_idempotent(SINK_SCOPE)
        except Exception as exc:  # noqa: BLE001 - degradation is the contract
            return SinkSettlement(
                project_id=project_id,
                scanned_events=len(events),
                diagnostics=[
                    "experience sink degraded: consumption markers unavailable for "
                    f"{project_id} ({exc.__class__.__name__}: {exc}); settlement "
                    "aborted rather than replaying the log"
                ],
            )

        consumed: set[str] = set()
        #: Event ids whose record step already happened. A marker left at phase
        #: ``recorded`` by an earlier settlement whose finalize failed is proof
        #: that ``record`` ran -- retrying it would append a second audit page for
        #: one failure (D-A6-11).
        recorded_this_run: set[str] = set()
        for entry in markers:
            record = entry.get("record") or {}
            fields = _marker_fields(record)
            key = str(entry.get("idempotency_key") or "")
            if record.get("state") == FINALIZED_STATE:
                consumed.add(key)
            elif fields.get("mapped") is True and record.get("phase") == RECORDED_PHASE:
                recorded_this_run.add(key)

        failure_events = [event for event in events if event["event_type"] in MAPPING_RULES]
        fresh = [event for event in failure_events if event["event_id"] not in consumed]

        # Per-settlement accumulator: how many events this run has already
        # settled for each cause. Needed because ``recurrence_count`` is derived
        # from *consumed markers*, and a marker for event N only exists after
        # event N is settled -- so a second event with the same cause inside one
        # settlement must see the first one through this counter, not through the
        # store. Without it the count is wrong whenever two same-cause events land
        # in the same batch (D-A6-06).
        settled_in_run: dict[str, int] = {}
        #: Event ids this settlement has already promoted, so a single pass cannot
        #: record one event twice.
        settled_this_run: set[str] = set()
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
                # A payload we cannot read is *not* a settlement. Leaving the
                # event unconsumed keeps it for a retry -- the same treatment the
                # write-failure path below gets. Consuming it here would drop the
                # failure permanently: the sink's whole job is archiving failures,
                # so silently discarding one is the worst possible degradation
                # (D-A6-08). ``unreadable`` still counts it, so the operator sees
                # that something was skipped rather than settled.
                diagnostics.append(
                    f"experience sink degraded: unreadable {event_type} payload "
                    f"{event_id} left unconsumed for retry ({exc})"
                )
                settlement = _replace(settlement, unreadable=settlement.unreadable + 1)
                continue
            if match is None:
                # A decoy that maps to no failure cause has nothing to archive, so
                # consuming it *is* its terminal state -- written straight to
                # finalized in one shot (there is no record step to protect).
                try:
                    self.store.reserve_idempotent(
                        SINK_SCOPE,
                        event_id,
                        {
                            "event_id": event_id,
                            "event_type": event_type,
                            "project_id": project_id,
                            "mapped": False,
                        },
                    )
                    self.store.finalize_idempotent(
                        SINK_SCOPE,
                        event_id,
                        {
                            "event_id": event_id,
                            "event_type": event_type,
                            "project_id": project_id,
                            "mapped": False,
                            "reason": "not a failure",
                        },
                    )
                except Exception as marker_exc:  # noqa: BLE001 - degradation is the contract
                    diagnostics.append(
                        "experience sink degraded: could not mark event "
                        f"{event_id} as consumed ({marker_exc.__class__.__name__}: {marker_exc})"
                    )
                    continue
                settlement = _replace(settlement, consumed=settlement.consumed + 1)
                continue
            recurrence_key = _recurrence_key(match.technique, match.problem)
            experience_id = _experience_id(project_id, recurrence_key)
            recurrence = (
                max(
                    self._recurrence_count(project_id, recurrence_key),
                    settled_in_run.get(recurrence_key, 0),
                )
                + 1
            )
            # Two-phase claim, using the A1/A2 primitives the rest of the
            # repository already relies on (D-A6-06c).
            #
            # Recording before claiming meant a claim-write failure left the
            # record written *and* the event unconsumed, so the retry ran
            # ``record`` twice and appended a second ``knowledge.page_added``.
            # Claiming first closes that, but then the claim has to be released
            # when the record fails -- and a failed release used to leave a marker
            # indistinguishable from a finished one, losing the failure for good.
            #
            # Claims are therefore ``pending``, and only a *finalized* marker
            # counts as consumed. Because ``finalize`` is a single conditional
            # UPDATE of an existing row, promotion cannot be half-done the way a
            # delete-then-insert can -- and a marker that never reaches
            # ``finalized`` is simply retried.
            try:
                self.store.reserve_idempotent(
                    SINK_SCOPE,
                    event_id,
                    {
                        "event_id": event_id,
                        "event_type": event_type,
                        "project_id": project_id,
                        "mapped": True,
                        "recurrence_key": recurrence_key,
                        "recurrence_count": recurrence,
                        "technique": match.technique,
                        "experience_id": experience_id,
                    },
                )
            except Exception as marker_exc:  # noqa: BLE001 - degradation is the contract
                diagnostics.append(
                    "experience sink degraded: could not claim event "
                    f"{event_id} ({marker_exc.__class__.__name__}: {marker_exc})"
                )
                continue
            record = self._merge_records(
                project_id=project_id,
                experience_id=experience_id,
                match=match,
                recurrence=recurrence,
            )
            if event_id in recorded_this_run:
                # A previous settlement recorded this event but could not
                # finalize it; skip straight to the promotion. Re-running
                # ``record`` would append a second audit page for one failure.
                pass
            else:
                try:
                    self.experiences.record(record)
                except Exception as exc:  # noqa: BLE001 - degradation is the contract
                    # Drop the claim so the next settlement retries cleanly. If
                    # this fails too the claim stays ``pending``, and pending is
                    # not treated as consumed -- so the retry happens either way.
                    try:
                        self.store.delete_idempotent(SINK_SCOPE, event_id)
                    except Exception as release_exc:  # noqa: BLE001 - degradation is the contract
                        diagnostics.append(
                            "experience sink degraded: could not release claim on "
                            f"{event_id} after a failed record "
                            f"({release_exc.__class__.__name__}: {release_exc}); the "
                            "claim stays pending and the event will be retried"
                        )
                    diagnostics.append(
                        "experience sink degraded: could not record experience "
                        f"{experience_id} for {event_type} {event_id} "
                        f"({exc.__class__.__name__}: {exc})"
                    )
                    continue
                # Mark the record step done *before* finalizing. This is what
                # makes the retry skippable: if the finalize below fails, the
                # next settlement sees ``service_started`` and knows the write
                # already happened, so it promotes without recording again
                # (D-A6-11).
                try:
                    self.store.mark_idempotent_phase(SINK_SCOPE, event_id, "service_started")
                except Exception as phase_exc:  # noqa: BLE001 - degradation is the contract
                    diagnostics.append(
                        "experience sink degraded: could not mark the record step on "
                        f"{event_id} ({phase_exc.__class__.__name__}: {phase_exc}); "
                        "the event will be re-recorded, which may duplicate one audit page"
                    )
            # Only now is the event actually settled. ``finalize`` rewrites the
            # pending row in place; if it fails the marker stays pending, so the
            # event is re-settled later. That rerun rewrites the same experience
            # row (upsert on a derived id) and re-appends one page -- which is why
            # the check below refuses to call ``record`` twice within one
            # settlement, and why a rerun is bounded to one extra attempt rather
            # than accumulating.
            if event_id in settled_this_run:
                # Defensive: the claim was already promoted in this settlement.
                continue
            try:
                self.store.finalize_idempotent(
                    SINK_SCOPE,
                    event_id,
                    {
                        # Identity fields are repeated here on purpose: the
                        # finalize payload lands under ``result`` and becomes the
                        # one a reader finds first, so anything the marker needs
                        # to be interpretable has to be in this dict too -- not
                        # only in the reservation (D-A6-11).
                        "event_id": event_id,
                        "event_type": event_type,
                        "project_id": project_id,
                        "mapped": True,
                        "recurrence_key": recurrence_key,
                        "recurrence_count": recurrence,
                        "technique": match.technique,
                        "experience_id": experience_id,
                    },
                )
            except Exception as settle_exc:  # noqa: BLE001 - degradation is the contract
                diagnostics.append(
                    "experience sink degraded: could not finalize claim on "
                    f"{event_id} ({settle_exc.__class__.__name__}: {settle_exc}); "
                    "it stays pending and will be re-settled"
                )
                continue
            settled_in_run[recurrence_key] = recurrence
            settled_this_run.add(event_id)
            if experience_id not in recordings:
                recordings.append(experience_id)
            settlement = _replace(
                settlement,
                consumed=settlement.consumed + 1,
                recorded=settlement.recorded + 1,
            )

        # A settlement that skips many events produces one diagnostic each, and
        # the list is returned to the caller verbatim. Left unbounded, one bad
        # batch of 200 unreadable payloads turns the settlement report into
        # 200 near-identical lines (~32 KB measured) and buries the diagnostics
        # that differ. Cap the detail and keep the counts authoritative: the
        # totals in ``unreadable`` / ``consumed`` / ``recorded`` stay exact, only
        # the prose is truncated (D-A6-10).
        if len(diagnostics) > MAX_DIAGNOSTICS:
            omitted = len(diagnostics) - MAX_DIAGNOSTICS
            diagnostics = diagnostics[:MAX_DIAGNOSTICS] + [
                f"experience sink degraded: {omitted} further diagnostic(s) omitted; "
                "see unreadable/consumed/recorded for exact counts"
            ]
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
        """Event ids whose settlement is **finalized**, not merely claimed.

        A claim is written ``pending`` (``reserve_idempotent``) and promoted to
        ``finalized`` (``finalize_idempotent``) only after its experience record
        is durable, so a claim abandoned by a crash or a failed release is not
        mistaken for finished work (D-A6-06c).
        """

        return {
            str(entry.get("idempotency_key") or "")
            for entry in self.store.list_idempotent(SINK_SCOPE)
            if (entry.get("record") or {}).get("state") == FINALIZED_STATE
        }

    def _recurrence_count(self, project_id: str, recurrence_key: str) -> int:
        """Count events already archived as this cause, in this project.

        A marker counts when the experience record exists -- i.e. it is
        ``finalized``, **or** it is still ``pending`` but has reached the
        ``recorded`` phase. That second case matters: when the finalize step
        fails, the record is already written and the failure *is* archived, so
        omitting it would under-count and could hold the ``recurrence_count >= 2``
        promotion gate shut even though the recurrence genuinely happened
        (D-A6-11).

        A marker with no record step at all (plain ``pending``) is work that has
        not happened and is excluded -- counting it would let the gate be
        satisfied by failures that were never archived (D-A6-06c).

        Unlike a first version, an unreadable marker table is *not* degraded to
        0 here: that made every record look like a first occurrence and silently
        held the promotion gate shut, while ``recorded`` stayed identical to the
        healthy run so the report looked normal (D-A6-06). ``settle`` reads the
        markers once, up front, and aborts the whole settlement if that read
        fails (D-A6-06b), so by the time this runs the table is known readable.
        The read here is therefore a plain one -- a failure would be a genuine
        bug rather than an anticipated degradation, and is left to propagate.
        """

        entries = self.store.list_idempotent(SINK_SCOPE)
        count = 0
        for entry in entries:
            record = entry.get("record")
            if not isinstance(record, Mapping):
                continue
            archived = record.get("state") == FINALIZED_STATE or (
                record.get("state") == PENDING_STATE
                and record.get("phase") == RECORDED_PHASE
            )
            if not archived:
                continue
            # The sink's fields live under ``request`` (reserved) or ``result``
            # (finalized), never at the top level.
            fields = _marker_fields(record)
            if (
                fields.get("mapped") is True
                and fields.get("project_id") == project_id
                and fields.get("recurrence_key") == recurrence_key
            ):
                count += 1
        return count

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
