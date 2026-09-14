# 项目进度

> 记录当前执行状态与有效工作节点；普通查看、搜索和无状态变化的命令不写入。

## 当前执行节点

| 任务 | 状态 | 负责人 | 完成条件 | 证据 ID | 最后更新 |
|---|---|---|---|---|---|
| P1 双 worktree + MVP 集成 | 进行中（S1/S2/S3 promoted+accepted，S3-A2（O12 已交付、PR #15 待复审）/S4-A/S4-B/S4-A2 ready，I0–I2 integrated，I3 首轮收口完成） | 用户/项目负责人；成员 A/B | A/B 任务与 I0–I4 集成任务全部 accepted，并通过最小 Evaluation Section 端到端验收 | UD-006、UD-007、P1-WORKTREE-TASK-PLAN、TASK-PACKAGE-REGISTRY | 2026-09-11 |

## 当前任务

| 任务 | 状态 | 负责人 | 完成条件 | 证据 ID | 最后更新 |
|---|---|---|---|---|---|
| P0-01 现有框架与官方资料核验 | 已完成 | Codex | 本地相关测试通过；LangGraph/论文索引官方能力有来源 | E-BASE-001、E-WEB-001 | 2026-08-21 |
| P0-02 详细计划书与五 Agent 架构 | 已完成 | Codex | 计划书覆盖用户全部环节并通过结构检查 | E-PLAN-001 | 2026-08-21 |
| P0-03 功能表与验收基线 | 已完成 | Codex | 功能状态唯一、每项有优先级/依赖/完成条件 | E-PLAN-001 | 2026-08-21 |
| P0-04 论文项目文件夹模板 | 已完成 | Codex | 模板目录完整，子项目 `.project-to-act` 校验通过 | E-TPL-001 | 2026-08-21 |
| P1-01 状态/交接/证据/Gate 合同 | 进行中 | Codex | 基础 schema、单元测试和 fail-closed 已通过；历史迁移待补 | E-RUN-001 | 2026-08-22 |
| P1-02 最小 LangGraph 父图与五子图 | 进行中 | Codex | SQLite checkpoint/interrupt/resume 已通过；进程重启、分布式幂等待补 | E-RUN-001、E-JOURNEY-001 | 2026-08-22 |
| P2 论文搜索与读取纵向切片 | 进行中 | Codex | 三连接器、题录、阅读卡、locator、陪读已落地；gold corpus 和人工质量验收待补 | E-RUN-001、E-LIVE-001 | 2026-08-22 |
| P3 创新挖掘与工作执行 | 进行中 | Codex | hypothesis、反证条件和证据化 WorkPackage 已落地；RunManifest/真实实验待补 | E-RUN-001 | 2026-08-22 |
| P4 写作与审核 | 进行中 | Codex | 缺口稿、版本化修改/润色、L3 审核打回已通过；真实 claim audit 待补 | E-RUN-001、E-JOURNEY-001 | 2026-08-22 |
| P5 Wiki+Graph、画像与自进化 | 进行中 | Codex | 分区 Wiki/一跳图、画像、经验晋级和 proposal-only 已落地；向量/灰度/回滚待补 | E-RUN-001 | 2026-08-22 |
| P6 真实端到端试点与 v1.0 | 已规划 | 待指定 | `PROJECT_ACCEPTANCE.md` 全部运行时标准通过 | 无 | 未开始 |

## 阻塞项

| 阻塞 | 影响 | 解除条件 | 状态 |
|---|---|---|---|
| 尚未提供首个真实论文 idea | 无法建立 gold query、真实阅读集与端到端论文试点 | 用户在 P2 前提供 idea、领域、目标和资源边界 | 不阻塞 P0/P1，阻塞 P2 验收 |
| embedding 配置与检索模型未选定 | 无法进行真实向量召回质量评测 | 在取得真实论文 corpus 后按安全配置流程选择并锁定版本 | 不阻塞 foundation；阻塞向量验收 |
| 目标部署规模未确认 | Neo4j/对象存储/并发容量只能按默认单团队方案规划 | P1 明确本地单机、内网团队或云端部署 | 待决策 |

