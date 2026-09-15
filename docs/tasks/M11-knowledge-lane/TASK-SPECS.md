# M11 知识库 lane — 任务规格（改进版）

> **版本**：v2（2026-09-15，owner 改进稿）
> **基础**：成员 A 提交的 `M11-MVP-01～04` 拆分（结构采纳）+ R-006 L2 契约（择优注入）
> **改动摘要**：见文末 §改动对照
> **权威关系**：本文件是 M11 lane 的执行权威；R-006 的 L1/L2 降为**参考设计**，只在本文件明确引用的地方生效。

---

## 0. 与 R-006 的关系（重要）

**R-006 已暂停 P2–P7，不再作为 M11 的验收依据。** 但 R-006 有三样东西经比对后优于原拆分，已注入本文件：

| 注入项 | 出处 | 注入位置 |
|---|---|---|
| **append-only 写入者**（`record_id = f"{page_id}:r{revision}"` + head 索引） | R-006 P1（**已实现，537 passed**） | MVP-01 |
| **受管桥接边白名单**（14 类） | R-006 C3（方向）+ 原设计 §12.3（清单） | MVP-01 |
| **`RecallAuditRecord`（L8 召回审计）** | R-006 C8 | MVP-02 |

**未注入的**：R-006 的 C2 `Statement`（暂缓，无消费方）、C9 `ExperienceInjection`（属 M12，不属 M11）。

---

## 1. lane 总览

| 包 | 对应原文 | 目标 | 依赖 | 规模 |
|---|---|---|---|---|
| **M11-MVP-01** | M11-01/02/03 | Wiki+Graph 规范来源与边界 | 无（承接 R-006 P1） | 3 |
| **M11-MVP-02** | M11-05 | 候选召回管线（三路） | MVP-01 | 5 |
| **M11-MVP-03** | M11-07 | 融合、去重、索引维护 | MVP-02 | 4 |
| **M11-MVP-04** | M11-08 | 固定回归与验收证据 | MVP-03 | 4 |

**lane 级不变量**（全部包都必须满足）：

1. **检索层只负责召回和排序，不判断内容真实性。**
2. **不得在检索层生成 `EvidenceItem` / `GateDecision` / 真实性结论。**
3. **不得改变 `KnowledgeService.retrieve()` 的输入签名与 `RetrievalHit` 的对外字段**（可新增字段，不可删除/改名既有字段）。
4. **所有行为可离线重复验证**（无网络依赖）。
5. **每个包的代码、测试、fixture、任务账本、验收证据、rollback 说明必须在同一交付快照中保持一致。**

---

## M11-MVP-01 — Wiki+Graph 规范来源与边界

- **状态**：`ready`
- **对应原文**：M11-01、M11-02、M11-03
- **目标**：固定 Wiki+Graph 的分区、页面版本和图边边界，为后续检索建立唯一规范来源。
- **依赖**：M04-01（已落地）、**R-006 P1（已实现，待合并——见下）**

### 主要交付

- 分区边界（五分区保持）
- **WikiPage append-only 版本写入者**（承接 R-006 P1）
- **`wiki_page_head` 索引 + `get_page()` / `list_pages()` 解析入口**
- **GraphEdge 受管桥接边白名单**
- 来源与 `evidence_ids` 保留

### 必须满足

1. **保留 `papers`、`experiences`、`knowledge`、`profiles`、`projects` 五个 Wiki 分区**（不改分区语义）。
2. **Evidence 使用独立的 `kind`（`"evidence"`），不得进入 Wiki 检索结果。**
   > ⚠️ 措辞更正：原拆分写「Evidence 使用独立 RecordStore」——**实测是同一个 `RecordStore` 实例**（`evidence.py` 用 `kind="evidence"`，`knowledge.py` 用 `kind="wiki_page"`）。意图正确，措辞与实现对齐。
3. **WikiPage 修改不得覆盖已有 revision。**
   - 写入路径：`record_id = f"{page_id}:r{revision}"`，**每个 revision 一条记录**
   - 新 revision 必须 `revision = max(既有) + 1`
   - 裸 `page_id` 通过 `wiki_page_head` 索引解析（`{current_revision_id, revision}`）
   - 版本写入与 head 更新**必须同一事务**
