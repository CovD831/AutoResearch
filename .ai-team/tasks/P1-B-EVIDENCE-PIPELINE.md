# Current Task

- ID: `P1-B-EVIDENCE-PIPELINE`
- Title: `Evidence / Writing Pipeline / Readiness`
- Status: `ready`
- Owner: `member B`
- Next owner: `user/team`

## Goal

完成第一条产品价值链：Evidence admission、Evaluation 章节计划、WritingProfile、benchmark 计划、材料缺口检查和章节规则验证。

## Acceptance scenarios

- [ ] candidate 有来源、locator、claim 和 provenance，并能去重和处理冲突。
- [ ] SectionPlan/SectionDraft 只消费已允许的 claims/evidence/artifacts。
- [ ] 关键材料缺失返回 `blocked`，非关键缺失返回 `needs_material`。
- [ ] BenchmarkPlan 区分计划与真实结果。
- [ ] section validation 返回 `verified / revise / blocked` 并有可定位原因。

## Invariants

- Evidence Module 是正式 EvidenceItem/ClaimLink/ArtifactLink 的唯一写入者。
- 不修改 P1-A 独占路径、`application.py`、共享 `contracts.py`。
- 不新增第二套 Store、总线、scheduler 或 Agent。

## Decisions

- 继承 UD-006/UD-007；具体 L3 由成员 B 在任务包中自行决定。

## Completed

- 任务包和 worktree 边界已准备。

## Pending

- 成员 B 填写 L3 并实施。

## Next step

创建 `codex/p1-evidence-pipeline` worktree，填写 L3，实施并提交验证证据。

## Verification

- [ ] `ruff check src tests`
- [ ] P1-B 相关 pytest
- [ ] readiness/benchmark/section validation reports
- [ ] `node .ai-team/check.mjs --task .ai-team/tasks/P1-B-EVIDENCE-PIPELINE.md`

## Handoff note

- From: `member B`
- To: `user/team`
- Required: changed paths、测试、pipeline evidence、rollback、已知限制和 rebase 说明。
