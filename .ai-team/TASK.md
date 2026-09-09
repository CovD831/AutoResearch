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
- [x] P1-A Runtime/Recovery 通过幂等、replay、recovery 和 legacy/target parity 验收；project owner accepted for integration (deep review PR #2, 2026-09-07), mainline integration pending.
- [x] P1-B Evidence/Writing Pipeline 通过 Evidence admission、readiness、benchmark plan 和 section validation 验收；project owner accepted for integration, mainline integration pending.
- [x] P1 端到端 Evaluation Section Pipeline 在 A 合并后由负责人完成集成验收（I2，2026-09-09：离线主线 E2E `tests/test_mainline_e2e.py` 全链路 VERIFIED，六阶段状态与证据可追溯；S1 promotion 完成，S2-A/S2-B 转 ready）。
- [ ] 负责人完成 I0–I4 集成任务，并将 `MVP-CLOSED-MINIMAL-E2E` 标记为 accepted。
- [x] 2026-09-07 owner 深度审查（PR #1/#2）发现项已落入 B2/A2 泳道 TASK-SPECS 作为 Gate 条款：B2 Gate 阻断项为 invalidated-evidence fail-open；A2 吸纳跨进程 TOCTOU、phase-aware recovery 与失败标签收窄。
- [x] 2026-09-08 P1-B2 Evidence Adversarial 已实现并合入主线（PR #4 + owner 跟进修复），B2 Gate 阻断项 invalidated-evidence fail-open 已关闭；成员账本由 owner 按 D-SYNC-01 补齐至 `.ai-team/tasks/`。
- [x] 2026-09-09 P1-A2 Runtime Hardening 已实现并合入主线（PR #5）：F-1 跨进程 TOCTOU（SQLite 条件更新拒绝 stale writer）、F-2 phase-aware recovery（按 durable phase 决策收口）、F-3 确定性失败与 unknown_outcome 分离均已关闭；owner 在合并结果上复现 69 passed 与 fault matrix（6 场景 `overall_passed=true`）。
- [x] 2026-09-09 A2 owner 跟进（PR #7）关闭 PR #5 深审发现项：F-4 审计事件并入记录转换事务（原子）、`StaleIdempotencyWriteError`、`_status` 词边界嗅探收窄、recovery API 清理（删死参数、`fail_pending` 限 reserved）；F-3 真实 connector 验收挂账 S4-B，F-8 挂账 owner。
- [x] 2026-09-09 I0 共享合同集成完成：审计确认 `EvidenceCandidate` 是唯一跨 lane 同名漂移（A/B 字段集几乎不相交），统一为 `contracts.py` 超集类型（D-I0-01），两 lane re-export 兼容，新增 I0 组合测试（A 线 invocation 候选 → B 线准入贯通 + 单类断言）；全量 `75 passed`、ruff、check.mjs valid。
- [x] 2026-09-09 I1 Pipeline Orchestration 完成：`PaperSearchAgent` 搜索路径改经 `InvocationBoundedSearchPort`（A2 幂等边界——同 (project, query, limit, seeds) 确定性幂等键，重复调用 replay、pending 崩溃记录自动 phase-driven 恢复、failed/unknown receipt 持久化，重试策略归 audit lane）；application 新增 `run_evaluation_section` 编排入口（plan→benchmark→readiness→draft→validate 五步，blocked 短路保持 B1 语义）；新增 5 个编排测试。全量 `80 passed`、ruff、check.mjs valid。
- [x] 2026-09-09 I2 主线 E2E 与 S1 Promotion Gate 完成：离线主线 E2E（`tests/test_mainline_e2e.py`）跑通 Paper Search（bounded 幂等边界）→ Evidence 准入 → 材料就绪 → BenchmarkPlan → SectionDraft → RuleValidation 全链路，verdict VERIFIED，claim_evidence_map/readiness.evidence_ids/checked_evidence_ids 全部回溯到已准入证据，审计流含 papers.search_completed 与 writing.* 全阶段事件。Promotion Gate 四项核验通过（blocking findings 已关闭、E2E 通过、证据可重跑、下游合同已由 I0 稳定），**S1 promotion 完成**：P1 四任务转 accepted，S2-A/S2-B 转 ready（base `main@6b706df`）。全量 `81 passed`、ruff、check.mjs valid、fault matrix exit 0。
- [x] 2026-09-09 S2-A Audit Runtime 合入主线（PR #8，merge `dae10f3`）：A3 交付 invocation contract/`audit_contracts.py`、版本化 resolver 快照持久化（不可变 + checksum 校验）、`AuditRuntime` + `AuditPersistencePort`、transport-agnostic JSON-lines stdio/selftest、CLI `audit` 命令、8 场景离线 fixture。Owner 深审 + 对抗性复审：fail-closed 全路径抽查通过（resolver 异常/版本不匹配/网络不可用 → unknown）、无 EvidenceItem/GateDecision 直写、candidates grade=None（D-I0-01）、快照 ON CONFLICT 与 records PK 匹配；本地 daf2b65 与合并结果各复现 88 passed（focused 7）、ruff、selftest、check.mjs。S2-A → integrated（acceptance 待 S2 promotion）。非阻塞 follow-up：F-9 audit 幂等 pending 无 phase-driven 恢复（崩在 reserve/finalize 之间毒死指纹，A2 recover_pending 模式未覆盖 audit）；F-10 共享 `admit_candidate` 对 grade=None candidate 会 ValidationError 崩溃（EvidenceItem.grade 必填，I 线接线前必须修，否则 A 线 candidate 无法准入）；A 线账本测试计数 6/87→7/88 漂移已由 owner 更正。
- [x] 2026-09-09 S2-B Audit Evidence（PR #9，97cd226）owner 审查完成，Decision: **blocked**：模块质量良好（97 passed/ruff owner 复现、验收矩阵 12/12、Evidence sole-writer 边界与 standalone 无副作用均有测试锁定），但与 S2-A 结构性撞车——allowed_paths 重叠 `src/autoresearch/audit.py`/`tests/test_audit_module.py`（add/add），双方均写 record kind `audit_report`（schema/键策略不同），且 base 落后（dad4658）。S2 包拆分未分区 audit 文件命名空间（owner 侧任务包缺陷，非成员实现走样）。CI Task contract/repo-task-sync 失败根因 = 成员 PR 缺 `.ai-team/tasks/` 账本，已由 owner 按 D-SYNC-01 补建 `.ai-team/tasks/S2-B-AUDIT-EVIDENCE.md`（参照 PR #4 先例）。非阻断发现：`_claim_matches_text` 空词条 claim 自动 pass locator（应 unknown）；grade=E1 硬编码待政策冻结；并发重复 audit 事件（无 reservation）。
- [x] 2026-09-09 **D-S2-01（owner 集成裁决，老板拍板"不打回、owner 补 PR"）**：S2 audit 双线撞车处理——A3 保留 canonical `src/autoresearch/audit.py`、kind `audit_report`、`audit.*` 事件；B3 实现改名 `audit_evidence.py`、kind `audit_evidence_report`、事件 `audit_evidence.*`。语义统一以 B3 严格语义为准（binding 需有效证据绑定、corrected/superseded 关系可追溯即 PASS、locator 空词条 fail-closed 为 unknown）；A3 运行时对应类别在 S2 promotion 集成窗口对齐（owner follow-up，含 F-9/F-10）。S2-B 成员实现不打回，由 owner 集成分支完成调整与测试。
- [x] 2026-09-09 S2-B Audit Evidence 经 owner 集成合入主线（PR #9 superseded → owner 集成 PR #10）：B3 模块以 `audit_evidence.py` 落地（AuditService，Evidence sole-writer 边界与 standalone 无副作用有测试锁定）；集成修复 `_claim_matches_text` 空词条隐式 PASS → UNKNOWN；B3 任务包 allowed_paths/状态与账本同步更新，TASK-SPECS A3/B3 补 D-S2-01 引用。合并验证：全量 `105 passed`（88 主线 + 16 B3 + 1 新增）、ruff、check.mjs valid。S2-B → integrated（acceptance 待 S2 promotion）。
- [x] 2026-09-09 owner follow-up（PR #11，D-S2-01 收尾）关闭 F-9/F-10：**F-9** `AuditRuntime.invoke` 对 crashed pending 幂等记录改为回收重算（`RecordStore.delete_idempotent` + `audit.invocation_reclaimed` 事件；audit 在 finalize 前无外部副作用，回收安全，fail-closed 不变），回归测试锁定"pending → completed → replayed"链路；**F-10** 共享 `EvidenceService.admit_candidate` 对缺分类（grade/evidence_type=None，A 线 candidate 常态）的 candidate 返回确定性 `BLOCKED` 并记 `evidence.candidate_blocked` 事件，替代 ValidationError 崩溃（D-I0-01 落地补全）。全量 `108 passed`（+3）、ruff、check.mjs。

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
- D-SYNC-01：成员 PR 以 `.ai-team/tasks/<TASK-ID>.md` 账本满足 repo-task-sync 同步检查；`check.mjs` 接受任意变更的成员账本作为有效 ledger，共享 `.ai-team/TASK.md` 集成队列仍由负责人维护（2026-09-08，PR #4 审查后落地，修复成员账本在 `docs/tasks/` 下被机器人无视的死锁）。
- D-I0-01：`EvidenceCandidate` 统一为共享 `contracts.py` 中的超集类型，`invocation_contracts.py` 与 `pipeline_contracts.py` 以 re-export 保持兼容（I0 共享合同集成）。统一前 A/B 两 lane 各有同名不同字段的定义（A 带调用溯源、B 带证据分类）。`grade`/`evidence_type` 为 Optional：R005 禁止 runtime lane 定证据评级，分类由 evidence lane 准入时提供；`locator` 统一 Optional，A 侧检索候选显式传占位 locator，B 侧准入维持 fail-closed 拒空。
- D-S2-01：S2 audit 双线集成裁决（2026-09-09）。①布局：A3 保留 canonical `audit.py`/`audit_contracts.py`/`resolver.py` 与 kind `audit_report`、事件 `audit.*`；B3 以 `audit_evidence.py` 落地，kind `audit_evidence_report`、事件 `audit_evidence.*`。②语义：binding/未绑定 claim、corrected/superseded 极性、locator 模型以 B3 严格语义为准，A3 运行时对应类别在 S2 promotion 窗口对齐。③grade 政策：evidence lane 的 audit 派生 candidate 下限等级冻结为 `E1`（"本地快照存在 + 状态可追溯"），runtime lane 候选仍为 grade=None。④成员实现不打回，owner 侧完成集成调整与测试（PR #10）。

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
