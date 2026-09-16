# R-006 L2 边界契约

**状态**：`accepted`（两关已过，2026-09-15）
**依据**：`00-scope-and-authority.md`（六条决策）+ `02-l1-architecture.md`（五层架构 + 7 条不变量）
**范围**：9 个契约 —— **5 个改造**（C1/C3/C5/C6/C7）+ **4 个新增**（C2/C4/C8/C9）

> **纪律**：每个契约给出**字段级定义**、**不变量**、**可机械校验性**。
> 凡不可机械校验者，**必须显式标注**（教训：本项目的"文档声称 vs 实现"缺陷族）。
>
> **两关记录**：§11.9–§11.12 为两关修正项，§12 为交叉验证汇总。
> 两路独立并行：① 对抗探针（实测破坏面）；② 独立盲审（不知情审查者 + 上游一致性比对）。

---

## 0. 契约总览

| # | 契约 | 类型 | 归属层 | 对应原设计 |
|---|---|---|---|---|
| C1 | `WikiPage` | 改造（加 revision） | L1 地基层 | §12.2 |
| C2 | `Statement` | **新增** | L1 地基层 | §12.2（"知识页可以引用论文页和证据"） |
| C3 | `GraphEdge` | 改造（类型枚举 + 受管桥接） | L1 地基层 | §12.3 |
| C4 | `GraphNodeKind` / `GraphEdgeKind` | **新增**（枚举） | L1 地基层 | §12.3 |
| C5 | `ExperienceRecord` | 改造（成熟度 + 边界 + 时效） | L3 经验层 | §15 |
| C6 | `UserProfileItem` | 改造（三层 + 敏感标记） | L4 画像层 | §14 |
| C7 | `RetrievalHit` | 改造（分数分解 + 通道） | L2 检索层 | §13 L5 |
| C8 | `RecallAuditRecord` | **新增** | L2 检索层 | §13 L8 |
| C9 | `ExperienceInjection` | **新增** | L5 回流层 | §15 消费端 |

（9 项：L1 说的"8 个"把 `GraphNodeKind`/`GraphEdgeKind` 合并计入 `GraphEdge`。）

---

## C1. `WikiPage`（改造：加 revision）

### 既有字段（**保留**）
```
page_id, project_id, partition, title, body, tags,
evidence_ids, level, created_at
```

### 新增字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `revision` | `int` (≥1) | ✅ | 页级版本号，**单调递增** |
| `supersedes` | `str \| None` | — | 被本 revision 取代的 `revision_id` |
| `author` | `str` | ✅ | 写入者标识（服务名或 agent id） |
| `review_status` | `ReviewStatus` | ✅ | `draft` / `published` / `superseded` |
| `effective_at` | `datetime \| None` | — | 生效时间（`published` 时必填） |

### 新增派生标识

| 字段 | 类型 | 说明 |
|---|---|---|
| `revision_id` | `str` | `f"{page_id}:r{revision}"`，**每次写入必须唯一** |

### 不变量（I2）

1. **不可覆盖**：同 `page_id` 的新 revision **必须** `revision = max(既有) + 1`，且旧 revision **永存**。
2. **`supersedes` 链完整**：非首个 revision 必须有 `supersedes` 指向上一 revision。
3. **`published` 必带 `effective_at`**。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| 不可覆盖 | ✅ | 写入者拒绝 `revision ≤ max` |
| supersedes 链完整 | ✅ | 写入时校验 |
| published 带 effective_at | ✅ | pydantic validator |

### ⚠️ 依赖：底层写入语义

**实测**：`storage.py` 的 `put` 是 `ON CONFLICT DO UPDATE`（upsert 就地覆盖）→ **不改写入者则 I2 无法保证**。

→ **本契约要求 P1 提供 append-only 写入路径**（决策 1 的适配器模式：保 `add_page` 签名，内部改走新写入者）。

---

## C2. `Statement`（新增：statement 级证据绑定）

### 为什么需要它

`WikiPage` 是**页级**的，而证据绑定需要**更细粒度**（owner 决策 4 的折中方案 (c)）。

原设计 §12.2：「知识页可以引用论文页和证据」—— 引用发生在**声称**这一级，不是页这一级。

