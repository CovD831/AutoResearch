# M01-CONTEXT

- ID: `M01-CONTEXT`
- Title: `M01 上下文装配 / 状态迁移 / 交接回放（L-01 lane，K5 + K6）`
- Status: `handoff`
- Status note: 2026-09-15 于独立 worktree `r007-l01-context`（分支 `feat/r007-l01-context`，base `main@8dd8780`）实现 K5 `ContextBudget`/`ContextSlice` 与 K6 `StateMigration`，并复用既有 `handoffs.py` 落地 M01-06 交接回放。基线实测 **537 passed / 2 skipped / 0 failed**；本包全量 **580 passed / 2 skipped**；专项 **43 passed**；`ruff check src tests` clean；`compileall -q src` exit 0；`check.mjs`（全仓 + 本账本）均 `valid`。**未 commit、未 push**（按门禁纪律改动停在本地）。K5 的「分级接口」已按 R-007 §2 要求留出（开放 `kind` + `register_kind(tier)` + 分层预算）。owner 已裁决 D-L01-02 / D-L01-02b 批准、K5-3 维持；D-L01-05 / D-L01-09 仍待裁决。
- Owner: `impl-l01-context`
- Next owner: `team-lead`

## Goal

把 R-007 L2 的 **K5**（`ContextBudget`/`ContextSlice`，原表 M01-05「只装配当前任务必需上下文；超限时退回拆分而非堆砌全文」）与 **K6**（`StateMigration`，原表 M01-02 `ResearchState` v1→v2 迁移 + 未知字段策略）落成可运行代码，并复用 `handoffs.py` 的既有 envelope 语义提供 M01-06 交接回放。K5 同时是 **M11-04（ContextPack 分级装配）的前置**，故必须**留分级接口**。

本包**不做**：M11-04 的分级装配本身；不碰 `knowledge.py` / `storage.py` / `contracts.py`（R-007 §3.2 全局串行点）；不建第二套 handoff 类型；不为 K5-3 写「通过」断言。

## Acceptance scenarios

- [x] K5 字段级契约落地：`ContextBudget`（`max_tokens`/`max_items_per_kind`/`reserved_ratio`）+ `ContextSlice`（`slice_id`/`kind`/`refs`/`rendered`/`truncated`/`dropped_refs`）。
- [x] **K5-1 超限退回拆分**：装不下的 item 被丢弃并记入 `dropped_refs`，输出按 kind 拆成多个 slice；被丢 item 的正文**不进入** `rendered`。
- [x] **K5-2** `truncated=True` ⟹ `dropped_refs` 非空（`ContextSlice` validator，取严格口径）。
- [x] **K5-3** `guidance` 不进入事实论断：**本层不做 validator、不写断言**（L2 自标「架构意图」）；只做结构半边（guidance 独立成末尾 tier/slice）。
- [x] **K5-4** `refs` 只存引用 ID：`RefId = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]`。
- [x] **K5 分级接口**（R-007 §2 硬要求）：开放 `kind`（`str`）+ `register_kind(kind, tier=)` + `max_items_per_kind` / `max_tokens_per_kind` 双层预算 + 按 tier 迭代装配。
- [x] **K6-1** 未知字段策略必须显式：`unknown_field_policy` **无默认值**，且 `Literal` 校验；`reject` 抛 `UnknownFieldError`，`preserve` 原样保留。
- [x] **K6-2** 迁移可回放：同输入同输出（含键序），不改入参。
- [x] **K6-3** `to_version` 严格递增：`version_key()` 数字感知比较（`v1 < v2 < v10`），非法版本号报错。
- [x] **M01-06** 交接回放：`HandoffReplayService.by_run` 复用 `HandoffEnvelope` 与 `handoffs` 分区，导出 envelope / artifact 引用 / evidence 引用（+ 显式声明 gate 作用域）。
- [x] 负例 N-1/N-2/N-3 均已实现且断言**结论**（非「没崩」）；N-4 记为「本层不可测」。
- [x] **既有 `ResearchState` 的版本桥**：`state_version()` 把 `schema_version: int` 桥成 K6 的 `str` 标签（无 int 版本时报错）；K6 无法自行 bump 版本号这一缺口已**显式断言**并上报（D-L01-09），未绕过、未粉饰。
- [x] 判据力：符号-only shim + **11 组**行为回退突变，全部得到判据型失败（见 §Verification）。
- [x] **D-L01-02b 等价性**：`max_tokens_per_kind` 为**可选**字段，**默认 `None` 时行为与 K5 原文等价**（省略 / 显式 `None` / `{}` 三者装配结果逐一相等，4 个规范 kind 的 ceiling 全等于 `usable_tokens`）；由测试机械证明，判别力由突变 M11 证明。
- [x] **预留与丢弃的语义边界（owner 裁决 3）**：未用的预留**不产生** `dropped_refs`；因预留而装不下的 item **必须点名记入** `dropped_refs`。两条各有断言，判别力由突变 M10 证明。