## 下一步

1. ~~A4/B4 交付 + owner 深审 + O7 gate~~ 已完成：S3 promotion 通过，S3-A/S3-B accepted（2026-09-10，base main@36ddbab）。
2. ~~O12 ProviderLane 09-11 交付~~ **已交付**：PR #15 open（owner 自修中）；A5 消费其计价——receipt 字段已冻结为 `tokens` 主口径 / `cost` 辅口径（带 `price_source`、`attempts`），A5 任务包已同步修订。
3. 09-11 **B5 已交付并合入**（PR #17 `7fdfb89`：owner 深审发现阻断缺陷 + 代修 + 独立对抗复核）；A5 已交付并进入 owner 集成（PR #18 → **PR #19**）、A6 待排期；09-12 B6 试点 + O5 空窗；09-13 B7 稿件 + O4 收官 MVP-CLOSED。
4. MVP 收口后，再用真实 idea、语料和实验资源建立 gold set 与真实论文试点。

## 进度历史

按时间倒序追加：日期、完成事项、证据 ID、遗留问题、下一步和确认来源。不要覆盖旧记录。

- 2026-09-11｜A5 S4 benchmark runtime：深审 + owner 代修 + owner 集成合入（runtime 线）：成员 A PR #18 → owner 深度审查发现**指标语义缺陷族「空/无样本被当作满分」**——`score` 在全部单元上取 `accepted_hallucination_ratio` 均值而未接受单元该值恒 0 → **拦得越多分越高**（live 实测 `acceptance_rate=0.0` 却 `score=100.0`）；空分母比率报 100.0/0.0；`hall(total_claims=0)=0.0`。根因**再次在规格**（`metric-definition.json` notes 原文即规定错误语义，同 B5）→ owner 代修 D-A5-12~16：只对已接受单元求均值、空分母一律 `None`、live 局限声明扩为两条、指标定义升版 1.0→1.1、补齐 TASK-SPECS 要求但未交付的 **F9**（receipt 成本字段位预留）。**独立盲审复核代修**另抓出 `false_block_rate` 空分母仍报 0.0（与自写 D-A5-13 自相矛盾）并修复。owner 集成 **PR #19 squash 合入 `8f6e7de`**（取代 #18）。合入后 main 全量 275 passed、ruff clean、报告逐位可复现、离线指标数值零变化｜遗留：F8（三条件从不调 LLM 却名 `bare_llm`）待裁决、`search_service.py` 第二条裸 S2 路径待裁决、`docs/BENCHMARK.md` 口径差未统一｜下一步：S4-A2 可领取；O12 PR #15 待成员 A 复核｜确认来源：用户指令（「我们来代修吧」「你帮他补一个 PR」「先合并 19 吧」）。

