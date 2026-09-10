# S3-A Capability Adapters

- ID: `S3-A-CAPABILITY-ADAPTERS`
- Title: `Capability Registry and unified native/MCP/skill/plugin adapter boundary`
- Status: `active`
- Owner: `member A`
- Next owner: `user/team`

## Goal

完成 A4/S3 Capability Adapters：实现 Capability Registry 与 native/MCP/skill/plugin 四协议的统一调用边界，交付 manifest registry、operator 指派 trust tier、adapter invocation receipt、candidate-only 限制与禁用网络默认策略；不实现 MCP 协议本体（ADR-01 slot 14：L3 扩展位），不新增第六个业务角色。

## Acceptance scenarios

- [x] candidate_only 正例：候选以 EvidenceCandidate 流出、结构化结果丢弃、receipt.trust_tier 为 operator 指派值。
- [x] candidate_only 负例：无候选而返回结构化值 → FAILED（`test_candidate_only_structured_value_without_candidate_fails`）。
- [x] candidate_only 丢弃证明：有候选同时有结构化值 → value 必须为 None 且 `structured_result_available=False`。
- [x] candidate_only 负例：直写 EvidenceItem 被拦截 → FAILED 且 blocked_write_attempts 可见。
- [x] adapter 直写 GateDecision 被拦截 → FAILED 且 blocked_write_attempts 可见。
- [x] compliant_structured 正例：类型化结果返回、structured_result_available=true。
- [x] compliant_structured 负例：无结构化结果 → FAILED。
- [x] adapter 异常（provider error）与非类型化返回 → FAILED receipt 且异常类型进 diagnostics，不向上抛。
- [x] 能力自述不能自行提升 trust tier：adapter 自述与 operator 指派不一致时忽略自述并记 diagnostic。
- [x] 外部能力只能经 adapter：注册视图不暴露 adapter 句柄；未注册能力 invoke 抛 CapabilityNotRegisteredError。
- [x] 禁用网络默认策略：network_required 能力在默认禁网下 DENIED 且 adapter 零调用；operator 显式 allow_network=True 后 adapter 被调用。
- [x] 幂等：同 (capability, invocation_id) + 同 fingerprint replay 返回 REPLAYED 且不二次调用；冲突 fingerprint 拒绝。
- [x] 重放保留原始极性：status=REPLAYED 时 outcome_status 仍为原始 failed / denied（评审修复 R-1）。
- [x] 引用解析确定性：裸 name 命中多版本 → CapabilityAmbiguousReferenceError；name@version 正常命中（评审修复 R-2）。
- [x] 四协议种类 native/mcp/skill/plugin 共用同一注册边界。
- [x] A1 Paper Search adapter 经 PaperSearchCapabilityAdapterBridge 进入 A4 边界。
- [x] 注册边界健壮性：重复注册拒绝、字符串 trust tier 强转、缺 invocation_id 拒绝（adapter 零调用）、pydantic/mapping/raw request 指纹路径。
- [x] 事实记录与准入判据分离：三条失败路径（adapter 异常 / 越权直写 / 契约违规）都保留 adapter 已 emit 的候选为**原始记录**，但 `receipt.candidates_admissible` 仅在 `outcome_status=completed` 时为 True；重放不改变可准入性（评审修复 R-6）。

## Invariants

- 不修改 `application.py`、共享 `contracts.py`、Evidence/Writing 路径、`.ai-team/TASK.md` 或 `.project-to-act/`。
- 能力自述（manifest）不能自行提升 trust tier；生效策略一律 operator 指派。
- 外部能力只能经 registry 注册后调用；adapter 只能 emit candidate，不能直写 EvidenceItem 或 GateDecision。
- 不新增业务 Agent；registry/adapter 是 Runtime 服务。
- 不引入 MCP SDK 或 MCP 协议实现（ADR-01 slot 14：L3 扩展位）。
- candidate_only 能力不得流出结构化结果；网络默认禁用，放行必须 operator 显式。
- 重放只改写 `status`，不得改写 `outcome_status`（原始终态不可被重放掩盖）。
- 失败路径保留 adapter 已 emit 的候选（事实记录），但候选准入由 `outcome_status=completed` 单点判定；消费方不得直接读 `candidates` 做准入。

