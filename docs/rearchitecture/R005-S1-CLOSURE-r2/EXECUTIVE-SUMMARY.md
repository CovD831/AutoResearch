# R-005-S1-CLOSURE（r2）执行摘要

## 一句话结论

R005 是 R-004 信任层重构程序下的 S1 收口设计包：它不授权运行时代码实现，而是把 S1 晋级所需的 parity、恢复和证据边界冻结成可执行的下一步。

## 为什么现在需要这个包

当前树中 `PaperSearchCapabilityAdapter` 已存在并具备幂等调用能力，但在 `application.py` 中仅被构造、尚未接入真实运行路径；同时 legacy search 的 `_persist` 已写入 `EvidenceItem` 和 `WikiPage`，adapter 又生成 `EvidenceCandidate`，存在双重证据表示风险。因此，当前不能直接宣布 S1 已完成或开放 S2。

## 本包交付内容

- 对账当前实现、R-003 合同和 R-004 程序边界。
- 冻结 legacy/target parity 的比较对象、隔离方式和 ID 归一化规则。
- 明确 recovery、unknown-outcome、pending invocation 的证据要求。
- 记录 L1 写入者偏差、Evidence 双表示和 replay outcome 语义等决策。
- 消费两轮审查：第一轮 6 条意见、第二轮 4 条 non-blocking 意见，当前均已登记并关闭。

## 当前状态

- 包类型：`design`
- 版本：`r2-consumption`
- checker：`OK`
- 结论：`implementation-candidate`
- 实现授权：无
- S2 Audit Module：继续等待 S1 晋级证据

## 下一步唯一任务

`S1-CLOSURE-EVIDENCE`：生成 parity、restart/timeout/unknown-outcome recovery 证据，裁决 Evidence 双表示接线方案，并修复 replay receipt outcome 语义。

## 开发前必须回答的两项问题

1. 将确定的零结果与 provider 不确定结果拆分为 `completed_empty` / `unknown_outcome`，还是明确接受合并语义。
2. pending invocation 的 recover 是标记失败还是允许重执行，以及 evidence 已落盘但 receipt 尚未 finalize 时如何处理。

## 推进与停止条件

只有在 R-003 的 promotion evidence 可复现，且 R003-AR-005 与 R-004 的 AR-OLD-002/004/005/006 全部关闭后，S1 才能 promotion，S2 才能启动。若 parity 不等价、unknown 被静默标记成功或 sole-writer 无法成立，应保留 legacy facade 并修订合同。

## 详细材料

请从 [README.md](README.md) 开始；完整状态见 [.rearchitecture-package.json](.rearchitecture-package.json)，审查记录见 `review-report.json`、`review-round2-report.md` 和 `review-ledger.json`。
