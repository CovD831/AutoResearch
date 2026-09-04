# R-001-04 L2 边界合同

## CapabilityManifest

职责：声明能力身份、版本、输入输出、权限和 evidence mode。
不负责：证明能力结果正确，不拥有项目状态。

必备字段：`name`、`kind`、`version`、`entrypoint`、`inputs`、`outputs`、`permissions`、`evidence_mode`。

状态：`established`（S1 所需字段）；签名、来源许可和依赖锁定为 `open`，由 plugin lifecycle 增量解决。

## CapabilityAdapter

职责：把 native、skill、MCP 或 plugin 协议转换为 typed request/result。
不负责：直接写 EvidenceItem、修改 GateDecision 或改变生命周期。

- 输入：`project_id`、`run_id`、`invocation_id`、manifest version、bounded request。
- 输出：domain result、diagnostic、`InvocationReceipt`、零个或多个 `EvidenceCandidate`。
- 授权：Runtime 按 manifest capability scope 授权；adapter 不能升级权限。
- 幂等：相同 invocation identity + request fingerprint 返回同一 receipt；冲突请求拒绝。
- 失败：provider error、timeout、parse error、unknown external outcome 必须显式返回。

## Evidence Module

职责：候选证据接纳、不可变 EvidenceItem、claim/artifact linkage、失效/替代和审计。
不负责：搜索、阅读、写作、实验或选择工具。

- 唯一写入者：Evidence Module。
- 可见数据：bounded evidence view；大正文/大 artifact 只保留受控 locator/ref。
- Gate 只读取 Evidence Module 的有效视图。
- Agent、Skill、MCP 只能提交 candidate，不能自行定级、失效或通过 Gate。

## Thin Runtime

职责：加载配置、解析 registry、调用 capability/domain port、驱动 run/checkpoint、返回 bounded result。
不负责：科研判断、证据评级、prompt 质量、工具内部重试策略。

## 兼容性

R-001 实现期间保留 `AutoResearchApplication` facade。新 Runtime 与旧入口都必须写入相同的项目/运行事实；无法证明等价时不得删除旧路径。