### 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `statement_id` | `str` | ✅ | 默认 `new_id("stmt")` |
| `page_id` | `str` | ✅ | 所属页 |
| `page_revision` | `int` | ✅ | 该 statement 所属的页版本（**内容版本**） |
| `text` | `str` | ✅ | 声称正文 |
| `evidence_ids` | `list[str]` | ✅ | 绑定的证据 |
| `status` | `StatementStatus` | ✅ | `supported` / `contradicted` / `needs_review` |
| `status_changed_at` | `datetime` | ✅ | 状态变更时刻 |

### `StatementStatus` 枚举

| 值 | 含义 |
|---|---|
| `supported` | 有有效证据支撑 |
| `contradicted` | 证据失效或被反驳 |
| `needs_review` | 需重审（证据状态不确定） |

### 不变量（I5 + 决策 4 裁决）

1. **状态变更不产生新页 revision** —— status 是**元数据**，不是内容。
   - 依据：Graphiti/Zep 的 bitemporal 模型（失效置 `invalid_at`）；PROV-O 的 `wasInvalidatedBy`
2. **证据失效 → `status` 降级，** `statement` **不删**。
3. **`page_revision` 必须指向存在的 revision**。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| 状态变更不产生新 revision | ✅ | 写入者：status 更新走独立路径，不触发 revision 递增 |
| 不删除 | ✅ | 无 delete API；状态机只允许 `→ contradicted/needs_review` |
| `page_revision` 存在 | ✅ | 外键式校验 |

---

## C3 + C4. `GraphEdge`（改造）+ 类型枚举（新增）

### 既有字段（**保留**）
```
edge_id, project_id, partition, source_id, relation, target_id, evidence_ids
```

### `relation` 的改造

**现状**：`relation` 是**自由字符串**（实测全仓只建过一种边 `summarized_by`）。

**改造**：`relation: GraphEdgeKind`（枚举），并区分**同类边**与**受管桥接边**。

### `GraphEdgeKind` 枚举（新增）

| 类别 | 取值 | 允许跨分区 |
|---|---|---|
| **同类边** | `SUMMARIZED_BY`, `DUPLICATES`, `SUPERSEDES`（同分区内） | ❌ |
| **受管桥接边** | `CITES`, `DERIVED_FROM`, `SUPPORTS`, `CONTRADICTS`, `APPLIES_TO`, `INVALIDATES` | ✅ **白名单** |

（对齐原 §12.3 的 16 类边；先落这 9 类，其余经**注册表**扩展，不改代码。）

### `GraphNodeKind` 枚举（新增）

核心节点类型（先落，其余走注册表）：
`PAPER`, `CLAIM`, `METHOD`, `DATASET`, `METRIC`, `EXPERIENCE`, `DECISION`, `CONCEPT`, `WIKI_PAGE`

### 不变量（I3）

1. **跨分区边必须使用受管桥接类型**；否则拒收。
2. **桥接边不传递等价性** —— `Experience --APPLIES_TO--> Method` **不意味着**该经验是该方法的事实依据（对齐 I1）。
3. **图端点必须存在且属于同一分区**（既有行为，保留）。

### 语义修正（相对既有实现）

**既有**：一刀切禁止**所有**跨分区边（`knowledge.py:41-42`）。
**原文意图**（`KNOWLEDGE_AND_EVOLUTION.md:15`）：「防止一个经验页**伪装**成论文证据」—— 防的是**伪装**，不是**关联**。

→ **收窄为**：禁无类型跨边，允许受管桥接。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| 跨分区用白名单类型 | ✅ | 写入者查 `relation in BRIDGE_KINDS` |
| 端点存在且同分区 | ✅ | 既有校验保留 |
| 不传递等价性 | ❌ **架构意图** | 需在消费方（L5 回流层）保证：经验通道的产物不得进入论断 |

---

## C5. `ExperienceRecord`（改造）

### 既有字段（**保留**）
```
experience_id, project_id, problem, technique, outcome,
grade, recurrence_count, evidence_ids, tags, promoted
```

### 新增字段

