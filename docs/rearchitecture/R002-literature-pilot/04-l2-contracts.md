# L2 合同

## PaperSearchCapability（conditional）

输入：`project_id`、`run_id`、`invocation_id`、manifest name/version、bounded query、limit。输出：typed `PaperRecord[]`、diagnostics、`InvocationReceipt`、`EvidenceCandidate[]`。相同 run+invocation 精确重放返回同一 receipt；冲突输入拒绝；连接器失败返回显式 failure/unknown，不伪造空成功。权限由 Runtime scope 传入，Adapter 不拥有项目状态。

## Evidence Module（established target）

只接受带 run/invocation/source/locator/adapter-version 的 candidate；唯一写入 EvidenceItem、ClaimLink、ArtifactLink、invalidation 和 audit。查询只暴露 bounded view。Evidence grade 与 GateDecision 不由 capability 或 Agent 设置。

## Runtime/Checkpoint（open）

重启时依据 invocation receipt 和 checkpoint 恢复；未知外部结果不得自动重复副作用。待用户确认部署边界后，用单进程 SQLite 先验证，再决定 PostgreSQL/分布式幂等合同。
