# Current to Target Map

| 当前热点 | 动作 | 目标 | 兼容与移除门槛 |
|---|---|---|---|
| `AutoResearchApplication` 大型构造器 | split | RuntimeFactory + Registry | 旧 facade 与新 Runtime 事实等价 |
| `graph.py` 直接拼 Agent | adapt | workflow plan/ports | legacy graph 保留到 parity |
| `search_service.py` connector | adapt | PaperSearch Adapter | native/fake adapter 对照通过 |
| Agent 直接依赖 Store | expose | typed ports | contract test 不依赖 concrete Store |
| EvidenceService 与业务装配耦合 | split authority | Evidence Module | 只有 Evidence Module 可写 evidence state |

任何 dependency count 下降都不是移除证据；必须比较 durable facts、receipt、failure、idempotency 和 checkpoint。
