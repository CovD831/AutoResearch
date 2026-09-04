# 当前到目标映射

| 当前热点 | 动作 | 目标边界 | 兼容与移除门槛 |
|---|---|---|---|
| `AutoResearchApplication` 构造所有组件 | split/expose | `RuntimeFactory` + registry | 旧 facade 与新 fixture 的 state/receipt/checkpoint 等价 |
| `search_service.py` 三连接器 | adapt | PaperSearch adapter port | native legacy 保留；target parity 通过后才接外部能力 |
| `evidence.py` 与 `gates.py` | retain/split authority | Evidence Module + Policy | 外部能力不得直接写证据表 |
| Agent 对具体 `RecordStore` 的隐式依赖 | expose/adapt | typed service ports | contract 测试不再要求具体 store |
| `graph.py` 直接装配子图 | adapt | Runtime workflow plan | 旧 `build_research_graph` wrapper 保留 |
| CLI/API 实例化 Application | retain/adapt | Runtime entrypoint | 新旧 doctor/run/status/resume 结果等价 |

不在本增量拆 `knowledge.py`、Writer、Plugin lifecycle；没有真实第二消费者前不增加抽象。
