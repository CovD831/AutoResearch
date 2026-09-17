# M02 Prefetch（L-02 lane 账本）

- ID: `M02-PREFETCH`
- Title: `R-007 L-02：证据前置检索 PrefetchRecord（K7）+ 失效传播 InvalidationPropagation（K8）`
- Status: `handoff`
- Status note: 2026-09-15 L-02 lane worktree（`feat/r007-l02-prefetch`，base `main@8dd8780`）。K7-2 / K7-3 / K8 全部实现并自测；K7-1 按 L2 §K7 的 B1 修正**只做代码结构层补偿、不写通过断言**。K1 `run_id` 以 **duck-typing** 接线（L-05 的 `run_manifest.py` 已落地但仍是其分支上的 untracked 文件、不在 main → import 会让本分支不可导入）。K8 传播拆出 `plan()`/`record()` 两步接缝（D-L02-10，L-04 写前校验需求），`propagate()` 对外行为不变。自查另修两处：跨分区误传播（D-L02-09）、突变残留在 live worktree 停留（D-L02-11，已改为隔离副本内做突变）。**交付态已还原并核验**：`50 passed` / `587 passed, 2 skipped` / ruff clean / 残留扫描 0。
本包对既有文件零改动（全部新增）。
**提交状态：已 commit `fb81880`、已 push 分支 `feat/r007-l02-prefetch`、已开 PR #28**
（此前本行写「尚未 commit、未 push、未开 PR」，是提交前的历史状态）。
- Owner: `impl-l02-prefetch`
- Next owner: `team-lead`

Next owner action: 决定是否提交本包 / 是否等 K1 一并接线 / 是否给 L-02 加独立审计。

## Goal

把 R-007 L2 的 K7（`PrefetchRecord`）与 K8（`InvalidationPropagation`）从契约落成可运行、可自测的库层模块：L2+ 动作有唯一的前置门禁入口并留下证据前置事实；证据失效（撤稿/过期/伪造/绕付费墙/未批准外发）能沿依赖图传播到 claim 与 Gate，其中永久性失效不可豁免、空传播必须报错。

**本包不做**：不实现 R-006 C8 `RecallAuditRecord`；不碰 `knowledge.py` / `storage.py` / `contracts.py` / `evidence.py` / `gates.py`；不重写 B5 的撤稿判据；不做上层接线（application / api / cli）。

## Acceptance scenarios

- [x] **K7-2 fail-closed**：缺证据时 `decision="blocked"`；且模型层禁止「`proceed` 但无 bundle / 无候选」与「`blocked` 却带 bundle」。
- [x] **K7-3 外键**：`final_bundle_id` 指向不存在的 bundle → 抛 `MissingBundleError`，且该记录**不落库**。
- [x] **K7-1 补偿**：L2+ 动作只能走 `execute_l2_action()`；L0/L1 调它被拒；记录先写、动作签名必须接收该记录；`blocked` 时动作不执行。
- [x] **K8-1**：`forged` / `paywall_bypass` / `unapproved_egress` 必须 `permanent_block`（枚举映射表 + validator 双层）。
- [x] **K8-2**：证据 → claim → Gate 两跳传播，落库并写审计事件。
- [x] **K8-3**：`affected_claims=[]` **报错**（不是静默返回空）；服务层抛 `BrokenPropagationError`，模型层抛 `ValidationError`。
- [x] **负例 N-1..N-4** 逐条断言（见 Decisions）。
- [x] **运行标识引用 K1、不自造**：`write_prefetch_for_run(manifest, ...)` 只读 `manifest.run_id`；模块不 import `run_manifest`（AST 断言）、不产生 `new_id("run")`（AST 断言）。
- [x] 离线可重跑；`-W error` 下零告警。
- [x] **单写入点守卫抗非字面形态绕过**：主守卫为运行期行为判据（A+C），#1/#2/#4 三种绕过**每条跑全量**均开火；**#3 跨模块写入仍漏**，已如实登记为未闭合项（需存储层不变量）。

