# S4-A Benchmark Harness

- ID: `S4-A-BENCHMARK-HARNESS`
- Title: `S4 benchmark runtime and real retrieval adapter`
- Status: `integrated`
- Status note: 两个切片均已本地 commit（检索 adapter `8cf0d7c`+`4488ad8`；benchmark 运行时 `30a12d1`）。分支已 rebase 到最新主线 `main@66aba64`。fresh 证据：99 focused / 全量 265 passed（rebase 后；rebase 前旧基线为 245，差 20 全部来自新基线已含的 B5 集成，本包代码未变）、`benchmark.py` 覆盖率 98%、ruff 绿、`check.mjs` 18/18 valid、`evidence/benchmark-report.json` 已生成、固定场景 12/12 + 端到端用户场景全绿。用户最新独立全量复跑为 `265 passed in 50.48s`。PR #18 已创建并停在 `handoff`；owner 深度审查发现 2 项中危指标语义缺陷，**代修已应用于 `owner/s4-a-integration`**（见 Decisions D-A5-12~15 与 Verification）。代修后全量 **271 passed**、ruff 绿、`check.mjs` valid、报告可复现（逐位一致）。第二轮 owner 补齐 TASK-SPECS 明确要求但 member 未交付的 **F9**（receipt 成本字段位预留，见 D-A5-16）：全量 **275 passed**、ruff 绿、`check.mjs` / `check_pr_contract` 双 valid；owner 分支 `owner/s4-a-integration` 已开 PR 取代 #18。 **合入**：2026-09-11 owner 集成 **PR #19** squash 合入 `8f6e7de`（取代 #18）；合入后 `main@8f6e7de` 全量 **275 passed**、ruff clean、报告逐位可复现。
- Owner: `member A`
- Next owner: `user/team`

## Goal

完成 A5/S4 Benchmark Runtime：交付可审计 benchmark harness 的运行时支持（benchmark invocation、资源预算、停止条件、结果 receipt、报告 artifact 与重跑命令），以及经 A4 `CapabilityRegistry` 注册的 **Semantic Scholar 真实检索 adapter**（ADR-01 槽位 2 主选 + arXiv 补充），为 benchmark 与 B 线试点提供真实文献数据源。不实现 ProviderLane（O12，Owner 线）。

## Acceptance scenarios

- [x] 检索 adapter 经 A4 registry 注册，不得旁路直调：注册视图不暴露 adapter 句柄，未注册能力 invoke 抛 `CapabilityNotRegisteredError`。
- [x] ADR-01 槽位 2 主选源（Semantic Scholar）以**免费 key 形态**接入；key 从 `Settings` 读取并以 header 注入，**不进 request / fingerprint / receipt**。
- [x] 无 key 时 fail-closed：在任何网络调用之前返回 `failed` 并给出可操作诊断（不静默退化为匿名共享池）。
- [x] 空结果为**确定性成功**（D-F8-01）：`completed` + 0 候选 + 明确 diagnostic，绝不写成 `unknown`。
- [x] 限流（429）为**已知失败**：查询可证明未执行 → `failed`，候选不可准入。
- [x] 5xx / 传输中断（超时、DNS、连接重置）为 `unknown`：provider 结局不可证，候选不可准入。
- [x] 默认禁网策略：`network_required` 能力在 `allow_network=False` 下 `denied` 且 adapter **零调用**。
- [x] 限流/离线矩阵七格（正常有结果 / 正常空结果 / 429 / 4xx / 传输中断 / 无凭据 / 禁网）逐格断言终态与可准入性。
- [x] 候选准入一律走 `CapabilityInvocation.admissible_candidates` / `receipt.candidates_admissible`，不直接读 `candidates`（D-S3-01 硬条款）。
- [x] 候选不携带证据评级（`grade`/`evidence_type` 为 None），R005 边界保持。
- [x] 畸形 provider 响应（非 JSON / 非对象 / 缺字段 / 非列表 / 非对象命中）一律 `failed`，不得变成通过。
- [x] 幂等重放：同 invocation_id + 同 request（pydantic 化，指纹确定）→ `replayed`，`outcome_status` 保留原始终态，provider 只被调用一次。
- [x] 限流监控（ADR-01 §5）：限流事件计数与 retry-after 提示落 diagnostics；OpenAlex 的 `X-RateLimit-*` 配额计数器进入 limit monitor，且不进 fingerprint。
- [x] benchmark invocation 运行时（三组对比可执行，非只算分）。
- [x] 资源预算与停止条件（超预算 → deny；单次超时 → interrupt/recovery），per-run 预算写进 receipt。
- [x] benchmark 级 run receipt（与 A4 `CapabilityInvocationReceipt` 分开）。
- [x] 报告 artifact `evidence/benchmark-report.json` 与重跑命令 `scripts/benchmark_trust.py`。
- [x] 冻结语料 fixture 与冻结的 hallucination ratio 定义。

