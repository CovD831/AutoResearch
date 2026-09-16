# R-007 L2 边界契约（并行模块总纲）

> **状态**：`accepted`（**两关已过**，2026-09-15；K7/K15 已修正，新增 §10.5 跨线硬冲突）
> **依据**：`02-l1-architecture.md`（9 条线的分层 + 9 条硬不变量 + 5 条架构意图）
> **粒度**：字段级定义 + 不变量 + **可机械校验性**（对齐 R-004 L2 的粒度）
>
> **纪律**：凡**不可机械校验**者必须显式标注；凡**当前无法被违反**者必须标注生效阶段。

---

## 0. 契约总览

| # | 契约 | 线 | 类型 | 对应原表 |
|---|---|---|---|---|
| **K1** | `RunManifest` | L-05 | **新增** | M08-02 |
| **K2** | `ExecutionRequest` / `ExecutionResult` | L-05 | **新增** | M08-03 |
| **K3** | `ArtifactLineage` | L-05 | **新增** | M08-04 |
| **K4** | `ResultGrade` | L-05 | **新增（独立枚举）** | M08-06 |
| **K5** | `ContextBudget` / `ContextSlice` | L-01 | **新增** | M01-05 |
| **K6** | `StateMigration` | L-01 | **新增** | M01-02 |
| **K7** | `PrefetchRecord` | L-02 | **新增** | M02-07 |
| **K8** | `InvalidationPropagation` | L-02 | **新增** | M02-09 |
| **K9** | `OutboxEntry` | L-03 | **新增** | M04-05 |
| **K10** | `RetractionStatus` | L-04 | **新增** | M05-06 |
| **K11** | `AccessPolicy` | L-09 | **新增** | M14-03 |
| **K12** | `SensitivityClass` | L-09 | **新增** | M14-04 |
| **K13** | `TelemetryPoint` | L-09 | **新增** | M15-02/04 |
| **K14** | `PanelProjection` | L-08 | **新增** | M13-04 |
| **K15** | `StageEvidence`（**已在 P2 实现**） | **L-07** | **新增** | **M12-05** |
| **K16** | `RegressionSet` | **L-07** | **新增** | **M12-05** |

**共 16 个契约，覆盖全部 9 条线。**

---

## K1. `RunManifest`

### 为什么需要
原表 M08-02：「代码、数据、环境、参数、seed、命令、退出状态和输出 hash 齐全」。
当前仓库**无任何 `RunManifest`**（实测 `\bRunManifest\b` = 0 行）。

### 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `run_id` | `str` | ✅ | 默认 `new_id("run")` |
| `project_id` | `str` | ✅ | |
| `work_package_id` | `str` | ✅ | 所属工作包（→ 既有 `WorkPackage`） |
| `code_revision` | `str` | ✅ | 代码版本（commit sha 或等价物） |
| `data_refs` | `list[str]` | ✅ | 输入数据引用（稳定 ID，非路径） |
| `environment` | `dict[str, str]` | ✅ | 关键环境（python 版本、依赖锁 hash 等） |
| `parameters` | `dict[str, Any]` | ✅ | 运行参数 |
| `seeds` | `list[int]` | ✅ | 随机种子（**禁止空**；无随机性时显式 `[0]`） |
| `command` | `list[str]` | ✅ | 命令 argv（非 shell 字符串） |
| `exit_code` | `int \| None` | — | 未运行时 `None` |
| `output_hashes` | `dict[str, str]` | ✅ | 产物名 → hash（**未产出时 `{}`，不得填假值**） |
| `rerun_of` | `str \| None` | — | 重跑来源 `run_id` |
| `created_at` | `datetime` | ✅ | |

### 不变量

1. **`command` 必须是 argv 列表**，不得是 shell 字符串（防注入 + 可审计）。
2. **`seeds` 不得为空**。无随机性的运行显式写 `[0]`，**不得省略**。
3. **`exit_code is None` ⟺ 未执行**。已执行必须有退出码（含非零）。
4. **`output_hashes` 不得包含未产出的产物名**。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| argv 列表 | ✅ | `isinstance(str)` 拒绝 |
| seeds 非空 | ✅ | validator |
| exit_code 语义 | ✅ | validator |
| hash 真实性 | ❌ **架构意图** | 需比对实际文件；靠执行器产出时写入 |