## Invariants

- `evidence_prefetch.py` 内写 `prefetch_record` 的调用点**恰好一处**（AST 断言 `test_write_path_has_exactly_one_call_site`）。这是 K7-1 补偿机制的结构守护，**不是** K7-1 的通过断言。
- 本包**不生成**运行标识：`PrefetchRecord.run_id` 默认 `None`，取值只能来自 K1 的 `RunManifest.run_id`（`write_prefetch_for_run` 读入）；**不 import** `run_manifest`（保持本分支可独立导入）。
- K8 的 `reason` 只能来自 `InvalidationReason` 五个值；撤稿判据来自 B5 `SourceStatus`，本模块不解析 Crossref。
- 失效传播**先校验后落库**：不变量不成立时不留任何半成品记录（`test_n4_broken_chain_raises_instead_of_returning_nothing` 断言 store 为空）。
- 对既有文件**零改动**（`git status` 可证：只有新增文件）→ 既有 537 条断言零影响。

## Decisions

- **D-L02-01**：`PrefetchRecord` 增 `run_id: str | None = None`（契约未列）。依据派单表 §2「必须引用 K1 的 `run_id`」。可选、不生成值、无语义副作用 —— 属类型对齐。
- **D-L02-02**：K7-3 外键源是**注入的** `BundleRegistry`。实测全仓无 `EvidenceBundle` 持久化写入方（`grep -rn EvidenceBundle src` = 1 处，仅 `contracts.py:255` 定义）。默认 `StoreBundleRegistry` 读 `evidence_bundle` kind；无数据时**答 False → 报错**（fail-closed），不是静默通过。
- **D-L02-03**：`affected_gates` **允许为空**（K8-3 只硬约束 claims）。强判 gates 非空会造出新假绿。
- **D-L02-04**：**不与 `KnowledgeService.retrieve()` 接线**。`retrieve()` 的签名在 L-06 MVP-02/03 会被改；接线会造语义耦合（本项目三次栽在「文件不重叠但语义耦合」）。本包只吃 `list[str]` 候选 ID。
- **D-L02-05**：不为 `forged` / `paywall_bypass` / `unapproved_egress` 造自动判据（归属 L-09 / L-04）；本包只负责「给了 reason 就必须守 K8-1」。
- **D-L02-06**：**不禁止** `retracted`/`expired` 使用 `permanent_block`。K8-1 只单向要求；反向禁止属过度约束，且过度阻断是 fail-closed 方向。若 owner 要严格双向，改一行 `PERMANENT_BLOCK_REASONS` 用法即可。
- **D-L02-07（部分闭合）**：**K1 `run_id` 已接线，用 duck-typing 而非 import**。开工时 `../r007-l05-execution/src/autoresearch/run_manifest.py` 不存在；收尾复测时 L-05 已落地该文件（8768 bytes，docstring 第 10 行明文要求 L-02 引用 `RunManifest.run_id`），但它是 **L-05 分支上的 untracked 文件**（不在 main）→ **import 会让本分支不可导入**（R-006 栽过的 stacked 分支故障）。故新增 `write_prefetch_for_run(manifest, ...)`，只读 `.run_id`，零 import 耦合，stub manifest 测试已过。**未闭合部分**：尚未用真实 `RunManifest` 跑端到端。
- **D-L02-08**：本包改动 2 源文件 + 2 测试文件、**含新逻辑分支** → 标「**待独立审计**」。
- **D-L02-09（自查实测到的真实缺陷）**：`StoreClaimGraph` 原先无作用域限定，`store.list("graph_edge")` 跨全部分区取边 → **一个分区的失效会命中另一分区的 claim**。实测 `affected_claims = ['claim_A', 'claim_B']`（A 在 `papers`、B 在 `experiences`），而 `permanent_block` 落到无辜 claim 上**不可恢复**。修法：`InvalidationService(..., partitions=[...])` 作用域参数 + 1 条作用域测试。**K8 无 project/partition 字段，作用域只能由调用方给出 → 生产接线必须传，已登记为未闭合项。**
- **D-L02-10（接缝：`plan()` / `record()` 两步）**：L-04 的 `K8InvalidationAdapter` 需要在**写前**校验 blast radius。原 `propagate` 是「推导 + 落库 + 审计」一体 → 事后拒绝时错的事实已落库、审计事件也落了（L-04 在合并树实测多出一条 `invalidation_propagation`）。若不拆，调用方只能伸手进 `service.graph` 自己再遍历一次 —— 正是本项目屡栽的跨 lane 语义耦合。已新增 `plan()`（纯推导、零副作用）/ `record(plan)`（落库 + 审计），**`propagate()` 保留为 `record(plan(...))` 简写，对外行为逐字不变**。附带代价：`record()` 成为可公开调用 → 必须自守 `append_event` 的非幂等（A6 D-A6-07 实证过审计事件翻倍），已加幂等守卫 + 判据型测试（M7）。
- **D-L02-11（流程失效：突变残留在 live worktree 内停留）**：见下节「流程失效登记」。
- **D-L02-12（K8 幂等键：契约空白，只给机制不定策略）**：K8 字段表没有幂等键，`propagation_id` 每次 `plan()` 新铸 → **重试路径必然换键**，「同一 evidence 重复失效是否折叠」契约未规定。本包新增**可选** `propagation_id`（不传=现状；传了=调用方自定身份），`record()` 的幂等守卫随之生效；**不做确定性派生**（会改 K8 的 id 语义，属契约修订）。同时 `record()` 的冲突判据改为**排除 `created_at`** 的事实比较 —— 这是**本包新写的 `test_a_caller_supplied_identity_folds_a_retry_onto_one_record` 第一次跑就红**抓出来的：原判据比全量 payload，而重试必然带新时间戳 → 合法重试被当成冲突（fail-closed 方向挡住合法功能）。折叠时返回**已落库的那条**。**需 owner 裁决**。
- **D-L02-13（主守卫从 AST 换成运行期行为判据；AST 降级为辅助）**：falsify-r007 的 R3 证明原 AST 守卫**只匹配一种字面语法形状** —— `getattr(self.store,"put")(...)`、模块级别名 `_PUT = RecordStore.put`、绑定别名、`transaction()+_write_record` **全部绕过它**，且全量套件**零检出**（本包复现：一次入口调用落库 **2 条** `prefetch_record`）。修法：新增 `test_prefetch_is_written_exactly_once_per_entry_call`（A=`store.put` 打桩计数 + C=**不加 partition 过滤**的落库条数），AST 守卫保留作廉价首线并在 docstring **写明已实测局限**。**A、C 必须合用**：实测「带 partition 过滤的计数」（B）会漏掉省略 `partition=` 的写入 —— 我最初打算交付的恰是 B，是 falsify 要求「先预跑四种形态」才发现的。四项绕过验收见 Verification。

