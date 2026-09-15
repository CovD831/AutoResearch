# R-007 并行模块总纲

> **一句话**：把**所有可并行开发的线**（含此前漏掉的 M12）放进一份 L1/L2 里。

## 阅读顺序

1. **`05-execution-plan.md`** —— **单页可执行总表**（一页速览 + 三批顺序 + 已在手两条线 + 纪律 + 挂账）★ 从这里开始
2. **`06-dispatch-sheet.md`** —— **派单表**：现在能同时开哪几条线、各自排他文件与禁区、**各 lane 的 worktree 路径** ★ 要开工时看这张
3. **`07-lane-kickoff-convention.md`** —— **开工约定**：**L3 什么时候写、写在哪、谁写** + 三条纪律 + 门禁 ★ **每个 lane 开工前必读**
4. **`00-scope-and-authority.md`** —— 为什么需要它、覆盖什么、权威关系
5. **`02-l1-architecture.md`** —— 9 条线的分层、唯一写入者、不变量、文件面
6. **`04-l2-contracts.md`** —— K1–K16 字段级契约
7. **`03-review-and-steelman.md`** —— 两关审查记录（想了解设计为何是现在这样时读）

> **⚠️ 本包有意只写 L1 + L2。** L1/L2 是 program 级、集中一份；
> **L3 是任务包级，在具体任务开工时才写，且写在各自 lane 的 worktree 里** —— 这不是缺口，是设计。
> 详见 `07-lane-kickoff-convention.md`。

## 覆盖的 9 条线

| 线 | 模块 | 任务包 | 状态 |
|---|---|---|---|
| L-01 | M01 | 状态迁移 / ContextAssembler / 交接回放 | ⬜ 未开工 |
| L-02 | M02 | 证据前置检索 / 失效传播 | ⬜ 未开工 |
| L-03 | M04 | checkpoint 测试 / outbox / 迁移 | ⬜ 未开工 |
| L-04 | M05 | 撤稿 / OA / 许可检查 | ⬜ 未开工 |
| L-05 | M08 | RunManifest / 执行器 / lineage / R 等级 / 闭环 Gate | ⬜ 未开工（**契约先行**） |
| L-06 | M11 | Wiki+Graph / 检索 / 融合 / 回归 | ✅ **P1 已并入 main**（`75a2d64`）；MVP-01～04 待做（**串行**） |
| **L-07** | **M12** | **成熟度阶梯 / 沙箱复现 / 回流层 / 画像** | ✅ **P2 已交付并推送**（**依赖已解除**，P3/P6/P7 未开工） |
| L-08 | M13 | UI 四面板 | ⬜ 未开工 |
| L-09 | M14+M15 | ACL / PII / 许可 / telemetry | ⬜ 未开工 |

## 16 个契约（K1–K16）

| K | 契约 | 线 |
|---|---|---|
| K1 | `RunManifest` | L-05 |
| K2 | `ExecutionRequest` / `ExecutionResult` | L-05 |
| K3 | `ArtifactLineage` | L-05 |
| K4 | `ResultGrade` | L-05 |
| K5 | `ContextBudget` / `ContextSlice` | L-01 |
| K6 | `StateMigration` | L-01 |
| K7 | `PrefetchRecord` | L-02 |
| K8 | `InvalidationPropagation` | L-02 |
| K9 | `OutboxEntry` | L-03 |
| K10 | `RetractionStatus` | L-04 |
| K11 | `AccessPolicy` | L-09 |
| K12 | `SensitivityClass` | L-09 |
| K13 | `TelemetryPoint` | L-09 |
| K14 | `PanelProjection` | L-08 |
| **K15** | **`StageEvidence`**（P2 已实现） | **L-07** |
| **K16** | **`RegressionSet`** | **L-07** |

## 状态

**`accepted`** —— 两关已过（2026-09-15）。

- 第 1 关（独立对抗审查，子代理）：5 条发现，逐条核实
- 第 2 关（双向钢人论证，作者侧）：裁决 L-07×L-06 为 stacked + **发现 1 条硬冲突（§10.5）**
- 处置 12 项已回写，详见 `03-review-and-steelman.md`

### ✅ 跨线硬冲突已修复

`ExperienceService.record()` 原先未传递增 `revision`，在 append-only 下同一经验第二次写入会抛 `ValueError`。
**已修复并验证**：`owner/r006-l2-stage` @ `7318f64`，全量 `549 passed / 2 skipped / 0 failed`，判别力已实测。详见 L2 §10.5。

### ⚠️ 已作废的两句话（v2 实测修正，2026-09-15）

1. ~~「L-06 待合并」~~ → **L-06 的 P1 已并入 main**（`75a2d64`，经保护窗口）。
2. ~~「合并顺序不可颠倒：L-06 → L-07；L-07 单独合并会 `AttributeError`」~~ →
   **依赖已解除**。实测预演（`git merge --no-commit --no-ff origin/owner/r006-l2-stage`，base = 新 main）：
   自动合并成功、**549 passed**、**v4 任务包未被旧版覆盖**（688 行保留）、`base_ref` 正确。
   **L-07 现在可从新 main 直接合并。**

> 注意：`evolution_service.py` 上 **L-06 与 L-07 各自独立修了同一个 `record()` revision bug**
> （修法等价）。合并时该文件会真冲突，**按 L-07 版本保留**（注释更完整）。

### 📌 重要：L-06 内部四包是**串行栈**，不是可并行的 4 条线

MVP-01/02/03 **都改 `knowledge.py`**，且依赖是语义级的（02 的召回建立在 01 的边界上、
03 的融合吃 02 的 `RecallAuditRecord`）。详见 `06-dispatch-sheet.md` §3。

---

## 开工状态（2026-09-15）

**L1/L2 已冻结（`accepted`），本轮 7 条 lane 的 worktree 已由 owner 预建**，
base 统一为 `main@8dd8780`（**实测 537 passed / 2 skipped / 0 failed**）。

| 就绪度 | lane | 说明 |
|---|---|---|
| ✅ **L3 完整** | **L-05 第 1 步** | `M08-execution/tasks/M08-01-run-manifest/L3.md` |
| ✅ **L3 骨架已就位** | L-01 / L-03 / L-04 / L-08 / L-09前半 | 开工者补全 L3 后即可写代码 |
| ⏸ **部分可开工** | **L-02** | 「运行标识」部分须等 K1；K7-2/K7-3 validator 与 K8 全部可先做 |
| ⏸ **不在本轮** | L-06 MVP-01、L-07 剩余 | L-06 归成员 A（任务包 v4 已 ready）；**L-07 归属待定** |

**L3 骨架的定位**：它把该 lane 的契约条目、禁区、负例方向、判别力口径预先摆好，
让开工者不必重新推导 —— 但**实现设计与 deviations 必须开工者自己写**。
