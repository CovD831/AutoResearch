# A 线任务队列

| Task | 状态 | 依赖 | 交付重点 |
|---|---|---|---|
| A1 P1-A Runtime/Recovery | ready | — | 幂等、replay、recovery、parity |
| A2 P1-A Runtime Hardening | ready-next | A1 | fault injection、边界回归、证据自动化 |
| A3 S2 Audit Runtime | waiting-for-gate | S1 promotion | audit CLI、resolver、运行时接线 |
| A4 S3 Capability Adapters | ready | S2 promotion | registry、trust tier、外部 adapter |
| A6 S3-A Provider Lane + 真实检索（追加包 2026-09-10） | planned | A4 accepted + S3 promotion | ProviderLane（pi-ai 语义 + lane 约束）、llm.py 替换、Semantic Scholar adapter、计价入 receipt |
| A5 S4 Benchmark Runtime | planned | S3 promotion + A6 | benchmark harness、运行资源和审计 |

每个任务独立 PR；本表只描述顺序，不替代详细验收。
