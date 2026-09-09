# Owner 线任务队列（P1-I Owner Lane）

Owner 职责定位（2026-09-09 确定）：成员 PR 审核与合并、小修不打回直接补 follow-up PR、独立裁决与集成收口。Owner 线与成员 A/B lane 并行推进，Owner 侧改动继续走 main 直推（保护窗口流程）或 follow-up PR，不改变现有集成流程。

本表为 Owner 全量工作视图：先列已完成（历史节选），再列未完成（排队，按触发时机排序）。

## 一、已完成（历史节选，详见 git log 与 .ai-team/TASK.md）

- 09-04 团队协作基线：repo-task-sync 体系、bot-first PR 审查工作流 + CI 审查检查、异步团队基线（8d821c0 / d26c54f / c0f8fbc / fd0f204）
- 09-04~06 P1 双 lane 拆分：任务包、验收标准、任务注册表（docs/tasks/ · TASK-PACKAGE-REGISTRY.md）
- 09-07 PR #1/#2 深度审查 → findings 转 B2/A2 Gate 条款（PR #3）
- 09-08 B2 follow-up PR #6（小修不打回直接补的职责先例）
- 09-09 A2 贴合度复审 + follow-up PR #7（F-4 审计原子化、StaleIdempotencyWriteError、recovery API 清理）
- 09-09 I0 契约统一（72fb544）→ I1 编排（6b706df）→ I2 主线 E2E + S1 promotion（dad4658，S2-A/S2-B 转 ready）
- 09-09 S2 MCP scope 裁决（15a5490，登记进 A3/B3 TASK-SPECS）

## 二、未完成（排队）

| Task | 状态 | 依赖 / 触发时机 | 交付重点 | 预估 |
|---|---|---|---|---|
| O1 成员 PR 审核与 follow-up 集成 | active（常驻） | 成员每次提交；当前无悬挂 PR | 成员 PR 人工审查（bot 审查后）；小修改不打回、直接 follow-up PR 补齐（先例：PR #6、PR #7）；撞车裁决 owner 集成（先例：D-S2-01 / PR #10）；合并窗口与分支保护恢复；后续 S3/S4 PR 的深度审查并入本项。**PR 纯净性（PR #6 教训）：follow-up PR 只装代码小修；文档/归档批量入库单独开 docs PR，不得混装** | 每次 ≤0.5 天 |
| O2 F-8 R003 空结果语义裁决 | done（2026-09-10，D-F8-01） | — | 裁决文档 `docs/coord/empty-result-ruling.md`：`completed_empty` 为确定性成功终态、`unknown_outcome` 仅限中断恢复；R003 L3 已注记、TASK-SPECS A2 F-8 关闭 | 0.5 天 |
| O6 S2 promotion gate | done（2026-09-10） | S2-A/S2-B integrated | 四项核验通过（blocking 清零含 F-8 关闭 / E2E 绿 108 passed / 证据可重跑 / 下游合同稳定）→ S2-A/S2-B 转 accepted、S3-A/S3-B 转 ready（base main@535f208） | 0.5 天 |
| O7 S3 promotion gate | 未开始 | A4 + B4 均 accepted **当天** | 四项核验同上 → S4-A/S4-B 转 ready。gate 不过夜 | 0.5 天 |
| O3 I3 账本收口 | 未开始 | O6 通过后 | registry 终态回写、invariants.md 刷新、演进协议归档、validate_registry 校验 | 0.5 天 |
| O5 F-3 真实 connector 验收标准 | 未开始 | S4 开工前 | 异常→状态分类边界的复验标准定义（S4-B 真实试点验收前置，挂账见 A2 TASK-SPECS） | 0.5 天 |
| O4 B6 稿件审核 + I4 交付检查 + MVP-CLOSED 判定 | 未开始 | B6 交付后 | 稿件审核（审核不自批，owner 为审核方）、local delivery manifest 核对、MVP-CLOSED 判定、B6 成员任务映射确认 | 0.5–1 天 |

分工说明：MVP 推进不是 Owner 独占——A5/B5/B6 为成员任务；Owner 独占的是裁决与验收（上表），总量约 3 天，全部是关键路径上的触发器：成员两条线都卡在 Owner 的 gate 上，gate/审核不过夜就是最大的提速杠杆。

每个裁决/收口任务产出独立文档或 registry 回写，审查类工作（O1）以 PR review 记录为准，不单独开 PR。
