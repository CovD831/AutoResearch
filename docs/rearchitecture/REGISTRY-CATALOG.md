# Registry 册（v0.1）

> 目的：登记可被 Runtime 选择的 native、skill、MCP 和 external service 能力。
>
> 注册不等于授权；注册池不拥有 Evidence、Gate 或生命周期状态。

## 1. 注册记录结构

每个 registry entry 使用：

```text
Identity / Contract
  manifest_id, name, version, kind, entrypoint
  contract_version, schema_version
  input_schema_ref, output_schema_ref

Trust / Policy
  trust_tier, permissions, network_allowlist
  filesystem_sandbox, secret_refs, data_retention
  external_write, evidence_mode, default_provider

Operations
  supports_replay, supports_recovery, supports_retry
  timeout, retry_limit, cancellation, concurrency
  resource_estimate, failure_codes

Lifecycle / Observability
  owner, status, support_until, healthcheck
  conformance_fixture, parity_fixture, trace_schema
```

详细 YAML 模板见 [CAPABILITY-REGISTRY-TEMPLATE.yaml](CAPABILITY-REGISTRY-TEMPLATE.yaml)。

## 2. Provider 选择规则

- 同一 capability 可以注册多个 provider；
- Runtime 选择必须记录 resolved provider 和 version；
- default provider 必须明确声明；
- fallback 只能按显式 policy 执行并写入 receipt；
- 不允许 adapter 自行切换 provider；
- 未声明的网络、文件或 secret 权限必须拒绝。

## 3. 注册状态

```text
draft → conformance_pending → active → deprecated → retired
```

- `draft`：只有 manifest，不能被默认 Runtime 选择；
- `conformance_pending`：正在跑契约和安全测试；
- `active`：可按 policy 选择；
- `deprecated`：仍可重放旧 run，但不接新任务；
- `retired`：只保留历史 receipt 和 artifact 引用。

## 4. 最小准入门

能力进入 `active` 前必须通过：

1. input/output schema 校验；
2. idempotency / replay 测试；
3. timeout、failure 和 unknown 测试；
4. evidence / artifact 行为测试；
5. sandbox、网络和 secret 检查；
6. conformance fixture；
7. legacy/target parity（存在 legacy 时）。

## 5. 第一批登记对象

```text
paper_reader.local
experiment_runner.local
citation_verifier.local
section_validator.native
reproduction_scorer.native
```

外部候选先登记为 `draft`，完成 adapter 和 conformance 后再启用：GROBID、Docling、OpenAlex、Crossref、Inspect AI、Benchopt、外部 Writer。

## 6. 首批 manifest 示例

下面的示例是注册池的最小可执行记录。它们保留运行时调用所需的
`name`/`version`，同时补齐 provider 选择、权限、失败语义和契约测试信息。
`input_schema_ref` 与 `output_schema_ref` 指向 L2 typed contract；外部 provider 的
原生响应必须先由 adapter 归一化，不能直接流入 Evidence 或 Gate。

### 6.1 默认内置能力

```yaml
- manifest_id: paper_reader.local@0.1.0
  name: paper_reader
  version: 0.1.0
  kind: native
  entrypoint: autoresearch.reader_service:ReaderService
  contract_version: l2
  schema_version: 0.1
  input_schema_ref: PaperReadRequest
  output_schema_ref: ReadingBundle
  selection: {enabled_by_default: true, priority: 10, supports_offline: true}
  trust: {tier: local, network_required: false, external_write: false}
  execution:
    supports_replay: true
    supports_recovery: false
    supports_retry: true
    timeout_seconds: 120
    failure_codes: [parse_error, unavailable, failed, unknown]
  evidence: {mode: candidate_only, admission_owner: evidence_service}
  artifacts: [reading_bundle, locator_index]
  conformance_fixture: fixtures/capabilities/paper_reader/minimal.pdf
  status: active
```

```yaml
- manifest_id: experiment_runner.local@0.1.0
  name: experiment_runner
  version: 0.1.0
  kind: native
  entrypoint: autoresearch.execution:LocalExperimentRunner
  contract_version: l2
  schema_version: 0.1
  input_schema_ref: ExperimentRunRequest
  output_schema_ref: RunResult
  selection: {enabled_by_default: true, priority: 10, supports_offline: true}
  trust:
    tier: local
    network_required: false
    external_write: false
    sandbox_required: true
  execution:
    supports_replay: true
    supports_recovery: true
    supports_retry: false
    timeout_seconds: 1800
    failure_codes: [invalid_command, timeout, nonzero_exit, cancelled, unknown]
  evidence: {mode: none, admission_owner: evidence_service}
  artifacts: [run_manifest, raw_output, metrics, experiment_artifact]
  conformance_fixture: fixtures/capabilities/experiment_runner/hello_world.yaml
  status: active
```

