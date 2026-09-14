# PLAN：能力元数据（①）与注册目录 + 内置多选（②）

- 状态：`approved v0.3 — owner 已裁决（2026-09-11 23:54），实施中`
- 日期：2026-09-11
- 基线：`main@1e7e196`（工作树干净；O12/#15 仍 OPEN，未合入）
- 触发：owner 转来参考实现 `ZRlzy/any-yyds-register`，认可其「目录发现 + 声明式能力」的插拔形态
- **owner 目标（原话）**：「我只是想要一个**足够模块化、足够可插拔**的结果」→ 见 §2.8「可插拔度判据」，该目标已被翻译成可失败的测试断言；**「足够」= 架构上任意槽可插，不等于一次把五个槽都做掉**。
- **v0.2 范围修订（owner 裁决 2026-09-11 23:45）**：
  > 「目前这个阶段，先不做让用户添加任意源或任意 skill。我们原本是打算内置一套实现，相当于每个模块做一个。现在我想的是，我们先把"注册目录"搞好，然后每个模块可以内置几个选项，让用户从中做选择。」
- **v0.3 裁决落定（2026-09-11 23:54，owner：「按照你推荐的来吧」）**：§0.1 的 8 条全部按推荐通过。
- 定性声明：本文件**只借用其注册/发现形态**，不涉及、不参照该仓库的业务域（批量账号注册）。该域不在本项目范围。

## 0.1 裁决落定（8 条，全部按推荐通过）

| # | 裁决 | 落点 |
|---|---|---|
| 1 | **`pdf_parse` 进目录，但 `primary` 强制钉死 `docling`**；`pymupdf4llm` 仅作受限兜底，不得成为可选 primary；目录显示 `license_spdx=AGPL-3.0` + 条款摘要；任何启用路径写事件 + receipt 含原因 | ② D2-7、B9 |
| 2 | **benchmark 强制钉死 ADR-01 选型**（`pinned=True`，`policy_source="adr-01"`） | ② D2-5、B10 |
| 3 | **首批只做 `paper_search` 一个槽**；形态验证完再扩 | ② §2.2、B1 |
| 4 | **用户选择复用 `RecordStore` 事件流持久化**，不新建存储 | ② D2-3 |
| 5 | **① 定性为 owner/O 线变更**，允许回写 L2 §CapabilityManifest | ① §1.5 |
| 6 | **`trust_class`（自述）与 `CapabilityTrustTier`（生效）在 L2 显式区分** | ① D1-1、L2 回写 |
| 7 | **判别力口径固化为全项目要求**：判据型失败计入，符号缺失型失败不计入 | ①-6、②-新 H、账本 Verification |
| 8 | **F10 两套检索实现登记为待裁决重复实现**，本阶段不纳入目录、不归并（归并归属另议） | X5、①§1.3 Non-goals |

## v0.1 → v0.2 变更摘要

| 项 | v0.1 | v0.2 |
|---|---|---|
| ② 的 T1（entry-point 外部源） | 计划内（默认关闭） | **取消** |
| ② 的 T2（MCP） | 排除 | 排除（不变） |
| ② 的重心 | 「可用性开放 + 选型冻结」 | **「统一注册目录 + 内置选项选择」** |
| ②-4 安全红线（域名白名单装饰性） | 必须裁决 | **解除**——不开放外部源即路径不通。理由与残留见 §5.1 |
| ① 的消费点 | 依赖 ② 的外部插件兑现 | **明确**：目录要向用户呈现选项差异，正是 ① 字段的消费点 |
| 新增 | — | §2 模块盘点；②-新 A（AGPL 绕过）、②-新 B（评测可比性）、②-新 D（选项不同质）、②-新 F（两类注册形态） |

---

## 0. 结论先行

1. **我们不是"没有模块化"，是"有实现、没有装配，而且装配点有五个、各做各的"。** 见 §2 盘点：`paper_search` / `pdf_parse` / `reader_port` / `writer_port` / `citation_resolve` 五处都有多个内置实现，**每一处自己发明了一套选择方式**。
2. **① 与 ② 都不是新设计。** 仓库已有：
   - `docs/rearchitecture/CAPABILITY-REGISTRY-TEMPLATE.yaml`（v0.1，2026-09-04）——完整注册模板，含 `selection:` 块（`enabled_by_default` / `priority` / `supports_offline` / `selection_tags` / `replaces`）与 `execution.implicit_fallback: false`；
   - `docs/rearchitecture/CAPABILITY-CANDIDATES.md`§注册模板审查结论——明说模板「**不能视为已实现的 runtime contract**」，并给出三层字段划分。
   **① = 把模板升格为运行时契约；② = 实现它的 `selection:` 块 + 把五处装配点收拢成一个目录。**
3. **顺序：① 必须先于 ②。** 让用户「从内置选项里挑」的前提是选项之间**可比**——接受什么输入、产出什么、要不要网络、能不能离线、什么许可、什么凭据。这些字段全属 ①。② 先行则用户面对的是一列无法比较的名字。
4. **「目录」的准确定义**（本文件的 ② 就指这个）：**一个声明式清单，列出每个能力槽有哪些内置实现、每个实现的契约与代价，以及「用户从里面选」的持久化与可观测入口。** 不含外部加载。
5. **两条独立红线**：
   - ① 若作为成员任务包下发 = 越权重写冻结 L2 合同，必须定性为 owner/O 线变更；
   - **② 新红线 A**：`pdf_parse` 的选项里含 **AGPL 后端**。让用户自由勾选会**绕过 ADR-01 签字块 2 的许可条款**——目录必须区分「可选」与「受条款约束的兜底」。

---

## 1. 权威依据与现状事实

### 1.1 权威依据（authority map）

