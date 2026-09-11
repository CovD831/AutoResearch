# S4-A2 Handoff

## Snapshot

- Branch: `codex/s4-a2-experience-wiring`
- Base: `origin/main@66aba64` (the local `main` ref still sits at `380bd49` and was deliberately **not** touched)
- Status: implemented and verified on the AI side, `handoff`; **not pushed, no PR opened** (per instruction)
- Worktree: `F:\AutoResearch\.worktrees\s4-a2-experience-wiring`, own venv (`.venv`, python 3.12.13)

## Delivered files

- `src/autoresearch/experience_sink.py` (new, 199 statements)
- `src/autoresearch/application.py` (+13: import, `self.experience_sink`, `settle_failure_experiences`)
- `src/autoresearch/api.py` (+8: `POST /projects/{project_id}/experiences/settle`)
- `src/autoresearch/cli.py` (+23: `settle-experiences` with `--dry-run`)
- `tests/test_experience_sink.py` (new, 22 tests)
- `tests/fixtures/experience_sink/event_log.json` (new, 9 frozen events)
- `docs/tasks/P1-A-runtime-lane/tasks/A6-experience-wiring/{TASK.md,task-package.json,L3.md,PROGRESS.md,HANDOFF.md}`
- `.ai-team/tasks/S4-A2-EXPERIENCE-WIRING.md`

## Additional implementation facts

- The consumption hook is a **read-only pull** over the persisted event log
  (`RecordStore.events(project_id)`), not a subscription. The producers of the three
  interception events live on forbidden paths (`audit_evidence.py` is B-lane,
  `audit.py` is A3), and the repository has no `subscribe`/`listener`/`publish`
  abstraction, so a push hook could not be landed without crossing the boundary.
  Registered as D-A6-01.
- `MAPPING_RULES` is the deliverable mapping table, in code:
  `evidence.candidate_blocked` → `evidence_admission_blocked`;
  `audit_evidence.report_created` with `status=fail` → `audit_evidence_remediation`;
  `audit_evidence.report_created` with `status=unknown` → `audit_unknown_resolution`;
  `audit.report_created` with `unknown_count > 0` → `audit_unknown_resolution`.
  A `pass` report and an `unknown_count == 0` report are **consumed but produce no
  record**, so a settle result is reproducible rather than merely "sometimes empty".
- Dedup key is `f"{technique}|{normalize(problem)}"` — frozen fields only, no event id
  and no counter. `experience_id` is derived deterministically as
  `"exp_" + sha256(f"{project_id}|{recurrence_key}")[:16]`, so a re-run rewrites the
  same record instead of creating a second one.
- Consumption markers reuse the A1/A2 `idempotency` ledger under scope
  `experience_sink`, keyed by `event_id` (`remember_idempotent` → `INSERT OR IGNORE`).
  No new table, no change to `storage.py`.
- **`recurrence_count` is derived, not incremented**: `1 + (consumed markers sharing
  the cause)`. The write order is "record first, marker second", so a crash between
  the two is self-healing — the retry recomputes the same count and rewrites the same
  record. If the marker table is unreadable the count degrades to 1 and the next
  healthy settle corrects it. Registered as D-A6-02.
- The sink stays below the four promotion gates: created records are always
  `grade=E0` / `promoted=False`; a merge only raises `recurrence_count` and unions
  `evidence_ids`, carrying the existing `grade` and `promoted` over untouched.
  `experience_sink.py` contains no `promote` call site — asserted at AST level, not by
  comment.
- Degradation is total and non-fatal: unreadable event log, unreadable markers,
  unreadable single payload, and rejected writes each turn into a diagnostic;
  `settle` never raises. A rejected write deliberately does **not** consume the event,
  so the next settle retries it.
- Payload reading is defensive: `_string_list` turns a field that changed type
  (bare string / dict / None) into an empty list instead of iterating characters, and a
  non-numeric `unknown_count` degrades to 0 (i.e. not a failure).
- Chain exactness: after a settle, the only event types added are
  `knowledge.page_added` (the mandated `ExperienceService.record` → `KnowledgeService.add_page`
  mirror). Zero `audit.*` / `audit_evidence.*` / `evidence.*` rows are added.

## Automated verification

Commands run in the A6 worktree with its own venv, with `-o addopts=""` (so the summary
line is visible), `-p no:cacheprovider` (Windows `WinError 5`), and an explicit
`--basetemp`.

