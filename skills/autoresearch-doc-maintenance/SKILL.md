---
name: autoresearch-doc-maintenance
description: "Update AutoResearch project records after an accepted PR using code, tests, evidence, and handoff facts. Use only on the owner side after review or integration."
---

# AutoResearch Doc Maintenance

This is a project-specific owner skill for synchronizing documentation after a member PR is accepted or a phase Gate changes. It does not review code, merge PRs, or invent project status. It updates only from observable Git, test, evidence, handoff, and user-decision facts.

## Before updating

Read:

1. `AGENTS.md`;
2. `.ai-team/PROJECT.md` and `.ai-team/TASK.md`;
3. the accepted task-local ledger under `.ai-team/tasks/`;
4. the task package and `HANDOFF.md`;
5. `docs/rearchitecture/TASK-PACKAGE-REGISTRY.md`;
6. the relevant Project-to-Act files according to `project-to-act` routing.

Read the current paragraph or table row immediately before editing it. If the file changed since it was read, stop and reconcile instead of overwriting.

## Operating sequence

1. Identify the exact merged commit and PR/task ID.
2. Collect changed paths, verification commands, exit status, evidence locations, reviewer result, known limitations, and rollback.
3. Update the task-local ledger from `reviewing/submitted` to `integrated` or `accepted` only when the acceptance evidence supports it.
4. Update `TASK-PACKAGE-REGISTRY.md` and `.ai-team/TASK.md` for queue/integration state.
5. If a project milestone, feature status, version, or acceptance result changed, update the appropriate `.project-to-act` file and append a dated history/evidence record.
6. If architecture, scope, or a frozen decision changed, require a new decision record; do not silently rewrite R004/R005 or UD-006/UD-007.
7. If the task contract changed, flag the lane ZIP for regeneration. Do not regenerate ZIPs for ordinary progress or handoff-only updates.
8. Re-read changed sections and run project validation plus the relevant task/package checks.

## Update map

- Task execution fact → `.ai-team/tasks/<TASK-ID>.md`, `PROGRESS.md`, `HANDOFF.md`.
- Integration queue fact → `.ai-team/TASK.md`, `TASK-PACKAGE-REGISTRY.md`.
- Project milestone/feature/version/acceptance fact → `.project-to-act/PROJECT_*.md`.
- Architecture or scope decision → new decision record and linked architecture document.
- Task contract change → lane package source and ZIP regeneration.

For detailed rules, read [post-merge-checklist.md](references/post-merge-checklist.md) and [project-file-routing.md](references/project-file-routing.md).

## Non-negotiable rules

- Never mark a task accepted from a green diff alone.
- Never copy raw tool output, secrets, full private source, or chain-of-thought into project records.
- Preserve historical entries; append rather than overwrite decisions or evidence.
- Separate `integrated` (merged) from `accepted` (acceptance evidence passed).
- Report stale or missing evidence as blocked/unknown, not as complete.

## Output contract

```text
Merged commit / task:
Documents updated:
Evidence consumed:
New status:
Gate impact:
Remaining risks:
ZIP regeneration needed: yes/no
Next action:
```
