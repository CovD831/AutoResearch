# ADR: 采用薄 Runtime 和独立 Evidence Module

## 状态

Proposed；本文件属于 skill test，不改变当前架构事实。

## 决策

以 Thin Runtime 负责编排，以 Capability Adapter 接入 native/skill/MCP，以 Evidence Module 维护证据真相，以 Policy/Gate 做确定性判定；保留五个业务 Agent。

## 替代方案

- 继续向 Application 增加 connector：短期简单，长期耦合增长。
- 每个模块都插件化：未被真实消费者证明，复杂度过高。
- 直接微服务化：扩大部署和恢复问题，不适合当前 foundation。

## 复审条件

S1 parity 失败则修订合同；出现第二个真实 consumer 后再评估正式 plugin lifecycle。
