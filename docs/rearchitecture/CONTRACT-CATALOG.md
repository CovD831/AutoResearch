# Contract 册（v0.1）

> 目的：记录 AutoResearch 的模块输入、输出、所有权、失败语义和兼容规则。
>
> 状态：L1/L2 已定义；typed model 和 runtime enforcement 分阶段落地。

## 1. Contract 分层

### Immutable Contract

所有 capability 必须具备：

```text
manifest_id
capability_name
version
kind
entrypoint
contract_version
input_schema_ref
output_schema_ref
```

它定义“是谁、如何调用、输入输出是什么”，不能随单次 invocation 改变。

### Trust / Policy Contract

所有 capability 必须声明：

```text
trust_tier
permissions
network_allowlist
filesystem_sandbox
secret_refs
data_retention
external_write
evidence_mode
```

它定义准入、权限和数据边界。

### Execution / Operational Contract

所有 capability 必须显式声明支持与否，并在 invocation 中提供实际配置：

```text
supports_replay
supports_recovery
supports_retry
timeout
retry_limit
cancellation
concurrency_limit
resource_budget
failure_codes
```

缺少支持能力时必须写 `false` 或 `0`，不能依靠缺省推断。

### Lifecycle / Observability Contract

```text
owner
status
support_window
healthcheck
conformance_fixture
trace_parent
event_schema_version
redaction_policy
```

## 2. 统一调用协议

```text
CapabilityRequest
  project_id
  run_id
  invocation_id
  manifest_ref
  bounded_input
  input_schema_version
  idempotency_key
  trace_id
  requested_permissions

CapabilityResponse
  status: completed | failed | unknown | replayed
  outcome_status: completed | failed | unknown
  typed_output
  output_schema_version
  diagnostics[]
  receipt
  evidence_candidates[]
  artifact_refs[]
```

`replayed` 是传输状态，不得覆盖原始业务结果；原始结果保存在 `outcome_status`。

### 2.1 最小 typed schema 草案（语言无关）

以下字段是跨 native、skill、MCP 和 external service 的最小共同集合。具体能力的参数必须放入 `bounded_input` / `typed_output` 所引用的 capability-specific schema，不得把 Reader、Search 或 Runner 的字段提升到通用信封。

```text
CapabilityManifest {
  manifest_id: string                 # 稳定注册项身份，不随 invocation 改变
  capability_name: string
  version: string
  kind: native | skill | mcp | external_service
  entrypoint: string
  contract_version: string
  input_schema_ref: SchemaRef
  output_schema_ref: SchemaRef
  permissions: PermissionSet
  trust_tier: local | reviewed_external | unreviewed_external
  evidence_mode: none | candidates | receipt_only
}

SchemaRef {
  name: string
  version: string
  media_type: string                 # application/json 等
  ref: string | null                  # registry 内部或 URI 引用
}

CapabilityRequest {
  project_id: string
  run_id: string
  invocation_id: string
  manifest_ref: string                # manifest_id + version 的解析结果
  bounded_input: object
  input_schema_version: string
  idempotency_key: string
  trace_id: string
  parent_invocation_id: string | null
  requested_permissions: PermissionSet | null
}

CapabilityResponse {
  status: completed | failed | unknown | replayed
  outcome_status: completed | failed | unknown
  typed_output: object | null
  output_schema_version: string
  diagnostics: Diagnostic[]
  receipt: InvocationReceipt
  evidence_candidates: GenericEvidenceCandidate[]
  artifact_refs: ArtifactRef[]
}

PermissionSet {
  network: none | allowlist
  filesystem: none | sandbox | project_read | project_write
  secrets: string[]                 # 仅引用名称，不携带 secret 值
  external_write: boolean
}

Diagnostic {
  code: string
  message: string
  retryable: boolean
  details: object | null
}

GenericEvidenceCandidate {
  candidate_id: string
  project_id: string
  run_id: string
  invocation_id: string
  capability_ref: string
  subject_ref: string | null          # paper/claim/run/artifact 等业务对象
  claim_ref: string | null
  claim: string | null
  source_ref: string | null
  locator: string | null
  artifact_refs: ArtifactRef[]
  provenance: Provenance
  status: candidate | duplicate | conflict | rejected
}

Provenance {
  source_kind: input | external_source | execution | derived
  source_uri: string | null
  source_version: string | null
  adapter_version: string
  created_at: datetime
}
```