- Focused: `pytest tests/test_experience_sink.py ...` → **22 passed**
- Full suite: `pytest tests ...` → **188 passed** (baseline `origin/main@66aba64` measured at **166**; this package adds 22)
- Coverage: `--cov=autoresearch.experience_sink --cov-report=term-missing` → **199 stmts / 0 miss / 100%**
- `ruff check src tests` → `All checks passed!`
- `node .ai-team/check.mjs --task .ai-team/tasks/S4-A2-EXPERIENCE-WIRING.md --base origin/main` → `valid`
  (`State: handoff`, `Functional progress: 8/8 (100%)`, `Code progress from origin/main: 1 commits, 11 files, +1602/-0`)
- `python scripts/check_pr_contract.py --base origin/main` → `PR contract check passed: 11 changed paths; 1 task ledger(s)` (exit 0)
- `node .ai-team/check.mjs --base main` also reports `valid`, but under that base the
  diff also swallows the B5 commits already in the new baseline
  (`4 commits, 27 files, +3208/-12`) because local `main` is behind. Use `--base origin/main`
  for this package's real surface.

### Functional scenario harness (untracked, not part of the package)

- `.workbuddy/a6-scenarios/scenario.py` — 12 field-level scenarios, run as
  `scenario.py` or `scenario.py 3 5`. All 12 printed the expected values; the notable
  ones: scenario 2 (same cause merges, `recurrence_count` 1→2, one record, same id),
  scenario 6 (`recurrence >= 2` satisfied yet `promote(...)` still raises
  `PermissionError` because grade is E0), scenario 7 (`grade=E2, promoted=True`
  preserved across a merge, `recurrence_count` 1→2), scenario 8 (log offline →
  `degraded=True`, no exception), scenario 10 (write rejected → 0 markers → retry
  records successfully), scenario 12 (`promote`/`append_event`/`add_page` call sites
  all absent; only `knowledge.page_added` added; table set unchanged).
- `.workbuddy/a6-scenarios/user-scenario.py` — one end-to-end business walkthrough for
  project `proj_llm_eval`: two intercepted candidates (one for missing classification,
  one for a missing locator), one failing `audit_evidence` report, one audit-runtime
  report with `unknown_count=2`; settle → 4 experiences all `E0`; a repeat of the
  classification failure → that record's `recurrence_count` becomes 2; promote still
  raises; the HTTP settle then reports `recorded=0`. 0 exceptions, 0 rejected writes.

## Known limits

- The read-only guarantee is a **structural** one ("this module has no `append_event`
  call site, and the producers are outside it"), guarded by an AST test — not a
  database-level permission. `ExperienceSink` holds a `RecordStore`; adding one
  `append_event` call to the module would break the invariant.
- **"Same cause" is our predicate, not a producer declaration**
  (`technique|normalize(problem)`). If a producer rewords its `reasons`, one fault
  becomes two causes, two records, each at `recurrence_count=1`. That is a real
  fragility in the `>= 2` gate base: if production is going to rely on this number, the
  cause predicate should move to an explicit stable reason code emitted by the
  producer.
- `_match`'s "event type outside the mapping table" branch is unreachable through the
  public API (both callers pre-filter); it is internal defence, covered by a direct
  unit test.
- The experience records take no part in any gate decision and are never written back
  into an audit report.
- `events(project_id)` returns the whole project log with no type filter, so every
  settle scans everything and then filters. At 10^5 events this needs pagination or a
  time lower bound; not done here.
- No user-side independent reproduction has been run yet — that is the owner/user-side
  acceptance step.

## Owner adjudication requests

- **D-A6-01 (spec wording)**: the specification says the package should *subscribe* to
  fail-closed interception events. Implemented as a read-only pull over the persisted
  log, because the producers sit on forbidden paths and no subscribe abstraction exists.
  Requested: confirm the wording is rewordable, or open a hook point on the producer
  side (which requires owner action, not this package).
- **D-A6-02 (`recurrence_count` semantics)**: the count is "number of consumed events
  sharing the cause", not "number of times the record was written". Requested: confirm
  this is what the `>= 2` gate base should mean. If a strictly incremented counter is
  required instead, the write order and the crash behaviour both change.
- **Registry row**: `S4-A2-EXPERIENCE-WIRING` is still `ready` in
  `docs/rearchitecture/TASK-PACKAGE-REGISTRY.md`. That is a shared document and this
  package did not modify it.
- **Ledger lag (record level)**: `docs/tasks/P1-A-runtime-lane/TASK-QUEUE.md` lags the
  registry (shared document, not modified, reported only).

## Next owner action

Adjudicate D-A6-01 (and confirm/deny D-A6-02), run the acceptance commands and the
scenario harness in your own environment, then decide whether to push / open the PR.
Next package: `S4-A3-KNOWLEDGE-VECTOR`.
