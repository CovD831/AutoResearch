# Owner mode

## Queue review

Read `docs/rearchitecture/TASK-PACKAGE-REGISTRY.md`. Confirm the task is registered, its dependencies are satisfied or explicitly marked `speculative`, and its owner lane is unambiguous.

## Async rule

Members may continue a `ready-next` task while an earlier PR is reviewing. They must use a separate branch or stacked branch and rebase after the predecessor merges. Do not interpret a submitted PR as an accepted task.

## Shared files

The project负责人 owns `src/autoresearch/application.py`, shared `src/autoresearch/contracts.py`, `.project-to-act/`, `.ai-team/TASK.md`, and the registry. A member's cross-boundary request must be recorded in HANDOFF before the owner changes it.

## State updates

Update the registry when a task becomes `active`, `submitted`, `reviewing`, `integrated`, `accepted`, `blocked`, or `superseded`. Update Project-to-Act only for actual project-level scope, milestone, evidence, or acceptance changes.
