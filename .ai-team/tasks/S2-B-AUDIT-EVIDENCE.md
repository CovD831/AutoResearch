# S2-B Audit Evidence

- ID: `S2-B-AUDIT-EVIDENCE`
- Title: `Audit evidence module: verdicts, reconciliation, candidate 回流`
- Status: `reviewing`
- Status note: PR #9，revision 97cd226；owner 判定 blocked，等布局裁决后 rebase。本文件由负责人按 D-SYNC-01 于 2026-09-09 补建（成员 PR 未带 `.ai-team/tasks/` 账本，导致 Task contract / repo-task-sync CI 失败；参照 PR #4 先例由 owner 补齐）。
- Owner: `member B`
- Next owner: `user/team`

## Goal

完成 B3/S2 Audit Module 的 Evidence reconciliation、引用核验、locator 核验、撤稿/更正/版本状态核验、未绑定 claim 报告和 candidate 回流；in-runtime 结论只能经 `EvidenceService.admit_candidate()` 回流，不直接写 EvidenceItem。

## Acceptance scenarios

- [x] 16 个 focused 测试覆盖任务包验收矩阵 12 项（存在性/捏造/撤稿/更正可追溯/resolver 不可用 fail-closed/locator unknown 与 mismatch/未绑定 claim/in-runtime 准入/重复与冲突/standalone 无副作用/幂等与快照版本身份/确定性与方法分离）。
- [x] 全量 97 passed（`-p no:cacheprovider`，owner 本地复现 exit 0）；ruff clean（owner 复现）。
- [x] Evidence sole-writer 边界：audit 模块零处 `RecordStore.put("evidence", ...)`；`_AdmissionOnlyGateway` 测试锁定 admission-only 契约。
- [ ] PR #9 合入主线（blocked，见 Pending）。

## Invariants

- Audit 不直接写 EvidenceItem、不构造 GateDecision；结论只能以 candidate 形式经 `EvidenceService.admit_candidate()` 回流。
- 不修改共享 `contracts.py`、`storage.py`、`application.py`、`gates.py`、`cli.py`、B1/B2 既有路径或 `.ai-team/TASK.md`。
- resolver/corpus 不可用 fail-closed（unknown），不把未知转换为通过。
- 不新增网络请求、真实语料、第二 Store、bus、scheduler 或业务 Agent。

## Decisions

- 确定性（deterministic）与模型辅助（model_assisted）verdict 分列存储；模型辅助 locator 冻结 0.8 置信度阈值，低于阈值一律 unknown。
- audit 幂等键 = 规范化输入 + corpus 版本 + resolver 快照版本 + mode 的内容哈希（`audit_<sha256>`），同键重放返回已存报告、不追加事件。
- audit 派生 candidate 硬编码 `grade=EvidenceGrade.E1`（符合 D-I0-01 分类归 evidence lane）；audit 下限等级政策待 owner 决策记录冻结。

## Completed

- `AuditService` + AuditVerdict/AuditReport/ResolverSnapshot/CorpusSnapshot 契约实现（`src/autoresearch/audit.py`，B3 分支）。
- 存在性/发布状态（撤稿、更正、版本关系可追溯）/locator/证据对账/未绑定 claim 五类判定与 `[未验证]` 报告。
- in-runtime candidate 回流经 `EvidenceService.admit_candidate()`，duplicate/conflict/accepted 结果可见；standalone 模式零准入副作用。
- 离线 synthetic fixture（`tests/fixtures/audit/citations.jsonl`，example.invalid + provenance 标注）与 16 个 focused 测试。
- 成员侧任务包文档：TASK-PACKAGE.md / task-package.json / L3.md / PROGRESS.md / HANDOFF.md / verification-report.json。

## Pending

- **等 owner 裁决后 rebase**：与 S2-A（PR #8，已合并 `dae10f3`）结构性撞车——allowed_paths 重叠 `src/autoresearch/audit.py`/`tests/test_audit_module.py`（add/add），双方均写 record kind `audit_report`（schema/键策略不同）；base 落后（dad4658）。S2 包拆分未分区 audit 文件命名空间，属 owner 侧任务包缺陷，非成员实现走样。
- rebase 时一并修复（owner 非阻断发现）：`_claim_matches_text` 空词条 claim 自动 pass locator（应 unknown）；并发相同 audit 重复追加 `audit.report_created` 事件（无 reservation，与 A 线各缺一半，集成时统一）；PR 标题笔误（`B3feat` → `feat(S2-B)`）。
- S2 promotion/O6 验收与 accepted 标记由 owner 按全局路线判定。

## Next step

等 owner 对 S2 audit 文件布局/record kind/语义（binding、corrected 极性、locator 模型、grade 政策）出统一裁决 → rebase 到最新 main 并改名重构 → 重新提交 PR（标题 `feat(S2-B): ...`）→ owner 复审。

## Verification

- [x] `pytest tests/test_audit_module.py -q`：16 passed（owner 本地复现）。
- [x] `pytest -W error -p no:cacheprovider -q`：97 passed，exit 0（owner 本地复现）。
- [x] `ruff check src tests`：通过（owner 本地复现）。
- [x] 成员侧记录：`node .ai-team/check.mjs --json` valid、Project-to-Act `--validate` valid、`git diff --check` 通过（见分支内 `verification-report.json`，E-B3-VERIFY-20260909）。
- [x] `node .ai-team/check.mjs --base main --task .ai-team/tasks/S2-B-AUDIT-EVIDENCE.md`：本账本补建后 owner 复跑。

## Handoff note

- From: `member B`（PR #9）→ owner 审查（2026-09-09）
- To: `user/team`
- Decision: **blocked**（非质量问题）：撞车与 base 落后见 Pending；模块本身贴合 B3 任务包，边界全部遵守。
- 回滚：仅移除 B3 允许路径内文件与任务目录；B1/B2 行为与共享记录不动；合并后回滚 = revert B3 merge commit。
