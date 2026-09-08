# AutoResearch 任务拆解书

> 版本：`AR-002 / 2026-08-22`  
> 用途：把 AutoResearch 从 idea 到论文结果的建设范围拆成可独立分配、可独立验收的任务包。  
> 适用对象：产品负责人、后端/工作流工程师、检索工程师、科研助理、评测工程师、运维和安全负责人。

## 1. 使用说明

本任务书是分配和排期入口，不替代架构、合同和证据策略。以下文件分别负责更细的约束：

- [详细计划书](AutoResearch_详细计划书.md)：产品目标、阶段路线和设计决策。
- [功能表](FUNCTION_MATRIX.md)：功能 ID 的唯一状态清单。
- [架构](ARCHITECTURE.md)：五个业务 Agent 与服务边界。
- [合同](CONTRACTS.md)：状态、handoff、证据和 API 的数据契约。
- [证据与门禁](EVIDENCE_AND_GATES.md)：L0–L4 动作风险和 fail-closed 规则。
- [工作流与状态](WORKFLOW_AND_STATE.md)：LangGraph 节点、状态机、暂停和恢复。
- [知识与进化](KNOWLEDGE_AND_EVOLUTION.md)：Wiki+Graph、画像、经验晋级和提案机制。

当前 `0.1.0 Foundation Preview` 已有可运行的五 Agent 基础纵向切片、SQLite、CLI/API、基础检索/阅读/写作/审核和本地证据旅程；尚未完成真实论文试点、真实实验、生产级数据库、灾备和 Web UI。凡表中标记“基础已落地”的任务，只表示当前证据支持的本地基础能力，不表示生产或论文质量已经验收。

## 2. 分配规则

### 2.1 最小可交付单元

每个子任务必须绑定一个任务负责人和一个合并请求；交付物至少包括：

1. 可运行代码或可审查文档。
2. 输入、输出、依赖和失败路径。
3. 一个正例和一个负例测试，或一份可复核的人工验收记录。
4. 对应的 evidence ID、日志/报告路径和变更说明。
5. `.ai-team/TASK.md` 中的状态、完成条件、下一步和验证结果。

不要把“把整个 Agent 做好”“优化一下检索”“完善前端”作为可分配任务；应按下面的 ID 拆成单一行为和单一验收门。

### 2.2 状态定义

| 状态 | 含义 |
|---|---|
| 基础已落地 | 当前 foundation 已有代码和本地证据，但仍可能需要真实语料、性能或生产验收 |
| 待开发 | 已进入范围，尚无可交付实现 |
| 外部阻塞 | 需要用户提供 idea、语料、许可、实验资源或部署决策 |
| 进行中 | 已有负责人或分支，尚未通过本任务的验收门 |
| 已验收 | 任务的本地/集成/人工验收条件全部通过，并有证据链接 |

### 2.3 推荐角色

| 角色 | 主要任务 |
|---|---|
| PO/研究负责人 | 研究问题、范围、目标 venue、人工 Gate、最终取舍 |
| WF 工程师 | LangGraph、状态机、handoff、checkpoint、重试和幂等 |
| Evidence 工程师 | EvidenceItem、Claim、GatePolicy、审计、审批和版权边界 |
| Retrieval 工程师 | OpenAlex/Crossref/S2、全文、去重、召回和排序 |
| Paper Scientist | 阅读卡、claim map、冲突分析、创新假设和人工 gold set |
| Experiment 工程师 | WorkPackage、RunManifest、实验执行和结果验证 |
| Writing/Review 工程师 | 提纲、草稿、引用、修改、审核和质量门 |
| KB/ML 工程师 | Wiki+Graph、向量/词法/图检索、画像、经验和自进化 |
| Platform/DevOps | API、CLI、可观测、迁移、备份恢复、CI/CD 和发布 |
| Security/Privacy | 密钥、ACL、PII、版权、外发和破坏性操作门禁 |

## 3. 依赖波次

| 波次 | 目标 | 可并行任务 | 进入条件 | 退出条件 |
|---|---|---|---|---|
| W0 | 治理和发布基线 | M00-01～04、M14-01 | 仓库和项目账本可读 | 分支、任务、验收、秘密策略一致 |
| W1 | 合同、证据、状态和规范存储 | M01、M02、M04 | W0 通过 | 负例不能越过 Gate，状态可恢复 |
| W2 | 五 Agent 工作流闭环 | M03、M13-01～03 | W1 通过 | 离线 idea→缺口稿件旅程通过 |
| W3 | 论文检索和阅读 | M05、M06 | 用户提供领域和全文边界 | gold query、阅读卡和 locator 质量可评估 |
| W4 | 创新、执行和结果验证 | M07、M08 | W3 有真实 paper bundle | 每个 claim 可追到运行/证据，未运行不进结果 |
| W5 | 写作、审核和项目交付 | M09、M10、M13-04～07 | W4 有证据化工作包 | 缺口稿、修改稿、审核打回可回放 |
| W6 | 知识、经验、自进化和运维 | M11、M12、M15 | W1～W5 有真实事件 | 分区隔离、晋级降级、备份恢复和审计通过 |
| W7 | 真实论文试点和生产化 | M16、M17 | 资源、许可、部署目标确认 | 一个真实项目闭环，结果不外推 |

