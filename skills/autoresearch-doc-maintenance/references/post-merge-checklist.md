# Post-merge documentation checklist

## Required inputs

- merged commit and PR/task ID;
- accepted task-local ledger;
- `HANDOFF.md`;
- test and static-check results;
- evidence/report paths;
- reviewer and integration decision;
- known limitations and rollback.

## Required updates

1. Mark the task `integrated` only after the commit is in the target branch.
2. Mark it `accepted` only after the task acceptance scenarios and verification evidence pass.
3. Update the global registry row: status, merged revision, evidence, next package, and blockers.
4. Update `.ai-team/TASK.md` only for the current integration queue and batch state.
5. Update Project-to-Act only when project-level progress, feature status, version, evidence, or acceptance changes.
6. Append a dated history entry; do not erase older conclusions.
7. If a promotion Gate passes, record the Gate result, evidence IDs, limitations, and newly unlocked tasks.

## Do not update automatically

- Do not mark unrelated features complete.
- Do not rewrite architecture decisions because implementation differs; create a decision record or record a deviation.
- Do not regenerate a ZIP for ordinary code progress.
- Do not copy complete logs or private data into durable documents.
