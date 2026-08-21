# 核心数据契约

所有契约位于 src/autoresearch/contracts.py，并由 Pydantic v2 在入口和 Agent 交接处验证。

## 1. 身份与状态

| 契约 | 用途 | 关键不变量 |
|---|---|---|
| AgentId | 五个业务角色 | enum 与 AGENT_TYPES 集合完全相等 |
| ResearchState | LangGraph state | schema_version=1；保存 ID，不保存全文 |
| LifecycleState | 科研阶段 | 只能通过 StateMachine allowlist 迁移 |
| RunStatus | 运行结果 | blocked、interrupted、completed、failed 分离 |
| ProjectCreate | 项目初始化 | project_id 受路径安全正则约束 |

## 2. 协作

| 契约 | 用途 | 限制 |
|---|---|---|
| HandoffEnvelope | 跨 Agent 派单 | sender != receiver；project/run 匹配；bounded_context <= 2000 |
| HandoffResult | 结构化回收 | 只返回 artifact/evidence refs、摘要和 blockers |
| ArtifactRef | 稳定产物引用 | ID、kind、URI、checksum、短摘要 |

## 3. 研究资产

| 契约 | 产物 |
|---|---|
| PaperRecord | 题录、摘要、全文位置和来源标识 |
| ReadingCard | 问题、方法、场景、发现、限制、locator |
| ReadingAnswer | 陪读问题、证据限定答案、locator、unresolved |
| InnovationCandidate | hypothesis、区别点、证据和反证实验 |
| WorkPackage | 目标、任务、依赖、产物、验收、状态和证据 |
| Manuscript | 分节稿件、证据、缺口、父版本和 release_ready |
| ReviewReport | verdict、findings、required changes 和已查证据 |

## 4. 治理资产

| 契约 | 产物 |
|---|---|
| EvidenceItem | 不可覆盖的证据记录 |
| GateRequest / GateDecision | 风险、证据、闭环和确定性结果 |
| WikiPage / GraphEdge | 分区知识和关系 |
| UserProfileItem | 来源明确的画像 |
| ExperienceRecord | 可晋级/降级的经验候选 |
| EvolutionProposal | proposal-only 自进化建议 |

## 5. 版本与兼容

对已持久化字段做破坏性变化时必须：

1. 提升 schema_version。
2. 编写旧数据迁移或读取适配。
3. 评估 paused LangGraph threads 的节点名和 channel 兼容性。
4. 增加旧 checkpoint 回归测试。
5. 在 Project-to-Act 记录兼容性和回滚方案。
