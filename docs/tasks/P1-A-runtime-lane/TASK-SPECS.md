# A 线任务详细规格

本文件让成员 A 可以沿着 Runtime lane 连续推进；每个任务仍然必须单独提交 PR、测试和 handoff。状态以全局注册表为准。

## A1 — P1-A Runtime / Recovery

- 状态：`ready`
- 目标：完成 Paper Search 调用边界的幂等、receipt、replay、timeout、pending、unknown、restart/recovery 和 legacy/target parity。
- 主要交付：`capability.py`、`storage.py`、`invocation_contracts.py`、恢复/幂等测试、fixture、parity report、L3/PROGRESS/HANDOFF。
- 必须满足：`completed_empty` 与 `unknown_outcome` 分开；reserve 先于副作用；精确 replay 不重复调用 connector；冲突 replay 拒绝；pending 不自动成功。
- 禁止：修改 `application.py`、共享 `contracts.py`、Evidence/Writing 路径；新增 Store、总线、scheduler 或 Agent。
- 验收：P1-A 任务包第 8 节的 Invocation、Recovery、Parity 全部通过。

## A2 — P1-A Runtime Hardening

- 状态：`ready-next`，依赖 A1。
- 目标：把 A1 的失败语义变成可持续回归的 fault-injection 和 parity harness。
- 主要交付：connector timeout/crash/partial-write 注入器、重复执行矩阵、稳定的 parity 命令、回归 fixture、诊断报告。
- 必须满足：每个失败窗口都能重现；不确定结果不能被归类为成功；测试可离线运行；报告记录 request fingerprint、receipt、durable facts 和副作用计数。
- 禁止：改变 R005 已冻结语义；绕过 A1 recovery API；修改 B 线独占路径。
- 验收：故障矩阵全覆盖，至少包含 timeout、进程重启、evidence-before-receipt、重复提交和冲突 fingerprint。
- **Owner review 补充条款（2026-09-07 深度审查，E-A1-REVIEW-FINDINGS，A2 Gate 前置）**：
  - **[必须关闭] F-1 跨实例 TOCTOU**：`storage.py` 的 `mark_idempotent_phase`/`finalize` 用进程内 `_lock`，多实例下 finalized 记录可被并发 mark 覆盖回 pending（深度审查实验证实，后果 fail-closed 但破坏 receipt 不变量）。A2 需引入跨进程安全的状态迁移（SQLite 条件 UPDATE `WHERE phase IN (...)` 或等价物）并附多进程回归测试。
  - **[必须关闭] F-2/`recover_pending` 语义**：`recover_pending` 不区分 phase 一律按 FAILED 处理，"service-started 中断 → unknown_outcome" 仅靠调用方约定。A2 需把 phase 感知恢复下沉到 recovery 本体，并以 fault-injection 测试固定。
  - **[必须关闭] F-3 失败标签过宽**：非 timeout 异常一律收口为 `failed`，把"不确定"标成"确定失败"。A2 需区分确定性失败与未知结果（对齐 A1 文档的 unknown_outcome 语义）。
  - **[测试] 非法 phase 转换测试不在常规 pytest 套件**：仅存在于验收脚本。A2 需把 phase guard、TOCTOU 等关键回归纳入 `pytest` 常规路径。
- **Owner 深审跟进（2026-09-09，PR #5 合并后贴合度复审）**：
  - **[已关闭] F-4 审计事件与记录转换非原子**：owner 跟进 PR 把 audit 事件写入并入 `reserve_idempotent`/`mark_idempotent_phase`/`finalize_idempotent` 的同一事务（事件列表参数），stale 拒绝时不产生审计行，并有 pytest 原子性回归。
  - **[已关闭] F-5**：A2 已顺带把非法 phase 转换测试纳入常规 pytest。
  - **[已关闭] stale 拒绝专用异常**：新增 `StaleIdempotencyWriteError`（RuntimeError 子类），跨进程 stale writer 测试改断言该类型。
  - **[已关闭] recovery API 语义债**：`recover_pending` 删除 `outcome_status` 死参数（phase 唯一决策源）；`fail_pending` 限定仅 `reserved` 阶段可用（provably no side effect），其余阶段抛错指向 `recover_pending`。
  - **[已关闭] `_status` 诊断嗅探收窄**：关键词匹配改为词边界匹配，"0 errors" 等计数表述不再误判为 unknown_outcome。
  - **[挂账 S4-B 真实试点前] F-3 真实 connector 验收**：异常→状态分类目前是类型启发，其正确性依赖隐含假设"legacy connector 的非 OSError 异常只发生在外部调用前"（响应解析期异常会被误标 failed）。该假设已在此文档化；真实 connector 接入时必须按真实异常面复验分类边界，作为 S4-B/真实论文试点的验收前置，结果回写本节。
  - **[已关闭 2026-09-10] F-8 R003 空结果语义回写**：owner 裁决 D-F8-01（`docs/coord/empty-result-ruling.md`）——确定零结果 = `completed_empty`（确定性终态），`unknown_outcome` 仅限中断恢复路径；「never successful invention」意图由 INV-10 + readiness fail-closed 承载；R003 L3 文档已加裁决注记。