- 2026-09-11｜B5 真实数据源与解析层：深审 + owner 代修 + 独立对抗复核（owner 主线任务）：成员 PR #16 深审发现**阻断级缺陷**——撤稿判据读 Crossref `update-to[]`（语义为「本文更新了谁」）方向反转，**被撤稿论文判 `found`、撤稿声明判 `retracted`**（真实 API 复核确认）；根因在任务包本身（`TASK-SPECS` B5:50 与 ADR-01 槽位 7 同错）。owner 代修 PR #17 合入 `7fdfb89`：判据改读 `updated-by[]`、fixture 依真实 payload 重录并区分两个 Lancet DOI、`hallucination_ratio` 只计 `not_found`（新增 `undetermined_ratio`）、`citation_recall`/`citation_precision` 去恒等、解析层按后端记因 + 去假 locator 改 fail-closed、规格与 ADR 就地修订 + 勘误。**独立对抗审查**（不知情子代理）复核代修，另发现 `resolver_record()` 把 404 DOI 投影成 `current` 的 fail-open（成员原版即有、owner 两轮自查漏报）并修复。聚焦 20 / 全量 166 passed。证据：`reviews/PR16-B5-deep-review.md`、`reviews/PR16-B5-fix-review.md`。遗留：docling 解析路径未验证（两 parser 均未安装）。
- 2026-09-11｜O12 ProviderLane 交付与对抗性自审（owner 主线任务）：段 1（S1.1–S1.5）+ 段 2（S2.0–S2.6）+ S3.1 完成并 rebase 至 `main@380bd49`（零冲突）；`LLMService` 内部改走 lane（公共签名不变、消费方零改动），共享 `contracts.py` 增 `TokenUsage`/`InvocationCost`（`invocation_contracts.py` re-export）；**PR #15 open**（CI 三项绿：PR quality / Task contract / repo-task-sync）。评审证据：全量 **268 passed / 2 skipped / 0 failed**（`-W error`）、ruff 绿、`check.mjs` valid、`check_pr_contract` passed；真实 parity（WorkBuddy 端点）`deepseek-v4-pro` 计价 delta=0、`glm-5.3` 无目录条目记 unpriced。审查：**对抗性自查 v2（6 项）+ 独立子代理盲审 v3（4 项）全部修复**（`SELF-REVIEW.md` / `CONTRACT-PARITY.md`）。**硬发现**：官方价目实测对照显示本项目快照与 DeepSeek 官方**偏差最高约 4.5×、且缺 peak/off-peak 结构** → 计价口径定为 **tokens 为主、cost 为辅**（`PRICE-POLICY.md` + D-O12-09 + D-O12-10），内置模型按官方 peak 档钉住（`price_overrides.json`），A5 任务包同步修订｜遗留：S3.3 成员 A 复审 → S3.4 registry 回写；`lane_drift_event` 无写入路径、peak/off-peak 双档不可表达、provider 改模型路由刷新脚本发现不了｜下一步：成员 A 复审 PR #15 → 合并后 registry 回写 `integrated`；09-11 A5 + B5 交付即审｜确认来源：用户指令（「走审核，但是在这之前你需要深度自审」「可以推送了」）。

- 2026-09-10｜S3 双线审查、集成与 O7 promotion（owner 主线任务）：A4 Capability Registry（PR #12，成员 A，R-1~R-6 self-review 后零集成修复）owner 深审通过合入 `f620915`（D-S3-01 三裁决：D-1 采纳回写 L2、D-4 双 receipt 保留+bridge 映射、D-7 确认单点准入判据）；B4 Reader/Writer Ports（PR #13，成员 B）深审后 owner 代修集成 PR #14 合入 `7b88e30`（rebase 3 commit + 孤儿 map-key gate 检查 + 更名，D-SYNC-01 先例，146 passed）；O7 S3 promotion 四项核验通过（fresh：focused 39 / 全量 146 / ruff / check.mjs @main `36ddbab`）→ **S3-A/S3-B accepted、S3-A2（O12 实施中）/S4-A/S4-B/S4-A2 ready（S4-A3 仍 planned，依赖 A6）**｜遗留：O12 今晚领取（speculative 段已开工）、A5/B5 明日交付即审、S3 promotion 后 S3-A2/B5 前置全满足｜下一步：O12 ProviderLane 09-11 交付；A5/B5 交付即审；09-13 O4 收官 MVP-CLOSED｜确认来源：用户指令（「可以，合并吧」「我们代修吧」「现在开」）。

