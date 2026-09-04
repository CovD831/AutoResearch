# Current to Target Map

| 当前热点 | 动作 | 目标 owner | 保留路径 | 移除门 |
|---|---|---|---|---|
| `AutoResearchApplication.__init__` | split | RuntimeFactory/Registry/Composition | facade 保留 | 新旧 run parity |
| `graph.py` | adapt | Runtime workflow plan | wrapper 保留 | target checkpoint parity |
| `search_service.py` connectors | adapt | PaperSearchCapability adapters | native adapter | native/fake parity |
| `search_service._persist` | split | Paper Domain + Evidence admission + Knowledge projection | legacy persistence | sole-writer/atomicity tests |
| Agent concrete Store/Service imports | expose | typed domain ports | compatibility injection | architecture dependency test |
| `evidence.py` + `gates.py` | split authority | Evidence Module + Policy | facade API | evidence writer exclusivity |
| CLI/API direct Application construction | retain/adapt | Runtime entrypoint | old commands | bounded result parity |