## Invariants

- 不修改 `contracts.py`、`invocation_contracts.py`、`capability.py`、`capability_registry.py`、Evidence/Gate 路径、`.ai-team/TASK.md` 或 `.project-to-act/`。
- 不在本包实现 ProviderLane（O12）；LLM 计价缺失不阻塞本包 accepted。
- 主选检索源不得由本包单方面更换（ADR-01 §1 生效规则）；本包只**追加** ADR 已授权的 arXiv 补充与 §5 降级轨。
- 凭据只从 `Settings` 读，永不进入 request、fingerprint、receipt、日志或仓库。
- 检索 adapter 只 emit candidate，不写 EvidenceItem / GateDecision；一律经 A4 registry 调用。
- 失败路径不得被写成通过；空结果按 D-F8-01 记为确定性成功，不得重新引入「空结果 = unknown」。
- 不新增业务 Agent；benchmark runtime 是 Runtime 服务。

## Decisions

- **D-A5-01 检索 adapter 注册为 `candidate_only`**：检索 adapter 只产出候选、无结构化结果，正是该 tier 的语义；同时保证空结果留在成功路径（`compliant_structured` tier 会把空结果改写成 FAILED，与 D-F8-01 冲突）。
- **D-A5-02 无 key 即 fail-closed，不静默匿名**：实测匿名搜索 429（本机 2026-09-11），静默退化只会产生难解释的失败；`allow_anonymous` 仅作测试/探针逃生门，非默认。
- **D-A5-03 追加 OpenAlex 为 ADR-01 §5 降级轨**：§5 原文要求「A5 实现加限流监控与降级路径（OpenAlex 可选轨顶上）」，故本包实现 OpenAlex adapter（第三个源），**不替换主选**。
- **D-A5-04 限流监控与 receipt 分离**：限流事件计数、retry-after、provider 配额是**供应商压力**，属进程级监控面（`rate_limit_summary()`），不进 receipt；receipt 只记单次 invocation 的结局（配额提示以 diagnostic 形式随 receipt 可观测）。
- **D-A5-05 指纹确定性**：本包 request 全部 pydantic 化（`SearchAdapterRequest`），满足 D-S3-01 登记的收紧项。
- **D-A5-06 超时按源定制**：arXiv 实测成功响应 ~31s 且频繁 429，默认超时 60s；Semantic Scholar 30s。
- **D-A5-07 benchmark run receipt 与 A4 invocation receipt 分开**：一次 adapter 调用与一整轮 benchmark run 是两种量级的事实，合并会让「单次检索失败」与「整轮没跑完」无法区分。测试以禁字段清单锁定。
- **D-A5-08 硬/软停止条件语义分离**：调用数上限与 wall clock 上限在**调用前**判（`deny`，可观测 `calls_denied` + `stop_reason`）；单次调用超时在**调用后**判（`interrupt`，路由 recovery，不进 ratio）。硬停止若放到调用后，预算可被单次慢调用绕过。
- **D-A5-09 三组「唯一变量是执法」**：同一冻结语料驱动三组，`gate_off` 与 `gate_on` 的草稿级 `hallucination_ratio` / `evidence_binding_rate` 必须逐位相同；差异只在 `accepted_hallucination_ratio` 与 `acceptance_rate`。测试直接断言这两个数值相等，任何把检索/校验也塞进执法差异的改动都会被挡。
- **D-A5-10 `ConditionSummary.score` 在无可评分格时为 `None`**：不是 `0.0`。给一个没跑成的条件打 0 分会读成「这个条件最差」，而事实是「这个条件没测」。报告同时写 warning。
- **D-A5-11 运行方声明的局限必须写进报告 artifact**：`TrustBenchmarkRuntime(limitations=...)` 的每一条会原样进入 `report.warnings` 与 `receipt.notes`。起因是 `--live-retrieval`：语料每题的 `claim_evidence_map` 钉死在 fixture 材料 id（`ev-case-XXX-N`）上，而 live 候选到 admission 时 `evidence_id is None` → 被 `new_id("ev")` 铸成新 id，`_fully_bound` 因此**永远不可能满足**，`hallucination_ratio` / `evidence_binding_rate` 在所有条件下结构性固定在 1.0 / 0.0。所以 live 报告里的 `score` 不是测量值，CLI 现在把它当局限显式写进 report，而不是留一句「live 不当晋级证据」的口头约定。
- **D-A5-12（2026-09-11 owner 代修，对抗审查发现）`score` 只对【已接受】单元求均值**：原实现在全部单元上求 `accepted_hallucination_ratio` 的均值，而未被接受的单元该值恒为 `0.0`，于是**拦得越多分数越高**。实测 live 报告 `acceptance_rate=0.0` 却 `score=100.0`（同一份报告里 `false_blocks=13/14`、`mechanism_safety_score=45.83`）。现在只对已接受单元求均值；一个条件**什么都没接受时 `accepted_hallucination_ratio` 与 `score` 均为 `None`**（与 D-A5-10 同一原则）。
- **D-A5-13（2026-09-11 owner 代修）空分母的比率一律为 `None`，不是 `100.0`**：「没有该拦的案例」不等于「拦截完美」。`fail_closed_block_rate` 在 `should_block` 为空时、`false_block_rate` 在 `should_accept` 为空时均改报 `None`（**后者由独立审查复核抓出**——首轮只修了前者，自相矛盾）；`_ratio` 对「分子非零 / 分母为零」改为 fail-closed 抛错（该组合只可能来自破坏「分子取自分母自身集合」的不变式）。
- **D-A5-14（2026-09-11 owner 代修）live 局限声明扩为两条**：原声明只覆盖作者注意到的 `hall`/`bind` 两项恒定；实测 live 下 `mechanism_safety_score`（100→41.67）、`false_block_rate`（0→100）、各条件 `score` 与 `status=budget_exhausted` **同样不可解释**，却无任何 warning 覆盖。现 `LIVE_RETRIEVAL_LIMITATIONS` 第二条逐项声明，使报告不会被读成「机制在真实检索下退化」。
- **D-A5-15（2026-09-11 owner 代修）指标定义升版 1.0 → 1.1**：`metric-definition.json` 的 notes **原文即规定**「`accepted_hallucination_ratio` covers all cells and zeroes a non-accepted cell」——**根因在规格**，与 B5 同类。按冻结资产的规则升版并改语义说明；新增 `zero_claim_cells`（空草稿在 lower-is-better 下得满分，故其数量必须可见）。`corpus.json` 未动。
- **D-A5-16（2026-09-11 owner 代修）receipt 预留成本字段位（F9，TASK-SPECS 明确要求但 member 未交付）**：TASK-SPECS 的「计价衔接注记」要求「receipt 的成本字段 schema 由**本包**预留（字段位固定）」，而原实现 `BudgetUsage` / `BenchmarkRunReceipt` / `CaseRunReceipt` **无任何 `tokens` / `cost` 字段**（全文件仅 1 处 "cost"，还是 docstring 里的 "what it cost"）——O12 交付后**无处可填**，衔接必然失败。现新增 `TokenUsageSlot` / `InvocationCostSlot` 两个槽类型，**字段逐一对位 O12 的 `contracts.TokenUsage` / `contracts.InvocationCost`**（不跨分支 import：O12 交付晚于本包，硬依赖会造成加载期失败），挂在 `CaseRunReceipt`（格级）与 `BudgetUsage`（run 级）各一对。**默认 `None` = 未测得，不是 0**：本包不调用任何 provider，若默认 0 则「没有计价」会被读成「这轮免费」——与 D-A5-10/12/13 同一原则。报告在 `warnings` 里点明未填格数；**不进 `notes`**（`notes` 是调用方声明 limitations 的专属通道，须恰等于声明内容，由既有测试锁定）。
- **偏离/待裁决（见 `L3.md`）**：`search_service.py` 存在第二条未带凭据的 S2 代码路径（A1 `PaperSearchService` 的裸 connector），本包未改（S1 已 accepted 路径）。建议 owner 裁决是否在后续包把主链路切到 A5 adapter，或删除裸 connector。