## 流程失效登记（D-L02-11：突变残留在 live worktree 内停留）

- **事实**：2026-09-15 我在 **live worktree 内**做 M7（`record()` 幂等守卫）突变时被消息打断，`if False:` 残留未还原；team-lead 观察到 `1 failed`，且该状态**被合并预演读到**（`1 failed, 896 passed`）。
- **归属**：**我的残留、我的责任**。**不是别的成员写我的 worktree** —— 那是我自己为 M7 取证而应用的突变。M1–M6 的「应用 → 跑 → 还原 → `shasum -c`」循环每次都核验通过；M7 停在「已应用、已跑出判据型失败」这一步。**本轮无任何跨成员写入。**
- **要分开的两种缺陷**：(a)「成员自己的突变纪律失效」——本轮**不是**（循环本身是对的）；(b)「**在共享、且被并发读取的 live worktree 内做突变**」——本轮**是这个**。突变循环在 live tree 内**时序不安全**：只要有人在「应用」与「还原」之间读这棵树，就必然读到中间态。
- **修法（已落地）**：突变不再在 live worktree 内进行。改为 `cp -R src tests /tmp/l02iso`，在**隔离副本**内突变/跑测/还原。M7/M8 已按此法重跑取证，**live tree 的 hash（`9a8ecaf4…`）全程不变**（`shasum -c` 核验）。
- **为什么 lint / `-W error` 抓不住**：`if False:` 短路的是一个「查询了但没用」的变量，`ruff` F841 只报**未赋值**变量，不报「查询了却没用」。抓住它的是**恰好守在该代码路径上的判据型测试** + team-lead 的跨 worktree 扫描。
- **对 team-lead 新硬检查的贡献**：已跑全 worktree 残留扫描，结果见 Verification。