## Invariants

- **只新建两个源文件**：`src/autoresearch/context_assembler.py`、`src/autoresearch/migration.py`（`git status` 可证；未改任何既有源文件）。
- **不碰全局串行点**：`knowledge.py` / `storage.py` / `contracts.py` 零改动（`git status` 无该三文件）。本包所需类型全部在自己模块内定义或引用既有契约。
- **不建第二套 handoff 类型**：`context_assembler.py` 内 handoff 相关类型只有 `HandoffEnvelope`（引用 `contracts.py`）与 `HandoffReplay`（新容器，字段是引用不是内容）。
- **K5-3 不得被伪造成可校验**：代码里没有 guidance/事实论断相关 validator，测试里没有对应「通过」断言。
- **`truncated` 与 `dropped_refs` 强绑定**：`ContextSlice` 构造期即拒绝 `truncated=True ∧ dropped_refs==[]`。
- **未测不等于 0**：`ContextItem.tokens is None` 时该 item 被丢弃并记入 `dropped_refs`（不按 0 计费）；`version_key` 对无数字成分的版本号报错（不排为 0）。
- **迁移的静默丢值防线**（构造期拒绝）：映射多对一、`defaults` 被映射遮蔽、单 payload 内新旧名同时出现。
- **不可违反的约束不写检查**：`MigrationChain` 初版有一条「chain 版本严格递增」检查，实测**不可达**（邻接性 + 每步 `to>from` 已蕴含），已删除且不为其写断言。

## Decisions