| 事项 | 权威文件 | 现状 |
|---|---|---|
| `CapabilityManifest` 字段 | `docs/rearchitecture/R004-trust-program/04-l2-contracts.md` §CapabilityManifest | 冻结。必备 10 字段；**「签名、来源许可、依赖锁定 open（plugin lifecycle 增量）」** ← ① 的落位槽 |
| 注册模板全量字段 | `docs/rearchitecture/CAPABILITY-REGISTRY-TEMPLATE.yaml` | **v0.1 草案，未成为运行时契约** |
| 模板三层划分 | `docs/rearchitecture/CAPABILITY-CANDIDATES.md`§注册模板审查结论 | 已裁决，未实现 |
| 外部模块选型（检索源） | `docs/coord/adr-01-external-integrations.md` | Accepted。slot 2 = S2 主选 + arXiv 补充，OpenAlex 可选；**生效规则：成员任务包内不得私改选型** |
| PDF 解析许可条款 | ADR-01§6 签字块 2 | **pymupdf4llm（AGPL）仅限「docling 权重不可用」的离线兜底；一旦启用须在 receipt/PROGRESS 记录启用原因** |
| 检索选型计入评测 | ADR-01 slot 11 + `docs/BENCHMARK.md` | gold set 指标口径依赖固定选型 |
| 注册表实现 | `src/autoresearch/capability_registry.py` | 已实现 |
| 门禁 | `scripts/check_pr_contract.py`、`.ai-team/check.mjs` | 产品改动必须自带 `.ai-team/tasks/*.md` 账本；禁 `var/` 改动 |

### 1.2 已验证的现状事实

**F1–F8（v0.1 原文，2026-09-11 复核；全部来自 `Grep` 工具全仓扫描——注意本环境 `grep` 的 BRE `\|` 交替会静默返回空，必须用 `Grep` 工具或 `grep -E`）**：

| # | 事实 |
|---|---|
| F1 | `CapabilityManifest` 的 `inputs` / `outputs` / `permissions` / `entrypoint` / `allowed_network_domains` **零消费者**；仅 `name`/`version`/`kind`/`network_required` 被 `register()` 读；`evidence_mode` 仅测试断言 |
| F2 | `allowed_network_domains` 只被存储与回显，**无任何强制点**；唯一网络闸是 `capability_registry.py:388` 的布尔 |
| F3 | A4 L3 已将该限制登记为**已知限制**（非缺陷） |
| F4 | **`CapabilityRegistry` 未接主线**：`register_search_adapters` 唯一生产调用点 = `scripts/benchmark_trust.py:157` |
| F5 | `build_search_adapters()` 的硬编码 dict 只服务该脚本与测试 |
| F6 | `register()` 被重复传 `kind`/`network_required`，与 manifest 自述重复 → 双真值源 |
| F7 | 注册表与幂等记录为进程内、不持久化（A4 已登记 deferral） |
| F8 | `docs/CONTRACTS.md` / `docs/ARCHITECTURE.md` **零提及** capability/registry/manifest → 架构文档已漂移 |

**F9–F12（v0.2 新增）**：

| # | 事实 | 证据 |
|---|---|---|
| **F9** | `reader_writer_ports.py` 的 `NativeReaderAdapter` / `StructuredReaderAdapter` / `NativeWriterAdapter` / `StructuredWriterAdapter` **只在 `tests/` 里被构造，`src/` 内零装配点** | 全仓 Grep：`src/` 命中仅类定义行 |
| **F10** | `search_service.py` 另有一族连接器（`OpenAlexConnector` / `CrossrefConnector` / `SemanticScholarConnector`，均实现 `ScholarlyConnector` Protocol）——**与 `search_adapters.py` 的 3 个 adapter 是同一概念的两套并行实现** | `search_service.py:28,34,71,103` |
| **F11** | `PdfParser` **已实现 ADR-01 要求的显式 fallback 记录**：`ParseResult.parser="docling"\|"pymupdf4llm"\|"unavailable"` + 记录为何启用 AGPL 兜底 | `external_sources.py:437-468` |
| **F12** | 与之对照，**paper_search 侧的选择完全无痕**：`benchmark_trust.py` 用 CLI `--source` 决定用谁，该选择不进 receipt（`build_search_adapters` docstring 自称「the primary slot is never silently rewritten」，但**无任何代码实现**） | F4/F5 + `search_adapters.py:729-735` |

**F11 与 F12 合起来是本计划最重要的立论点：两个模块各做对了一半，而且是相反的一半。** `PdfParser` 有可观测性、无注册与选择入口；`CapabilityRegistry` 有注册边界、无选择落痕。**目录要做的是把这两半合成一个。**

---

## 2. 模块盘点（v0.2 新增）

「每个模块内置几个选项」——先确认**哪些模块真的有多个内置选项**（`main@1e7e196` 实测）：

| 能力槽 | 内置选项 | 装配点现状 | 选择可观测 | 选择入口 |
|---|---|---|---|---|
| **paper_search** | 3：`semantic_scholar` / `arxiv` / `openalex` | `register_search_adapters`（**仅 `benchmark_trust.py` 调用**） | **✗ 无痕迹**（F12） | CLI `--source`（脚本私有） |
| **pdf_parse** | 2：`docling`（默认）/ `pymupdf4llm`（AGPL 兜底） | `PdfParser` 硬编码优先级，**无注册** | **✓ 有痕迹**（F11） | **无**（用户不可选） |
| **paper_read（port）** | 2：`NativeReaderAdapter` / `StructuredReaderAdapter` | **仅测试**（F9） | — | 无 |
| **section_write（port）** | 2：`NativeWriterAdapter` / `StructuredWriterAdapter` | **仅测试**（F9） | — | 无 |
| **citation_resolve** | 2+：`SnapshotResolverAdapter` / `CrossrefAdapter` | 硬编码 | 部分（`ResolverSnapshot` 版本） | 无 |
| **paper_search（legacy A1）** | 3：`OpenAlex` / `Crossref` / `SemanticScholar` Connector | `PaperSearchCapabilityAdapter` + `UnknownProviderError` | — | 函数参数 |
| **benchmark materials** | 2：`FixtureMaterialsProvider` / `RegistryMaterialsProvider` | 显式传参 | — | 参数 |

**读法**：三个站点（`paper_search` / `reader_port` / `writer_port`）是**同一病症**——**实现齐全，装配缺席**。目录的边际价值在这三处最高；`pdf_parse` 已做对可观测性，只缺"被目录认领"；legacy A1 连接器族与 `search_adapters` 重复（F10），**不应进目录，应登记为待裁决的重复实现**。

**建议首批纳入目录的槽**（按价值排序）：
1. `paper_search` —— 已有 registry、缺落痕与入口，改动最小、收益最直接
2. `pdf_parse` —— 已有可观测性、缺目录身份；**但受 AGPL 条款约束，见 §5.2**
3. `section_write` / `paper_read` —— 已有双实现、零装配，目录化即可让用户选

---

# PLAN ①：能力元数据升格为驱动性契约

## 1.1 Goal

