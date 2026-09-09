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

- 状态：`planned`，依赖 S2 promotion。
- 目标：实现 Capability Registry 和 native/MCP/skill/plugin adapter 的统一调用边界。
- 主要交付：manifest registry、operator-assigned trust tier、adapter invocation receipt、candidate-only 限制、禁用网络的默认策略。
- 必须满足：能力自述不能自行提升 trust tier；外部能力只能经 adapter；不增加第六个业务角色。
- 验收：candidate_only 和 compliant_structured 两种信任层级各有正/负例，越权和旁路调用为 0。

## A5 — S4 Benchmark Runtime

- 状态：`planned`，依赖 S3 promotion。
- 目标：提供可审计 benchmark harness 的运行时支持。
- 主要交付：benchmark invocation、资源预算、停止条件、结果 receipt、报告 artifact 和重跑命令。
- 必须满足：计划、观测结果和未知结果分开；资源超限触发 interrupt/deny；运行环境和命令可追溯。
- 验收：S4 benchmark 三组对比可重跑，失败、超时和未执行结果不会被写成通过。
- **评估纪律条款（2026-09-10 追加，karpathy 三约束吸收，见 workspace 生态调研报告第七节）**：主指标唯一（以 hallucination ratio 为首，其余为辅指标不参与裁决）；固定语料集与固定调用预算（per-run 预算写进 receipt，来自 A6 的计价链）；换写作头/检索源不得改变评估口径——指标定义与评估预算在本任务包内冻结，变更须走 owner 裁决。依据：无验证器/无固定口径的自进化已被 AI Scientist（57% 虚假数据）证伪。

## A6 — S3-A Provider Lane 与真实检索接入（追加包，2026-09-10）

- 状态：`planned`，依赖 A4 accepted + S3 promotion（O7）。
- 背景：外部模块选型已定稿（workspace `docs/autoresearch-生态调研-2026-09.md` 第九节，正式落库待 O8 ADR-01）。LLM 调用底座从 76 行裸 `llm.py` 升级为 ProviderLane；paper search bounded port（R003）接入第一个真实数据源。
- 目标：ProviderLane 统一 LLM 调用边界 + Semantic Scholar 真实检索 adapter，为 A5 benchmark 与 B5 真实试点提供真实生成与检索能力。
- 主要交付：`provider_lane.py`（lane 不可变身份 `provider:model:reasoning:vN`；模型目录含 cost/contextWindow 元数据；usage→invocation receipt 计价字段；reasoning 档位统一；跨 provider handoff 消息转换）、lane 约束（预算档/max_rounds/凭据 env 白名单/settings 漂移 fail-closed 校验）、`llm.py` 迁移改造、Semantic Scholar adapter（经 A4 registry 注册，trust tier 与 candidate-only 限制生效）、成本汇总命令。
- 必须满足：凭据只读白名单 env，坏配置显式报错、不静默回退；每次调用 receipt 含 token/成本/模型来源（资金化数字链的源头）；provider 调用全部经 A4 adapter 边界，不得旁路；检索空结果遵循 D-F8-01（`completed_empty`）；离线默认禁用网络，直连仅在显式启用时发生；结构化输出走 constrained-sampling 式降级（prefer/require）。
- 禁止：引入 MCP SDK（MCP 是 S3-B 契约与 L3 扩展位的事）；绕过 idempotency/receipt 语义；在 lane 内写业务逻辑；改 B 线独占路径。
- 验收：双 provider（真实一路 + mock 一路）三路 parity（真实/回放/mock）；计价与官方计费口径误差可解释并记录；settings 漂移注入测试 fail-closed；检索 adapter 的空结果/限流/离线/部分响应矩阵可重跑。

## 每个 A 任务的交付门槛

代码、测试、fixture、task-local ledger、证据报告和 rollback 必须在同一 PR；前置 Gate 未通过时，后续任务只能标记 `speculative`，不能合并或标记 `accepted`。