| 字段 | 类型 | 必填 | 说明 | 依据 |
|---|---|---|---|---|
| `stage` | `ExperienceStage` | ✅ | 成熟度阶段（见下） | §15 阶梯 |
| `applicable_when` | `list[str]` | ✅ | **什么时候适用** | **原设计明文要求** |
| `not_applicable_when` | `list[str]` | ✅ | **什么时候不适用** | **原设计明文要求** |
| `counterexample_ids` | `list[str]` | — | 反例（经验不成立的实例） | §15 "跨任务验证+反例" |
| `raw_trace_refs` | `list[str]` | ✅ | 指向原始轨迹的回链 | `arXiv 2605.12978`（抽象会剥离适用条件） |
| `valid_from` | `datetime` | ✅ | 生效起点 | *When Memory Lies*：信过期记忆失败率 74.4% |
| `valid_until` | `datetime \| None` | — | 过期点；`None` = 未设过期 | 同上 |
| `regression_set_id` | `str \| None` | — | 晋级所依据的回归集 | §15 "晋级必须有回归集" |

### `ExperienceStage` 枚举（对齐 §15 阶梯）

| 值 | 对应阶梯位置 | 晋级条件 |
|---|---|---|
| `X0_RAW` | X0 原始候选 | — （A6 的 `experience_sink` 产出到这里） |
| `X1_ATTRIBUTED` | 去敏+归因+**适用边界** | 必填 `applicable_when` + `not_applicable_when` |
| `X2_REPRODUCED` | 沙箱复现与回归 | **沙箱复现通过** + 回归集通过 |
| `X3_CROSS_PROJECT` | 跨任务验证+反例 | 跨项目验证 + 有反例记录 |
| `X4_POLICY` | 正式策略 | 审核 + 人工批准 + 灰度 + 可回滚 |

### 不变量

1. **晋级必须逐级**，不可跳级。
2. **`X1_ATTRIBUTED` 起必须双向边界齐全**（`applicable_when` 与 `not_applicable_when` 都非空）。
3. **`X2` 起必须有 `regression_set_id`**。
4. **既有四门槛保留**（实测已实现于 `evolution_service.promote`）：
   `recurrence_count >= 2 ∧ grade ∈ {E2,E3,H3} ∧ reviewer_approved ∧ human_approved`
   → **本契约不修改它**，只在它**之上**加 stage 门槛。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| 逐级晋级 | ✅ | 状态机 |
| 双向边界齐全（X1+） | ✅ | pydantic validator |
| regression_set_id（X2+） | ✅ | validator |
| **边界内容是否正确** | ❌ **架构意图** | 内容质量靠审核，不可机械判定 |

---

## C6. `UserProfileItem`（改造）

### 既有字段（**保留**）
```
profile_item_id, user_id, key, value, confidence, source,
confirmed_by_user, evidence_ids
```

### 新增字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `tier` | `ProfileTier` | ✅ | 三层 |
| `sensitive` | `bool` | ✅ | 默认 `False`；**为真则禁止进入向量索引** |
| `expires_at` | `datetime \| None` | — | 有效期 |

### `ProfileTier` 枚举（对齐 §14）

| 值 | 含义 | 约束 |
|---|---|---|
| `explicit` | 用户直接给出 | 最高可信 |
| `inferred` | 系统推断 | **confidence ≤ 0.6**（既有行为，保留） |
| `confirmed` | 用户确认 | 可作为人工证据 |

### 不变量

1. **`sensitive=True` 的条目禁止 embedding**（§14 明文）。
2. `tier=inferred` 时 `confidence ≤ 0.6`。
3. `tier=confirmed` 必须 `confirmed_by_user=True`。

### 可机械校验性
三条**全部可校验**（validator）。

---

## C7. `RetrievalHit`（改造）

### 既有字段（**保留**）
```
record_id, partition, title, snippet, score, evidence_ids, retrieval_level
```

### 新增字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `score_breakdown` | `dict[str, float]` | **分数分解**（§13 L5 明文"保留每个候选的分数分解"） |
| `channel` | `RetrievalChannel` | 命中来自哪条通道 |
| `matched_stage` | `str` | 命中在哪一级（`L1`–`L8`） |

### `RetrievalChannel` 枚举

`LEXICAL` / `VECTOR` / `GRAPH` / `FUSED`

### 不变量
1. `channel=FUSED` 时 **必须有 `score_breakdown`**（否则无法追溯融合来源）。

---

## C8. `RecallAuditRecord`（新增：L8 召回审计）

### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `audit_id` | `str` | 默认 `new_id("recall")` |
| `project_id` | `str` | |
| `query` | `str` | 原始查询 |
| `filters` | `dict[str, Any]` | 使用的过滤器 |
| `candidates` | `list[str]` | 各阶段候选 id |
| `deduped` | `list[str]` | 去重后 |
| `reranked` | `list[str]` | 重排后 |
| `final_hits` | `list[str]` | 最终返回 |
| `stage_timings_ms` | `dict[str, float]` | 各级耗时 |
| `created_at` | `datetime` | |