把 `CapabilityManifest` 从**描述性**（字段存在但无人读）升格为**驱动性**（字段驱动校验与选择），实现 `CAPABILITY-REGISTRY-TEMPLATE.yaml` 的 identity/contract 层与 policy/profile 层，**使目录能够向用户呈现选项之间的差异**（接受什么 / 产出什么 / 是否需网络 / 可否离线 / 什么许可 / 什么凭据）。不实现 operational 层（timeout / retry / concurrency / resources）——归 Runtime 执行面，与 O12 重叠。

## 1.2 依据与推导

- 权威：`CAPABILITY-REGISTRY-TEMPLATE.yaml` 已定义 `input.schema` / `output.schema` / `trust.tier` / `security.allowed_network_domains` / `compatibility.contract_version` / `health.conformance_tests` / `lifecycle.status`；`CAPABILITY-CANDIDATES.md` 规定三层划分且明说「不能视为已实现的 runtime contract」。
- L2 状态注记：「签名、**来源许可**、依赖锁定 **open**（plugin lifecycle 增量）」——**"来源许可"正是本计划要补的槽**。
- **与参考实现的差异（必须写清）**：它用 `param_schema` + `ui_hints`，因为其 capability 直接渲染成前端按钮。**我们没有 capability UI**（消费者是 CLI / benchmark / 未来 MCP）。因此采用 `input_schema_ref` / `output_schema_ref`（指向 typed contract 的**引用**），与模板 `input.schema: PaperReadRequest` 一致。**任何 `ui_*` 前缀字段一律判定为抄错。**

## 1.3 Non-goals（显式排除）

| 排除项 | 理由 |
|---|---|
| 不实施 `permissions` 授权执行 | A4 已登记 **D-6**，归 S4/O12 |
| 不裁决双 receipt 形状 | A4 已登记 **D-4**，归 S3 promotion 窗口 |
| 不把 adapter 输入从 opaque `Any` 收紧为 typed request | A4 已登记 **D-2**，归 I 线；`input_schema_ref` 仅作**预留接线点** |
| 不做 operational 层 | 与 O12 执行面重叠，避免双实现 |
| 不动 `application.py`、共享 `contracts.py`、Evidence/Writing 路径 | 沿用 S3-A Invariants |
| **不把 legacy A1 连接器族（F10）纳入目录** | 重复实现，应先裁决归并 |
| 不引入任何新依赖 | manifest 已是 pydantic，`model_json_schema()` 白送 |

## 1.4 设计

### D1-1｜manifest 字段扩展（全部可选默认，向后兼容）

- `manifest_id: str` —— 稳定身份，不随 version 变
- `contract_version: str = "l2"` —— 对齐模板 `compatibility.contract_version`
- `input_schema_ref: str | None` / `output_schema_ref: str | None` —— typed contract 名（如 `SearchAdapterRequest` / `RetrievedPaper`）
- `trust_class: str = "local"` —— 对齐模板 `trust.tier`（`local` / `reviewed_external` / `unreviewed_external`）。**与 operator 指派的 `CapabilityTrustTier` 是不同维度**：前者是能力自述的来源类别，后者是生效策略；二者不可互相提升（沿用 S3-A 不变式）
- `license_spdx: str | None` —— **新增，补 L2 的「来源许可」open 槽**。用途见 §5.2
- `requires_credentials: tuple[str, ...] = ()` —— 如 `("semantic_scholar_api_key",)`。目录靠它告诉用户「选这个得先配 key」
- `supports_offline: bool = False` —— 对齐模板 `selection.supports_offline`
- `selection_tags: tuple[str, ...] = ()` —— 对齐模板 `selection.selection_tags`
- `conformance_fixture: str | None` —— 对齐模板 `health.conformance_tests`
- `lifecycle_status: str = "active"` —— `draft|active|deprecated|retired`

**纪律**：每个字段必须有一个**消费点**，否则不引入。消费点见 D1-2 / D1-3 / PLAN ② 的目录渲染。

### D1-2｜`validate_manifest()` —— 唯一校验入口

```
validate_manifest(manifest) -> list[str]   # 违规清单，空 = 通过
```

1. identity 非空：`name` / `version` / `manifest_id` / `contract_version`
2. `input_schema_ref` / `output_schema_ref` 必须可解析（在已知 contract 名字表内）
3. **`network_required=True` 时 `allowed_network_domains` 必须非空** —— 关闭 F2 的静默洞
4. `trust_class` / `lifecycle_status` ∈ 已知集合；`retired` 拒绝注册，`deprecated` 允许但记 diagnostic
5. **`license_spdx` 为 AGPL/SSPL 类时，必须同时声明 `selection_restricted_reason`（见 §5.2）**
6. `conformance_fixture` 指向的文件存在（收集期校验）

### D1-3｜注册期 fail-closed 接线

- `register()` 在**重复检查之前**调用 `validate_manifest()`；违规抛 `CapabilityManifestInvalidError(CapabilityRegistrationError)`，**adapter 零调用**。
- `register()` **默认从 manifest 推导** `kind` / `network_required` / `allowed_network_domains`（关闭 F6）。显式传参允许，但与 manifest 不一致时**记 diagnostic 并标注 override 来源**，不得静默覆盖。
- `CapabilityRegistrationView` 与 `CapabilityInvocationReceipt` 增 `manifest_id` / `contract_version` / `input_schema_ref` / `output_schema_ref`，使 manifest 变更在下游可观测。
- **`registry.list()` 成为目录的数据源。**

### D1-4｜符合性 fixture

`tests/fixtures/capabilities/<manifest_id>@<version>.json`，由 `test_capability_manifest_contract.py` 逐条校验。对齐模板 `health.conformance_tests`。

## 1.5 变更面

| 文件 | 动作 | 归属 |
|---|---|---|
| `src/autoresearch/invocation_contracts.py` | 扩展 `CapabilityManifest` | **owner（冻结 L2 面）** |
| `src/autoresearch/capability_registry.py` | `validate_manifest` + fail-closed + 推导 + 新错误 + view/receipt 字段 | owner |
| `src/autoresearch/search_adapters.py` | 三个 adapter 的 `manifest()` 补齐新字段 | owner |
| `tests/test_capability_manifest_contract.py` | 新增 | owner |
| `tests/fixtures/capabilities/*.json` | 新增 | owner |
| `tests/test_capability_registry.py` / `test_search_adapters.py` | 扩充 | owner |
| `docs/rearchitecture/R004-trust-program/04-l2-contracts.md` | ★ 回写（并入模板字段，关闭 open 项） | owner |
| `docs/CONTRACTS.md` | 补 capability/manifest 章节（修 F8） | owner |
| `.ai-team/tasks/O13-CAPABILITY-MANIFEST.md` | 新建账本（9 章） | owner |
| `docs/rearchitecture/TASK-PACKAGE-REGISTRY.md` | 登记 O13 | owner |

