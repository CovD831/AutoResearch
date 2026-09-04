# Positioning and Complexity

## 目标

AutoResearch 作为科研 Agent 生态的薄运行时和可信交付层：复用成熟 Skill/MCP/Plugin，统一 typed result、provenance、证据引用和恢复语义。

## 关键取舍

- 不与成熟写作/搜索工具争夺每个单点能力。
- Runtime 只负责装配、调用、checkpoint 和 bounded result。
- Evidence Module 独立负责证据真相；Gate 只消费其视图。
- 第一阶段保留本地 native 能力和显式 adapter，不承诺任意远程执行。

## 复杂度预算

只新增 `CapabilityManifest`、`CapabilityAdapter`、`InvocationReceipt`、`EvidenceCandidate` 四个名词；每个都有 paper-search 消费者和对应验收证据。
