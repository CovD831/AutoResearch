# R-004-01 定位、范围与复杂度预算

## 要解决的问题

1. 替换一个用户偏好的 Skill/MCP/工具需要同时触碰 Runtime、Agent、Service 与 Store 多层（INDEPENDENT-2026-09-03 的既有诊断，R-002 继承）。
2. 可信机制（证据、门禁、审计）散落在应用装配与各 Agent 私有逻辑中，无法独立复用，也无法对外输出为产品能力。
3. 项目需要一个与市场定位一致的产品形态：认知层可插拔借用生态，信任层（Evidence/Policy/Audit）是自研本体并对外可交付。

## 目标用户

- 想用自有 Skill、MCP 或本地科研工具组装研究流程的研究者与团队。
- 需要对 AI 产出稿件做引用/声明核验与审计留痕的作者、审阅者（Audit Module 的外部消费者）。
- 需要审计、复核、人工发布批准的高风险科研场景。

## 价值假设

1. 用户可替换能力而不改 Runtime 主流程（S1/S3 证明）。
2. 外部工具输出统一进入 EvidenceCandidate 接纳，不产生第二写入者（S1 证明）。
3. Audit Module 可独立于完整研究流程对外核验任意稿件的引用与声明（S2 证明）。
4. 同一任务下 gate 开/关的伪造率差异可用公开 benchmark 度量（S4 证明）。

每条假设的对照基线：1 对照 native 直连路径；2 对照 legacy 持久化路径；3 对照裸 LLM + 无审计；4 对照裸 LLM / 无 gate 变体。依据见 `docs/市场调研与定位分析_2026-09.md`（市场事实，非架构权威）。

## 非目标

- 不与 Elicit/STORM/PaperQA/zotero-mcp 等单点能力产品竞争；它们以 adapter 接入。
- 不默认把每个模块做成插件；不建插件市场、不做动态加载（延至出现第二个真实 capability consumer 后的独立增量）。
- 不在 S1–S4 内承诺任何科研质量指标（阅读/写作质量属于可替换能力，另立验收）。

## 复杂度预算

继承 R-001 已放行的四个 L2 名词：`CapabilityManifest`、`CapabilityAdapter`、`InvocationReceipt`、`EvidenceCandidate`。R-004 新增两个名词（第二个为 07 对抗审查 F-1 补报）：

| 名词 | 真实消费者 | 解决的问题 |
|---|---|---|
| `AuditVerdict` | Policy/Gate（审核输入）、外部 MCP 审计消费者（writer agent 自检） | 单项核验的确定结果：`pass / fail / unknown` + 目标引用 + 证据引用，避免审计结果以散文或隐式布尔形式传播 |
| capability `trust tier` | Registry/接纳上限逻辑（candidate_only 的 P0/H1 封顶）、operator 注册治理 | 把"能力可信度"从 manifest 自述改为 operator 指派的事实，防止模块自抬证据等级 |

删除任一名词：前者把审计结果混回 ReviewReport 散文；后者让信任层级退化为模块自我声明。均通过 over-design gate。plugin lifecycle、进程隔离、版本共存、第二数据库等名词继续缺席；出现第二个真实 capability consumer 前不申请。