- **D-L01-01（K5-2 收窄为严格口径）—— owner 已批准**：契约原文是「`truncated=True` ⟹ `dropped_refs` 非空**或** `rendered` 截断可追」。本装配器 item 原子、不存在条内截断，**软口径在本装配器里恒为真分支 → 留着就是留一个恒真假绿的口子**，故实现取「必须记 `dropped_refs`」的严格口径 —— 不变量更强且**可被违反**（突变 M1 实测失败）。**登记为收窄，非静默偏离。**
- **D-L01-02（K5 分级接口的三件套）**：`kind` 用开放 `str`（枚举只给规范值）、新增 `max_tokens_per_kind` 字段、新增 `register_kind(kind, *, tier)`；未给 ceiling 的 kind 回落到全局 `usable_tokens`。**这是 R-007 §2「为分级留接口，不要写死单级」的实现方式**，不是偏离契约；登记以求可审。未注册 kind 显式报错（否则 tier 概念不成立）。**owner 裁决（2026-09-15）：批准**——`max_tokens` 是总量预算，加一个**可选**字段属「新增」而非「改既有字段语义」，符合「新 lane 在新模块定义自己的类型」。
- **D-L01-02b（owner 批准，附条件登记）**：`ContextBudget` 新增 **`max_tokens_per_kind: dict[str, int] | None = None`（可选）** —— K5 原文（`04-l2-contracts.md` K5 字段表）只列 `max_tokens` / `max_items_per_kind` / `reserved_ratio`，**只约束条数维度**；本字段是**为 M11-04 分级装配预留的 token 维度扩展**。**默认 `None` 时行为与 K5 原文等价**：所有 kind 回落到全局 `usable_tokens`，与只设 `max_tokens` + `reserved_ratio` 的单级调用**逐字段一致**。等价性由 `test_max_tokens_per_kind_is_optional_and_none_is_k5_equivalent` 机械证明（省略 / 显式 `None` / `{}` 三者装配结果逐一相等，且 4 个规范 kind 的 `kind_token_ceiling` 全等于 `usable_tokens`），判别力由突变 **M11** 证明（把回落值改成 0 → `assert 0 == 80` 失败）。
- **D-L01-02c（owner 裁决 2：K5-3 维持「无断言」）**：owner 确认 K5-3 与 K7-1 / K1-4 / K12 / K14-4 同族，均**不可机械校验**；本包的处置（`DEFAULT_TIER_ORDER` 把 guidance 放末层 + docstring 声明「规则在下游强制」）是**结构性补偿**，正确。**禁止**为它写「通过」断言 —— 本包未写，维持。
- **D-L01-03（未测成本 fail-closed）—— owner 已批准**：契约未规定 `tokens` 未测时的行为。按本项目「裸露的未测绝不许记成正常值」纪律（`07-lane-kickoff-convention.md` §4.3）取 fail-closed：丢弃 + `dropped_refs` + `truncated=True`，**可观测**。突变 M3（把未测当 0）实测被 `test_unmeasured_token_cost_is_not_treated_as_free` 抓住。
- **D-L01-04（K5-3 不做校验、不写断言）—— owner 已裁决维持**：L2 K5「可机械校验性」表自标 ❌ 架构意图。本层只保证 guidance 独立成末尾 tier/slice，禁止为 K5-3 写「通过」断言（避免恒真假绿）。**N-4 因此记为「本层不可测」，不是「已测通过」。** owner 确认这与 K7-1 / K1-4 / K12 / K14-4 同族。
- **D-L01-05（M01-06 的 Gate 引用降级为 project 作用域）—— owner 已裁决维持**：原表要求按 run 导出「Gate 引用」，但实测 `GateDecision`（`contracts.py:277`）**只有 `project_id`/`operation`，没有 `run_id`** —— 在 run 粒度上**不可实现**。不越界改 `contracts.py`，改为 project 作用域导出，并在 `HandoffReplay.gate_scope="project"` 上**显式声明**作用域，避免调用方误读为 run 作用域。owner 评语：**契约表达能力不足时，显式降级并声明，而不是偷偷改共享契约**。→ 另立**契约缺口上报 E-L01-01**（见 §Contract gap escalations）。
- **D-L01-06（`MigrationChain` 扩展）**：K6 只定义单步 `StateMigration`。K6-3「严格递增」在单步里退化为 `to > from`；引入 chain（邻接性校验 + 端到端回放）才让它成为真约束。约 35 行、无新依赖、只在本模块内。
- **D-L01-07（删掉一条不可违反的检查）**：`MigrationChain` 初版另写「chain 版本严格递增」检查。**实测不可达**：邻接性把第 i 步 target 钉死为第 i+1 步 source，每步自身已保证 `to>from` → 任一非递增链必然先在邻接性或单步校验上失败。已删除，代码内注释留证，**且不为其写断言**（空约束纪律）。
- **D-L01-08（未定义行为一律显式报错）**：传入未注册 kind、版本号无数字成分、单 payload 新旧名并存 —— 三者均显式报错，不做静默处理。
- **D-L01-09（契约缺口；上报，待裁决）**：既有 `ResearchState.schema_version` 是 **`int`**（`contracts.py:642`，实测只出现过 `1`），而 K6 声明版本字段为 **`str`**；更关键的是 **K6 没有值变换能力** —— `field_mapping` 只能重命名、`defaults` 只能补**缺失**字段，因此 `schema_version` 的 bump（`1 → 2`）**表达不了**。读侧由 `state_version()` 桥成 `"v1"`（只此一处对齐，无 int 版本时报错）；写侧留给调用方，**本包不发明 `set_fields` 之类的新字段**。测试 `test_migrating_a_research_state_dump_preserves_fields_but_not_the_version` **显式断言该限制**（断言 `schema_version` 仍为 `1`），不绕过、不粉饰。若「迁移一步完成 v1→v2」是硬要求，**K6 需补值变换语义 —— 契约变更须由契约作者裁决**。
- **D-L01-10（owner 裁决 3 的答复：`reserved_ratio` 与 `dropped_refs` 的语义边界）**：owner 问「哪一项涉及 `reserved_ratio` 或迁移策略的取舍」，初步倾向为「**预留但未用的预算不应被记为「丢弃」**」。核实后答复如下 —— 契约原文（`04-l2-contracts.md` K5）写：「`reserved_ratio` — 预留给输出的比例（默认 0.2）」；K5-1 写「超限时退回拆分」；K5-2 写「`truncated=True` ⟹ `dropped_refs` 非空……」。本包实现与该倾向**一致**，且把它拆成两条互补的断言：
  1. **预留但未用的额度不产生 `dropped_refs`** —— 在 `usable_tokens`（`max_tokens × (1 - reserved_ratio)`）之内装得下的 item 全部留在 `refs`、`truncated=False`，那 20% 不会被记成「丢弃」（`test_unused_output_reserve_does_not_fabricate_dropped_refs`）。
  2. **因预留而装不下的 item 必须点名记入 `dropped_refs`** —— 它**确实没进 slice**，隐藏它才是 fail-open（`test_output_reserve_excludes_an_item_by_naming_it`）。
  判别力由突变 **M10**（把 `usable_tokens` 改回 `max_tokens`，即忽略预留 → `assert ['ev1','ev2'] == ['ev1']` 失败）证明。**推论登记**：`reserved_ratio` 只影响「装得下/装不下」，**不参与丢弃记账**；`dropped_refs` 的语义是「该引用未进入 slice」，与丢弃原因（条数层 / token 层 / 预留 / 成本未测）无关。