## Completed

- 基线核对：分支已从 `main@66aba64` rebase（worktree `.worktrees/s4-a-benchmark-harness`）；A5 之前的主线已包含 B5 集成。
- 新增 `src/autoresearch/search_adapters.py`：`SemanticScholarSearchAdapter`、`ArxivSearchAdapter`、`OpenAlexSearchAdapter`，统一 A4 `CapabilityAdapter` 形状，transport 可注入（矩阵全离线可跑）。
- `Settings` 增加 `semantic_scholar_api_key` / `semantic_scholar_timeout_seconds` / `openalex_api_key` / `openalex_mailto` 与 `semantic_scholar_configured` 判据；`.env.example` 同步。
- 39 个 focused 测试覆盖上表全部已完成项；模块覆盖率 99%（287 stmts / 3 miss，剩余为抽象方法与真实 transport 成功路径）。
- 真实源实探（本机 2026-09-11）：OpenAlex 匿名可用（3 hits，quota 680/1000，$0.068 余量，$0.001/query）；arXiv 被限流（429）；S2 无 key fail-closed；禁网 denied。
- `src/autoresearch/benchmark.py` 新增运行时层（保留原 scoring 层不动）：三条件 `bare_llm` / `gate_off` / `gate_on` 可执行对比、`ResourceBudget` + `CallBudget`（硬停止=调用前 deny / 软停止=调用后 interrupt）、`BenchmarkRunReceipt`、`BenchmarkRunReport`、四个注入缝（agent / materials / admission / gate）。
- 冻结 fixture：`tests/fixtures/benchmark/corpus.json`（24 case，digest `1e4aa966…09b2`）与 `metric-definition.json`（definition_version 1.1，digest `01960a93…1fe7`，owner 代修升版）；`MetricDefinition.frozen=False` 加载即 `ValueError`。
- 59 个 focused 测试（含 4 个重跑命令 CLI 测试）锁定三组对比：`bare_llm` hall=1.0 / bind=0.0；`gate_off` 与 `gate_on` 草稿级 hall=0.145833、bind=0.881944 逐位相同，`gate_on` accepted_hall=0.0；机制指标 `mechanism_safety_score=100.0`，标签零错配。
- `scripts/benchmark_trust.py`（`--report` / `--live-retrieval` / `--source` / `--max-calls`），离线默认跑出 `evidence/benchmark-report.json`（144/240 calls，status=completed；member 交付时 0 warnings，owner 代修后为 1 条成本槽声明）。
- 运行方局限通道（D-A5-11）：`TrustBenchmarkRuntime(limitations=...)` → `report.warnings` / `receipt.notes`；`--live-retrieval` 用它把「live 无法绑定冻结语料」写进报告。离线路径不声明该局限（`receipt.notes` 保持为空——`notes` 是调用方专属通道）；owner 代修后离线报告额外携带 1 条**内在** warning（成本槽未填，D-A5-16），故与 member 交付时相比，除 `generated_at` / `wall_clock_seconds` 外还多出该条与新增键。