### ⚠️ 与既有类型的接口
- **`WorkPackage` 已存在**（`contracts.py:277`）→ `RunManifest.work_package_id` 引用它，**不重定义**
- **`ArtifactRef` 已存在**（`:100`）→ 产物引用复用

---

## K2. `ExecutionRequest` / `ExecutionResult`

### 字段

**`ExecutionRequest`**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `request_id` | `str` | ✅ | |
| `manifest` | `RunManifest` | ✅ | 待执行清单 |
| `dry_run` | `bool` | ✅ | 默认 `False` |
| `timeout_seconds` | `int \| None` | — | 超时（`None` = 用默认，**非无限**） |
| `resource_budget` | `dict[str, Any]` | — | CPU/内存/时间上限 |
| `allowlist_group` | `str` | ✅ | 命令白名单组名（**不是命令本身**） |

**`ExecutionResult`**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `result_id` | `str` | ✅ | |
| `manifest_id` | `str` | ✅ | 回链 |
| `status` | `Literal["completed", "failed", "timeout", "cancelled", "rejected"]` | ✅ | |
| `exit_code` | `int \| None` | — | |
| `stdout_ref` / `stderr_ref` | `str \| None` | — | **引用，非内容** |
| `output_hashes` | `dict[str, str]` | ✅ | |
| `diagnostics` | `list[str]` | ✅ | 默认 `[]` |

### 不变量

1. **命令必须在 `allowlist_group` 内**；否则 `status="rejected"`。
2. **`timeout_seconds=None` 不等于无上限** —— 必须落到默认上限。
3. **`dry_run=True` 时不得产生副作用**（不写产物、不改状态）。
4. **`status="failed"` 时 `exit_code` 必须是具体值**，不得为 `None`。

### 可机械校验性
四条**全部可校验**（validator + 执行器前置检查）。

### ⚠️ 风险敞口标注
`allowlist_group` 的白名单内容本身**不在本契约内**（属执行器配置）。
→ **必须在实现里说明"白名单如何被违反"的负例**，否则这是一条空约束。

---

## K3. `ArtifactLineage`

### 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `lineage_id` | `str` | ✅ | |
| `artifact_ref` | `ArtifactRef` | ✅ | 被追踪的产物 |
| `produced_by` | `str` | ✅ | `run_id` |
| `derived_from` | `list[str]` | ✅ | 上游产物 ID |
| `code_revision` | `str` | ✅ | 冗余存储（便于审计不 JOIN） |
| `created_at` | `datetime` | ✅ | |

### 不变量

1. **每条 lineage 必须能追到 `RunManifest`**（`produced_by` 存在且有效）。
2. **`derived_from` 的每一项必须存在于 lineage 图内**（否则断链）。
3. **三跳可达**：`制品 → RunManifest → 输入数据 → 代码版本`（原表 M08-04 的要求）。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| 追到 manifest | ✅ | 外键式校验 |
| `derived_from` 存在 | ✅ | 图遍历 |
| **断链时显式 unknown** | ✅ | 不得"跳过"—— 必须返回 `UNKNOWN` 标记 |

> ⚠️ **关键纪律**：**断链时不得静默跳过，也不得填充**。
> 这是本项目反复出现的缺陷族（"缺失记成正常值"）。**断链必须是可观测的 `UNKNOWN`。**

---

## K4. `ResultGrade`

### 决策：**独立枚举**（**不是**复用 `EvidenceGrade`）

**实测**：`EvidenceGrade`（`contracts.py:77`）只有 `E0/E1/E2/E3/H3` —— **没有 R 系列**。
而原设计 §10.2 明确要求 R0–R4 五级：

