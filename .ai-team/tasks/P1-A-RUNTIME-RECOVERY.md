# Current Task

- ID: `P1-A-RUNTIME-RECOVERY`
- Title: `Runtime / Capability / Recovery`
- Status: `handoff`
- Owner: `member A`
- Next owner: `user/team`

## Goal

完成 Paper Search 可靠调用边界：幂等、receipt、replay、timeout、pending、unknown、restart/recovery 和 legacy/target parity。

## Acceptance scenarios

- [x] 相同 identity 和 fingerprint 只调用 connector 一次。
- [x] fingerprint 冲突明确拒绝。
- [x] `completed_empty` 与 `unknown_outcome` 区分。
- [x] pending、timeout、restart 和 recover/fail 均有可重跑测试。
- [x] legacy/target parity report 可重跑。

## Invariants

- 不修改 P1-B 独占路径、`application.py`、共享 `contracts.py`。
- reserve 先于 connector 副作用；精确 replay 不重复调用。
- adapter 不直接写 Evidence 状态或 GateDecision。

## Decisions

- 继承 UD-006/UD-007；具体 L3 由成员 A 在任务包中自行决定。

## Completed

- 任务包和 worktree 边界已准备；L3、实现、fixture 和测试已完成。

## Pending

- 已完成 L3、实现、fixture、专项/全量测试和 parity 报告；结果已写入 task-local handoff。

## Next step

负责人审查 `HANDOFF.md`、parity 报告和分支 diff；确认共享边界后 rebase/合并。

## Verification

- [x] `ruff check src tests`（通过；另含 parity 脚本）
- [x] P1-A 相关 pytest（9 passed；全量 `pytest -W error -q` 为 27 passed）
- [x] parity/recovery report（`docs/rearchitecture/worktrees/A-runtime-recovery/parity-report.json`，`overall_equal=true`）
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/P1-A-RUNTIME-RECOVERY.md --base main`（valid）

## Handoff note

- From: `member A`
- To: `user/team`
- Required: changed paths、测试、parity/recovery evidence、rollback、已知限制和 rebase 说明，均见 `HANDOFF.md`。
