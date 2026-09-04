# Current Task

- ID: `P1-DUAL-WORKTREE-IMPLEMENTATION-2026-09-04`
- Title: `P1 Evaluation Section Pipeline dual-worktree implementation`
- Status: `active`
- Owner: `user/team`
- Next owner: `member A / member B`

## Goal

按 R004/R005 和 UD-006/UD-007 冻结的 P1 产品切片，在两个独立 worktree 并行实施 Evaluation Section Pipeline。成员自行编写 task-local L3 并直接实施；项目负责人负责共享边界、跨 worktree 决策和最终集成。

## Async execution model

- 全局队列：`docs/rearchitecture/TASK-PACKAGE-REGISTRY.md`。
- 路线和 Gate：`docs/rearchitecture/IMPLEMENTATION-ROADMAP.md`。
- 成员任务账本：`.ai-team/tasks/<TASK-ID>.md`；成员更新自己的账本，负责人更新本文件的集成队列。
- 成员可以在前一 PR `reviewing` 时继续 `ready-next` 或 `speculative` 任务；后续分支必须在前置任务合并后 rebase 到最新 `main`。
- `speculative` 任务不得合并或标记 accepted，直到其前置 Promotion Gate 通过。
- ZIP 只用于传输；解压后的任务包源文件必须随代码和 task-local ledger 一起进入分支。

## Acceptance scenarios

- [x] 现状耦合点基于当前代码、文档和任务账本记录。
- [x] 旧 R-001 已标记 abandoned，不再作为当前重构包。
- [x] 新建 `docs/rearchitecture/skill-test-2026-09-03/` 测试包并按新版 skill 创建 manifest。
- [x] 启动独立 review sub-agent，保存 Round 1/2 JSON 报告并建立 consumption ledger。
- [x] 新独立包完成 Round 1/2 审查，结论为 `blocked_for_handoff`。
- [x] 当前模块到目标模块映射包含 retain/expose/adapt/split 与移除门槛。
- [x] 第一条迁移切片、legacy/target fixture、失败语义、回滚边界和 promotion gate 已冻结。
- [x] 首个垂直场景、外部能力边界和 Runtime 部署边界沿用 R-002 中已记录的用户决策。
- [ ] P1-A Runtime/Recovery 通过幂等、replay、recovery 和 legacy/target parity 验收。
- [ ] P1-B Evidence/Writing Pipeline 通过 Evidence admission、readiness、benchmark plan 和 section validation 验收。
- [ ] P1 端到端 Evaluation Section Pipeline 在 A 合并后由负责人完成集成验收。
- [ ] 负责人完成 I0–I4 集成任务，并将 `MVP-CLOSED-MINIMAL-E2E` 标记为 accepted。

## Invariants

- 保留恰好五个业务 Agent；skill/MCP/plugin 是能力来源，不增加隐藏 Agent。
- Runtime 不拥有证据评级、Gate 决策或具体论文/写作工具实现。
- Evidence Module 是证据状态、失效、替代和 claim linkage 的唯一写入者。
- 不在 S1 引入通用消息总线、动态卸载、第二套数据库或未被真实消费者证明的抽象。
- 旧 `AutoResearchApplication` facade 在迁移窗口内继续可运行。
- P1-A 与 P1-B 使用独占路径；共享 `application.py`、`contracts.py` 和项目级账本由负责人维护。

## Decisions

- D-R001-01：先做设计增量 R-001，再实现 Paper Search Adapter；不一次性重写全部 Agent。
- D-R001-02：目标 L1 采用 `Thin Runtime -> Capability/Domain -> Evidence/Policy -> Store` 单向依赖。
- D-R001-03：CapabilityManifest、CapabilityAdapter、InvocationReceipt、EvidenceCandidate 只在 S1 被实现，避免过早平台化。
- UD-006：首个产品切片为证据约束的 Evaluation Section Pipeline；首版只支持一种论文类型。
- UD-007：成员可在各自 worktree 自行编写 task-local L3 并直接实施，无需先提交 L3 等待批准。

## Completed

- 读取并核对现有 `AGENTS.md`、`.ai-team`、Project-to-Act、架构/验收文档和当前源码耦合。
- 新建完整 `docs/rearchitecture/R001/` 架构包；`docs/REARCHITECTURE.md` 降级为摘要入口。
- 按新版 skill 创建 `.rearchitecture-package.json` 并运行 package completeness checker。

## Pending

- 成员 A/B 创建 worktree、填写 L3 并开始实施；负责人保持共享边界和主线账本同步。

## Next step

成员完成各自实现后填写 PROGRESS/HANDOFF、运行测试和 task-local `node .ai-team/check.mjs`；A 先合并，B 随后 rebase，负责人依次完成 I0–I4 集成任务和最小 MVP 验收。

## Verification

- [x] R005/UD-006/UD-007 已冻结并生成 P1-A/P1-B 任务包。
- [x] 两个 worktree 的独占路径、禁止路径和合并顺序已记录。
- [ ] 成员 A/B 完成 task-local L3、实现和测试。
- [ ] 运行项目测试、P1 相关 package checks 和 `node .ai-team/check.mjs --base main`。

## Handoff note

- From: `user/team`
- To: `member A / member B`
- Summary: P1 双 worktree 实施基线。成员自行填写各自 L3 并实施；不得修改对方独占路径或负责人维护的共享文件。交接时必须同步 task package、`.ai-team/TASK.md`、代码和测试证据。

---

## Previous task: AR-003

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
