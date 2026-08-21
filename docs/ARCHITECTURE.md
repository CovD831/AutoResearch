# AutoResearch 架构说明

## 1. 架构目标

AutoResearch 把科研过程建模为“Agent 负责认知任务、确定性服务负责安全与一致性、项目文件夹负责长期治理”的系统。基础版可以从 idea 启动真实工作流，遇到缺论文、缺实验、审核打回或缺人工批准时按规则停止。

当前版本为 0.1.0 foundation。它是完整的基础架构和可运行纵向切片，不等于已经完成真实论文项目，也不等于生产级多租户部署。

## 2. 组件关系

    CLI / FastAPI
          |
    AutoResearchApplication
          |
    LangGraph parent graph + SQLite checkpointer
          |
    +----------------- exactly five agents -----------------+
    | Orchestrator | Paper Search | Paper Reader | Writer   |
    | Reviewer                                             |
    +-------------------------------------------------------+
          |
    deterministic services
    evidence | gate | handoff | state machine | execution
    project | knowledge | profile | experience | evolution
          |
    SQLite canonical store + Wiki/Graph partitions
          |
    paper-projects/<project_id>/.project-to-act

LLM 是可选认知增强器，不是授权器。LLM 不可覆盖 GateDecision、状态迁移、证据有效性或外发人工审批。

## 3. 五个 Agent

| Agent | 核心输入 | 核心输出 | 明确禁止 |
|---|---|---|---|
| 总控 Agent | idea、项目约束、证据引用 | research charter、检索式、工作包、结构化派单 | 自行确认创新或实验结果 |
| 论文搜索 Agent | 检索式、seed paper | 去重 PaperRecord、题录证据、检索诊断 | 无结果时编造论文 |
| 论文读取 Agent | PaperRecord、全文或摘要 | ReadingCard、陪读回答、InnovationCandidate | 把摘要推断写成全文事实；把候选写成已证实创新 |
| 写作 Agent | 放行的阅读卡、证据、实验记录 | 论文草稿、修改/润色版本、缺口清单 | 新增无证据数字；把草稿标记为可发布 |
| 审核 Agent | 候选、稿件、Evidence IDs | ReviewReport、Gate 建议、定向打回 | 修改证据后自批；越过人工外发 Gate |

总控和审核在父图中会被不同阶段复用，但 registry 中业务 Agent 仍严格为五个。服务节点不能被路由成 Agent。

## 4. LangGraph 结构

父图节点顺序：

1. orchestrator_scope
2. paper_search
3. paper_reader
4. reviewer_innovation
5. orchestrator_execution
6. writer
7. reviewer_manuscript
8. release_gate（仅请求外发时进入）

每个业务节点调用对应 Agent 的 LangGraph 子图。SQLite checkpointer 以 run_id 作为 thread_id。L4 节点调用 interrupt；恢复必须用同一个 run_id 和 Command(resume=...)。

父状态只保留 typed state、稳定 ID、短诊断和不超过 2000 字符的 bounded_context。论文全文、完整聊天和大产物不进入 handoff。

## 5. 数据与持久化

基础版使用两个 SQLite 文件：

- autoresearch.sqlite3：规范记录、证据、门禁、知识页、图边、审计事件。
- checkpoints.sqlite3：LangGraph checkpoint、interrupt 与恢复游标。

RecordStore 使用 kind + record_id 作为主键，project_id 和 partition_name 作为检索边界。关键操作同时写 append-only audit_events。

基础版 SQLite 适合本地开发和单进程验证。生产部署目标仍是 PostgreSQL/pgvector 规范源、对象存储大产物和可重建的 Neo4j 投影；当前代码没有把 SQLite 冒充该生产拓扑。

## 6. 运行边界

- 默认 network_enabled=false，只处理用户授权的 seed papers。
- 打开网络后可调用 OpenAlex、Crossref、Semantic Scholar；连接器失败返回诊断。
- 默认 LLM_PROVIDER=offline，确定性路径仍能运行。
- 配置模型时，只从受管环境读取 API 配置。
- 外部投稿、邮件、公开发布、删除和高成本实验均不在基础版自动执行范围。
