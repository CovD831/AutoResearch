# Task Package Registry

> # 🔴 状态源口径（2026-09-18 重设）—— **派发前必读**
>
> **本文件下方的表格是历史记录（S1–S4 / O12–O14 世代），已不再作为派发依据。**
> **当前唯一派发依据 = `docs/tasks/<MODULE>/tasks/task-package.json` 的 `status` 与 `archived_at` 字段。**
>
> ## 可派发的包（**9 个**：6 个接线/激活 + 3 个 M11 续链）
>
> ### ⚠️ 判据口径已重设（2026-09-18 第二轮）—— 旧口径可被空壳刷绿
>
> 旧判据含「`reach.py` 输出不再列出 X 模块」。**反事实已实测证伪**：
> 在 `cli.py:33` 注入一个**永不执行**的 `import autoresearch.audit_evidence  # noqa: F401` 后，
> `reach.py` 可达模块数 **44 → 45**，`audit_evidence`（894 行）从孤岛清单消失，**零生产调用**。
> 因为 `reach.py` 的图只由 `ast.Import` / `ast.ImportFrom` 构成（`reach.py:15-34`；`ast.walk` 连函数内 import 都收），
> **没有任何运行时证据**。
>
> **⇒ 新口径：判据必须是「一次真实 run 的运行时可见后果」**，静态可达性至多作附带项。
> 运行时通道已实测存在：run 记录经 `application.py:288-291` 落 store、`cli.py:155` 打印、`api.py:60` 可查；
> `WorkflowState` 已声明 `diagnostics` / `warnings` / `blockers`（`base.py:28` / `:33-40`）。
> 另注：`base.py:30-38` 注释明写 **langgraph 只保留 state schema 声明过的键、其余静默丢弃** —— 任何新 state 键都必须在 `base.py` 声明。
>
> ### A. 可派发（6 个，`status: ready`）
>
> | 包 | 承担者 | 孤岛（行数）| 接入点 | 运行时判据（观测点）|
> |---|---|---|---|---|
> | `M01-WIRE` | 成员 A | `context_assembler`(305) · `migration`(210) | `application.py` 装配路径 | run 记录 `state.diagnostics` 出现真实装配出的 slice 摘要 |
> | `M04-WIRE` | 成员 B | `outbox`(880) | `graph.py:82 release_gate`（外部发布）| store 里该幂等键的 outbox entry 数=1（`outbox.py:295`）|
> | `M08-WIRE` | **Owner** | `run_manifest`(193) | 新建 `executor.py` + `graph.py` | run 记录 `state.loop_closure` 不再恒为 `NOT_APPLICABLE`；同 run ≥2 条 RunManifest |
> | `M11-WIRE` | 成员 A | `benchmark`(1833) | CLI 评估子命令 | 子命令 stdout 含冻结语料 `corpus_id`（`benchmark.py:722`）|
> | `M13-WIRE` | **Owner** | `web_api`(1407) | `cli.py serve` | `GET /ui/panels` = 200（`web_api.py:1357`）|
> | `S3-B3-PORT-ACTIVATION` | 成员 B | `reader_writer_ports`(580) · `lane_llm_adapter`(94) | 端口层激活，native/service/llm 三轨并存 | 真实 run 返回 dict 含 `parity`；store 落 `parity_report` |
>
> **统一判据命令**（6 个 `ready` 包都带；命令用**可移植的 `python`**，成员机应能直接跑）：
> ```bash
> PYTHONPATH=src python -m pytest -q -o addopts="" -W error
> PYTHONPATH=src python -m pytest -q -o addopts="" <该包判别力测试路径>   # 唯一判据型命令
> PYTHONPATH=src python -m ruff check src tests
> PYTHONPATH=src python reviews/island-audit-2026-09-18/reach.py   # 附带项，单独不构成判据
> ```
> 若本机 `python` 缺依赖（报 `ModuleNotFoundError: No module named 'langgraph'` 或 `No module named ruff`），先跑 `python -c 'import langgraph, pytest, ruff'` 自检再重试；owner 侧沙箱无依赖，用 `/Users/abab/.workbuddy/binaries/python/envs/default/bin/python`。
>
> **统一条款（老板裁决）**：**每条判据必须绑定一条可执行命令，且该命令必须在「未接线」的基线上失败（判据型失败）。**
> 散文式判据（无命令核对）一律不成立——实测现状三条命令在未接线树上全绿，判别力为 0，故新增第 2 条判别力测试命令为唯一判据型核对。
>
> **第三轮新增字段 `discriminating_power`**（每个 ready 包）= `{ short_circuit, assertion_turns_red_at, self_proof }`。
> 判据型 vs 符号缺失型：判别力测试必须在**未接线基线**上以 `AssertionError`（判据型）失败，
> **不得**以 `ImportError` / `AttributeError` / collection error（符号缺失型）失败。各包 `allowed_paths` 已补齐其测试路径。
>
> | 包 | 判别力测试（本包 exclusive）|
> |---|---|
> | `M01-WIRE` | `tests/test_m01_wire_context.py` |
> | `M04-WIRE` | `tests/test_m04_wire_outbox.py` |
> | `M08-WIRE` | `tests/test_m08_wire_executor.py` |
> | `M11-WIRE` | `tests/test_m11_wire_benchmark_cli.py` |
> | `M13-WIRE` | `tests/test_m13_wire_serve_panels.py` |
> | `S3-B3-PORT-ACTIVATION` | `tests/test_s3b3_wire_parity.py` |
>
> **`forbidden_paths` 统一口径（registry 口径，已与 10 包 JSON 对齐）**：`contracts.py` **10 包全禁**；
> `graph.py` **仅 M04 与 M08 合法**（M04 挂在发布门、M08 新增执行节点），其余一律禁；
> `agents/base.py` **10 包全禁（无豁免）** —— `WorkflowState` 是全 lane 共享状态契约；已声明 `loop_closure` / `diagnostics` / `warnings` / `blockers`，本批 6 个 ready 包无一需要新增键（D-WIRE-04）。
>
> ### ⛔ 不可派发（4 个，`status: blocked`）—— 卡在 owner 裁决
>
> | 包 | 卡点 |
> |---|---|
> | `M02-WIRE` · `M05-WIRE` | **K8 claim 图前缀缺口**：`invalidation.py:163-164` 默认前缀 `claim_`/`gate_`，而 `knowledge.py:171-174` 的 `add_edge` 端点是 **wiki page id** ⇒ **默认路径构造即抛 K8-3 校验错**（`invalidation.py:119-124`）；**全仓无人注入自定义 `ClaimGraph`**（grep 只命中 `invalidation.py` 自身与其测试）⇒ `invalidation.propagated` 永不触发 ⇒ 判据物理不可达 |
> | `M10-WIRE` | **哪套审计引擎是正典未定**：`cli audit` 现走 `audit.py:AuditRuntime`，而 `audit_evidence`(894)/`audit_stdio`(132) 是**另一套**引擎。合并 / 废弃 / 并行未裁决 ⇒ 本包形状未定，不应以「接线」形式派发 |
> | `M14-WIRE` | **policy 层挂点未定**：egress 唯一路径是 `external_sources.py`，读路径是 knowledge search；`pii`/`licensing` 挂哪一层决定真实 `allowed_paths`（含是否触碰 `knowledge.py` 这一全局串行点）|
>
> ### 孤岛认领覆盖
>
> 新增认领 `reader_writer_ports`(580) 与 `lane_llm_adapter`(94) —— 这两个是此前 9 个包的 `islands` 字段**都未覆盖**的。
> 二者互为依赖（后者是前者在 `src/` 内的唯一引用者），故并入同一包。
>
> ### B. M11 知识库续链（3 个，`status: planned`）
>
> | 模块 | 包 | status | base_ref | 说明 |
> |---|---|---|---|---|
> | M11 知识库 | `M11-MVP-02` 候选召回管线 | `planned` | `main` | MVP-01 **已合**（`780e051` / PR #36）→ 前置已满足 |
> | M11 知识库 | `M11-MVP-03` 融合/去重/索引维护 | `planned` | `main` | 依赖 MVP-02 |
> | M11 知识库 | `M11-MVP-04` 固定回归与验收证据 | `planned` | `main` | 依赖 MVP-03 |
>
> **其余 M0x 包全部 `integrated` —— 不要重复派发**：
> `M01-CONTEXT` · `M02-PREFETCH` · `R007-L03-M04-OUTBOX` · `R007-L04-M05-RETRACTION` · `M08-01-RUN-MANIFEST` · `M13-UI` · `M11-MVP-01` · `O16-ARTIFACT-CORRECTNESS` · `S4-A4/A5/A6`
> （各包的 `integrated_at` 字段写明合并证据）
>
> ## 已归档（13 个，**不再派发**）
>
> `P1-A-runtime-lane/tasks/{A1,A3,A4,A5,A6}` · `P1-A-runtime-recovery` · `P1-B-evidence-lane/tasks/{B1,B2,B4,B5}` · `P1-B-evidence-pipeline` · `O15-GATE-SCORING` · `O17-PDF-PIPELINE`
>
> 各自的 `task-package.json` 里带 `archived_at` 与 `archived_reason`。**产物均已并入 main，或已被明确作废。**
>
> ## `status` 的语义（只有这四个）
>
> | 取值 | 含义 |
> |---|---|
> | `planned` | 依赖未满足，**不可开工** |
> | `ready` | 依赖满足，可创建 worktree（**当前无此类包**） |
> | `integrated` | 已合入 main，**不得重复派发** |
> | `archived_at` 非空 | 非派发源，仅历史保留 |
>
> ## 分发归属（2026-09-18 决定）
>
> | 承担者 | 持有模块 |
> |---|---|
> | **成员 A**（证据生产） | M01 上下文 · M05 检索/撤稿 · M06 阅读 · M07 分析 · M11 知识库 |
> | **成员 B**（证据消费） | M09 写作 · M10 审核 · M04 交付 · M14/M15 安全与可观测 |
> | **Owner** | M00 · M02 门禁 · M03 编排 · **M08 实验** · M12 经验 · M13 UI |
>
> **契约边界**：已冻结的 `EvidenceItem`。**全局串行文件**（`contracts.py` / `graph.py` / `agents/base.py` / `application.py`）归 Owner。
>
> ---

