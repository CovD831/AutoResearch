# M11-MVP-02 Progress

| Date | State | Change | Evidence | Blocker / next step |
|---|---|---|---|---|
| 2026-09-17 | planning | Read the task package, the M11-MVP-02 section of `TASK-SPECS.md`, `lane-manifest.json`, `.ai-team/SKILL.md`, `AGENTS.md` and the MVP-01 ledger; confirmed owner lane, base ref `f197b7a`, dependency on M11-MVP-01 and the path boundary | `.ai-team/tasks/M11-MVP-02.md`; `git rev-parse HEAD` = `f197b7a`; clean worktree | Baseline re-measured in this worktree before coding: `tests/test_knowledge_boundary.py` → `34 passed` |
| 2026-09-17 | planning | Recorded the L0 `project_id` specification/boundary conflict as a declared finding rather than silently narrowing the requirement | ledger `Boundary finding` section; `knowledge.py:84` (constructor takes only `store` + `relation_registry`); `TASK-SPECS.md:429` vs `:442` / `:470` | Owner must rule on where the project scope is wired in (ledger `D-M11-02-01`) |
| 2026-09-17 | implemented | Added `src/autoresearch/knowledge_retrieval.py`: `in_scope` / `apply_l0_boundary` (L0), `bm25_scores` (L1), `EmbeddingProvider` / `HashingEmbedder` / `cosine_similarity` / `vector_scores` (L2 vector), `expand_graph` (L2 graph), `describe_retrieval_level`, and `recall` | `src/autoresearch/knowledge_retrieval.py`; `ruff check src tests` clean | Replaced the naive substring scoring; fusion (RRF) deliberately left to M11-MVP-03 |
| 2026-09-17 | implemented | Added `src/autoresearch/recall_audit.py`: `RecallAuditRecord` (10 fields + subset-chain validator), `build_record`, switchable `RecallAuditWriter` | `src/autoresearch/recall_audit.py` | Audit rows reuse the kind-generic `records` table; `storage.py` is forbidden here so no schema change was made |
| 2026-09-17 | implemented | Rewrote the body of `KnowledgeService.retrieve()`: L0 → L1 → L2 vector → graph, one audit row per call, then map to `RetrievalHit`. Signature unchanged; the unused `_score()` static method removed | `git diff -U0 f197b7a -- src/autoresearch/knowledge.py` (3 hunks: imports, `_score` removal, `retrieve()` body) | The `_score` removal sits outside `retrieve()` and is explicitly authorized by `task-package.json:59`; declared in the ledger in case the owner wants it restored |
| 2026-09-17 | implemented | Added the frozen offline fixture `tests/fixtures/knowledge_retrieval/recall_pipeline.json` (7 pages, 2 edges, hand-authored orthogonal vectors, hand-authored `expected`) | fixture `schema` = `m11-knowledge-retrieval/v1` | `expected` values are hand-authored from the boundary rules, never regenerated from the implementation |
| 2026-09-17 | tested | Added `tests/test_knowledge_retrieval.py` (23 tests) covering L0, both arms, the audit subset chain, degradation, level gating, determinism and an adversarial meta-check against the pre-MVP-02 implementation | focused suite `23 passed` | The meta-check asserts the fixture also fails on the old ranking (cross-project leak, superseded page, missing vector arm) |
| 2026-09-17 | tested | Ran the acceptance command set | focused `23 passed`; full `tests` → `652 passed, 2 skipped` (`-W error` gives the same numbers); `ruff check src tests` → `All checks passed!`; `node .ai-team/check.mjs --task .ai-team/tasks/M11-MVP-02.md --base f197b7a` → `Result: valid` | Not pushed and no PR opened, per instruction; owner review of the boundary and decisions comes next |

## Boundary

This package changes only its declared `allowed_paths`. It does not modify `.project-to-act/`,
shared contracts, storage, gates, application orchestration or capability code. Forbidden paths
were confirmed untouched by comparing `git status --porcelain` against `task-package.json:14-32`
one entry at a time.
