# L1 Target Architecture

```text
CLI/API/UI → Thin Runtime → Capability Registry → Skill/MCP/Native Adapter
                                      ↓
                           Research Domain Ports
                                      ↓
                   Evidence Module ← Policy/Gate
                                      ↓
                         Project Ledger / Store
```

## 唯一权威

| 事实 | 唯一写入者 |
|---|---|
| capability metadata | Registry |
| invocation receipt | Runtime |
| domain records | Domain Service |
| claim/evidence/provenance | Evidence Module |
| gate decision | Policy/Gate |
| run/checkpoint | Runtime + checkpoint adapter |
| project projection | Project Ledger |

依赖方向只能是 `Runtime → Capability/Domain → Evidence/Policy → Store`。Agent、Skill、MCP 不得直接写证据或项目状态。
