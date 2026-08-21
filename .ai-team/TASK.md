# Current Task

- ID: `AR-001`
- Title: `Implement the complete foundational five-agent AutoResearch framework`
- Status: `done`
- Owner: `zzg`
- Next owner: `zzg`

## Goal

Turn the approved planning baseline into a runnable foundational product whose architecture and major functions are complete at basic fidelity. Leave advanced retrieval quality, production databases, polished UI, and real paper-pilot quality for later revisions without leaving structural holes.

## Acceptance scenarios

- [x] Given a new idea, offline mode, and user-authorized seed papers, when a run starts, then exactly five business agents participate through validated handoffs and produce persisted project state plus a local manuscript draft; without papers it stops before reading.
- [x] Given insufficient or invalid evidence, when an L2+ transition is requested, then the deterministic gate returns `REVISE`, `INTERRUPT`, or `DENY` and the lifecycle cannot advance.
- [x] Given a paused run, when it is resumed with the same thread and a valid approval/evidence update, then checkpointed execution continues and the stable human-approval evidence ID prevents duplicate release approvals.
- [x] Given papers, knowledge, experience, project facts, evidence, and a user profile, when retrieval runs, then partitions remain distinct and results expose provenance and retrieval level.
- [x] Given a paper-project request, when it is created, then the folder and Project-to-Act-compatible project artifacts are instantiated without overwriting existing work.
- [x] Given CLI and HTTP clients, when they create/run/inspect a project, then both use the same application service and return structured success or blocked results rather than invented results.
- [x] Given an evolution event, when consolidation runs, then it creates a reviewable proposal and never mutates protected workflow, gate, prompt, or skill assets directly.
- [x] Given a clean Python 3.12 environment without an API key, when the full verification suite runs, then install, lint, tests, CLI doctor, and HTTP smoke all pass.
- [x] Given repository collaboration files, when VibeCollab validation runs, then PROJECT/TASK/code/test progress remain synchronized and no private session capture is enabled.

## Invariants

- Exactly five business agents; service nodes do not count as agents.
- Offline deterministic behavior is a first-class supported mode, not a mocked success claim.
- No fabricated citations, paper contents, experimental results, human approvals, or external delivery results.
- No credentials in code, docs, tests, task files, logs, or evidence.
- External publication and destructive actions default to disabled.
- Existing planning documents and paper-project template remain authoritative and are updated rather than replaced by a second plan.

## Decisions

- Use Python 3.12, Pydantic v2, LangGraph, FastAPI, SQLite for the foundational canonical store, and optional OpenAI-compatible model calls.
- Use SQLite/JSON/Markdown adapters behind interfaces now; document PostgreSQL/pgvector/Neo4j as production replacements without pretending they are already integrated.
- Keep the parent lifecycle deterministic. Agent outputs may propose data, but state transitions and gates are code-owned.
- Use one repository root Git history. The nested `DeepReason-Agents-Framework/` remains an ignored local reference and is not vendored into AutoResearch.
- Install and apply VibeCollab in non-private mode because this local repository has no confirmed private remote.
- Pin the pulled `repo-task-sync` source provenance to VibeCollab commit `f13ece435e41f143ccfc54dfde4c85ff8c05510e` in project documentation.

## Completed

- Approved detailed plan, 86-item feature catalog, Project-to-Act root ledger, and paper-project folder template.
- Installed `repo-task-sync` from `redmaplewww/vibecollab` and applied VibeCollab 0.5.0 in non-private mode.
- Initialized the AutoResearch root Git repository and excluded the nested reference repository and local secrets/runtime artifacts.
- Confirmed Python 3.12 and managed LLM profiles are available without exposing credentials.
- Implemented the Pydantic contracts, SQLite canonical/audit store, append-only evidence facade, deterministic L0–L4 gates, lifecycle state machine, structured handoffs, project service, Wiki+Graph partitions, profiles, experience promotion, and proposal-only evolution.
- Implemented exactly five Agent classes and LangGraph subgraphs, a parent graph with conditional stop paths, SQLite checkpoints, and L4 human interrupt/resume.
- Implemented OpenAlex/Crossref/Semantic Scholar connectors, seed-paper handling, deduplication, PDF/text reading cards, evidence-limited reading Q&A, innovation hypotheses, work packages, evidence-bound drafting, revisions, and reviewer gates.
- Implemented shared CLI/FastAPI boundaries, project folder runtime projection, complete architecture/operations/security/development/API/testing documentation, and managed optional LLM configuration.
- Verified 18 tests with warnings treated as errors, 84% statement coverage, Ruff, doctor, Project-to-Act root/template validation, four isolated real-HTTP customer journeys, two live scholarly connectors, and a managed LLM JSON connectivity call.

## Pending

- No required AR-001 work remains.
- Follow-up scope, not part of AR-001: a real paper idea/gold corpus, RunManifest and real experiments, production PostgreSQL/pgvector/Neo4j, process-restart/outbox hardening, Web UI/authentication, backup/restore, and real-paper acceptance.

## Next step

Start a new VibeCollab task for the first real literature pilot after the user supplies the idea, domain, target venue, licensed/full-text corpus, and experiment resource boundaries.

## Verification

- [x] `py -3.12 -m venv .venv`
- [x] `.venv\Scripts\python.exe -m pip install -e ".[dev]"`
- [x] `.venv\Scripts\python.exe -m ruff check src tests`
- [x] `.venv\Scripts\python.exe -m pytest -W error -q` — 18 passed
- [x] `.venv\Scripts\pytest.exe --cov=autoresearch` — 84% statements
- [x] `.venv\Scripts\autoresearch.exe doctor` — ok, exactly five agents, safe configuration summary
- [x] FastAPI real-listener health/create/no-paper/abstract-draft journeys — four journey reports pass
- [x] `node .ai-team/check.mjs --base main`
- [x] Project-to-Act root and paper template `--validate` — both valid with zero issues

## Handoff note

- From: `zzg`
- To: `zzg`
- Summary: AR-001 is complete. The foundation is runnable and evidence-backed; create a separate task for the first real-paper pilot and preserve all non-claims recorded in `evidence/FOUNDATION_EVIDENCE.md`.
