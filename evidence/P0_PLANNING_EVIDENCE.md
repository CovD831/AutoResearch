# P0 规划交付证据

- 证据日期：2026-08-21
- 证据范围：AutoResearch 详细计划、功能表、根 Project-to-Act、论文项目模板、现有 DeepReason 候选底座核验
- 结论边界：本证据只支持“P0 规划交付完成”，不支持“AutoResearch 产品已实现或已验收”

## E-BASE-001：现有候选底座

- 方法：读取 `DeepReason-Agents-Framework/AGENTS.md`、`pyproject.toml`、内置 AutoResearch 模板和证据/门禁/知识/记忆/自进化代码；运行相关回归。
- 命令：`python -m unittest tests.test_evidence_and_gates tests.test_knowledge_memory_evolution tests.test_workflow_spec -v`，运行时 `PYTHONPATH=src`。
- 退出状态：0。
- 结果：28 tests OK；测试后嵌套仓库工作树 clean。
- 关键事实：现有模板有 14 个 Agent；LangGraph 在 `pyproject.toml` 中是 optional dependency；因此只能作为参考底座，不能视为严格五 Agent LangGraph 目标实现。

## E-WEB-001：官方能力核验

- LangGraph Persistence：<https://docs.langchain.com/oss/python/langgraph/persistence>
- LangGraph Subgraphs：<https://docs.langchain.com/oss/python/langgraph/use-subgraphs>
- LangGraph Interrupts：<https://docs.langchain.com/oss/python/langgraph/interrupts>
- OpenAlex API：<https://help.openalex.org/api/>
- OpenAlex Works：<https://developers.openalex.org/api-reference/works/list-works>
- Crossref REST API：<https://www.crossref.org/documentation/retrieve-metadata/rest-api/>
- Semantic Scholar Academic Graph API：<https://www.semanticscholar.org/product/api>
- 核验日期：2026-08-21；实现启动时需重新核验接口、限流和版本。

## E-PLAN-001：计划与功能表

| 检查 | 结果 |
|---|---|
| 根 Project-to-Act `--validate` | PASS |
| 用户要求关键词 | 22/22 |
| 五 Agent 角色表 | 恰好 5 行 |
| 功能 ID | 86 个、唯一 |
| 功能表字段 | 每行 7 列；优先级/状态合法 |
| 相对链接 | 4 个，全部有效 |
| 密钥样式扫描 | 29 个交付文件，未发现 |
| 产品完成措辞边界 | 明确为“规划交付完成；运行时未实现” |

## E-TPL-001：论文项目模板

| 检查 | 结果 |
|---|---|
| 模板 Project-to-Act `--validate` | PASS |
| 必需路径 | 20/20 |
| 模板文件总数 | 21 |
| 外部发布默认值 | `false` |
| 大对象/密钥边界 | README 与 manifest 已明确 |

## SHA-256

| 对象 | SHA-256 |
|---|---|
| `docs/AutoResearch_详细计划书.md` | `2b0b0d84f794df047383a0a18efd5f138bd3ac3c396890230ce03b4637a60c1b` |
| `.project-to-act/PROJECT_OVERVIEW.md` | `5fd9af51c74e886454d8d9bae7ceff33db1bc55b431fa1386f7d7d1427471da1` |
| `.project-to-act/PROJECT_PROGRESS.md` | `b164e4bef1766308d9dcf1cad8a8924a300c7a0844e2a6f4165997a6b0b50f12` |
| `.project-to-act/PROJECT_FEATURES.md` | `6708f591af81af70a99e491e3ccba25349413ed2718f9258ead195fa1dcb0203` |
| `.project-to-act/PROJECT_VERSIONS.md` | `e6974e0f3191e0187e6337adfdb875b41d490fa9c67bfdefa86aec8100cc966e` |
| `paper-projects/_template` 规范化相对路径+文件 hash 清单的树 hash | `8e9926a6d7d0abbbe1bf10d706a714d6d7198c5a7bf4cd7b047249e9ff5368a2` |

模板树 hash 的计算输入为按绝对路径排序后的 21 个文件，以模板相对 POSIX 路径和单文件 SHA-256 组成记录，再对 UTF-8 记录串计算 SHA-256。模板任一文件变化后本证据失效。