硬依赖：W1 未通过时，任何 L2+ 自动化操作不得上线；W3 未建立 gold set 时，不能声称检索/阅读质量；W4 未有真实 RunManifest 时，写作只能生成明确缺口稿；W7 未通过时，版本名称必须保留 `Preview` 或 `Pilot`。

## 4. 模块总览

| 模块 | 名称 | 主要边界 | 负责人建议 | 当前状态 |
|---|---|---|---|---|
| M00 | 项目治理与发布 | Git、Project-to-Act、VibeCollab、版本和发布 | PO + Platform | 基础已落地 |
| M01 | 合同、状态和交接 | Pydantic 状态、handoff、ContextPack | WF 工程师 | 基础已落地，待迁移加固 |
| M02 | 证据与门禁 | Evidence、Claim、Gate、人工审批 | Evidence 工程师 | 基础已落地，待扩展 |
| M03 | LangGraph 工作流 | 父图、五子图、暂停恢复和路由 | WF 工程师 | 基础已落地，待进程重启加固 |
| M04 | 存储、事件和幂等 | SQLite、审计、outbox、迁移 | Backend 工程师 | 基础已落地，待生产化 |
| M05 | 论文搜索 | 多源检索、去重、筛选、许可 | Retrieval 工程师 | 基础已落地，待真实评测 |
| M06 | 论文读取与陪跑 | 全文解析、阅读卡、问答和引用定位 | Paper Scientist | 基础已落地，待 gold corpus |
| M07 | 创新与 claim 分析 | 近邻、差异、反证条件、创新候选 | Paper Scientist + Retrieval | 基础已落地，待反例评测 |
| M08 | 工作执行与结果 | WorkPackage、RunManifest、实验和产物血缘 | Experiment 工程师 | 待开发 |
| M09 | 写作、修改和润色 | 提纲、稿件、引用、版本差异 | Writing 工程师 | 基础已落地，待引用闭环 |
| M10 | 审核与质量 | 证据、方法、创新、结果和定向打回 | Review 工程师 | 基础已落地，待人工基准 |
| M11 | Wiki+Graph 与检索 | 六分区知识库、图谱、分级召回 | KB/ML 工程师 | 基础已落地，待生产索引 |
| M12 | 画像、经验与自进化 | 用户画像、经验晋级、提案和回滚 | KB/ML + PO | 基础已落地，待跨项目验证 |
| M13 | API、CLI 与用户界面 | 入口复用、任务查询、项目面板 | Platform + Frontend | CLI/API 基础已落地，UI 待开发 |
| M14 | 安全、隐私和模型配置 | 密钥、ACL、版权、LLM profile、外发门禁 | Security | 基础已落地，待审计 |
| M15 | 可观测、运维和灾备 | telemetry、告警、迁移、备份恢复 | DevOps | 部分已落地，待开发 |
| M16 | 真实论文试点 | idea、gold set、端到端人工验收 | PO + Paper Scientist | 外部阻塞 |
| M17 | 生产化与规模验证 | PostgreSQL/pgvector/Neo4j、并发和成本 | Platform/DevOps | 待开发 |

## 5. 详细任务清单

任务表中的“验收”是合并前最小门；“规模”按 0.5–5 人日估算，只用于排期，不是承诺工期。

### M00｜项目治理与发布

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M00-01 | 固化仓库目录和五 Agent 边界 | README、AGENTS、PROJECT 与架构图一致；Agent 数量检查为 5 | 无 | PO/Platform | 1 | 基础已落地 |
| M00-02 | 建立 Project-to-Act 根账本 | 六份根账本和模板账本可初始化、校验为 valid | M00-01 | PO | 1 | 基础已落地 |
| M00-03 | 建立 VibeCollab 非私有协作基线 | `.ai-team` 文件、任务检查脚本和非私有策略可复现 | M00-01 | Platform | 1 | 基础已落地 |
| M00-04 | 建立版本、证据和变更记录规则 | 每次功能变更都能链接功能 ID、版本和 evidence ID | M00-02 | PO/QA | 1 | 基础已落地 |
| M00-05 | 配置 GitHub public 仓库与保护规则 | `main` public；分支保护、Issue/PR 模板和 CI 状态检查可见 | M00-03 | Platform | 1 | 进行中 |
| M00-06 | 建立 release checklist | Preview/Pilot/Production 三种发布清单；未验收项不能写成已完成 | M00-04 | PO/QA | 1 | 待开发 |