4. **GraphEdge 的两个端点必须存在**（不改）。
5. **跨分区 GraphEdge 使用受管桥接类型（白名单），无类型跨分区边拒收。**
   - **受管桥接边（14 类，允许跨分区）**：
     `CITES`、`SUPPORTS`、`CONTRADICTS`、`INVALIDATES`、`DERIVED_FROM`、
     `APPLIES_TO`、`USES_METHOD`、`USES_DATASET`、`EVALUATES_ON`、`HAS_LIMITATION`、
     `EXTENDS`、`IMPROVES`、`CREATED_IN`、`PREFERS`
   - **同类边（3 类，不跨分区）**：`SUMMARIZED_BY`、`DUPLICATES`、`SUPERSEDES`
   - **白名单可经注册表扩展，不改代码**
   - **桥接边不传递等价性**（架构意图，需消费端保证）
6. **页面和图边保留 `project_id`、`partition`、`record_id`、`evidence_ids` 等追踪字段。**
7. **`list_pages` 必须为 O(1) 查询数**（不得每条 head 一次 `store.get`）。
8. **所有按裸 `page_id` 读取的地方必须走 `get_page()`**，包括 `add_edge` 端点解析与 `retrieve` 图扩展邻居解析。

### 禁止

- 改变现有分区语义；
- 将 Evidence、Experience 和 Paper 混成无类型数据；
- **在本包引入向量召回或排序逻辑**；
- **改回 `record_id = page_id`**（会使 append-only 失效）；
- **在 `add_edge` / `retrieve` 内直接 `store.get("wiki_page", 裸id)`**（head 索引后查不到）；
- **把桥接边白名单扩展成"任意字符串都可以"**。

### 验收

| 类型 | 项 |
|---|---|
| 正例 | 同一页面创建新版本时**旧版本仍可读取** |
| 正例 | **白名单类型跨分区边被允许**（⚠️ 新增，见下） |
| 正例 | 页面来源、分区和 `evidence_ids` 可被完整读取 |
| 负例 | **直接覆盖旧 revision 被拒绝** |
| 负例 | **跨分区无类型 GraphEdge 被拒绝** |
| 负例 | 端点不存在时拒绝 |
| 性能 | **N 页时 `store.get` 调用数 ≤ 常数**（对照：旧版为 0，不得退化到 N） |
| 一致性 | 所有行为可离线重复验证 |

> ⚠️ **必须补正向测试**：既有测试**只覆盖「拒绝」侧**（R-006 两关结论 Q2：「`ValidationError ⊂ ValueError`，既有测试仍绿」）。
> 白名单收窄后**必须新增「白名单类型跨分区被允许」的正向断言**，否则新语义无人校验。
> 同时需**新增**「裸 id 查不到 → `get_page` 能查到」的对照断言。

### MVP 边界

只完成 Wiki+Graph 规范来源和边界。**不实现** `Statement`（statement 级证据绑定，留待 M02-09 失效传播需要时）、ContextPack、向量检索和生产级图数据库。

---

## 承接说明：R-006 P1 的处理

**R-006 P1 已实现本包的核心**（`wt-l1-writer` 分支，实测 **537 passed / 2 skipped / 0 failed**）：

| 已实现 | 文件 |
|---|---|
| `WIKI_PAGE_HEAD_KIND` 常量 + append-only `add_page` | `knowledge.py:13,29-75` |
| `get_page()` / `list_pages()` | `knowledge.py:78-115` |
| `add_edge` 改走 `get_page()` | `knowledge.py:118-133` |
| `retrieve` 图扩展改走 `get_page()` | `knowledge.py:178` |
| `storage.transaction()` / `_write_record()` | `storage.py:41-79` |
| C1–C9 契约字段 | `contracts.py`（+236 行） |
| `tests/test_r006_contracts.py` | 17 passed |

### 本包的增量工作（P1 未做或做错的部分）

| # | 增量 | 说明 |
|---|---|---|
| **1** | **修 N+1** | `list_pages` 现为 `for head in heads: store.get(...)`；实测 200 页 = 200 次 `get` / **118ms**（旧版 1 次 `list` / **1.03ms**）。**改法**：`RecordStore` 加一个 JOIN 查询方法（一条 SQL 取 head + version） |
| **2** | **桥接边白名单** | P1 保留了一刀切禁止（`knowledge.py:126`）。**本包需实现 14 类白名单 + 3 类同类边** |
| **3** | **正向测试** | 补「白名单跨分区被允许」+「`get_page` 能解析裸 id」两条正向断言 |
| **4** | **contracts.py 上收** | P1 的契约改动在 `contracts.py`（+236）；本包合并时由 owner 决定是否上收 |

