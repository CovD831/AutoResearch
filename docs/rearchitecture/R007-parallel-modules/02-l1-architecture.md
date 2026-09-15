# R-007 L1 目标架构（并行模块总纲）

> **状态**：`accepted`（**两关已过**，2026-09-15；第 1 关 5 条发现 + 第 2 关 1 条硬冲突全部处置）
> **建立**：2026-09-15
> **范围**：**覆盖全部可并行开发的分支** —— 含 M11/M12（经验/知识）在内的 9 条线
> **上位**：`docs/AutoResearch_任务拆解书_详细版.md`（原计划权威）+ `docs/AutoResearch_详细计划书.md` §10–§19
> **关系**：R-006（知识/经验）为本 program 的子集；R-006 P1/P2 的成果直接并入

---

## 0. 为什么需要这份总纲

**此前的问题**：L1/L2 是按单个 program 出的（R-004 一份、R-006 一份），
导致 **P2（成熟度阶梯）所属的 M12 从未被任何 L1/L2 覆盖** —— 这是我们刚才发现的漏洞。

**本纲的做法**：把**所有并行线**放在一份架构下，统一边界、不变量与唯一写入者。

---

## 1. 覆盖范围（9 条并行线）

| 线 | 模块 | 任务包 | 归谁 | 状态 |
|---|---|---|---|---|
| **L-01** | M01 | 状态迁移 / ContextAssembler / 交接回放 | 你 | 未开工 |
| **L-02** | M02 | 证据前置检索 / 失效传播 | 你 | 未开工 |
| **L-03** | M04 | checkpoint 测试 / outbox / 迁移 | 你 | 未开工 |
| **L-04** | M05 | 撤稿 / OA / 许可检查 | 你 | 未开工 |
| **L-05** | M08 | RunManifest / 执行器 / lineage / R 等级 / 闭环 Gate | 你 | 未开工 |
| **L-06** | M11 | Wiki+Graph 规范来源 / 候选召回 / 融合索引 / 回归 | **成员 A** | ✅ **P1 已并入 main**（`75a2d64`）；MVP-01～04 待做（**内部串行**）；`M11-MVP-01～04` 已派 |
| **L-07** | **M12** | **成熟度阶梯 / 沙箱复现 / 回流层 / 画像** | 未派（不在 M11 包内） | ✅ **P2 已交付并推送** `owner/r006-l2-stage` @ `7318f64`（**依赖已解除**，可从新 main 直接合并；原 stacked 于 L-06**）；P3/P6/P7 未开工 |
| **L-08** | M13 | UI 四面板 | 你 | 未开工 |
| **L-09** | M14/M15 | ACL / PII / 许可 / telemetry | 你 | 未开工 |

**不在本纲**：M16（真实试点，裁决②延后）、M17（生产化，依赖 M16）、5 个 gold set（依赖 M16-01）。

### 为什么 M03 / M09 / M10 也出范围（第 1 关 D1 要求显式交代）

| 模块 | 为什么不在本轮并行线 |
|---|---|
| **M03** LangGraph 工作流 | 原表状态「基础已落地」，I0–I2 已完成主线 E2E；**无活跃任务包**（实测 `docs/tasks/` 无 M03 目录） |
| **M09** 写作 | 同上；且 **M09-03 结果稿依赖 M08-06**（属 L-05）→ 本纲完成后才解锁 |
| **M10** 审核 | 同上（S4-A Benchmark Harness 已交付基础能力） |

**→ 三者属「已完成基线」或「等待依赖」，不是被遗漏。**

---

## 2. 分层

```text
┌──────────────────────────────────────────────────────────────────┐
│  L5 消费层     Agents · UI 面板 · CLI/API                        │
│      ├─ 事实通道（evidence）：可进论断                            │
│      └─ 经验通道（guidance）：experiential 标注，禁入事实声明      │
├──────────────────────────────────────────────────────────────────┤
│  L4 适配层     ContextAssembler · 入口共享服务                    │
├──────────────────────────────────────────────────────────────────┤
│  L3 领域层                                                        │
│      ├─ 执行域   RunManifest · Executor · Lineage · ResultGrade   │
│      ├─ 经验域   ExperienceService（成熟度阶梯）· ProfileService   │
│      └─ 检索域   RetrievalPipeline（词法+向量+图）                 │
├──────────────────────────────────────────────────────────────────┤
│  L2 可信层     Evidence · Gate · Invalidation · Audit             │
├──────────────────────────────────────────────────────────────────┤
│  L1 地基层     KnowledgeStore（唯一写入者）· RecordStore · Outbox  │
└──────────────────────────────────────────────────────────────────┘
```

**依赖方向**：L5 → L4 → L3 → L2 → L1。**不允许反向依赖。**

---

