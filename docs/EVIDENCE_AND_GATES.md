# 证据与门禁规范

## 1. EvidenceItem

基础字段包括 evidence_id、project_id、evidence_type、grade、title、claim、source_uri、source_id、locator、checksum、independent_source、valid、supersedes、created_at 和 metadata。

EvidenceItem 新增后不可原地改写。失效通过 evidence_status 和 evidence.invalidated 审计事件表达。Gate 只消费同项目且 valid=true 的证据。

## 2. 基础等级

| 等级 | 权重 | 典型用途 |
|---|---:|---|
| E0 | 5 | 未验证意图、系统提示或弱经验 |
| E1 | 15 | 题录、摘要级论文记录、单次观察 |
| E2 | 30 | 有定位的全文抽取、复核材料 |
| E3 | 45 | 强实验记录、独立复核结果 |
| H3 | 50 | 具名人工高风险批准 |

EvidenceType 独立记录 human、paper、experiment、experience、knowledge、system。基础版采用“类型 + 通用等级”的统一模型；计划书中的 H/P/X/R 更细家族策略是后续生产化扩展，不应与当前实现混称。

## 3. 风险门禁

| 风险 | 最低分 | 独立来源 | 工作闭环 | 人工 |
|---|---:|---:|---|---|
| L0 | 0 | 0 | 否 | 否 |
| L1 | 15 | 1 | 否 | 否 |
| L2 | 30 | 1 | 否 | 否 |
| L3 | 75 | 2 | 是 | 否 |
| L4 | 85 | 2 | 是 | 必须 |

同一个 independent_source 只计最强一条证据，不能用重复摘要和阅读卡刷分。explicitly_rejected 优先返回 DENY。L4 缺人工批准返回 INTERRUPT。其他不足返回 REVISE。

## 4. Fail-closed 规则

以下任一成立均不能进入下一阶段：

- 无真实论文记录。
- 交接 receiver、project 或 run 不匹配。
- 证据分或独立来源不足。
- 工作包或结果 lineage 未闭环。
- 稿件存在 unresolved_gaps。
- 审核或人工明确拒绝。
- L4 没有具名人工批准。
- 证据已失效或属于其他项目。

LLM 的文本、置信度或自我评价不参与最终 GatePolicy 覆盖。

## 5. 审计

每次证据新增/失效、Gate 计算、handoff、run checkpoint、稿件修订和人工恢复都写 audit_events。API 可按 project_id 读取时间线。生产化前仍需补充签名、保留期、访问控制和不可篡改存储。