| 等级 | 含义 |
|---|---|
| **R0** | **推测、模型模拟或未执行计划，不能作为结果** |
| R1 | 单次可重放运行，环境/参数/输出齐全 |
| R2 | 重复运行或对照/消融完成，结果稳定性可检查 |
| R3 | 独立复核或不同环境复现 |
| R4 | 发布级复现包、数据说明和审计通过 |

**→ R 是独立阶梯，与 E/H 不同维度**（E 是证据可信度，R 是运行成熟度）。

### 字段/枚举

```python
class ResultGrade(StrEnum):
    R0 = "R0"   # 未执行 / 推测 —— 绝不能作为结果
    R1 = "R1"   # 单次可重放
    R2 = "R2"   # 重复或对照/消融
    R3 = "R3"   # 独立复核
    R4 = "R4"   # 发布级
```

### 不变量

1. **默认 `R0`**；**未运行的产出永远 R0**（原表 M08-06 明文）。
2. **`R0` 的产物不得进入结果稿**（M09-03 的前置条件）。
3. **升级必须逐级**（不可 R0 → R3）。
4. **R2 起必须有 `manifest_id`**（复现的基础）。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| 默认 R0 | ✅ | 字段默认值 |
| 逐级升级 | ✅ | 状态机 |
| R2+ 有 manifest | ✅ | validator |
| **"是否真跑了"** | ❌ **架构意图** | 靠执行器产出，不可机械判定 |

### ⚠️ 必须写的负例（防本项目缺陷族）
**必须有一条测试断言：未运行的结果 `grade == R0` 且 `exit_code is None`** ——
而**不是**断言"某个计数字段为 0"（那会造出"缺失记成正常值"的假绿）。

---

## K5. `ContextBudget` / `ContextSlice`

### 为什么需要
原表 M01-05：「只装配当前任务必需上下文；**超限时退回拆分而非堆砌全文**」。
**实测 `ContextAssembler` = 0 行**，全新。

### 字段

**`ContextBudget`**

| 字段 | 类型 | 说明 |
|---|---|---|
| `max_tokens` | `int` | 总预算 |
| `max_items_per_kind` | `dict[str, int]` | 按 kind 的条数上限 |
| `reserved_ratio` | `float` | 预留给输出的比例（默认 0.2） |

**`ContextSlice`**

| 字段 | 类型 | 说明 |
|---|---|---|
| `slice_id` | `str` | |
| `kind` | `str` | `evidence` / `handoff` / `knowledge` / `guidance` |
| `refs` | `list[str]` | **引用 ID，非内容** |
| `rendered` | `str \| None` | 渲染后的文本（**可空**） |
| `truncated` | `bool` | 是否被截断 |
| `dropped_refs` | `list[str]` | **被丢弃的引用（必须记录）** |

### 不变量

1. **超限时退回拆分** —— 不得堆砌全文（原表明文）。
2. **`truncated=True` ⟹ `dropped_refs` 非空或 `rendered` 截断可追**。
3. **`kind="guidance"` 的 slice 不得进入事实论断**（对齐 L1 §4.2 A1）。
4. **`refs` 只存引用 ID**，不存全文（对齐既有 handoff 纪律）。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| 超限退回拆分 | ✅ | 装配器断言 `truncated ⟹ dropped_refs` |
| guidance 不进论断 | ❌ **架构意图** | 靠输出侧追溯 |
| 只存引用 | ✅ | 长度上限 + 类型校验 |

> ⚠️ **M01-05 是 M11-04（ContextPack 分级装配）的前置** → 本契约要**为分级留接口**（`kind` + 预算分层），**不要写死单级**。

---

## K6. `StateMigration`

### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `from_version` / `to_version` | `str` | |
| `field_mapping` | `dict[str, str]` | 旧字段 → 新字段 |
| `unknown_field_policy` | `Literal["reject", "preserve"]` | **必须显式选择** |
| `defaults` | `dict[str, Any]` | 新增字段的默认值 |

### 不变量

1. **未知字段策略必须显式**，不得默认静默丢弃。
2. **迁移必须可回放**（同输入同输出）。
3. **`to_version` 必须严格递增**。

