# S4-A Benchmark Harness

- ID: `S4-A-BENCHMARK-HARNESS`
- Title: `S4 benchmark runtime and real retrieval adapter`
- Status: `in_progress`
- Status note: 检索 adapter 切片已完成（S2 + arXiv + OpenAlex，全部经 A4 registry 注册，39 focused / 185 full passed）；benchmark 运行时切片未开工。未 commit/push/PR。
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
- [ ] benchmark invocation 运行时（三组对比可执行，非只算分）。
- [ ] 资源预算与停止条件（超预算 → deny；单次超时 → interrupt/recovery），per-run 预算写进 receipt。
- [ ] benchmark 级 run receipt（与 A4 `CapabilityInvocationReceipt` 分开）。
- [ ] 报告 artifact `evidence/benchmark-report.json` 与重跑命令 `scripts/benchmark_trust.py`。
- [ ] 冻结语料 fixture 与冻结的 hallucination ratio 定义。

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
- **偏离/待裁决（见 `L3.md`）**：`search_service.py` 存在第二条未带凭据的 S2 代码路径（A1 `PaperSearchService` 的裸 connector），本包未改（S1 已 accepted 路径）。建议 owner 裁决是否在后续包把主链路切到 A5 adapter，或删除裸 connector。

## Completed

- 基线核对：分支从 `main@380bd49` 切出（worktree `.worktrees/s4-a-benchmark-harness`），基线全量 146 passed。
- 新增 `src/autoresearch/search_adapters.py`：`SemanticScholarSearchAdapter`、`ArxivSearchAdapter`、`OpenAlexSearchAdapter`，统一 A4 `CapabilityAdapter` 形状，transport 可注入（矩阵全离线可跑）。
- `Settings` 增加 `semantic_scholar_api_key` / `semantic_scholar_timeout_seconds` / `openalex_api_key` / `openalex_mailto` 与 `semantic_scholar_configured` 判据；`.env.example` 同步。
- 39 个 focused 测试覆盖上表全部已完成项；模块覆盖率 99%（287 stmts / 3 miss，剩余为抽象方法与真实 transport 成功路径）。
- 真实源实探（本机 2026-09-11）：OpenAlex 匿名可用（3 hits，quota 680/1000，$0.068 余量，$0.001/query）；arXiv 被限流（429）；S2 无 key fail-closed；禁网 denied。

## Pending

- benchmark 运行时切片（invocation / 预算 / 停止条件 / receipt / 报告 / 重跑命令）与冻结语料 fixture。
- `docs/BENCHMARK.md` 的「四条件」与 TASK-SPECS/R004-05 的「三组」口径差：本包按三组交付，method 维度可扩展（已登记，见 L3.md）。

## Next step

实现 `src/autoresearch/benchmark.py` 的运行时层与 `scripts/benchmark_trust.py`，把三组对比跑成可重跑报告；随后补 HANDOFF 与 PR。

## Verification

- [x] `python -m pytest tests/test_search_adapters.py`（39 passed）。
- [x] `--cov=autoresearch.search_adapters`（99%，287 stmts / 3 miss）。
- [x] `python -m pytest tests`（185 passed in 31.54s）。
- [x] `python -m ruff check src tests`（All checks passed）。
- [ ] `python scripts/benchmark_trust.py --report evidence/benchmark-report.json`（脚本未实现）。
- [ ] `node .ai-team/check.mjs --task .ai-team/tasks/S4-A-BENCHMARK-HARNESS.md --base main`（待 PR 前跑）。

## Handoff note

- From: `member A`
- To: `user/team`
- 代码与任务包/账本均在 `codex/s4-a-benchmark-harness`；检索切片已完成，benchmark 运行时切片进行中。
- 检索源现状（2026-09-11 实测）：S2 需免费 key 且申请表单拒收免费邮箱 → 由公司后续申请；当前可用的真实源是 OpenAlex（§5 已授权的降级轨），arXiv 代码就绪但被 provider 限流。
- 上报记录级不一致：`docs/tasks/P1-B-evidence-lane/tasks/B5-data-sources/TASK.md:8` 把 Crossref 与 S2 混写为「Crossref S2 免费 key 主选」，且括号内「2026-02 起强制 key + 用量计费」按 ADR-01 §2/§3 实为 **OpenAlex** 的政策（Crossref polite pool 未作废）。共享文件，未改。
