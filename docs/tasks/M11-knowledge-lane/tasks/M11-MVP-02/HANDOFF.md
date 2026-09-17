# M11-MVP-02 Handoff

## Status

`tested`; the candidate recall pipeline is implemented and every acceptance command passes.
Not pushed and no PR opened, per instruction. Owner review of the boundary finding and the three
open decisions comes next.

## Base and branch state

- Base: `f197b7a` (the main HEAD this worktree branched from; `origin/main` on this machine is
  stale at `3b524e1` and must not be used as `--base`).
- Branch: `codex/m11-mvp-02`.
- The package changes are currently the working-tree changes listed below; no commit exists yet.
- `depends_on` / `merge_after`: M11-MVP-01, which is already merged.

## Changed paths

- `src/autoresearch/knowledge_retrieval.py` (new)
- `src/autoresearch/recall_audit.py` (new)
- `src/autoresearch/knowledge.py` (modified: imports, `_score` removal, `retrieve()` body)
- `tests/test_knowledge_retrieval.py` (new)
- `tests/fixtures/knowledge_retrieval/recall_pipeline.json` (new)
- `docs/tasks/M11-knowledge-lane/tasks/M11-MVP-02/` (new: this file, `L3.md`, `PROGRESS.md`)
- `.ai-team/tasks/M11-MVP-02.md` (new)

Every entry is within `task-package.json:14-32` `allowed_paths`. No `forbidden_paths` entry was
touched; the comparison is recorded in `.ai-team/tasks/M11-MVP-02.md`.

## Verification

- Python `3.13.12`, pytest via `.venv/Scripts/python.exe`.
- Focused, acceptance-command form: `tests/test_knowledge_retrieval.py` → `23 passed`.
- Full suite: `tests` → `652 passed, 2 skipped`; identical numbers under `-W error`.
- `ruff check src tests` → `All checks passed!`
- `node .ai-team/check.mjs --task .ai-team/tasks/M11-MVP-02.md --base f197b7a` → `Result: valid`.
- Baseline re-measured in this worktree before coding: `34 passed`.

Reproduction notes:

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
- The L0 `project_id` filter is real and tested, but the service has no project scope and this
  package cannot add one. Until the owner wires it, a service built without the optional
  `project_id` attribute behaves as before (no project filtering).
- Vector recall needs an injected `EmbeddingProvider`; without one the package degrades to lexical
  and says so. The bundled `HashingEmbedder` is a deterministic offline placeholder, not a
  semantic model.

## Decisions awaiting the owner

- `D-M11-02-01`: where the project scope is wired in (`application.py` / `api.py` / `cli.py` are
  outside this package's allowed paths, and `application.py` is the lane's `forbidden_shared_paths`).
- `D-M11-02-02`: the availability predicate (`review_status == superseded` is treated as
  unavailable). The repository does not define "availability".
- `D-M11-02-06` downstream: the comment at `contracts.py:167` claiming the vector channel is
  unreachable is now stale and needs updating in a package allowed to edit `contracts.py`.

## Rollback

Revert this package's commit, or remove only the changed paths listed above. M11-MVP-01 behaviour,
the frozen contracts and all shared project records stay intact.

## Next owner

Project owner: review the changed-path boundary, the three open decisions, and the verification
evidence. After that, M11-MVP-03 (fusion, de-duplication, index maintenance) can start.
