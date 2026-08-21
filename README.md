# AutoResearch

AutoResearch 是一个以证据为边界、以项目文件夹为账本的 LangGraph 多 Agent 科研工作流。它覆盖 idea 拆解与深化、论文检索、阅读总结、创新点候选、工作包、写作、审核、自进化提案和经验沉淀。

系统严格保持五个业务 Agent：

1. 总控 Agent
2. 论文搜索 Agent
3. 论文读取 Agent
4. 写作 Agent
5. 审核 Agent

证据、门禁、状态机、知识库、用户画像和经验沉淀均为确定性服务，不伪装成额外 Agent。门禁拒绝时工作流不会越级；缺实验结果时，写作 Agent 只能输出明确标记缺口的研究草稿。

## 快速开始

    py -3.12 -m venv .venv
    .venv\Scripts\python.exe -m pip install -e ".[dev]"
    .venv\Scripts\autoresearch.exe doctor
    .venv\Scripts\autoresearch.exe init-project demo "Evidence-aware agents"
    .venv\Scripts\autoresearch.exe run demo --idea "研究证据门禁对多 Agent 科研可靠性的影响"

默认离线运行。需要模型时，使用本机 llm-api-config 向 .env.local 注入受管档案，不要把密钥写进命令、源码或提交记录。

启动 API：

    .venv\Scripts\autoresearch.exe serve --host 127.0.0.1 --port 8010

文档入口：

- docs/ARCHITECTURE.md：总体架构与五 Agent。
- docs/FUNCTION_MATRIX.md：基础版功能表与生产边界。
- docs/WORKFLOW_AND_STATE.md：状态机、handoff、checkpoint/resume。
- docs/EVIDENCE_AND_GATES.md：证据等级与 L0–L4 门禁。
- docs/KNOWLEDGE_AND_EVOLUTION.md：Wiki+Graph、画像、经验与自进化。
- docs/API.md、docs/OPERATIONS.md、docs/DEVELOPMENT.md：接口、运行和开发。
- docs/AutoResearch_详细计划书.md：完整产品路线。
- docs/AutoResearch_任务拆解书.md：按模块、依赖、负责人和验收目标分配工作。
- docs/AutoResearch_任务拆解书_详细版.md：需要继续细化时使用的历史详细拆解附录。

项目治理见 .project-to-act，当前协作任务见 .ai-team/TASK.md。