## 1.6 验收（含判别力）

| ID | 场景 | 判别力 |
|---|---|---|
| A1 | manifest 缺 `input_schema_ref` → 注册抛 `CapabilityManifestInvalidError`，adapter 零调用 | **符号型 → 不计入判别力** |
| A2 | `network_required=True` + `allowed_network_domains=()` → 注册被拒 | **判据型**：旧代码下该 manifest 注册**成功**（可复现） |
| A3 | **穷举**：全仓现存全部 manifest 构造点（3 个内置 adapter + `tests/` + `scripts/benchmark_trust.py`）通过新校验；`registry.list()` 输出与改动前**逐字段相等** | 向后兼容证明 |
| A4 | 不传 `kind=` / `network_required=` 时从 manifest 推导，`registry.list()` 与显式传参版相等 | 关闭 F6 |
| A5 | `manifest_id` / `contract_version` / `input_schema_ref` 出现在 view 与 receipt | **符号型 → 不计入** |
| A6 | `retired` 拒绝注册；`deprecated` 注册成功且 diagnostics 非空 | **判据型** |
| A7 | 每个内置 adapter 的 conformance fixture 存在且被测试读取 | **判据型** |
| A8 | **AGPL 纪律**：manifest 声明 `license_spdx="AGPL-3.0"` 而无 `selection_restricted_reason` → 注册被拒 | **判据型（新）** |
| A9 | 全量 `pytest -o addopts="" -q` 不低于基线（**275 passed / 0 skipped**，2026-09-11 实测）+ 新增 | 回归 |

**判别力纪律（吸取 O12 轮教训）**：A1/A5 依赖新符号，旧代码上以 `ImportError`/`AttributeError` 失败——那是**符号缺失型失败**，不计入证据。只有 A2 / A6 / A7 / A8 计入。账本 `Verification` 必须把两类分开写。

## 1.7 门禁与流程

- 产品改动 → 必须自带 `.ai-team/tasks/O13-CAPABILITY-MANIFEST.md`（9 章齐全，≥1 acceptance checkbox）
- `node .ai-team/check.mjs --task .ai-team/tasks/O13-CAPABILITY-MANIFEST.md --base main`
- `python scripts/check_pr_contract.py --base <base>`（禁 `var/`）
- `ruff check src tests` + `compileall -q src` + `pytest -W error -q`
- `- Status:` 必须为纯状态 token（注解写 `- Status note:`）
- 不得：`application.py` / `contracts.py` / `.ai-team/TASK.md` / `.project-to-act/`

## 1.8 验证

```
python -m ruff check src tests
python -m compileall -q src
python -m pytest -o addopts="" -q          # 计数用 -o addopts=""，勿点阵计数
node .ai-team/check.mjs --task .ai-team/tasks/O13-CAPABILITY-MANIFEST.md --base main
python scripts/check_pr_contract.py --base main
```

## 1.9 风险与回滚

- 全部新字段可选默认 → `git revert` 即恢复。
- **最大风险 = 校验误伤在飞注册**（①-5）。缓解：A3 穷举先跑通再合。
- 语义风险：`trust_class`（自述）vs `CapabilityTrustTier`（生效）易混 → L2 回写用★标注，view 里分开列。

---

# 对抗审查 ①

### ①-1｜收益可能被高估（首击）
F1 已证 manifest 的多个字段**零消费者**。给 manifest 加字段**不会自动改善任何行为**。若只加字段不接校验，「更丰富的 manifest」就是形式主义——正落进我们批评参考实现的坑（它 22 个字段里被消费的也只有几个）。
**反制**：A2 / A3 / A6 / A7 / A8 五条**判据型**验收为不可裁剪最小集；无消费点、无判据的字段从范围里删。**评分标准 = 有几个字段产生了可失败的测试。**

### ①-2｜`ui_hints` 是范畴错误（红线）
参考实现的 `param_schema` 嵌了 `type: select, options: [...]`——那是**渲染指令**。注入 core 契约与「契约是数据、单一真值源」的立场直接冲突。
**反制**：用 `input_schema_ref`/`output_schema_ref`（引用），并在 L2 回写里记一句「capability 元数据不含呈现层字段」。出现任何 `ui_*` 字段即判失败。

### ①-3｜越权风险
A4 Invariants 明令「不单方面改写共享合同」。① 改的正是 `04-l2-contracts.md` §CapabilityManifest。
**反制**：定性为 **owner/O 线变更**，与 L2 回写同窗口完成；不得以成员任务包下发。

### ①-4｜手搭在 D-2 的接线柱上
引入 `input_schema_ref` 后，顺手把 opaque `Any` 收紧成 typed request 是极自然的下一步——但那会替 I 线做决定，并可能与 A1 `PaperSearchRequest` 撞车（D-4 同型）。
**反制**：写入 Non-goals 与账本 Invariants；L3 登记「`input_schema_ref` 是 D-2 的预留接线点」。

### ①-5｜校验可能误伤在飞的其它 lane（最可能造成实际损失）
`register()` 改 fail-closed 后，任何 manifest 形状的注册都会被拦。O12 `ProviderLane` 自带 provider 目录与预算推导；形状不同则会在 ① 合入后突然被拦——而 O12 是 P0 关键路径。
**反制**：A3 必须**穷举**；合入前先审 O12 分支上的 manifest 形状，若 #15 引入 manifest 必须纳入枚举清单。

### ①-6｜判别力容易被伪证
A1/A5 依赖新符号，旧代码上以 `ImportError` 失败。那是**符号缺失**，不是判据生效（O12 轮必须写 `/tmp` shim 注入符号才拿到逐条结论）。
**反制**：账本 `Verification` 分开写「判据型失败（计入）」与「符号型失败（不计入）」。

### ①-7｜文档漂移未覆盖
F8：`docs/CONTRACTS.md` 与 `ARCHITECTURE.md` 对 capability/registry/manifest **零提及**。只回写 L2 不够。
**反制**：补 `docs/CONTRACTS.md` 章节（已列入 §1.5）。