## A3 — S2 Audit Runtime

- 状态：`waiting-for-gate`，依赖 S1 promotion。
- 目标：提供 Audit CLI/stdio runtime 的调用边界和 resolver adapter，不直接写 EvidenceItem。
- 主要交付：Audit invocation contract、resolver adapter、CLI/selftest、AuditReport artifact receipt、unknown/fail-closed 诊断。
- 必须满足：Audit 只读 bounded evidence view；核验结论以 verdict/candidate 返回；网络不可用返回 `unknown`；不得由 Audit 产生 GateDecision。
- 验收：S2 fixture 的存在性、撤稿、更正、locator 和网络受限场景可重跑。
- **Owner scope 裁决（2026-09-09，成员问询后登记）**：S2 **不包含 MCP 协议实现**。A3 交付的调用边界是 invocation contract + CLI/stdio + selftest，必须与传输协议无关；MCP 适配归 S3（A4 的 native/MCP/skill/plugin adapter 层）包装。理由：①MCP 是外部工具连接协议，提前绑定会让 Audit Runtime 与传输耦合；②MCP SDK 属外部依赖，引入时机由 S3 统一选型。允许预留 MCP 兼容钩子，但不得引入 MCP SDK 依赖、不得改变 invocation contract 形状。验收标准始终是 S2 fixture 矩阵可重跑，不是"MCP 可调用"。
- **D-S2-01（2026-09-09，owner 集成裁决）**：A3 保留 canonical `src/autoresearch/audit.py`、record kind `audit_report` 与 `audit.*` 事件；B3 实现改名 `audit_evidence.py`、kind `audit_evidence_report`、事件 `audit_evidence.*`。语义统一以 B3 严格语义为准（binding 需有效证据、corrected 关系可追溯即 PASS）；A3 运行时的对应类别在 S2 promotion 集成窗口对齐（owner follow-up）。

## A4 — S3 Capability Adapters

- 状态：`accepted`（O7 S3 promotion 2026-09-10：四项核验通过；PR #12 合入 `f620915`）。
- 目标：实现 Capability Registry 和 native/MCP/skill/plugin adapter 的统一调用边界。
- 主要交付：manifest registry、operator-assigned trust tier、adapter invocation receipt、candidate-only 限制、禁用网络的默认策略。
- 必须满足：能力自述不能自行提升 trust tier；外部能力只能经 adapter；不增加第六个业务角色。
- 验收：candidate_only 和 compliant_structured 两种信任层级各有正/负例，越权和旁路调用为 0。

## A5 — S4 Benchmark Runtime

- 状态：`ready`（O7 S3 promotion 已于 2026-09-10 通过），依赖 S3 promotion。
- 目标：提供可审计 benchmark harness 的运行时支持。
- 主要交付：benchmark invocation、资源预算、停止条件、结果 receipt、报告 artifact 和重跑命令；**Semantic Scholar 真实检索 adapter（2026-09-10 增补，经 A4 registry 注册，为 benchmark 与 B 线试点提供真实文献数据源）**。
- 必须满足：计划、观测结果和未知结果分开；资源超限触发 interrupt/deny；运行环境和命令可追溯；检索 adapter 的空结果遵循 D-F8-01、限流/离线矩阵化。
- 验收：S4 benchmark 三组对比可重跑，失败、超时和未执行结果不会被写成通过。
- **评估纪律条款（2026-09-10 追加，karpathy 三约束吸收，见 workspace 生态调研报告第七节）**：主指标唯一（以 hallucination ratio 为首，其余为辅指标不参与裁决）；固定语料集与固定调用预算（**per-run 预算以 tokens 为主口径写进 receipt，cost 为辅**——tokens 是 provider 报告的事实，cost 是用价目表折算的推断，会随价目表滞后而失准，故预算纪律一律写在 tokens 上；口径定义见 O12 `PRICE-POLICY.md`；计价链由 Owner 线 O12 ProviderLane 供给）；换写作头/检索源不得改变评估口径——指标定义与评估预算在本任务包内冻结，变更须走 owner 裁决。依据：无验证器/无固定口径的自进化已被 AI Scientist（57% 虚假数据）证伪。
- **分工注记（2026-09-10）**：LLM 调用底座（ProviderLane）由 Owner 实现（O12，需参考本地 openpilot 代码），A5 通过 invocation receipt 消费其调用边界与 `tokens`/`cost` 字段，不在本任务包范围内实现。
- **计价衔接注记（2026-09-10 追加；2026-09-11 更新为 O12 实际交付口径）**：receipt 的成本 schema 原由本包**预留字段位**，现已由 O12 冻结落地——`tokens`（主口径，provider 报告的事实）与 `cost`（辅口径，估算）定义在共享 `contracts.py`（`TokenUsage` / `InvocationCost`）；`cost` 携带 `price_source`（价目表 + 核对日期）与 `attempts`（重试上界），未命中价目时为 `None` 而非 0。**引用任何成本数字必须带 `price_source`**；本项目快照与 provider 官方价目实测存在系统性偏差（最高约 4.5×），故 cost 只用于对外报数，**不用于评估纪律裁决**。端到端计价验收在本包 accepted 后补验，不阻塞。口径定义见 O12 `PRICE-POLICY.md`。
- **候选消费纪律（2026-09-10 D-S3-01 硬条款）**：A5 消费 A4 invocation 时，候选准入必须走 `CapabilityInvocation.admissible_candidates` / `receipt.candidates_admissible` 单点判据（computed，keyed on `outcome_status`），**不得直接读 `candidates` 做准入**——失败路径的 `candidates` 是原始事实记录，非准入许可（D-7 裁决落位）。同窗口收紧项：`request_fingerprint` 对 raw dict 的确定性（A5 request 全部 pydantic 化）。

