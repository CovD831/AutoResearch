# O13 Capability Manifest Runtime Contract

- ID: `O13-CAPABILITY-MANIFEST`
- Title: `CapabilityManifest promoted from design draft to runtime contract (metadata + registration-time validation)`
- Status: `active`
- Status note: 本地完成，未 commit/push。owner 定性为 O 线变更（PLAN-capability-metadata §0.1 第 5 条）。编号取 O13（O11 已占、O12 = ProviderLane；S3-A2/S3-A3/O14 已被 provider lane 与目录包占位）
- Owner: `owner`
- Next owner: `user/team`

## Goal

把 `CapabilityManifest` 从**描述性**升格为**驱动性**：实现 `docs/rearchitecture/CAPABILITY-REGISTRY-TEMPLATE.yaml` v0.1 与 `CAPABILITY-CANDIDATES.md`§注册模板审查结论所定义的 identity/contract 层与 policy/profile 层，使登记项能被枚举与比较（接受什么输入 / 产出什么 / 是否需网络 / 可否离线 / 什么许可 / 什么凭据），为 S3-A3/O14 注册目录与内置多选提供数据源。**不实现** operational 层（timeout / retry / concurrency / resources），**不做**外部源加载，**不动** `application.py` 与共享 `contracts.py`。

## Acceptance scenarios

- [x] A1 必备身份与 schema 引用缺失 → 拒绝注册且 adapter 零调用（`manifest_id` / `input_schema_ref` / `output_schema_ref` 三个参数化用例）。
- [x] A1b schema ref 形状非法（含空格与标点）→ 拒绝注册。
- [x] A2 `network_required=True` 且 `allowed_network_domains` 为空 → 拒绝注册（关闭「声明出网但白名单为空」的静默洞）。
- [x] A2b 白名单非空的网络能力仍可注册（修复不得误伤合法能力）。
- [x] A2c 非网络能力零影响（白名单保持空、`network_required=False`）。
- [x] A3 三个内置 adapter 全部通过新校验，`registry.list()` 与注册视图逐字段相等。
- [x] A4 `kind` / `network_required` / `allowed_network_domains` 未显式传参时**从 manifest 推导**；推导不产生 `overridden_fields`。
- [x] A4b 显式传参与 manifest 不一致时写入 `overridden_fields`；一致时不写入。
- [x] A6 `lifecycle_status=retired` → 拒绝注册；`deprecated` → 注册成功且 `warnings` 非空。
- [x] A6b `manifest_warnings()` 永不拒绝合法 manifest（与 `validate_manifest()` 双通道分离）。
- [x] A7 每个内置 adapter 的符合性 fixture 存在，且内容与 manifest 的目录表面**逐字段一致**（fixture 漂移即失败）。
- [x] A8 受限许可（`AGPL-3.0`）无 `selection_restricted_reason` → 拒绝注册；给出原因后合法注册且 `license_spdx` 可读。
- [x] A8b MIT / Apache-2.0 / BSD-3-Clause 不需要受限原因。
- [x] A9 目录表面（`manifest_id`/`contract_version`/`input_schema_ref`/`output_schema_ref`/`license_spdx`/`requires_credentials`/`supports_offline`/`selection_tags`/`trust_class`/`lifecycle_status`/`conformance_fixture`）对三个内置 adapter 全部填充。
- [x] A10 `trust_class`（自述）与 `CapabilityTrustTier`（生效）分列，自述不提升生效层级。
- [x] 回归：全量 `299 passed`（基线 275 + 新增 24），ruff `All checks passed!`。

## Invariants

- 不修改 `application.py`、共享 `contracts.py`、Evidence/Writing 路径、`.ai-team/TASK.md` 或 `.project-to-act/`。
- `CapabilityManifest` 新增字段**全部可选默认**，对 A1/A2/A4 构造零影响（沿用 S3-A 先例）。
- 能力自述（`trust_class`）不能提升生效层级（`trust_tier` 一律 operator 指派）。
- `validate_manifest()` 是唯一校验入口，由 `register()` 在**重复注册检查之前**调用；adapter 在任何拒绝路径上零调用。
- `manifest_warnings()` 是**非致命**通道，**不具备拒绝能力**；两通道不得合并。
- schema ref 只校验形状，**不解析到中央名字表**（中央表会成为「新增能力必须改核心」的耦合点，与可插拔判据 P1/P2 冲突）。
- 校验层**不做文件系统或 import 操作**——fixture 存在性由契约测试断言，保持注册边界为纯策略边界。
- 白名单（`allowed_network_domains`）的**传输层强制仍不在本包**，归 ProviderLane/O12 与网络沙箱窗口。
- 不引入新依赖（`re` 为标准库）。

