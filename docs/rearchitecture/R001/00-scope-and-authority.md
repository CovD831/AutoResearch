# R-001-00 范围与权威基线

## 当前事实

- `src/autoresearch/application.py` 直接构造所有 Service、Agent、SQLite checkpointer 和父图。
- `src/autoresearch/graph.py` 直接依赖五个具体 Agent、EvidenceService、GateService、StateMachine。
- Agent 实现直接依赖具体 Service、`RecordStore`、handoff 和状态机。
- `search_service.py` 内置 OpenAlex、Crossref、Semantic Scholar connector。
- `evidence.py`、`gates.py`、`storage.py` 已存在，但 Evidence 与业务能力仍由应用装配层紧密串联。
- 当前 foundation 已有 CLI/API、五 Agent、基础 checkpoint/resume、项目账本和本地 SQLite。

## 来源优先级

1. 当前源码和测试：实现事实。
2. `AGENTS.md`、`.ai-team/PROJECT.md`、`.ai-team/TASK.md`：仓库约束和当前任务。
3. `.project-to-act/PROJECT_*`：长期范围、进度和验收事实。
4. `docs/ARCHITECTURE.md`、`docs/FUNCTION_MATRIX.md`：当前/目标说明，须以状态标记区分。
5. 本目录：R-001 目标设计和迁移计划，不能覆盖当前实现事实。

## 范围

本包只处理运行时装配、能力接入和证据边界。论文搜索、阅读、写作算法本身不在 S0 重写范围；它们作为真实消费者验证新边界。

## 未知项

- 首个垂直领域和真实 corpus 尚未确定。
- 是否允许远程/不可信插件在独立进程中执行尚未确定。
- 生产部署规模、并发和持久化拓扑尚未确定。