### M01｜合同、状态和结构化交接

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M01-01 | 定义 ResearchState v1 | 状态字段、稳定 ID、版本、错误和证据索引有 Pydantic 合同 | M00-01 | WF | 2 | 基础已落地 |
| M01-02 | 完成状态迁移与兼容层 | v1→v2 的迁移脚本、未知字段拒绝/保留策略和回放测试 | M01-01 | WF/Backend | 3 | 待开发 |
| M01-03 | 固化 HandoffEnvelope | 发送方、接收方、任务、输入引用、输出、风险、Gate、hash 齐全 | M01-01 | WF | 2 | 基础已落地 |
| M01-04 | 实现 HandoffResult 校验 | 缺字段、超范围上下文、重复交接、越权输出均返回结构化失败 | M01-03 | WF/QA | 2 | 基础已落地 |
| M01-05 | 实现 ContextAssembler | 只装配当前任务必需上下文；超限时退回拆分而非堆砌全文 | M01-03,M11-04 | WF/KB | 3 | 待开发 |
| M01-06 | 建立交接回放工具 | 给定 run/thread 可按序导出 envelope、Gate 和 artifact 引用 | M01-04,M04-03 | WF/QA | 2 | 待开发 |

### M02｜证据系统与门禁系统

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M02-01 | EvidenceItem append-only 存储 | source、locator、hash、许可、可见范围、时间和 revision 不可覆盖 | M01-01,M04-01 | Evidence | 3 | 基础已落地 |
| M02-02 | 统一 H/P/X/R 证据等级 | 人工、论文、执行和经验等级有枚举、解释和负例 | M02-01 | Evidence/PO | 2 | 基础已落地 |
| M02-03 | 建立 Claim registry | claim 的支持、反驳、未知、冲突和适用范围可查询 | M02-01 | Evidence | 3 | 基础已落地 |
| M02-04 | 构建 EvidenceBundle | 按直接性、独立性、时效、冲突和覆盖度计算，不只按条数计数 | M02-02,M02-03 | Evidence | 3 | 基础已落地 |
| M02-05 | 实现 L0–L4 动作分类 | 高风险动作自动升级；外发、删除、发布、昂贵执行必须可识别 | M02-02 | Evidence/Security | 2 | 基础已落地 |
| M02-06 | 实现 GatePolicy 版本化 | PASS/REVISE/INTERRUPT/DENY 决定由代码产生，LLM 不可覆盖 | M02-04,M02-05 | Evidence/WF | 3 | 基础已落地 |
| M02-07 | 实现证据前置检索与 Gate 审计 | L2+ 动作前记录查询、候选、最终 bundle 和决定；缺证据 fail-closed | M02-06,M11-05 | Evidence/KB | 4 | 待开发 |
| M02-08 | 实现人工 H3 审批与去重 | 人、目的、范围、时间、证据 ID 有效；同 thread 不重复释放审批 | M02-06,M03-05 | Evidence/Security | 3 | 基础已落地，待加强 |
| M02-09 | 实现失效传播和永久阻断 | 撤稿、过期、伪造、绕过付费墙、未批准外发导致关联 claim/Gate 重算或永久拒绝 | M02-03,M02-06 | Evidence | 4 | 待开发 |

### M03｜LangGraph、状态机与工作流

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M03-01 | 注册五个业务 Agent | 配置和运行时都只出现 orchestrator/search/reader/writer/reviewer 五个业务 Agent | M01-01 | WF | 2 | 基础已落地 |
| M03-02 | 建立父图和子图输入输出 | 每个子图只读写声明字段；服务节点不能被误计为 Agent | M03-01,M01-03 | WF | 3 | 基础已落地 |
| M03-03 | 固化生命周期状态机 | 合法/非法转移、前置 artifact 和 Gate 条件有表格和测试 | M01-01,M02-06 | WF | 3 | 基础已落地 |
| M03-04 | 完成条件边与停止路径 | PASS、REVISE、INTERRUPT、DENY、CANCELLED 五路均有可观测结果 | M03-03 | WF/QA | 3 | 基础已落地 |
| M03-05 | 完成 checkpoint/resume | 同 thread 暂停后使用有效 evidence/approval 恢复，断点不重复副作用 | M03-04,M04-04 | WF/Backend | 4 | 基础已落地，待重启验证 |
| M03-06 | 实现错误分类和重试预算 | transient、invalid、blocked、denied 分开；重试上限和 dead-letter 可查 | M03-04,M04-05 | WF/QA | 3 | 待开发 |
| M03-07 | 实现版本化 workflow registry | 运行绑定不可变 workflow 版本；旧 run 可回放和分叉 | M03-03,M04-06 | WF | 3 | 待开发 |

### M04｜规范存储、事件和幂等

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M04-01 | SQLite canonical store | 项目、run、artifact、evidence、knowledge、profile 有外键和索引 | M01-01 | Backend | 3 | 基础已落地 |
| M04-02 | 审计时间线和 revision | append-only 事件可按 project/run/claim/action 重建 | M04-01,M02-03 | Backend/Evidence | 3 | 基础已落地 |
| M04-03 | 产物注册和内容 hash | 每份阅读卡、草稿、报告和导出物可定位、校验和、可见范围 | M04-01 | Backend | 2 | 基础已落地 |
| M04-04 | checkpoint 持久化测试 | 进程退出、重新启动、同 thread 恢复的集成测试通过 | M04-01,M03-05 | Backend/QA | 4 | 待开发 |
| M04-05 | outbox 和幂等键 | retry/resume 不重复写库、知识、实验、通知或发布 | M04-02,M04-03 | Backend/WF | 4 | 待开发 |
| M04-06 | 数据库迁移和兼容检查 | 空库、旧库、部分失败迁移可回滚；schema version 可审计 | M04-01 | Backend/DevOps | 3 | 待开发 |