- 2026-09-10｜S2 双线集成收口 + O2/O6 gate + O3 账本收口（owner 主线任务）：D-S2-01 裁决落地（A3 保 canonical `audit.py`、B3 改名 `audit_evidence.py`，语义以 B3 严格版为准，grade=E1 冻结）；owner 集成 PR #10（105 passed）+ follow-up PR #11 关 F-9/F-10（108 passed）；O2/D-F8-01 空结果语义裁决（`completed_empty` 确定性成功终态，`docs/coord/empty-result-ruling.md`）；O6 S2 promotion 四项核验通过 → S2-A/S2-B accepted、S3-A/S3-B ready（base main@535f208）；O3/I3 账本收口首轮（S2 账本 accepted 对齐、演进协议 D-EVOL-01 Decisions 归档、registry I3 integrated、本文件回写）；任务包扩容重排（B5 数据源/B6 试点/B7 稿件、O12 ProviderLane 归 Owner、A6/A7 前移；09-10 排期提优：O3/O8 提前下午、O12 今晚领取 09-11 交付）｜遗留：A4/B4 今日交付待审、O8 ADR-01 下午、O7 今晚 gate｜下一步：O8 → 今晚深审 A4/B4 + O7 → O12 领取｜确认来源：用户指令（集成裁决 + 排期提优拍板）。

- 2026-09-09｜I2 主线 E2E 与 S1 Promotion Gate 完成（owner 主线任务）：离线主线 E2E（`tests/test_mainline_e2e.py`）跑通最小 Evaluation Section 场景——Paper Search（A2 幂等边界，离线种子）→ Evidence 准入 → 材料就绪 → BenchmarkPlan → SectionDraft → RuleValidation，verdict VERIFIED，claim_evidence_map/readiness.evidence_ids/checked_evidence_ids 全部回溯到已准入证据，审计流含 papers.search_completed 与 writing.* 全阶段事件。Promotion Gate 四项核验通过：blocking findings 全部关闭（F-1/F-2/F-3/F-4/F-5、B2 invalidated-evidence fail-open；F-3 真实 connector 验收挂账 S4-B）、E2E 通过、证据可重跑（全量 81 passed + fault matrix exit 0）、下游合同已由 I0 稳定（D-I0-01）。**S1 promotion 完成**：P1-A/P1-B/P1-A2/P1-B2 转 accepted，S2-A/S2-B 转 ready（base main@6b706df）｜遗留：I3 账本收口、I4 交付检查未做；F-3 真实 connector 验收与 F-8 挂账｜下一步：成员 A/B 可领取 S2-A/S2-B；负责人推进 I3 账本收口｜确认来源：用户指令（跑 E2E 并推进集成）。

- 2026-09-09｜I1 Pipeline Orchestration 完成（owner 主线任务）：`PaperSearchAgent` 搜索路径接入 A2 可靠调用边界（`InvocationBoundedSearchPort`——确定性幂等键、重复调用 replay、pending 自动 phase-driven 恢复、failed/unknown receipt 持久化，重试策略归 audit lane）；application 新增 `run_evaluation_section` 编排入口（五步编排，blocked 短路保持 B1 语义）｜全量 `pytest -W error` 80 passed、ruff、check.mjs valid（+5 编排测试）｜遗留：I2 主线最小 E2E 场景与 S1 promotion 未执行；failed receipt 重试策略归 audit lane｜下一步：I2 Mainline E2E and Promotion Gate｜确认来源：用户指令（成员 P1 已全部完成，S2 系列卡 S1 promotion，集成线是关键路径）。

- 2026-09-09｜I0 共享合同集成完成（owner 主线任务）：审计确认 `EvidenceCandidate` 为唯一跨 lane 同名漂移并统一至 `contracts.py` 超集类型（D-I0-01，grade/locator 语义按 R005 与 B2 fail-closed 保留），`invocation_contracts`/`pipeline_contracts` re-export 兼容；新增 I0 组合测试（A 线 invocation 候选 → B 线准入贯通 + 单类断言）｜全量 `pytest -W error` 75 passed、ruff 通过、check.mjs valid｜遗留：I1 需把 `PaperSearchCapabilityAdapter` 接入 application 搜索路径并暴露 evaluation pipeline 编排入口；I2 主线最小 E2E 与 S1 promotion 未做｜下一步：I1 Pipeline Orchestration｜确认来源：用户指令（启动 I0–I4 集成）。

