# S3-B2 Data Sources

- ID: `S3-B2-DATA-SOURCES`
- Title: `Real Crossref verification, PDF parsing, and gold-set metrics`
- Status: `integrated`
- Owner: `member B`
- Next owner: `user/team`
- Status note: 成员交付 PR #16 → owner 深审发现阻断级缺陷（撤稿判据方向反转）→ owner 代修 PR #17 合入 main（`7fdfb89`，2026-09-11）→ 独立对抗审查复核通过。docling 解析路径未验证（两 parser 均未安装），不计入验收。

## Goal

把核验数据源与论文解析从 fixture 升级为真实外部源：真实 Crossref DOI verdict（存在性/元数据/更正/撤稿，**撤稿判定读 `updated-by[]`**）、docling-first PDF 解析、ScholarQABench 口径的金集三指标；全部产物走 candidate 通道，撤稿信息经 B3 verdict 流回流。

## Acceptance scenarios

- [x] Crossref adapter 真实调用（httpx，polite pool，可注入 transport）对实时/离线 DOI 给出确定性 verdict；404=not_found、**`updated-by[]` type=retraction=本文被撤稿=`retracted`**、`updated-by[]` type=correction=`corrected`、`update-to[]` type=retraction=本文是撤稿声明=保持 `found`。
- [x] 降级链 live→snapshot→unknown；`TransportOutcome` 矩阵（rate_limited/timeout/unavailable/partial）测试锁定，不静默降级、不虚构 verdict。
- [x] `resolver_record()` 把撤稿/更正投影为 B3 素材（status + related_source_ids），复用已解析 verdict 避免二次网络调用，不直写证据。
- [x] PDF parser docling 优先、pymupdf4llm 兜底；两者不可用→`unknown` 并记**每个后端的原因**；AGPL 兜底启用留痕。
- [x] 解析产物经 `ParseEgress` 构造 `EvidenceCandidate` 并走 `admit_candidate()`，不直写 EvidenceItem（sole-writer 边界）；**无真实定位信息时 locator 留空并 fail-closed**。
- [x] gold set 三指标按 ScholarQABench 口径：`hallucination_ratio` 只计 `not_found`；传输失败单列 `undetermined_ratio`；`citation_recall` 为金标覆盖率，`citation_precision` 需 NLI attributable 判断（缺失时报 None+注明）——两者不再恒等。
- [x] 聚焦 20 passed + 全量 166 passed + ruff + check.mjs + 真实 Crossref smoke 证据见 Verification。

## Invariants

- 不新增领域角色；B5 是 evidence/domain 数据供给层。
- 任何 adapter 不得调用 `EvidenceService.add` 或 `RecordStore.put("evidence", ...)`。
- 撤稿/更正一律经 B3 `audit_evidence` verdict 流回流，adapter 只产出 resolver 素材。
- 不修改共享 `contracts.py`、`config.py`、`application.py`、storage、gates、cli/api、A 线路径（capability/capability_registry）、B3 `audit_evidence.py`、B4 `reader_writer_ports.py`、`.ai-team/TASK.md`、`.project-to-act/`。
- 真实网络仅走可注入的 httpx transport；测试用 MockTransport；不引入付费依赖、不下载 docling 权重。
- 空结果遵循 D-F8-01：确定性零命中 = `completed_empty`，不重新解释为 unknown。
- **fixture 一律录自真实 API，不得为匹配期望而编辑**（本轮返工的直接教训）。

## Decisions

- 单文件 `src/autoresearch/external_sources.py` 承载 Crossref adapter + PDF 解析 + candidate egress + gold-set 指标。
- 真实网络在本轮入 scope：live Crossref 优先，snapshot 兜底，unknown 兜底末位；Semantic Scholar/arXiv 检索归 A5（TASK-SPECS A5:58），不在 B5。
- 指标口径采用 ScholarQABench 官方定义；NLI judge 由 A5 接线，本层只消费传入判断、不跑裁判、不造假 attribution。
- 真实 DOI 只使用经 live Crossref 实测核对的记录（Nature OpenScholar + Lancet MMR 撤稿案），不编造真实 DOI。
- **D-B5-01（2026-09-11 Owner 代修）**：撤稿判定读 `updated-by[]`（本文被谁更新），`update-to[]` 表示本文是更新者（即声明本身，判 `found`）。原实现只读 `update-to[]`，导致**被撤稿论文判 `found`、撤稿声明判 `retracted`**——方向 100% 反转，B5 核心目的失效。依据：2026-09-11 真实 Crossref API 复核（`...(97)11096-0` 被撤稿原文 `update-to=null` / `updated-by=[correction, retraction]`；`...(10)60175-4` 撤稿声明 `update-to=[{type:retraction}]` / `updated-by=null`）。**任务包 TASK-SPECS B5:50 与 ADR-01 槽位 7 的原表述同错，已就地修订并加勘误**。
- **D-B5-02（2026-09-11 Owner 代修）**：`hallucination_ratio` 只计 `not_found`；`unknown`（限流/超时/不可用）单列 `undetermined_ratio`。原因：原口径把基础设施故障计入幻觉，而 A5 的评估纪律以 hallucination ratio 为唯一主指标——网络抖动会直接移动裁决依据。`citation_recall`（金标覆盖）与 `citation_precision`（NLI 支持率）分离，原实现两者同分子同分母恒等。
- **D-B5-04（2026-09-11，独立对抗审查后）**：`resolver_record()` 对 `not_found` 也返回 `None`（原仅对 `unknown` 短路）。原实现会把**不存在的 DOI 投影成 `status="current"`** 喂给 B3——把断掉的引用当作有效来源，属 fail-open。**由独立对抗审查发现；owner 两轮自查均漏报**（见 `reviews/PR16-B5-fix-review.md`）。
- **D-B5-03（2026-09-11 Owner 代修）**：pymupdf4llm 不再返回 `["docling-fallback"]` 假 locator；无定位信息时留空，由 `admit_candidate` fail-closed 拦截，定位可由调用方注入（`ParseEgress.admit(locator=...)`）。docling 解析失败原因计入 diagnostics，不再 `except Exception: return None` 静默吞掉。