## Decisions

- 注册键 = `name@version`；重复注册拒绝；多版本并存时裸 name 引用拒绝。
- receipt 预留 `admitted` 字段（None）：L2 ★补偿语义的 schema 位固定，端到端补偿验收留 I3（与 A5 成本字段预留同款做法）。
- receipt 增加 `outcome_status`：对齐 A1 `InvocationReceipt` 已冻结约定，重放不改写原始终态。
- 幂等与注册表暂为进程内实现：S3-A 无真实消费者要求持久化；A5 接入真实检索 adapter 时按需下沉（不提前抽象）。
- `CapabilityManifest` 的 L2 必备字段以可选默认补齐（向后兼容 A1 构造），S3-A 注册时按需填写。
- MCP 在本包只是 kind 标签；协议本体（stdio transport 等）按 ADR-01 slot 14 留 L3。
- 对 L2 的偏离 D-1..D-6 不在包内单方面改写共享合同，登记待 owner 裁决（见 `L3.md`）。
- `candidates` 是事实记录（含失败路径），准入判据由边界单点计算（`computed_field`，不可被写错）：`receipt.candidates_admissible`，消费方走 `invocation.admissible_candidates`。相关语义选择登记为 `L3.md` D-7，供 owner 确认或否决。

## Completed

- 基线核对：分支 HEAD = `origin/main@80e2277`（无需 rebase）；本地 `main` 快进至同一提交。
- `CapabilityManifest` 补齐 L2 字段（entrypoint/inputs/outputs + evidence_mode/network）。
- 实现 CapabilityRegistry 全套（注册/视图/调用/receipt/策略/幂等/bridge）。
- 评审修复 R-1（重放极性）、R-2（引用歧义）、R-3（补 11 个测试，模块覆盖率达 100%）、R-4（契约偏离登记）、R-5（ADR-01 引用溯源校正）。
- 评审修复 R-6（候选准入语义）：实测两条 FAILED 路径对已 emit 候选处理不一致（异常路径丢、契约违规路径留）→ 统一为「保留原始记录」；新增 `CapabilityInvocationReceipt.candidates_admissible`（computed，判据 = `outcome_status=completed`）与 `CapabilityInvocation.admissible_candidates`；补 5 个测试。
- 29 个 focused 测试覆盖全部验收场景。

## Pending

- 用户侧功能场景自测（场景 1–8）。
- commit/push/PR。
- Owner review 与 S3 promotion；D-1/D-4 裁决。

## Next step

用户完成场景自测后提交并推送分支、创建 PR；Owner review 与 S3 promotion 按全局路线。

## Verification

- [x] `python -m pytest tests/test_capability_registry.py`（29 passed）。
- [x] `--cov=autoresearch.capability_registry`（100%，210 stmts / 0 miss）。
- [x] `python -m pytest tests`（137 passed）。
- [x] `python -m ruff check src tests`（通过）。
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/S3-A-CAPABILITY-ADAPTERS.md --base main`（valid）。
- [x] 用户侧独立复跑 Step 1（R-A 显式 `--basetemp`）：全量 `[100%]` 无 F/E、focused 24、模块覆盖率 100%（201 stmts / 0 miss）、ruff `All checks passed!`、check.mjs `valid`（17/17，0 commits / 9 files，+8/-2）。精确 passed 计数因 `addopts="-q"` 叠加未观测。
- [ ] 用户侧功能场景自测（本文件完成后由用户执行并回填 observed 证据）。

## Handoff note

- From: `member A`
- To: `user/team`
- 代码与任务包/账本均在 `codex/s3-a-capability-adapters`；尚未 commit/push/PR。
- 本包只交付四协议统一调用边界；MCP 协议本体、admission 补偿端到端、注册表持久化均明确留后续（ADR-01/I3/A5）。
- 上报记录级不一致：`TASK-SPECS.md:48` A4 状态仍为 `planned`，与 queue/registry 的 `ready` 不一致（共享规范由 owner 维护，未改）。
