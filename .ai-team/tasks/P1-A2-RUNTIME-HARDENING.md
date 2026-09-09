# Current Task

- ID: `P1-A2-RUNTIME-HARDENING`
- Title: `Runtime Hardening`
- Status: `active`
- Owner: `member A`
- Next owner: `user/team`

## Goal

把 A1 的失败语义变成可持续重跑的 fault-injection、recovery 和 parity harness，关闭 F-1 跨进程 TOCTOU、F-2 phase-aware recovery、F-3 失败标签过宽三个 A2 Gate 条款。

## Acceptance scenarios

- [x] timeout、crash、partial-write 故障注入可离线且可重复运行。
- [x] 故障矩阵覆盖 timeout、进程重启、evidence-before-receipt、重复提交和冲突 fingerprint。
- [x] 每个失败窗口都可重现，未知结果不会被归类为成功。
- [x] 诊断报告记录 request fingerprint、receipt、durable facts 和 side-effect count。
- [x] SQLite 状态迁移跨进程安全，旧快照不能覆盖 finalized 记录。
- [x] recovery 根据 reserved/service_started/service_returned phase 自动选择收口方式。
- [x] 确定性失败与 unknown_outcome 分开，具体失败原因保留在 diagnostics/audit 中。
- [x] phase guard、TOCTOU 和 recovery 回归进入常规 pytest。

## Invariants

- 保留 A1 的 replay、fingerprint conflict、completed_empty、unknown_outcome 和 reserve-first 语义。
- 不绕过 A1 recovery API，不通过直接改数据库伪造成功。
- 不修改 P1-B 独占路径、`application.py`、共享 `contracts.py` 或全局 `.ai-team/TASK.md`。
- 不新增第二套 Store、消息总线、scheduler 或业务 Agent。
- 所有故障测试使用 fake connector、本地 SQLite 和确定 fixture，不依赖网络。

## Decisions

- 结果状态和具体失败原因分离；业务状态保持有限集合，原因写入 diagnostics/audit。
- phase-aware recovery 的具体决策表记录在 task-local `docs/tasks/P1-A-runtime-lane/tasks/A2-runtime-hardening/L3.md`，实现前由用户确认。
- 跨进程状态迁移使用数据库条件更新或等价的版本检查，并以更新行数判断 stale writer。

## Completed

- 已从最新 `origin/main` 建立 `codex/p1-a2-runtime-hardening` worktree。
- 已读取 A2 任务规格和负责人审查 Gate 条款。
- 已建立 A2 task-local L3、PROGRESS 和 HANDOFF 草案。
- 已完成 crash、timeout、partial-write、evidence-before-receipt、duplicate submission 和 conflicting fingerprint fixture。
- 已完成 F-1 条件更新与跨进程 stale writer 回归。
- 已完成 F-2 phase-aware recovery 与 recovery audit 字段。
- 已完成 F-3 不确定异常分类和 diagnostics 原因保留。
- 已完成可重跑 fault matrix 命令和 JSON 报告。
- 已完成全量 Ruff 和 pytest 验证：`48 passed`。

## Pending

- 用户已运行 fault matrix 并确认诊断报告；等待 A2 PR 提交完成。
- 补充 warning 的具体来源（如果用户希望纳入最终风险记录）。
- 等待 A2 PR 提交、推送和负责人审查。

## Next step

代码实现、自动化验证和用户 fault matrix 验收已完成；下一步提交 A2 独立任务记录和代码，不修改全局 `.ai-team/TASK.md`。

## Verification

- [x] `ruff check src tests`
- [x] A2 专项 pytest
- [x] 全量 `pytest -W error -q`
- [x] A2 fault matrix / diagnostic report 可重跑
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/P1-A2-RUNTIME-HARDENING.md --base origin/main`

## Handoff note

- 当前仍在 `active`，尚未标记 `done`，等待 PR 审查和主线集成。
- 用户验收已通过；当前只提交 A2 独立任务记录和代码，不修改全局 `.ai-team/TASK.md`，不扩大到 P1-B。
