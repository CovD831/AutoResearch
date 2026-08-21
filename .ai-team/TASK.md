# Current Task

- ID: `AR-001`
- Title: `Implement the complete foundational five-agent AutoResearch framework`
- Status: `active`
- Owner: `zzg`
- Next owner: `zzg`

## Goal

Turn the approved planning baseline into a runnable foundational product whose architecture and major functions are complete at basic fidelity. Leave advanced retrieval quality, production databases, polished UI, and real paper-pilot quality for later revisions without leaving structural holes.

## Acceptance scenarios

- [ ] Given a new idea and offline mode, when a run starts, then exactly five business agents participate through validated handoffs and produce a persisted project state plus a local manuscript draft.
- [ ] Given insufficient or invalid evidence, when an L2+ transition is requested, then the deterministic gate returns `REVISE`, `INTERRUPT`, or `DENY` and the lifecycle cannot advance.
- [ ] Given a paused run, when it is resumed with the same thread and a valid approval/evidence update, then checkpointed execution continues without duplicating append-only evidence or external-action intents.
- [ ] Given papers, knowledge, experience, project facts, evidence, and a user profile, when retrieval runs, then partitions remain distinct and results expose provenance and retrieval level.
- [ ] Given a paper-project request, when it is created, then the folder and Project-to-Act-compatible project artifacts are instantiated without overwriting existing work.
- [ ] Given CLI and HTTP clients, when they create/run/inspect a project, then both use the same application service and return structured success or failure rather than invented results.
- [ ] Given an evolution event, when consolidation runs, then it creates a reviewable proposal and never mutates protected workflow, gate, prompt, or skill assets directly.
- [ ] Given a clean Python 3.12 environment without an API key, when the full verification suite runs, then install, lint, tests, CLI doctor, and HTTP smoke all pass.
- [ ] Given repository collaboration files, when VibeCollab validation runs, then PROJECT/TASK/code/test progress remain synchronized and no private session capture is enabled.

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

## Pending

- Scaffold package, dependencies, configuration, contracts, and storage.
- Implement governance services and exactly five agents.
- Implement LangGraph, CLI, API, project instantiation, documentation, and examples.
- Run full verification and update `.project-to-act` plus this task with evidence.

## Next step

Create the Python package and foundational contracts, then implement the governance services before wiring the LangGraph parent graph.

## Verification

- [ ] `py -3.12 -m venv .venv`
- [ ] `.venv\Scripts\python.exe -m pip install -e ".[dev]"`
- [ ] `.venv\Scripts\python.exe -m ruff check src tests`
- [ ] `.venv\Scripts\python.exe -m pytest -q`
- [ ] `.venv\Scripts\python.exe -m autoresearch.cli doctor --json`
- [ ] FastAPI health and one offline project/run smoke test
- [ ] `node .ai-team/check.mjs --base HEAD`
- [ ] Project-to-Act root `--validate`

## Handoff note

- From: `zzg`
- To: `zzg`
- Summary: AR-001 is active. Implement the complete foundational framework; do not stop at additional planning.
