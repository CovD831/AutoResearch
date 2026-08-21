# 开发指南

## 1. 目录

- src/autoresearch/agents：严格五个业务 Agent 及子图 helper。
- src/autoresearch/graph.py：LangGraph 父图和 L4 interrupt。
- src/autoresearch/contracts.py：Pydantic 契约与 enum。
- src/autoresearch/*_service.py：确定性业务服务。
- configs：Agent、workflow、evidence policy 的可读配置。
- tests：合同、Gate、知识分区、工作流、API/CLI 测试。
- paper-projects/_template：论文项目 canonical 模板。
- .project-to-act：产品级长期治理账本。
- .ai-team：VibeCollab 当前任务事实源。

## 2. 本地检查

    .venv\Scripts\ruff.exe format src tests
    .venv\Scripts\ruff.exe check src tests
    .venv\Scripts\pytest.exe
    .venv\Scripts\autoresearch.exe doctor
    node .ai-team/check.mjs --base main
    py -3.12 C:\Users\zzg\.codex\skills\project-to-act\scripts\init_project_management.py --project-root . --validate

任何“完成”提交都必须同时更新测试、.ai-team/TASK.md 和必要的 Project-to-Act 里程碑。

## 3. 设计约束

- 业务 Agent enum 和 registry 必须恰好为五个。
- 新增安全、检索或存储能力时优先实现 service，不新增第六个 Agent。
- Agent 之间只传 HandoffEnvelope 和稳定引用。
- Gate 是同步确定性决策，LLM 不得覆盖。
- 所有外部副作用在 interrupt 之后执行，并使用稳定幂等键。
- 未执行的实验保持 unknown/placeholder。
- 修改节点名、state channel 或 checkpoint schema 前必须设计迁移。
- 新增 endpoint 不能绕过 application/service 的规则。

## 4. 新增科研连接器

连接器实现 ScholarlyConnector：

- name 是稳定来源名。
- search(query, limit) 返回统一题录 dict。
- 网络错误必须抛给聚合器转成诊断。
- 不得在连接器内构造虚假 fallback 论文。
- DOI、source_record_id、URL 和许可信息尽可能保留。
- live 测试需使用小 limit、缓存和服务条款允许的调用频率。

## 5. 测试策略

每个新增功能至少覆盖：

1. 正常合同。
2. 缺字段或越权负例。
3. 证据不足。
4. 重复/resume 幂等。
5. 审计事件。
6. 不泄露秘密。
7. 真实与 unknown/blocked 分离。

## 6. 版本策略

当前 state.schema_version=1，workflow_id=autoresearch-default-v1。数据库或 checkpoint schema 变化必须提升兼容版本；不能仅修改代码后继续复用旧 paused thread。