### M05｜论文搜索 Agent 与外部连接器

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M05-01 | idea→检索式生成 | 中英文同义词、布尔式、时间/领域过滤器和查询版本可追溯 | M03-02 | Retrieval/Paper Scientist | 3 | 基础已落地 |
| M05-02 | OpenAlex/Crossref 连接器 | 正常、限流、超时、空结果和服务不可用均有诊断 | M05-01 | Retrieval | 3 | 基础已落地 |
| M05-03 | Semantic Scholar 连接器 | API 失败不伪造结果；重试、退避、速率限制和来源记录齐全 | M05-02 | Retrieval | 3 | 基础已落地 |
| M05-04 | 题录去重和版本归并 | DOI/外部 ID/标题作者年份去重；预印本与正式版关系保留 | M05-02,M05-03 | Retrieval | 3 | 基础已落地 |
| M05-05 | 纳排筛选和诊断报告 | 每条排除有理由；输出命中、保留、去重、缺口统计 | M05-04 | Retrieval/Paper Scientist | 3 | 基础已落地 |
| M05-06 | 撤稿、更正、OA 和许可检查 | 不能绕过付费墙；全文可用性和授权进入 evidence | M05-04,M02-01 | Retrieval/Security | 4 | 待开发 |
| M05-07 | 召回 gold query 评测 | 人工相关集版本化；Recall@k、MRR/nDCG、遗漏类型和回归报告齐全 | M05-05,M16-02 | Retrieval/QA | 5 | 外部阻塞 |

### M06｜论文读取 Agent 与阅读陪跑

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M06-01 | 全文导入和 PDF hash | 仅处理用户授权/公开全文；原文、版本和 hash 可追溯 | M05-06 | Retrieval/Security | 3 | 基础已落地 |
| M06-02 | 章节/段落/图表/公式解析 | locator 稳定；解析失败显式 unknown，不填充缺失内容 | M06-01 | Paper Scientist/Backend | 4 | 基础已落地 |
| M06-03 | ReadingCard 结构化总结 | 问题、方法、数据、基线、指标、结果、限制和复现资源齐全 | M06-02 | Paper Scientist | 4 | 基础已落地 |
| M06-04 | claim-evidence map | 每个关键主张绑定 section/page/figure/table 和 evidence ID | M06-03,M02-03 | Paper Scientist/Evidence | 4 | 基础已落地 |
| M06-05 | 章节级陪读和追问 | 只装配当前段落与必要前置证据；回答引用 locator；未知明确返回 | M06-02,M01-05 | Paper Scientist/WF | 3 | 基础已落地 |
| M06-06 | 跨论文支持/冲突分析 | 支持、反驳、不可比、未知和来源独立性分开记录 | M06-04,M11-03 | Paper Scientist | 4 | 待开发 |
| M06-07 | 阅读质量人工基准 | 盲评总结完整度、引用准确率、遗漏和幻觉率，形成回归集 | M06-03,M16-03 | Paper Scientist/QA | 5 | 外部阻塞 |

### M07｜创新点、近邻和 Claim 分析

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M07-01 | 研究缺口分类 | 将缺口分为未研究、证据冲突、方法瓶颈、数据/评测空白和适用边界 | M06-06 | Paper Scientist | 2 | 基础已落地 |
| M07-02 | 最近似工作检索 | 每个候选创新点列出 top-k 近邻、检索式、时间范围和漏检风险 | M05-05,M06-04 | Retrieval | 3 | 基础已落地 |
| M07-03 | 差异特征和可证伪假设 | 输出区别特征、适用条件、反证条件和最小验证实验，不直接宣称创新 | M07-02 | Paper Scientist | 3 | 基础已落地 |
| M07-04 | 重复创新反例集 | 建立“看似新、实际已有”的负例；新候选必须通过相似度和人工复核 | M07-02,M16-04 | Paper Scientist/QA | 4 | 外部阻塞 |
| M07-05 | Claim graph 和证据覆盖 | claim→paper/method/data/result/experiment 的边可查询，冲突不覆盖 | M07-03,M11-03 | KB/Evidence | 4 | 待开发 |
| M07-06 | 创新候选 Gate | 证据不足返回 REVISE/UNKNOWN；没有反证条件不得进入工作包 | M07-03,M02-06 | Evidence/Review | 2 | 基础已落地，待严格评测 |