### 可机械校验性
三条**全部可校验**；但**"策略选得对不对"是架构决策**（需 owner 裁决）。

---

## K7. `PrefetchRecord`

### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `prefetch_id` | `str` | |
| `action_level` | `int` | L0–L4（既有风险分级） |
| `query` | `str` | |
| `candidates` | `list[str]` | 候选证据 ID |
| `final_bundle_id` | `str \| None` | 最终 EvidenceBundle |
| `decision` | `Literal["proceed", "blocked"]` | |
| `created_at` | `datetime` | |

### 不变量

1. **L2+ 动作前必须写一条**（原表 M02-07）。
2. **缺证据时 `decision="blocked"`（fail-closed）**。
3. **`final_bundle_id` 必须指向已存在的 bundle**。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| **缺证据时 `decision="blocked"`** | ✅ | validator |
| **`final_bundle_id` 指向已存在 bundle** | ✅ | 外键式校验 |
| **「L2+ 动作前必须写一条」** | ❌ **时序型约束（架构意图）** | validator 只能校验字段内容，**校验不了"某动作发生前已写记录"** |

> ⚠️ **修正（第 1 关 B1）**：初版把本契约标为「三条全部可校验」，**违反了本文档自身的纪律**。
> 第三条是**时序要求**，无法机械校验。
> **补偿手段**：在 L2+ 动作的**统一入口**处强制先写 prefetch（代码结构层面），而非依赖 validator。

### ⚠️ 与 L-06 的接口
本契约的"查询/候选/最终 bundle"与 **R-006 C8 `RecallAuditRecord`** 的字段有重叠。
→ **两者是不同层的审计**：`RecallAuditRecord` 记**检索过程**，`PrefetchRecord` 记**门禁前置动作**。
→ **不得合并**；但 `candidates` 可引用同一来源。

---

## K8. `InvalidationPropagation`

### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `propagation_id` | `str` | |
| `source_evidence_id` | `str` | 失效源 |
| `reason` | `Literal["retracted", "expired", "forged", "paywall_bypass", "unapproved_egress"]` | |
| `affected_claims` | `list[str]` | 受影响 claim |
| `affected_gates` | `list[str]` | 受影响 Gate |
| `action` | `Literal["recompute", "permanent_block"]` | |
| `created_at` | `datetime` | |

### 不变量

1. **永久阻断不可豁免** —— `forged` / `paywall_bypass` / `unapproved_egress` 必须 `permanent_block`。
2. **失效传播到关联 claim 与 Gate**（原表 M02-09）。
3. **`affected_claims` 不得为空**（若为空说明传播断链 → 应报错而非静默通过）。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| 永久阻断不可豁免 | ✅ | 枚举映射表 |
| 传播到位 | ✅ | 图遍历 |
| **`affected_claims` 空则报错** | ✅ | validator |

> ⚠️ **对齐既有**：B5 已实现撤稿判据 `updated-by[]`（PR #17 真实验收）→ **复用，不重写**。

---

## K9. `OutboxEntry`

### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `outbox_id` | `str` | |
| `idempotency_key` | `str` | **幂等键（唯一约束）** |
| `effect_kind` | `str` | `knowledge_write` / `experiment_run` / `notification` / `publish` |
| `payload_ref` | `str` | 引用，非内联 |
| `status` | `Literal["pending", "delivered", "failed"]` | |
| `attempts` | `int` | 默认 0 |
| `created_at` / `delivered_at` | `datetime` | |

### 不变量

1. **`idempotency_key` 唯一** —— 重复投递被拒（原表 M04-05）。
2. **`payload_ref` 是引用**，不内联（对齐 handoff 纪律）。
3. **`attempts` 有上限**；超限转 `failed`（不无限重试）。

### 可机械校验性
三条**全部可校验**（唯一约束 + 类型 + 计数器）。

### ⚠️ 串行约束
**不得改 `storage.py`** —— L-06 正用其 `transaction()`。
`OutboxEntry` 用 `RecordStore.put("outbox", ...)` 即可，幂等靠唯一约束。

