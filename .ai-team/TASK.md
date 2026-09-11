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
- [x] 2026-09-10 **D-F8-01 空结果语义裁决 + O6 S2 Promotion Gate 完成**：①O2/F-8——R003 L3「empty result is unknown」与 A1 实现（确定零结果 → `completed_empty`）冲突，owner 裁决以实现语义为准（`docs/coord/empty-result-ruling.md`，D-F8-01）：`completed_empty` 为确定性成功终态、`unknown_outcome` 仅限中断恢复路径、anti-invention 意图由 INV-10 + readiness fail-closed 承载；R003 L3 已加裁决注记，TASK-SPECS A2 F-8 关闭。②O6 四项核验——blocking findings 清零（F-1~F-10 全关，F-8 由 D-F8-01 关闭）、E2E 绿（本地独立复现全量 `108 passed` 含 `test_mainline_e2e.py`，src/tests ruff 全绿）、证据可重跑（A3 selftest 8 场景、B3 验收矩阵 12/12、fault matrix exit 0）、下游合同稳定（I0 契约统一 + D-S2-01 语义统一 + D-F8-01 补齐）。**S2 promotion 完成：S2-A/S2-B → accepted，S3-A/S3-B → ready（base main@535f208）**。registry 与本文件同步回写。
- [x] 2026-09-10 docs 清理（O1 PR 纯净性条款的存量治理）：删除 `docs/rearchitecture/AUTORESEARCH-REARCHITECTURE-TEAM-R2/` 整目录（与根级 R004/R005 逐字节重复的副本，仅 diagram png 一处差异；768K）；`docs/市场调研与定位分析_2026-09.md` 移出 repo 至 workspace docs/（与代码库无关的个人材料）。根级 R003/R004/R005 的 review-ledger/review-report/evidence-* 生成物保留——属 promotion 审计证据链。入库白名单固化：设计 md/yaml + 契约 + 账本入库；工具生成物、归档副本、个人材料不入库。O1 纯净性条款（follow-up PR 不混装文档）同步至 docs/tasks/P1-I-owner-lane/TASK-QUEUE.md。
- [x] 2026-09-10 任务包扩容（外部模块接入计划入包）：A 线追加 **A6 S3-A Provider Lane 与真实检索**（ProviderLane = pi-ai 语义[模型目录/计价/跨 provider handoff/结构化降级] + lane 约束[预算/白名单/settings 漂移 fail-closed] 合体；llm.py 替换；Semantic Scholar adapter 经 A4 registry；计价入 receipt；依赖 A4+O7，A5 改依赖 A6）；A5 加评估纪律条款（karpathy 三约束吸收：单一主指标/固定语料与预算/口径冻结须 owner 裁决）；B 线追加 **B7 S3-B 真实数据源与解析层**（Crossref + Retraction Watch 经 B3 verdict 流、pymupdf4llm/GROBID 解析进 candidate 通道、AGPL 复核回写；B5 前置，未交付只能 mock 试点）；B6 加组装工具条款（pandoc 导出、matplotlib 图数据出 evidence store）；Owner 追加 **O8 ADR-01 选型定稿**（09-12 与 O3/O5 同窗口）/ **O9 孤儿模块激活一期**（三接线点+rule/capsule 两粒度）/ **O10 孤儿模块激活二期**（Ratchet 验证器+sqlite-vec 向量检索）/ **O11 治理层公开 demo+打榜**，O9–O11 均在 MVP-CLOSED 后不占关键路径。registry 登记 S3-A2-PROVIDER-LANE / S3-B2-DATA-SOURCES 并更新 next-package 链。依据：workspace docs/autoresearch-生态调研-2026-09.md 第六~九节（pi-ai 源包确认 + karpathy/EvoMap 吸收落位 + 全管线 14 环节选型三层接入）。
- [x] 2026-09-10 任务包重排修正（Owner 指示）：①ProviderLane 移交 Owner 亲自实现（编号 **O12**，需参考本地 openpilot `provider_lane.py`/`provider_tool_admission.py`），A 线撤销 A6、恢复 A4→A5 顺序；Semantic Scholar 检索 adapter 并入 A5 交付；A5 计价链改消费 O12。②B 线编号重排为执行顺序：**B5**=真实数据源与解析层（原 B7）、**B6**=Real Pilot（原 B5，新增 EvoMap 交叉评审+盲审条款：双模型各生成一版、盲审差异入审计事件、仅 candidate 参考 INV-26、打回版本归档为失败经验）、**B7**=MVP Manuscript（原 B6）。③registry：S3-A2 lane 改 integration/lead（Owner O12），S3-B2 引用改 B5。④Owner 队列新增「三、外部项目吸收点 → 落位任务映射」节：karpathy×4（三约束/Ratchet/FAILED.md/program.md）+ Evolver×1（Gene/Capsule）+ EvoMap×5（交叉评审盲审/knowledge_base 人工审核/全落盘/负结果/结构化通道论据）全部显式落位可追溯。以上改动与 dd1e66e 均未推送，待 Owner 确认后统一提交（提交纪律 2026-09-10）。
- [x] 2026-09-10 成员 A 排期补齐（Owner 批准 A6/A7 方案）：A 线追加 **A6 S4 经验沉淀接线**（audit 拦截事件 → ExperienceService.record 自动失败沉淀，事件消费钩子+映射器+同因去重；只读消费不改审计链、四门槛原样、钩子故障静默降级不阻塞主管线；原 O9 接线点①前移）与 **A7 S4 knowledge 向量检索升级**（sqlite-vec + bge-small 本地 embedding + RRF 双路融合，接口签名不变、向量仅做索引、模型缺失回退词法；模型文件预置 vendor 或首轮 TF-IDF 降级规避离线禁网冲突——开工前 Owner 确认；原 O10 实现部分前移）。O9 缩为接线点②③+rule/capsule 两粒度（0.5–1 天）、O10 缩为 Ratchet 验证器设计与验收（0.5–1 天）。registry 登记 S4-A2/S4-A3。A 线编号=执行序：A4→A5→A6→A7（09-10→09-14 连续排期）。诚实注记：A6 是纯接线（1 天），A7 是模块内部改造非接入（1–1.5 天），已向 Owner 说明差异。
- [x] 2026-09-10 两个决策点下放成员（Owner 指示「让成员自己去考虑」）：A6 的拦截事件→失败经验映射表改由成员自行拟定、随 PR 提交（Owner 审查把关，不再是前置裁决）；A7 的模型预置方案（vendor 预下载 vs TF-IDF 降级）由成员自行评估取舍、决策理由随 PR 记录。A6 依赖改为仅 A3/B3 accepted；O9 表述同步为「Owner 保留验收」。
- [x] 2026-09-10 计划对抗性审查（Owner 要求）+ O4 前移至 09-13。审查发现并修正四处时序缝隙：①A5（09-11 交付）计价链消费 O12（09-12 交付）——A5 SPECS 补「receipt 成本字段 schema 预留、端到端计价验收 O12 后补验，不阻塞 accepted」；②B6（09-12）双模型交叉评审与 O12 同日——B6 SPECS 补「就绪前 llm.py 直连临时路径（不绕过 candidate 通道与审计），就绪后切 lane 补计价」；③A7（09-14）晚于 MVP-CLOSED（09-13）——A7 SPECS 补「平行增量不阻塞判定，09-14 起用于收官演示」；④O3 是 B6 的 I3 硬前置——Owner QUEUE 标注 09-11 上午优先，O5/O8 可浮动。治理建议：O12 走 PR + 成员 A 人工复审（审核不自批对 Owner 同样适用）。O4 前移：09-13 完成 B7 交付+O4 收官 MVP-CLOSED，09-14 变纯缓冲日（余量至 09-15）。表格 Sheet1/2/3 同步。
- [x] 2026-09-10 O3/I3 账本收口首轮（排期提优提前至 09-10 下午执行）：①S2-A/S2-B 账本 integrated → accepted（Status note/Verification 补 O6 证据，S2-B 两条 stale Pending 关闭）；②registry I3 → integrated（首轮收口；最终 accepted 判定挂 O4/MVP-CLOSED 条件 5）；③演进协议条目 Decisions 归档索引（D-EVOL-01，owner 裁决走 TASK.md 不建独立文档）；④Project-to-Act PROJECT_PROGRESS.md 回写（当前执行节点刷新至 09-10 + 补 09-10 进度历史 + 下一步更新）。校验证据：check.mjs 六账本全绿、check_pr_contract、全量 pytest。口径注记：invariants 按 owner 裁决保守核对（不新建全局文件，以各账本 Invariants 章节 + TASK.md Invariants 节为准）；I3 直接消费者是 I4/B7（registry B6 行仅依赖 S3 promotion，任务板宽口径显示今晚统一）。
- [x] 2026-09-10 O8/ADR-01 选型定稿（提前执行，Owner 指令「对每一个外部模块的选型做好充分调研」）：3 个并行调研代理复核 12 个争议槽位（LLM 底座/检索/PDF/阅读/大纲/写作头/核验/评测/向量/经验注入/MCP；matplotlib/pandoc 事实标准未复研），证据 URL 全部内嵌 ADR。结果 **9 维持 / 3 调整 / 1 更名**：①槽位3 PDF→Markdown 默认改 **docling（MIT）**（OpenDataLoader 2026-06 基准 0.86–0.88 vs pymupdf4llm 0.57–0.73），AGPL 规避与质量提升同时成立，pymupdf4llm 降为轻量兜底（AGPL 条款：仅本地工具链不分发，ADR 签字块 2 已签署——Owner 2026-09-10「按照目前的这个调研来决定」，ADR-01 全文生效）；②槽位2 OpenAlex 降级可选——2026-02 起强制 key+用量计费、原 polite pool 作废；S2 免费 key（5000 req/5min）主选 + arXiv 补充；③槽位11 评测以 B5 自建 gold set 为主，ScholarQABench（Nature 2026，真实存在）数据 ODC-BY 辅助——官方跑分需 LLM 裁判，违反零 API 约束；「CITE-AI」查无权威出处，弃名改用 ScholarQABench 指标名。诚实清单：5 项未能确认（S2 长期政策 / sqlite-vec pre-v1 / MinerU 许可 / PubPeer API / sqlite-vector license）入 ADR 第 5 节待监控。pi-ai 语义移植决策（O12 依据）经复调研维持并签认（ADR 签字块 1）。ADR 消费方＝O12/A5/B5/B7；成员任务包选型引用一律以本 ADR 为准。
- [x] 2026-09-10 S3-A owner 深度审查（PR #12，成员 A）+ 合并完成：规则层全过（CI 三项绿、9 文件全在 allowed_paths、账本合规 D-SYNC-01）；验收命令独立复现（focused 29 passed / 全量 137 passed / ruff 绿 / check.mjs 18/18 valid）。深度结论：统一边界设计正确（注册视图无 bypass 句柄、operator 指派 tier、默认禁网零调用、R-1 重放极性、R-6 事实与准入分离 computed_field 单点判据）；共享合同仅加 6 个可选字段零破坏；ADR-01 slot 14 引用核对一致；D-1..D-7 偏离登记与 L2 原文逐条比对无虚报。**Decision: merge → PR #12 已合入 main `f620915`**（保护窗口照例：备份→解除→approve+merge→验证→记录同步直推→恢复保护），合并结果复现 137 passed。裁决落 D-S3-01；registry S3-A → integrated（acceptance 待 S3 promotion）；S3-B（B4）为 S3 promotion 剩余前置。诚实注记：覆盖率 100% 未独立复现（审查环境无 pytest-cov，CI 佐证）；场景 1–9 user-side 走查为成员转述证据（HANDOFF 回填表），自动化层有等效覆盖。
- [x] 2026-09-10 S3-B owner 深度审查（PR #13，成员 B）+ owner 集成合并：规则层——CI Task contract FAILURE 根因为分支从 `437e15e` 切出落后 main 3 commit（check_pr_contract 判 not an ancestor），账本格式本身合规（成员本地 check.mjs valid 已复现）；PR 标题/body 不合规。复现：聚焦 8 passed / 全量 116 passed / ruff 绿。深度层——交付合格（sole-writer 边界干净、candidate 通道完整、fail-closed 三态正确、parity 结构比较、compose 交叉锚点），但发现孤儿 key 缺口（`claim_evidence_map` key ∉ `claims` 完全静默）与两条消费方注记。**老板拍板 owner 代修（D-SYNC-01 先例）**：PR #13 superseded → owner 集成 PR #14 合入 main `7b88e30`（rebase + 孤儿 key gate 检查 + 对抗测试 + `adap_version` 更名 + L3 消费方注记），合并结果复现全量 **146 passed**（137 main + 8 B4 + 1 owner）。registry S3-B → integrated（acceptance 待 S3 promotion）。诚实注记：B 交付无 self-review 留痕/机械 diff/场景走查（与成员 A 的 R-1~R-6 流程差距），建议后续把「rebase 到最新 main + self-review 留痕」写进 B 线交付纪律。
- [x] 2026-09-10 **O7 S3 Promotion Gate 完成（老板拍板「现在开」）**：四项核验——①blocking findings 清零（S3-A 的 D-1/D-4/D-7 已裁决落 D-S3-01、4 观察项登记 follow-up 非阻断；S3-B 的孤儿 key 缺口已修+对抗测试锁定、typo 已修、2 注记登记 I 线）；②E2E 绿（mainline E2E 含于全量）；③证据可重跑（fresh 复现：focused E2E+A4+B4 共 **39 passed**、全量 **146 passed** @main `36ddbab`、ruff 全绿、check.mjs valid）；④下游合同稳定（D-I0-01 + D-S2-01 + D-F8-01 + **D-S3-01** 今日落 + B4 L3 消费方注记，S3 双模块 allowed_paths 未破坏共享合同）。**S3 promotion 完成：S3-A/S3-B → accepted，S3-A2（O12，owner/provider-lane 实施中）与 S4-A/S4-B/S4-A2 → ready（S4-A3 仍 planned，依赖 A6）**。registry 与本文件同步回写，Project-to-Act 阶段状态回写。
- [x] 2026-09-10 09-11 冲刺前置准备（owner 授权「可以」）：①**B 线任务包目录对齐重排编号**（旧骨架错位修复）：`B5-real-pilot/` → `B6-real-pilot/`、`B6-mvp-delivery/` → `B7-mvp-delivery/`（git mv），新建 `B5-data-sources/`；A5/B5/B6/B7 四个占位 TASK.md 刷新（状态对齐 S3 promotion 后事实：A5/B5 ready、B6 planned[依赖 B5 未交付]、B7 planned[依赖 B6]，并注记 ADR-01 选型/D-S3-01 消费纪律/EvoMap 条款要点）；TASK-SPECS A5/B5 状态行 → ready，registry S3-B2 → ready。②**O4 MVP-CLOSED 收官核对清单预置**：`docs/tasks/P1-I-owner-lane/tasks/O4-mvp-closure/CHECKLIST.md`——七条件逐条核对方式 + 09-13 当日执行顺序 + 缓冲与风险（A7 不阻塞/F-3 挂账规则/计价补验不阻塞），09-13 照单执行。
- [x] 2026-09-11 B5 真实数据源与解析层交付并合入（owner 主线任务）：成员交付 PR #16 → **owner 深审发现阻断级缺陷**（撤稿判据读 `update-to[]` 方向反转：被撤稿论文判 `found`、撤稿声明判 `retracted`，真实 API 复核确认；根因在任务包规格本身）→ owner 代修 PR #17 合入 `7fdfb89`：判据改读 `updated-by[]`、fixture 依真实 payload 重录并区分两个 Lancet DOI、`hallucination_ratio` 只计 `not_found`（新增 `undetermined_ratio`）、recall/precision 去恒等、解析层按后端记因并去假 locator、`TASK-SPECS` B5 与 `ADR-01` 槽位 7 就地修订 + 勘误。**独立对抗审查复核代修**（不知情子代理）另发现 `resolver_record()` 对 `not_found` 的 fail-open（成员原版即有，owner 两轮自查漏报）并修复。聚焦 20 / 全量 166 passed。报告 `reviews/PR16-B5-deep-review.md` / `PR16-B5-fix-review.md`。**未验证**：docling 解析路径零执行。

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
- D-EVOL-01（演进协议归档索引，2026-09-10 O3 收口）：经验/演进相关协议条目收口为单条索引——A6 接线协议（audit 拦截事件 → `ExperienceService.record` 失败沉淀：只读消费不改审计链、四门槛原样、钩子故障静默降级；事件→经验映射表由成员拟定随 PR，Owner 保留验收）；A7 向量检索方案（sqlite-vec + bge-small + RRF 双路融合，向量仅做索引、模型缺失回退词法 fail-closed；模型预置方案成员自选随 PR 记录）；O9 经验两粒度（rule 型进 Gate 条款 / capsule 型进 writer context）；O10 Ratchet 验证器（proposal → A5 跑分 → 改进 accepted / 无改进 abandoned，proposal-only + owner 批准）。完整定义见 Owner TASK-QUEUE 第三节吸收点映射与 A 线 TASK-SPECS A6/A7；本条为 I3 收口索引，非新裁决。
- D-S3-01（2026-09-10，owner 深审 PR #12 三项裁决，老板拍板）：①**D-1 采纳**：L2 `network` 单字段拆分为 `network_required` + `allowed_network_domains`，已回写 `04-l2-contracts.md`（A1/A2 零影响，传输层强制归 O12/沙箱窗口）。②**D-4 选 option (a)**：A1 `InvocationReceipt` 与 A4 `CapabilityInvocationReceipt` 双形状保留，`PaperSearchCapabilityAdapterBridge` 状态映射为唯一映射点——A1 receipt 已有持久化存量且枚举含 `completed_empty`、A4 含 `denied`，统一需动 S1 accepted 语义；两层角色不同（A1 领域内 vs A4 registry 边界），非 D-I0-01 式同名漂移。③**D-7 确认成员方案**：失败路径保留候选原始记录，准入由 `receipt.candidates_admissible`（computed，keyed on `outcome_status`）单点判定，消费方走 `invocation.admissible_candidates`；A5 消费点落地该判据为硬条款（已写入 A 线 TASK-SPECS A5）。④非阻塞观察项登记 follow-up（A5 接入窗口处理）：fingerprint 对 raw dict `default=str` 非确定、`emit_candidate` 无运行时类型校验（下游 pydantic 兜底）、`CapabilityRegistrationView.manifest` 同引用可 mutate（进程内自伤非越权）、candidate_only 空产出 completed 空成功（D-F8-01 语义下接受）。

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
