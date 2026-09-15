# M11 Knowledge Lane — readiness revision (v3)

- ID: `M11-READINESS-V3`
- Title: `M11 task pack v3 — readiness audit fixes + R-006 P1 merge`
- Status: `active`
- Status note: 就绪性审计发现 M11 任务包**不可开工**（6 项缺陷），本 ledger 记录修订内容与两个新发现。同时把 R-006 P1（`ea1663b`）合入 main，解锁 MVP-01。
- Owner: `owner`
- Next owner: `member A`（M11-MVP-01 可开工）

## Goal

让 M11 知识库 lane 从「文档自洽但不可执行」变为「可开工」：
修掉审计发现的 6 项就绪性缺陷，并把其硬前置 R-006 P1 合入 main。

## Decisions

- **D-M11-01 `contracts.py` 从自相矛盾改为「条件允许」**。原状态：`task-package.json` 的 `allowed_paths` 含它、
  `lane-manifest.json` 的 `forbidden_shared_paths` 也含它、`SOURCE-AND-HANDOFF.md` 写「owner 决定」但从未决定。
  新规则 = default deny + A/B/C 三选一（A 新增字段 / B 有失败用例的契约 bug 修复 / C 新增契约模型），
  **禁止**删除或改名 `RetrievalHit` 既有对外字段、改动 C2/C9、借顺手重构改组织方式；每个 hunk 须在 PR 描述里列出命中哪条。
  依据：全禁会让 MVP-03 的 `score_breakdown` 无处落地，必然逼出平行结构（本项目「新模块绕过现成原语」缺陷族）；全放会让人删字段（违反 lane 不变量 3）。
- **D-M11-02 新增边界类 `frozen_paths`**。P1 实际改了 4 个 `forbidden_paths` 文件（原稿漏列）。
  「禁止」与「已改过」并存会让执行人困惑 → 改列 `frozen_paths`（只读不得改）。
- **D-M11-03 `base_ref` 由 `04ce9a9` 改为 P1 的实际 sha**。`04ce9a9` 是 main，**不含 P1 的代码**，基线指向错误。
- **D-M11-04 先合 P1 再开 MVP-01**（老板 2026-09-15 采纳建议）。理由：P1（写入者基建）与 M11（边界 + 检索）性质不同，
  混一个 PR 会让审查面从 +234 膨胀到 +4536，且 M11 是三包串行栈。

## Acceptance scenarios

- [x] A1 `contracts.py` 在 `task-package.json` / `lane-manifest.json` / `SOURCE-AND-HANDOFF.md` 三处归类一致。
- [x] A2 4 个 P1 已改文件全部移入 `frozen_paths`，且逐处说明授权依据。
- [x] A3 `tests/test_governance_services.py` 加入 `allowed_paths`，并在「必须满足」与 `contracts_to_satisfy` 里点名其断言位置。
- [x] A4 四包 + lane-manifest 的 `base_ref` 全部为 P1 的实际 sha。
- [x] A5 三条 gate 命令修正后**实测可跑**（解释器全路径 + `PYTHONPATH=src`；`check.mjs --base` 改传 P1 sha）。
- [x] A6 三个待新建交付物标 `CONSTRUCTED:`；账本要求写入开工步骤。
- [x] A7 行号与性能数字在 `9c60043` 上**重新实测**更正。
- [x] A8 R-006 P1 以 `--ff-only` 合入 main（`04ce9a9` → `ea1663b`），合并态全量 **537 passed / 2 skipped**。
- [x] A9 5 个 JSON 全部校验合法。

## Invariants

- **未测/未验证不得写成已达标**；数字引用必须注明 worktree 与 commit。
- **基线不可跨 worktree 搬运**：`537 passed` 只对 `9c60043` 成立。
- **`check.mjs` 报 blocked 时先定位是哪个文件缺账本**，不要默认是自己改坏了。
- **P1 与 M11 的合并顺序不可颠倒**：MVP-01 承接 P1 的 `get_page()` / head 索引。

## New findings

- **F-M11-01 P1 分支自身过不了 `check.mjs`**（不是 M11 的问题）。实测：
  `--base 9c60043`（自身）→ `valid`；`--base main` → `blocked`（"changed without updating a member ledger"）。
  根因：P1 改了 29 文件但 `.ai-team/tasks/` 下无账本（对照 `l2-stage` 有账本故 valid）。
  **已修**：`ea1663b` 补建 `.ai-team/tasks/R006-L1-WRITER.md`，补后转 `valid`。
- **F-M11-02 L-06 与 L-07 各自独立修了同一个 `record()` revision bug**（修法等价，变量命名不同）。
  含义：R-007 说的「L-07 依赖 L-06 的 `get_page()`」代码层面已不成立；但两分支合并时
  `evolution_service.py`（第 24-40 行区域）**会真冲突**，按 L-07 版本保留（注释更完整）。

## Verification

```
PYTHONPATH=src python -m pytest -q -o addopts="" -W error      # 537 passed, 2 skipped
python -m ruff check src tests                                  # All checks passed!
python -m compileall -q src                                     # clean
node .ai-team/check.mjs --base <prev sha>
```

合并预演：临时 worktree 上 `git merge --no-commit --no-ff owner/r006-l1-writer` → 自动合并成功，
合并态全量 537 passed / ruff clean / 30 files。

## Follow-up: base_ref moved to the merged main (v4)

R-006 P1 was merged into main through the protection window
(`04ce9a9` → `ea1663b` → `f31d0dc`; protection restored and verified 12/12).

The task pack was updated in the same change:

- All four `task-package.json` and `lane-manifest.json`: `base_ref` `9c60043` → `f31d0dc`
  (the previous value pointed at an unmerged branch).
- `TASK-SPECS.md` → v4: §5-B1 marked resolved with the execution record;
  MVP-01 status changed from "ready but blocked" to "ready, can start".
- `TASK-QUEUE.md` → v4: blocking banner removed.
- `SOURCE-AND-HANDOFF.md` → v4: §0 and §7 rewritten to cut from `origin/main`;
  the `upstream/owner/r006-l1-writer` instruction is gone (P1 is in main now).

Merge dry-run: temporary worktree `git merge --no-commit --no-ff owner/r006-l1-writer`
→ clean, 537 passed, ruff clean, 30 files.

> Note: the first `--ff-only` attempt aborted because the main worktree held an
> untracked copy of this task pack (the local v3 revision) that collided with the
> same paths arriving from P1. Handled by backing v3 up, moving the local copy
> aside, merging, then restoring v3 on top — v3 is a superset (664 vs 419 lines).

## Handoff note

**MVP-01 已解锁**：base 是合并后的 main。执行人按 `TASK-SPECS.md` §7 开工，
第一步跑裸 id 枚举（§7.3）+ 建自己的账本 `.ai-team/tasks/M11-MVP-01.md`。
