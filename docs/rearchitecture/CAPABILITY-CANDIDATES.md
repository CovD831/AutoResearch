# Capability 候选清单（v0.1）

> 目标：为默认内置管线和后续可插拔接入筛选候选，不代表已经承诺接入。

## 筛选原则

- 能输出稳定的 typed object，而不是只返回自然语言；
- 能声明版本、权限、失败状态和资源需求；
- 能提供本地或离线路径，避免默认管线依赖单一外部服务；
- 能保留 receipt、artifact 和 provenance；
- 许可和数据边界清楚；
- 可以用固定 fixture 做 parity / conformance 测试。

## 候选能力

| 能力 | 候选 | 角色 | 建议 |
|---|---|---|---|
| Paper Reader | GROBID | PDF → TEI/XML、科学论文结构和参考文献 | 外部 Reader 首选；输出需再归一化为 ReadingBundle |
| Paper Reader | Docling | PDF/HTML → 统一文档对象，支持阅读顺序、表格、公式和 OCR | 适合作为第二 Reader 或复杂 PDF fallback |
| Paper Search | OpenAlex | 开放学术 works / authors / venues / concepts 检索 | 默认 metadata/search provider 候选 |
| Paper Search | Semantic Scholar API | 论文、作者、引用和推荐关系 | 作为补充 provider，不作为唯一来源 |
| Citation Metadata | Crossref REST API | DOI、作者、出版物和许可等 metadata | citation identity/metadata verifier 候选 |
| Experiment Runner | 本地受控命令 runner | command、env、timeout、seed、raw outputs | 默认内置；最符合薄 Runtime 边界 |
| Experiment Harness | Benchopt | 可重跑、可比较的优化 benchmark 编排 | 后续候选；仅接 adapter，不引入第二 scheduler |
| Evaluation Harness | Inspect AI | dataset、solver、scorer、日志和可复跑评测 | 后续候选；作为 scorer/runner 外部能力 |
| Writing | 外部 writing skill / LLM pipeline | SectionPlan → SectionDraft | 只能消费允许的 claims/evidence/artifacts |
| Reproduction Audit | Artisan-Bench / ReproRepo 思路 | paper + artifact 的复现和问题发现 | 先借鉴 case/gold 组织，不直接依赖其 judge |

## 默认内置组合

第一版建议内置：

```text
Local Paper Reader
+ Local Experiment Runner
+ Crossref/OpenAlex metadata verifier
+ Deterministic Section Validator
+ Internal Reproduction Diff Scorer
```

外部接入顺序建议为：GROBID → OpenAlex → Crossref → Docling → Inspect/Benchopt → 外部 Writer。

## 风险注记

- OpenAlex 和 Semantic Scholar 只能提供 bibliographic/discovery 数据，不能替代原文证据；
- PDF 解析器必须保留 page/section/table locator，解析成功不等于事实正确；
- 外部 Writer 不能成为 Evidence 或 Gate 的写入者；
- 外部评测 harness 不能覆盖 AutoResearch 自己的 audit 和 trust metrics；
- 任一 provider 不能隐式 fallback，fallback 必须显式记录在 receipt。

## 注册模板审查结论（2026-09-04）

当前模板可作为设计草案，但不能视为已实现的 runtime contract。正式注册池应将字段分成三层：

1. immutable identity/contract：`manifest_id`、`name`、`version`、`contract_version`、`schema_version`、`entrypoint`、`input_schema_ref`、`output_schema_ref`；
2. policy/profile：`trust_tier`、权限、网络 allowlist、sandbox、secret refs、数据保留、默认 provider、fallback policy；
3. operational：timeout、retry/cancellation、recovery、concurrency、resource estimate、healthcheck、conformance fixture、owner、lifecycle。

需要在后续实现中补齐或裁决：

- 通用 `CapabilityRequest/Response` 尚未落地，当前代码只有 Paper Search adapter；
- `EvidenceCandidate` 当前强绑定 `paper_id`，需要 generic artifact/subject refs 或 capability-specific subtype；
- replay receipt 需要保留原始 outcome，不应只覆写成 `replayed`；
- Paper Search legacy `_persist` 与 candidate admission 的双写问题必须先裁决；
- `ReadingBundle`、`BenchmarkPlan`、`RunManifest` 等文档对象需要逐步落成 typed contracts；
- 普通编辑不应要求计算 implementation digest/checksum，只有安全、发布或字节身份场景才启用。

因此：注册模板现在可以先冻结为设计接口；具体 provider、serialization、retry 和 isolation 仍保持可配置，不应隐式写死。
