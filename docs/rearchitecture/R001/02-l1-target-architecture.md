# R-001-02 L1 目标架构

## 边界图

```text
User / CLI / API / UI
          |
     Thin Runtime
  (compose, invoke, run)
          |
  Capability Registry
          |
  Skill / MCP / Plugin / Native adapters
          |
  Research Domain Ports
  search | reader | execution | writing
          |
  Evidence Module <---- Policy / Gate
          |
  Project Ledger / Store / Artifacts
```

## 唯一权威

| 事实 | 唯一权威/写入者 |
|---|---|
| capability metadata/version | Capability Registry |
| invocation lifecycle/receipt | Thin Runtime |
| paper/reading/manuscript domain records | 对应 Domain Service |
| claim/evidence/artifact provenance | Evidence Module |
| gate decision | Policy/Gate |
| run/checkpoint | Runtime + LangGraph checkpoint adapter |
| project file projection | Project Ledger |

## 依赖方向

`CLI/API -> Thin Runtime -> Capability/Domain Ports -> Evidence/Policy -> Store`。

禁止：Agent 直接写 Evidence 表；MCP 直接写项目状态；Gate 反向调用 Writer；Runtime 内嵌某个厂商的搜索或写作 prompt。

## 第一阶段部署边界

保持单进程、本地运行；native capability 和受信任的本地 skill 可同进程调用。远程 MCP 仅通过显式 adapter 接入。若未来需要不可信脚本、冲突依赖版本或动态卸载，必须另立进程隔离和恢复设计。
