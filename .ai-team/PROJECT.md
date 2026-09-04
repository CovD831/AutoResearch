# Project Context

This file contains stable facts shared by every developer and AI. Change it only when the project direction or architecture changes.

## Goal

Build AutoResearch: a LangGraph-based, evidence-gated research system that takes one research idea through decomposition, literature discovery and reading, novelty analysis, work execution support, manuscript drafting, review, and local delivery with auditable artifacts.

## Scope

- In scope: exactly five business agents (`orchestrator`, `paper_search`, `paper_reader`, `writer`, `reviewer`).
- In scope: typed state, deterministic lifecycle transitions, structured handoffs, evidence grades, fail-closed gates, checkpoint/resume, partitioned Wiki+Graph knowledge, user profiles, experience consolidation, evolution proposals, paper-project folders, CLI, HTTP API, tests, and documentation.
- In scope: offline deterministic execution for development and an optional OpenAI-compatible LLM adapter selected only through environment configuration.
- Out of scope: bypassing paywalls or access controls; fabricating citations, experiments, or approvals; autonomous submission/publication; destructive research-data operations; claims of publication readiness without a real paper pilot.

## Architecture

- `src/autoresearch/contracts.py`: authoritative Pydantic contracts and enums.
- `src/autoresearch/storage.py`: SQLite canonical store, append-only audit data, artifact references, and checkpoints for the foundational profile.
- `src/autoresearch/evidence.py` and `gates.py`: evidence policy and final deterministic gate ownership.
- `src/autoresearch/knowledge.py`: partitioned Wiki+Graph model and tiered retrieval facade.
- `src/autoresearch/*_service.py`: paper search/reading, profile, project, execution, writing, and evolution services.
- `src/autoresearch/agents/`: exactly five business-agent implementations.
- `src/autoresearch/graph.py`: LangGraph parent graph, lifecycle routing, checkpoint/resume, and handoff validation.
- `src/autoresearch/api.py` and `cli.py`: supported external boundaries.
- `.project-to-act/`: canonical product scope, feature status, version, progress, evidence, and acceptance.
- `.ai-team/TASK.md`: the current integration batch and global queue checkpoint.
- `.ai-team/tasks/`: task-local ledgers for parallel worktrees; each member owns only their task ledger.
- `docs/rearchitecture/IMPLEMENTATION-ROADMAP.md`: global phases, asynchronous execution, and Gate rules.
- `docs/rearchitecture/TASK-PACKAGE-REGISTRY.md`: package queue, owner lanes, dependencies, and merge order.
- `docs/`: architecture, contracts, development, operations, API, and user guides.

## Invariants

- Never commit credentials, private source copies, system/developer prompts, raw tool output, keyboard activity, or chain-of-thought.
- Raw user submissions may be committed only when the repository is private and `.ai-team/session-policy.json` explicitly enables verbatim capture. This repository currently has private session capture disabled.
- Preserve exactly five business agents. Evidence, gates, state, handoff, knowledge, profile, evolution, and project management are services/nodes, not hidden agents.
- Gate decisions are deterministic and fail closed; an LLM cannot override them or populate human approval identity.
- Agent handoffs contain stable IDs and bounded summaries, never full chat history or full-paper dumps.
- Model calls are optional and environment-configured. Offline tests must pass without an API key.
- External publication, sending, deletion, and high-cost execution remain disabled unless explicit H3 approval and policy requirements pass.
- Let tests and CI decide observable behavior; distinguish implemented local behavior from external integration and real research validation.

## Commands

- Install: `py -3.12 -m venv .venv` then `.venv\Scripts\python.exe -m pip install -e ".[dev]"`
- Test: `.venv\Scripts\python.exe -m pytest -q`
- Verify: `.venv\Scripts\python.exe -m ruff check src tests` then `.venv\Scripts\python.exe -m pytest -W error -q` then `.venv\Scripts\autoresearch.exe doctor`
- Collaboration check: `node .ai-team/check.mjs --base HEAD`
