# S4-A Benchmark Harness

- ID: `S4-A-BENCHMARK-HARNESS`
- Title: `S4 benchmark runtime and real retrieval adapter`
- Status: `handoff`
- Status note: 两个切片均已本地 commit（检索 adapter `65ada56`+`2cca01a`；benchmark 运行时 `6829391`）。fresh 证据：98 focused（39+59）/ 244 full passed、`benchmark.py` 覆盖率 98%、ruff 绿、`check.mjs` 18/18 valid、`evidence/benchmark-report.json` 已生成、固定场景 12/12 + 端到端用户场景全绿。按用户要求**未 push、未开 PR**，故按 repo-task-sync 停在 `handoff` 而非 `done`；待 owner 裁决 D-A5-偏离-1 与晋级。
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
- **偏离/待裁决（见 `L3.md`）**：`search_service.py` 存在第二条未带凭据的 S2 代码路径（A1 `PaperSearchService` 的裸 connector），本包未改（S1 已 accepted 路径）。建议 owner 裁决是否在后续包把主链路切到 A5 adapter，或删除裸 connector。

## Completed

- 基线核对：分支从 `main@380bd49` 切出（worktree `.worktrees/s4-a-benchmark-harness`），基线全量 146 passed。
- 新增 `src/autoresearch/search_adapters.py`：`SemanticScholarSearchAdapter`、`ArxivSearchAdapter`、`OpenAlexSearchAdapter`，统一 A4 `CapabilityAdapter` 形状，transport 可注入（矩阵全离线可跑）。
- `Settings` 增加 `semantic_scholar_api_key` / `semantic_scholar_timeout_seconds` / `openalex_api_key` / `openalex_mailto` 与 `semantic_scholar_configured` 判据；`.env.example` 同步。
- 39 个 focused 测试覆盖上表全部已完成项；模块覆盖率 99%（287 stmts / 3 miss，剩余为抽象方法与真实 transport 成功路径）。
- 真实源实探（本机 2026-09-11）：OpenAlex 匿名可用（3 hits，quota 680/1000，$0.068 余量，$0.001/query）；arXiv 被限流（429）；S2 无 key fail-closed；禁网 denied。
- `src/autoresearch/benchmark.py` 新增运行时层（保留原 scoring 层不动）：三条件 `bare_llm` / `gate_off` / `gate_on` 可执行对比、`ResourceBudget` + `CallBudget`（硬停止=调用前 deny / 软停止=调用后 interrupt）、`BenchmarkRunReceipt`、`BenchmarkRunReport`、四个注入缝（agent / materials / admission / gate）。
- 冻结 fixture：`tests/fixtures/benchmark/corpus.json`（24 case，digest `1e4aa966…09b2`）与 `metric-definition.json`（digest `8f641f27…c3fe`）；`MetricDefinition.frozen=False` 加载即 `ValueError`。
- 59 个 focused 测试（含 4 个重跑命令 CLI 测试）锁定三组对比：`bare_llm` hall=1.0 / bind=0.0；`gate_off` 与 `gate_on` 草稿级 hall=0.145833、bind=0.881944 逐位相同，`gate_on` accepted_hall=0.0；机制指标 `mechanism_safety_score=100.0`，标签零错配。
- `scripts/benchmark_trust.py`（`--report` / `--live-retrieval` / `--source` / `--max-calls`），离线默认跑出 `evidence/benchmark-report.json`（144/240 calls，status=completed，0 warnings）。

## Pending

- 第四组条件（`docs/BENCHMARK.md` 的「gate 开 + recovery/replay」）留后续包；本包按 TASK-SPECS/R004-05 的三组交付（D-A5-偏离-2）。
- `docs/BENCHMARK.md` 的「四条件」与本包「三组」口径差：未改共享文档，待 owner 统一口径。
- 真实检索源现状：S2 需免费 key（申请中，审核 ~3-4 周）→ 当前 live 轨用 OpenAlex；arXiv 代码就绪但被 provider 限流。

## Next step

owner 裁决 D-A5-偏离-1（`search_service.py` 第二条裸 S2 路径）与本包晋级；随后按 repo-task-sync 的 Hand off 流程开 PR（本包因用户要求未 push/未开 PR，故停在 `handoff`）。

## Verification

