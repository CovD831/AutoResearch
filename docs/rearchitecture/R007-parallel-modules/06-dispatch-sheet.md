# R-007 派单表（v3 · 2026-09-15）

> **本表回答一个问题：现在到底能同时开几条线、各自碰哪些文件。**
> 配套：`05-execution-plan.md`（三批顺序）、`02-l1-architecture.md`（边界）、`04-l2-contracts.md`（契约）、
> **`07-lane-kickoff-convention.md`（开工约定 —— L3 怎么写、worktree 怎么用）**。
> **判据（本项目已验证 3 次）**：**新 lane 一律开新文件** —— 文件面不相交才叫可并行。

---

## 零、worktree 与 L3 的约定（**v3 新增**）

**本包有意只写 L1 + L2** —— 那是 program 级、集中一份。
**L3 是任务包级，在具体任务开工时才写，且写在各自 lane 的 worktree 里。**

```bash
cd ../r007-<lane>          # 已由 owner 预建，base = main@8dd8780
# 1. 实测基线（537 passed / 2 skipped / 0 failed —— 不得搬运别人的数字）
# 2. 写本包的 L3（docs/tasks/<lane>/tasks/<PKG>/L3.md）—— 这是开工第一步
# 3. 建本包账本（.ai-team/tasks/<PKG>.md）
# 4. 实现 + 自测取证
```

**各 lane 的 worktree（owner 已预建）**：

| lane | worktree | 分支 | L3 骨架（已就位，开工者补全） |
|---|---|---|---|
| **L-05** | `../r007-l05-execution` | `feat/r007-l05-execution` | `docs/tasks/M08-execution/tasks/M08-01-run-manifest/L3.md` **（完整版，非骨架）** |
| **L-01** | `../r007-l01-context` | `feat/r007-l01-context` | `docs/tasks/M01-context/tasks/L3-SKELETON.md` |
| **L-02** | `../r007-l02-prefetch` | `feat/r007-l02-prefetch` | `docs/tasks/M02-prefetch/tasks/L3-SKELETON.md` |
| **L-03** | `../r007-l03-outbox` | `feat/r007-l03-outbox` | `docs/tasks/M04-outbox/tasks/L3-SKELETON.md` |
| **L-04** | `../r007-l04-retraction` | `feat/r007-l04-retraction` | `docs/tasks/M05-retraction/tasks/L3-SKELETON.md` |
| **L-08** | `../r007-l08-ui` | `feat/r007-l08-ui` | `docs/tasks/M13-ui/tasks/L3-SKELETON.md` |
| **L-09** | `../r007-l09-security` | `feat/r007-l09-security` | `docs/tasks/M14-15-security/tasks/L3-SKELETON.md` |

> **骨架的定位**：它把该 lane 的**契约条目、禁区、负例方向、判别力口径**预先摆好，
> 让开工者不必重新推导 —— 但**实现设计与 deviations 必须开工者自己写**（骨架里明标「开工者补全」）。

---

## 一、可并行开工的线（一张表）

| # | 线 | 人日 | 排他文件（**只碰这些**） | 前置 | 状态 |
|---|---|---:|---|---|---|
| 1 | **L-05 第 1 步** | ~1–2 | `run_manifest.py`（K1 冻结） | 无 | 🟢 **建议最先做** |
| 2 | **L-01** | 8 | `context_assembler.py` `migration.py` | 无 | 🟢 可开工 |
| 3 | **L-02** | 8 | `evidence_prefetch.py` `invalidation.py` | 无 | 🟢 可开工 |
| 4 | **L-03** | 11 | `outbox.py` | 无 | 🟢 可开工 |
| 5 | **L-04** | 4 | `external_sources.py`（扩展）+ `retraction.py` | 无 | 🟢 可开工 |
| 6 | **L-08** | 14 | `web/` + `web_api.py` | 无 | 🟢 可开工 |
| 7 | **L-09 前半** | 10 | `acl.py` `pii.py` `licensing.py` | 无 | 🟢 可开工 |
| 8 | **L-06（M11-MVP-01）** | 3 | `knowledge.py` `storage.py` (`contracts.py` 条件) | 无（P1 已入 main） | 🟢 **可开工** |
| 9 | **L-07（P3/P6/P7）** | — | `evolution_service.py` 等 | 无（依赖已解除） | 🟢 可开工（归属待定） |

**并行汇总**：**8 条互相零交集的线**（1–8）。
人日算术（可核对）：`8+8+11+4+14+10`（L-01～L-04、L-08、L-09前半）= **55**，加 L-06 的 MVP-01 **3** 人日 = **58**；L-05 全量 **19** 人日（含第 1 步）单独计；L-07 待定。
→ 与 `05-execution-plan.md` §1 的口径一致：全量 **80 人日 / 7 条线**（L-05 计入 19）。

**第 3 批**（须等 L-05 的 K1）：L-05 剩余（执行器 / lineage / R 等级 / 闭环 Gate）+ L-09 后半（telemetry 依赖 K13）。