## Contract gap escalations

两条都是**契约表达能力不足**，不是本包实现缺陷。本包一律**就地显式降级 / 显式断言限制**，**不单方面改共享契约**（`contracts.py` 是 L-06/L-07 的全局串行点，本包未碰）。owner 已确认两条的处置均正确、维持。契约侧是否变更**须 owner 裁决**。

**E-L01-01 —— M01-06「按 run 导出 Gate 引用」在 run 粒度不可实现**

- **缺口**：`GateDecision`（`contracts.py:277`）只有 `project_id` / `operation`，**没有 `run_id`**，也无其它 run 关联字段 → 按 run 过滤 Gate 引用**不可实现**（对应 D-L01-05）。
- **就地处置**：改为 **project 作用域**导出，并在 `HandoffReplay` 上**显式声明** `gate_scope="project"`，消费方不会把 project 作用域误读成 run 作用域。**不改 `contracts.py`。**
- **建议 L2 补**：给 `GateDecision`（或 `GateRequest`）补 `run_id` / `work_package_id`，并与 K1 `RunManifest` 建立引用 —— **属契约变更，须 owner 裁决**。
- **回退成本**：≈3 行（`by_run` 的 gate 过滤条件 + `gate_scope` 默认值）+ 1 条测试。

**E-L01-02 —— K6 无值变换语义，`schema_version` 的 bump（1→2）不可表达**