### 不变量
1. **每次 `retrieve` 必须写一条**（可配置关闭，但默认开）。
2. `final_hits` ⊆ `reranked` ⊆ `deduped` ⊆ `candidates`（**集合包含链**）。

### 可机械校验性
不变量 2 **可校验**（集合包含断言）—— 这是 L8 的核心价值。

---

## C9. `ExperienceInjection`（新增：回流层载荷）

### 为什么需要它

L1 §6.1 的**双通道**需要一个**显式载荷类型**来承载"这是经验，不是事实"。

### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `channel` | `InjectionChannel` | **必须为 `EXPERIENTIAL`** |
| `records` | `list[ExperienceInjectionItem]` | 注入的经验 |
| `rendered_guidance` | `str` | 渲染后的 guidance 段文本 |

### `ExperienceInjectionItem`

| 字段 | 类型 | 说明 |
|---|---|---|
| `experience_id` | `str` | |
| `stage` | `ExperienceStage` | 成熟度（决定权重） |
| `tier_weight` | `float` | 见 L1 §6.3 的"乘数+地板" |
| `applicable_when` | `list[str]` | **必须随经验一起展示**（防剥离） |
| `not_applicable_when` | `list[str]` | 同上 |
| `counterexample_ids` | `list[str]` | 反例一并展示 |

### `InjectionChannel` 枚举

| 值 | 含义 |
|---|---|
| `EVIDENCE` | 事实通道（可进论断） |
| `EXPERIENTIAL` | 经验通道（**禁入论断**） |

### 不变量（I1 的落地）

1. **`ExperienceInjection.channel` 恒为 `EXPERIENTIAL`** —— 该类型**不可能**承载事实。
2. **`applicable_when` / `not_applicable_when` 必须随载荷一起渲染** —— 防止抽象剥离（`arXiv 2605.12978`）。
3. **`tier_weight` 满足"乘数 + 地板"**（低成熟度可因高相关浮现，但权重受限）。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| channel 恒为 EXPERIENTIAL | ✅ | 常量字段（Literal） |
| 边界随载荷渲染 | ✅ | 渲染函数断言 |
| tier_weight 在界内 | ✅ | validator |
| **经验是否真被当事实** | ❌ **架构意图** | 双通道是提示结构，无代码级强制（L1 §6.1 已降级声明）；补偿在**输出侧**（论断必须可追溯到 evidence 通道） |

---

## 10. 契约与不变量的对应

| L1 不变量 | 由哪些契约保证 | 可机械校验 |
|---|---|---|
| I1 经验不替代事实 | C9（channel 常量）+ 输出侧追溯 | **部分**（通道可校验；"被当事实"不可） |
| I2 revision 不可覆盖 | C1 | ✅ |
| I3 跨分区边受管 | C3/C4 | ✅（"不传递等价性"为架构意图） |
| I4 向量按库独立 | C7（`partitions` 参数）+ P4 实现 | **`【P4 后生效】`** —— 仓库无向量实现，当前为空约束（§11.8） |
| I5 证据失效降级不删 | C2 | **部分**（"不删"✅；**降级语义依赖 P4 的证据状态机**） |
| I6 抽象保留 raw 回链 | C5（`raw_trace_refs`） | **部分**（字段存在可校验；"回链真实"不可） |
| I7 评估集独立 | C5（`regression_set_id`） | **`【P3 后生效】`**（回归集本身尚不存在） |

---

## 11. 预登记问题的裁决（owner，2026-09-15）

> **纪律**：以下每条**先取既有代码事实**，再裁决。凡与既有行为冲突的，**以既有行为为准并写明**，不得凭设计意图改写既有语义。

### 11.1 `revision` 与 `revision_id` 是否重复？→ **不重复，且 `revision_id` 就是存储主键**

**实测**（`storage.py:94-110`）：
```sql
INSERT INTO records (kind, record_id, ...) VALUES (...)
ON CONFLICT(kind, record_id) DO UPDATE SET payload_json=excluded.payload_json, ...
```

**主键是 `(kind, record_id)`。** 因此：

