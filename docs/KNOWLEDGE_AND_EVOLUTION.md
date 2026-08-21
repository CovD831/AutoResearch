# Wiki+Graph、分级检索、画像与自进化

## 1. 分库

KnowledgePartition 规定五个 Wiki/Graph 分区：

- papers：题录、摘要、ReadingCard、阅读问答。
- experiences：问题、技巧、复现次数和晋级状态。
- knowledge：概念页、创新候选、方法知识。
- profiles：用户明确偏好或推断偏好。
- projects：项目级研究资产。

Evidence、handoff、run 和 governance 使用独立 RecordStore partition，不混入 Wiki 检索结果。

跨分区 GraphEdge 被拒绝，防止一个经验页被伪装成论文证据。跨库综合必须由调用方显式选择多个 partitions，并保留每条命中的原分区。

## 2. Wiki + Graph

WikiPage 保存 title、body、tags、evidence IDs 和 level。GraphEdge 保存 source、relation、target、partition 和 evidence IDs。

基础图关系包括：

- Paper summarized_by ReadingCard。
- 后续可增加 supports、refutes、uses_method、evaluated_on、supersedes。

图端点必须已经存在且属于同一分区。

## 3. 分级检索

当前两级：

- Level 1：分区内词法检索，对 title/tag/body 分别加权。
- Level 2：Level 1 后做同分区一跳图扩展。

require_evidence=true 会过滤没有 evidence IDs 的页面。返回 RetrievalHit 包含 record_id、partition、snippet、score、evidence IDs 和 retrieval_level。

生产路线中的向量、FTS、RRF、rerank 和证据包重排尚未声称实现。

## 4. 用户画像

UserProfileItem 保存 user_id、key、value、confidence、source、confirmed_by_user 和 evidence IDs。未被用户确认的推断置信度最多为 0.6，不能冒充明确偏好或人工证据。

基础 API 可新增和查看画像。生产化还需增加字段级权限、修改、删除、导出和敏感信息禁 embedding 策略。

## 5. 经验沉淀

ExperienceRecord 保存 problem、technique、outcome、grade、recurrence_count、evidence IDs 和 promoted。

晋级同时要求：

- recurrence_count >= 2。
- 等级至少 E2。
- 审核批准。
- 人工批准。

条件不满足返回 PermissionError，不会把单次技巧自动升级为全局规则。

## 6. 自进化

EvolutionService 只能：

1. 生成 proposal。
2. 保存问题、变更、收益、风险和证据。
3. 记录 reviewer/human review 状态。
4. 标记 approved_for_manual_application。

它没有修改源码、GatePolicy、工作流配置或提示词的执行路径。自动回归、canary 与 rollback 在生产阶段补齐前，任何 proposal 都需要人工应用。
