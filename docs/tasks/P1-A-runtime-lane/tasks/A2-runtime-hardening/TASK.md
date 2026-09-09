# A2 Runtime Hardening

- ID：`P1-A2-RUNTIME-HARDENING`
- 状态：`integrated`
- Owner：`member A`
- Next owner：`user/team`
- Branch：`codex/p1-a2-runtime-hardening`
- Base：`c1dbefc` (`origin/main`)
- 依赖：A1 已合并

## 目标

把 A1 的失败语义变成可持续重跑的 fault-injection、recovery 和 parity harness，关闭负责人审查提出的 F-1/F-2/F-3 门禁。

## 任务书要求

- [x] timeout、crash、partial-write 故障注入器可离线、可重复运行。
- [x] 建立重复执行矩阵，覆盖 timeout、进程重启、evidence-before-receipt、重复提交和冲突 fingerprint。
- [x] 建立稳定的 parity/diagnostic 命令并落盘报告。
- [x] 报告记录 request fingerprint、receipt、durable facts 和 side-effect count。
- [x] 每个失败窗口都能重现，未知结果不能被归类为成功。
- [x] 关闭 F-1 跨进程 TOCTOU，并加入多进程回归测试。
- [x] 关闭 F-2 phase-aware recovery，并加入 fault-injection 测试。
- [x] 关闭 F-3 失败标签过宽问题，并保留具体失败原因。
- [x] 将 phase guard 和 TOCTOU 关键回归纳入常规 pytest。

## 边界

- 允许修改 A1 Runtime/Capability/Recovery 路径、A2 task-local ledger、测试、fixture 和诊断报告。
- 不修改 P1-B 独占路径、`application.py`、共享 `contracts.py`、全局 `.ai-team/TASK.md`。
- 不新增第二套 Store、消息总线、scheduler 或业务 Agent。

## 当前进度

- [x] 从最新 `origin/main` 建立 A2 worktree 和分支。
- [x] 激活 A2 task-local 任务记录。
- [x] 完成 L3 设计冻结。
- [x] 完成故障注入和回归实现。
- [x] 完成用户可运行验收。
- [x] 准备第二个 PR 材料。
- [x] 完成 commit、push 和第二个 PR。
- [x] Owner 审查合并（2026-09-09，PR #5 → merge commit `4b7c7fa`）；owner 在合并结果上复现 69 passed 与 fault matrix。

> 实现、自动化验证、用户 fault matrix 验收与主线集成已完成。
