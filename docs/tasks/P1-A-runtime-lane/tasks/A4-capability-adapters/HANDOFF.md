# S3-A Handoff

## Snapshot

- Branch: `codex/s3-a-capability-adapters`
- Base: `main@80e2277`（本地 `main` 已快进至同一提交）
- Status: implemented + review-fixed (R-1~R-6), `ready`; user-side Step 1 re-run and scenarios 1–9 all passed — commit / push / PR pending

## Delivered files

- `src/autoresearch/capability_registry.py`
- `src/autoresearch/invocation_contracts.py`（`CapabilityManifest` 补齐 L2 字段）
- `tests/test_capability_registry.py`
- A4 task-local package and ledger files

## Additional implementation facts

- Registry key is `name@version`; duplicate registration is rejected; the public
  registration view never exposes the raw adapter (no bypass handle).
- A bare capability name that matches more than one registered version is rejected
  with `CapabilityAmbiguousReferenceError`; callers must use `name@version`. This keeps
  the idempotency key deterministic.
- Trust tier is operator-assigned at registration; adapter self-declaration is
  ignored and recorded as a diagnostic (privilege escalation = 0).
- `candidate_only` drops any structured value and emits `EvidenceCandidate`s only;
  `compliant_structured` requires a structured result, otherwise FAILED.
- Network is denied by default: `network_required` capabilities are rejected with a
  DENIED receipt before the adapter is called unless the operator sets
  `allow_network=True`.
- Idempotency is in-memory on `(name@version, invocation_id)`: identical fingerprint
  replays with a REPLAYED receipt, conflicting fingerprint is rejected.
- `status=REPLAYED` means "served from the idempotency record"; `outcome_status`
  preserves the original terminal outcome (completed/failed/unknown/denied). This
  mirrors the A1 `InvocationReceipt` convention and was fixed during review (before
  the fix, replayed failures and denials were silently rewritten to `replayed`).
- The receipt reserves an `admitted` field (always None here) for the I3 admission
  compensation semantics (R004-04 L2:21).
- Candidate **facts and admissibility are separated** (review fix R-6). `candidates` /
  `candidate_count` are the raw record of what the adapter emitted and are preserved on
  every failure path too. Admission must not read them directly: the receipt carries a
  computed `candidates_admissible` (true only when `outcome_status == completed`, so a
  replay keeps its original verdict) and `CapabilityInvocation.admissible_candidates`
  is the safe entry point. Before the fix the two FAILED paths disagreed: an adapter
  exception dropped already-emitted candidates (`candidate_count=0`) while a contract
  violation kept them (`candidate_count=1`). Resolving it by "keep the record, gate the
  admission" was preferred over "clear on failure" because deleting information is
  irreversible, clearing turns a loud failure into a silent empty, and it would
  contradict this package's own failure-leaves-a-trace design (cf. the retained
  `blocked_write_attempts`). Registered as D-7 for owner confirmation.
- No MCP protocol implementation: A4 delivers only the unified four-kind boundary.
  ADR-01 slot 14 (`docs/coord/adr-01-external-integrations.md:50`, landed in this base)
  defers the MCP stdio transport to the L3 extension slot, and requires
  "allowlist + explicit authorization + fail-closed"; the deny-by-default policy and
  the explicit `allow_network` opt-in satisfy the first three, transport enforcement
  is out of scope.

## Automated verification

- Focused: `python -m pytest tests/test_capability_registry.py -q` — 29 passed.
- Coverage: `python -m pytest tests/test_capability_registry.py -q --cov=autoresearch.capability_registry --cov-report=term-missing` — 100% (210 stmts, 0 miss).
- Full suite: `python -m pytest tests -q` — 137 passed.
- `python -m ruff check src tests` — passed.
- `node .ai-team/check.mjs --task .ai-team/tasks/S3-A-CAPABILITY-ADAPTERS.md --base main` — valid
  (`Functional progress: 18/18`).
