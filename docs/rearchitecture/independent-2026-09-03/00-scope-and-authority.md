# Scope and Authority

## 用户已确定的方向

- 基础 Runtime 应保持薄，只提供接口实现和编排能力。
- 证据、门禁等治理能力应从 Runtime 中独立提取；Evidence 是独立模块。
- 用户可导入自定义 Skill；成熟工具通过可插拔集成接入。
- 开箱即用配置允许替换 Skill、工具和 provider。
- 本轮先重构架构，不一次性补齐所有科研能力。

## 当前实现基线

- `src/autoresearch/application.py` 集中装配 Store、Evidence、Gate、所有 Service、五个 Agent、LangGraph checkpointer。
- `src/autoresearch/graph.py` 直接绑定五个 Agent、EvidenceService、GateService 和 StateMachine。
- Agent 直接依赖具体 Service、Store、handoff 和状态机。
- `search_service.py` 在同一持久化路径写 PaperRecord、Evidence 和 Knowledge 投影。
- 当前事实来自源码、测试、`AGENTS.md`、`.ai-team` 和 `.project-to-act`；本包是 target/design。

## 范围

首个真实迁移切片为 paper-search：native connector 与可替换 capability 通过同一 port 进入 Runtime，结果由 Evidence Module admission。

## 不在范围

不实现远程任意代码执行、热卸载、冲突版本共存、通用消息总线、微服务拆分或完整 Web UI。
