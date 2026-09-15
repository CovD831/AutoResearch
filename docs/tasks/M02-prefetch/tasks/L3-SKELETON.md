# L-02 M02 L3 骨架（证据前置检索 / 失效传播）

> **层级**：L3 骨架 —— **开工者必须把它补全成完整 L3 后再写代码**
> **上游权威**：R-007 `04-l2-contracts.md` **K7**（`PrefetchRecord`）+ **K8**（`InvalidationPropagation`）
> **原表**：M02-07（证据前置检索）、M02-09（失效传播）
> **base_ref**：`main@8dd8780`（**实测 537 passed / 2 skipped / 0 failed**，本 worktree 自测）
> **排他文件**：`evidence_prefetch.py` `invalidation.py`（**新开新文件**）

---

## 1. Task source

| 子任务 | 原表要求 | 本包契约 |
|---|---|---|
| **M02-07** | 「L2+ 动作前记录查询/候选/最终 bundle/决定」 | **K7** |
| **M02-09** | 「撤稿/过期/伪造/绕付费墙/未批准外发 → claim/Gate 重算或永久拒绝」 | **K8** |

---

## 2. 必须落地的契约

### K7 `PrefetchRecord`

**字段**：`prefetch_id` / `action_level`（L0–L4）/ `query` / `candidates` / `final_bundle_id` / `decision`（`proceed`|`blocked`）/ `created_at`

| # | 不变量 | 可校验 |
|---|---|---|
| K7-1 | **L2+ 动作前必须写一条** | ❌ **时序型约束（架构意图）** |
| K7-2 | **缺证据时 `decision="blocked"`（fail-closed）** | ✅ validator |
| K7-3 | `final_bundle_id` 必须指向已存在的 bundle | ✅ 外键式校验 |

> 🔴 **K7-1 是本包最容易写错的地方。**
> 初版 R-007 L2 曾把 K7 标为「三条全部可校验」—— **那是违反文档自身纪律的**，
> 第 1 关审查 B1 已纠正。**validator 校验不了「某动作发生前已写记录」。**
>
> **补偿手段（必须实现）**：在 L2+ 动作的**统一入口**处强制先写 prefetch
> （**代码结构层面**，例如把 prefetch 写进唯一的动作执行函数入口），而非依赖 validator。
> **禁止**为 K7-1 写「通过」断言 —— 那是恒真假绿。

### K8 `InvalidationPropagation`

**字段**：`propagation_id` / `source_evidence_id` / `reason`（`retracted`|`expired`|`forged`|`paywall_bypass`|`unapproved_egress`）/ `affected_claims` / `affected_gates` / `action`（`recompute`|`permanent_block`）/ `created_at`

| # | 不变量 | 可校验 |
|---|---|---|
| K8-1 | **永久阻断不可豁免** —— `forged`/`paywall_bypass`/`unapproved_egress` 必须 `permanent_block` | ✅ 枚举映射表 |
| K8-2 | 失效传播到关联 claim 与 Gate | ✅ 图遍历 |
| K8-3 | **`affected_claims` 不得为空**（空 = 传播断链 → **应报错而非静默通过**） | ✅ validator |

> ⚠️ **K8-3 是「空集被当作满分」的正面对防线**（本项目缺陷族）。
> 负例必须断言「空 `affected_claims` 时**报错**」，而不是断言「返回了空列表」。

---

## 3. 复用既有（**不得重造**）

- **K8 的撤稿判据复用 B5 的 `updated-by[]`**（PR #17 真实验收，`7fdfb89`）→ **复用，不重写**。
- **与 L-06 的接口（K7 侧）**：本契约的「查询/候选/最终 bundle」与 **R-006 C8 `RecallAuditRecord`** 字段有重叠。
  **两者是不同层的审计**：`RecallAuditRecord` 记**检索过程**，`PrefetchRecord` 记**门禁前置动作**。
  → **不得合并**；但 `candidates` 可引用同一来源。
- **与 L-01 的接口**：`evidence_prefetch` 与 L-06 的 L0 过滤概念相邻（R-007 L1 §6 列为**需协调**项之一）。
  → **开工时先读 `knowledge.py` 的 `retrieve()` 现有签名**，确认接口对齐方式。

---

## 4. ⚠️ 运行标识：**引用 K1，不得自造**

**R-007 `06-dispatch-sheet.md` §2 明文**：L-02 **不得定义自己的「运行标识」**。

- K1 `RunManifest` 由 **L-05** 在 `run_manifest.py` 独占定义（**契约先行**）。
- 本包的 `PrefetchRecord` 若需要运行维度，**必须引用 K1 的 `run_id`**。
- **开工前先确认 `run_manifest.py` 已在 main 或已可引用**；若 L-05 尚未冻结，
  本包先做**不依赖运行标识**的部分（K7-2/K7-3 的 validator、K8 全部）。

> **这正是 R-006 未合并时发生的事**：每条线各自发明运行标识 → 合起来必然矛盾。

---

## 5. 负例（**开工者补全**）

| # | 负例 | 断言什么 |
|---|---|---|
| N-1 | 缺证据 | `decision="blocked"`（**fail-closed**），不是 `proceed` |
| N-2 | `final_bundle_id` 指向不存在的 bundle | **外键校验失败**（不是静默通过） |
| N-3 | `reason="forged"` + `action="recompute"` | **被拒**（永久阻断不可豁免） |
| N-4 | `affected_claims=[]` | **报错**（不是静默返回空） |

---

## 6. Deliberate non-goals

- **不实现** R-006 C8 `RecallAuditRecord` 本身（属 R-006 P4，已冻结）。
- **不碰** `knowledge.py` / `storage.py` / `contracts.py` / `evidence.py` / `gates.py`。
- **不重写** B5 的撤稿判据。

---

## 7. 判别力 / 验收 / 偏离

判别力要求、验收命令、偏离登记要求同 `07-lane-kickoff-convention.md` §2 / §6。

```bash
PYTHONPATH=src python -m pytest tests/test_m02_*.py -q -o addopts="" -W error
PYTHONPATH=src python -m pytest -q -o addopts="" -W error    # 基线 537 passed 不得下降
ruff check src tests && compileall -q src
node .ai-team/check.mjs --base main
```