- 若 revision **复用** `record_id = page_id` → 新 revision **就地覆盖**旧 revision（`DO UPDATE`）→ **I2 直接失效**
- **`revision_id` 必须是 `record_id`**，即写入时用 `store.put("wiki_page", revision_id, ...)`

**裁决**：`revision_id = f"{page_id}:r{revision}"` **作为 `record_id` 使用**。C1 的「append-only」不是新增存储引擎能力，而是**换用带 revision 的 `record_id`**。

**同时**：`page_id → 当前 revision` 需要一条**独立索引记录**（`kind="wiki_page_head"` 或等价物），否则「取当前版本」要全表扫描。→ **列为 P1 的交付项**。

### 11.2 `page_revision` 在 status 变更时是否更新？→ **不更新**

**裁决**：`page_revision` 语义是**「该 statement 内容所属的页版本」**，status 是元数据（I5 / 决策 4）。status 变更**不改 `page_revision`**。

**理由**：若 status 变更要递增 `page_revision`，则「状态是元数据、不产生 revision」这条不变量自相矛盾。

### 11.3 `stage` 与既有 `promoted: bool` 的关系 → **`promoted` 降级为派生视图，不删除**

**实测**：`contracts.py:403` `promoted: bool = False`；`evolution_service.py:59` `model_copy(update={"promoted": True})`。

**裁决**：
- **不删 `promoted`**（删除会破坏既有调用点与已存记录的反序列化）
- **定义 `promoted == (stage == X4_POLICY)`**，写入时由 stage 派生
- **`stage` 是真值来源**，`promoted` 是兼容字段

**反面做法（明确禁止）**：让两者可独立设置 —— 那会造出「`promoted=True` 但 `stage=X0`」的非法状态。

### 11.4 四门槛与 stage 门槛是 AND 还是 OR？→ **AND，且四门槛只在 X3→X4 时校验**

**实测**（`evolution_service.py:52-58`）：四门槛为
`recurrence_count >= 2 ∧ grade ∈ {E2,E3,H3} ∧ reviewer_approved ∧ human_approved`，
在 `promote()` 里**一次性全部校验**，不满足即 `PermissionError`。

**裁决**：
- **AND**。stage 门槛是**新增的必要条件**，不替代四门槛。
- 四门槛**只在 `X3_CROSS_PROJECT → X4_POLICY` 这一跳校验**（因为 `promote()` 的语义就是「成为正式策略」）
- `X0→X1→X2→X3` 各跳只校验**本跳的 stage 门槛**（11.5 的表）
- **既有 `promote()` 的失败语义保留**：不满足即抛 `PermissionError`，**不静默降级**

### 11.5 各跳的 stage 门槛（唯一真值表）

| 跳转 | 校验项 | 可机械校验 |
|---|---|---|
| `X0 → X1` | `applicable_when` 与 `not_applicable_when` **均非空** | ✅ |
| `X1 → X2` | 上项 + `regression_set_id` 非空 + **沙箱复现记录存在且通过** | ✅（复现结果取 P3 的记录） |
| `X2 → X3` | 上项 + **跨项目证据**（≥1 个异 project_id 的复现记录）+ `counterexample_ids` 非空 | ✅ |
| `X3 → X4` | 上项 + **既有四门槛**（AND） | ✅ |
| 任意跳 | 不可跳级；`stage` 只能单调前进 | ✅ |

> **`not_applicable_when` 非空是硬要求** —— 对应 GP-10 的 Experience-Following 发现：无过滤注入会**自降级**。空边界 = 无过滤。

### 11.6 `sensitive` 与 `tier=inferred` 重叠时 → **正交，不重叠**

**实测**（`profile_service.py:14-15`）—— **既有行为与我原先写的不同**：
```python
if not item.confirmed_by_user and item.confidence > 0.6:
    item = item.model_copy(update={"confidence": 0.6})   # ← 静默截断，不是拒绝
```

**裁决**：
- **保留既有截断语义**（`record()` 里 clamp 到 0.6），**不改成 validator** —— 改成 validator 会让既有调用点抛异常，属破坏性变更
- `tier` 由 `confirmed_by_user` **派生**：`confirmed_by_user=True → CONFIRMED`，否则 `INFERRED`。`EXPLICIT` 需**显式指定**（`source` 标记为用户直给）
- `sensitive` **独立于 `tier`**（一条 explicit 的画像项也可能是敏感的，如健康信息）
- **`sensitive=True` 禁止 embedding** → **见 §11.8，当前无法校验**

