# Member Task Ledger

- ID: `P1-B2-EVIDENCE-ADVERSARIAL`
- Title: `P1-B2 Evidence adversarial hardening (locators, expiry, baselines, plan-only)`
- Status: `reviewing`
- Owner: `member B (wangdafa750)`
- Next owner: `project owner`

## Goal

按 B2 任务包冻结的边界，对 B1 证据与 Evaluation section 管线做 fail-closed 加固：locator 必填准入、失效/过期证据剔除且可追溯、具体基线 readiness 门禁、planned-only 不携带观测结果、结果型数字断言报 revise。落实 owner 深度审查（PR #1）的 Gate 条款 invalidated-evidence fail-open。

## Acceptance scenarios

- [x] locator 缺失/空白时准入返回 blocked、不写 EvidenceItem 并记录诊断事件；直接写入路径抛错。
- [x] 失效、过期、格式错/无时区的证据被排除出有效支撑，且仍可读取用于审计追溯。
- [x] 无具体基线时 readiness 为 blocked；空 metrics/required materials 同样不满足。
- [x] 计划型 benchmark 携带观测摘要或非 plan-only 标志时，结果永不 verified。
- [x] 草稿含无结果工件支撑的结果型数字断言时，verdict 为 revise 且 issue 指明该断言。
- [x] 绑定失效证据 ID 的草稿无法产生 verified。

## Decisions

- 过期/格式错/无时区的 `expires_at` 一律判失效（fail-closed），仅在有效支持解析中剔除，不删除证据。
- validator 的允许证据集从 `plan.evidence_ids` 改为 readiness 解析后的 `readiness.evidence_ids`。
- 结果型数字断言采用小型正则 allowlist，命中即 revise；Evidence ID、页码、年份、计划计数不视为结果断言。

## Completed

- 交付 `evidence.py`/`readiness.py`/`benchmark_advisor.py`/`section_validator.py`/`writing_service.py` 加固与 `tests/test_evidence_adversarial.py`、`tests/test_fail_closed_rules.py` 离线对抗测试。
- 任务包源文件（TASK-PACKAGE/L3/PROGRESS/HANDOFF/task-package.json/verification-report）随分支提交。

## Pending

- owner 审查路径边界、对抗矩阵与新鲜验证证据；通过后合入主线并更新任务包注册表状态。

## Next step

owner 验收 B2；随后 S2-B-AUDIT-EVIDENCE 仍受 S1 promotion gate 约束，不得提前启动实现。

## Verification

- [x] 聚焦套件 6 个测试文件 `19 passed`（owner 复核 2026-09-08，Python 3.13.12）。
- [x] 全量 `pytest -W error -q` `47 passed`（owner 复核 2026-09-08）。
- [x] `ruff check src tests` 通过（owner 复核）。
- [x] `node .ai-team/check.mjs` 结构校验通过。

## Handoff note

- From: `member B (wangdafa750)`
- To: `project owner`
- Summary: B2 基于 B1 集成后的 main@c1dbefc，单提交 `26be2d3`；验证在恢复工作树完成并经 owner 在最终提交上复核。已知边界：不添加数值结果工件契约；blocked compose 语义未变。