---

## K10. `RetractionStatus`

### 字段

```python
class RetractionStatus(StrEnum):
    ACTIVE = "active"           # 未撤稿、未更正
    RETRACTED = "retracted"
    CORRECTED = "corrected"     # 有更正但未撤稿
    UNAVAILABLE = "unavailable" # 无法获取（网络/权限）
```

### 不变量

1. **`UNAVAILABLE` ≠ `ACTIVE`** —— 不可用不得当作"正常"（本项目缺陷族）。
2. **`RETRACTED` 必须触发 K8 传播**。
3. **判据复用 B5 的 `updated-by[]`**。

### 可机械校验性
三条**全部可校验**。

---

## K11. `AccessPolicy`

### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `subject` | `str` | 用户/服务 |
| `resource_kind` | `str` | `project` / `partition` / `artifact` |
| `resource_id` | `str` | |
| `actions` | `list[str]` | `read` / `write` / `export` / `delete` |
| `granted` | `bool` | |

### 不变量

1. **默认拒绝**（无策略 = 不可读）。
2. **越权必须可观测**（不得静默返回空）。
3. **`export` / `delete` 需更高门槛**。

### 可机械校验性
**全部可校验**（判定函数 + 正负例）。

> **实测**：`\bACL\b` = **0 行** → 完全从零建。

---

## K12. `SensitivityClass`

### 字段

```python
class SensitivityClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"   # 禁止进入 embedding / 外部模型
```

### 不变量
1. **`SENSITIVE` 禁止 embedding / 送外部模型**。
2. **导出/删除可追溯**。

### ⚠️ 生效阶段标注（**强制**）

| 不变量 | 当前状态 | 标注 |
|---|---|---|
| `SENSITIVE` 禁 embedding | **空约束** —— 实测仓库**无任何 embedding/向量实现** | **`【向量落地后生效】`** |

**纪律**：**禁止为它写"通过"断言** —— 那会造出恒真假绿（R-006 §11.8 的教训）。

---

## K13. `TelemetryPoint`

### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `metric` | `str` | `blocked` / `denied` / `retry` / `latency_ms` / `cost_usd` |
| `dimensions` | `dict[str, str]` | project / run / node / agent / gate |
| `value` | `float \| None` | **`None` = 未测**（**不得用 0**） |
| `threshold` | `float \| None` | 触发 interrupt 的阈值 |
| `redacted` | `bool` | 是否已脱敏 |

### 不变量

1. **`value=None` 表示未测**，**绝不用 0 代替**（对齐 O12 的计价口径）。
2. **`cost_usd` 未命中价目时为 `None`**（TASK-SPECS:63 明文）。
3. **不得记录 prompt / 全文 / token / secrets**（`redacted=True` 且不含原文）。
4. **超阈值触发 interrupt**。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| None vs 0 | ✅ | 类型 + 断言 |
| 不留敏感内容 | ✅ | 正则扫描 + 字段白名单 |
| 超阈值 interrupt | ✅ | 阈值逻辑 |

### ⚠️ 与 O12 ProviderLane 的对齐
成本指标必须用 **`price_source` + `attempts`** 口径；**未命中价目一律 `None`，绝不用 0**。

---

## K14. `PanelProjection`

### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `panel_id` | `str` | `project` / `evidence` / `files` / `approval` |
| `sections` | `list[PanelSection]` | |
| `verification_state` | `Literal["verified", "unverified", "blocked"]` | **每个 section 必须标** |

**`PanelSection`**：`title` / `refs`（引用 ID）/ `verified`（bool）/ `unknown_reason`（str \| None）

### 不变量

1. **不得展示虚假完成** —— 每个 section 必须带 `verification_state`（原表 M13-04 明文）。
2. **`refs` 是引用**，面板不复制内容。
3. **未验证项必须显式标注**（`unverified` + `unknown_reason`）。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| 每 section 带状态 | ✅ | 类型必填 |
| **"展示是否真实"** | ❌ **架构意图** | 展示层约定（A5） |

