# FastAPI 接口

默认本地地址为 http://127.0.0.1:8010。OpenAPI 文档位于 /docs。

## 系统与项目

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | /health | 版本、五 Agent、配置安全摘要、数据库状态 |
| POST | /projects | 从 canonical 模板实例化论文项目 |
| GET | /projects/{project_id} | 读取项目记录 |
| GET | /projects/{project_id}/audit-events | 读取项目审计时间线 |

POST /projects 示例请求：

    {
      "project_id": "paper01",
      "title": "Evidence-aware research agents",
      "idea": "Evaluate evidence gates in multi-agent research."
    }

project_id 只接受小写字母、数字、下划线和连字符。已有目录返回 409，系统不覆盖项目。

## 工作流

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | /runs | 启动新 LangGraph run |
| GET | /runs/{run_id} | 查看运行记录 |
| GET | /runs/{run_id}?include_checkpoint=true | 同时查看 checkpoint/next/interrupt |
| POST | /runs/{run_id}/resume | 恢复 L4 人工 interrupt |

POST /runs 可包含 seed_papers。没有真实论文时返回 201，但 run.status=blocked，这是有效的 fail-closed 业务结果，不是 HTTP 故障。

POST /runs/{id}/resume：

    {
      "approval": true,
      "reviewer": "principal-investigator",
      "note": "Evidence and manuscript reviewed."
    }

非 interrupted run 恢复返回 409。

## 证据与执行

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | /evidence | 登记 EvidenceItem |
| GET | /projects/{project_id}/evidence | 列出项目证据 |
| POST | /evidence/{evidence_id}/invalidate | 追加失效状态 |
| GET | /projects/{project_id}/work-packages | 列出工作包 |
| PATCH | /work-packages/{work_package_id} | 更新 planned/in_progress/blocked/completed |

工作包标记 completed 时必须提供至少一条同项目、有效的 evidence_id，否则返回 409。

## 论文阅读与写作

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | /papers/{paper_id}/questions | 证据限定的陪读问答 |
| POST | /manuscripts/{manuscript_id}/revisions | 生成修改或润色版本 |

阅读材料不足时返回 unresolved=true，不生成猜测答案。修订不会覆盖原稿，继承 evidence IDs 和 unresolved gaps，并强制 release_ready=false。

## Wiki、Graph 与画像

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | /knowledge/pages | 新增 WikiPage |
| POST | /knowledge/edges | 新增同分区 GraphEdge |
| GET | /knowledge/search | 分区检索，level=1 或 2 |
| POST | /profiles | 新增画像项 |
| GET | /profiles/{user_id} | 查看画像项 |

knowledge/search 参数：q、partitions、level、limit、require_evidence。

## 经验与自进化

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | /experiences | 新增经验候选 |
| POST | /experiences/{id}/promote | 审核+人工双批准晋级 |
| POST | /evolution/proposals | 生成 proposal-only 提案 |
| POST | /evolution/proposals/{id}/review | 记录审核状态 |

approved_for_manual_application 不代表系统已经修改任何代码或策略。