### 分支与文件边界

```
branch: codex/m11-mvp-01
allowed_paths:
  src/autoresearch/knowledge.py
  src/autoresearch/storage.py
  src/autoresearch/contracts.py          # ⚠️ 仅在 owner 批准下修改
  tests/test_knowledge_boundary.py
  tests/test_r006_contracts.py           # 承接 P1 的测试
  tests/fixtures/knowledge_boundary/
  docs/tasks/M11-knowledge-lane/
  .ai-team/tasks/M11-MVP-01.md
forbidden_paths:
  src/autoresearch/evolution_service.py
  src/autoresearch/profile_service.py
  src/autoresearch/reader_service.py
  src/autoresearch/search_service.py
  .ai-team/TASK.md
  .project-to-act/
```

---

## M11-MVP-02 — 候选召回管线

- **状态**：`planned`
- **对应原文**：M11-05
- **目标**：在现有分区化检索基础上增加向量召回，形成可解释、可过滤的 MVP 检索候选管线。
- **依赖**：M11-MVP-01

### 主要交付

- 词法召回（**升级为 FTS/BM25**，替换现有朴素子串）
- 向量召回
- 同分区图扩展（保留既有语义）
- Evidence 过滤
- **`RecallAuditRecord`（L8 召回审计）** ← 注入自 R-006 C8
- `RetrievalHit` 兼容

### 必须满足

1. **检索候选先经过 `project_id`、`partition` 和可用性边界过滤（L0）。**
2. **词法和向量召回都遵守同一分区边界。**
3. **`require_evidence=True` 时，任何没有 `evidence_ids` 的页面都不得进入结果**（两路都要过滤）。
4. **保留现有同分区图扩展语义。**
5. **每个结果保留 `record_id`、`partition`、`evidence_ids`、`retrieval_level`。**
6. **检索层只负责召回和排序，不判断内容真实性。**
7. **每次 `retrieve` 必须写一条 `RecallAuditRecord`**（可配置关闭，默认开）。
   - 字段：`audit_id`、`project_id`、`query`、`filters`、`candidates`、`deduped`、`reranked`、`final_hits`、`stage_timings_ms`、`created_at`
   - **不变量（可机械校验）**：`final_hits ⊆ reranked ⊆ deduped ⊆ candidates`（集合包含链）
8. **降级路径必须显式记录**：向量能力不可用时回退词法，并在结果中**明确标注降级状态**（`retrieval_level` 反映实际走的路）。

### 禁止

- 改变 `KnowledgeService.retrieve()` 的输入签名；
- 改变 `RetrievalHit` 的对外字段（可新增，不可删除/改名）；
- 跨分区合并无类型结果；
- 在检索层直接生成 `EvidenceItem`、`GateDecision` 或真实性结论；
- **把降级结果伪装成向量检索成功**。

### 验收

| 类型 | 项 |
|---|---|
| 正例 | 固定 fixture 中词法和向量两路均能产生**可追踪排序** |
| 正例 | `RecallAuditRecord` 的**集合包含链**成立（`final ⊆ reranked ⊆ deduped ⊆ candidates`） |
| 负例 | `require_evidence` 过滤**同时作用于两路**结果 |
| 负例 | 跨分区页面不会混入 |
| 负例 | 向量不可用时回退词法，且**结果中降级状态可见** |
| 一致性 | 相同输入和相同索引状态得到一致结果 |

### MVP 边界

只完成候选召回管线。不实现复杂 rerank、ContextPack 和真实领域质量结论。

### 分支与文件边界

```
branch: codex/m11-mvp-02
allowed_paths:
  src/autoresearch/knowledge_retrieval.py      # 新建
  src/autoresearch/recall_audit.py             # 新建
  src/autoresearch/knowledge.py                # 仅 retrieve() 内部
  tests/test_knowledge_retrieval.py            # 新建
  tests/fixtures/knowledge_retrieval/
  docs/tasks/M11-knowledge-lane/
  .ai-team/tasks/M11-MVP-02.md
forbidden_paths:
  src/autoresearch/contracts.py
  src/autoresearch/evidence.py
  src/autoresearch/gates.py
  src/autoresearch/storage.py
  .ai-team/TASK.md
  .project-to-act/
```

---

## M11-MVP-03 — 融合、去重和索引维护

- **状态**：`planned`
- **对应原文**：M11-07
- **目标**：完成多路结果的确定性融合、去重和派生索引维护。
- **依赖**：M11-MVP-02

