# AutoResearch 0.1.0 Foundation 验证证据

- 验证日期：2026-08-22（Asia/Shanghai）
- 验证对象：feat/ar-001-foundation 工作树
- 范围：本地基础架构、CLI/API、五 Agent 工作流、证据门禁、项目文件夹投影
- 明确不包含：真实论文质量、真实实验结果、外部投稿、生产部署与灾备

## E-RUN-001：干净 Python 3.12 验证

环境：

- Python 3.12.10
- LangGraph 1.2.11
- langgraph-checkpoint-sqlite 3.1.1
- FastAPI 0.141.1
- Pydantic 2.13.4
- PyPDF 6.16.1

命令与结果：

    py -3.12 -m venv .venv
    .venv\Scripts\python.exe -m pip install -e ".[dev]"
    .venv\Scripts\ruff.exe check src tests
    .venv\Scripts\pytest.exe -W error
    .venv\Scripts\pytest.exe --cov=autoresearch --cov-report=term-missing:skip-covered
    .venv\Scripts\autoresearch.exe doctor

观察结果：

- 安装退出 0。
- Ruff 无问题。
- 18 tests passed，warnings-as-errors 退出 0。
- 语句覆盖率 84%。
- doctor 返回 ok=true、agent_count=5，Agent IDs 为 orchestrator、paper_search、paper_reader、writer、reviewer。
- doctor 只显示 LLM 配置布尔状态，不显示密钥。

## E-JOURNEY-001：真实本地 HTTP 客户旅程

使用 aawo-agent-tester，通过真实 127.0.0.1:18110 listener 测试；服务使用隔离数据库和 var/journey-projects，完成后按精确 PID 70064 停止。

| Scenario | 业务终态 | Journey status | Report SHA-256 |
|---|---|---|---|
| health.read-only | ok=true、agent_count=5 | pass | 849CB9EE2CD0C9F987BF122232E83E892347A9DF03B16C36CD35CFCD00B6114E |
| project.create-isolated | 项目 active、路径在隔离目录 | pass | 12F5B615455A2A76E06D256D0FA3DD13B1EE74C454878CC34F9AE472F4FFA209 |
| run.no-paper-fail-closed | run blocked、waiting_evidence、0 paper | pass | 2278150C5E76F21DC0A954D8B1FA2AFC76EAEAFCF3D187F2995C65CED24FF43C |
| run.abstract-to-evidence-gap-draft | 2 reading cards、1 innovation、1 manuscript；L3 blocked | pass | 95CF7B278C6838B98DFB2EEE0F2B43DA71CE2410DDD1165D0C1D7AD664DA445D |

原始报告和 append-only tester ledgers 位于 evidence/journeys/。首次 health runner 因 ledger 父目录不存在而发生 invocation error；创建受控目录后原样重跑并通过。该错误不被转换为 pass，也不属于 AutoResearch 服务故障。

## E-LIVE-001：外部边界最小探测

论文连接器，query limit=1：

- OpenAlex：HTTP 调用成功，返回 1 条真实题录。
- Crossref：HTTP 调用成功，返回 1 条真实题录。
- Semantic Scholar：当前返回 HTTPStatusError；系统会形成源级诊断，未伪造 fallback。
- 此探测只证明当时的 transport/解析边界，不证明召回质量或持续可用性。

LLM：

- 使用 llm-api-config 将已有 deepseek 受管档案注入 ignored .env.local。
- doctor 显示 provider=openai-compatible、model=deepseek-v4-flash、base URL/key configured=true。
- 最小 JSON connectivity call 成功，仅检查结果存在及 key 列表。
- 没有读取或输出 .env.local、API key 或 Authorization header。
- 此探测不证明学术生成质量。

## E-PROJECT-001：论文项目文件夹治理

自动化验证：

- 模板实例化后 PROJECT_MANIFEST.yaml 的 project_id/title/status/thread 字段被替换。
- 已存在项目拒绝覆盖。
- 每个 run 终态/interrupt 更新 manifest、state/RUN_INDEX.jsonl 和子项目 PROJECT_PROGRESS.md 的受控 runtime 区块。
- 没有真实论文时，子项目进度明确记录 waiting_evidence，而不是写成完成。
- 稿件写入 05_writing，修改版本不覆盖原稿。

## E-COLLAB-001：VibeCollab 与长期账本一致性

    node .ai-team/check.mjs --base main

结果：AR-001 状态 done，acceptance 9/9，private sessions disabled，Result=valid。Project-to-Act 根目录和 paper-projects/_template 使用官方脚本校验，均 valid=true、issues=[]。

## 限制

- 测试 seed papers 是隔离的合成题录，不是文献真实性或创新性证据。
- E3 experiment evidence 在自动化中是显式测试 fixture，不是现实实验结果。
- SQLite 基础版未做跨进程并发、断电恢复或备份恢复演练。
- 没有测试自动投稿，因为基础版没有该副作用执行路径。