## 3. 唯一写入者（**全体必须遵守**）

| 事实 | 唯一写入者 | 既有/新增 |
|---|---|---|
| `WikiPage` / `Statement` / `GraphEdge` | **KnowledgeStore** | 既有（R-006 P1 已强化为 append-only） |
| `ExperienceRecord` / `EvolutionProposal` | **ExperienceService** | 既有（P2 补 `advance_stage`） |
| `UserProfileItem` | **ProfileService** | 既有 |
| `EvidenceItem` / `ClaimLink` / invalidations | **Evidence Module** | 既有 |
| `GateDecision` | **Policy/Gate** | 既有 |
| `invocation receipt` | **Thin Runtime** | 既有 |
| **`RunManifest` / `ExecutionResult`** | **Executor 域**（新） | **L-05 新建** |
| **`ArtifactLineage`** | **Lineage 域**（新） | **L-05 新建** |
| **`OutboxEntry`** | **Outbox**（新） | **L-03 新建** |
| `AuditReport` 内容 | Audit Module | 既有 |
| run lifecycle / checkpoint | Runtime + Checkpoint Adapter | 既有 |

**禁止反向依赖与越权**：
- Agent / Skill / MCP / Adapter → **不得**直写 Store、不得 → `GateDecision`
- Gate → **不得** → Writer
- Audit → **不得**直写 `EvidenceItem`
- **检索层 → 不得**生成 `EvidenceItem` / `GateDecision` / 真实性结论
- **执行域 → 不得**直接改 `EvidenceItem`（只能产 `EvidenceCandidate` 走准入）

---

## 4. 不变量（全 program 级）

### 4.1 硬不变量（有代码级强制）

| # | 内容 | 强制手段 | 归属线 |
|---|---|---|---|
| **I1** | **`WikiPage` revision 不可覆盖** | append-only 写入者拒绝 `revision ≤ max` | L-06（**已实现**） |
| **I2** | **跨分区边必须受管**（类型声明语义） | 边类型白名单校验 | L-06（**待实现**） |
| **I3** | **经验晋级必须逐级、不可跳级** | `advance_stage` 只允许 `+1` | **L-07（P2 已实现）** |
| **I4** | **X1+ 必须双向边界齐全** | pydantic validator | **L-07（P2 已实现）** |
| **I5** | **未运行结果永远 R0** | `ResultGrade` 默认 R0 + 升级须过检查 | L-05（**待实现**） |
| **I6** | **执行产物必须可追到 RunManifest** | lineage 外键式校验 | L-05（**待实现**） |
| **I7** | **resume/retry 不重复副作用** | 幂等键（outbox） | L-03（**待实现**） |
| **I8** | **证据失效 → statement 降级，不删除** | 无 delete API；状态机单向 | L-02（**待实现**） |
| **I9** | **`require_evidence=True` 时无证据页面不得进入结果** | 检索层过滤 | L-06（**待实现**） |

### 4.2 架构意图（**无技术强制，必须如实标注**）

| # | 内容 | 为什么无强制 | 补偿 |
|---|---|---|---|
| **A1** | 经验不替代事实 | 双通道是**提示结构**，LLM 仍可能误用（*Grounding is not a prompt*） | **输出侧**：论断必须可追溯到 evidence 通道（复用 R-004 门禁） |
| **A2** | 桥接边不传递等价性 | `APPLIES_TO` 不意味着"事实依据" | 消费端（回流层）保证 |
| **A3** | 摘要经验保留 raw 轨迹回链 | 回链真伪不可机械判定 | 字段必填 + code review |
| **A4** | 评估集独立于自进化流程 | 治理层约定 | 流程纪律 |
| **A5** | UI 不展示虚假完成 | 展示层约定 | 面板必须区分"已验证/未验证" |

> **纪律（源自 R-006 §11.8）**：**不是所有写下来的不变量都能被违反** ——
> 凡当前**无法被违反或无从校验**的约束，**必须标注生效阶段**，且**禁止为其写"通过"断言**（会造出恒真假绿）。

### 4.3 阶段性硬依赖（**发布门禁，不是数据不变量**）

> **来源**：原计划 §3 的硬依赖条款（第 1 关 C3 指出 L1 遗漏）。
> **性质**：这些**不是数据层不变量**，而是**阶段门禁** —— 违反它们不会让数据错，但会让**声明失真**。

| # | 门禁 | 内容 | 强制性 |
|---|---|---|---|
| **G1** | **W1 未通过时，任何 L2+ 自动化操作不得上线** | W1 = 合同/证据/状态/规范存储。**已通过**（R-004 完成） | 已验证 ✅ |
| **G2** | **W3 未建立 gold set 时，不能声称检索/阅读质量** | W3 的 gold set **依赖 M16-01**（老板裁决延后）→ **当前生效中** | **生效** |
| **G3** | **W4 未有真实 RunManifest 时，写作只能生成明确缺口稿** | 依赖 L-05（M08）；**L-05 完成前一直生效** | **生效** |
| **G4** | **W7 未通过时，版本名称必须保留 `Preview` 或 `Pilot`** | W7 = 真实论文试点（已延后）→ **当前生效** | **生效** |

