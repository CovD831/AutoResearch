# R-001-03 当前到目标映射

| 当前热点 | 动作 | 目标边界 | 保留兼容 | 移除门槛 |
|---|---|---|---|---|
| `AutoResearchApplication` 大型构造器 | split/expose | `RuntimeFactory`、Registry、Domain composition | 旧 facade | 新旧 fixture 的 receipt/state/checkpoint 等价 |
| `graph.py` 直接拼具体 Agent | adapt | Runtime workflow plan | `build_research_graph` wrapper | target workflow parity |
| `search_service.py` 三个 connector | adapt | `PaperSearchCapability` | native adapter | fake MCP/native parity |
| `evidence.py` 与 `gates.py` | split authority | Evidence Module / Policy | facade API | Agent 不再直写 evidence |
| Agent 直接依赖 `RecordStore` | expose/adapt | typed ports | facade 注入旧 service | contract test 不依赖 concrete store |
| `knowledge.py` Wiki+Graph | retain | Project Knowledge capability | 原实现 | 两个真实消费者后再拆 |
| CLI/API 直接 new Application | retain/adapt | Runtime entrypoint | `AutoResearchApplication` | 新入口覆盖 doctor/run/status/resume |

## 迁移规则

- 每个热点先适配，不先删除。
- 旧路径成为 legacy fixture，而不是隐式“已经废弃”。
- 只有 target fixture 的 durable facts、receipts、failure 和 checkpoint 等价，才允许移除 concrete dependency。
- 任何新增抽象必须绑定一个真实消费者和一个验收测试。
