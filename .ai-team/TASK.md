# Current Task

- ID: `AR-003`
- Title: `Simplify the assignment plan to module level`
- Status: `done`
- Owner: `zzg`
- Next owner: `user/team`

## Goal

根据用户反馈，把任务拆解入口从 122 个子任务收敛为模块级分配。保留此前详细版作为附录，但当前团队先按模块认领负责人、边界、主要产出、依赖和验收目标。

## Acceptance scenarios

- [x] `docs/AutoResearch_任务拆解书.md` 只作为模块级分配入口，覆盖 M00–M17。
- [x] 每个模块说明目标、边界、主要交付物、前置模块、负责人建议和当前状态。
- [x] 文档提供模块负责人验收模板和第一批模块分配建议。
- [x] 原 122 子任务版本保留为 `docs/AutoResearch_任务拆解书_详细版.md`，不丢失后续拆解素材。
- [x] README、Project-to-Act 和 VibeCollab 任务状态保持一致，不改变五业务 Agent 和证据门禁边界。

## Invariants

- 当前入口不要求团队一次性拆到函数、接口或工单；模块负责人后续再自行细化。
- 详细版是参考材料，不代表所有子任务都已实现或已验收。
- 真实论文试点、生产数据库、Web UI、灾备和性能仍保持原有“外部阻塞/待开发”状态。
- 不提交 token、密钥、私有来源、完整论文、原始提示或虚构外部结果。

## Decisions

- 使用 M00–M17 作为稳定模块 ID，先按模块分配负责人。
- 保留详细拆解版，避免未来重新整理时丢失依赖和验收素材。
- `.project-to-act` 继续作为长期项目事实源；`.ai-team/TASK.md` 只记录本次短周期交付。

## Completed

- 将原 `docs/AutoResearch_任务拆解书.md` 移为 `docs/AutoResearch_任务拆解书_详细版.md`。
- 新建模块级 `docs/AutoResearch_任务拆解书.md`，包含 18 个模块、执行阶段、负责人模板和首批分配建议。
- 保留 README 任务书入口，并将 AR-003 的状态、范围和下一步写入协作账本。

## Pending

- 用户/团队需要为模块负责人模板填写实际 owner、分支、目标日期和 evidence ID。
- 模块负责人确认后，再选择需要展开的模块，不默认展开全部模块。
- 真实论文试点仍等待 idea、领域、目标 venue、授权全文和实验资源边界。

## Next step

先认领 M01–M04、M05–M07、M08、M09–M10、M11–M12、M13–M15/M17、M16 这 7 个模块包；完成模块边界确认后，再只对当前瓶颈模块做子任务拆解。

## Verification

- [x] Project-to-Act `--check` — managed 配置有效，唯一账本保持不变。
- [x] 模块文档结构检查 — M00–M17 全部存在，详细版文件可访问。
- [x] `node .ai-team/check.mjs --base main` — AR-003 acceptance 5/5，任务范围和变更同步有效。
- [x] Project-to-Act `--validate` — managed 配置 valid，issues 为空。

## Handoff note

- From: `zzg`
- To: `user/team`
- Summary: 当前分配入口已经降为模块级；详细拆解保留在附录。先分模块负责人，后续只对真正需要的模块继续细化。