### M08｜工作包、实验执行与结果验证

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M08-01 | WorkPackage 合同 | 目标、非目标、输入、输出、依赖、风险、工作量假设和回滚齐全 | M07-06 | Experiment/WF | 3 | 基础已落地 |
| M08-02 | RunManifest schema | 代码、数据、环境、参数、seed、命令、退出状态和输出 hash 齐全 | M08-01,M04-03 | Experiment/Backend | 4 | 待开发 |
| M08-03 | 本地执行器和 dry-run | 白名单命令、资源预算、超时、取消和 dry-run 结果可审计 | M08-02,M02-05 | Experiment/Security | 4 | 待开发 |
| M08-04 | artifact lineage | 图、表、数字和中间结果可追到 RunManifest、输入数据和代码版本 | M08-02,M04-03 | Experiment/Backend | 4 | 待开发 |
| M08-05 | baseline/ablation 编排 | 对照、消融、重复次数、随机种子和停止条件可复查 | M08-03 | Experiment/Research | 4 | 待开发 |
| M08-06 | 结果验证和 R 等级 | 未运行结果为 R0；通过统计、完整性和一致性检查后才升级 | M08-04,M02-02 | Experiment/Evidence | 4 | 待开发 |
| M08-07 | 执行后闭环 Gate | 预期 artifact、退出码、hash、日志和状态一致，否则回退/阻断 | M08-06,M02-06 | WF/Review | 3 | 待开发 |

### M09｜写作、修改和润色 Agent

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M09-01 | 证据化论文提纲 | 每节列出 claim、evidence、result、缺口和目标读者 | M07-06,M08-01 | Writing/PO | 3 | 基础已落地 |
| M09-02 | 缺口稿生成 | 没有真实结果时使用 TODO/UNKNOWN；禁止虚构数字、实验和引用 | M09-01,M02-06 | Writing/Evidence | 3 | 基础已落地 |
| M09-03 | 结果稿生成 | 仅使用已验证 R 证据和 artifact lineage；数字可反向定位 | M08-06,M09-01 | Writing/Experiment | 4 | 待开发 |
| M09-04 | 版本化修改和润色 | 保留 diff、修改理由、证据影响和回退版本；润色不改变事实强度 | M09-02 | Writing/Review | 3 | 基础已落地 |
| M09-05 | BibTeX/CSL 和正文一致性 | DOI/题录可解析；正文引用、参考文献和 evidence 一一对应 | M05-04,M06-04 | Writing/Retrieval | 4 | 待开发 |
| M09-06 | 目标 venue 模板适配 | 模板、字数、章节、匿名化和附录要求版本化，缺失要求返回阻塞 | M09-05 | Writing/PO | 3 | 待开发 |

### M10｜审核 Agent 与质量门

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M10-01 | 证据审查 | 逐 claim 检查来源、locator、直接性、冲突和过期状态 | M02-04,M06-04 | Review/Evidence | 3 | 基础已落地 |
| M10-02 | 方法与实验审查 | 检查 baseline、数据、指标、随机性、资源和可复现性 | M08-05 | Review/Experiment | 4 | 待开发 |
| M10-03 | 创新与相关工作审查 | 检查近邻覆盖、差异是否真实、反例和反证条件是否存在 | M07-04 | Review/Paper Scientist | 3 | 基础已落地，待人工基准 |
| M10-04 | 写作与引用审查 | 检查断言强度、引用完整性、数字一致性和术语统一 | M09-05 | Review/Writing | 3 | 待开发 |
| M10-05 | 定向打回和复验 | 问题有等级、依据、回退目标、复验条件；打回阻止越级 | M10-01,M02-06 | Review/WF | 3 | 基础已落地 |
| M10-06 | 审核 gold rubric | 用真实样例建立 inter-rater agreement、漏检率和回归报告 | M16-03 | Review/QA | 4 | 外部阻塞 |

### M11｜Wiki+Graph、分库和分级检索

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M11-01 | 六分区存储和 ACL | evidence/project/paper/experience/knowledge/user 分区写入路径隔离 | M04-01,M14-03 | KB/Security | 3 | 基础已落地 |
| M11-02 | Wiki 页面和 revision | draft/published/invalid 状态、作者、来源和版本不可覆盖 | M11-01,M02-01 | KB | 3 | 待开发 |
| M11-03 | 属性图节点/边 schema | Paper、Claim、Method、Data、Metric、Result、Experience 等节点可投影 | M11-01 | KB | 3 | 基础已落地 |
| M11-04 | ContextPack 分级装配 | L0–L8 按权限、任务、证据等级和预算逐级召回 | M11-03,M01-05 | KB/WF | 4 | 待开发 |
| M11-05 | 词法、向量、图和证据融合 | 精确→词法→向量→图→Evidence filter 的路径可解释并留审计 | M11-03,M02-07 | KB/ML | 5 | 待开发 |
| M11-06 | 论文库发布管线 | 题录、阅读卡、claim、方法、结果和限制审核后入论文库 | M06-03,M06-04 | KB/Paper Scientist | 4 | 基础已落地，待审核发布 |
| M11-07 | RRF/rerank/去重 | 分数可拆解，镜像不重复计权，embedding 版本可迁移 | M11-05 | KB/ML | 4 | 待开发 |
| M11-08 | Recall gold set 和回归 | 每次索引或模型变化自动输出 Recall@k、MRR/nDCG 和遗漏分类 | M05-07,M11-07 | KB/QA | 4 | 外部阻塞 |

