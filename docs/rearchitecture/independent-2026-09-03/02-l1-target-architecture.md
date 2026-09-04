# L1 Target Architecture

## Construction

```text
Config → RuntimeFactory → CapabilityRegistry → Runtime → Domain Ports → Evidence/Policy → Stores
```

## Dependency

```text
CLI/API → Thin Runtime → Capability/Domain Ports → Evidence Query/Admission → Persistence Ports
```

禁止反向依赖：Agent/Skill/MCP → Store、Agent/Skill/MCP → GateDecision、Gate → Writer。

## Interaction

```text
Runtime --Command--> CapabilityAdapter --TypedResult--> Domain Service
Domain Service --EvidenceCandidate--> Evidence Module
Policy --Query--> Evidence Module
Runtime --Checkpoint--> Checkpoint Adapter
Project Ledger --Projection--> Project Files
```

## 唯一写入者

| 事实 | 唯一写入者 |
|---|---|
| capability manifest/version | Capability Registry |
| invocation receipt | Runtime |
| PaperRecord/ReadingCard/Manuscript | 对应 Domain Service |
| EvidenceItem/ClaimLink/ArtifactLink/invalidations | Evidence Module |
| GateDecision | Policy/Gate |
| run lifecycle/checkpoint | Runtime + Checkpoint Adapter（各自边界内） |
| project file projection | Project Ledger |

L1 不把 checkpoint 和 project projection 视为同一 writer；两者通过 typed projection/receipt 交互。