### ①-8｜`selection_tags` / `supports_offline` 的服务对象在 ②
这两个字段对 ① 的消费者（CLI/benchmark）无用，只为 ② 服务。放进 ① 会让 ① 依赖 ② 的需求。
**反制**：字段定义放 ①（类型归位，避免 ② 再改一次契约），**消费点与验收全放 ②**；① 账本写明「本包定义但不消费，消费方为 O14」。

### ①-9（v0.2 新增）｜`license_spdx` 可能被当成"加个字段就合规了"
A8 只校验「声明了 AGPL 就必须给受限原因」，**它不阻止任何人勾选 AGPL 后端**。
**反制**：① 只负责**把许可事实变成机器可读**；**真正拦人的是 ② 的选择层**（§5.2）。若 ② 不做，A8 就是一块安慰牌——这点必须说清，不许含糊。

---

# PLAN ②（v0.2）：统一注册目录 + 内置多选

## 2.1 Goal

建立**一个**声明式注册目录，把 §2 盘点的各槽内置实现收拢成可枚举、可比较、可选择、可观测的一组选项；用户从内置选项里选，**不引入任何外部代码加载**。实现 `CAPABILITY-REGISTRY-TEMPLATE.yaml` 的 `selection:` 块与 `execution.implicit_fallback: false`。

## 2.2 范围（v0.2 收敛）

| 做 | 不做 |
|---|---|
| 统一目录：所有能力槽的选项集中声明 | **不做** entry-point / 目录扫描 / 第三方包加载 |
| 目录数据源 = `registry.list()` + catalog 声明 | **不做** MCP（ADR-01 slot 14，另立任务） |
| 用户选择：持久化 + 可观测 + 进 receipt | **不做** legacy A1 连接器族（F10，先裁决归并） |
| 选择入口：CLI（`list` / `show` / `select` / `reset`） | **不做** Web UI |
| 默认值锚定 ADR-01，且**可测** | **不做**「用户选择成为新默认」——默认改动仍须走 ADR/ruling |

## 2.3 设计

### D2-1｜两类注册形态（**v0.2 关键判断**）

盘点（§2）显示五个站点**形态不同**：`CapabilityRegistry` 侧有完整 invocation 契约（幂等 / receipt / 边界），而 `PdfParser` 是同步方法、无 invocation 契约。**强行把后者塞进 registry 需要包一层 adapter，会引入不必要的间接。**

| 形态 | 适用 | 需要 invocation 契约 |
|---|---|---|
| **registry-backed** | `paper_search` 的 3 个 adapter | 是（幂等 / receipt / trust tier） |
| **catalog-only** | `pdf_parse` 的 2 个 parser、`reader_port` / `writer_port` 的双实现 | 否——只声明身份、契约、代价，选择在本地装配点生效 |

**诚实说明**：catalog-only 不提供 registry 的治理保证，**不得被用来注册任何会产生候选或需要网络的能力**。写进目录校验：catalog-only 条目若声明 `network_required=True` 或 `emits_candidates=True` → 拒绝登记，必须走 registry-backed。

### D2-2｜目录结构

新增 `src/autoresearch/capability_catalog/`（**包，不是单文件**，见 ②-新 C）：

```python
CAPABILITY_SLOTS: dict[str, SlotDeclaration]     # 槽 → 内置选项
describe_slots() -> list[SlotView]               # 供 CLI / 用户看，不含 adapter 句柄
resolve_selection(policy) -> dict[str, str]      # 槽 → 选中的 name@version
```

- 只用**显式表**。不用 `pkgutil`、不用目录扫描（本仓门禁的评审面就是 git diff；扫目录 = 「多放一个文件就多一个能力」，绕过 review 面）。
- 槽声明**按槽分文件**（`capability_catalog/paper_search.py` …），`__init__.py` 只做聚合与解析。**目录是索引，不是实现。**
- `describe_slots()` 的每个选项必须带齐 ① 的字段：`license_spdx` / `requires_credentials` / `supports_offline` / `trust_class` / `input_schema_ref`。**这是 ① 的第一个真实消费点。**
- 目录**必须能回答「为什么选它」**：每个选项一条 `selection_tags` + 一句 `selection_note`（如「S2：有 citation context，需免费 key」「arXiv：免 key，仅预印本」「OpenAlex：2026-02 起计费」）。

### D2-3｜选择策略与持久化

`selection_contracts.py`：

```
SelectionPolicy:
  slot: str
  primary: str                    # "<name>@<version>"
  supplements: list[str] = []
  allow_fallback: bool = False    # 默认 False，对齐模板 implicit_fallback: false
  policy_source: "adr-01" | "owner_ruling" | "user"
  pinned: bool = False

SlotDeclaration:
  slot: str
  selection_semantics: "exclusive" | "supplementary"
  options: list[OptionDeclaration]
```

- **落盘**：`<data_dir>/capability-selection.yaml`（`Settings` 已有 `data_dir`）。
- **默认值锚定 ADR-01**：未显式选择时 `primary` 必须等于 ADR-01 对应裁定。
- **变更记录**：追加写进既有 `RecordStore` 事件流（`storage.py` 已有 `append_event`），含 `slot` / `from` / `to` / `policy_source` / `changed_at`。

### D2-4｜可观测：选择进 receipt

- `CapabilityInvocationReceipt` 增 `selected_by: "adr-01" | "user" | "explicit-arg"` 与 `fallback_from: str | None`。
- **fallback 纪律**：`allow_fallback=False`（默认）时**不自动降级**，直接 `FAILED`/`UNKNOWN`。与 `PdfParser` 现有 docling-first 行为**不同**，故目录须显式标注 `fallback_policy: "explicit" | "none"`。
- 对齐 `CAPABILITY-CANDIDATES.md`：「任一 provider 不能隐式 fallback，fallback 必须显式记录在 receipt」。

### D2-5｜钉死（pin）与 ADR 冻结的可执行化

- `pinned=True` 的槽**禁止用户覆盖**（用于 benchmark，见 §5.3）。
- 一条测试断言：「`policy.primary` 与 ADR-01 裁定一致，**除非** `policy_source != "adr-01"` 且存在 owner 裁决记录引用」。**让 ADR-01 的冻结从文档变成会失败的测试。**