```yaml
- manifest_id: citation_verifier.local@0.1.0
  name: citation_verifier
  version: 0.1.0
  kind: native
  entrypoint: autoresearch.citation:LocalCitationVerifier
  contract_version: l2
  schema_version: 0.1
  input_schema_ref: CitationVerifyRequest
  output_schema_ref: CitationVerificationBundle
  selection: {enabled_by_default: true, priority: 10, supports_offline: true}
  trust: {tier: local, network_required: false, external_write: false}
  execution:
    supports_replay: true
    supports_recovery: false
    supports_retry: true
    timeout_seconds: 60
    failure_codes: [malformed_citation, identity_mismatch, unavailable, unknown]
  evidence: {mode: candidate_only, admission_owner: evidence_service}
  artifacts: [citation_report, locator_index]
  conformance_fixture: fixtures/capabilities/citation_verifier/citations.json
  status: active
```

### 6.2 外部候选能力

```yaml
- manifest_id: paper_reader.grobid@0.8.x
  name: paper_reader
  version: 0.8.x
  kind: external_service
  entrypoint: adapter.grobid:GrobidReaderAdapter
  contract_version: l2
  schema_version: 0.1
  input_schema_ref: PaperReadRequest
  output_schema_ref: ReadingBundle
  selection: {enabled_by_default: false, priority: 20, supports_offline: false}
  trust:
    tier: reviewed_external
    network_required: true
    external_write: false
    allowed_network_domains: [grobid_service]
  execution:
    supports_replay: true
    supports_recovery: false
    supports_retry: true
    timeout_seconds: 180
    failure_codes: [http_error, parse_error, unavailable, unknown]
  normalization: {native_output: TEI_XML, adapter_output: ReadingBundle}
  evidence: {mode: candidate_only, admission_owner: evidence_service}
  artifacts: [tei_xml, reading_bundle, locator_index]
  conformance_fixture: fixtures/capabilities/paper_reader/grobid_sample.tei.xml
  parity_fixture: fixtures/capabilities/paper_reader/reader_parity.json
  status: draft
```

```yaml
- manifest_id: paper_search.openalex@0.1.0
  name: paper_search
  version: 0.1.0
  kind: external_service
  entrypoint: adapter.openalex:OpenAlexSearchAdapter
  contract_version: l2
  schema_version: 0.1
  input_schema_ref: PaperSearchRequest
  output_schema_ref: PaperSearchBundle
  selection: {enabled_by_default: false, priority: 20, supports_offline: false}
  trust:
    tier: reviewed_external
    network_required: true
    external_write: false
    allowed_network_domains: [api.openalex.org]
  execution:
    supports_replay: true
    supports_recovery: false
    supports_retry: true
    timeout_seconds: 30
    failure_codes: [rate_limited, unavailable, malformed_response, unknown]
  normalization: {native_output: OpenAlexWork, adapter_output: PaperRecord}
  evidence: {mode: candidate_only, admission_owner: evidence_service}
  artifacts: [raw_response, search_diagnostics]
  conformance_fixture: fixtures/capabilities/paper_search/openalex_response.json
  status: draft
```

## 7. 字段映射约定

| 注册能力 | 外部/本地输入 | 归一化输出 | 进入下游前的约束 |
|---|---|---|---|
| `paper_reader.local` | `PaperReadRequest.paper_ref` + PDF/HTML | `ReadingBundle`（兼容现有 `ReadingCard`） | 保留 page/section/table locator；证据仅以 candidate 进入 admission |
| `experiment_runner.local` | command、cwd、env、timeout、seed、expected outputs | `RunManifest`、`RawOutputs`、`Metrics`、`ExperimentArtifact` | 未知退出状态不得转成 observed；所有副作用在 sandbox 内 |
| `citation_verifier.local` | bibliography、citation spans、允许来源 | `CitationVerificationBundle` + candidates | 只报告 identity/locator/availability，不自行判定 claim truth |
| `paper_reader.grobid` | PDF bytes/URI | TEI XML → `ReadingBundle` | 原生 TEI 必须保留为 artifact；provider 错误写入 receipt |
| `paper_search.openalex` | query、filters、pagination、seed papers | `PaperRecord[]` + diagnostics | 仅 metadata/discovery；不直接当全文证据；响应原文保留 artifact |

所有 manifest 都必须能生成现有 `InvocationReceipt`：`invocation_id`、`run_id`、
`CapabilityManifest{name,version}`、status、request 摘要和 diagnostics；provider、
resolved version、fallback 与 normalization 结果应写入 diagnostics 或扩展 receipt，
而不是改变 L2 的核心字段。
