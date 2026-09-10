# R-004-04 L2 边界合同

前四个合同继承 INDEPENDENT-2026-09-03（本文件为其后继权威），修订处以 ★ 标注；Audit Module 为 R-004 新增。状态：`established`（S1 实现所需字段已定）/ `conditional`（S2 前需实验或实现确认）/ `open`。

## CapabilityManifest

职责：声明能力身份、版本、输入输出、权限与自述 evidence mode。不负责：证明结果正确、拥有项目状态、★决定生效信任层级（trust tier 由 operator 指派，见 02 修订 2）。

必备字段：`name`、`kind`、`version`、`entrypoint`、`inputs`、`outputs`、`permissions`、`evidence_mode`（自述）、★`network_required`（布尔，默认 false = 默认禁网）、★`allowed_network_domains`（resolver 域名白名单）。
状态：established（S1 字段）；签名、来源许可、依赖锁定 open（plugin lifecycle 增量）。
★D-S3-01（2026-09-10，owner 审查 PR #12 裁决）：原 `network` 单字段拆分为 `network_required` + `allowed_network_domains`——布尔必填位与域名白名单分离，语义更可执行；A1/A2 构造零影响（两者均为可选默认字段）。`allowed_network_domains` 传输层强制归 ProviderLane/O12 与后续网络沙箱窗口。

## CapabilityAdapter

职责：把 native/skill/MCP/plugin 协议转换为 typed request/result。不负责：直写 EvidenceItem、修改 GateDecision、改变生命周期、升级权限。

- 输入：`project_id`、`run_id`、`invocation_id`、manifest version、bounded request。
- 输出：domain result、diagnostics、`InvocationReceipt`、零或多个 `EvidenceCandidate`。
- 授权：Runtime 按 manifest capability scope 授权。
- 幂等：相同 invocation identity + request fingerprint → 同一 receipt；冲突请求拒绝。
- 失败：provider error / timeout / parse error / unknown outcome 必须显式返回；unknown 不得标记成功。
- ★补偿语义：receipt 已提交而 admission 失败时，invocation 终态为 `admitted=false` 且允许同 invocation_id 重放 admission；禁止静默成功或部分提交不可见。

状态：established。

## Evidence Module

职责：candidate 接纳、不可变 EvidenceItem、claim/artifact linkage、失效/替代、审计事件；★接纳 `candidate_only` 能力产出的降级上限（P0/H1 直至 Audit 晋级）。不负责：搜索/阅读/写作/实验、选择工具、执行 gate。

- 唯一写入者：Evidence Module（Audit Module 核验结论同样只能以 candidate 进入）。
- Gate 只读有效视图；大正文只留受控 locator/ref。
- ★接纳原子性：跨 store 写入无法原子时必须显式 compensation/unknown（同 Adapter 补偿语义）。

状态：established（S1 范围）；冲突传播、时效策略 conditional（S2 实现确认）。

## Thin Runtime

职责：加载配置、解析 registry、调用 capability/domain port、驱动 run/checkpoint、返回 bounded result。不负责：科研判断、证据评级、prompt 质量、工具内部重试。状态：established。

## Audit Module（新增，conditional→S2 冻结）

职责：对稿件或声明列表执行确定性核验并产出 `AuditVerdict` 与 AuditReport artifact。核验类别：

1. 引用存在性（metadata resolver 反查 DOI/arXiv/标题）；
2. locator 一致性（claim 与本地已纳全文的页/节/表图定位比对）；
3. 撤稿/更正/版本状态（resolver + 本地证据库）；
4. 未绑定声明标记（无有效证据绑定的陈述显式输出 `[未验证]` 清单）。

不负责：写 EvidenceItem、产生 GateDecision、改写稿件、评价写作质量。

- 输入：manuscript/claims + citation registry 引用 + 目标策略（哪些类别启用）。
- 输出：`AuditReport`（artifact）+ verdict 列表 + `EvidenceCandidate`（核验结论回流；standalone 模式下无此项）。
- 幂等：相同 manuscript hash + 本地 corpus 版本 + resolver 快照版本 → 相同报告。resolver 响应必须缓存为带版本快照的本地证据，禁止活查询直接决定 verdict（否则同一稿两次审计结果漂移）。
- 运行形态：`in-runtime`（有 Evidence Module，verdict 回流 candidate）与 `standalone`（CLI/MCP 独立调用，无项目上下文：只产 report+verdict，不做 admission、receipt 可选）。
- 失败语义：resolver 不可达 → `unknown` verdict（fail-closed，不得 fail-open）；本地无全文 → locator 类别 `unknown`，不算 fail。
- locator 一致性比对的语义判定允许 LLM 辅助，但 verdict 必须携带方法标记（`deterministic | model_assisted`）与置信度；`model_assisted` 单独计类，不与确定性结果混排。
- 授权：只读 evidence view + manifest 声明的 resolver 网络域。

状态：conditional。S2 实现前需用标注 fixture 冻结 verdict 判定规则与 `model_assisted` 的一致性阈值。