### 主要交付

- 融合排序（算法**由证据决定**，见验收）
- 镜像去重
- 索引构建、增量同步、索引重建
- 版本追踪和降级路径
- **`RetrievalHit.score_breakdown` / `channel` / `matched_stage`** ← 注入自 R-006 C7

### 必须满足

1. **词法排序和向量排序使用确定性融合规则。**
2. **同一个 WikiPage 不得因多个镜像重复计权。**
3. **融合结果可以区分词法、向量和图扩展来源**（`channel` ∈ `{LEXICAL, VECTOR, GRAPH, FUSED}`）。
4. **`channel=FUSED` 时必须有 `score_breakdown`**（否则无法追溯融合来源）。
5. **向量索引只能由 WikiPage 规范内容派生。**
6. **WikiPage 新增或新 revision 产生后索引可以增量同步。**
7. **索引损坏或版本变化后可以从 WikiPage 重新构建。**
8. **向量能力不可用时回退词法检索，并明确记录降级状态。**

### 禁止

- 把向量索引作为规范数据源；
- 直接修改 WikiPage 的事实内容；
- 通过外部付费或网络服务完成必要检索；
- **让降级结果伪装成向量检索成功**；
- **默认上 RRF 而不给对比证据**（见验收）。

### 验收

| 类型 | 项 |
|---|---|
| 正例 | 相同两路输入得到**稳定一致的融合排序** |
| 正例 | 重复镜像**不会重复增加分数** |
| 正例 | 新增 WikiPage 后可以被检索 |
| 正例 | 从规范 WikiPage 重建索引后结果一致 |
| 正例 | 索引版本变化可以被识别 |
| 正例 | 向量能力不可用时词法回退**可重复验证** |
| **决策证据** | **必须产出「纯词法 vs 混合检索」的对比报告**，并据此决定融合策略 |

> ⚠️ **关于 RRF 的硬要求**：本包的分区（`experiences` / `knowledge` / `profiles`）**属于小语料**（几十~几百条）。
> 调研实证：**小语料两路信号高度相关时，RRF 不增值甚至为负**。
> **因此本包不得默认采用 RRF** —— 必须给出「RRF vs 简单加权融合 vs 字段过滤」的对比证据，由证据决定分层策略。
> （大语料走 RRF、小语料走加权/字段过滤，是**待验证的假设**，不是结论。）

### MVP 边界

不实现生产级 pgvector、复杂 reranker、跨项目质量评测和自动策略变更。

### 分支与文件边界

```
branch: codex/m11-mvp-03
allowed_paths:
  src/autoresearch/knowledge_fusion.py         # 新建
  src/autoresearch/knowledge_index.py          # 新建
  src/autoresearch/knowledge.py                # 仅 retrieve() 内部
  tests/test_knowledge_fusion.py               # 新建
  tests/fixtures/knowledge_fusion/
  scripts/m11_fusion_comparison.py             # 新建（对比报告生成器）
  docs/tasks/M11-knowledge-lane/
  .ai-team/tasks/M11-MVP-03.md
forbidden_paths:
  src/autoresearch/contracts.py
  src/autoresearch/evidence.py
  src/autoresearch/storage.py
  .ai-team/TASK.md
  .project-to-act/
```

---

## M11-MVP-04 — 固定回归与验收证据

- **状态**：`planned`
- **对应原文**：M11-08
- **目标**：建立最小固定语料和回归证据，验证检索变化没有破坏分区、Evidence 和结果追踪语义。
- **依赖**：M11-MVP-03

> **本包为 A7 的独立验收包。** 原拆分写得好，本改进稿**基本保留原样**，只补两处。

### 主要交付

- 固定 fixture 语料
- 固定查询
- 相关页面标注
- 词法与混合检索对比
- 遗漏分类
- 检索审计记录

### 必须满足

1. **每个查询都有固定的预期相关页面。**
2. **测试可以比较纯词法和混合检索结果。**
3. **报告记录命中、漏召回、跨分区污染、Evidence 缺失和重复计权。**
4. **结果保留查询、过滤条件、候选和最终排序。**
5. **相同代码、语料和索引状态可以重复得到相同报告。**

### 禁止

- 用 fixture 结果宣称真实论文领域质量达标；
- 用排序变化直接推断内容真实性；
- 把未测得的真实 Recall、MRR 或 nDCG 写成已达标；
- 跳过失败、遗漏和降级结果；
- **（新增）把 `RecallAuditRecord` 的集合包含链当作召回质量证据** —— 它只证明审计记录自洽，不证明召回正确。