## Completed

- 重写 `src/autoresearch/external_sources.py`：live Crossref（httpx）+ 离线 snapshot 兜底 + transport 矩阵 + gold-set 三指标。
- 更新 fixture 为真实 DOI（`doi_snapshot.json` + `crossref_responses.json`，基于 live 实测 payload 复现）。
- 重写 `tests/test_external_sources.py`：覆盖真实 verdict 矩阵、限流/超时/404 降级、resolver 投影、指标、candidate E2E。
- 更新 B5 任务包与成员账本，如实记录真实网络/真实 DOI/标准指标口径与本轮 scope 修正。
- **owner 代修（2026-09-11）**：撤稿判据改读 `updated-by[]`；fixture 依真实 payload 重建并区分「撤稿声明 / 被撤稿原文」两个 DOI 身份；`hallucination_ratio` 与 `undetermined_ratio` 分离、recall/precision 去重；解析层按后端记因、去除假 locator；TASK-SPECS B5:50 与 ADR-01 槽位 7 就地修订 + 勘误；测试补「被撤稿原文必须判 retracted」等断言（11 → 18 用例）。

## Pending

- 合并与 `integrated` 判定由 owner 执行（缺陷已修，待 re-verify + merge）。
- docling 权重离线预置（A7）、NLI attributable judge 接线（A5）、Crossref 真实限流策略生产化由 owner 排期。
- **docling 解析路径未验证**（两个 parser 均未安装，无真实 PDF 流过）——不得计入本包验收通过。

## Next step

Owner re-verify scope diff → merge `owner/s3-b2-integration` → 回写 registry `S3-B2-DATA-SOURCES → integrated`。

## Verification

- [x] 聚焦测试 `python -m pytest tests/test_external_sources.py -q`：`20 passed`。
- [x] 全量 `python -m pytest -o addopts="" -W error -q`：`166 passed`（main@380bd49 基线 146 + 20）。
- [x] `ruff check src tests`：`All checks passed!`。
- [x] **真实 Crossref smoke（2026-09-11，代修后复跑）**：`10.1016/S0140-6736(97)11096-0`（1998 被撤稿原文）→ `retracted`（related 含撤稿声明 `...(10)60175-4`）；`10.1016/S0140-6736(10)60175-4`（2010 撤稿声明）→ `found` + reason "this work is a retraction notice for ..."；`10.1038/s41586-025-10072-4` → `found`。resolver_record 对被撤稿原文给出 `status="retracted"`（落在 B3 识别词表内）。
  - 更正记录：原 smoke 声称「Lancet `...(10)60175-4`→`retracted`」并当作通过证据——**该结果本身即缺陷现场**（撤稿声明被误判为被撤稿），已随本次修复更正。
- [x] `node .ai-team/check.mjs --base 380bd49 --json`：`valid: true`。
- 环境注记：Python 3.13.x + 仓库内 `var/_b4_deps` 临时依赖（gitignore）；docling/pymupdf4llm 未安装；真实网络 smoke 依赖沙箱外网。

## Handoff note

- From: `member B`（原始交付）
- To: `user/team`
- Summary: **已合入 main（PR #17，`7fdfb89`）**。B5 交付真实 Crossref 核验 + docling-first 解析 + ScholarQABench 三指标 + candidate-only 回流。**owner 深度审查发现阻断级缺陷（撤稿方向反转），已代修**：判据改 `updated-by[]`、fixture 重建、指标口径分离、解析层留因去假 locator，并同步修订任务包与 ADR 原表述。回滚仅移除 B5 allowed paths 内文件；owner 代修的回滚点为 `1eec625`。
