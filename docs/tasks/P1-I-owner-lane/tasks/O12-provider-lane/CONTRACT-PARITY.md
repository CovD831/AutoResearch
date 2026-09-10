# O12 ↔ B4 契约比对记录（S2.1）

- 日期：2026-09-11
- 依据：B4 `src/autoresearch/reader_writer_ports.py`（main `7b88e30`，O7 accepted）
- O12 产物：`src/autoresearch/lane_llm_adapter.py`（薄缝，74 行）
- 结论：**缝接口与 B4 契约 diff = 0**（无镜像类型、无新增 port 方法、无字段增删）

## 1. 接缝点判定

B4 L3「Known limits」原文：

> The LLM/external adapters wrap supplied payloads; they do not implement live provider, MCP, or recipe wiring. **That integration belongs to O12 ProviderLane** and A4 capability adapters.

故 O12 薄缝的唯一职责 = 把 lane 的真实 completion 归一化成 B4 已定义的 payload，再交给 B4 的 structured port。payload 生产是 B4 显式留给 O12 的缺口，不是 B4 契约的一部分。

## 2. 类型级比对（identity，非等价）

| 项 | B4 定义 | O12 缝引用 | 关系 |
|---|---|---|---|
| 读取 payload | `StructuredReadingPayload` | 直接 import 同名对象 | `is` 恒真 |
| 写作 payload | `StructuredDraftPayload` | 直接 import 同名对象 | `is` 恒真 |
| 读取 port | `StructuredReaderAdapter` | 构造并委托 | `is` 恒真 |
| 写作 port | `StructuredWriterAdapter` | 构造并委托 | `is` 恒真 |
| adapter kind | `AdapterKind.LLM` | 固定传入 `AdapterKind.LLM` | 同一枚举成员 |

断言位置：`tests/test_lane_llm_adapter.py::test_seam_reuses_b4_models_and_ports_verbatim`（用 `is` 而非 `==`，杜绝镜像类型）。

## 3. 字段级比对

### 3.1 `StructuredReadingPayload`（缝消费，逐字段）

`research_question` / `method` / `data_or_setting` / `findings` / `limitations` / `locators` / `confidence` / `source_uri` / `locator` / `independent_source`

→ **无增删改**。缝只做 `model_validate_json(text)`，字段集完全由 B4 决定。

### 3.2 `StructuredDraftPayload`（缝消费，逐字段）

`title` / `body` / `claims` / `claim_evidence_map` / `unresolved_gaps` / `limitations` / `observed_result_summary`

→ **无增删改**。

### 3.3 port 方法签名

| B4 方法 | 签名 | 缝的调用 |
|---|---|---|
| `StructuredReaderAdapter.read` | `(request: ReaderRequest, payload: StructuredReadingPayload) -> ReaderResult` | 原样调用 |
| `StructuredWriterAdapter.write` | `(request: WriterRequest, payload: StructuredDraftPayload) -> WriterResult` | 原样调用 |

→ **无新增 port 方法**；缝不定义 `ReaderPort` / `WriterPort` 的替代或扩展。

## 4. 缝自身新增物（非 B4 契约）

| 新增 | 说明 | 是否触碰 B4 契约 |
|---|---|---|
| `LaneLLMAdapter` 类 | O12 侧适配器，组合（非继承）B4 port | 否 |
| `last_result: LaneResult \| None` | 供 S2.5 计价取 usage/cost | 否（O12 自有属性） |
| `strict="prefer"` 约束调用 | 接 S2.4 降级矩阵，对 B4 不可见 | 否 |

## 5. 行为级验证

`tests/test_lane_llm_adapter.py`（7 用例，全离线）：

1. 类型 identity 全真（diff=0 的机制性证明）；
2. 缝产出的 `ReaderResult` / `WriterResult` 就是 B4 类型，`adapter is AdapterKind.LLM`；
3. 缝调用带 `json_schema` 且 `strict="prefer"`（S2.4 矩阵接入）；
4. 畸形 completion（缺必填字段）在进入 port 前 `ValidationError` fail-closed，不伪造 reading/draft。

## 6. 边界声明

- 缝不改 `reader_writer_ports.py`、`reader_service.py`、`writing_service.py`、共享 `contracts.py`。
- 缝不写证据：candidate 仍由 B4 port 构造，admission 仍归 `EvidenceService.admit_candidate`。
- 提示词（system/user）由调用方给定：recipe wiring 属 B6/A5 消费侧，不在本缝范围（保持 <80 行薄缝）。