### D2-6｜选择入口（CLI）

```
autoresearch capabilities list                      # 目录：槽 / 选项 / 契约 / 代价 / 许可
autoresearch capabilities show <slot> <option>      # 单个选项详情
autoresearch capabilities select <slot> <option>    # 写 policy + 记事件
autoresearch capabilities reset <slot>              # 回落 ADR-01 默认
```

`select` 必须：① 拒绝非内置选项；② 拒绝 `pinned` 槽；③ 拒绝 `license_spdx` 属 AGPL 类且未带 `--accept-restricted-license` 的选项（§5.2）；④ 打印变更前后的值与 `policy_source`。

### D2-7｜受限许可选项的强制约束（**裁决 1 的落点，唯一有法律敞口的机制**）

适用于 `license_spdx` ∈ `{AGPL-3.0, AGPL-3.0-only, AGPL-3.0-or-later, SSPL-1.0}` 的选项：

1. **不得成为任何槽的 `primary`**（`SlotDeclaration` 构造期拒绝；`validate_slot()` 报错）。
2. 只能出现在 `fallback` 位，且该槽 `fallback_policy` 必须为 `"explicit"`（即**仅在 primary 不可用时启用，且必须记录原因**）。
3. 目录渲染必须带 `license_spdx` + 一句条款摘要。
4. 用户 `select` 该选项时必须显式传 `--accept-restricted-license`，否则拒绝。
5. 每次启用（无论自动兜底还是用户显式）追加写事件：`{slot, option, reason, enabled_at, accepter}`。

**为什么钉死 primary**：ADR-01 签字块 2 的条款是「**仅限 docling 权重不可用的离线场景作轻量兜底**」。一旦它成为 primary，条款前提就不成立了——不是"用户选了个东西"，是"我们把 AGPL 组件当默认件提供"。前者是用户行为，后者是产品行为。

**`selection_restricted_reason`**：由 ① 的 manifest 必填（A8）。② 读它做渲染与日志。

## 2.4 变更面

| 文件 | 动作 |
|---|---|
| `src/autoresearch/capability_catalog/`（包） | 新增（槽声明 + 目录 + 解析） |
| `src/autoresearch/selection_contracts.py` | 新增（`SelectionPolicy` / `SlotDeclaration`） |
| `src/autoresearch/capability_registry.py` | `CapabilitySelectionError` + receipt 增字段 |
| `src/autoresearch/invocation_contracts.py` | receipt 增 `selected_by` / `fallback_from` |
| `src/autoresearch/search_adapters.py` | `build_search_adapters` 改走目录解析 |
| `src/autoresearch/external_sources.py` | `PdfParser` 认领 catalog-only 身份（**不改解析逻辑**） |
| `src/autoresearch/cli.py` | `capabilities` 子命令 |
| `scripts/benchmark_trust.py` | 改走 `SelectionPolicy`（钉死 `adr-01`） |
| `.ai-team/tasks/O14-CAPABILITY-CATALOG.md` | 新建账本 |
| `docs/CONTRACTS.md` / `docs/ARCHITECTURE.md` | 补目录章节（修 F8） |

## 2.5 验收（含判别力）

| ID | 场景 | 判别力 |
|---|---|---|
| B1 | `describe_slots()` 覆盖首批槽；每选项字段齐备（含 `license_spdx`/`requires_credentials`/`supports_offline`） | 判据型 |
| B2 | `policy.primary` ≠ ADR-01 且 `policy_source="adr-01"` → 失败并指名 ADR-01 | **判据型（核心）** |
| B3 | `select` 一个非内置选项 → 拒绝 | 判据型 |
| B4 | `pinned` 槽 `select` → 拒绝 | 判据型 |
| B5 | `allow_fallback=False` 时主选项失败 → **不降级**，`FAILED` 且无第二次调用 | **判据型**：`PdfParser` 现状为降级 |
| B6 | 选择变更写入事件流；重启后 policy 仍在（持久化） | 判据型 |
| B7 | **旧代码复现 F12**：`benchmark_trust.py --source openalex` 的 receipt **不含任何选择痕迹**；新代码含 `selected_by` | **判据型（核心）** |
| B8 | catalog-only 条目声明 `network_required=True` 或 `emits_candidates=True` → 拒绝登记 | 判据型 |
| B9 | AGPL 选项 `select` 无 `--accept-restricted-license` → 拒绝；带则接受且写事件 | **判据型（新红线 A）** |
| B10 | `benchmark_trust.py --offline` 输出与改动前**逐字段一致**（钉死策略下） | 向后兼容 |
| B11 | 槽声明不得绕过 `selection_semantics` 声明（缺声明 → 拒绝登记） | 判据型（②-新 D） |
| B12 | 全量回归 ≥ 基线（**275 passed / 0 skipped**）+ 新增 | 回归 |

## 2.6 验证

同 §1.8，账本换 `O14-CAPABILITY-CATALOG.md`；另加 `python scripts/benchmark_trust.py --offline` 输出对比。

## 2.7 风险与回滚

- 目录为**加性**模块：删 `capability_catalog/` + 恢复 `build_search_adapters` 即回滚。
- 选择策略落盘在 `data_dir` 下；回滚后残留文件不影响旧代码（旧代码不读它）。
- **建议拆两个 PR**：① `paper_search` 单槽目录化（最小闭环，验证形态）；② 扩到 `pdf_parse` / reader / writer 槽。

## 2.8 可插拔度判据（owner 目标「足够模块化、足够可插拔」的可测化）

**先澄清一个张力**：owner 要「足够可插拔」，而本计划首批只做一个槽。二者不矛盾——
**「可插拔」的判据是「任意槽都能插」，不是「一次全插」。** 一次性做完五个槽，得到的是一个**无人验证的巨型目录**；先把机制做对，再按需插槽，得到的才是可插拔。

因此把"足够"翻译成**五条可失败的断言**（P1–P5）。它们才是本计划真正的交付物——四个槽是副产品。