### 11.7 `tier_weight` 公式 → **L2 只定不变量，公式留 P6**

**裁决**：L2 定**三条不变量**（可机械校验）：
1. `tier_weight ∈ [floor, 1.0]`，`floor > 0`（低成熟度可浮现但受限）
2. `stage` 越高 → 权重上界越高（单调不减）
3. **相关性与 stage 正交**：高相关的 `X0` 不得因相关性压过低相关的 `X3`

**公式**（乘数 + 地板的具体参数）留 P6 —— 它依赖回归集的真实数据，L2 定死会是**无据的数字**。

### 11.8 【新增·关键】不是所有写下来的不变量都能被违反 —— 必须标注「当前不可校验」

**实测**：`grep -rln "embedding\|vector" src/autoresearch/*.py` → **空**（仅 `models_catalog.json` 的模型名与 `experience_injection.py` 的注释 "no vectors"）。

**即：仓库里没有任何 embedding / 向量实现。**

因此以下"不变量"**当前无法被违反，也无从校验**：

| 契约 | 声称的不变量 | 真实状态 | 标注 |
|---|---|---|---|
| C6 | `sensitive=True` 禁止进入向量索引 | **无向量索引存在** → 空约束 | `【P4 后生效】` |
| C7 | `channel=VECTOR` / `score_breakdown` 含向量分 | 同上，枚举值当前不可达 | `【P4 后生效】` |
| C8 | `stage_timings_ms` 含向量级耗时 | 同上 | `【P4 后生效】` |
| **I4** | **向量索引按库（分区）独立** | **同上** —— §10 误标 `✅` | **`【P4 后生效】`** |
| C7 | `channel=FUSED` 必须有 `score_breakdown` | 可校验，但**当前只有 LEXICAL+GRAPH 可融合** | 保留，注明"当前 FUSED 仅 2 通道" |
| **C5** | X1+ 双向边界 / X2+ `regression_set_id` / X2→X3 跨项目+反例 | **依赖 P3 尚未存在的沙箱复现记录** | **`【P3 后生效】`** |

**裁决**：
1. 这些字段与门槛**保留**（它们描述 P3/P4 的目标形态），但**必须逐条标注生效阶段**
2. **禁止**在测试中为它们写「通过」的断言 —— 那会造出**恒真的假绿**（本项目「空/无样本被当作满分」缺陷族）
3. **P3/P4 落地时必须回头补这些条的判别力测试**

> **这条本身是本 L2 最重要的产出**：它把「文档声称 vs 实现」从**事后追查**变成**事前标注**。

**（2026-09-15 两关修正）** 初版只标了 C6/C7/C8，**漏标 I4**（§10 误标 `✅`）与 **C5 的 P3 依赖**（§11.5 门槛表误标 `✅`）。经独立盲审 M3 指出后补齐。

---

## 11.9 【两关修正·高】H1：`revision_id` 作为 `record_id` 与 C3/C7 的裸 id 查询**直接矛盾**

**这是跨契约的内部矛盾，初版未察觉。**

### 矛盾内容

| 契约 | 对存储主键的假设 |
|---|---|
| C1（§11.1） | `record_id = f"{page_id}:r{revision}"` —— **带版本** |
| C3 `add_edge`（`knowledge.py:37-38`） | `get("wiki_page", edge.source_id)` —— **裸 page_id** |
| C7 `retrieve` 图扩展（`knowledge.py:93`） | `get("wiki_page", neighbor_id)` —— **裸 page_id** |

### 实测后果（两路独立复现）

```
store.get('wiki_page', 'p1') -> None      # ← 裸 id 查不到
count: 2  page_ids: ['p1', 'p1']          # ← list 每页返回多版本
```

- `add_edge` → 端点查不到 → 抛 `"graph edge endpoints must exist"`
- `retrieve` 图扩展 → 邻居全跳过 → **图通道静默失效**
- `list("wiki_page")` → 计数类测试（`test_recovery_contract.py:237-238` 的 `wiki_page_count`）由"页数"变"版本数"

**§11.1 只补了"取当前版本"的 head 索引，未覆盖边端点/邻居解析。**

### 裁决：**head 索引必须是"解析裸 page_id"的唯一入口**，且 §11.1 的方案不够