- **R-6 zero-regression (mechanical)**: reverted *only* R-6's two `except` branches in a
  throwaway copy of `src`, pointed the scenario harness at the copy, and diffed scenario
  1–8 stdout against the current tree — `RESULT: scenarios 1-8 byte-identical`. This
  upgrades the earlier eyeball comparison to a mechanical diff and confines R-6's
  observable behaviour change to the "emitted candidates then failed" path exercised only
  by scenario 9b/9c. The worktree itself was not modified (copy-only).

### User-side independent reproduction (Step 1 repo check)

- User ran the acceptance commands in their own environment with an explicit
  `--basetemp` (the default pytest basetemp was ACL-blocked): full suite reached
  `[100%]` with no F/E, focused run 24 tests, module coverage 100% (201 stmts / 0 miss),
  ruff `All checks passed!`, and `check.mjs` reported `valid` with
  `Functional progress: 17/17` and `Code progress from main: 0 commits, 9 files, +8/-2`.
  **These numbers predate review fix R-6** (24→29 focused, 201→210 stmts, 132→137 full,
  17→18 acceptance checks).
- **Post-R-6 re-run (user-side, 2026-09-10 20:46)**: adding `-o addopts=""` makes the
  summary line visible, so the counts are now observed — focused `29 passed`, coverage
  `210 stmts / 0 miss / 100%`, full `137 passed` (27.97s), ruff `All checks passed!`,
  `check.mjs` `valid` with `Functional progress: 18/18` and
  `Code progress from main: 0 commits, 9 files, +8/-2`. Matches the expected post-R-6
  values exactly → Step 1 numerically reproduced. The only warning is a benign
  `PytestCacheWarning` (`.pytest_cache` ACL `WinError 5`), which does not affect results.
- Scenario walkthrough complete (user-side, 2026-09-10): scenarios 1–9 all judged
  PASS / 0 contradictory against the raw output the user ran and pasted.

## Functional scenario evidence (user-side)

Harness: `.workbuddy/a4-scenarios/scenario.py` (untracked, not part of this package).
Each row records the field-by-field judgement against the raw output the user pasted.

| # | Scenario | Judgement | Evidence highlights |
|---|---|---|---|
| 1 | registration boundary / bypass=0 / duplicate reject | **observed 5/5, 0 contradictory** | public view exposes no `adapter` attribute (`register()` and `list()` both return `CapabilityRegistrationView`); count=1; unregistered invoke raises `CapabilityNotRegisteredError`; duplicate raises `CapabilityRegistrationError` with `name@version` key |
| 2 | trust tier is operator-assigned only | **all fields observed, 0 contradictory** | adapter self-declared `compliant_structured` while receipt shows `trust_tier=candidate_only`; declaration recorded in diagnostics verbatim and never adopted |
| 3 | candidate_only positive / negative | **all fields observed, 0 contradictory** | 3a drop proof holds: adapter really returned a `value`, receipt still `value=None` + `structured_result_available=False`, status `completed`; 3b contract violation → `failed` + `candidates=0` + diagnostic `candidate_only adapter returned no EvidenceCandidate` |
| 4 | compliant_structured positive / negative | **all fields observed, 0 contradictory** | 4a `structured_result_available=True` with typed `value`, `candidates=0`; 4b candidate-only delivery → `failed` + diagnostic `compliant_structured adapter returned no structured result`. The `failed` yet `candidates=1` reading raised here became review fix R-6 |
| 5 | write-violation interception (evidence / gate) | **all fields observed, 0 contradictory** (user-side) | both `write_evidence` and `write_gate_decision` → `failed`, `candidates=0`, `blocked_write_attempts=1`; the adapter is still called (`calls=1`), i.e. interception is at the write, not a bypass |
| 6 | network denied by default / explicit opt-in | **all fields observed, 0 contradictory** (user-side) | 6a `denied` with adapter `calls=0`; 6b `allow_network=True` → `completed`, typed value, `calls=1` |
| 7 | idempotency / replay polarity / fingerprint conflict | **all fields observed, 0 contradictory** (user-side) | first `failed` → replay `status=replayed, outcome_status=failed`; denied replay keeps `denied`; adapter called once; conflicting fingerprint → `CapabilityInvocationConflictError`; bare name → `CapabilityAmbiguousReferenceError`; `@2` hits `version=2` |
| 8 | four-kind shared boundary / A1 bridge | **all fields observed, 0 contradictory** (user-side) | native/mcp/skill/plugin all `completed` with matching `receipt_kind`; bridge → `candidate_only`, `completed`, `candidates=1`, legacy `calls=1` |
| 9 | fact-record vs admissibility split (R-6) | **all fields observed, 0 contradictory** (user-side) | 9a fresh + replay both `candidates_admissible=True / admissible_candidates=1` (replay keeps `outcome_status=completed` ⇒ predicate keyed off `outcome_status`, not `status`); 9b `raw=2/count=2` but `admissible=False`; 9c/9d `raw=1`, inadmissible; 9e `denied`, all zero |