- 2026-09-09｜PR #5 深审（owner 贴合度复审）产出 4 项修补经 owner 跟进 PR #7 合入：F-4 审计事件与幂等记录转换原子化（stale 拒绝零审计行）、`StaleIdempotencyWriteError` 专用异常、`_status` 词边界嗅探收窄（"0 errors" 不再误判 unknown）、recovery API 清理（删 `outcome_status` 死参数、`fail_pending` 限 reserved 阶段）｜全量 `pytest -W error` 73 passed、ruff、check.mjs valid、fault matrix exit 0｜遗留：F-3 真实 connector 验收挂账 S4-B（类型启发假设已文档化）；F-8 R003 空结果语义待 owner 裁决｜下一步：owner 启动 I0 共享合同集成与 P1 集成验收｜确认来源：用户指令（深审发现由 owner 侧 PR 修补，不开新成员任务包）。

- 2026-09-09｜P1 双泳道成员任务全部合入主线：B2 Evidence Adversarial（PR #4 + owner 跟进 PR #6，B2 Gate 条款 invalidated-evidence fail-open 关闭）与 A2 Runtime Hardening（PR #5，A2 Gate 条款 F-1 跨进程 TOCTOU、F-2 phase-aware recovery、F-3 失败分类关闭）｜owner 在合并结果上独立复现：全量 `pytest -W error` 69 passed、ruff 通过、check.mjs 账本校验 valid、fault matrix 6 场景 `overall_passed=true`（schema `p1-a2-fault-matrix/v1`）｜遗留：P1 端到端集成验收（I0–I4）未执行；`recover_pending` 的 `outcome_status` 参数已成死参数待清理；注册表 P1-A/P1-B/P1-A2/P1-B2 行已同步为 integrated｜下一步：负责人执行 I0 共享合同集成与 P1 集成验收｜确认来源：用户指令（不打回成员，由 owner 直接补账本、修复问题并合并）。

- 2026-09-04｜冻结 P1 双 worktree 实施基线｜P1-A/P1-B 任务包、UD-006、UD-007、P1-WORKTREE-TASK-PLAN 已准备；遗留：成员尚未实施，`.ai-team/TASK.md` 与本节点已同步｜下一步：成员填写 L3 并开始编码｜确认来源：用户本轮分发指令。

- 2026-08-22｜按用户反馈将任务拆解入口收敛到模块级｜模块版覆盖 M00–M17，原 122 子任务版本保留为详细附录｜遗留：模块负责人和实际 evidence 尚未填写｜下一步：先分配模块负责人，再只细化当前瓶颈模块｜确认来源：用户本轮反馈。

- 2026-08-22｜发布 public GitHub 仓库并补充 M00–M17 任务拆解书｜仓库可见性、main 推送和文档结构已核验｜遗留：分支保护/CI、真实论文试点和生产化仍按任务书待分配｜下一步：由团队填写 owner 并启动 M00-05、M01-02、M02-07、M04-04、M16-01｜确认来源：用户本轮发布与任务拆解指令。

- 2026-08-22｜交付 0.1.0 foundation：VibeCollab 管理的严格五 Agent LangGraph、证据/Gate/状态/handoff、三论文连接器、阅读/陪读/创新、工作包、写作/修改/审核、Wiki+Graph、画像、经验、自进化提案、CLI/API 和论文项目运行投影；18 tests、84% coverage、3 个核心 HTTP 旅程与 1 个健康旅程通过｜证据：E-RUN-001、E-JOURNEY-001、E-LIVE-001、E-PROJECT-001｜遗留：真实 idea/gold corpus/实验/生产数据库/灾备未验收｜下一步：真实论文试点｜确认来源：用户本轮构建指令。
- 2026-08-21｜完成 P0：初始化根 Project-to-Act；核验嵌套 DeepReason 候选底座与官方资料；交付详细计划、86 项功能表和论文项目模板；双层账本/结构/链接/字段/秘密扫描通过｜证据：E-BASE-001、E-WEB-001、E-PLAN-001、E-TPL-001｜遗留：产品运行时尚未实现，真实论文 idea 未提供｜下一步：P1 合同与最小父图｜确认来源：用户本轮指令。
