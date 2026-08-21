# 项目版本

> 只在版本号、发布状态、升级路径或兼容性发生变化时读取和更新。

## 当前版本

- 版本号：`0.1.0`
- 版本代号：Foundation Preview
- 发布状态：本地基础架构可运行；不是生产发布，也未完成真实论文验收
- 兼容性说明：已验证 Python 3.12.10、LangGraph 1.2.11、langgraph-checkpoint-sqlite 3.1.1、Pydantic 2.13.4、FastAPI 0.141.1；SQLite profile 仅承诺本地单进程基础验证。
- 最后更新：2026-08-22

## 下一版本计划

- 目标版本：`0.2.0-literature-pilot`
- 计划内容：真实论文 idea/gold corpus、许可明确全文、检索/阅读人工评测、RunManifest 与真实 baseline 试点，并补 checkpoint 重启和幂等回归。
- 发布条件：P1 严格验收补齐；至少一个真实论文项目从检索到本地缺口稿件保留完整 evidence/gate/handoff/run 链；不把试点结果外推为通用质量。

## 版本路线

| 版本 | 目标 | 主要范围 | 发布 Gate |
|---|---|---|---|
| `0.1.0-plan` | 规划基线 | 计划书、功能表、项目模板、验收与差距分析 | 文档和账本验证 |
| `0.1.0` | Foundation Preview | 可运行五 Agent 纵向切片、SQLite checkpoint、CLI/API、基础知识与进化 | foundation 自动化与本地旅程 |
| `0.2.0-literature-pilot` | 文献试点 | 真实 corpus、人工 gold set、RunManifest 与真实本地论文项目 | P1/P2 严格验收 |
| `0.3.0-literature` | 文献闭环 | 多源检索、全文读取、陪读、论文库、claim map | P2 验收 |
| `0.4.0-research` | 研究执行 | 创新反检索、工作包、RunManifest、结果验证 | P3 验收 |
| `0.5.0-writing` | 稿件闭环 | 提纲、写作、修改、润色、引用和审核 | P4 验收 |
| `0.6.0-learning` | 知识与进化 | Wiki+Graph、分级检索、画像、经验晋级/降级 | P5 验收 |
| `1.0.0` | 可交付 | 真实端到端论文项目、备份恢复、手册和安全验收 | P6 全部 Gate |

## 版本历史

按时间倒序追加：版本号、日期、状态、主要变更、原因、兼容性、证据 ID 和 Gate 结果。

- `0.1.0`｜2026-08-22｜Foundation Preview｜严格五 Agent、LangGraph/SQLite、证据门禁、检索/阅读/创新/工作包/稿件、Wiki+Graph、画像/经验/提案、CLI/API 和项目运行投影｜原因：用户要求架构和基础功能完整落地｜兼容性：仅经验证的 Python 3.12 本地 profile；旧规划文档无运行时兼容承诺｜证据：E-RUN-001、E-JOURNEY-001、E-LIVE-001、E-PROJECT-001｜Gate：G-FND-001 PASS，P1–P6 严格 Gate 未全部通过。
- `0.1.0-plan`｜2026-08-21｜规划交付完成｜建立规划、功能、项目模板与验收基线｜原因：先固化架构和不可变约束｜兼容性：仅文档，不代表运行时实现｜证据：E-PLAN-001、E-TPL-001｜Gate：G-P0-001 PASS。