## Decisions

- D-O13-01 新字段清单：identity/contract 层 `manifest_id` / `contract_version` / `input_schema_ref` / `output_schema_ref`；policy/profile 层 `trust_class` / `license_spdx` / `selection_restricted_reason` / `requires_credentials` / `supports_offline` / `selection_tags` / `conformance_fixture` / `lifecycle_status`。依据 = `CAPABILITY-REGISTRY-TEMPLATE.yaml` + `CAPABILITY-CANDIDATES.md` 三层划分；L2「来源许可」open 项据此关闭。
- D-O13-02 新增 `CapabilityManifestInvalidError(CapabilityRegistrationError)`。子类化而非新增顶级错误，使既有 `except CapabilityRegistrationError` 调用方不受影响。
- D-O13-03 `overridden_fields` 取代「显式传参静默覆盖 manifest」。**修复前**：`register()` 在 `allowed_network_domains=None` 时把存储值置为 `()`，**覆盖 manifest 自述**；`kind` / `network_required` 亦然。**修复后**：默认从 manifest 推导，不一致则记录，manifest 保持单一真值源。
- D-O13-04 非致命事项走 `manifest_warnings()` / `CapabilityRegistrationView.warnings`，**不塞进 `overridden_fields`**（后者描述「注册调用的偏离」，前者描述「manifest 本身」，语义不同）。
- D-O13-05 receipt 增加 `manifest_id` / `contract_version` / `input_schema_ref` / `output_schema_ref` / `license_spdx`（默认 None / "l2"）。理由：receipt 是持久记录，不应依赖回查 manifest 才能解释自己；重放路径经 `model_copy(update=...)` 天然保留这些字段。
- D-O13-06 `CapabilityRegistrationView` 以**只读属性**暴露 manifest 身份字段（`manifest_id` / `contract_version` / `input_schema_ref` / `output_schema_ref` / `license_spdx` / `supports_offline`），**不复制字段**——避免再造一处真值源。
- D-O13-07 **已裁决 · 接受实现**（owner 批准 2026-09-14）：PLAN §D1-2 第 2 条原写「schema ref 必须可解析（在已知 contract 名字表内）」。实现改为**只校验形状**，**owner 批准以此为准**。理由：中央 contract 名字表会让「接入一个新能力就要改核心」，正是 O14 目录化要消除的失败模式；深度解析属选择层职责（S3-A3/O14）。PLAN 与实现的不一致以此条关闭。
- D-O13-08 **已裁决 · 接受实现**（owner 批准 2026-09-14）：PLAN §A6 原写「`deprecated` 注册成功且 diagnostics 非空」。实现改为独立的 `warnings` 字段（`CapabilityRegistrationView.warnings` + `manifest_warnings()`）。**owner 批准以此为准**。理由：语义等价、落点更清晰，且强化「非致命告警永不具备拒绝能力」这一不变式（两通道不合并）。
- D-O13-09 判据力口径固化为全包要求（owner 裁决 §0.1 第 7 条）：**判据型失败计入，符号缺失型失败不计入**。见 Verification。
- D-O13-10（owner 独立盲审后自修；契约必备字段必须真的必填）：L2 合同明文列 `name` / `kind` / `version` / `entrypoint` / `inputs` / `outputs` / `permissions` / `evidence_mode` / `network_required` / `allowed_network_domains` 为**必备字段**，而 `validate_manifest()` 只覆盖了其中一部分：**`entrypoint` 与 `evidence_mode` 从未被检查**，且两者默认值都是 `None`。实测：`CapabilityManifest(name='x', manifest_id='x', input_schema_ref='A', output_schema_ref='B')` → `validate_manifest()` 返回 `[]`（放行）。更糟的是**仓库自己的三个 built-in 适配器全部没有声明 `entrypoint`**，且被既有测试背书通过——即「冻结契约声称必备、实现既不校验、自家数据也不填」。修法：补上两个必备字段的校验；三个 built-in 通过新的 `capability_entrypoint` 属性声明入口（默认 `module:ClassName`）。
- D-O13-11（owner 独立盲审后判定为**虚警**；空候选是成功不是失败）：盲审提出 `candidate_only` 适配器返回 `value=None + candidates=[]` 时仍记为 `COMPLETED`，属 fail-soft，建议判 `FAILED`。**复核判定不成立**：`D-F8-01` 是早已确立的设计决策——「合法查询返回零命中是**确定性终态成功**」，适配器会在 diagnostics 里显式标记该情形；把空候选一律判失败会**摧毁这条语义**（实测按盲审意见修改后 44 个测试失败，含 `test_deterministic_empty_result_is_a_success_not_an_unknown`）。**已回退该修改，逻辑保持原样**，仅在注释中写明「空候选不是失败」的理由与 D-F8-01 的出处，避免下一轮审查者重复提出。**教训：审查发现必须先用仓库既有的设计决策校验，否则会把有意语义当缺陷「修掉」。**

