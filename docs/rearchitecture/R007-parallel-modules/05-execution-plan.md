# R-007 执行总表（单页可执行）

> **用途**：本包是**本地自用**的实施总纲（非派单包，故不含 L3）。
> **阅读顺序**：本表 → `02-l1-architecture.md`（边界/不变量）→ `04-l2-contracts.md`（字段级契约）。
> **状态**：`accepted`（两关已过，2026-09-15）。**本表是唯一进度口径**，与 L1 §1 的线状态表同源。
> **v2（2026-09-15 15:15）**：L-06 已合入 main；L-07 的依赖关系经实测**已不阻塞**。见 §3。

---

## 1. 一页速览：9 条线的真实状态

| 线 | 模块 | 内容 | 状态 | 人日 | 文件面 |
|---|---|---|---|---:|---|
| **L-01** | M01 | 状态迁移 / ContextAssembler / 交接回放 | ⬜ 未开工 | 8 | `context_assembler.py` `migration.py` |
| **L-02** | M02 | 证据前置检索 / 失效传播 | ⬜ 未开工 | 8 | `evidence_prefetch.py` `invalidation.py` |
| **L-03** | M04 | checkpoint 测试 / outbox / 迁移 | ⬜ 未开工 | 11 | `outbox.py` ⚠️ **不碰 `storage.py`** |
| **L-04** | M05 | 撤稿 / OA / 许可检查 | ⬜ 未开工 | 4 | `external_sources.py`(扩展) + `retraction.py` |
| **L-05** | M08 | RunManifest / 执行器 / lineage / R 等级 / 闭环 Gate | ⬜ 未开工（**契约先行**） | **19** | `run_manifest.py` `executor.py` `lineage.py` `execution_gate.py` |
| **L-06** | M11 | Wiki+Graph / 候选召回 / 融合索引 / 回归 | ✅ **P1 已并入 main**（`75a2d64`）；MVP-01～04 待做（**串行**） | — | 见 §3 |
| **L-07** | M12 | 成熟度阶梯 / 沙箱复现 / 回流层 / 画像 | ✅ **P2 已交付并推送**（P3/P6/P7 未开工）；**依赖已解除** | — | 见 §3 |
| **L-08** | M13 | UI 四面板 | ⬜ 未开工 | 14 | `web/` + `web_api.py` |
| **L-09** | M14+M15 | ACL / PII / 许可 / telemetry | ⬜ 未开工 | 16 | `acl.py` `pii.py` `licensing.py` `telemetry.py` |

**本轮可开工合计：80 人日 / 7 条线**（L-01～L-05、L-08、L-09）+ **L-07 剩余（P3/P6/P7）已可开工**。
**L-06 内部四包是串行栈**，只占一条执行线（见 §3）。

**人日口径（可核对）**：取自 `docs/AutoResearch_任务拆解书_详细版.md` 的「待开发」子任务，
按模块归到线下 —— M01 8 + M02 8 + M04 11 + M05 4（M05-06，M05-07 gold set 属 M16 门）
+ M08 19（M08-02/03/04/05/06/07，含老板裁决「做真实实验」）+ M13 14 + M14 10 + M15 6。
**注意 L-09 的 16 = M14 10 + M15 6**（M15 剩余 9 人日待 M17 一并处理）。

**不在本纲**（老板裁决）：M16 真实试点（26 人日，等完整跑通）、M17 生产化（31 人日，依赖 M16）、
5 个 gold set（22 人日，依赖 M16-01）。**合计 79 人日移出本轮。**

**M03 / M09 / M10 出范围的理由**：M03 无活跃任务包（I0–I2 已跑通主线 E2E）；
M09/M10 的产出依赖真实实验（M16）。见 L1 §1。

---

## 2. 建议执行顺序（三批）

### 第 1 批：契约先行（**先做 L-05 的 RunManifest，1–2 天**）

**为什么先做它**：L-05 的 `RunManifest`（K1）是其余 6 条线的**共同前提**——
L-02 的 `PrefetchRecord`、L-09 的 `TelemetryPoint` 都要记录"哪次运行"。
先把 schema 冻住，后面 6 条线才不用各自发明。

```
L-05 第 1 步：只写 run_manifest.py（K1 字段级冻结）   ~1–2 天
```

### 第 2 批：6 条线并行（L-01 / L-02 / L-03 / L-04 / L-08 / L-09-前半）

**全部零冲突**（各自开新文件，实测文件面不相交）：