- [x] `python -m pytest tests/test_search_adapters.py`（39 passed）。
- [x] `--cov=autoresearch.search_adapters`（99%，287 stmts / 3 miss）。
- [x] `python -m pytest tests/test_benchmark_runtime.py tests/test_benchmark.py`（62 passed）。
- [x] `--cov=autoresearch.benchmark`（98%，678 stmts / 14 miss；剩余 14 行全为既有 scoring 层的输入校验分支）。
- [x] `python -m pytest tests`（244 passed in 54.94s）。
- [x] `python -m ruff check src tests`（All checks passed）。
- [x] `python scripts/benchmark_trust.py --report evidence/benchmark-report.json`（status=completed，三条件 24/24/24 格）。
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/S4-A-BENCHMARK-HARNESS.md --base main`（Result: valid）。
- [x] live 轨冒烟：`python scripts/benchmark_trust.py --live-retrieval --source openalex`（真实网络 14.9s / 60 calls，硬停止正确触发 budget_exhausted）。不作晋级证据。
- [x] 固定场景 harness（`F:\AutoResearch\.workbuddy\a5-scenarios\`，未跟踪、不进 PR）：`scenario.py` 12 个编号场景全绿 —— 1-6 打检索 adapter（注册边界 / 无 key fail-closed 零网络 / 空结果确定性成功 / 429-4xx-5xx-传输中断四格终态矩阵 / 凭据只进 header / 幂等重放 + 同 id 异请求冲突）；7-12 打 benchmark 运行时（三组真跑并复现报告数字 / 唯一变量是执法 off==on / 硬停止调用数 / 硬停止 wall clock / 软停止超时且无 FAILED / run receipt 与 A4 receipt 分离 + 冻结资产 fail-closed）。
- [x] `user-scenario.py` 端到端固定字段场景：24 题 × 3 条件 = 72 格，逐格打印全部字段（含 `unsupported_claims` / `validation_verdict` / `calls`），三组汇总与 `mechanism_metrics` 与 committed `evidence/benchmark-report.json` 逐位一致（bare hall=1.000000 / off 与 on 草稿级 hall=0.145833、bind=0.881944 / on accepted_hall=0.000000 / `mechanism_safety_score=100.0` / 144 calls）。
- [x] 场景 harness 复跑方式（cwd = 本 worktree，用其 venv）：`.venv/Scripts/python.exe F:/AutoResearch/.workbuddy/a5-scenarios/scenario.py <1-12>` 与 `.venv/Scripts/python.exe F:/AutoResearch/.workbuddy/a5-scenarios/user-scenario.py`。**用户侧独立复跑才构成验收证据**；AI 侧运行仅记为 provenance。

## Handoff note

- From: `member A`
- To: `user/team`
- 代码与任务包/账本均在 `codex/s4-a-benchmark-harness`；两个切片（检索 adapter + benchmark 运行时）均已完成并本地 commit，待 owner 裁决与开 PR。
- **需 owner 补的项目级账本（本包 forbidden_paths，未改）**：`.project-to-act/PROJECT_PROGRESS.md` 当前仍记 A5 为「交付即审」（2026-09-10 快照），未反映两个切片已交付；`.project-to-act/PROJECT_OVERVIEW.md` 的「最后更新」仍是 2026-09-04。按 project-to-act skill「路线变化后立即同步」应由 owner 侧回写。
- **committed 报告的口径**：`evidence/benchmark-report.json` 是**离线**结果（冻结语料即材料库），digest 锚定在 `corpus_digest` / `metric_definition_digest`；重跑命令 `python scripts/benchmark_trust.py --report evidence/benchmark-report.json`。
- **明确局限（R004-05 要求载明）**：①作者即评测者偏差——语料与标签由本包自造，非外部标注集；②离线默认，非真实检索；③单主指标，`evidence_binding_rate` 仅报告级；④第四条件未交付。
- 检索源现状（2026-09-11 实测）：S2 需免费 key 且申请表单拒收免费邮箱 → 由公司后续申请；当前可用的真实源是 OpenAlex（§5 已授权的降级轨），arXiv 代码就绪但被 provider 限流。
- 上报记录级不一致：`docs/tasks/P1-B-evidence-lane/tasks/B5-data-sources/TASK.md:8` 把 Crossref 与 S2 混写为「Crossref S2 免费 key 主选」，且括号内「2026-02 起强制 key + 用量计费」按 ADR-01 §2/§3 实为 **OpenAlex** 的政策（Crossref polite pool 未作废）。共享文件，未改。
