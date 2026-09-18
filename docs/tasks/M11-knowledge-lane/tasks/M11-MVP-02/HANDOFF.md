# M11-MVP-02 Handoff

## Status

`tested`; the candidate recall pipeline is implemented and every acceptance command passes, including
the second round that repairs the four behaviours the owner rejected. Committed on
`codex/m11-mvp-02`; **not pushed and no PR opened**, per instruction. Owner sign-off on `D-M11-02-07`
(the approved cross-package wiring) and `D-M11-02-02` (the frozen availability reading) comes next.

## Base and branch state

- Base: `f197b7a` (the main HEAD this worktree branched from; `origin/main` on this machine is
  stale at `3b5241e` and must not be used as `--base`).
- Branch: `codex/m11-mvp-02`. Both rounds are committed on it; the working tree is clean.
- `depends_on` / `merge_after`: M11-MVP-01, which is already merged.

## Changed paths

This package's own paths:

- `src/autoresearch/knowledge_retrieval.py` (new; round 2 added `vector_arm`)
- `src/autoresearch/recall_audit.py` (new)
- `src/autoresearch/knowledge.py` (modified: imports, `_score` removal, `retrieve()` body; round 2
  added `KnowledgeScopeRequiredError` and the constructor keywords)
- `tests/test_knowledge_retrieval.py` (new; round 2 grew it from 23 to 40 tests)
- `tests/fixtures/knowledge_retrieval/recall_pipeline.json` (new)
- `docs/tasks/M11-knowledge-lane/tasks/M11-MVP-02/` (new: this file, `L3.md`, `PROGRESS.md`)
- `.ai-team/tasks/M11-MVP-02.md` (new)

Round 2 additionally changed six paths **outside** `allowed_paths`, under the owner's explicit
approval and listed one by one in the ledger (`D-M11-02-07`):

- `src/autoresearch/application.py` — new `knowledge_scope()` factory
- `src/autoresearch/api.py`, `src/autoresearch/cli.py` — required project scope on the search
  endpoint / command
- `tests/test_knowledge_boundary.py`, `tests/test_r006_l1_writer.py`,
  `tests/test_governance_services.py` — pre-existing call sites bound to each fixture's real project

No `forbidden_paths` entry was touched; the comparison is recorded in `.ai-team/tasks/M11-MVP-02.md`.

## Verification

- Python `3.13.12`, pytest via `.venv/Scripts/python.exe` — the **absolute** path, see below.
- Focused, acceptance-command form: `tests/test_knowledge_retrieval.py` → `40 passed`.
- Full suite: `tests` → `669 passed, 2 skipped`; identical numbers under `-W error`.
- `ruff check src tests` → `All checks passed!`
- `node .ai-team/check.mjs --task .ai-team/tasks/M11-MVP-02.md --base f197b7a` → `Result: valid`.
- Mutation check (round 2): reverting the fail-closed guard kills exactly 4 tests; removing the
  vector arm's failure boundary kills exactly 4 different tests. Both ran on a throw-away copy of
  `src`; the worktree was not modified.

Reproduction notes:

- **Always invoke the interpreter by absolute path.** Passing a relative
  `.venv/Scripts/python.exe` to `subprocess` with `cwd` set to the worktree does **not** run the
  worktree's venv: on Windows the executable is resolved against the parent process's working
  directory, so the main repo's `.venv` (and therefore the main repo's `src`) is what actually runs.
  The symptom is `ModuleNotFoundError: autoresearch.knowledge_retrieval` — a harness artefact that
  looks exactly like a broken package.
- `--basetemp` must point at a **fresh, empty** directory for each run. Reusing a non-empty
  basetemp makes pytest wipe it at startup, which the sandbox safe-delete guard blocks
  (`SAFE_DELETE_BULK_CONFIRM_REQUIRED`, threshold 50 per turn); the symptom is a setup error on
  every test that uses `tmp_path`, which looks alarming but is unrelated to the code.
- Also required: `-o addopts=""`, `-p no:cacheprovider`, serial execution.
- `--base` must be `f197b7a`, not the local `origin/main`.

## Known limits

- Fusion / RRF, mirror de-duplication and index maintenance are **not** in this package; they are
  M11-MVP-03 (`TASK-SPECS.md:486-499`).
- `RetrievalHit.score_breakdown` / `channel` / `matched_stage` are written with the single arm that
  produced the winning score, never `FUSED`. The fields already exist in the frozen contract
  (`contracts.py:513-516`), so nothing was added or renamed; see ledger `D-M11-02-06`.
- Vector recall needs an injected `EmbeddingProvider`; without one the package degrades to lexical
  and says so. The bundled `HashingEmbedder` is a deterministic offline placeholder, not a
  semantic model.
- The search endpoint and command now **require** a project scope. That is a deliberate behaviour
  change for callers who omitted it; `D-M11-02-09` records it and names the two files to touch if the
  owner prefers inferring the project from an existing record instead.

## Decisions awaiting the owner

- `D-M11-02-07`: keep or revert the round-2 cross-package wiring (six paths, of which
  `application.py` is the lane's `forbidden_shared_paths`). The owner approved this scope; the
  registration exists so the approval is visible in the diff, not inferred from it.
- `D-M11-02-02`: confirm the frozen availability reading (`review_status == superseded` is
  unavailable; `draft` / `published` / missing are available). Changing it means editing
  `is_available()` in one place.
- `D-M11-02-09`: confirm that the search endpoint and command should **require** a project scope
  rather than infer one.
- `D-M11-02-06` downstream: the comment at `contracts.py:167` claiming the vector channel is
  unreachable is now stale and needs updating in a package allowed to edit `contracts.py`.

## Rollback

Revert this package's commits, or remove only the changed paths listed above. The pipeline half
(this package's own four files) is independent of the wiring half (the six cross-package paths), so
the wiring can be reverted on its own. M11-MVP-01 behaviour, the frozen contracts and all shared
project records stay intact.

## Next owner

Project owner: review the changed-path boundary, the decisions above, and the verification evidence.
After that, M11-MVP-03 (fusion, de-duplication, index maintenance) can start.