## Completed

- `invocation_contracts.py`：`CapabilityManifest` 补 12 个字段 + `CapabilityTrustClass` / `CapabilityLifecycleStatus` / `RESTRICTED_LICENSES` + `is_restricted_license` 属性。
- `capability_registry.py`：`validate_manifest()`、`manifest_warnings()`、`CapabilityManifestInvalidError`；`register()` 接线（先校验、后重复检查）；推导 + `overridden_fields`；view/receipt 字段；`__all__` 导出。
- `search_adapters.py`：`_CandidateOnlyAdapter` 补 `license_spdx` / `requires_credentials` / `supports_offline` / `selection_tags` / `selection_note`；`manifest()` 补 `manifest_id` / schema refs / fixture 路径；三个子类补各自元数据与 `selection_note`（S2 主选需 key / arXiv 免 key 仅预印本 / OpenAlex 计费且 opt-in）。
- 新增 `tests/fixtures/capabilities/{semantic_scholar_search,arxiv_search,openalex_search}.json`（从真实 manifest 生成的目录表面快照）。
- 新增 `tests/test_capability_manifest_contract.py`（24 个用例）。
- 测试构造点同步：`tests/test_capability_registry.py` 的 `manifest()` helper（含 `network_required` 时自动补白名单）、`tests/test_benchmark_runtime.py` 的 `StubAdapter.manifest()`。
- 文档回写：`04-l2-contracts.md` §CapabilityManifest（★S3-A2 段）、`docs/CONTRACTS.md` 新增 §5 能力接入契约（并修 F8 漂移：该文档此前对 capability/registry/manifest **零提及**）。

## Pending

- S3-A3/O14（注册目录 + 内置多选，含 §2.8 可插拔判据 P1–P5）未开工——依赖本包落地。
- D-O13-07 / D-O13-08 **两处偏离已于 2026-09-14 由 owner 批准，均接受实现（见 Decisions）**——不再阻塞合并。
- **owner 独立盲审已完成（2026-09-14）**：2 高 3 中 2 低，逐条独立复现。**已修 1 条高危（D-O13-10）**，**1 条判定为虚警并回退（D-O13-11）**，其余为「校验分支实为死代码」「关键失败路径零覆盖」「外部旧 manifest 无迁移说明」——**登记为已知，不在本包修**（理由见下）。
- `manifest_id` 与 `name` 目前在三处构造点取值相同；**「同一能力的多版本是否共享 manifest_id」的语义仅由文档约束、无测试强制**（见 Known limits）。
- 未与 O12/#15 分支交叉验证：该分支若引入 manifest 形状，须纳入未来穷举验收。
- `docs/ARCHITECTURE.md` 仍未补 capability 章节（`docs/CONTRACTS.md` 已补）。

## Next step

owner 复核 D-O13-07 / D-O13-08 两处偏离与 Known limits 后决定合并；随后开工 S3-A3/O14 的 `paper_search` 单槽目录化（最小闭环）。

## Verification

```
python -m ruff check src tests            -> All checks passed!
python -m compileall -q src
python -m pytest -o addopts="" -W error -q
node .ai-team/check.mjs --base origin/main
python scripts/check_pr_contract.py --base origin/main
```

**基线与现状（均在本 worktree 实测，勿跨 worktree 搬运）**：

| 场景 | 结果 |
|---|---|
| `main@1e7e196`（O13 开发期基线） | 275 passed / 0 skipped |
| `1e7e196` + O13 原始改动 | 299 passed |
| `main@60a9ea4`（合并 O12 + A6 后） | 481 passed / 2 skipped |
| **`60a9ea4` + O13 + 本轮盲审修复** | **509 passed / 2 skipped / 0 error** |

O13 与最新 main 的合并冲突仅 `capability_registry.py` 一处（两处冲突区块均为「双方各自新增字段」，逐块合并即可），`contracts` 侧的 `tags` 与 `TokenUsage`/`InvocationCost` 分别落在不同区域，自动合并。

### 判别力（owner 裁决 §0.1 第 7 条口径：两类分开写）

> 方法论见 `docs/process/DISCRIMINATING-POWER.md`（本包同时把该口径固化为项目过程文档）。

