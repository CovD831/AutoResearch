# P1 闭环后的集成与复现计划

> 版本：v0.1
>
> 日期：2026-09-04
>
> 状态：计划草案，等待 P1-A/P1-B 和 I0–I4 验收后进入实施排期

## 1. 目标

基于已经冻结的 L1 总体架构和 L2 模块边界，现在就定义一条开箱即用的默认管线：输入一个可复现论文包，运行内置能力，生成一份实证型复现论文，并输出与原论文的结构、方法、结果和证据差异报告。

在此基础上，建立统一的 Capability Registry 和 Adapter Contract，使外部 skill、MCP、开源项目或本地实现可以替换单个能力，而不改变 Runtime、Evidence、Gate 和 Pipeline 的边界。

P1 成员任务属于模块内部实现；它们不决定 L1/L2 的总体方向。成员实现期间即可完成 contract-first 的输入包和能力注册设计，P1 完成后再做一次实现一致性审计，并跑真实端到端 case。

## 2. 冻结的产品方向

### 2.1 首版论文类型

首版只支持 `Empirical Reproduction Report`（实证型复现报告），不支持综述、理论论文、人类受试者研究或多种 venue 格式。

固定章节：

1. Abstract
2. Research Question and Original Work
3. Reproduction Protocol
4. Experimental Setup
5. Results
6. Comparison with Original Results
7. Deviations and Failure Analysis
8. Limitations
9. Reproducibility Appendix

### 2.2 两套独立评测

不计算跨体系总分。

- `Paper Reproduction Scorecard`：论文结构、科研对象、过程、结果、claim、引用、偏差披露和复现材料。
- `Trust Mechanism Ablation Scorecard`：Gate、Evidence、Provenance、Audit、Replay、Recovery 和资源开销。

Gate 开启/关闭属于机制消融，不进入论文质量分数。

## 3. 工作流总览

```text
Reproduction Package
  → Case Intake
  → Paper / Artifact Reading
  → Evidence Admission
  → Reproduction Plan
  → Local Experiment Runner
  → RunManifest / Metrics / Artifacts
  → SectionPlan
  → SectionDraft
  → Rule Validation
  → Paper Reproduction Report
  → Structural / Content Diff
  → Mechanism Ablation Report
```

原论文正文主要作为 evaluator 的 gold reference；生成阶段优先消费代码、数据、配置、运行结果和结构化元数据，避免把 benchmark 变成原文改写测试。

L1/L2 已经可以提前确定逻辑输入：`PaperRecord`、`ReadingBundle`、`EvidenceCandidate`、`EvidenceBundle`、`BenchmarkPlan`、`RunManifest`、`ExperimentArtifact`、`SectionPlan` 和 `WritingProfile`。P1 完成后需要确认的是字段是否完整、状态语义是否一致、实际消费者是否覆盖，而不是重新发现这些输入。

## 4. Reproduction Case 输入包

每个 case 采用版本化目录：

```text
reproduction_case/
  case.yaml
  original_paper.pdf
  paper_metadata.json
  research_question.json
  source_manifest.json
  code/
  data_manifest.json
  environment/
  run_commands/
  original_results/
  expected_schema/
  allowed_references/
```

`expected_schema/` 是评测 gold，不是原文副本，至少包含：

- research question；
- method / model；
- dataset；
- baseline；
- metrics；
- experiment settings；
- atomic claims；
- result tables；
- limitations；
- reproduction requirements。

第一版 case 选择标准：公开代码和数据、运行成本可控、一个主任务、2–4 个 baseline、2–4 个指标、至少一张主结果表、无需私有 API 或人工受试者数据。

## 5. Capability Registry

### 5.1 目的

Registry 是能力发现和选择层，不执行能力本身，也不拥有 Evidence 或 Gate 状态。Runtime 根据 registry 选择 adapter，并将统一的 bounded input 传入能力。

### 5.2 最小字段

```yaml
capability_name: paper_reader
version: 0.1
kind: native | skill | mcp | external_service
input_schema: PaperReadRequest
output_schema: ReadingBundle
trust_tier: local | reviewed_external | unreviewed_external
side_effects: none | artifacts | external_write
network_required: false
idempotency_support: true
timeout_behavior: explicit_failure
failure_states: [parse_error, unavailable, unknown]
evidence_behavior: emits_candidates | emits_refs | none
artifact_behavior: emits_artifacts | none
adapter: autoresearch.capabilities.paper_reader
```

### 5.3 Registry 约束

- 同一 capability name 可以存在多个版本，但选择必须显式可追溯；
- 每个 adapter 必须声明输入输出 schema、权限、side effects 和失败语义；
- 外部能力不能直接写 Evidence、GateDecision 或项目状态；
- reserve 必须先于外部副作用；
- 相同 invocation identity 和 fingerprint 必须可 replay；
- unknown、timeout、parse error 不能自动转换成 success；
- Registry 不允许隐式 fallback 到另一个 provider；
- 默认能力必须有本地、离线或最小依赖实现。

## 6. L2 Adapter Contract

统一能力调用形态：

```text
CapabilityRequest
  = project_id + run_id + invocation_id
  + capability_version + bounded_input

CapabilityResponse
  = typed_output
  + diagnostics
  + InvocationReceipt
  + EvidenceCandidate[]
  + ArtifactRef[]
```

adapter 的职责：

