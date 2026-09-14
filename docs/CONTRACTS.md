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

## 5. 能力接入契约（Capability boundary）

外部与内置能力统一经由 `CapabilityRegistry` 注册后调用，**不存在旁路**。权威定义见 `docs/rearchitecture/R004-trust-program/04-l2-contracts.md` §CapabilityManifest / §CapabilityAdapter。

| 契约 | 位置 | 职责 |
|---|---|---|
| `CapabilityManifest` | `invocation_contracts.py` | 声明能力身份、版本、输入输出 schema 引用、权限、许可、离线能力与生命周期 |
| `CapabilityAdapter` | `capability_registry.py` | 把 native/MCP/skill/plugin 协议转成 typed request/result，只能 emit candidate |
| `CapabilityRegistry` | `capability_registry.py` | 注册边界与策略：唯一性、版本歧义、trust tier、网络默认拒、幂等、写边界 |
| `CapabilityInvocationReceipt` | `capability_registry.py` | 单次调用的持久记录（含 manifest 身份与选择来源） |
| `SelectionPolicy` | 〔S3-A3，未实现〕 | 能力槽的选项选择；目录与内置多选 |

关键不变式：

1. **能力自述不等于生效策略**。`CapabilityManifest.trust_class` 是自述来源类别，`CapabilityTrustTier` 是 operator 指派；自述永不提升生效层级。
2. **注册期 fail-closed**。`validate_manifest()` 是唯一校验入口，违规即拒绝注册且 adapter 零调用；非致命事项走独立的 `manifest_warnings()`，该通道不具备拒绝能力。
3. **本地能力不能直写项目事实**。adapter 只能 `emit_candidate`；`write_evidence` / `write_gate_decision` 抛 `CapabilityBoundaryViolation`。
4. **网络默认禁用**。`network_required` 能力在 `allow_network=False` 时于调用前 DENIED。`allowed_network_domains` 目前为**声明值，传输层未强制**（归 ProviderLane/O12）。
5. **受限许可必须留痕**。声明 AGPL/SSPL 族许可时必须给出 `selection_restricted_reason`，且不得成为任何能力槽的默认主选。

## 6. 版本与兼容

对已持久化字段做破坏性变化时必须：

1. 提升 schema_version。
2. 编写旧数据迁移或读取适配。
3. 评估 paused LangGraph threads 的节点名和 channel 兼容性。
4. 增加旧 checkpoint 回归测试。
5. 在 Project-to-Act 记录兼容性和回滚方案。

> `CapabilityManifest` 的新增字段一律为**可选默认**，因此不构成破坏性变化；`CapabilityInvocationReceipt` 新增字段同理（旧 receipt 可读，字段为 `None`）。