---

## K15. `StageEvidence`（**L-07 / M12，已在 P2 实现**）

### 现状（实测）

**这个契约此前从未被任何 L1/L2 覆盖** —— 这正是我们发现的漏洞。它已于 `wt-l2-stage` 实现：

```python
class ReproductionRecord(BaseModel):
    project_id: str
    passed: bool

class StageEvidence(BaseModel):
    reproductions: list[ReproductionRecord] = Field(default_factory=list)
```

配套实现：`_NEXT_STAGE` 阶梯映射、`_sandbox_passed()`、`_cross_project_passed()`、`advance_stage()`。

### 不变量（对齐 R-006 L2 §11.5 的跳转门槛）

| 跳转 | 校验项 | 可机械校验 |
|---|---|---|
| `X0 → X1` | `applicable_when` 与 `not_applicable_when` **均非空** | ✅ |
| `X1 → X2` | 上项 + `regression_set_id` 非空 + **沙箱复现记录存在且通过** | ✅ |
| `X2 → X3` | 上项 + **跨项目证据**（≥1 个异 `project_id`）+ `counterexample_ids` 非空 | ✅ |
| `X3 → X4` | 上项 + **既有四门槛**（`recurrence_count≥2 ∧ grade∈{E2,E3,H3} ∧ reviewer_approved ∧ human_approved`） | ✅ |
| 任意跳 | **不可跳级**；`stage` 只能单调前进 | ✅ |

### 生效阶段标注（**强制**）

| 不变量 | 当前状态 | 标注 |
|---|---|---|
| X1→X2 的"沙箱复现通过" | `ReproductionRecord` 来自 fixture，**真实复现日志尚未产出** | **`【P3 后生效】`** |
| X2→X3 的跨项目证据 | 同上 | **`【P3 后生效】`** |
| X3→X4 的四门槛 | ✅ **`promote()` 在 mainline 已实现**（`evolution_service.py:41`）；`advance_stage`/`StageEvidence` 已提交于 `owner/r006-l2-stage` @ `7318f64`（stacked 于 L-06） | ✅ |

> ⚠️ **修正（第 1 关 C2）**：初版标「既有实现，已生效」，但**实测 mainline 只有 `promote()`**，
> `advance_stage` / `StageEvidence` / `_NEXT_STAGE` **只存在于 `wt-l2-stage` 分支（未提交）**。
> → **mainline 不可核实**。已改为分列表述。

### 与既有实现的接口
`promote()` 的签名与 `PermissionError` 失败语义**保持不变**；`advance_stage()` 是新增的 X0→X3 通道。

---

## K16. `RegressionSet`（**L-07 / M12**）

### 为什么需要
原设计 §15 明文：「每次晋级或降级都必须有**回归集、证据 ID、审核结论、版本和回滚点**」。
**当前不存在** —— `regression_set_id` 字段在 R-006 C5 里定义了，但**回归集本身没有契约**。

### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `regression_set_id` | `str` | |
| `project_ids` | `list[str]` | 覆盖的项目 |
| `cases` | `list[RegressionCase]` | |
| `version` | `str` | **版本化**（回归集本身可演进） |
| `created_at` | `datetime` | |

**`RegressionCase`**：`case_id` / `input_ref` / `expected` / `kind`（`positive` / `negative`）

### 不变量

1. **回归集必须版本化**（`version` 必填）。
2. **每个 case 的 `expected` 必须可机械判定**（不得是"看起来对"）。
3. **晋级必须引用具体版本的回归集**（`regression_set_id` + `version`）。
4. **回归失败必须降级**（不是仅记录）。

### 可机械校验性

| 不变量 | 可校验 | 手段 |
|---|---|---|
| 版本化 | ✅ | 字段必填 |
| expected 可判定 | ✅ | case 类型约束 |
| **"回归集是否覆盖了该经验的适用场景"** | ❌ **架构意图** | 靠人工审核 |

### 生效阶段标注
**`【P3 后生效】`** —— 回归集的真实内容依赖沙箱复现（P3）。