## Pending

- 第四组条件（`docs/BENCHMARK.md` 的「gate 开 + recovery/replay」）留后续包；本包按 TASK-SPECS/R004-05 的三组交付（D-A5-偏离-2）。
- `docs/BENCHMARK.md` 的「四条件」与本包「三组」口径差：未改共享文档，待 owner 统一口径。
- **F8（待裁决，2026-09-11 独立审查发现）三条件从不调用 LLM**：`TrustBenchmarkRuntime.agent` 默认 `RecordedAgent()`，CLI 不传 `agent=`，故 `bare_llm` / `gate_off` / `gate_on` 三组全部**回放冻结草稿**，一次 provider 调用都没有。这是设计意图（D-A5-09 的「唯一变量是执法」正以逐位相同为前提，docstring 已述），但**条件名 `bare_llm` 会让读者误判为真实 LLM 基线**，且 member 交付时报告 `warnings` 为空、无任何声明。待 owner 裁决：补一条声明，或仅改名。本包未改（改条件名会动冻结口径）。
- 真实检索源现状：S2 需免费 key（申请中，审核 ~3-4 周）→ 当前 live 轨用 OpenAlex；arXiv 代码就绪但被 provider 限流。

## Next step

本包**已合入**（`8f6e7de`）。剩余 owner 裁决项：① `search_service.py` 第二条裸 S2 路径（D-A5-偏离-1）；② F8「三条件从不调用 LLM 而名为 `bare_llm`」是否补声明；③ `docs/BENCHMARK.md`「四条件」与「三组」口径差。下游 S4-A2-EXPERIENCE-WIRING 可领取（registry 已回写 `integrated`）。