## Known limits

- The "no privilege escalation / no bypass" guarantee is structural, not a sandbox:
  the context grants no write path and the registration view exposes no adapter
  handle, but an adapter that already holds an `EvidenceService` reference could still
  write directly. What this package guarantees is "no path is given", not "escape is
  impossible".
- Registry and idempotency state are process-local; persistence is deferred until
  a real consumer (A5 Semantic Scholar adapter) requires it.
- `allowed_network_domains` is a schema slot; transport-level domain enforcement
  is not implemented (no network sandbox in S3-A). Cf. ADR-01 slot 14.
- `admitted` is schema-reserved only; end-to-end admission compensation is I3 scope.
- Candidate admit gating is a **contract, not an enforcement**: `invocation.candidates`
  stays publicly readable, so the package cannot stop a consumer from bypassing
  `receipt.candidates_admissible` and reading it directly. What is provided is "a safe
  entry point exists and is the only correct read" (`admissible_candidates`), not
  "the wrong read is impossible". The first real consumer (A5) should enforce the
  predicate at its consumption point.
- Contract deviations D-1..D-7 are registered in `L3.md` for owner adjudication:
  `network` field split (D-1), `project_id`/`run_id` not promoted to the boundary
  (D-2), registry-signed receipt instead of adapter-returned receipt (D-3), the
  resulting two-shape receipt drift vs A1 (D-4), and the failure-path candidate
  disposition chosen in R-6 (D-7).

## Owner adjudication requests

- **D-4 (receipt drift)**: two same-role receipts now exist — A1 `InvocationReceipt`
  (`invocation_contracts.py:71`) and A4 `CapabilityInvocationReceipt`. The bridge's
  status mapping table is the drift evidence. Precedent: `D-I0-01`, `D-S2-01`.
  Requested ruling at the S3 promotion window: (a) keep both shapes and register the
  mapping, or (b) make the A4 receipt re-export the A1 type plus extension fields.
- **D-1**: whether R004-04 L2 should be reworded to the split
  `network_required` + `allowed_network_domains`.
- **D-7 (failure-path candidate disposition)**: R-6 chose "keep the raw record + gate
  admission at a single computed field" over "clear candidates on failure". Requested:
  confirm or reject. If rejected in favour of clearing, `candidate_count` must be
  corrected in the same change and the acceptance suite re-run. Note the new
  `candidates_admissible` is an A4-native field — under D-4 option (b) it would move to
  the extension fields.
- **Ledger inconsistency (record level)**: `docs/tasks/P1-A-runtime-lane/TASK-SPECS.md:48`
  still marks A4 as `planned` while `TASK-QUEUE.md:8` and the registry mark it `ready`.
  Not modified here (owner-maintained shared spec).

## Next owner action

Review the implementation against TASK-SPECS A4 and R004-04 L2, adjudicate D-1/D-4/D-7,
then run the S3 promotion review. Do not mark accepted until the owner satisfies the
S3 promotion gate.
