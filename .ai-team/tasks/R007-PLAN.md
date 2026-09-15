# R007 Plan Freeze

- ID: `R007-PLAN`
- Title: `R-007 并行模块改造 —— L1/L2 program 计划冻结 + 开工约定`
- Status: `done`
- Owner: `user/team`
- Next owner: `unassigned`

## Goal

把 R-007 的 L1/L2 **program 级**计划（9 条线的分层、K1–K16 字段级契约、派单表）在 main 上冻结，
并向各 lane 提供统一的**开工约定**。

**为什么 L3 不在这里**：L1/L2 是 program 级、集中一份；**L3 是任务包级，在具体任务开工时才写、
且写在各自 lane 的 worktree 里** —— 这不是缺口，是设计（见 `07-lane-kickoff-convention.md`）。

## Acceptance scenarios

- [x] `04-l2-contracts.md` 的 K1–K16 字段级契约在 main 可见，含「合并顺序依赖已解除」的 v2 修正
- [x] `06-dispatch-sheet.md` v3 列明 7 条 lane 的 worktree、排他文件与禁区；**端点口径更正为 24**（实测）
- [x] `README.md` 阅读顺序纳入 `07`，并声明「本包有意只写 L1+L2」
- [x] `07-lane-kickoff-convention.md` 含 §3.4–§3.8.1（收口硬检查 / 审计时序 / 环境依赖证据 / 突变有效性 / 守卫覆盖面）

## Invariants

- 本 PR 不动任何产品代码：`src/` `tests/` `web/` 零改动。
- 本 PR 不含 L3：L3 写在各自 lane 的 worktree 里。
- **`07` 的权威版本是 370 行版**；各 lane worktree 里的 153 行旧版必须丢弃、不得提交。
  （两版差异：主仓版是旧版的严格超集，多出 §3.4–§3.8.1 五节方法论。）

## Decisions

- **D-R007-P0-01**：`07` §3.4 的哈希扫描**只作兜底**，不作「树是干净的」的证明 ——
  它对**无任何标记**的突变是隐形的（如 `<=` 改 `<`、删 `return early`）。
  真正的完备判据是「把最后一次全量绿绑到交付态 hash 上」或「突变在 fixture 脚本里声明并自动还原」。
- **D-R007-P0-02**：`restore`**不得依赖脚本跑到底** ——
  命令被中断时尾部动作不保证执行。（实证：一次冻结命令被中断，树根本没建出来，而我差点拿不存在的冻结件去汇报。）
- **D-R007-P0-03**：**端点口径以代码实测为准 = 24**，
  逐条核对命令：`grep -cE '@app\.(get|post|put|patch|delete)\("' src/autoresearch/api.py`。
  本文早先几处写的 22 已更正（`06-dispatch-sheet.md` / `ALIGNMENT-PLAN-A-K.md` / `KICKOFF-NON-R006.md`）。

## Completed

- `04-l2-contracts.md`（M）：合并顺序表述修正为「依赖已解除」，并注明 `evolution_service.py` 的真冲突处理
- `06-dispatch-sheet.md`（M）：v3 派单表 + worktree 约定 + **端点数 22→24 更正**
- `README.md`（M）：阅读顺序纳入 `07` + 开工状态表
- `07-lane-kickoff-convention.md`（A，370 行）：开工约定全文
- 本台账

## Pending

- 无。P0 的交付是**声明性**的（计划与约定），不含实现。

## Next step

各 lane 以本 PR 为 base 开各自的 PR。**合并顺序**：

```text
P0（本 PR）
 ├─ P1 L-05 / P2 L-01 / P3 L-02 / P4 L-03 / P7 L-09   ← 无依赖，任选顺序
 │    └─ P5 L-04（依赖 P3 的 K8 owner）
 └─ P6a L-08 代码+生成链  ─→  P6b L-08 纯视觉快照
```

## Verification

- [x] `git diff --stat` 仅含 `docs/` 与 `.ai-team/`，`src/` `tests/` `web/` 零改动
- [x] `07` 为 **370 行**版（非各 lane worktree 里的 153 行旧版）
- [x] 端点数为 **24**，与 `src/autoresearch/api.py` 的路由装饰器逐条一致
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/R007-PLAN.md --base <base>` → `Result: valid`
- [x] `python scripts/check_pr_contract.py --base <base>` → `PR contract check passed`

## Handoff note

**给各 lane 开工者的三条硬约束**（详见 `07-lane-kickoff-convention.md`）：

1. **`07` 以主仓的 370 行版为准** —— 你的 worktree 里若有一份 153 行的旧版，**丢弃它，不要提交**。
2. **台账元数据字段的格式是机器解析的**：
   `.ai-team/check.mjs` 的 `field()` 用严格正则 `^- Name: \`([^\`]+)\`$` ——
   **值内不得有内层反引号，行尾不得有明文注解**。违反会让整值解析为 `null`，
   并报出「missing metadata」这类与真实原因无关的错误。注解请写在 `Next step` 或 `Handoff note`。
   （实证：3 个 PR 因这条规则门禁红。）
3. **合入前必查**（三条实测踩过的坑）：
   - `pytest -q -o addopts=""` + **看 summary 行与退出码**，不要数点阵
   - 引用基线数字前**在该 commit 上实测**，不跨 worktree 搬运
   - **并发验证必须一任务一工作树** —— 多个审计者共用一棵树时，
     `git checkout` 会互相覆盖 HEAD（实证：3 个互不知情的审计者各自撞到）