## Completed

1. `src/autoresearch/evidence_prefetch.py` —— K7 全部（含 L2+ 唯一入口、单写入点、K1 duck-typing 接线）。
2. `src/autoresearch/invalidation.py` —— K8 全部（枚举映射表 + 两跳遍历 + B5 reason 复用 + `plan`/`record` 接缝 + 作用域参数）。
3. `tests/test_m02_prefetch.py`（16 条，含 R3 运行期主守卫）、`tests/test_m02_invalidation.py`（34 条，含参数化展开）。
4. `docs/tasks/M02-prefetch/tasks/L3.md`（完整 L3）、`task-package.json`、本账本。
5. 判别力：**10 条变异实测**（M1–M10，全部判据型；见 Verification）。

## Pending

| # | 项 | 阻塞方 | 说明 |
|---|---|---|---|
| 1 | 用**真实** `RunManifest` 跑一次端到端 | L-05 把 `run_manifest.py` 提交并合入 main | **duck-typed 接线已实现**（`write_prefetch_for_run` + stub 测试通过）；仅缺真实类型的一次实测 |
| 2 | D-L02-04 的 `retrieve()` 口径确认 | owner 合并 L-06 后 | 本包未接线，需 owner 裁决是否要在合并后接线 |
| 3 | **`InvalidationService(..., partitions=[...])` 必须由接线方传入**（D-L02-09） | 接线方 | **未闭合**：不传则跨分区误传播（实测可命中另一分区的 claim） |
| 4 | **K8 幂等键（契约空白）需 owner 裁决**（D-L02-12） | **owner** | **未闭合**：K8 字段表无幂等键，`propagation_id` 每轮新铸 → 重试不折叠。本包已给机制（可选 `propagation_id`），①②方向属边界修订、不在 L-02 权限内 |
| 5 | 生产触发通路（application / api / cli） | 不在本包排他文件 | 有意不做，交 owner |

## Next step

owner 决定：(a) 是否提交本包；(b) 是否等 L-05 的 K1 一并接线 `run_id`；(c) 是否给 L-02 加独立审计（本包含新逻辑分支）。

## Verification

**命令与数字（本 worktree 实测，2026-09-15）**

```
$ PYTHONPATH=src python -m pytest tests/test_m02_*.py -q -o addopts="" -W error
50 passed in 0.62s

$ PYTHONPATH=src python -m pytest -q -o addopts="" -W error
587 passed, 2 skipped in 22.88s          # 基线 537 passed / 2 skipped / 0 failed → 不下降

$ python -m ruff check src tests
All checks passed!

$ python -m compileall -q src
OK

$ grep -rnE "if False:|and False:|MUTATION|MUTATED" src/ tests/test_*.py
（0 命中）

# 交付态 hash（供合并树核验，比记忆更可靠）
391644fe76d87c730f2c5b34a73b3328302ff00737325fee93e45dc16e096d03  src/autoresearch/invalidation.py
b44489f79a1d67362dce62bea6c907dbf188dc632b55afded7b68f0687db73c9  src/autoresearch/evidence_prefetch.py
6b15a53f8b828f01065fd57adeafc0546bfe7f3d48c789be6b773fe6533cb394  tests/test_m02_invalidation.py
294988aae3dcca73d0e333915a93cd8be259f4453198127b38fe22702a7f90b5  tests/test_m02_prefetch.py

$ # 全 worktree 突变残留扫描（team-lead 新增硬检查的首次执行）
r007-l01-context : residue_hits=0
r007-l02-prefetch : residue_hits=0
r007-l03-outbox : residue_hits=0
r007-l04-retraction : residue_hits=0
r007-l05-execution : residue_hits=3   ← 全部在 tests/fixtures/run_manifest/probe_discriminating_power.py
r007-l08-ui : residue_hits=0
r007-l09-security : residue_hits=0
```