> 这是全局任务队列和集成索引，不替代任务包中的详细说明。

成员长期任务包：

- [P1-A Runtime Lane](../tasks/P1-A-runtime-lane/LANE-README.md)
- [P1-B Evidence/Domain Lane](../tasks/P1-B-evidence-lane/LANE-README.md)

两个 lane package 只包含成员 A/B 的任务序列；`I0–I4` 和 `MVP-CLOSED` 是负责人主线任务，不进入成员 ZIP。

| Task ID | Phase | Owner lane | Branch | Status | Base | Depends on | Merge after | Next package |
|---|---|---|---|---|---|---|---|---|
| P1-A-RUNTIME-RECOVERY | P1/S1 | runtime | merged via PR #2 | accepted | — | — | — | P1-A2 |
| P1-B-EVIDENCE-PIPELINE | P1/S1 | evidence/domain | merged via PR #1 | accepted | — | — | P1-A | P1-B2 |
| P1-A2-RUNTIME-HARDENING | P1/S1 | runtime | `codex/p1-a2-runtime-hardening` merged via PR #5 + owner follow-up PR #7 | accepted | P1-A | P1-A | — | S2-A |
| P1-B2-EVIDENCE-ADVERSARIAL | P1/S1 | evidence/domain | `codex/p1-evidence-adversarial` merged via PR #4 + owner follow-up | accepted | P1-B | P1-B | — | S2-B |
| S2-A-AUDIT-RUNTIME | S2 | runtime | `codex/s2-a-audit-runtime` merged via PR #8 (`dae10f3`) + owner follow-up PR #11（F-9/F-10） | accepted（O6 S2 promotion，2026-09-10：四项核验通过） | `main@6b706df`（实际 base `main@15a5490`） | S1 promotion | — | S3-A |
| S2-B-AUDIT-EVIDENCE | S2 | evidence/domain | `codex/s2-audit-evidence`（PR #9）经 owner D-S2-01 集成调整后以 PR #10 合入（`2d4029a`） | accepted（O6 S2 promotion，2026-09-10：四项核验通过） | `main@6b706df`（实际 base `main@dad4658`） | S1 promotion | — | S3-B |
| S3-A-CAPABILITY-ADAPTERS | S3 | runtime | `codex/s3-a-capability-adapters` merged via PR #12 (`f620915`) | accepted（O7 S3 promotion，2026-09-10：四项核验通过） | S2 promotion | S2 promotion | — | S3-A2 |
| S3-A2-PROVIDER-LANE | S3 | integration/lead（Owner O12，2026-09-10 重排：需参考本地 openpilot 代码故归 Owner 亲自实现；真实检索 adapter 归 A5） | `owner/provider-lane` merged via **PR #15** (`ba6fdf8`) | **integrated**（2026-09-14：owner 两轮代修（C1–C4 / P1-1~P2-2，共 8 条成员意见全部复现为真）+ 独立盲审 + 判别力实测；合并后 `main` 全量 481 passed / 0 error） | B4 accepted（LLM adapter contract）+ O7 | S3 promotion | — | S4-A |
| S3-B-READER-WRITER-PORTS | S3 | evidence/domain | `codex/s3-reader-writer-ports`（PR #13，superseded）经 owner 集成 PR #14 合入（`7b88e30`，D-SYNC-01 先例：rebase + 孤儿 map-key gate 检查 + 更名） | accepted（O7 S3 promotion，2026-09-10：四项核验通过） | S2 promotion | S2 promotion | — | S3-B2 |
| S3-B2-DATA-SOURCES | S3 | evidence/domain | `codex/s3-b2-data-sources`（PR #16，superseded）经 owner 集成 PR #17 合入（`7fdfb89`：撤稿判据改 `updated-by[]`、fixture 依真实 payload 重录、指标口径分离、解析层 fail-closed；记录见 `reviews/PR16-B5-deep-review.md` 与 `PR16-B5-fix-review.md`） | accepted（2026-09-11：owner 深审发现阻断缺陷后代修，独立对抗审查复核；聚焦 20 / 全量 166 passed） | B4 accepted + S3 promotion | S3 promotion | — | S4-B |
| S4-A-BENCHMARK-HARNESS | S4 | runtime | main | integrated（2026-09-11：owner 深审 + 代修（D-A5-12~16）+ owner 集成 **PR #19** squash 合入 `8f6e7de`，取代 #18） | S3 promotion | S3 promotion | — | S4-A2-EXPERIENCE-WIRING |
| S4-B-REAL-PILOT | S4 | evidence/domain | reserved | ready（O7 S3 promotion，2026-09-10；B6 EvoMap 交叉评审条款见 B 线 TASK-SPECS） | S3 promotion | S3 promotion | — | — |
| S4-A2-EXPERIENCE-WIRING | S4 | runtime | `owner/s4-a2-integration` merged via **PR #21** (`febd12d`)，supersedes #20 | **integrated**（2026-09-14：owner 三轮审查 + 三轮代修；1 高 + 4 中 + 1 低全部关闭；失败注入矩阵 `scripts/experience_sink_failure_matrix.py` 7/7） | A3/B3 accepted（已满足） | O7（已过） | — | — |
| S4-A3-KNOWLEDGE-VECTOR | S4 | runtime | reserved | planned（追加包 2026-09-10：sqlite-vec + bge-small 向量检索，原 O10 实现部分前移成员 A，见 A 线 TASK-SPECS A7） | A6 | — | — | — |
| O13-CAPABILITY-MANIFEST | S3 | integration/lead（Owner 亲自实施，2026-09-11：定性为 O 线变更——改写冻结 L2 §CapabilityManifest，成员包不得单方面改写） | `owner/o13-capability-manifest` merged via **PR #22** (`ac782d1`)，基于 `main@60a9ea4` | **integrated**（2026-09-14：owner 独立盲审后自修——修 D-O13-10（契约必备字段 `entrypoint`/`evidence_mode` 从未被校验，3 个 built-in 全未声明）；D-O13-11 判定为虚警并回退（空候选是 `D-F8-01` 的确定性终态成功）；D-O13-07/D-O13-08 两处偏离经 owner 批准按实现为准） | `main@1e7e196` | S3-A accepted（已满足） | — | O14-CAPABILITY-CATALOG |
| O14-CAPABILITY-CATALOG | S3 | integration/lead | reserved | planned（注册目录 + 内置多选；依赖 O13；首批仅 `paper_search` 单槽，含 PLAN §2.8 可插拔判据 P1–P5） | O13 | — | — | — |
| S4-A4-MAINLINE-ADAPTER | S4 | integration/lead（Owner 亲自实施，2026-09-14：执行 `D-A5-偏离-1` 选项 (a)，触及 `application.py` / `search_service.py` 等 A5 禁区文件） | `owner/s4-runtime-retrieval-integration` merged via **PR #23** (`b5853bd`) | **integrated**（2026-09-16：squash 合入 `main@b5853bd`。合并后 `main` 实测 **587 passed / 2 skipped**；四门全绿。成员 A 独立复核「未发现新引入回归」，其三项流程闭合要求已由 owner 在 `4eecd33` 补齐） | `main@04ce9a9` | S4-A-BENCHMARK-HARNESS integrated（已满足） | — | S4-A5-HANDOFF-BY-REFERENCE |
| S4-A5-HANDOFF-BY-REFERENCE | S4 | integration/lead（Owner 亲自实施，2026-09-14：改写冻结的 `contracts.py` HandoffEnvelope 语义，成员包不得单方面改写） | `owner/s4-runtime-retrieval-integration` merged via **PR #23** (`b5853bd`) | **integrated**（2026-09-16：交接单由内容承载改为引用界；包级快照 `b7635d7` 532 passed，判别力 4 判据型。其中 3 条为符号缺失型，已在报告里如实标注） | `owner/a8-mainline-adapter`（A8） | S4-A4-MAINLINE-ADAPTER（已满足） | — | A10 |
| S4-A6-BIBLIOGRAPHIC-CLAIM | S4 | integration/lead（Owner 亲自实施，2026-09-14：处置第二轮独立盲审的 F4/N1，触及 `capability.py` / `invocation_contracts.py` 等 A8/A9 禁区） | `owner/s4-runtime-retrieval-integration` merged via **PR #23** (`b5853bd`) | **integrated**（2026-09-16：共享书目写入函数 + claim 只描述实际材料 + 不可归属命中拒绝铸 E1 + `receipt.provider_failure`；包级快照 548 passed，判别力两轮 11 判据型。未闭合项 10 条见 `reviews/A8-A9-ADVERSARIAL-REVIEW.md`） | `owner/a8-mainline-adapter`（A9） | S4-A5-HANDOFF-BY-REFERENCE（已满足） | — | S4-A3-KNOWLEDGE-VECTOR |
| I0-SHARED-CONTRACT-INTEGRATION | MVP | integration/lead | `main` | integrated | P1-A + P1-B | P1-A, P1-B | I1 | — |
| I1-PIPELINE-ORCHESTRATION | MVP | integration/lead | `main` | integrated | I0 | I0 | I2 | — |
| I2-MAINLINE-E2E-AND-PROMOTION | MVP | integration/lead | `main` | integrated | I1 | I1 | I3 | — |
| I3-PROJECT-LEDGER-CLOSURE | MVP | integration/lead | `main` | integrated（首轮收口 2026-09-10：S2-A/S2-B 账本 accepted 对齐、演进协议 D-EVOL-01 Decisions 归档、Project-to-Act 阶段回写、check.mjs 全绿；最终 accepted 判定挂 O4/MVP-CLOSED 条件 5） | I2 | I2 | I4 | — |
| I4-MANUSCRIPT-DELIVERY-CHECK | MVP | integration/lead | `main` | planned | I3 + S4-B | I3, S4-B | MVP-CLOSED | — |
| MVP-CLOSED-MINIMAL-E2E | MVP | integration/lead | `main` | waiting-for-gate | A/B + I0-I4 | all MVP rows | — | — |

