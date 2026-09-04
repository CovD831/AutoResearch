# ADR INDEPENDENT-2026-09-03

## 决策

采用 Thin Runtime、Capability Registry/Adapter、独立 Evidence Module 和 Policy/Gate；保留五个业务 Agent，把 Skill/MCP 视为可替换能力来源。

## 为什么不是单体增强

继续向 Application 增加 connector 会扩大耦合；每个文件插件化会引入没有消费者的复杂度；直接微服务化会扩大部署/恢复边界。

## 保守边界

首阶段单进程、本地、显式 adapter；不支持动态卸载、任意远程代码执行和第二数据库。

## 复审

S1 parity 或恢复测试失败时修订合同；第二个真实 capability consumer 出现时重新评估 plugin lifecycle。