## A6 — S4 经验沉淀接线（追加包，2026-09-10；原 Owner O9 接线点①前移成员 A）

- 状态：`planned`，依赖 A3/B3 accepted（已满足）。
- 目标：把 B3/A3 的 fail-closed 拦截事件流接到孤儿模块 `evolution_service.py`，让失败经验从第一次真实拦截开始自动沉淀——数据飞轮经验层上线。
- 主要交付：事件消费钩子（订阅 `audit_evidence.*` / fail-closed 拦截事件，经 A lane receipt/replay 底座，只读消费不改审计链）、事件→经验映射器（**拦截事件→失败经验的映射表由成员自行拟定**，作为交付物随 PR 提交，Owner 审查时把关：把拦截类型模板化为 ExperienceRecord，打 `failure` 标签，复用 record 自带的 WikiPage 镜像）、重复拦截去重（同因经验合并计数，供 promote 的「复现 ≥2」门槛使用）、fixture 与离线测试。
- 必须满足：只读消费审计事件，不改变事件本身与审计链语义；record 走 EvolutionService 原有四门槛（复现 ≥2 + E2 + 审核者 + 人工批准），接线不得给自动晋级留路径；拦截事件不可用时静默降级为无经验产生（fail-closed 方向的降级），不阻塞主管线。
- 禁止：修改 EvolutionService 的 promote 语义；写入 knowledge 其他分区；触碰 B 线 evidence 路径。
- 验收：注入拦截事件 → 对应失败经验出现在 experiences 分区并镜像 WikiPage；同因重复拦截 → 记录计数 +1；主管线在钩子故障时不受影响；全部离线可重跑。

## A7 — S4 knowledge 向量检索升级（追加包，2026-09-10；原 Owner O10 实现部分前移成员 A）

- 状态：`planned`，依赖 A6（串行，同属孤儿模块域）。
- 目标：`knowledge.py` 检索从纯词法升级为词法 + 向量双路 RRF 融合——知识库从「目录」变「引擎」，B6 试点灌入的真实数据即插即用。
- 主要交付：embedding 管线（bge-small 本地推理）、sqlite-vec 向量索引（构建/增量更新与 WikiPage 写入联动）、RRF 融合排序（词法 × 向量双路）、跨分区与 `require_evidence` 过滤语义保持不变、模型文件预置方案（vendor 目录一次性预下载，或首轮 TF-IDF 降级，规避离线默认禁网冲突——<b>两方案的取舍由成员自行评估决定，决策理由随 PR 记录</b>）、fixture 与离线测试。
- 必须满足：检索接口签名与返回结构不变（`evidence_ids` + `retrieval_level` 可追溯保留）；向量仅做索引、Wiki 页保持 Markdown 可读（karpathy「文件即数据库」原则）；embedding 模型与版本号记录进 registry（可追溯）；模型不可用时自动回退纯词法（fail-closed 方向降级）。
- 禁止：引入付费/网络 embedding API；改变跨分区禁止语义；在检索层做内容判断。
- 验收：双路 RRF 对纯词法的召回对比报告（fixture 语料）；增量更新正确性（新增页即时可检索）；模型缺失时回退路径可用；全部离线可重跑。
- **与 MVP-CLOSED 的关系注记（2026-09-10 对抗审查）**：本包为平行增量，交付（09-14）晚于 MVP-CLOSED 判定（09-13）——**不阻塞判定**；向量检索能力 09-14 起用于收官演示与后续试点，演示叙事按「收官次日增强」表述。

## 每个 A 任务的交付门槛

代码、测试、fixture、task-local ledger、证据报告和 rollback 必须在同一 PR；前置 Gate 未通过时，后续任务只能标记 `speculative`，不能合并或标记 `accepted`。
