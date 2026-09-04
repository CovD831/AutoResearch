# L2 Contracts

## Capability Adapter

输入：`project_id`、`run_id`、`invocation_id`、manifest version、bounded request。
输出：typed domain result、diagnostic、`InvocationReceipt`、`EvidenceCandidate[]`。
不负责：写 EvidenceItem、改 GateDecision、推进生命周期。

相同 invocation identity 和 request fingerprint 必须幂等；冲突请求拒绝；timeout、parse error、unknown external outcome 显式返回。

## Evidence Module

唯一写入 EvidenceItem、claim/artifact linkage、失效/替代和 audit。外部能力只能提交 candidate；Gate 只读取有效 bounded view；大正文保留 locator/ref。

## Thin Runtime

负责加载配置、解析 Registry、调用 port、驱动 run/checkpoint 和返回 bounded result；不负责科研判断、证据评级和工具内部 prompt。

## Skill / MCP / Plugin

Skill 是方法层；MCP 是外部工具/数据连接；Plugin 是打包格式。三者都必须通过 adapter 进入 Runtime，不能成为隐式状态权威。
