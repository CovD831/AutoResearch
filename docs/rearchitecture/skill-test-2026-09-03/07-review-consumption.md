# Review Consumption Ledger (canonical human-readable mirror)

机器权威报告见 [review-report.json](review-report.json)，机器消费账本见 [review-ledger.json](review-ledger.json)。

| Finding | 消费位置 | 状态 |
|---|---|---|
| AR-001–AR-006, AR-009 | `review-ledger.json` → L2/migration/L1/S1 tasks | blocking / pending evidence |
| AR-007–AR-008 | `review-ledger.json` → review checker/ADR | non-blocking / pending closure |

规则：每个 finding 必须有 decision、consumer、task、owner、gate、test/evidence 和 status；blocking finding 没有 resolved evidence 时，review gate 不能通过。Round 1 的 9 条 finding 已消费；Round 2 新增 AR-010，并确认 AR-001–AR-006、AR-009 仍 pending，故包保持 blocked。