- **缺口**：K6 只有 `field_mapping`（改名）+ `defaults`（补**缺失**字段）+ 未知字段策略，**没有值变换**，因此「把 `schema_version` 从 `1` 改成 `2`」表达不了；且既有 `ResearchState.schema_version` 是 `int`、K6 声明版本字段为 `str`（对应 D-L01-09）。**K6 从来不是值变换引擎** —— 这是它的**表达力边界**，不是实现缺陷（owner 裁决原话）。
- **就地处置**：读侧 `state_version()` 桥 `int → "v1"`（无 int 版本时报错，只此一处对齐）；写侧留给调用方；测试**显式断言该限制**（`schema_version` 仍为 `1`）。**不发明 `set_fields` / `constants` 之类的新契约字段。** owner 裁决：**算「部分满足，且是当前权限内的最大满足」**。
- **建议 L2 补**：给 K6 补值变换语义（如 `set_fields` / `transforms`），或明文规定「版本号标签由调用方在迁移后写入」—— **属契约变更，须 owner 裁决**。
- **回退成本**：≈10 行（`_validate_step` + `apply`）+ 改 1 条测试断言（「仍为 1」→「已变为 2」）+ 新增 1 条判别力突变；`state_version()` 桥可保留。

## Completed

- `src/autoresearch/context_assembler.py`：`ContextKind`（4 个规范值）/ `ContextBudget`（含 `usable_tokens` / `kind_token_ceiling` / `kind_item_ceiling`）/ `ContextItem` / `ContextSlice`（含 K5-2 validator）/ `ContextAssembly` / `ContextAssembler`（`register_kind` + 按 tier 的装配循环）/ `HandoffReplay` + `HandoffReplayService`（M01-06）。
- `src/autoresearch/migration.py`：`UnknownFieldPolicy` / `MigrationError` + `UnknownFieldError` + `FieldCollisionError` / `version_key` / `StateMigration`（含 K6-3 与三条静默丢值防线）/ `MigrationChain`。
- `tests/test_m01_context_assembler.py`（23 例）+ `tests/test_m01_migration.py`（20 例）= **43 例**，覆盖 N-1..N-4、K5-1..K5-4、K6-1..K6-3、分级接口 5 组（含 D-L01-02b 等价性 + 非正 ceiling 拒绝）、回放 5 例、`ResearchState` 版本桥 3 例、预留/丢弃语义 2 例。
- `docs/tasks/M01-context/tasks/L3.md`（六节完整 L3）+ `task-package.json`；`L3-SKELETON.md` 原样保留作来源凭证。
- 判据力证据：符号-only shim 一次（42 failed / 1 passed，`ImportError`/`AttributeError` = 0）+ **11 组**行为回退突变（11/11 判据型失败）。证据自包含脚本随包落盘：`docs/tasks/M01-context/evidence/discriminating_power.py` + `results.txt`。

## Pending

- **提交 / 推送：owner 已明确「不许可」**（2026-09-15，老板纪律：不得自动 commit/push，等老板明确确认）。本包改动**全部停在本地工作区**（未 commit / 未 push），等老板确认后才可提交。
- **D-L01-02 / D-L01-02b 已裁决批准**（2026-09-15）：`ContextBudget` 新增 `max_tokens_per_kind`（可选）获准，**登记已写明「默认 `None` 时行为与 K5 原文等价」**（见 Decisions）。K5-3 维持「无断言」。
- **D-L01-05 / D-L01-09 已裁决：处置维持**。两条均转为**契约缺口上报**（E-L01-01 / E-L01-02，见 §Contract gap escalations）：缺陷在**契约表达能力**，不在本包实现；**改契约须 owner 裁决**，本包不单方面改 `contracts.py`。回退成本已逐条写明（分别 ≈3 行 / ≈10 行 + 测试）。
- **D-L01-09 待契约作者裁决**：K6 无值变换能力，无法自己把 `ResearchState.schema_version` 从 `1` 跳到 `2`。当前读侧有 `state_version()` 桥、写侧留给调用方。若 owner 认为「一步完成 v1→v2」是硬要求，K6 需补值变换字段（如 `set_fields`），**这是契约变更，须由契约作者裁决**。
- **K5-1「退回拆分」解读已闭环**：owner（同时为 K5 契约作者）已确认「按 `kind` 分层拆成多个 slice + 丢弃溢出项」**正确，以本实现为准**，无需返工。见 L3 §7 首条。
- **K5-3 的机械校验**：本层不做，需在 M11-04 / 输出侧落地。本包只交付结构前提。
- **`check_pr_contract.py --base main` 在本 lane 上是空转的**：该脚本只看 `git diff main...HEAD`（已提交），本 lane 按纪律未提交 → 输出「0 changed paths」。因此它的「通过」**不构成对本 lane 的证据**，真实验收以工作区测试为准。若 owner 提交后再跑，该脚本会要求 `.ai-team/tasks/` 下存在 ledger（本文件已备）。