### M12｜用户画像、经验沉淀与自进化

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M12-01 | explicit/inferred/confirmed 画像 | 推断不冒充确认；每个字段有来源、置信度、有效期和可见范围 | M04-01,M14-03 | KB/Security | 3 | 基础已落地 |
| M12-02 | 画像查看、修改和删除 | 用户能查看/纠正/删除；敏感字段默认不 embedding | M12-01,M14-04 | Security/Platform | 3 | 基础已落地 |
| M12-03 | 经验事件捕获 | 记录问题、技巧、失败、打回和人工修正，并去敏和归因 | M04-02,M10-05 | KB/QA | 3 | 基础已落地 |
| M12-04 | X0/X1 候选提炼 | 经验含触发条件、做法、边界、反例、证据和适用项目 | M12-03,M02-04 | KB/Paper Scientist | 3 | 基础已落地 |
| M12-05 | 沙箱复现、跨项目晋级降级 | X2 需可复现；X3 需跨任务；冲突、过期和失败自动降级 | M12-04,M16-05 | KB/QA | 5 | 待开发 |
| M12-06 | proposal-only、灰度和回滚 | 只生成 workflow/prompt/skill diff；H3+回归+canary 后才生效，可回滚 | M12-05,M02-08 | PO/Platform | 4 | 基础已落地，待生产化 |

### M13｜API、CLI 和用户界面

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M13-01 | 统一 Application Service | CLI、HTTP、未来 UI 共用项目/运行/查询/审批服务，不出现旁路 | M01-01,M03-02 | Platform/WF | 3 | 基础已落地 |
| M13-02 | 项目创建/运行/查询 API | 成功、blocked、denied、unknown 均返回结构化 schema | M13-01 | Platform | 3 | 基础已落地 |
| M13-03 | CLI doctor/init/run | 离线安装后可发现 Agent 数、配置状态和安全边界 | M13-01,M14-02 | Platform | 2 | 基础已落地 |
| M13-04 | 研究项目面板信息架构 | 展示阶段、Gate、证据覆盖、handoff、任务和阻塞，不展示虚假完成 | M13-02 | Frontend/PO | 3 | 待开发 |
| M13-05 | 证据和审核面板 | 按 claim/action/run 查看 evidence、Gate、审查意见和回退入口 | M13-04,M02-07 | Frontend/Evidence | 4 | 待开发 |
| M13-06 | 项目文件夹浏览与导出 | 论文库、经验库、知识库、稿件、实验产物和 manifest 可按 ACL 导出 | M13-04,M11-01 | Frontend/Platform | 4 | 待开发 |
| M13-07 | 人工审批和打回交互 | H3 审批必须显示范围/风险/证据；确认、拒绝、打回均写审计 | M13-05,M02-08 | Frontend/Security | 3 | 待开发 |

### M14｜安全、隐私、版权和模型配置

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M14-01 | secrets/环境分层 | `.env.local`、token、日志和提交扫描；示例配置不含真实值 | M00-01 | Security/Platform | 2 | 基础已落地 |
| M14-02 | LLM profile 管理 | provider/model/base URL 从受管 profile 注入；脱离配置时安全回到离线模式 | M13-03 | Security/Platform | 3 | 基础已落地 |
| M14-03 | 项目/用户/库 ACL | 用户只能读取授权项目和分区；越权正负例均有测试 | M11-01,M12-01 | Security/Backend | 4 | 待开发 |
| M14-04 | PII 和敏感画像最小化 | 默认不将敏感字段送 embedding/外部模型；导出/删除可追溯 | M12-02 | Security/KB | 3 | 待开发 |
| M14-05 | 论文全文许可策略 | OA、用户授权、内部授权和不可用状态区分；拒绝绕过付费墙 | M05-06 | Security/Retrieval | 3 | 待开发 |
| M14-06 | 外发、删除和高成本动作 Gate | 未有 H3、范围、预览和结果审计时，API/CLI 均不可执行 | M02-08,M13-07 | Security/Evidence | 4 | 基础已落地，待端到端验证 |