- 输入校验；
- capability invocation；
- 幂等和 replay；
- provider 错误归一化；
- receipt 和 artifact ref；
- 将候选证据交给 Evidence Admission。

adapter 不负责：

- 直接写 EvidenceItem；
- 直接做 GateDecision；
- 修改 Pipeline 状态；
- 把 unknown 结果包装成成功；
- 修改外部项目或论文原始材料。

## 7. 默认内置能力与接入顺序

### 阶段 1：默认闭环能力

P1 和 I0–I4 完成后，先提供以下内置能力：

1. `Paper Reader`：PDF/HTML 到 PaperRecord、Section、Claim、Citation、Table、Locator；
2. `Local Experiment Runner`：命令、环境、超时、seed、原始输出和退出状态；
3. `Citation Metadata Verifier`：引用身份、元数据、去重和 locator 基本检查；
4. `Deterministic Section Validator`：SectionPlan、SectionDraft、claim/evidence/artifact 绑定和 planned/observed 规则；
5. `Reproduction Diff Scorer`：结构、过程、结果、claim 和偏差报告。

目标：不依赖外部 skill，也能跑通一个真实 reproduction case。

### 阶段 2：可替换外部能力

默认闭环稳定后，再接入：

1. Paper Search provider；
2. 外部 Reader skill；
3. 外部 Writing skill；
4. 外部 Experiment Harness；
5. MCP capability。

每次只替换一个 capability，并运行 legacy/target parity 与机制回归测试。

### 阶段 3：规模化能力

最后再考虑多 provider、远程执行、多论文类型、多 venue、批量 case 和公开 benchmark 发布。

## 8. Paper Reproduction Scorecard

每个维度独立报告，不计算总分：

- Structural Alignment；
- Research Object Coverage；
- Procedure Fidelity；
- Result Alignment；
- Claim Alignment；
- Citation / Evidence Alignment；
- Deviation Reporting；
- Reproducibility Completeness。

每个指标必须保存：定义、分子、分母、输入 artifact、case 版本、run ID、报告状态和失败原因。

## 9. Trust Mechanism Ablation Scorecard

每个维度独立报告：

- False-pass Rate；
- Block Recall；
- Over-blocking Rate；
- Evidence Integrity；
- Provenance Completeness；
- Audit Completeness；
- Replay / Idempotency Correctness；
- Recovery Correctness；
- Latency / Resource Overhead。

首批消融条件：

```text
A: Gate off
B: Gate on
C: Gate on + Evidence enforcement
D: Gate on + Evidence enforcement + Recovery/Replay
```

所有条件固定 case、prompt、模型、材料、预算和随机种子，只改变待研究的机制变量。

## 10. 分阶段交付与验收

### R0：Contract-first 输入与能力盘点（可立即开始）

交付：根据 L1/L2 和当前 P1 任务包整理出的 pipeline input/output matrix、首版 reproduction case 选择标准、Capability Registry 草案和 adapter 清单。

验收：每个 stage 都有明确的 producer、consumer、schema、evidence/artifact 产物和失败状态；不等待 P1 成员实现完成。

### R1：P1 实现一致性审计

交付：将 R0 的 contract-first 清单与 P1 实际实现对照，记录字段缺口、命名偏差、额外状态和共享边界变更请求。

验收：P1 实现与 L1/L2 契约一致，所有偏差有明确处理结论；若需变更共享 contract，先走集成决策。

### R2：首个 Reproduction Package

交付：一个公开、低成本、可重跑 case 和 expected schema。

验收：基于 R0 的输入矩阵构造 case；本地可执行，原始结果和 gold 结构化事实可追溯。

### R3：Registry + Adapter MVP

交付：Registry schema、内置能力 manifest、一个外部能力 adapter、receipt/replay 测试。

验收：替换单个 capability 不修改 Pipeline、Evidence 或 Gate 代码。

### R4：Paper Reproduction Scorer

交付：结构、过程、结果、claim、引用和复现材料差异报告。

验收：planned、unknown、failed 和 unavailable 不会被写成 observed；报告可重跑。

### R5：Mechanism Ablation

交付：Gate on/off 和 recovery/replay 对比报告。

验收：报告 false-pass、block recall、over-blocking 和成本变化，不生成跨体系总分。

### R6：外部能力扩展

交付：至少一个 Reader 或 Writer 外部 adapter，含 parity、失败和回滚证据。

验收：外部能力遵守 L2 contract，越权写入和隐式 fallback 被拒绝。

## 11. 风险与停止条件

- 如果首个 case 需要大量人工标注，先降级为结构化事实和结果表对比；
- 如果外部 skill 无法提供稳定 typed output，不接入默认管线；
- 如果 provider 结果无法留下 receipt、artifact 或 evidence provenance，不进入正式 benchmark；
- 如果需要修改共享 `contracts.py`、`application.py` 或 Store，先提交共享边界变更请求；
- 如果生成器可以直接复制原论文正文，必须单独标记为 conditioned track，不与 reproduction track 混比；
- 如果无法区分 planned、observed、failed 和 unknown，停止扩大论文生成范围。

## 12. 当前不做的事情

- 不做多论文类型；
- 不做 venue-specific formatting；
- 不做统一总分；
- 不做专家主观总评；
- 不做自动投稿或公开发布；
- 不做大规模远程执行平台；
- 不在 P1 闭环前引入大量外部 provider。
