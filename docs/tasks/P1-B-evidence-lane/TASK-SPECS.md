# B 线任务详细规格

本文件让成员 B 可以沿着 Evidence/Domain lane 连续推进；每个任务仍然必须单独提交 PR、测试和 handoff。状态以全局注册表为准。

## B1 — P1-B Evidence / Evaluation Pipeline

- 状态：`ready`
- 目标：完成 Evidence admission、Evaluation 章节计划、WritingProfile、材料就绪、benchmark 计划和章节规则验证。
- 主要交付：`evidence.py`、`writing_service.py`、pipeline/readiness/benchmark/validator 模块、fixture、L3/PROGRESS/HANDOFF。
- 必须满足：candidate 去重和冲突处理；关键材料缺失为 `blocked`；非关键缺失为 `needs_material`；planned benchmark 不得写成 observed result；验证结果为 `verified/revise/blocked`。
- 禁止：修改 `application.py`、共享 `contracts.py`、A 线独占路径；旁路写 EvidenceItem。
- 验收：B1 任务包第 8 节的 Evidence、Section、Readiness、Benchmark、Validation 全部通过。

## B2 — P1-B Evidence Adversarial

- 状态：`ready-next`，依赖 B1。
- 目标：补足证据、章节和规则验证的对抗性 fixture 与 fail-closed 回归。
- 主要交付：重复/冲突 candidate、伪造数字、无 locator、缺 baseline、过期 evidence、planned-as-result、规则边界 fixture 和报告。
- 必须满足：任何无证据关键 claim 都不能 verified；冲突不覆盖事实；未知、失败和 limitation 保留在输出；错误必须可定位。
- 验收：正例/负例矩阵可离线重跑，所有 fail-open 场景均被阻断。
- **Owner review 补充条款（2026-09-07 深度审查，E-B1-REVIEW-FINDINGS，B2 Gate 前置）**：
  - **[Gate 阻断] F1 失效证据 fail-open**：`evidence.py` 的 `resolve(valid_only=False)` 不过滤 invalidated evidence，readiness 与 section validator 对失效证据放行并可给 VERIFIED（`readiness.py:25,32-33`、`section_validator.py:40`）。B2 必须让 readiness/validator 默认只消费 `valid` 证据，或对失效证据显式 fail-closed，并附对抗性 fixture 与回归测试。
  - **[必须关闭] F3 死枚举**：`EvidenceAdmissionStatus.BLOCKED` 不可达，L3 承诺的三个 admission 失败态只实现两个（`evidence.py`）。B2 需实现或显式删除该状态并回写 L3。
  - **[必须关闭] F2 locator 折叠**：`_source_key` 中 locator 归一化 `None → ""`，同源不同段落无 locator 时被折叠为 conflict（`evidence.py:51-57`）。B2 对抗性 fixture 需覆盖该场景。
  - **[测试] 失效证据场景零覆盖**：B2 需补充 invalidated-evidence 的 admission/readiness/validator 全链路测试。

## B3 — S2 Audit Evidence

- 状态：`waiting-for-gate`，依赖 S1 promotion。
- 目标：完成 AuditVerdict、Evidence reconciliation 和 candidate 回流。
- 主要交付：Audit evidence contract、存在性/撤稿/更正/locator 规则、AuditReport artifact、Evidence candidate reconcile。
- 必须满足：Audit 不直接写 EvidenceItem；确定性 verdict 与 unknown 分开；冲突和替代关系可追溯；网络不可用 fail-closed。
- 验收：S2 标注 fixture 的 verdict、回流和审计报告可重跑。
- **Owner scope 裁决（2026-09-09，成员问询后登记）**：S2 **不包含 MCP 协议实现**。B3 交付 Audit evidence contract、存在性/撤稿/更正/locator 规则、AuditReport artifact、candidate 回流；MCP 适配归 S3（B4 的 LLM/MCP adapter contract）。B3 的 contract 必须与传输协议无关，验收标准是标注 fixture 可重跑，不是"MCP 可调用"。
- **D-S2-01（2026-09-09，owner 集成裁决）**：B3 实现以 `src/autoresearch/audit_evidence.py` 落地（A3 保留 canonical `audit.py`），record kind `audit_evidence_report`、事件 `audit_evidence.*`。语义统一以 B3 严格语义为准（binding 需有效证据绑定、corrected/superseded 关系可追溯即 PASS、locator 空词条 fail-closed 为 unknown）；A3 运行时对应类别在 S2 promotion 集成窗口对齐。

## B4 — S3 Reader / Writer Ports

- 状态：`planned`，依赖 S2 promotion。
- 目标：将 Reader/Writer 能力接入 typed Domain Port，并保留 claim/evidence 约束。
- 主要交付：ReadingCard、SectionDraft、claim binding、LLM/MCP adapter contract、三路契约级 parity 报告。
- 必须满足：不同实现不要求文字相同，但 schema、claim 绑定、Gate 合规和审计结果必须可比较；外部输出先进入 candidate 通道。
- 验收：native、LLM、外部能力三路 fixture 的契约级 parity 通过。

## B5 — S4 Real Pilot

- 状态：`planned`，依赖 S3 promotion。
- 目标：完成一个真实论文 idea 的检索、阅读、证据化写作和 claim audit 试点。
- 主要交付：许可明确的 corpus、gold query/reading set、真实材料清单、论文章节草稿、claim audit 报告和限制说明。
- 必须满足：关键 claim 可追溯；无证据内容标记未验证；未执行实验不能写成结果；真实来源和许可边界明确。
- 验收：从 idea 到本地章节草稿的端到端试点可重跑。

## B6 — MVP Manuscript Delivery

- 状态：`planned`，依赖 I3 和 B5。
- 目标：完成最小论文稿件组装、审核、修订和本地交付检查。
- 主要交付：manuscript assembly、引用/证据索引、review feedback、revision artifact、local delivery manifest。
- 必须满足：稿件数字、图表、引用和结果均可追到 artifact/evidence；未知和缺口不被隐藏；原稿不可覆盖；审核不能自批。
- 验收：最小 Evaluation/Related Work/Method 组合稿件通过规则和证据审查。

## 每个 B 任务的交付门槛

代码、测试、fixture、task-local ledger、证据报告和 rollback 必须在同一 PR；前置 Gate 未通过时，后续任务只能标记 `speculative`，不能合并或标记 `accepted`。
