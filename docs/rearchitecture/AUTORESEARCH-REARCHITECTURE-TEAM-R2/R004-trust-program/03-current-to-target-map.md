# R-004-03 Current-to-Target Map

继承 INDEPENDENT-2026-09-03 的映射表并扩展到全仓。注：`src/autoresearch/capability.py` 与 `tests/test_capability_adapter.py` 已由 R-003 线创建（2026-09-03），映射表以其为 current 起点。动作：retain / expose / adapt / split / freeze。所有"目标 owner"为 S3 末期形态；S1 只建立 capabilities/evidence 边界，不做全仓搬移。

| 当前热点 | 动作 | 目标 owner | 保留路径 | 移除/解冻门 |
|---|---|---|---|---|
| `application.py` 集中装配 | split | `runtime/`（RuntimeFactory/Registry/组合） | `AutoResearchApplication` facade | 新旧 run parity（S1） |
| `graph.py` 直接绑定五 Agent 与服务 | adapt | Runtime workflow plan + 领域角色组合 | wrapper 保留 | target checkpoint parity（S1） |
| `search_service.py` 三连接器 | adapt | `capabilities/` native PaperSearch adapter | native 路径 | native/fake parity（S1） |
| `search_service._persist` 混合写入 | split | Paper Domain + Evidence 接纳 + Knowledge 投影 | legacy 持久化 | sole-writer/atomicity 测试（S1） |
| Agent 直接 import 具体 Store/Service | expose | typed domain ports（`domain/`） | 兼容注入 | architecture dependency 测试（S1） |
| `evidence.py` + `gates.py` | split | `evidence/`（接纳、账本、失效）与 `policy/`（gate、风险级） | facade API | evidence writer exclusivity 测试（S1） |
| `reader_service.py` / `writing_service.py` / `execution_service.py` | adapt | `domain/` reader/writer/execution 服务（能力可替换，S3 LLM 化） | 确定性实现保留为 fallback 与 oracle | 契约级 parity（S3） |
| `llm.py` OpenAI 兼容边界 | retain | provider capability（manifest 注册） | 不变 | — |
| `cli.py` / `api.py` | adapt | 保留 + 新增 `audit` 子命令与 MCP stdio 入口 | 旧命令 | bounded result parity（S2） |
| `contracts.py` | split | 领域记录入 `domain/`，Capability/Evidence/Receipt 契约入对应模块 | 兼容 re-export | S3 末统一清理 |
| `state_machine.py` / `handoffs.py` | retain | Runtime/Policy 边界内 | 不变 | — |
| `storage.py` RecordStore | retain | Persistence Port 实现（SQLite） | 不变 | — |
| `project_service.py` | retain | `projects/` Project Ledger | 不变 | — |
| `evolution_service.py` | freeze | 不迁移、不投入 | facade 后保持可用 | 用户重新优先级化时解冻 |
| `profile_service.py` | freeze | 同上 | 同上 | 同上 |
| `knowledge.py` Wiki+Graph 投影 | freeze | 同上 | 同上 | 同上 |
| Postgres/pgvector/Neo4j 生产迁移 | freeze | 不投入 | SQLite 规范源 | 部署边界变更时重开（ADR-2） |
| Web UI / 多租户 | freeze | 不投入 | — | 同上 |

新增产物（当前不存在）：`capabilities/`（registry、manifest schema、native/fake/mcp adapter）、`audit/`（Audit Module）、`scripts/dependency_inventory.py`、`scripts/benchmark_trust.py`、`tests/test_capability_adapters.py`、`tests/test_recovery_contract.py`、`tests/test_architecture_dependencies.py`、`tests/test_audit_module.py`、审计 fixture 集。
