# R-001-07 对抗性审查与双向钢人论证

> 审查方式：由当前作者在 fresh pass 中执行；尚未有独立 reviewer。此限制本身是非阻塞但需在实现前补审的风险。

## 对抗性审查

| Finding | Evidence | Severity | Decision | Action | Owner/gate |
|---|---|---|---|---|---|
| Capability abstraction 可能只是换名 wrapper | 当前 Application/Service 依赖扫描 | blocking if no consumer | accept | S1 必须同时有 native + fake target fixture | S1 gate |
| 外部 skill 脚本可能带来任意代码风险 | 当前无进程隔离 | non-blocking for S1 | defer | S1 禁止不可信远程执行；未来单独设计 process boundary | Plugin lifecycle ADR |
| Evidence Module 可能复制 Store authority | 当前 EvidenceService/RecordStore 共存 | blocking | accept | Evidence Module 成为 evidence state 唯一 writer；Store 只提供持久化端口 | L2 contract test |
| 新 Runtime 与旧 facade 结果不等价 | 当前无 target fixture | blocking | accept | 做 durable facts/receipt/checkpoint parity，而不是只测返回值 | S1 promotion |
| 过早引入 plugin loader/bus | 用户需求尚未要求动态加载 | non-blocking | reject for R-001 | 保留显式 registry，不引入通用 bus/loader | complexity gate |
| “可信”可能遮蔽论文质量不足 | 当前真实 corpus/质量 gold set 缺失 | blocking for product claim | accept | 把真实论文试点和质量 benchmark 设为后续 promotion 条件 | P2/P3 gate |

## 双向钢人论证

### 最强支持论证

AutoResearch 最有机会成为科研 Agent 生态的可信运行底座：用户可以复用成熟 skill/MCP，系统不重复建设所有单点能力；Evidence Module 将 claim、来源、artifact、版本和审计统一起来；Runtime 的简洁边界允许长期演化而不把治理散落进每个 Agent。

### 最强反对论证

如果用户实际只需要一个好用的论文写作界面，Capability/Receipt/Evidence 可能增加配置和认知成本；成熟工具已经拥有更好的搜索、阅读和写作体验，AutoResearch 可能沦为“多一层但不更好用”的编排器。若没有一个领域的真实质量提升证据，薄 Runtime 只是架构偏好，不是产品价值。

### 综合结论

重构方向成立，但必须以真实领域纵向切片证明“能力质量 + 证据治理”同时提升。S1 只证明接入边界，不允许把它宣传成完整平台；产品成功门槛应包含论文质量/科研效率指标，而不只是模块数量或依赖数量下降。