> **L-05 的 3 个命中不是残留**：`tests/fixtures/run_manifest/probe_discriminating_power.py` 是一个**突变探针 fixture**，把突变模式**声明为字符串数据**（含 `'        if False:\n'`）再应用到**临时副本**上。文件名不以 `test_` 开头 → pytest 不收集 → 不是产品代码、不是残留。**建议扫描时排除 `tests/fixtures/**` 下的探针脚本**，否则该硬检查会永久假阳性。

**R3 补丁的四项绕过验收（每条跑全量，非聚焦跑）** —— 合并树副本（`/tmp/falsify-r007/xtest` 的复制品，原树未改），基线 **907 passed / 2 skipped / 0 failed**：

| # | 绕过后全量 | 失败测试 | 判定 |
|---|---|---|---|
| #1 `getattr`+partition | 1 failed, 906 passed | `test_prefetch_is_written_exactly_once_per_entry_call` | ✅ 开火 |
| #2 模块级别名 `_PUT = RecordStore.put` | 1 failed, 906 passed | 同上 | ✅ 开火 |
| #4 `transaction()`+`_write_record` | 1 failed, 906 passed | 同上 | ✅ 开火 |
| **#3 跨模块**（`context_assembler.py` 的 `HandoffReplayService.by_run`） | **907 passed / 0 failed** | **无** | ❌ **漏（已声明边界，如实报）** |

#3 行为求证：该写入**真的落库**（一次 `by_run` → 1 条 `prefetch_record`），且 `by_run` 被 `tests/test_m01_context_assembler.py` 执行 → **不是没跑到，是真没发现**，主辅守卫双双静默。守它需要存储层不变量（`storage.py`，非本包排他文件）→ 未闭合项 #6。

**判别力（变异实测；新文件在 base 上是符号缺失型失败，故不计入，改用变异建立）**

| # | 摘掉什么 | 失败测试 | 失败类型 |
|---|---|---|---|
| M1 | K8-1 validator 的「永久 reason ⟹ permanent_block」检查 | `test_n3_permanent_reason_with_recompute_is_rejected[forged / paywall_bypass / unapproved_egress]`（3 条） | **判据型** `DID NOT RAISE ValidationError` |
| M2 | K8-3 模型层 validator | `test_n4_empty_affected_claims_raises_on_the_model` | **判据型** `DID NOT RAISE ValidationError` |
| M3 | K7-2 模型层「proceed ⟹ bundle+候选」检查 | `test_proceed_without_bundle_is_rejected_by_the_model`、`test_proceed_with_no_candidates_is_rejected_by_the_model`（2 条） | **判据型** `DID NOT RAISE ValidationError` |
| M4 | K7-3 外键校验调用 | `test_n2_final_bundle_id_must_resolve_to_an_existing_bundle`、`test_rejected_bundle_is_not_persisted`（2 条） | **判据型** `DID NOT RAISE MissingBundleError` |
| M5 | K8-3 服务层早失败 | `test_n4_broken_chain_raises_instead_of_returning_nothing`、`test_gate_ids_are_not_mistaken_for_claims`（2 条） | **判据型** 抛的是模型层 `ValidationError` 而非 `BrokenPropagationError` |
| M6 | —（反向：**新增**第二条 `store.put("prefetch_record"...)` 写入点） | `test_write_path_has_exactly_one_call_site` | **判据型** `expected one prefetch write site, found 2` |
| M7 | `record()` 幂等守卫（新接缝） | `test_recording_the_same_plan_twice_does_not_duplicate_audit_events` | **判据型** `assert 2 == 1`（重复审计事件） |
| M8 | `plan()` 的 K8-3 早失败（新接缝） | `test_plan_refuses_a_broken_chain_before_anything_is_written` + 2 条既有 | **判据型** 抛 `ValidationError` 而非 `BrokenPropagationError` |
| M9 | `plan()` 对调用方 `propagation_id` 的采纳 | `test_a_caller_supplied_identity_folds_a_retry_onto_one_record` + 2 条 | **判据型** 折叠失效 |
| M10 | `VOLATILE_FIELDS` 排除 `created_at` | 同 2 条 | **判据型** 抛 `InvalidationContractError`（合法重试被当冲突） |