## Next step

请 team-lead / owner：

1. 裁决是否提交本 lane（`git status` 里的两新源文件 + 两测试文件 + `docs/tasks/M01-context/` + 本账本）；
2. 裁决 D-L01-05（M01-06 的 Gate 粒度）；
3. 把「K5 分级接口」的具体形态带话给 M11-04（L-06）：新 kind 走 `register_kind(kind, *, tier)`，token 层走 `max_tokens_per_kind`，条数层走 `max_items_per_kind`，`kind` 字段是开放 `str`。

**请优先攻击这三处**：

1. **K5-3 是否被本包变相「测绿」**：我刻意没写断言；若你认为 `guidance` 独立成 tier 这一结构也是「断言了 K5-3」，请指出。
2. **`tokens=None` 丢弃**（D-L01-03）：这会让「成本未测」的 item 永远进不了上下文，是个真实的功能缺口 —— 但它至少是**可见**的。若你认为应该改为「收下但标记」，请给出。
3. **`MigrationChain` 是否成立**：K6 只定义单步。若 owner 认为 chain 属于契约外扩张，可整块删除（只影响 4 条测试 + `migration.py` 末 35 行）。
4. **E-L01-02（D-L01-09）契约缺口**：owner 已裁决「读侧桥 + 写侧留给调用方」**算部分满足、且是当前权限内的最大满足**；缺口本身（K6 无值变换）已上报。若最终要给 K6 补值变换语义，请一并裁决回退成本与测试改动（见 §Contract gap escalations）。

## Handoff note

交回 `team-lead`（R-007 主理人）。**改动全部停在本地工作区，未 commit、未 push —— owner 已明确「不许可」，等老板确认。** owner 已裁决：D-L01-01 / -02 / -02b / -03 **批准**、D-L01-04（K5-3 无断言）**维持**、D-L01-05 / -09 **处置维持并转为契约缺口上报**（E-L01-01 / E-L01-02）、D-L01-10（预留↔丢弃语义）**批准**；K5-1 解读**已确认以本实现为准**。判据力证据分两层（符号 shim 42 failed / 11 组行为突变 11/11），**未把弱判据型（`NotImplementedError`）粉饰成强证据**。

## Verification

命令均在 `/Users/abab/Documents/ChatGPT/autoresearch/r007-l01-context` 下、用 `<python> = /Users/abab/.workbuddy/binaries/python/envs/default/bin/python`、`PYTHONPATH=src` 执行。

- [x] **开工基线（本 worktree 自测，未搬运他人数字）**：`pytest -q -o addopts="" -W error` → **537 passed, 2 skipped**，exit 0。
- [x] **专项**：`pytest tests/test_m01_context_assembler.py tests/test_m01_migration.py -q -o addopts="" -W error` → **43 passed**。
- [x] **全量**：`pytest -q -o addopts="" -W error` → **580 passed, 2 skipped**（537 + 43，基线未下降）。
- [x] `ruff check src tests` → **All checks passed!**（首轮抓到 1 处 test 文件 import 排序，已修）。
- [x] `compileall -q src` → exit 0。
- [x] `scripts/check_pr_contract.py --base main` → exit 0，但**输出 0 changed paths**（原因见 Pending：未提交 → 该门为空转，不计为本 lane 证据）。
- [x] `node .ai-team/check.mjs --base main` → 见下（写账本前 blocked，写后复跑）。