---

## 10. 契约与不变量的对应

| L1 不变量 | 由哪些契约保证 | 可机械校验 |
|---|---|---|
| **I1** revision 不可覆盖 | （R-006 C1，已实现） | ✅ |
| **I2** 跨分区边受管 | （R-006 C3） | ✅（"不传递等价性"为架构意图） |
| **I3** 晋级逐级 | **K15 `StageEvidence`** | ✅ |
| **I4** X1+ 双向边界 | **K15** | ✅ |
| **I5** 未运行永远 R0 | **K4 `ResultGrade`** | ✅ |
| **I6** 产物可追 | **K3 `ArtifactLineage`** | ✅（断链必须显式 UNKNOWN） |
| **I7** resume 不重复副作用 | **K9 `OutboxEntry`** | ✅ |
| **I8** 失效降级不删 | **K8 `InvalidationPropagation`** | ✅ |
| **I9** require_evidence 过滤 | （R-006 C7/K7 的检索层） | ✅ |
| **A1** 经验不替代事实 | **K5 `ContextSlice`**（guidance 通道）+ 输出侧追溯 | **部分** |
| **A2** 桥接边不传递等价性 | **I2 / K8** | **架构意图** |
| **A3** raw 回链 | K3（lineage）+ R-006 C5 | **部分** |
| **A4** 评估集独立 | **K16 `RegressionSet`** | **架构意图** |
| **A5** UI 不展示虚假完成 | **K14 `PanelProjection`** | **部分** |

---

## 10.5 ✅ 跨线硬冲突（**L-06 × L-07**）—— 已修复

> **状态：已修复并验证**（2026-09-15）。
> 修复提交：`owner/r006-l2-stage` @ `7318f64`，**stacked 于 L-06 `owner/r006-l1-writer` @ `9c60043`**。
> 全量 `549 passed / 2 skipped / 0 failed`；ruff clean；`check.mjs --base 9c60043` = valid。
> 从 GitHub 全新克隆该分支实测：**549 passed**（栈序 `788ac26(P1) → 9c60043 → 7318f64`）。
>
> 本节保留完整的**成因与证据链**，因为它是「文件面不相交 ≠ 可并行」的样板案例，
> 也是回归测试的判据来源（两条新测试**必须**在 stacked 分支上跑才有判别力）。

### 冲突内容

| 侧 | 行为 |
|---|---|
| **L-06**（P1） | `add_page` 强制 append-only：同 `page_id` 的第二次写入必须 `revision > max` |
| **L-07**（P2） | `ExperienceService.record()` 构造 `WikiPage(...)` 时**未传 `revision`**（默认 `1`），且 `page_id = experience.experience_id` **固定** |

### 实测复现（修复前）

把 L-07 的 `evolution_service.py` 叠到 L-06 分支上：
```
第 1 次 record OK
第 2 次 record 失败 → ValueError: revision 1 must be > current max 1
                      for page e1 (append-only: revisions are never overwritten)
```

### 为什么是高严重度

| 证据 | 说明 |
|---|---|
| `experience_sink.py:547` | **明确会重复调** `self.experiences.record(record)` |
| `experience_sink.py:755` | `recurrence_count=max(1, recurrence)` —— 同一条经验被再次记录是**核心场景** |
| `experience_sink.py:540-543` | 注释自承「Re-running `record` would append a second audit page」→ 在**绕开**而非修好 |

### 采用的修法

`record()` 从 head **派生** `revision`，并写入 C1 的 `supersedes`：
```python
current = self.knowledge.get_page(experience.experience_id)
next_revision = (current.revision if current is not None else 0) + 1
# ...
WikiPage(..., revision=next_revision,
         supersedes=current.revision_id if current is not None else None, ...)
```

### 同族修复（**不是只修可见的那一处**）

修复过程中另发现两处同族缺陷，一并修掉：