**处置纪律**：
- 这四条**不得写进测试断言**（不是数据不变量），而是**写入交付文档与发布检查清单**
- **G2/G3/G4 当前均在生效状态** → 任何声称"检索质量达标"/"结果稿"/"1.0 版本"的表述都**必须先检查这三条**

---

## 5. 各线的边界（文件面）

**核心规则：新线一律开新文件。判据 —— 代码里没有出现那个机制的 API 名，就说明在重新实现它。**

| 线 | 排他文件（新建） | 禁止触碰 |
|---|---|---|
| **L-01** | `context_assembler.py` `migration.py` | `knowledge.py` `storage.py` `contracts.py` |
| **L-02** | `evidence_prefetch.py` `invalidation.py` | 同上 + `evidence.py` `gates.py` |
| **L-03** | `outbox.py` | **`storage.py`**（L-06 用其 `transaction()`） |
| **L-04** | `retraction.py` + `external_sources.py`（扩展） | `search_service.py` |
| **L-05** | `run_manifest.py` `executor.py` `lineage.py` `execution_gate.py` | `evidence.py` `gates.py` |
| **L-06** | `knowledge.py` `storage.py` `contracts.py`（owner 批准） `knowledge_retrieval.py` `knowledge_fusion.py` `knowledge_index.py` `recall_audit.py` | 其余全部 |
| **L-07** | `stage_evidence.py`（新建）+ **修改既有** `evolution_service.py` `profile_service.py` | `knowledge.py` `contracts.py`（需协调） |
| **L-08** | `web/` + `web_api.py` | `src/autoresearch/`（只读消费 API） |
| **L-09** | `acl.py` `pii.py` `licensing.py` `telemetry.py` | — |

> ⚠️ **修正（第 1 关 B2）**：L-07 的 `evolution_service.py`（3882 字节）/ `profile_service.py`（1503 字节）
> **实测已存在**，**不是新建文件，是既有共享模块**。
> 原文档标为「新建」**掩盖了耦合** —— 见下「语义耦合」。

### ⚠️ 三处必须串行

| 文件 | 谁占 | 规则 |
|---|---|---|
| **`contracts.py`** | L-06（P1 已 **+234/−2**） | **只有 owner 批准才能改**；其他线用新模块定义自己的类型 |
| **`knowledge.py` 写入路径** | L-06 | 其他线**只读**，且必须走 `get_page()` |
| **`storage.py`** | L-06 | L-03 只新建 `outbox.py`，**不改 `storage.py`** |

**跨线协调点**：
- **L-07 要改 `contracts.py`**（`ExperienceRecord` 的 stage 派生）—— 需与 L-06 协调
- ✅ **协调成本实测很低**：**P2 是 P1 的严格超集**，`diff` 显示 P2 相对 P1 在 `contracts.py` 上**只多 11 行**（一个 `@model_validator`），改的是不同 class → **git 可自动合并**

### 🔴 语义耦合（**必须逐条检查，不能只看文件面**）

> **纪律（源自本项目三次事故）**：**文件不重叠 ≠ 无冲突**。
> 事故史：S2-B `audit.py` add/add、A7×P1 `knowledge.py`、**本次 L-07×L-06 `record()`**。

| 被依赖的文件 | 依赖方（实测） | 状态 |
|---|---|---|
| `evolution_service.py` | `application.py:42,166,168`；`experience_sink.py:21,38,53,314` | ⚠️ **原文档未检查** → 已补 |
| `knowledge.py` | `application.py:166`；`reader_service.py`；`search_service.py`；`evolution_service.py:116` | ⚠️ **原文档未检查** → 已补 |
| `profile_service.py` | `application.py` | ⚠️ **原文档未检查** → 已补 |

**🔴 实测硬冲突（S2）**：`ExperienceService.record()` 构造 `WikiPage(...)` 时**未传 `revision`**（默认 `1`），
而 L-06 的 `add_page` 强制 append-only → **同一经验的第二次写入抛 `ValueError`**。

**实测复现**（把 L-07 的 `evolution_service.py` 叠到 L-06 分支上）：
```
第 1 次 record OK
第 2 次 record 失败 → ValueError: revision 1 must be > current max 1
                      for page e1 (append-only: revisions are never overwritten)
```

