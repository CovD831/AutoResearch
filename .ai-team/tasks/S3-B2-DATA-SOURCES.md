# S3-B2 Data Sources

- ID: `S3-B2-DATA-SOURCES`
- Title: `Real Crossref verification, PDF parsing, and gold-set metrics`
- Status: `handoff`
- Owner: `member B`
- Next owner: `user/team`

## Goal

把核验数据源与论文解析从 fixture 升级为真实外部源：真实 Crossref DOI verdict（存在性/元数据/更正/撤稿）、docling-first PDF 解析、ScholarQABench 口径的金集三指标；全部产物走 candidate 通道，撤稿信息经 B3 verdict 流回流。

## Acceptance scenarios

- [x] Crossref adapter 真实调用（httpx，polite pool，可注入 transport）对实时/离线 DOI 给出确定性 verdict；404=not_found、`update-to[]` type=retraction=retracted、其他 update-to=corrected。
- [x] 降级链 live→snapshot→unknown；`TransportOutcome` 矩阵（rate_limited/timeout/unavailable/partial）测试锁定，不静默降级、不虚构 verdict。
- [x] `resolver_record()` 把撤稿/更正投影为 B3 素材（status + related_source_ids），复用已解析 verdict 避免二次网络调用，不直写证据。
- [x] PDF parser docling 优先、pymupdf4llm 兜底；两者不可用→`unknown` 并记 diagnostic；AGPL 兜底启用留痕。
- [x] 解析产物经 `ParseEgress` 构造 `EvidenceCandidate` 并走 `admit_candidate()`，不直写 EvidenceItem（sole-writer 边界）。
- [x] gold set 三指标按 ScholarQABench 口径：`hallucination_ratio`=未解析/总数；`citation_recall`/`citation_precision` 由传入的 NLI attributable 判断计算，缺失时报 None+注明。
- [x] 聚焦 11 passed + 全量 + ruff + check.mjs + Project-to-Act + 真实 Crossref smoke 证据见 Verification。

## Invariants

- 不新增领域角色；B5 是 evidence/domain 数据供给层。
- 任何 adapter 不得调用 `EvidenceService.add` 或 `RecordStore.put("evidence", ...)`。
- 撤稿/更正一律经 B3 `audit_evidence` verdict 流回流，adapter 只产出 resolver 素材。
- 不修改共享 `contracts.py`、`config.py`、`application.py`、storage、gates、cli/api、A 线路径（capability/capability_registry）、B3 `audit_evidence.py`、B4 `reader_writer_ports.py`、`.ai-team/TASK.md`、`.project-to-act/`。
- 真实网络仅走可注入的 httpx transport；测试用 MockTransport；不引入付费依赖、不下载 docling 权重。
- 空结果遵循 D-F8-01：确定性零命中 = `completed_empty`，不重新解释为 unknown。

## Decisions

- 单文件 `src/autoresearch/external_sources.py` 承载 Crossref adapter + PDF 解析 + candidate egress + gold-set 指标。
- 真实网络在本轮入 scope：live Crossref 优先，snapshot 兜底，unknown 兜底末位；Semantic Scholar/arXiv 检索归 A5（TASK-SPECS A5:58），不在 B5。
- 指标口径采用 ScholarQABench 官方定义（NLI attributable 判支持、hallucination=无法解析的引用占比）；NLI judge 由 A5 接线，本层只消费传入判断、不跑裁判、不造假 attribution。
- 真实 DOI 只使用经 live Crossref 实测核对的记录（Nature OpenScholar + Lancet MMR 撤稿案），不编造真实 DOI。

## Completed

- 重写 `src/autoresearch/external_sources.py`：live Crossref（httpx）+ 离线 snapshot 兜底 + transport 矩阵 + gold-set 三指标。
- 更新 fixture 为真实 DOI（`doi_snapshot.json` + `crossref_responses.json`，基于 live 实测 payload 复现）。
- 重写 `tests/test_external_sources.py`：11 个用例覆盖真实 verdict 矩阵、限流/超时/404 降级、resolver 投影、指标、candidate E2E。
- 更新 B5 任务包与成员账本，如实记录真实网络/真实 DOI/标准指标口径与本轮 scope 修正。

## Pending

- Owner 审查、commit、push、开 PR；`integrated`/`accepted` 由 owner 判定。
- docling 权重离线预置（A7）、NLI attributable judge 接线（A5）、Crossref 真实限流策略生产化由 owner 排期。

## Next step

Owner review scope diff → commit B5 paths → push `codex/s3-b2-data-sources` → PR against `CovD831/AutoResearch:main`。

## Verification

- [x] 聚焦测试 `python -m pytest tests/test_external_sources.py -q`：`11 passed`。
- [x] 全量 `python -m pytest -q -p no:cacheprovider`：绿色（见 PROGRESS/HANDOFF）。
- [x] `ruff check` + `ruff format --check` B5 文件：`All checks passed!`。
- [x] 真实 Crossref smoke：Native `10.1038/s41586-025-10072-4`→`found`；Lancet `10.1016/S0140-6736(10)60175-4`→`retracted`（related `10.1016/s0140-6736(97)11096-0`）；resolver_record→`retracted`。
- [x] `node .ai-team/check.mjs --base 380bd49 --json`：`valid: true`。
- [x] Project-to-Act `--check`：`configured: true, mode: managed`。
- 环境注记：Python 3.13.9 + 仓库内 `var/_b4_deps` 临时依赖（gitignore）；docling/pymupdf4llm 未安装，parser 测试断言 fail-closed unknown 或 OK；真实网络 smoke 依赖沙箱外网（已验证通）。

## Handoff note

- From: `member B`
- To: `user/team`
- Summary: B5 重做交付真实 Crossref 核验 + docling-first 解析 + ScholarQABench 三指标 + candidate-only 回流；撤稿/更正经 B3 resolver 素材。本轮 scope 已修正（Semantic Scholar 归 A5）。不提交、不推送、不开 PR；回滚仅移除 B5 allowed paths 内文件。