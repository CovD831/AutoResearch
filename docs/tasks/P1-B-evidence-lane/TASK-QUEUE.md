# B 线任务队列

| Task | 状态 | 依赖 | 交付重点 |
|---|---|---|---|
| B1 P1-B Evidence/Evaluation Pipeline | handed-off | — | admission、readiness、benchmark plan、section validation |
| B2 P1-B Evidence Adversarial | ready-next | B1 | 冲突、缺口、规则和 fail-closed fixture |
| B3 S2 Audit Evidence | waiting-for-gate | S1 promotion | verdict、reconciliation、candidate 回流 |
| B4 S3 Reader/Writer Ports | ready | S2 promotion | typed reader/writer、LLM/MCP contract |
| B5 S3-B 真实数据源与解析层（2026-09-10 重排编号） | accepted（PR #17 合入 `7fdfb89`，2026-09-11） | B4 accepted + S3 promotion | Crossref + Retraction Watch 核验数据源（**撤稿判据读 `updated-by[]`**）、PDF 解析层（docling 默认 / pymupdf4llm 兜底，ADR-01 槽位 3；**解析路径未验证**）、ScholarQABench 三指标 |
| B6 S4 Real Pilot | planned | S3 promotion + B5 | 真实试点、claim audit、交叉评审盲审对比（EvoMap 吸收）、manuscript evidence |
| B7 MVP Manuscript Delivery | planned | I3 + B6 | 最小稿件组装、审核和本地交付 |

每个任务独立 PR；本表只描述顺序，不替代详细验收。
