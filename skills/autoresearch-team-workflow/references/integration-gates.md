# Integration gates

## Merge Gate

Before merging a PR, verify:

- changed paths are within the task package;
- task-local ledger, code, tests, and handoff are in the same PR;
- required tests and static checks pass;
- failure and recovery semantics are tested;
- evidence reports are reproducible;
- no secrets, generated databases, unrelated changes, or unauthorized shared-contract edits are present;
- rollback and rebase instructions are clear.

## Promotion Gate

Before promoting a phase, verify:

- all blocking findings for the phase are resolved;
- the merged mainline scenario passes;
- the evidence report is fresh and rerunnable;
- downstream contracts are stable;
- Project-to-Act and the registry agree on status.

## Commands

Use the task-local check for member work:

```bash
node .ai-team/check.mjs --task .ai-team/tasks/<TASK-ID>.md --base origin/main
```

Run project tests and any package-specific checker named by the task package. Never infer a pass from a green-looking diff alone.
