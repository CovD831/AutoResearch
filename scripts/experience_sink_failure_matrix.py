#!/usr/bin/env python3
"""Exercise ``ExperienceSink.settle`` under every failure combination.

    python scripts/experience_sink_failure_matrix.py

**Why this exists.** ``settle`` performs several writes in sequence -- claim the
event, write the experience record, promote the claim -- and changing that order
*moves* the failure window rather than closing it. It was changed twice in one
sitting, and each version introduced a different failure mode (a duplicated
audit page in one, a permanently lost failure in the other). Two- and
three-way combinations like "claim succeeded, record failed, and the release
failed too" are not something you notice by reading; they have to be enumerated.

So this script enumerates them: for every subset of {claim, record, release}
that can fail, it injects exactly those failures, then restores the sinks and
asserts the two invariants that matter:

1. **no failure is lost** -- once the dependencies recover, every mapped event
   is eventually archived;
2. **no work is duplicated** -- the audit chain never gains a second page for a
   single failure, and no settlement ever exceeds the fixture's page count.

Exit status is non-zero if any row fails, so it can be wired into a pre-change
checklist for this module.
"""

from __future__ import annotations

import json
import sys
import tempfile
from itertools import combinations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from autoresearch.application import AutoResearchApplication  # noqa: E402
from autoresearch.config import Settings  # noqa: E402
from autoresearch.contracts import ProjectCreate  # noqa: E402
from autoresearch.experience_sink import SINK_SCOPE, ExperienceSink  # noqa: E402
from autoresearch.storage import RecordStore  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "experience_sink" / "event_log.json"

#: The fixture's shape, asserted so a drifting fixture fails loudly instead of
#: making the invariants vacuous.
EXPECTED_RECORDINGS = 6
EXPECTED_UNIQUE_EXPERIENCES = 5
EXPECTED_PAGE_ADDED = 6

ACTIONS = ("claim", "record", "release")


def _runtime(tmp: Path) -> AutoResearchApplication:
    settings = Settings(
        _env_file=None,
        LLM_PROVIDER="offline",
        AUTORESEARCH_DATA_DIR=tmp / "var",
        AUTORESEARCH_DB_PATH=tmp / "var" / "autoresearch.sqlite3",
        AUTORESEARCH_CHECKPOINT_PATH=tmp / "var" / "checkpoints.sqlite3",
        AUTORESEARCH_PROJECTS_DIR=tmp / "paper-projects",
        AUTORESEARCH_TEMPLATE_DIR=REPO_ROOT / "paper-projects" / "_template",
        AUTORESEARCH_NETWORK_ENABLED=False,
    )
    application = AutoResearchApplication(settings)
    application.create_project(
        ProjectCreate(project_id="demo", title="Failure matrix", idea="Enumerate failures.")
    )
    return application


def _seed(application: AutoResearchApplication) -> None:
    for event in json.loads(FIXTURE.read_text(encoding="utf-8"))["events"]:
        application.store.append_event(
            event["event_type"], event["payload"], project_id="demo", actor=event["actor"]
        )


def _records(application: AutoResearchApplication) -> list[dict]:
    return application.store.list("experience", project_id="demo", partition="experiences")


def _page_added(application: AutoResearchApplication) -> int:
    return sum(
        1
        for event in application.store.events("demo")
        if event["event_type"] == "knowledge.page_added"
    )


def _break(application: AutoResearchApplication, action: str) -> None:
    def explode(*_args, **_kwargs):
        raise RuntimeError(f"injected {action} failure")

    if action == "claim":
        # The claim is the reservation; its promotion is the finalize.
        application.store.reserve_idempotent = explode  # type: ignore[method-assign]
    elif action == "record":
        application.experiences.record = explode  # type: ignore[method-assign]
    else:
        application.store.finalize_idempotent = explode  # type: ignore[method-assign]


def _restore(application: AutoResearchApplication) -> None:
    store_cls = type(application.store)
    application.store.reserve_idempotent = (  # type: ignore[method-assign]
        store_cls.reserve_idempotent.__get__(application.store, store_cls)
    )
    application.store.finalize_idempotent = (  # type: ignore[method-assign]
        store_cls.finalize_idempotent.__get__(application.store, store_cls)
    )
    application.store.delete_idempotent = (  # type: ignore[method-assign]
        store_cls.delete_idempotent.__get__(application.store, store_cls)
    )
    application.experiences.record = (  # type: ignore[method-assign]
        type(application.experiences).record.__get__(
            application.experiences, type(application.experiences)
        )
    )


def run_case(broken: tuple[str, ...]) -> tuple[bool, str]:
    """Inject ``broken``, then recover, and check both invariants."""

    with tempfile.TemporaryDirectory() as tmpdir:
        application = _runtime(Path(tmpdir))
        try:
            sink = ExperienceSink(application.store, application.experiences)
            _seed(application)

            for action in broken:
                _break(application, action)
            first = sink.settle("demo")
            _restore(application)

            # Settle until quiescent: a failure injected into an early action can
            # need more than one retry to drain.
            for _ in range(4):
                if sink.settle("demo").consumed == 0:
                    break

            records = _records(application)
            pages = _page_added(application)
            counts = sorted(record["recurrence_count"] for record in records)

            if len(records) != EXPECTED_UNIQUE_EXPERIENCES:
                return False, f"lost failures: {len(records)} != {EXPECTED_UNIQUE_EXPERIENCES}"
            if pages != EXPECTED_PAGE_ADDED:
                return False, f"duplicated audit pages: {pages} != {EXPECTED_PAGE_ADDED}"
            if counts != sorted([1, 1, 1, 1, 2]):
                return False, f"counts drifted: {counts}"
            pending = [
                marker
                for marker in application.store.list_idempotent(SINK_SCOPE)
                if marker["record"].get("mapped") is True
                and marker["record"].get("state") != "finalized"
            ]
            if pending:
                return False, f"{len(pending)} claim(s) left unsettled after recovery"
            return True, f"first-attempt degraded={first.degraded}, recovered cleanly"
        finally:
            application.close()


def main() -> int:
    failures = 0
    print(f"{'injected failures':<34} {'result'}")
    print("-" * 78)
    for size in range(1, len(ACTIONS) + 1):
        for broken in combinations(ACTIONS, size):
            ok, detail = run_case(broken)
            label = " + ".join(broken)
            print(f"{label:<34} {'PASS' if ok else 'FAIL'}  {detail}")
            if not ok:
                failures += 1
    print("-" * 78)
    total = sum(len(list(combinations(ACTIONS, n))) for n in range(1, len(ACTIONS) + 1))
    print(f"{total - failures}/{total} combinations hold both invariants")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
