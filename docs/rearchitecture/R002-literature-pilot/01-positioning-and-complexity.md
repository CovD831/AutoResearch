# 定位与复杂度预算

问题：`AutoResearchApplication` 直接装配 graph、Agent、service、store 和 checkpoint；搜索连接器、证据写入与运行控制的替换边界不清，重启幂等尚未证明。

目标：先让一个 literature-pilot 场景拥有可替换的 PaperSearch capability port、统一 invocation receipt 和 EvidenceCandidate，同时保持旧入口与五 Agent 不变。

新增名词仅限 `CapabilityManifest`、`CapabilityAdapter`、`InvocationReceipt`、`EvidenceCandidate`、`RuntimeFactory`。每个都有 S1 真实消费者；暂不引入通用 bus、动态 plugin lifecycle、第二数据库或 sandbox。最小替代方案是继续在 `PaperSearchService` 内增加 if/else，但无法隔离外部能力版本、receipt 和唯一证据写入权，因此不足。

明确不声称：外部工具质量、生产多租户、分布式调度、动态卸载、全 Agent 插件化。