| ID | 判据 | 断言方式 | 为什么它是"可插拔"的定义 |
|---|---|---|---|
| **P1** | **新增一个内置选项 = 只加 1 个文件**（`capability_catalog/<slot>/<option>.py`），**核心零改动** | 测试：在 tmp 目录合成一个新材料文件后，`describe_slots()` 能枚举到它，且 `git diff --stat` 对 `capability_registry.py` / `invocation_contracts.py` / `cli.py` 为零 | 增量成本 = 1 文件，这才是插拔 |
| **P2** | **新增一个能力槽 = 只加槽声明 + 1 行聚合**，registry 零改动 | 测试：断言 `capability_registry.py` **不 import 任何具体槽模块**（结构测试，正则扫描 import 段） | 核心不认识任何具体能力，才是真解耦 |
| **P3** | **用户切换选项 = 改 policy，代码零改动** | 测试：`select` 后重启进程，行为差异仅来自 policy；不需要改配置代码 | 选择与实现分离 |
| **P4** | **删掉一个选项文件 = 它从目录消失，无残留引用** | 测试：移除某槽的某个选项模块后，全量测试仍通过（除该选项自身的测试），且 `describe_slots()` 不再列出它 | 可拔 = 拔掉不留伤口 |
| **P5** | **每个槽的选项集合可被外部枚举与比较**（无需读源码） | 测试：`describe_slots()` 输出的每一项都含齐 `license_spdx`/`requires_credentials`/`supports_offline`/`trust_class`/`input_schema_ref`/`selection_semantics` | 目录是唯一事实源，不是代码顺序 |

**P2 是最关键的一条**：参考实现的 `pkgutil` 扫目录恰恰**不满足** P2 的对称要求（它把"核心不认识具体能力"做到了，但代价是核心知道了"目录布局"这个约定，且破坏了 P4 的可审计性）。我们的目标是**用显式表拿到同样的解耦度，同时保住 diff 可审计**。

**P1/P2 的验证方式必须诚实**：它们断言的是「改动的**形状**」（只动 1 个文件、核心 import 段不变），不是"运行时动态加载"。**本阶段不做动态加载**——P1/P2 是"改代码很容易"，不是"不改代码就能加载"。**这个区别必须写进对外表述，否则又变成 ②-3 说的"用可插拔包装范围"。**

**落点**：P1–P5 全部进入账本 `O14-CAPABILITY-CATALOG.md` 的 `Acceptance scenarios`，与 B1–B12 并列。P2 额外作为一条**结构测试**进 CI（防回归：一旦有人在 registry 里 import 具体槽，CI 红）。

---

# 对抗审查 ②（v0.2）

### ②-1（v0.1 保留，仍成立）｜消费者稀薄，收益取决于"用户真的要看目录"
F4/F9/F12：`CapabilityRegistry` 未接主线、reader/writer 双实现只在测试里、paper_search 选择只服务一个脚本。**目录的第一个真实使用者是 CLI 上的用户**，而用户能不能用到取决于 CLI 是否被当作产品入口（PROJECT.md 把 `cli.py` 列为 supported external boundary，**成立**）。但必须诚实：**在没有真实用户前，B1/B6/B9 这类验收保证的是"目录可用"，不是"有人用"。**
**反制**：首批只做 `paper_search` 一个槽，验证形态后再扩。**不要一次性目录化五个槽**——那会造出一个没人验证的巨型目录。

### ②-2（v0.1 保留，性质已变）｜ADR-01 冻结 vs 用户选择
v0.1 里这是**冲突**；v0.2 下变为**边界定义问题**：ADR-01 冻结的是**默认实现**（「首选即任务包默认实现」），用户运行时另选是**operator 层覆盖**，不与「成员任务包内不得私改选型」冲突——因为用户不是成员任务包。
**反制**：D2-5 用**测试**把边界钉死：`policy_source="adr-01"` 时必须等于 ADR-01；用户覆盖必须显式改 `policy_source="user"` 并留事件。**默认值仍是 ADR-01，用户改的是自己的实例，不是仓库的默认。** 这条若 owner 不认，② 应整体回退到 v0.1 的裁决流程。

### ②-3（v0.1 保留）｜不要用「可插拔」包装范围
v0.2 已明确不开放外部加载，因此**"可插拔"在本阶段是虚的**。真实能力是「内置多选 + 可观测」。Goal（§2.1）已按此措辞。**若对外表述用了"用户可添加任意源"，即与实现不符。**

### ②-4（**v0.1 红线 → v0.2 解除，须留痕**）｜域名白名单
F2/F3：`allowed_network_domains` 仍无强制点。v0.1 判其为红线，理由是"用户加源后布尔闸是唯一防线"。**v0.2 不开放外部源，路径不通，红线解除。**
**残留两点必须留痕**：
- (a) 目录**仍会展示** `allowed_network_domains`，用户可能误以为它被强制执行 → 目录渲染必须标注「声明值，传输层未强制」；
- (b) 若未来开放外部源，**该红线立即复活**，不得以"目录已存在"为由跳过域名强制。

### ②-新 A（**v0.2 最重要的新发现**）｜AGPL 后端变成用户可勾选项 = 绕过许可条款
ADR-01 签字块 2 原文：pymupdf4llm（AGPL-3.0）**仅限「docling 权重不可用」的离线场景作轻量兜底**，使用范围 = 本地工具链、不随产品分发；**一旦启用须在 receipt/PROGRESS 记录启用原因**。
现状 `PdfParser` 严格守法：只有 docling 失败才走 pymupdf，且写入 `diagnostics=["AGPL fallback enabled..."]`（F11）。
**但「让用户从内置选项里选」会把这个后端变成一个自由勾选项**——用户直接选 pymupdf4llm 就等于绕过"仅限 docling 不可用时兜底"的条款约束；而若本产品对外提供，这个选项可能被读作"随产品提供该能力"。
**反制（三条缺一不可）**：
1. `pdf_parse` 槽的 **`primary` 强制钉死为 `docling`**；`pymupdf4llm` 只能作为**受限兜底**出现，**不得成为可选 `primary`**；
2. 目录渲染该选项时必须显示 `license_spdx=AGPL-3.0` + 条款摘要；
3. 任何启用路径（自动兜底或用户显式）都必须写 `selection_events` + receipt，含启用原因——**承接 ADR-01 原有要求，不新造机制**。
**若 owner 认为"用户显式选择"应被禁止**，则 `pdf_parse` 不进目录，保持现状（现状是合规的）。
**这是本计划唯一可能产生法律后果的点，必须先裁。**