| 线 | 排他文件 | 注意 |
|---|---|---|
| L-01 | `context_assembler.py` `migration.py` | **`ContextAssembler` 要留「分级」接口**（它是 M11-04 ContextPack 的前置，别写死单级） |
| L-02 | `evidence_prefetch.py` `invalidation.py` | K7 的"L2+ 动作前必须写记录"是**时序型架构意图**，不是硬校验（见 L2 §K7） |
| L-03 | `outbox.py` | ⚠️ **不改 `storage.py`**（L-06 用其 `transaction()`） |
| L-04 | `external_sources.py` + `retraction.py` | 是**扩展**不是新建（`external_sources.py` 已有 673 行） |
| L-08 | `web/` + `web_api.py` | 按 `ui-skeleton-first`：先出喂真实数据的静态骨架 + 无头浏览器截图自查 |
| L-09 | `acl.py` `pii.py` `licensing.py` `telemetry.py` | K12 的 embedding 禁入是**空约束**（禁写"通过"断言）；成本指标复用 O12 的 `price_source` |

**+ 第 2 批可加一条**：**L-06 的 MVP-01**（唯一 ready 的包，依赖已满足）——
它与上面 6 条零交集（改 `knowledge.py` / `storage.py`，其余线全部新建文件）。
**但 L-06 内部 02/03/04 必须等 01**，见 §3。

### 第 3 批：L-05 剩余（执行器 / lineage / R 等级 / 闭环 Gate）+ L-09 后半

`RunManifest` 定稿后，L-05 的其余部分可与第 2 批并行；L-09 的 telemetry 依赖 L-05 的 K13。

---

## 3. 已在手的两条线（**不要重复实现**）

### L-06 M11 —— **P1 已并入 main**；MVP-01～04 是串行栈

| 项 | 内容 |
|---|---|
| 分支 | **已合并**（`owner/r006-l1-writer` @ `ea1663b` → main `75a2d64`） |
| 已交付 | R-006 P1：append-only wiki 写入者 + `wiki_page_head` 索引 + `get_page`/`list_pages` |
| 任务包 | `docs/tasks/M11-knowledge-lane/`（`SOURCE-AND-HANDOFF.md` 是第一入口，v4） |
| 验证 | **537 passed / 2 skipped / 0 failed**（全新克隆复现） |
| **待做** | M11-MVP-01（N+1 修复 / 桥接边白名单 / 正向测试）→ 02 → 03 → 04 |
| **base_ref** | **`main`（语义引用）** —— 已不需要 `owner/r006-l1-writer` |

**归属**：成员 A。

#### ⚠️ L-06 内部四包是**严格串行栈**，不是可并行的 lane

实测两两**写面交集**（`allowed_paths ∪ conditional_paths`）：

| 组合 | 交集 |
|---|---|
| MVP-01 × 02 | `knowledge.py` + `docs/tasks/M11-knowledge-lane/` |
| MVP-01 × 03 | `knowledge.py` + 同上 |
| MVP-02 × 03 | `knowledge.py` + 同上 |
| MVP-01/02/03 × 04 | `docs/tasks/M11-knowledge-lane/` |

**三个包都改 `knowledge.py`**（01 改 `list_pages`；02 改 `retrieve()` 加三路；03 改 `retrieve()` 加融合）。
且依赖是**语义级**的：02 的召回建立在 01 的分区边界上、03 的融合吃 02 的 `RecallAuditRecord`、
04 的回归对比 03 的混合检索。**并行会得到四份互不兼容的假设，然后全部返工。**

**→ L-06 只占一条执行线，串行跑完 01→02→03→04。**

### L-07 M12 —— P2 已交付并推送；**依赖已解除**

| 项 | 内容 |
|---|---|
| 分支 | `origin/owner/r006-l2-stage` @ **`7318f64`** |
| 交付 | 成熟度阶梯 X0→X4（`advance_stage` / `StageEvidence`）+ 修复 `record()` 的 revision 递增 |
| 验证 | 单独合并预演：**549 passed / 2 skipped**（含 12 条新测试） |
| **未做** | P3 沙箱复现与回归集（K16）、P6 回流层双通道、P7 用户画像三层 |

#### ✅ 依赖关系更新（v2 实测修正）

**原文写「L-07 依赖 L-06 的 `get_page()`，单独合并会 `AttributeError`」——现已不成立。**

1. **L-06 已并入 main**，`get_page()` 就在 main 里；
2. **预演实测**：`git merge --no-commit --no-ff origin/owner/r006-l2-stage`（base = 新 main）→
   自动合并成功、**549 passed**、**v4 任务包未被旧版覆盖**（688 行保留）、`base_ref` 正确。

→ **L-07 现在可以从新 main 直接合并**，不再需要「先 L-06 再 L-07」的栈式顺序。
**上一版本文档的「合并顺序不可颠倒」的红字警告已作废。**

> 注意：`evolution_service.py` 上 **L-06 与 L-07 各自独立修了同一个 `record()` revision bug**
> （修法等价，变量命名不同）。合并时该文件会真冲突，**按 L-07 版本保留**（注释更完整）。

**与 M11 派单的关系**：**L-07 完全不在 M11 任务包里**，实测两条证据：
- M11 包全文搜 `advance_stage|ExperienceStage|StageEvidence|maturity` → **0 命中**
- `evolution_service.py` / `profile_service.py` 是 M11 四个包的 **`frozen_paths`**

