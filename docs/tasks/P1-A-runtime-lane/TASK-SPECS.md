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

## A3 — S2 Audit Runtime

- 状态：`waiting-for-gate`，依赖 S1 promotion。
- 目标：提供 Audit CLI/stdio runtime 的调用边界和 resolver adapter，不直接写 EvidenceItem。
- 主要交付：Audit invocation contract、resolver adapter、CLI/selftest、AuditReport artifact receipt、unknown/fail-closed 诊断。
- 必须满足：Audit 只读 bounded evidence view；核验结论以 verdict/candidate 返回；网络不可用返回 `unknown`；不得由 Audit 产生 GateDecision。
- 验收：S2 fixture 的存在性、撤稿、更正、locator 和网络受限场景可重跑。

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

## 每个 A 任务的交付门槛

代码、测试、fixture、task-local ledger、证据报告和 rollback 必须在同一 PR；前置 Gate 未通过时，后续任务只能标记 `speculative`，不能合并或标记 `accepted`。