## Verification

- [x] `python -m pytest tests/test_search_adapters.py`（39 passed）。
- [x] `--cov=autoresearch.search_adapters`（99%，287 stmts / 3 miss）。
- [x] `python -m pytest tests/test_benchmark_runtime.py tests/test_benchmark.py`（63 passed）。
- [x] `--cov=autoresearch.benchmark`（98%，679 stmts / 14 miss；剩余 14 行全为既有 scoring 层的输入校验分支）。
- [x] `python -m pytest tests`（245 passed in 56s；**rebase 前**的旧基线 `main@380bd49`）。
- [x] Rebase 到 `main@66aba64` 后全量重跑（2026-09-11 18:2x）：`python -m pytest tests`（**265 passed in 55.99s**）。本包代码在 rebase 中逐位未变（commit hash 全部重写），增量 20 全部来自新基线已含的 B5 集成（PR #17）。**该行为 AI 侧 provenance，非用户侧验收证据。**
- [x] 基线口径提醒：本地 `main` 仍停在 `380bd49`（未随 `origin/main` 前移，rebase 是用 `origin/main` 做的）。故 `--base main` 会把 B5 的 3 个提交算进本包 diff（10 commits / 29 files），需看本包真实改动请用 `--base origin/main`（7 commits / 13 files / +5762-6）。两口径均 Result: valid。
- [x] `python -m ruff check src tests`（All checks passed）。
- [x] `python scripts/benchmark_trust.py --report evidence/benchmark-report.json`（status=completed，三条件 24/24/24 格）。
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/S4-A-BENCHMARK-HARNESS.md --base main`（Result: valid）。
- [x] live 轨冒烟：`python scripts/benchmark_trust.py --live-retrieval --source openalex`（真实网络 14.9s / 60 calls，硬停止正确触发 budget_exhausted）。不作晋级证据。
- [x] 固定场景 harness（`F:\AutoResearch\.workbuddy\a5-scenarios\`，未跟踪、不进 PR）：`scenario.py` 12 个编号场景全绿 —— 1-6 打检索 adapter（注册边界 / 无 key fail-closed 零网络 / 空结果确定性成功 / 429-4xx-5xx-传输中断四格终态矩阵 / 凭据只进 header / 幂等重放 + 同 id 异请求冲突）；7-12 打 benchmark 运行时（三组真跑并复现报告数字 / 唯一变量是执法 off==on / 硬停止调用数 / 硬停止 wall clock / 软停止超时且无 FAILED / run receipt 与 A4 receipt 分离 + 冻结资产 fail-closed）。
- [x] `user-scenario.py` 端到端固定字段场景：24 题 × 3 条件 = 72 格，逐格打印全部字段（含 `unsupported_claims` / `validation_verdict` / `calls`），三组汇总与 `mechanism_metrics` 与 committed `evidence/benchmark-report.json` 逐位一致（bare hall=1.000000 / off 与 on 草稿级 hall=0.145833、bind=0.881944 / on accepted_hall=0.000000 / `mechanism_safety_score=100.0` / 144 calls）。
- [x] 场景 harness 复跑方式（cwd = 本 worktree，用其 venv）：`.venv/Scripts/python.exe F:/AutoResearch/.workbuddy/a5-scenarios/scenario.py <1-12>` 与 `.venv/Scripts/python.exe F:/AutoResearch/.workbuddy/a5-scenarios/user-scenario.py`。**用户侧独立复跑才构成验收证据**；AI 侧运行仅记为 provenance。
- [x] **用户侧独立复跑（rebase 前，2026-09-11 15:5x，member A 机器上的同一 worktree）**：聚焦 99 passed / 全量 245 passed / 覆盖率 benchmark 98% + search_adapters 99% / `ruff check src tests` 通过 / `check.mjs` valid 18/18 / 12 场景全绿 / `user-scenario.py` 与 committed 报告逐位一致 / 离线重跑 status=completed / live 三源冒烟（openalex 3 格接受、arxiv 1 格接受、S2 零网络 fail-closed）/ 非法源名报可用源列表并退出 1。**该条中的 245 是 rebase 前旧基线。**
- [x] **用户侧最新全量复跑（2026-09-11，用户提供日志）**：使用项目 `.venv`、关闭 pytest addopts/cache 后，全量 `pytest tests` 结果为 **265 passed in 50.48s**。
- [x] **owner 代修后复验（2026-09-11）**：全量 `-W error` → **271 passed**（265 + 6 条新回归测试）；`ruff check src tests` → All checks passed；`check.mjs` → valid；`check_pr_contract` → valid。**新增 6 条测试在原版代码下全部失败、在代修版下全部通过**（判别力实测，非「怎么都过」的断言）。
- [x] **离线报告数值零影响（精确口径）**：代修后重跑 `evidence/benchmark-report.json`，所有**指标数值**（各条件 score / hall / acc_hall / bind、机制指标、usage）逐位不变；变化仅两部分：① 新增 `accepted` / `zero_claim_cells` 两键；② `metric_definition_version` 1.0→1.1 与 `metric_definition_digest` 随之更新（**因此不是逐字节相同**，此前表述过宽，已更正）。片段：`bare_llm=0.00` / `gate_off=85.42` / `gate_on=100.00`、144 calls、机制指标全部不变；报告仍逐位可复现。
- [x] **独立审查复核（2026-09-11，第二轮盲审）**：不知情子代理对代修复审，抓出 `false_block_rate` 空分母仍报 `0.0`（与 D-A5-13 自相矛盾，属同一缺陷族漏修）并已修复 + 扩测试；另指出「零影响」表述过宽（见上）。修复后全量 **271 passed**。
- [x] **live 假满分消失**：`--live-retrieval --source openalex --max-calls 30` 复跑，`gate_on` 由 `acc=0 / score=100.0` 变为 **`acc=0 / acc_hall=n/a / score=n/a`**；报告 warnings 出现第二条（机制指标局限）。
- [x] **合入后复验（2026-09-11，`main@8f6e7de`）**：全量 `-W error` → **275 passed**；`ruff check src tests` → All checks passed；报告与 committed `evidence/benchmark-report.json` 逐位一致（除时间戳）。本包**已合入**，PR #18 由 owner 集成 PR #19 取代。
- [x] **F9 补齐后复验（2026-09-11）**：全量 `-W error` → **275 passed**（271 + 4 条 F9 测试）；`ruff check src tests` → All checks passed；`check.mjs` → valid；`check_pr_contract` → valid。**4 条 F9 测试在原版代码下全部失败**（连 `InvocationCostSlot` 都 import 不到，feature 确系新增）。
- [x] **F9 的离线数值零影响**：重跑 `evidence/benchmark-report.json`，各条件 `score`（0.00 / 85.42 / 100.00）、`hall` / `acc_hall` / `bind`、机制指标、`calls_used=144` **全部逐位不变**；新增仅为 `usage.tokens` / `usage.cost`（恒 `None`）、每格 `tokens` / `cost`（恒 `None`）与 1 条 warnings。
- [x] live 局限告警（D-A5-11）实测：`--live-retrieval` 的报告 `warnings[0]` 即「live retrieval cannot bind the frozen corpus…」，离线路径 `receipt.notes` 仍为 `[]`（`notes` 为调用方专属通道），但其 `warnings` 现含 1 条内在的成本槽声明（D-A5-16）。

## Handoff note

- From: `member A`
- To: `user/team`
- 代码与任务包/账本均在 `codex/s4-a-benchmark-harness`；两个切片（检索 adapter + benchmark 运行时）均已完成并本地 commit，待 owner 裁决与开 PR。
- **Rollback boundary**：若 A5 promotion 未通过，回滚本包在 `main@66aba64` 之后的 A5 提交即可；保留主线已有 A1–A4/B5，A5 的 adapter、benchmark、fixture 和报告 artifact 可重新生成，无数据库迁移。
- **需 owner 补的项目级账本（本包 forbidden_paths，未改）**：`.project-to-act/PROJECT_PROGRESS.md` 当前仍记 A5 为「交付即审」（2026-09-10 快照），未反映两个切片已交付；`.project-to-act/PROJECT_OVERVIEW.md` 的「最后更新」仍是 2026-09-04。按 project-to-act skill「路线变化后立即同步」应由 owner 侧回写。
- **committed 报告的口径**：`evidence/benchmark-report.json` 是**离线**结果（冻结语料即材料库），digest 锚定在 `corpus_digest` / `metric_definition_digest`（**已随指标定义升版至 1.1 而更新**）；重跑命令 `python scripts/benchmark_trust.py --report evidence/benchmark-report.json`。
- **owner 代修说明**：`owner/s4-a-integration`（基于 `57cf558`）修 2 项中危 + 3 项低危，并补齐 F9（receipt 成本字段位预留，D-A5-16）。全部改动落在 `allowed_paths` 内。**未改** member 的检索适配器、语料、gate 路径与 registry 边界（`contracts.py` 等仍在 `forbidden_paths`，故成本槽**以字段对位方式预留**而非 import O12 类型）。
- **明确局限（R004-05 要求载明）**：①作者即评测者偏差——语料与标签由本包自造，非外部标注集；②离线默认，非真实检索——且 **live 轨结构上不可与离线报告相比**（语料 `claim_evidence_map` 钉在 fixture 材料 id 上，live 候选 `evidence_id is None` 由 admission 铸新 id，`_fully_bound` 永不满足 → 各条件 `hall`=1.0 / `bind`=0.0 恒定）；live 只验证检索通路，已由 D-A5-11 写进报告 warnings；③单主指标，`evidence_binding_rate` 仅报告级；④第四条件未交付。
- 检索源现状（2026-09-11 复测）：**OpenAlex 可用**（§5 已授权的降级轨，匿名可用；当日配额 312/1000、$0.001/query）；**arXiv 限流已解除**（当日实测 3 hits completed，上午曾连续 429）；S2 无 key → fail-closed（申请表单拒收免费邮箱，由公司后续申请）。
- 上报记录级不一致：`docs/tasks/P1-B-evidence-lane/tasks/B5-data-sources/TASK.md:8` 把 Crossref 与 S2 混写为「Crossref S2 免费 key 主选」，且括号内「2026-02 起强制 key + 用量计费」按 ADR-01 §2/§3 实为 **OpenAlex** 的政策（Crossref polite pool 未作废）。共享文件，未改。