### 验收

| 类型 | 项 |
|---|---|
| 正例 | 固定查询可以重复执行 |
| 正例 | 纯词法与混合检索差异可被记录 |
| 正例 | 索引或模型变化能够触发回归报告 |
| 负例 | 关键负例可以稳定复现 |
| 诚实性 | 报告**明确区分**已验证项、未验证项和后续任务 |

### MVP 边界

只建立最小离线回归证据。真实领域 gold set、人工盲审和生产质量目标延期处理。

### 分支与文件边界

```
branch: codex/m11-mvp-04
allowed_paths:
  tests/test_m11_regression.py                 # 新建
  tests/fixtures/m11_regression/               # 新建
  scripts/m11_regression_report.py             # 新建
  docs/tasks/M11-knowledge-lane/
  .ai-team/tasks/M11-MVP-04.md
forbidden_paths:
  src/autoresearch/                            # 本包只加测试与 fixture，不改实现
  .ai-team/TASK.md
  .project-to-act/
```

---

## 2. 任务关系

```
MVP-01（规范来源与边界）
   ↓
MVP-02（候选召回：词法 + 向量 + 图）
   ↓
MVP-03（融合、去重、索引维护）
   ↓
MVP-04（固定回归与验收证据）← A7 的独立验收包
```

- 所有包均**不改变** Evidence Module、Gate 和 Experience 的职责。
- 每个包的代码、测试、fixture、任务账本、验收证据和 rollback 说明必须在**同一交付快照**中保持一致。
- **MVP-01 是硬前置**（其余三包都依赖它的边界）。

---

## 3. 改动对照（相比成员原稿）

| # | 项 | 原稿 | 改进 | 理由 |
|---|---|---|---|---|
| **1** | revision 不可覆盖的实现 | 只写验收，未说怎么实现 | **补 append-only 写入者 + head 索引 + `get_page`/`list_pages`** | 底层 `ON CONFLICT DO UPDATE` 不换写入者就做不到；**R-006 P1 已实现，直接承接** |
| **2** | 跨分区边 | 一刀切禁止 | **14 类白名单 + 3 类同类边** | 原设计 §12.3 的 16 类边中 ≥11 类必然跨分区；一刀切会让图不成立 |
| **3** | 正向测试 | 只有拒绝侧 | **补「白名单跨分区被允许」+「`get_page` 解析裸 id」** | 收窄语义后必须有正向断言，否则新行为无人校验 |
| **4** | N+1 | 未提及 | **新增硬条款：`list_pages` 必须 O(1) 查询数** | 实测退化：200 页 118ms vs 1.03ms |
| **5** | Evidence 独立存储 | 「独立 RecordStore」 | **改为「独立 `kind`」** | 实测是同一个 `RecordStore`，靠 `kind` 区分 |
| **6** | L8 召回审计 | 只在 MVP-04 提"审计记录" | **提到 MVP-02 作为契约 + 集合包含链不变量** | 可机械校验，且是 MVP-03/04 的输入 |
| **7** | RRF | 默认使用 | **改为「由对比证据决定」** | 小语料上 RRF 不增值甚至为负（有实证） |
| **8** | `score_breakdown` | 未提 | **MVP-03 补 `score_breakdown`/`channel`/`matched_stage`** | 融合来源可追溯；`channel=FUSED` 时必须给 |
| **9** | `Statement` | 未提 | **MVP-01 的 MVP 边界明确「不实现」** | 无消费方，避免过度设计 |
| **10** | 任务包机器可读 | 只有 md | **补 `task-package.json`（`allowed_paths`/`forbidden_paths`）** | 把文件边界从口头约定变成机器可查 |

## 4. 未采纳的建议（留痕，防重复提出）

| 项 | 为什么未采纳 |
|---|---|
| R-006 C2 `Statement` | 无消费方；等 M02-09 失效传播真需要 statement 级绑定再补 |
| R-006 C9 `ExperienceInjection` | 属回流层（M12），不属 M11 |
| R-006 的 7 包切分（P1–P7） | 成员的 4 包更紧凑，且每包带 MVP 边界 |
| R-006 的分层融合作为**结论** | 它只是**假设**（小语料 RRF 不增值有实证，但"该用加权"未被验证）→ 改为**要求对比证据** |
