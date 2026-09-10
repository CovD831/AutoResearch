# S2-B Audit Evidence

- ID: `S2-B-AUDIT-EVIDENCE`
- Title: `Audit evidence module: verdicts, reconciliation, candidate 回流`
- Status: `accepted`
- Status note: 2026-09-09 成员 PR #9 经 owner 按 D-S2-01 集成调整（改名/kind 分家/locator fail-closed 修复）后经 PR #10 合入主线；本文件由负责人按 D-SYNC-01 于 2026-09-09 补建。2026-09-10 O6 S2 promotion 四项核验通过 → accepted（O3/I3 收口回写账本）。
- Owner: `member B`
- Next owner: `user/team`

## Goal

完成 B3/S2 Audit Module 的 Evidence reconciliation、引用核验、locator 核验、撤稿/更正/版本状态核验、未绑定 claim 报告和 candidate 回流；in-runtime 结论只能经 `EvidenceService.admit_candidate()` 回流，不直接写 EvidenceItem。

## Acceptance scenarios

- [x] 16 个 focused 测试覆盖任务包验收矩阵 12 项（存在性/捏造/撤稿/更正可追溯/resolver 不可用 fail-closed/locator unknown 与 mismatch/未绑定 claim/in-runtime 准入/重复与冲突/standalone 无副作用/幂等与快照版本身份/确定性与方法分离）。
- [x] 全量 97 passed（`-p no:cacheprovider`，owner 本地复现 exit 0）；ruff clean（owner 复现）。
- [x] Evidence sole-writer 边界：audit 模块零处 `RecordStore.put("evidence", ...)`；`_AdmissionOnlyGateway` 测试锁定 admission-only 契约。
- [x] PR #9 经 owner 集成调整（D-S2-01）后合入主线（PR #10）。

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

- ~~等 owner 裁决后 rebase~~ → 已裁决（D-S2-01）并由 owner 完成集成（见下）。
- ~~S2 promotion/O6 验收与 accepted 标记由 owner 按全局路线判定。~~ → 2026-09-10 O6 通过，accepted。
- ~~A3 运行时与 B3 语义对齐（binding/corrected/locator）为 owner follow-up（PR #11 后续窗口）。~~ → 语义统一以 B3 严格版为准已冻结（D-S2-01），O6 promotion 窗口核验通过（108 passed），闭环。

## Owner integration record（2026-09-09，D-S2-01，PR #10）

- 裁决落地：模块改名 `src/autoresearch/audit_evidence.py`、测试 `tests/test_audit_evidence.py`、fixture `tests/fixtures/audit_evidence/`；record kind `audit_evidence_report`、事件 `audit_evidence.*`，与 A3 运行时的 `audit_report`/`audit.*` 分家。
- 集成修复：`_claim_matches_text` 空词条/空 claim 由隐式 PASS 改 UNKNOWN（fail-closed），新增 `test_vague_claim_locator_is_unknown_not_fail_open`；语义裁决以本模块严格语义为准。
- 合并验证：owner 分支全量 **105 passed**（88 主线 + 16 本模块 + 1 新增）、ruff clean、check.mjs valid。
- PR #9（97cd226）以 superseded 关闭；成员实现全部保留，仅位置/命名按裁决调整，无质量打回。

## Next step

已闭环（D-S2-01 → owner 集成 PR #10 → O6 accepted，2026-09-10）。无待办；成员 B 下一任务为 B4/S3 Reader-Writer Ports。

## Verification

- [x] `pytest tests/test_audit_module.py -q`：16 passed（owner 本地复现）。
- [x] `pytest -W error -p no:cacheprovider -q`：97 passed，exit 0（owner 本地复现）。
- [x] `ruff check src tests`：通过（owner 本地复现）。
- [x] 成员侧记录：`node .ai-team/check.mjs --json` valid、Project-to-Act `--validate` valid、`git diff --check` 通过（见分支内 `verification-report.json`，E-B3-VERIFY-20260909）。
- [x] `node .ai-team/check.mjs --base main --task .ai-team/tasks/S2-B-AUDIT-EVIDENCE.md`：本账本补建后 owner 复跑。
- [x] O6 S2 promotion（2026-09-10）：四项核验通过、全量 108 passed owner 独立复现；S2-B → accepted（registry 行与 `.ai-team/TASK.md` 2026-09-10 条目同步）。

## Handoff note

- From: `member B`（PR #9）→ owner 审查（2026-09-09）
- To: `user/team`
- Decision: **blocked**（非质量问题）：撞车与 base 落后见 Pending；模块本身贴合 B3 任务包，边界全部遵守。
- 回滚：仅移除 B3 允许路径内文件与任务目录；B1/B2 行为与共享记录不动；合并后回滚 = revert B3 merge commit。