**修订方案**（替代 §11.1 的单条 head 索引）：

| 层 | 落点 | 语义 |
|---|---|---|
| 版本存储 | `kind="wiki_page"`, `record_id=revision_id` | **append-only，每版本一条** |
| 头索引 | `kind="wiki_page_head"`, `record_id=page_id`, payload=`{current_revision_id, revision}` | **裸 page_id → 当前版本** |
| 解析入口 | `KnowledgeService.get_page(page_id) -> WikiPage \| None` | **所有既有 `get("wiki_page", ...)` 改走这里** |
| 列表语义 | `KnowledgeService.list_pages(project, partition)` | **按 page 去重、取 head**；`store.list("wiki_page")` 降级为"列版本"，**仅供审计/迁移用** |

**硬约束**：
1. **`add_edge` / `retrieve` 不得直接调 `store.get("wiki_page", ...)`** —— 必须走 `get_page()`
2. **`list("wiki_page")` 的所有既有调用点必须逐个确认语义**（是要"页"还是"版本"）
3. **P1 的交付项包含**：`get_page` / `list_pages` / `wiki_page_head` 的**写入原子性**（版本写入与 head 更新必须同一事务）

**待 P1 核实的调用点清单**（两关汇总）：
`knowledge.py:21, 37, 38, 78-79, 93, 100`、`test_recovery_contract.py:184, 237, 238`、`test_experience_sink.py:1105, 1157`、`test_adapter_search_service.py:255, 676`、`a2_runtime_fixtures.py:335`

---

## 11.10 【两关修正】新增必填字段的处置 —— 逐字段给默认值，避免破坏 8 处生产构造点

**实测构造点**（`grep -rn "WikiPage(" src/ tests/` 等）：

| 类型 | 生产 | 测试 | 合计 |
|---|---|---|---|
| `WikiPage(` | **5**：`profile_service.py:23`、`evolution_service.py:28`、`search_service.py:142`、`reader_service.py:136,208` | 3：`test_governance_services.py:116,125,134` | 8 |
| `ExperienceRecord(` | **2**：`experience_sink.py:748`、`experience_injection.py:97` | 0（测试经 `synthesize_experiences` 间接触发） | 2 |
| `UserProfileItem(` | 0 | 1：`test_project_and_evolution.py:44` | 1 |

**裁决：全部给默认值，实现"零破坏"**：

| 字段 | 默认 | 理由 |
|---|---|---|
| `WikiPage.revision` | `1` | 首次写入即 r1；append-only 由 `page_id` 派生 |
| `WikiPage.review_status` | `DRAFT` | 新建页天然是草稿 |
| `WikiPage.author` | **无默认，必填** | 5 个生产点**都已知服务名**，应显式传；**禁止默认 `"unknown"`**（会污染审计溯源） |
| `Statement.*` | 全新类型，无兼容问题 | — |
| `ExperienceRecord.stage` | `X0_RAW` | `experience_sink` 产出的天然阶段 |
| `ExperienceRecord.applicable_when` / `not_applicable_when` | `[]` | **X0 允许空边界**；X1+ 才由 validator 强制（与 §11.5 一致） |
| `ExperienceRecord.raw_trace_refs` | `[]` | 同上，X1+ 强制 |
| `ExperienceRecord.valid_from` | `utc_now()` | 无历史时间可推 |
| `UserProfileItem.tier` | `INFERRED` | 由 `confirmed_by_user=False` 派生 |
| `UserProfileItem.sensitive` | `False` | 文档原已写 |

> **关键**：`author` 是**唯一故意保持必填**的字段 —— 因为 5 个生产点都已知自己的身份，**默认值会掩盖"谁写的"这个审计必需信息**。

---

## 11.11 【两关修正·中】X0→X3 的晋级 **API 缺失** —— 门槛真值表无执行者

**实测**：`grep "def " src/autoresearch/evolution_service.py` → 只有 `promote()`（X3→X4 一跳）。**全仓无任何 stage 推进函数**。

**后果**：§11.5 的"逐级晋级、不可跳级"不变量**无落地函数** → 契约不可机械落实。

**裁决：新增两个 API，明确分工**

