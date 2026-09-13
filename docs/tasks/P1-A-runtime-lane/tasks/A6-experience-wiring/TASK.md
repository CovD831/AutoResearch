# A6 Experience Wiring

状态：`handoff`（2026-09-12 已 rebase 到 `origin/main@1e7e196` 并完成实现与自动验证）。完整目标、交付物、边界和验收见 `../../TASK-SPECS.md` 的 A6 节。

要点注记（实现前必读，均为已冻结条款或本包开工时确认的事实）：

- **「订阅 / 推送钩子」在结构上不可行**：`evidence.candidate_blocked` 的产生点是 `src/autoresearch/audit_evidence.py`（B3 独占 allowed path，属 **B 线 evidence 路径**，A6 被明令禁止触碰），`audit.report_created` 的产生点是 `src/autoresearch/audit.py`（A3 独占）。产生侧无法插钩子，故「事件消费钩子」只能实现为**对已落地事件日志的只读消费**（`RecordStore.events(project_id)`），这也是「只读消费 + 不改审计链」最贴合的实现。→ D-A6-01
- **无事件级 replay/subscribe 抽象**：全仓只有 A1/A2 的 `idempotency` 底座（`RecordStore.remember_idempotent / get_idempotent / delete_idempotent`）。去重与重放安全直接复用该底座，不新建表、不改 `storage.py`。→ D-A6-02
- **不得给自动晋级留路径**：自动沉淀写出的记录 `grade` 恒为 `EvidenceGrade.E0`（`ExperienceRecord` 默认值），且**永不调用** `ExperienceService.promote`。`promote` 的四门槛（`recurrence_count>=2` + `grade∈{E2,E3,H3}` + `reviewer_approved` + `human_approved`）保持原样。`evolution_service.py` 列入本包 `forbidden_paths`，使该约束机械可证。→ D-A6-03
- **只写 experiences 分区**：全部写入经 `ExperienceService.record`（它自身只写 `KnowledgePartition.EXPERIENCES` 的 record 与 WikiPage 镜像），本包不直接调 `KnowledgeService.add_page`。
- **降级方向**：拦截事件源不可用 / 单条 payload 畸形 → 不抛异常、不阻塞调用方，返回的诊断里可见；主管线行为不变。
- **生产可达性**：本包必须给出真实触发通路（`Application` 方法 + HTTP 端点 + CLI 子命令），否则重演 O12 的「接线了但生产上永不触发」缺陷。
- 基线口径：本包当前基于 `origin/main@1e7e196`。看本包真实改动使用 `--base origin/main`。
