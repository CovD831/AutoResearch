# B Evidence Pipeline

This worktree note captures the narrow B1 slice only.

## In scope

- Evidence admission for candidates, duplicate detection, and conflict detection.
- Evaluation section planning for a single section.
- Versioned writing profiles.
- Plan-only benchmark advice.
- Material readiness checks.
- Section validation with verified, revise, and blocked outcomes.

## Out of scope

- `application.py`, `storage.py`, `contracts.py`, and `capability.py`.
- New agents, stores, schedulers, or buses.
- Observed benchmark results being written into the planned section.
- The real pilot and reader/writer port lanes.

## Current state

- Service-layer implementation is in place.
- Task-local docs and the repo task ledger have been updated.
- B1 focused tests, the full warning-as-error test suite, full ruff, and the repository check passed on 2026-09-06.
- B1 owner review passed with explicit B2 follow-ups for missing locators and invalidated evidence; project owner accepted the bounded slice for integration against GitHub `main@c0f8fbce89c8094fb02c022b2918a2c04e04380e`.
- The remote `main` base does not contain the B1 implementation; local branch and handoff commit metadata remain unavailable, so mainline integration is pending.