| # | 位置 | 问题 |
|---|---|---|
| 1 | `tests/test_experience_sink.py` | mirror-page 断言用**裸 id** `store.get("wiki_page", id)`（C1 后返回 `None`）→ 改走 `get_page()` |
| 2 | 同上 | 断言 `len(pages) == len(records)` **固化了 upsert 语义**（append-only 后 N 次写入 → N 个 revision、M 个 head）→ 改为**页级（head）计数 + 逐 revision 校验** |

> 第 2 条是「**测试固化了缺陷**」的又一实例：测试名与 docstring 是对的，断言是错的。

### 契约层面的要求（**已落地**）

**K15 不变量**：
> **`ExperienceService.record()` 写入 `WikiPage` 时必须派生 `revision = get_page(page_id).revision + 1`**（首次为 `1`）。
> 禁止传递定值。违反时 `add_page` 会拒绝（fail-closed 方向正确），但会**打断经验沉淀主链路**。

**验收（已实现，2 条）**：
1. `test_record_same_experience_twice_appends_two_revisions`
   —— 同一 `experience_id` 连续 `record()` 两次 → **两次都成功**，`wiki_page` 有 **2 个 revision**、
   `head` 指向 r2、**旧 revision r1 仍可读**、`supersedes == "exp_rr:r1"`
2. `test_record_derives_revision_not_constant`
   —— 连续 4 次写入得到 `[1,2,3,4]`（证明是**派生**而非定值）

**判别力（实测）**：把修复回退后，两条均以**判据型**失败
（`ValueError: revision 1 must be > current max 1`，非 `ImportError`/`AttributeError`）。

> ⚠️ **必须在 stacked（L-06 ← L-07）分支上跑**。单独在 L-07（无 P1）上跑**不构成判别力**——
> 那时 `add_page` 是 upsert，重复写入「成功」是**错误原因造成的假绿**。
> 这是「判别力验证本身要验证环境」的又一实例。

**合并顺序（不可颠倒）**：`owner/r006-l1-writer`（L-06）→ `owner/r006-l2-stage`（L-07）。
L-07 **依赖 L-06 的 `get_page()`**：在无 P1 的分支上单独跑会 `AttributeError`（实测 10 failed）。

---

## 11. 生效阶段汇总（**必须逐条标注**）

| 契约 | 不变量 | 当前状态 | 标注 |
|---|---|---|---|
| **K12** | `SENSITIVE` 禁 embedding | 无向量实现 | `【向量落地后生效】` |
| **K15** | X1→X2 沙箱复现 | 无真实复现日志 | `【P3 后生效】` |
| **K15** | `advance_stage`/`StageEvidence` 本身 | 已提交 `owner/r006-l2-stage` @ `7318f64` | ✅ |
| **K15** | `record()` 的 revision 递增 | **已修复，见 §10.5**（含 2 条判别力实测的回归测试） | ✅ |
| **K15** | X2→X3 跨项目证据 | 同上 | `【P3 后生效】` |
| **K16** | 回归集内容 | 依赖 P3 | `【P3 后生效】` |
| **K1** | `output_hashes` 真实性 | 靠执行器 | 部分 |
| **K2** | 白名单内容 | 需实现时给出负例 | **需补负例** |
| **K3** | 断链检测 | 需实现 | **需补负例** |

**纪律**：**凡标 `【…后生效】` 的，禁止为其写"通过"断言。**

---

## 12. 待办（本 L2 自身）

| # | 项 | 状态 |
|---|---|---|
| 1 | **两关审查**（对抗性独立审查 + 双向钢人论证）—— 未过两关不算定稿 | ✅ 已过 |
| 2 | 协调 `contracts.py` 的改动顺序（L-06 与 L-07 都要动） | ✅ 已协调（L-07 stacked 于 L-06；P2 相对 P1 在 `contracts.py` 只多 11 行 validator） |
| 3 | K2 / K3 的负例清单（防"空约束"） | ⬜ 待办 |
| 4 | **修复 §10.5 的 L-06×L-07 硬冲突**（`record()` 的 revision 递增）+ 补组合分支测试 | ✅ 已修复（`7318f64`，含 2 条判别力实测的回归测试） |