---

## 二、每条的禁区（**必读**）

| 线 | 🔴 绝不能碰 | 原因 |
|---|---|---|
| L-01 | 不定义自己的 `RunManifest` | 用 K1 |
| L-02 | 不定义自己的「运行标识」 | 用 K1；K7 的时序要求是**架构意图**不是硬校验 |
| **L-03** | 🔴 **不改 `storage.py`** | L-06 的 `transaction()` 在那里 |
| L-04 | 不新建 `external_sources.py` | 它是**扩展**（已有 673 行） |
| L-08 | 不改后端 | 24 个 API 端点已够用；按 `ui-skeleton-first` 先出静态骨架 |
| L-09 | 不写"K12 通过"断言 | embedding 禁入是**空约束**（无向量实现），标 `【向量落地后生效】`；成本未测一律 `None`，**绝不用 0** |
| **L-06** | 🔴 **不改 4 个 frozen 文件**：`evolution_service.py` / `profile_service.py` / `reader_service.py` / `search_service.py` | P1 已改过（补 `author=` + `record()` revision 派生） |
| L-07 | 不碰 M11 任务包 | 两条线边界互斥 |

> **口径更正（2026-09-15 实测）**：API 端点数是 **24**，不是本文早先几处写的 22。
> 逐条核对命令：`grep -cE '@app\.(get|post|put|patch|delete)\("' src/autoresearch/api.py` → `24`。
> 清单见 `04-l2-contracts.md` 的 K14 节与 L-08 的 `HANDOFF.md`（后者先于本次更正发现并记录了该差异）。

**全局三处串行**：

| 文件 | 占用方 | 其他线怎么做 |
|---|---|---|
| `contracts.py` | L-06 / L-07 | **条件允许**（判据见 `TASK-SPECS.md` §5-B2 的 A/B/C）；其他线在新模块定义自己的类型 |
| `knowledge.py` 写入路径 | L-06 | **只读**，且必须走 `get_page()`（裸 id 读不到） |
| `storage.py` | L-06（`transaction()`） | 不改 |

---

## 三、⚠️ L-06 内部是**串行栈**，不是可并行的 4 条线

**实测两两写面交集**（`allowed_paths ∪ conditional_paths`）：

```
MVP-01 × 02 → knowledge.py ✗
MVP-01 × 03 → knowledge.py ✗
MVP-02 × 03 → knowledge.py ✗
MVP-01/02/03 × 04 → docs/tasks/M11-knowledge-lane/ ✗
```

三个包都改 `knowledge.py`（01 改 `list_pages`；02/03 改 `retrieve()`）。
**且依赖是语义级的**：

```
MVP-01 分区边界 + get_page()
   ↓ 02 的三路召回建立在这个边界上
MVP-02 三路召回 + RecallAuditRecord
   ↓ 03 的融合吃 02 的审计记录（集合包含链）
MVP-03 混合检索
   ↓ 04 的回归报告对比 03 的混合 vs 纯词法
```

**→ L-06 只占 1 条执行线，串行跑完 `01 → 02 → 03 → 04`。**
并行会得到四份互不兼容的假设，然后全部返工。

---

## 四、建议的开工批次

```
第 1 批（今天）：L-05 第 1 步（run_manifest.py，K1 冻结）~1–2 天
                 ↑ 它是 L-02 的 PrefetchRecord、L-09 的 TelemetryPoint 的共同前提
                 ← L3 已就位（完整版，非骨架），可直接开工
                 同时可并行：L-06 的 MVP-01（不依赖 K1）
                 同时可并行：L-01 / L-03 / L-04 / L-08 / L-09前半（不依赖 K1，骨架已就位）
                 ⏸ L-02 的「运行标识」部分须等 K1；其余（K7-2/K7-3 validator、K8 全部）可先做

第 2 批：L-02 剩余（引用 K1）+ L-06（继续 02）
         ← 全部零交集

第 3 批：L-05 剩余（executor / lineage / R 等级 / 闭环 Gate）+ L-09 后半（telemetry 依赖 K13）
```

**为什么 L-05 第 1 步排最前**：其余 6 条线都要记「哪次运行」，
不先冻 K1 的话，每条线会各自发明一个运行标识 → 合起来必然矛盾（这正是 R-006 L1/L2 未合并时发生的事）。

---

## 五、本表的口径

- **人日**：取自 `docs/AutoResearch_任务拆解书_详细版.md` 的「待开发」子任务，按模块归线（详见 `05-execution-plan.md` §1）。
- **不在本表**：M16 真实试点（26）、M17 生产化（31）、5 个 gold set（22）= **79 人日**，
  等 M16 参数（领域 / 问题 / venue / 时间窗 / 授权全文 / 资源边界）到位后再开。
- **M03 / M09 / M10**：M03 无活跃任务包；M09/M10 依赖真实实验（M16）。