## 状态定义

- `planned`：只有路线和目标。
- `waiting-for-gate`：可以准备，不可正式实现或合并。
- `ready-next`：当前任务完成后可立即领取。
- `ready`：依赖满足，可以创建 worktree。
- `active`：成员正在实施。
- `submitted` / `reviewing`：已提交，等待负责人审查。
- `integrated`：已合并到主线。
- `accepted`：完成阶段验收并有新鲜证据。
- `speculative`：接口冻结后的隔离预研，不得进入主线。

## MVP 闭环定义

`MVP-CLOSED-MINIMAL-E2E` 不是成员任务包，而是负责人最终验收项。只有以下条件全部满足，才能将其标记为 `accepted`：

1. A 线任务和 B 线任务均已 `accepted`；
2. `I0–I1` 完成共享合同、application 组装和 pipeline 编排；
3. `I2` 在合并后的主线上跑通一条最小 Evaluation Section 场景；
4. Paper Search、Evidence、材料就绪、BenchmarkPlan、SectionDraft、RuleValidation 的状态和证据可追溯；
5. `I3` 完成 Project-to-Act、task ledger、artifact 和验收证据收口；
6. `I4` 完成最小 manuscript/local delivery 检查，未执行结果、unknown 和缺失材料没有被写成已完成事实；
7. 所有 blocking findings、失败路径和回滚边界均有处理记录。

MVP 闭环完成后，仍允许存在生产化、性能、多论文类型、多 venue、完整 UI 和长期知识库等优化 backlog；这些不应阻塞最小端到端 MVP，除非它们违反可信边界。

## 更新规则

1. 成员只更新自己任务的 task-local ledger 和任务包。
2. 负责人更新本表、`.ai-team/TASK.md` 和 Project-to-Act 的阶段状态。
3. 状态变化必须带证据路径或命令。
4. ZIP 是分发载体；解压后的任务包源文件必须进入成员分支并与代码一起交接。