```python
def advance_stage(
    self,
    experience_id: str,
    *,
    target: ExperienceStage,
    evidence: StageEvidence,      # 沙箱复现记录 / 跨项目证据 / 反例
) -> ExperienceRecord: ...         # X0→X1→X2→X3；只能 +1；不满足本跳门槛抛 PermissionError

def promote(experience_id, *, reviewer_approved, human_approved) -> ExperienceRecord:
    ...                            # 保持既有签名与失败语义：X3→X4，含既有四门槛
```

**硬约束**：
1. **`promote()` 签名与失败语义不变**（`PermissionError`）—— 既有测试 `test_experience_sink.py:334-348` 仍绿
2. **`advance_stage` 只能 `+1`**，`target` 必须等于 `current + 1`，否则 `ValueError`
3. **`promoted` 字段改为从 `stage` 派生**（§11.3）→ **所有直接置 `promoted=True` 的调用点必须改为驱动 stage**：`experience_sink.py:364,392`、`evolution_service.py:59`

**这是 P2 的交付项**（P2 = stage 阶梯）。

---

## 11.12 【两关修正·低】C9 的定性 —— 不是重复造轮子，但必须锁定唯一渲染路径

**实测**：`src/autoresearch/experience_injection.py:324`
```python
GUIDANCE_HEADER = "# Past experience (guidance -- treat as suggestion, not fact):\n"
```

**即：I1 的「经验不是事实」语义已经落地在 prompt 头。**

**裁决（修正初版"重复造"的判断）**：
- C9 **不是**重复机制，而是**既有渲染约定的类型化封装** —— 判定为**虚警**，但**必须锁死约束**：
- **`C9.rendered_guidance` 必须由既有 `_format_guidance()` 产出**，**禁止另写 renderer**（否则两套路径漂移 → 正是本项目「新模块绕过现成原语」缺陷族）
- **`GUIDANCE_HEADER` 是 I1 语义的唯一权威文本**，C9 的 `channel=EXPERIENTIAL` 是它的**类型化表达**

---

## 12. 两关结论汇总（2026-09-15）

### 审查方法

两路**独立并行**：① **对抗探针**（实测破坏面）；② **独立盲审**（不知情审查者，含上游一致性比对）。

### 交叉验证结果

| # | 发现 | 探针 | 盲审 | 裁定 |
|---|---|---|---|---|
| H1 | `revision_id` 与裸 id 查询矛盾 | 高 | **高**（并指出是**跨契约矛盾**） | **真，盲审更准确** → §11.9 |
| M1 | X0→X3 晋级 API 缺失 | 中 | **中** | **真，两关一致** → §11.11 |
| M2 | 必填字段破坏既有构造点 | 高（11 处） | 中（**8+2+1 准确清单**） | **真，位置以盲审为准** → §11.10 |
| M3 | §11.8 标注不全 | — | **中**（漏标 I4 + C5 的 P3 依赖） | **真（盲审独有）** → §11.8 |
| L1 | C9 是否重复造轮子 | 中（判为重复） | **虚警**（是类型化封装） | **以盲审为准** → §11.12 |
| L2 | L2 §10 对 I5 标 `✅`，L1 标"部分" | — | 低 | **真** → §10 已修正 |
| L3 | "保留字段"清单 | — | **已核实完全一致** | **无问题** |
| Q2 | 跨分区边收窄有无回归 | **低（无回归）** | — | 真：`ValidationError ⊂ ValueError`，既有测试仍绿 |
| Q5 | C8 审计写入冲击 | **低（无冲击）** | — | 真：新 kind 不影响既有计数断言 |

### 两关闭环状态

- **高**：H1 → 已给出修订方案（§11.9 四层解析）
- **中**：M1 / M2 / M3 → 全部已裁决（§11.10 / §11.11 / §11.8）
- **低**：→ 已记录
- **虚警**：L1（C9 重复）→ 已定性并留约束注释

### 待 P1/P2/P3/P4 的移交项

| 阶段 | 移交项 |
|---|---|
| **P1** | `wiki_page_head` 索引 + `get_page`/`list_pages` + 写入原子性；穷举 `get("wiki_page")` 调用点 |
| **P2** | `advance_stage()` + `promoted` 派生改造 + 8 处构造点的字段补齐 |
| **P3** | C5 的 X1+/X2+ 门槛解除 `【P3 后生效】` 标注 + 补判别力测试 |
| **P4** | C6/C7/C8/I4 解除 `【P4 后生效】` 标注 + 补判别力测试 |
