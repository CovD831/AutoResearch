# A5 Benchmark Runtime

状态：`ready`（O7 S3 promotion 已于 2026-09-10 完成，A4 registry 已 accepted）。完整目标、交付物、边界和验收见 `../../TASK-SPECS.md` 的 A5 节；`task-package.json` 由成员实现时按实际命名填写（参照 A4 先例）。

要点注记（均为已冻结条款，实现前必读）：

- Semantic Scholar 真实检索 adapter **经 A4 registry 注册**（`CapabilityRegistry`，2026-09-10 合入 `f620915`），不得旁路直调。
- 候选消费必须走 `CapabilityInvocation.admissible_candidates` / `receipt.candidates_admissible` 单点判据，**不得直接读 `candidates` 做准入**（D-S3-01 硬条款，A4 L3 Known limits）。
- receipt 成本字段 schema 预留（O12 交付后补验端到端计价，不阻塞本包 accepted）。
- 评估纪律（karpathy 三约束）：主指标唯一（hallucination ratio 为首）、固定语料集与固定调用预算（per-run 预算写进 receipt）、换写作头/检索源不改评估口径——变更须 owner 裁决。
- 空结果遵循 D-F8-01（`completed_empty` 为确定性成功终态）；限流/离线矩阵化。