### ②-新 B｜用户换源会破坏评测可比性
ADR-01 slot 11 + `docs/BENCHMARK.md`：A5 的指标口径（citation recall / precision / hallucination ratio）依赖**固定选型**。用户把 `paper_search` 换成 `openalex` 后再跑 benchmark，**报告与历史不可比**。
**反制**：D2-5 的 `pinned=True` **必须对 benchmark 生效**——`benchmark_trust.py` 与任何 A5 入口强制 `policy_source="adr-01"`。B10 即为此。**若 owner 不要这条，则必须在报告里嵌入 policy 指纹**（哪个源、哪个版本、哪个 parser），否则评测结论无法追责。

### ②-新 C｜目录变 god-object 的风险
把 5 个槽塞进一个 `capability_catalog.py`，正是我们批评参考实现 `base_mailbox.py` 93KB 的同型风险。
**反制**：槽声明**按槽分文件**（包结构），`__init__.py` 只做聚合与解析。**目录是索引，不是实现。** 可加一条结构测试断言单文件行数上限（如 ≤200 行）。

### ②-新 D｜"选项"不同质，选择其实是配置
`paper_search` 三个选项并非等价物：S2 有 citation context 且需免费 key；arXiv 免 key 但只有预印本；OpenAlex 2026-02 起计费（ADR-01 勘误）。用户"选一个"的语义在不同槽里不同——有的是**替换**（parser），有的是**补充**（supplement source）。
**反制**：`SlotDeclaration` 必须声明 `selection_semantics: "exclusive" | "supplementary"`。`paper_search` = supplementary（ADR-01 本就是"主选+补充"），`pdf_parse` = exclusive。**不声明语义的槽拒绝登记**（B11）。

### ②-新 E｜默认值多了一个真值源
现状默认硬编码在 `build_search_adapters` 的 dict **顺序**里（S2、arXiv、OpenAlex）。目录化后默认来自 `SelectionPolicy`，若不同步就会有两处真值源——正是 F6 同型。
**反制**：默认**只能**来自"ADR-01 裁定 + 目录声明"，B2 断言两者一致。**禁止在 catalog 里另写一份默认。**

### ②-新 F｜不强推 registry
`PdfParser` 是同步、无 invocation 契约的。为"统一"而给它包一层 adapter 会引入不必要的间接并可能污染 receipt 语义。
**反制**：D2-1 的两类注册形态即答案；B8 保证 catalog-only 不被用来夹带需要网络/产生候选的能力——**这是"简化"与"治理"的交换点，必须显式。**

### ②-新 G｜持久化仍是新增体量，成本别低估
A4 明确注册表/幂等**不持久化**（F7）。用户选择要"可配置、可审计"就必须落盘 + 事件流。
**反制**：复用既有 `RecordStore` 的 append-only 事件机制（`storage.py` 已有 `append_event`），**不新建存储**。若做不到复用，本计划体量需重新评估。

### ②-新 H｜判别力自检
B1/B3/B6/B9 中涉及新符号者旧代码上会以符号缺失失败 → **不计入**。② 真正可用的判别力证据：**B2（ADR 冻结）**、**B5（默认不降级 vs PdfParser 现状降级）**、**B7（选择无痕 → 有痕）**、**B8（catalog-only 越界拒绝）**、**B11（缺语义声明拒绝）**。

### ②-新 I｜最坏情形
若在没有 owner 对 `pdf_parse` 的裁决、没有 benchmark 钉死、没有分批的情况下一次性目录化五个槽，会得到一个**体量大、无人验证、且在 AGPL 选项上留有法律敞口**的目录——**比现状更糟**，因为现状至少 `PdfParser` 是合规的。
**② 的准入门槛（四项缺一不可）**：① owner 对 `pdf_parse`/AGPL 的裁决；② benchmark 钉死策略落地；③ 首批仅 `paper_search` 一个槽；④ 槽声明分文件 + 语义声明必填。

---

## 3. 交叉依赖与裁决清单

| # | 依赖 | 说明 |
|---|---|---|
| X1 | **② 依赖 ①** | 目录要向用户呈现选项差异，靠的是 ① 的 `license_spdx`/`requires_credentials`/`supports_offline`/`input_schema_ref` |
| X2 | ① 与 ② 不得同 PR | ① 是冻结契约变更（owner/合同面），② 是运行时/消费面 |
| X3 | ① 需先审 O12/#15 的 manifest 形状 | 防 A3 误伤在飞关键路径 |
| X4 | `docs/CONTRACTS.md` 漂移（F8） | ① 一并修 |
| X5 | **F10 重复实现** | `search_service.py` 连接器族 vs `search_adapters.py` adapter 族是同一概念的两套实现；先裁决归并，**不得都进目录** |

### 需 owner 裁决（v0.2）

1. **`pdf_parse` 是否进目录？AGPL 后端能否成为用户显式选项？**（②-新 A，唯一可能产生法律后果的点）—— 我倾向：进目录，但 `primary` 钉死 `docling`，`pymupdf4llm` 标为受限兜底且启用必写痕。
2. **benchmark 是否强制钉死 ADR-01 选型？**（②-新 B）
3. 首批是否只做 `paper_search` 一个槽？（②-1）
4. 用户选择是否复用 `RecordStore` 事件流持久化？（②-新 G）
5. ① 定性为 owner/O 线变更并允许回写 L2 §CapabilityManifest（①-3）。
6. `trust_class`（自述）vs `CapabilityTrustTier`（生效）是否在 L2 显式区分（①-2/①-8）。
7. 判别力口径（判据型/符号型分离）是否固化为全项目要求（①-6 / ②-新 H）。
8. F10 的两套检索实现何时归并、谁负责（X5）。

## 4. 本文件未做的事（诚实边界）

- **未写任何代码**，未改产品文件。
- **已实测**：`main@1e7e196` 全量 `pytest -o addopts="" -q` = **275 passed / 0 skipped**（15.97s）；`ruff check src tests` = `All checks passed!`。**此前记录的「413 passed / 2 skipped」对本 commit 不成立**，已按实测更正（该数字很可能来自 `main + O12` 合并态 worktree，不可作为 `main` 基线）。
- F1–F12 来自静态读取与 `Grep` 工具全仓扫描。**本环境 `grep` 的 BRE `\|` 交替会静默返回空**（本轮两次踩到并纠正），故所有"零命中"结论均以 `Grep` 工具复核。
- **未逐条执行测试复核** F1/F2/F4/F9/F10/F12，建议开工前以一次覆盖报告复验。
- **未与 O12 分支交叉验证**：X3 待办。
- **未评估 MCP（T2）**：按 ADR-01 明确排除。
