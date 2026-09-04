# 06 Handoff — R-005-S1-CLOSURE

- Package：`docs/rearchitecture/R005-s1-closure-design/`（size `design`，documentation only）
- Program：R-004-TRUST-PROGRAM（active）的第 N+1 个增量；前置：R-003（blocked）
- Baseline：`46fbd7a43c01bebb + 在飞 S1 修改`（[00-scope.md](00-scope.md)、[evidence-baseline.txt](evidence-baseline.txt)）
- Review：见 [review-report.json](review-report.json) 与 [review-ledger.json](review-ledger.json)（消费状态以 manifest `review.status` 为准；该映射仅在本文件与两个 JSON 存在后加入 manifest）

## Outcome：continue（implementation-candidate，不授权实现）

本设计增量把"S1 还缺什么证据"从考古问题变成一张可执行清单；建议下一步以 implementation 包执行它。未满足程序触发条件前，S2 开工门保持关闭（R-004 stop_rule 不变）。

## Exact next task

- ID：`P1-IMPLEMENTATION-PACKAGE`
- Owner：`user/team`（S1 implementer）
- 内容（先完成 task-local L3 冻结，再对应 [04-l2-contracts.md](04-l2-contracts.md) 的 open/conditional claims）：
  1. B-2 parity：同场景（同 query+seeds）下 legacy `PaperSearchService.search` vs adapter 路径的 receipt/durable facts/checkpoint 等价测试 + 落盘 parity 报告（关闭 R003-AR-005 的 parity 半边、AR-OLD-006）。
  2. A-3/A-4 recovery：pending 残留与 unknown-outcome 的构造性测试 + 显式 recover/fail 操作路径（关闭 AR-OLD-004/005、R003-AR-005 恢复半边、AR-OLD-002 的 oracle 部分）。
  3. B-1 接线 + A-5 字段修法：在 L3 冻结后实现候选准入（先裁决双表示，[04-l2-contracts.md](04-l2-contracts.md) B-1）与 replay outcome 语义。parity 断言模型已在 B-2 冻结（ADR-8），实现包直接照写。
- L3 冻结时的必答题（round2 审查 F-R5-2-01/03，见 [review-round2-report.md](review-round2-report.md)）：
  1. receipt `unknown` 语义裁决：拆分 `completed_empty`（确定空结果）与 `unknown_outcome`（provider 不确定），或声明合并语义并写入 B-2 归一化规则——不得默认混淆。
  2. 恢复操作语义 gate：pending 记录的 recover = 标记失败还是允许重执行；方案 (b) 下"证据先于 receipt finalize 落盘"的崩溃窗口必须有处置规则。
  3. 任务 3 完成后必须重跑任务 1 的 parity 冻结命令（接线改变持久化行为，旧报告即过期）。
- 完成定义：R-003 ledger `R003-AR-005` 与 R-004 ledger `AR-OLD-002/004/005/006` 全部 `resolved` 且附可重跑证据；R-003 closure review 重开并通过。

## Advancement trigger / stop rule

见 manifest 与 [01-positioning.md](01-positioning.md)（delivery horizon 为 canonical owner）。

## Discoverability

- 项目目录页 `docs/REARCHITECTURE.md` 已追加 2026-09-03 目录更新块（R-004 程序指针 + 本包入口 + next task）；review AR5-004 已按此闭环。
- Backlog（非本包 gate，owner：user/team，触发条件：下次触碰对应包时）：R-002/R-003/R-004 manifest 与 skill v0.31.0 checker 的结构漂移修复（[evidence-checker-prior-packages.txt](evidence-checker-prior-packages.txt)）；`docs/REARCHITECTURE.md` 第 1–10 节正文仍以 R-001 为完整包叙述，宜在下次内容性修订时重写为程序视角（本次仅加目录块，不重写用户正文）。

## Review

Round 1（独立 sub-agent，`review-request.json` 冻结输入）：6 findings（3 blocking AR5-001/002/003，3 non-blocking），overall `blocked`。全部消费进 [review-ledger.json](review-ledger.json)：blocking 三项以修订后的 02/04/05（ADR-7、ADR-8）关闭。

Round 2（外部 fresh pass，详见 [review-round2-report.md](review-round2-report.md)）：4 条 non-blocking findings（F-R5-2-01..04），已全部消费进同一 ledger；其中 unknown 语义与恢复操作语义列为 S1 L3 必答题，WikiPage parity 项已补入 B-2。两轮均未产生未决 blocking finding；本包仍是 design recommendation，不构成实现授权。

## 未支持声明

本包不证明：adapter 已可上生产、外部 MCP 检索质量、五 Agent 工作流插件化、动态更新或跨进程隔离。