约束：`CapabilityResponse.receipt` 必须记录 request fingerprint、manifest ref、实际权限和最终 outcome；`typed_output` 为空时不得声明 `completed`。`GenericEvidenceCandidate` 只能提交 Evidence Admission，不能直接升级为 `EvidenceItem`。`subject_ref` 取代 paper-specific `paper_id`；Paper Search 可在其扩展 schema 中保留 `paper_id`。

## 3. 领域 Contract 索引

| Contract | 当前状态 | 主要消费者 |
|---|---|---|
| PaperSearchRequest / PaperRecord | 部分实现 | Search、Reader |
| ReadingBundle | 文档定义，待 typed model | Evidence、Section Planner |
| EvidenceCandidate / EvidenceBundle | 部分实现 | Evidence Admission、Gate |
| BenchmarkPlan | 文档定义，待 typed model | Readiness、Runner |
| RunManifest / ExperimentArtifact | 文档定义，待 runner | Evidence、Writer、Validator |
| SectionPlan / SectionDraft | 文档定义，P1 部分实现 | Writer、Validator |
| RuleValidationReport | 文档定义，待 typed model | Pipeline、Delivery |

## 4. 所有权

- Evidence Module：EvidenceItem、ClaimLink、ArtifactLink；
- Gate Service：GateDecision；
- Runtime / State Machine：生命周期状态；
- Capability Adapter：receipt、幂等记录、候选输出；
- Experiment Runner：RunManifest、raw outputs、metrics；
- Writer：SectionDraft 草稿，不得新增无证据事实。

## 5. 冻结与变更规则

- additive 字段优先保持向后兼容；
- 破坏性变更提升 major contract version；
- 每次变更必须更新 schema、fixture、parity test 和 migration note；
- capability-specific 字段放 extension，不污染通用 contract；
- P1 完成后的重点是实现一致性审计，不重新设计 L1/L2。

## 6. 冻结字段与开放字段

### 6.1 现在应冻结

- 身份与追踪：`manifest_id`、`capability_name`、`version`、`project_id`、`run_id`、`invocation_id`、`trace_id`；
- 信封结构：`bounded_input`、typed output、receipt、diagnostics、evidence candidates、artifact refs；
- schema 发现：`contract_version`、输入/输出 schema 名称、版本和 media type；
- 权限最小化：manifest 声明权限，request 只能请求不超过 manifest 的权限；
- 幂等与结果：idempotency key、冲突 replay 拒绝、`status` 与 `outcome_status` 分离；
- 证据边界：candidate 只能提交准入；Evidence/Gate/lifecycle 的唯一写入者不变；
- 失败语义：completed、failed、unknown 三种业务结果必须可区分，未知结果不得伪造成功；
- 版本规则：新增字段优先兼容，语义破坏升级 major，并同步 fixture/parity/migration。

### 6.2 暂时保持开放

- provider 的具体实现、skill/MCP 协议和 entrypoint 解析方式；
- JSON Schema、Pydantic、Protobuf 等实际 schema 编码和传输协议；
- retry/backoff、队列、取消和跨进程隔离的具体实现（能力必须声明是否支持）；
- 签名、来源许可、依赖锁定和供应链证明字段的最终格式；
- 资源预算的细粒度单位与成本模型；
- capability-specific typed input/output 和 evidence 扩展字段；
- registry 的发现后端、热加载和多 provider 选择算法。

开放不等于隐含：若某能力不支持上述功能，manifest 应显式写 `false`、`none` 或空集合，而不是依赖默认值。
