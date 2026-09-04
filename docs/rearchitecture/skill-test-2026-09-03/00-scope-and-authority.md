# Scope and Authority

## 测试问题

本次不是实现重构，而是测试：按 skill 规定的设计包流程，能否为 AutoResearch 产生可实施、可审查、可恢复的架构材料。

## 当前基线

- `application.py` 负责装配全部服务、Agent、SQLite 和 LangGraph。
- `graph.py` 直接绑定五个 Agent、EvidenceService、GateService 和 StateMachine。
- Agent 直接依赖具体 Service、Store、handoff 和状态机。
- `search_service.py` 内置三个论文连接器。
- 代码、测试、`.ai-team` 和 `.project-to-act` 是当前事实；本包全部是 target/design。

## 范围

测试薄 Runtime、Capability Adapter、独立 Evidence Module 的设计材料是否完整。首个示例切片是 paper-search。

## 不在范围

不实现代码、不接入真实远程 MCP、不改变五 Agent、不引入动态插件加载、消息总线、第二数据库或进程隔离。