### M15｜可观测、运维、迁移和灾备

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M15-01 | 结构化 telemetry | 按 project/run/node/agent/tool/gate/evidence 记录耗时、状态和错误 | M04-02,M03-04 | DevOps | 3 | 基础已落地 |
| M15-02 | 日志脱敏和审计查询 | 不记录 prompt、全文、token 或 secrets；审计可按稳定 ID 查询 | M15-01,M14-01 | DevOps/Security | 3 | 待开发 |
| M15-03 | 健康检查和依赖诊断 | SQLite、连接器、LLM profile、存储空间和任务队列返回可行动诊断 | M13-03 | DevOps | 2 | 基础已落地 |
| M15-04 | 指标、告警和预算 | blocked/denied/retry/latency/成本阈值可观测；超限触发 interrupt | M15-01,M02-05 | DevOps/WF | 3 | 待开发 |
| M15-05 | 备份和恢复演练 | 数据库、artifact、证据、索引和配置可恢复并校验 hash | M04-06,M11-05 | DevOps | 5 | 待开发 |
| M15-06 | schema/索引重建工具 | 可从规范源重建 Wiki、图和向量索引；过程有 checkpoint 和报告 | M11-03,M11-07 | DevOps/KB | 4 | 待开发 |
| M15-07 | 运行手册与故障演练 | 安装、升级、回滚、断网、连接器失败、磁盘满和恢复步骤可照做 | M15-03,M15-05 | DevOps/PO | 4 | 部分已落地 |

### M16｜真实论文试点与人工验收

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M16-01 | 确认首个真实 idea 和边界 | 记录领域、问题、目标 venue、时间窗、语言、禁用范围和成功标准 | M00-04 | PO/用户 | 1 | 外部阻塞 |
| M16-02 | 准备许可明确的 paper corpus | 题录、全文、许可、hash、版本和排除清单齐全 | M16-01,M05-06 | PO/Retrieval | 3 | 外部阻塞 |
| M16-03 | 标注搜索/阅读 gold set | 相关性、摘要要点、locator、关键 claim 和遗漏反例由人工复核 | M16-02 | Paper Scientist/QA | 5 | 外部阻塞 |
| M16-04 | 标注创新近邻反例 | 至少覆盖“已有工作误判为新”和“证据不足仍值得追踪”两类 | M16-03 | Paper Scientist | 4 | 外部阻塞 |
| M16-05 | 确认实验资源和安全边界 | GPU/CPU、数据、预算、时限、命令白名单、停止条件和人工审批人明确 | M16-01 | Experiment/Security | 2 | 外部阻塞 |
| M16-06 | 执行端到端项目 | idea→检索→阅读→创新→工作包→实验/缺口稿→审核，保留完整链 | M16-02,M16-05 | 全体 | 5 | 外部阻塞 |
| M16-07 | 人工质量评估 | 检索、阅读、创新、写作、审核分别打分；记录误报、漏报和修改次数 | M16-03,M16-06 | QA/PO | 4 | 外部阻塞 |
| M16-08 | 形成 Pilot release report | 只报告该项目、该语料和该配置的结果；明确未验证项和下一轮修复 | M16-07 | PO/QA | 2 | 外部阻塞 |

### M17｜生产化与规模验证

| ID | 子任务 | 交付物与验收 | 依赖 | 角色 | 规模 | 状态 |
|---|---|---|---|---|---:|---|
| M17-01 | PostgreSQL 规范存储迁移 | 迁移、回滚、并发写入和审计结果与 SQLite profile 对齐 | M04-06,M16-08 | Backend/DevOps | 5 | 待开发 |
| M17-02 | pgvector/FTS 分区索引 | 每库独立索引、embedding 版本、删除/失效传播和重建通过 | M11-07,M17-01 | KB/ML | 5 | 待开发 |
| M17-03 | Neo4j 派生图投影 | outbox 水位可审计；图可从规范源全量重建且不能反写 | M11-03,M15-06,M17-01 | KB/DevOps | 5 | 待开发 |
| M17-04 | 队列、并发和租约 | 长任务可恢复；重复消费、worker 崩溃和死信处理有集成测试 | M03-06,M04-05 | WF/Platform | 5 | 待开发 |
| M17-05 | 性能和成本基线 | 按目标规模实测延迟、吞吐、存储、模型调用和连接器成本 | M17-02,M17-04 | DevOps/QA | 4 | 待开发 |
| M17-06 | 多用户权限和审计验收 | 跨项目、跨库、导出、删除、审批和管理员操作均有审计 | M14-03,M15-02 | Security/QA | 4 | 待开发 |
| M17-07 | `1.0.0` 发布门 | 真实项目、恢复演练、手册、CI、漏洞和人工审批全部通过；否则保持 Preview/Pilot | M15-05,M16-08,M17-05 | PO/QA | 3 | 待开发 |

## 6. 推荐的分配包

下面的分配包用于把表中的细任务交给不同的人或 Agent。一个人可以承担多个包，但每个子任务仍必须有唯一 owner。