**八条全部判据型**。M1–M6 在 live tree 内做完即还原并核验（见 D-L02-11 对 M7 的登记）；**M7/M8 在隔离副本 `/tmp/l02iso` 内进行，live tree 全程未变**。表内容为**声明式记录**（与 L-05 的探针 fixture 同思路），实际执行是一次性的、不留脚本。

全部变异均为**符号存在条件下的判据型失败**（无 `ImportError` / `AttributeError`）。还原后逐条 `shasum -a 256 -c` 核验，`grep -rn "MUTATION\|MUTATED\|if False:" src/ tests/` = **0 命中**。

**M5 的诚实注记（负向结论优先）**：摘掉服务层早失败后，空传播**仍然被模型层拦住**（照样抛错、照样不落库）——即 M5 的失败是「异常类型不对」，**不是**「静默通过」。也就是说 K8-3 的两层守卫在 fail-closed 方向上是**部分冗余**的；服务层早失败买到的主要是**诊断**（指明是哪个失效源、走的是哪条链）。**安全性质由模型层独立守住**，这一点必须如实说明，不能把两层守卫说成两层独立防线。

## Handoff note

1. **K7-1 绝对不能写成「已校验」**。L2 §K7 的 B1 修正已把第 1 条降为时序型（架构意图）。本包的补偿是 `execute_l2_action()` 的结构（入口唯一 + 记录先写 + 动作签名携带记录 + blocked 短路）。**剩余不可证明的部分**：别的模块仍可绕过本入口直接做 L2+ 动作 —— 本包**没有**、也**无法**阻止它，且**没有**为它写通过断言。任何把它表述为「validator 通过了 K7-1」的说法都是假绿。
2. `test_write_path_has_exactly_one_call_site` 的 AST 判据只看 `store.put(PREFETCH_RECORD_KIND, ...)` 这种**字面第一参数**形式。若有人把 kind 存进变量再 `put`，该断言会漏报 —— 已知局限，非机械完备。
3. **「唯一入口」的准确含义**：`execute_l2_action()` 是唯一**驱动动作**的入口；`write_prefetch()` 层级无关，所以 L2+ 记录**仍可由别处写入**。不要读成「L2+ 记录只可能由该入口产生」。
4. **`InvalidationService` 必须传 `partitions=[...]`**（D-L02-09）。不传时遍历跨全部分区 —— 实测一个分区的失效会命中另一分区的 claim，而 `permanent_block` 不可恢复。默认值 `None` 为兼容性保留，**不是安全默认**。
5. `StoreClaimGraph` 用 **id 前缀**（`claim_` / `gate_`）推断节点种类，因为 R-007 的图节点没有 kind 列。**这是启发式**：claim id 不遵循前缀约定的仓库必须注入自己的 `ClaimGraph`。
6. `StoreBundleRegistry` 当前对**任何** id 都答 `False`（仓库无 bundle 写入方）→ 现在任何带 bundle 的 K7-3 校验都会失败。这不是缺陷而是事实的诚实反映；接线时要换成真实注册表（D-L02-02）。
7. 本包**未 commit / 未 push / 未开 PR**，对既有文件零改动。回退 = 删除 4 个新文件 + 2 个新目录。
