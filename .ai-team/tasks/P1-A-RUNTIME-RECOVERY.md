# Current Task

- ID: `P1-A-RUNTIME-RECOVERY`
- Title: `Runtime / Capability / Recovery`
- Status: `ready`
- Owner: `member A`
- Next owner: `user/team`

## Goal

完成 Paper Search 可靠调用边界：幂等、receipt、replay、timeout、pending、unknown、restart/recovery 和 legacy/target parity。

## Acceptance scenarios

- [ ] 相同 identity 和 fingerprint 只调用 connector 一次。
- [ ] fingerprint 冲突明确拒绝。
- [ ] `completed_empty` 与 `unknown_outcome` 区分。
- [ ] pending、timeout、restart 和 recover/fail 均有可重跑测试。
- [ ] legacy/target parity report 可重跑。

## Invariants

- 不修改 P1-B 独占路径、`application.py`、共享 `contracts.py`。
- reserve 先于 connector 副作用；精确 replay 不重复调用。
- adapter 不直接写 Evidence 状态或 GateDecision。

## Decisions

- 继承 UD-006/UD-007；具体 L3 由成员 A 在任务包中自行决定。

## Completed

- 任务包和 worktree 边界已准备。

## Pending

- 成员 A 填写 L3 并实施。

## Next step

创建 `codex/p1-runtime-recovery` worktree，填写 L3，实施并提交验证证据。

## Verification

- [ ] `ruff check src tests`
- [ ] P1-A 相关 pytest
- [ ] parity/recovery report
- [ ] `node .ai-team/check.mjs --task .ai-team/tasks/P1-A-RUNTIME-RECOVERY.md`

## Handoff note

- From: `member A`
- To: `user/team`
- Required: changed paths、测试、parity/recovery evidence、rollback、已知限制和 rebase 说明。