| 包 | 包含任务 | 推荐 owner | 先后关系 | 输出 |
|---|---|---|---|---|
| A｜治理发布 | M00-01～06、M14-01 | PO + Platform | 立即开始 | public 仓库、分支/CI、版本和任务账本 |
| B｜合同状态 | M01-01～06、M03-03 | WF | A 后 | `ResearchState`、handoff、迁移和状态机 |
| C｜证据门禁 | M02-01～09、M14-06 | Evidence + Security | B 并行 | EvidenceBundle、Gate、H3 审批和审计 |
| D｜存储恢复 | M04-01～06、M15-05～06 | Backend + DevOps | B/C 并行 | canonical store、outbox、迁移、备份恢复 |
| E｜工作流闭环 | M03-01～07、M13-01～03 | WF + Platform | B/C/D 后 | 离线 idea 到缺口稿的稳定 run |
| F｜文献切片 | M05-01～07、M06-01～07 | Retrieval + Paper Scientist | E 后 | 可授权 corpus、检索报告、阅读卡和 gold set |
| G｜创新执行 | M07-01～06、M08-01～07 | Paper Scientist + Experiment | F 后 | innovation hypothesis、RunManifest 和结果 Gate |
| H｜写作审核 | M09-01～06、M10-01～06 | Writing + Review | G 后 | 结果稿/缺口稿、引用一致性和审核回路 |
| I｜知识进化 | M11-01～08、M12-01～06 | KB/ML | C/F/G 后 | 六分区知识库、分级检索、经验和 proposal |
| J｜交付运维 | M13-04～07、M15-01～07、M17-01～07 | Frontend + DevOps + Security | E/I 后 | 面板、审计、备份、生产化和发布报告 |
| K｜真实试点 | M16-01～08 | PO + 全体 | F/G/H 后 | 仅针对一个真实项目的 Pilot 报告 |

可并行关系：A/B/C/D 可以有条件并行；F 与 I 的纯 schema 工作可以并行，但真实召回、ContextPack 和经验晋级必须等语料/事件；J 不应在核心 Gate 未稳定前做“漂亮 UI”。

## 7. 每个任务的交接模板

将下列模板复制到 `.ai-team/TASK.md` 或 PR 描述中，禁止用整段聊天上下文交接：

```yaml
task_id: M05-04
title: 题录去重和版本归并
owner: <唯一负责人>
status: active
goal: 一句话说明本任务要改变的行为
inputs:
  - contract_or_artifact_id: <稳定 ID>
  - source: <数据/接口/文件>
outputs:
  - artifact: <文件或 API schema>
  - evidence: <evidence ID>
dependencies:
  - M05-02
acceptance:
  - positive: <正例>
  - negative: <负例/阻断例>
  - regression: <回归命令或人工检查>
gate:
  required: L1
  decision: PASS | REVISE | INTERRUPT | DENY
risks:
  - <未验证的外部条件或许可风险>
verification:
  command: <可复现命令>
  result: <实际结果，不写估计>
next_step: <完成后的唯一下一步>
handoff_to: <下一 owner>
```

## 8. Definition of Done

任务负责人提交前必须逐项确认：

- [ ] 任务只改变一个清晰边界，没有顺手扩展到未分配模块。
- [ ] 所有输入和输出都有稳定 ID 或版本化文件，不把全文或整段聊天塞入 handoff。
- [ ] 至少一个成功场景和一个 fail-closed/unknown 场景已经验证。
- [ ] 没有虚构论文、引用、实验结果、人工审批、外部发送或发布结果。
- [ ] 证据等级、Gate 决定和人工动作写入审计时间线。
- [ ] 代码、测试、文档、`.ai-team/TASK.md` 和 Project-to-Act 状态一致。
- [ ] 运行 `ruff`、`pytest -W error`、`doctor`、项目账本校验和 `node .ai-team/check.mjs`；跳过项必须写明原因。
- [ ] 变更没有提交密钥、全文复制件、私有来源、原始模型提示或原始工具输出。

## 9. 当前建议的第一批任务

若现在开始分配，建议按下面顺序建立 4 个短周期：

1. **短周期 1：发布和合同加固**：M00-05、M00-06、M01-02、M01-05、M03-06、M04-04。
2. **短周期 2：证据闭环和真实语料准备**：M02-07、M02-09、M05-06、M16-01、M16-02。
3. **短周期 3：阅读/创新/实验质量**：M06-06、M06-07、M07-04、M08-02、M08-03、M08-06。
4. **短周期 4：论文交付和知识进化**：M09-03、M09-05、M10-02、M11-05、M12-05、M15-05。

短周期 2 中的 `M16-01` 是用户输入门；没有真实 idea、领域、目标 venue、授权全文和实验资源，就只能完成基础工程，不能把项目标成“真实论文闭环”。

## 10. 分配记录表

复制本表作为项目团队的实际分配台账；不要直接覆盖功能表中的状态。

| 任务 ID | Owner | 分支/PR | 开始 | 目标完成 | 状态 | Gate | evidence ID | 阻塞/备注 |
|---|---|---|---|---|---|---|---|---|
| M00-05 |  |  |  |  | 待分配 | L1 |  |  |
| M01-02 |  |  |  |  | 待分配 | L1 |  |  |
| M02-07 |  |  |  |  | 待分配 | L2 |  |  |
| M04-04 |  |  |  |  | 待分配 | L2 |  |  |
| M16-01 | 用户/PO |  |  |  | 外部阻塞 | H1 |  | 需要真实项目参数 |

