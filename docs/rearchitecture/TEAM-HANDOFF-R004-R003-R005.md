# AutoResearch 重构团队审查包

## 这是什么

这是 AutoResearch 全项目重构的团队审查入口，包含三层材料：

```text
R-004：全项目重构总计划
  ↓
R-003：S1 Paper Search 当前实现权威
  ↓
R-005：S1 收口设计与下一步实施入口
```

重要：项目重构目标是整个 AutoResearch，不是只做论文搜索。Paper Search 只是第一个真实纵向切片，用来证明新的边界、幂等、证据和恢复机制。

## 建议阅读顺序

### 所有人先读

1. `R005-s1-closure-design/TEAM-READING-GUIDE.md`
2. `R004-trust-program/README.md`
3. `R005-s1-closure-design/EXECUTIVE-SUMMARY.md`
4. `R005-s1-closure-design/DECISION-BOARD.md`
5. `ARCHITECTURE-V2-DRAFT.md`（全项目论文生成 pipeline 候选架构，供讨论，不是当前权威）
6. `AUTORESEARCH_ARCHITECTURE_GUIDE.md`（项目级架构与协作总手册）
7. `P1-WORKTREE-TASK-PLAN.md`（两条 worktree 的独占路径、L3 委托和合并顺序）
8. `docs/tasks/P1-A-runtime-recovery/TASK-PACKAGE.md` 与 `docs/tasks/P1-B-evidence-pipeline/TASK-PACKAGE.md`（两份可直接分发的任务包）

### 想理解全项目方向

阅读：

- `R004-trust-program/00-scope-and-authority.md`
- `R004-trust-program/01-positioning-and-complexity.md`
- `R004-trust-program/02-l1-target-architecture.md`
- `R004-trust-program/05-migration-and-evidence.md`
- `R004-trust-program/diagram/architecture.svg`

### 参与 S1 实现

阅读：

- `R003-paper-search-adapter/README.md`
- `R003-paper-search-adapter/01-l3-paper-search-adapter.md`
- `R003-paper-search-adapter/03-fixtures.md`
- `R003-paper-search-adapter/04-acceptance.md`
- `R005-s1-closure-design/04-l2-contracts.md`
- `R005-s1-closure-design/06-handoff.md`

## 当前状态

| 包 | 作用 | 当前状态 |
|---|---|---|
| R-004 | 全项目目标架构与 S0–S4 路线 | active program |
| R-003 | S1 Paper Search 实现与验收权威 | active implementation，closure evidence 待补 |
| R-005 | S1 parity/recovery 收口设计 | design，implementation-candidate |

## 本轮团队需要反馈什么

请重点反馈：

- 目标架构是否清楚，是否存在职责重叠；
- S1 作为第一切片是否合理；
- parity、recovery、Evidence sole-writer 是否可验收；
- `unknown` 语义和 pending recover 是否有更好的方案；
- 当前任务拆分是否适合团队实际能力。

反馈请尽量使用：

```text
位置：哪个包 / 哪一节
问题：具体不清楚或可能出错的地方
证据：代码、测试或文档路径
建议：保留、修改或删除什么
影响：影响哪个边界、门禁或任务
```

## 当前不要求团队做什么

- 不要求现在修改运行时代码；
- 不要求现在冻结 L3；
- 不要求现在开始 S1 实现；
- 不把讨论中的方案当成已批准实现要求。

负责人收集完反馈后，再通过 `DECISION-BOARD.md` 完成决策冻结，随后才创建 implementation package 并正式分配任务。
