# L2 Contracts

## Capability Registry

唯一维护 capability identity/version/manifest；解析失败不返回默认能力。Registry snapshot 随 run 固化，避免同一 run 中能力漂移。

## Capability Adapter

输入：`project_id`、`run_id`、`invocation_id`、manifest/version、bounded request。输出：typed result、diagnostic、receipt、EvidenceCandidate。相同 identity+request fingerprint 幂等，冲突 replay 拒绝；timeout/parse/unknown 显式返回。

## Evidence Module

唯一写入 EvidenceItem、ClaimLink、ArtifactLink、invalidations 和 evidence audit。Candidate admission 必须绑定 `run_id`、`invocation_id`、source、locator、adapter version。Domain/Capability 不得直接改 evidence state。

## Thin Runtime

只负责 config、registry、port invocation、run lifecycle、checkpoint 和 bounded output；不负责论文判断、证据评级、Gate 策略或 provider prompt。

## 状态/恢复

Invocation 状态为 `planned → started → receipt_committed | unknown | failed`；receipt committed 后才允许 admission。unknown 不自动重试；恢复先查询 receipt，再决定继续或人工处理。
