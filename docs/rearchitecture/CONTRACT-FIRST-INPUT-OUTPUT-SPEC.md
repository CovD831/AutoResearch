# Contract-first 输入输出规格（v0.1）

> 状态：基于已冻结 L1/L2 的实施前规格；P1 完成后只做实现一致性核对。

## 1. 统一调用信封

所有可插拔能力都通过同一调用信封进入 Runtime：

```text
CapabilityRequest
  project_id
  run_id
  invocation_id
  capability_name
  capability_version
  bounded_input
  idempotency_key

CapabilityResponse
  typed_output
  diagnostics[]
  invocation_receipt
  evidence_candidates[]
  artifact_refs[]
  status: completed | failed | unknown | replayed
```

约束：reserve 先于外部副作用；相同 identity 和 fingerprint 必须可 replay；冲突 replay 必须拒绝；timeout、provider error、parse error 和 unknown 必须显式返回。

## 2. 纵向管线矩阵

| Stage | 输入 | 输出 | 主要消费者 | 失败状态 |
|---|---|---|---|---|
| Intake | ProjectCreate、Research Question、PaperType | ResearchPlan、初始 claims、未知项 | Orchestrator、Planner | invalid_input、blocked |
| Search | ResearchPlan、SearchRequest | PaperRecord[]、SearchReceipt、EvidenceCandidate[] | Reader、Evidence Admission | failed、unknown、unavailable |
| Read | PaperRecord、ReadRequest | ReadingBundle、Section、Claim、Citation、Locator | Evidence、Section Planner | parse_error、incomplete、unknown |
| Evidence Admission | EvidenceCandidate[] | EvidenceItem、ClaimLink、ArtifactLink、admission report | Gate、Writer、Audit | duplicate、conflict、rejected |
| Section Plan | PaperType、WritingProfile、EvidenceBundle、BenchmarkPlan | SectionPlan[] | Experiment、Writer、Validator | missing_material、blocked |
| Benchmark Plan | Claims、Method、Dataset、Resources | BenchmarkPlan | Readiness、Experiment Runner | insufficient_material、planned |
| Experiment | BenchmarkPlan、RunRequest、Environment | RunManifest、RawOutputs、Metrics、ExperimentArtifact | Evidence、Writer、Validator | timeout、failed、unknown |
| Section Draft | SectionPlan、allowed claims、Evidence、ExperimentArtifact | SectionDraft | Validator、Audit、Delivery | blocked、revise |
| Rule Validation | SectionDraft、SectionPlan、Evidence、Artifacts | RuleValidationReport | Pipeline、Delivery | verified、revise、blocked |
| Manuscript Delivery | validated sections、reports、artifacts | Reproduction Report、delivery manifest | User | blocked、incomplete |

## 3. 领域对象最小要求

### PaperRecord

必须包含 paper identity、来源、版本或年份、可用正文位置和项目归属。

### ReadingBundle

必须能定位 section、claim、citation、table、figure 和 locator；不能只有无来源的摘要文本。

### EvidenceCandidate

必须包含 source、locator、claim、provenance、run_id、invocation_id 和 adapter identity；只能进入 Evidence Admission，不能直接成为正式 EvidenceItem。

### EvidenceBundle

必须包含 project_id、claim 和 evidence_ids；关键 claim 的 evidence 必须可定位且状态有效。

### BenchmarkPlan

必须区分 benchmark、baseline、metrics、required materials、risks 和 status；`planned` 不得表示已观察结果。

### RunManifest / ExperimentArtifact

必须记录 command、code/data/environment version、parameters、seed、exit status、raw outputs、metrics 和异常。

### SectionDraft

必须包含 section_id、section_type、writing_profile、claims、citations、evidence_refs、experiment_refs、unresolved_items 和 validation_status。

## 4. 所有权和禁止越权

| 对象 | 唯一写入者 | Adapter 是否可写 |
|---|---|---:|
| Invocation receipt / idempotency | Capability Adapter + Store 幂等表 | 是 |
| EvidenceItem / ClaimLink / ArtifactLink | Evidence Module | 否 |
| GateDecision | Gate Service | 否 |
| Pipeline lifecycle state | Runtime / State Machine | 否 |
| RunManifest | Experiment Runner / Runtime | 仅通过 contract |
| SectionDraft prose | Writer capability | 仅输出草稿，不改 Gate |
| Audit event | 对应 owner service | 仅按事件 contract |

## 5. 版本和兼容

- schema 版本必须随 receipt 和 artifact manifest 保存；
- 新增字段优先向后兼容；
- 删除或改变语义必须增加 major contract version；
- adapter 不得依赖未声明的下游字段；
- legacy facade 在 removal gate 前继续可运行；
- P1 完成后执行 legacy/target parity，而不是重定义 contract。

## 6. P1 后核对清单

- 字段是否完整；
- producer / consumer 是否与实现一致；
- planned、observed、failed、unknown 是否分离；
- receipt、artifact、evidence 是否能互相追溯；
- 失败和恢复路径是否符合 L2；
- 是否出现共享边界变更请求。