**测量方法**：在 `main@1e7e196` 建 detached worktree，拷入新测试文件与 fixture，注入**符号 shim**（把本包新增的符号以「惰性桩」形式补到旧模块上）后运行。不做 shim 的话整模块会在 import 期失败，**一个断言都不会被执行**——`ImportError` 不能作为任何证据。

**结果：基线代码上 16 failed / 8 passed。**

| 类别 | 数量 | 计入判别力 | 示例 |
|---|---|---|---|
| **判据型失败**（旧代码「允许」了它：`DID NOT RAISE` / 值断言不符） | **10** | ✅ **计入** | `network_required=True` + 空白名单**注册成功**；`retired` **注册成功**；`AGPL-3.0` 无受限原因**注册成功**；缺 `manifest_id` / `input_schema_ref` / `output_schema_ref` **注册成功**；未传白名单时存储值被覆盖为 `()`  |
| 符号型失败（`AttributeError` / `KeyError`，本包新符号缺失） | 6 | ❌ 不计入 | `conformance_fixture` / `trust_class` 属性不存在；`warnings` 通道不存在；`license_spdx` 视图属性不存在 |

**诚实注记**：其中 2 例（`overridden_fields` 断言、`warnings` 断言）在真实旧代码上是 `AttributeError`（符号型），是 shim 把属性补成了空元组后才表现为断言失败。**故按符号型计，不计入上表 10 例。** 这与 O12 轮「16 个新测试中 12 个在修复前失败」同款做法：**先注入符号，再逐条判定**。

**基线旧行为复现（判据型核心证据，可独立重跑）**：

- 「网络能力 + 空白名单」在 `1e7e196` 上**注册成功**且 `view.allowed_network_domains == ()`——即声明出网却无白名单被静默接受。
- 「未传 `allowed_network_domains`」在 `1e7e196` 上把存储值覆盖为 `()`，与 manifest 自述的 `["api.example"]` 不符——**manifest 不是真值源**。

### 判别力 · 第二轮（D-O13-10 的必备字段校验）

**测量方法**：在**修复前**的合并态 `d4a629f` 建 detached worktree，**只替换测试文件**（`git checkout -- src/` 保持基线），确认 `src` 未含修复后运行。

**结果：3 failed / 25 passed（修复前）→ 28 passed（修复后）**，全部为判据型：

| 失败测试 | 失败信息 |
|---|---|
| `test_missing_entrypoint_is_rejected_at_registration` | `validate_manifest` 未报 entrypoint 问题 |
| `test_missing_evidence_mode_is_rejected_at_registration` | 同上 |
| `test_every_builtin_adapter_declares_a_resolvable_entrypoint` | **`AssertionError: ('semantic_scholar_search', None)`** |

最后一条是最直接的证据：**built-in 适配器的 `entrypoint` 实际就是 `None`**。

### Known limits

- 越权=0 仍是**结构保证**而非沙箱（沿用 A4 Known limits）：adapter 为进程内对象，自行持有 `EvidenceService` 引用仍可绕行。本包不改变这一点。
- `manifest_id` 的**语义**（同能力多版本共享、新能力必须换新 id）只有文档与 fixture 快照约束，**无跨版本一致性测试**。当前三处构造点取 `manifest_id == name`，若将来引入同能力多版本，需要一条「同 name 不同 version 必须同 manifest_id」的断言——本包未写，**登记为已知缺口**。
- schema ref 不做解析（D-O13-07）：拼错的 contract 名只要形状合法即可注册。深度解析归 S3-A3/O14。
- `allowed_network_domains` 仍**不强制**（沿用 A4 F2/F3 已知限制），本包只补上「非空」这一必要条件。
- `selection_tags` / `supports_offline` / `selection_note` 在 `_CandidateOnlyAdapter` 上**已有取值但本包零消费**——消费方是 S3-A3/O14 目录。这是有意的类型归位（避免 S3-A3/O14 再改一次契约），**但不构成本包的收益**。

## Handoff note

- From: `owner`
- To: `user/team`
- 改动全在本地工作树，**未 commit / 未 push**。
- 本包只交付「manifest 升格 + 注册期校验」，**不含目录、不含选择、不含外部源加载**。
- 上游依据：`docs/coord/PLAN-capability-metadata-and-discovery.md` §0.1（8 条裁决）与 §1；`CAPABILITY-REGISTRY-TEMPLATE.yaml`；`CAPABILITY-CANDIDATES.md`§注册模板审查结论。
- 待决：D-O13-07（schema ref 只校验形状）、D-O13-08（warnings 取代 diagnostics）、`manifest_id` 跨版本一致性缺口。