### 判据力实测（两层，如实分层记录）

**A. 符号-only shim（约定要求的取判据型手段）**

shim 内容：**只补符号 + 字段声明，不含 validator、不含方法体**（`assemble`/`apply`/`register_kind`/`version_key`/`state_version` 抛 `NotImplementedError`；`unknown_field_policy` 给了个天真默认值 `"preserve"` 以模拟「未强制显式」）。仅用于测量，**不进交付**（随包保留于 `docs/tasks/M01-context/evidence/*.shim.py`）。

实测：**42 failed / 1 passed**（共 43 条）；**`ImportError`/`AttributeError` 计数 = 0**。失败类型分布：

| 类型 | 数量 | 判据强度 |
|---|---|---|
| `Failed: DID NOT RAISE ValidationError/ValueError` | **7** | **强**（测试点名了缺失的保证）：K5-2、K6-1、K6-3、映射多对一、defaults 被遮蔽、chain 邻接性、`state_version` int 守卫 |
| `NotImplementedError: shim` | **34** | **弱**（证明测试确打到了 API 且方法体缺失，不证明断言绑定行为） |
| shim 自身字段声明触发的 `ValidationError` | **1** | **强**：`..._none_is_k5_equivalent` 传 `max_tokens_per_kind=None`，shim 里该字段仍是必填 `dict`（K5 原文形态）→ 被 pydantic 拒绝。**恰好证明测试咬住「本字段必须可选」** |
| 通过 | 1 | `test_refs_reject_non_string_and_over_long_ids` —— shim 保留了 `RefId` 类型声明，故该例对 shim 无判别力；其判别力由突变 M2 证明 |

> 诚实说明：34 条 `NotImplementedError` 按约定字面（非 `ImportError`/`AttributeError`）算判据型，但它**只证明测试触达了被测 API**，不证明断言咬住了行为。真正强的证据在 B。

**B. 行为回退突变（自加，强判别力）**

从**真实实现**上逐个撤掉一条守卫，跑对应测试：

| 突变 | 撤掉什么 | 对应测试的实际失败 |
|---|---|---|
| M1 | K5-2 validator | `Failed: DID NOT RAISE ValidationError` |
| M2 | `RefId` 的类型/长度约束（退化为 `str`） | `Failed: DID NOT RAISE ValidationError` |
| M3 | 把 `tokens is None` 当作 0 | `AssertionError: assert ['ev1'] == []` |
| M4 | 不记录 `dropped_refs` | `pydantic ValidationError: 1 validation error for ContextSlice`（K5-2 守卫**抓住了** K5-1 的丢失） |
| M5 | 忽略 `max_tokens_per_kind` 分层 | `AssertionError: assert [] == ['ev2']` |
| M6 | 给 `unknown_field_policy` 静默默认值 | `Failed: DID NOT RAISE ValidationError` |
| M7 | 撤掉 K6-3 递增检查 | `Failed: DID NOT RAISE ValidationError` |
| M8 | `reject` 策略 fail open | `Failed: DID NOT RAISE UnknownFieldError` |
| M9 | 撤掉 `state_version` 的 int 版本守卫 | `Failed: DID NOT RAISE ValueError` |
| M10 | 忽略 `reserved_ratio` 预留（`usable_tokens` 改回 `max_tokens`） | `AssertionError: assert ['ev1', 'ev2'] == ['ev1']` |
| M11 | per-kind 回落值改成 0（而非全局预算） | `AssertionError: assert 0 == 80` |

**11/11 全部判据型失败，0 例 `ImportError`/`AttributeError`。** 复现（自包含，跑完自动还原，末行 `restored, focused suite: PASS (43 passed)` 即还原校验）：

```bash
python docs/tasks/M01-context/evidence/discriminating_power.py
# 实跑输出：docs/tasks/M01-context/evidence/results.txt
```
