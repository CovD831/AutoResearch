# 本地运行与运维手册

## 1. 环境

- Windows 10/11 或兼容 Python 环境。
- Python 3.12。
- 当前验证依赖 LangGraph 1.2.11、Pydantic 2.13.4、FastAPI 0.141.1。
- 本地基础版不需要 Docker、PostgreSQL 或 Neo4j。

安装：

    py -3.12 -m venv .venv
    .venv\Scripts\python.exe -m pip install -e ".[dev]"
    .venv\Scripts\autoresearch.exe doctor

doctor 只输出密钥是否配置，不输出密钥值。

## 2. 项目与运行

创建项目：

    .venv\Scripts\autoresearch.exe init-project paper01 "My paper" --idea "..."

执行离线 run：

    .venv\Scripts\autoresearch.exe run paper01 --idea "..."

传入用户有权使用的题录/全文：

    .venv\Scripts\autoresearch.exe run paper01 --idea "..." --seed-file seeds.json

seed JSON 每项可包含 title、abstract、authors、year、doi、url、source、source_record_id、full_text_path。全文必须来自开放获取或用户有权提供的位置。

查看运行：

    .venv\Scripts\autoresearch.exe status run_xxx --checkpoint

## 3. 模型配置

默认离线。模型配置只通过本机 llm-api-config 受管档案注入 .env.local。不得：

- 把 API key 写进 .env.example、README、测试、Git 或命令历史。
- 输出 .env.local 内容。
- 在日志中打印 Authorization header。

模型不可用时，检索式、阅读、门禁、草稿与审核仍有确定性退化路径。

## 4. 网络检索

将 AUTORESEARCH_NETWORK_ENABLED 设为 true 后，PaperSearchService 尝试 OpenAlex、Crossref 和 Semantic Scholar。任一源失败会记录连接器名和异常类型，其他源继续。所有源均失败且没有 seed paper 时 run 进入 WAITING_EVIDENCE。

网络启用不授权绕过付费墙、不授权抓取受限全文，也不代表检索质量已经通过领域 gold set。

## 5. 数据目录

默认：

- var/autoresearch.sqlite3
- var/checkpoints.sqlite3
- paper-projects/<project_id>
- paper-projects/<project_id>/.project-to-act

var 和 .env.local 已在 .gitignore 中。项目文件夹中的研究资产可能包含版权或敏感内容，提交前需人工确认。

## 6. 备份与恢复

基础版建议停机后同时备份两个 SQLite 文件和对应 paper-projects 目录。只备份数据库或只备份项目文件都不能形成完整恢复点。

当前版本尚未执行正式备份/恢复演练；生产部署前必须补充一致性水位、校验和、恢复测试和保留策略。

## 7. 常见阻断

| 现象 | 含义 | 处理 |
|---|---|---|
| blocked at literature search | 无真实论文 | 打开受控网络或提供 seed papers |
| blocked after manuscript | 实验/独立来源/闭环不足 | 登记真实证据，启动新 run |
| interrupted at release | 等待人工外发批准 | 检查稿件和 ledger 后 resume |
| unresolved reading answer | 供应文本不包含答案 | 提供授权全文或缩小问题 |
| work package 409 | 完成状态缺有效证据 | 先登记并绑定真实产物 |

## 8. 服务启动

    .venv\Scripts\autoresearch.exe serve --host 127.0.0.1 --port 8010

默认只绑定 loopback。未配置认证和 TLS 前，不要绑定 0.0.0.0 或暴露公网。
