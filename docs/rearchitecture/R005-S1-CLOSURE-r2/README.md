# R-005-S1-CLOSURE（design）

程序 R-004-TRUST-PROGRAM 的最小设计增量：对账在飞 S1 实现与 R-003/R-004 合同，冻结 legacy/target parity 与 recovery 的证据计划。**不含实现授权**；不修改运行时代码。

管理层先读：[EXECUTIVE-SUMMARY.md](EXECUTIVE-SUMMARY.md)。

| 文档 | 一句话职责 |
|---|---|
| [00-scope.md](00-scope.md) | 权威次序、基线版本、现状恢复（各历史包状态）与 UD-004 委托记录 |
| [01-positioning.md](01-positioning.md) | 用户/问题、交付与推迟、推进触发条件、停止规则（delivery horizon canonical owner） |
| [02-l1-target.md](02-l1-target.md) | L1 有界重述（零修改判定） |
| [03-current-to-target-map.md](03-current-to-target-map.md) | hotspot 分类 + 关键新发现（adapter 悬空） |
| [04-l2-contracts.md](04-l2-contracts.md) | 两个边界的 L2 合同与 established/conditional/open claims |
| [05-adr.md](05-adr.md) | ADR-4/5/6/7/8 |
| [06-handoff.md](06-handoff.md) | 结论、exact next task、discoverability、未支持声明 |

状态：design，checker 已通过；两轮审查均已登记并消费，详见 [review-ledger.json](review-ledger.json) 与 [review-round2-report.md](review-round2-report.md)。本包仍不授权实现，下一步是 `S1-CLOSURE-EVIDENCE` implementation 包。
