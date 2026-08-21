# 功能实现表

本表描述 0.1.0 foundation 的实际可用能力。完整产品级 86 项验收仍以 .project-to-act/PROJECT_FEATURES.md 为唯一状态源。

## 1. 用户科研环节

| 环节 | 基础实现 | 入口/模块 | 产物 | 当前边界 |
|---|---|---|---|---|
| idea 拆解 | 已实现 | OrchestratorAgent.scope | research_charter、研究问题、成功条件 | 基础规则拆解；可选受管 LLM 优化检索式 |
| idea 深化 | 已实现 | OrchestratorAgent.scope | 可证伪问题、非目标、工作包 | 尚无领域专用模板库 |
| 相关论文检索 | 已实现 | PaperSearchService | PaperRecord、题录证据、诊断 | 三个连接器已编码；默认关闭网络，live 质量未作为本地测试结论 |
| 论文去重 | 已实现 | PaperSearchService._dedupe_key | DOI/标题归一结果 | 尚未实现预印本到期刊版本图 |
| 论文总结 | 已实现 | PaperReaderService.read | ReadingCard、locator、置信度 | 结构化抽取为基础算法；图表/公式解析待增强 |
| 阅读陪跑 | 已实现 | POST /papers/{id}/questions、ask-paper | ReadingAnswer、locator、evidence IDs | 只回答已供应文本；无材料时 unresolved=true |
| 创新点挖掘 | 已实现 | PaperReaderService.mine_innovations | InnovationCandidate、反证测试 | 永远先标记 hypothesis，不自动宣称 novelty |
| 工作量辅助 | 已实现 | WorkPackage、ExecutionService | 四类工作包、依赖、验收、状态 | 完成状态必须绑定有效证据；资源估算器待增强 |
| 论文写作 | 已实现 | WriterAgent、WritingService.draft | MANUSCRIPT_DRAFT.md | 缺实验时 Results 固定为待真实实验 |
| 修改与润色 | 已实现 | POST /manuscripts/{id}/revisions、revise-manuscript | 独立 revision 文件 | 保留证据和缺口；新版本默认 release_ready=false |
| 审核与打回 | 已实现 | ReviewerAgent | ReviewReport、GateDecision | L3 证据/闭环不足转 WAITING_EVIDENCE |
| 外发批准 | 已实现为安全门 | release_gate、resume | H3 人工证据、L4 decision | 只改变内部 RELEASED 状态，不实际投稿或发布 |

## 2. 平台功能

| 系统 | 基础实现 | 关键能力 | 仍待生产化 |
|---|---|---|---|
| 证据系统 | EvidenceService | 类型、E0–E3/H3、source、locator、checksum、失效事件 | 证据家族细分、冲突传播、时效策略 |
| 门禁系统 | GateService | L0–L4、独立来源去重、闭环、打回、人工批准 | 策略版本迁移与领域策略包 |
| 状态机 | StateMachine | 合法迁移 allowlist、错误跳转拒绝 | 历史 schema 迁移和长任务 retry policy |
| 交接 | HandoffService | receiver/run/project 校验、引用型上下文、长度上限 | hash/version 签名和分布式 outbox |
| 工作流 | LangGraph | 五 Agent 子图、checkpoint、条件边、interrupt/resume | Postgres checkpointer、分布式 worker |
| Wiki+Graph | KnowledgeService | paper/experience/knowledge/profile/project 分区、图边、两级检索 | FTS/vector/RRF/rerank/Neo4j 投影 |
| 用户画像 | UserProfileService | explicit/confirmed 标记、推断置信度上限 | 用户自助修改/删除、细粒度 ACL |
| 经验沉淀 | ExperienceService | 候选、等级、重复次数、双批准晋级 | 自动反例集、跨项目验证和过期降级 |
| 自进化 | EvolutionService | proposal-only、审核/人工批准状态 | 沙箱回归、canary、自动回滚编排 |
| 项目管理 | ProjectService | 从模板实例化独立 Project-to-Act 文件夹 | 跨项目仪表盘和归档/迁移工具 |
| 接口 | CLI + FastAPI | doctor/project/run/resume/evidence/knowledge/profile/evolution | Web UI、认证、多租户限流 |
| 审计 | RecordStore | append-only event timeline | WORM 存储、签名审计和外部 SIEM |

## 3. 非完成声明

以下内容未被本版本声称完成：

- 真实论文检索质量、真实创新性、真实实验结果或论文录用。
- 自动获取受版权限制全文。
- 自动投稿、邮件发送或公开发布。
- PostgreSQL/pgvector/Neo4j 生产部署、HA、备份恢复演练。
- Web 前端、多租户认证、成本和并发基线。