**为什么是高严重度**：`experience_sink.py:547` **明确会重复调** `record()`，
且 `:755` 用 `recurrence_count=max(1, recurrence)` —— **"同一条经验被再次记录"正是 A6 的核心场景**。
（`experience_sink.py:540-543` 的注释已承认「Re-running `record` would append a second audit page」—— 它在**绕开**而非修好。）

**→ L-07 叠上来之前必须修复：`record()` 必须传递增 `revision`（或由 `get_page()` 派生 `current+1`）。**

---

## 6. 波次与并行度

```
W0 ✅ 治理发布（已完成）
W1 ✅ 合同/证据/状态/存储（R-004 已完成大半）
W2 ✅ 五 Agent 工作流闭环（mainline E2E 已跑通）
W3 ⚠️ 文献检索与阅读（部分完成：Crossref/docling 已真实验收）

【本轮】W4-W5 并行（9 条线）
  ├─ L-06 M11（成员 A，已派；P1 已并入 main `75a2d64`）
  ├─ L-07 M12（P2 已交付并推送，**依赖已解除**；P3/P6/P7 未开工）
  ├─ L-01 / L-02 / L-03 / L-04（基础设施，零冲突）
  ├─ L-05 M08（**契约先行**，19 人日）
  ├─ L-08 M13 UI（14 人日）
  └─ L-09 M14/M15（16 人日）

**本轮 7 条线可开工：80 人日。详见 [`05-execution-plan.md`](05-execution-plan.md)。**

W6 ⏸ 知识/经验/运维（部分在本轮）
W7 ⏸ 真实试点（裁决②延后）
```

### 并行度矩阵

| | L-01 | L-02 | L-03 | L-04 | L-05 | L-06 | L-07 | L-08 | L-09 |
|---|---|---|---|---|---|---|---|---|---|
| L-01 | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| L-02 | ✅ | — | ✅ | ✅ | ✅ | ⚠️见下 | ✅ | ✅ | ✅ |
| L-03 | ✅ | ✅ | — | ✅ | ✅ | ⚠️见下 | ✅ | ✅ | ✅ |
| L-04 | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| L-05 | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ |
| L-06 | ✅ | ⚠️ | ⚠️ | ✅ | ✅ | — | ⚠️ | ✅ | ✅ |
| L-07 | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | — | ✅ | ✅ |
| L-08 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| L-09 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |

**⚠️ 三处需协调（**修正**：原表述「33 对可并行」过于乐观）**：
- **L-02 × L-06**：`evidence_prefetch` 与 L-06 的 L0 过滤概念相邻（文件不重叠，接口要对齐）
- **L-03 × L-06**：都涉及幂等/事务语义；`storage.py` 归 L-06
- **L-07 × L-06**：~~stacked（须先 L-06 后 L-07）~~ → **v2 实测修正：依赖已解除**（L-06 的 P1 已入 main，预演 549 passed）。原硬冲突 S2 **已修复**（见 §5）

**→ 修正后的准确表述**：
> **33 对为「文件面可并行」；其中 L-06 × L-07 原为 stacked —— v2 实测修正：S2 已修复、依赖已解除，两者均可从当前 main 独立开工。**
> **⚠️ 但 L-06 内部四包（MVP-01～04）是串行栈，不是 4 条并行线** —— 三者都改 `knowledge.py`。见 `06-dispatch-sheet.md` §3。

**其余 33 对文件面无交集**，但**仍需逐线做语义耦合检查**（§5）。

---

## 7. 与既有 program 的关系

| Program | 覆盖 | 本纲的处理 |
|---|---|---|
| **R-004**（信任层） | S1–S4、I0–I4 | **已完成，作为基础层**（L2 可信层 + L1 地基层的既有部分） |
| **R-006**（知识/经验） | P1–P7 | **拆入 L-06（M11）+ L-07（M12）**；P1/P2 已完成 |
| **R-007**（本纲） | **全部并行线** | 统一边界、不变量、唯一写入者 |

**R-006 的 L1/L2 仍是 L-06/L-07 的详细契约来源**（`04-l2-contracts.md` 的 C1–C9），本纲不重复。

---

## 8. 本纲的定位

**本纲只做三件事**：
1. **统一边界**：谁能写什么（§3）
2. **统一不变量**：什么必须成立、什么是架构意图（§4）
3. **统一文件面**：谁占哪些文件（§5）

**本纲不做**：字段级契约（在 R-006 L2 + 各线自己的 L2 里）、实现细节、验收命令。

---

## 9. 待办（本纲自身）

| # | 项 |
|---|---|
| 1 | **两关审查**（对抗性独立审查 + 双向钢人论证）—— 按 owner 2026-09-14 纪律，未过两关不算定稿 |
| 2 | 补 `L2-CONTRACTS.md`（14 个新契约，见配套文件） |
| 3 | 与 L-06/L-07 协调 `contracts.py` 的改动顺序 |
