# Positioning and Complexity

## 定位

AutoResearch 是科研 Agent 的薄编排层和可信交付层：能力由 Skill/MCP/Native Adapter 提供，Runtime 负责运行，Evidence Module 负责事实和 provenance，Policy 负责 Gate。

## 第一阶段部署

单进程、本地运行；只接入受信任的本地 Skill、native capability 和显式 MCP adapter。远程/不可信脚本需要另立进程隔离设计。

## 复杂度预算

第一切片只引入四个核心抽象：`CapabilityManifest`、`CapabilityAdapter`、`InvocationReceipt`、`EvidenceCandidate`。每个都有 paper-search 的真实消费者；不新增 bus、scheduler、plugin loader 或第二数据库。

## 成功标准

不以“依赖数量下降”作为成功标准，而比较 legacy/target 的业务结果、durable facts、receipt、失败语义、幂等、checkpoint 和可追溯性。