→ **两条线的文件边界互斥，可以放心各自推进。**

---

## 4. 三处必须串行的文件（唯一硬约束）

| 文件 | 被谁占 | 规则 |
|---|---|---|
| **`contracts.py`** | L-06 / L-07 | **条件允许**（L-06 的判据见 `TASK-SPECS.md` §5-B2 的 A/B/C）；其他线**在新模块里定义自己的类型** |
| **`knowledge.py` 写入路径** | L-06 | 其他线**只读**，且必须走 `get_page()` |
| **`storage.py`** | L-06（`transaction()`） | L-03 只新建 `outbox.py`，**不改它** |

**判据（本项目已验证 3 次）**：**新 lane 一律开新文件**。
`search_adapters.py`(830) / `provider_lane.py`(1722) / `audit_evidence.py`(894) 都是这么长出来的，从未撞车。

**⚠️ 补充（v2）**：改为 `frozen_paths` 的 4 个文件
（`evolution_service.py` / `profile_service.py` / `reader_service.py` / `search_service.py`）
**L-06 不得再动** —— P1 已改过（补 `author=` 必填 + `record()` revision 派生）。
L-07 会动 `evolution_service.py`，那是它的**本职工作**，不冲突。

---

## 5. 三条纪律（各对应一次真实事故）

1. **文件面检查必须配语义耦合检查。**
   本项目**三次**栽在"文件不重叠但语义耦合"：S2-B 的 `audit.py` add/add、A7×P1 的 `knowledge.py`、
   **L-07×L-06 的 `record()`**（前者已实测复现并修复）。

2. **测试可能固化缺陷。**
   同型**三例**：`stays_zero`（断言 `cost.total == 0.0`）、`test_malformed_payload...`
   （断言 `rerun.unreadable == 0`）、`len(pages) == len(records)`（固化 upsert 语义）。
   **共同特征：测试名和 docstring 是对的，断言是错的。**
   改缺陷时必查「有没有测试在断言这个错误行为」。

3. **裸露的「未测/缺失」绝不许记成正常值。**
   本项目反复出现「空/无样本被当作满分」、「退化路径上把未知记成正常值」。
   凡 `except ...: return <正常值>` 处，必须有断言该退化路径**结果正确**的测试，
   而非只断言「没崩」。K4 的 **R0 = 未运行**、K13 的 **`value=None` = 未测**（**绝不用 0**）是这条的落地。

---

## 6. 待裁决 / 挂账（不阻塞开工）

| # | 事项 | 影响 |
|---|---|---|
| 1 | ~~**L-06 何时合并 main**~~ | ✅ **已解决**（`75a2d64`，经保护窗口，12/12 项恢复一致） |
| 2 | **L-07 归谁** | 老板：只要不在 M11 派单里即可（已确认不在）；**P3/P6/P7 归属待定** |
| 3 | `wt-p0` / `wt-l3-retrieval` 两个**残留 worktree** | 已实测为纯副本 → 可删（需老板确认） |
| 4 | `wt-a8` 的 P0 保留资产（`experience_injection.py` 649 行等）**未提交、分支未推送** | 有丢失风险 |
| 5 | **M16 何时开** | 需提供：领域、问题、目标 venue、时间窗、授权全文、实验资源边界 |
| 6 | **（新增）L-07 是否本轮合并** | 依赖已解除（预演 549 passed），但从新 main 合仍需走一次保护窗口 |

---

## 7. 附：本包文件清单

| 文件 | 内容 |
|---|---|
| `00-scope-and-authority.md` | 范围、权威关系、三条纪律 |
| `02-l1-architecture.md` | L1：9 线分层 / 唯一写入者 / 9 硬不变量 / 5 架构意图 / 文件面 / 波次与并行矩阵 |
| `03-review-and-steelman.md` | 两关审查记录（第 1 关 5 条发现 + 第 2 关 S2 硬冲突 + 修复记录） |
| `04-l2-contracts.md` | L2：**K1–K16** 字段级契约 + 生效阶段标注 + §10.5 跨线冲突 |
| **`05-execution-plan.md`** | **本表**：一页速览 + 三批顺序 + 已在手两条线 + 纪律 + 挂账 |
| `06-dispatch-sheet.md` | **派单表（v2 新增）**：可并行开工的线 × 排他文件 × 禁区 |

**16 个契约**：K1 `RunManifest`｜K2 `ExecutionRequest/Result`｜K3 `ArtifactLineage`｜K4 `ResultGrade`｜
K5 `ContextBudget/Slice`｜K6 `StateMigration`｜K7 `PrefetchRecord`｜K8 `InvalidationPropagation`｜
K9 `OutboxEntry`｜K10 `RetractionStatus`｜K11 `AccessPolicy`｜K12 `SensitivityClass`｜K13 `TelemetryPoint`｜
K14 `PanelProjection`｜K15 `StageEvidence`｜K16 `RegressionSet`
