# 工作流、状态机与交接

## 1. 生命周期

正常主线为：

    INTAKE
      -> SCOPED
      -> LITERATURE_SEARCHED
      -> LITERATURE_READ
      -> INNOVATION_REVIEWED
      -> EXECUTION_PLANNED
      -> DRAFT_WRITTEN
      -> DRAFT_REVIEWED
      -> RELEASE_PENDING
      -> RELEASED

终止或暂停状态：

- WAITING_EVIDENCE：论文、实验、独立来源或闭环不足。
- WAITING_HUMAN：概念状态；LangGraph 实际 interrupt checkpoint 保留在 RELEASE_PENDING。
- REJECTED：审核或人工明确拒绝。
- FAILED：系统错误，不能当作证据不足。
- RunStatus.BLOCKED：可通过补证据并启动新 run 重新评估。
- RunStatus.INTERRUPTED：必须用同一 thread_id 执行 resume。

## 2. 关键 Gate

| Gate | 风险 | 通过条件 | 失败动作 |
|---|---|---|---|
| 文献进入创新规划 | L2 | 至少 30 分、至少一个独立来源 | WAITING_EVIDENCE |
| 稿件证据完整 | L3 | 至少 75 分、两个独立来源、无 unresolved gap | WAITING_EVIDENCE |
| 外部发布状态 | L4 | L3 基础成立、至少 85 分、H3 人工批准 | interrupt、DENY 或 WAITING_EVIDENCE |

内部草稿允许保留缺口，但不能由 DRAFT_WRITTEN 升级到 DRAFT_REVIEWED。这样既能辅助写作，也不会把计划或推测变成论文结果。

## 3. HandoffEnvelope

每次跨 Agent 传递必须包含：

- project_id、run_id、from_agent、to_agent。
- objective 和 expected_output。
- 最多 20 个 ArtifactRef、最多 100 个 evidence IDs。
- 最多 20 条 constraints。
- 最多 2000 字符 bounded_context。

接收 Agent 校验 receiver、project 和 run。发送者与接收者不能相同。全文、完整聊天、隐藏提示词和密钥不属于 handoff。

## 4. Checkpoint 与恢复

- 初次运行用 run_id 作为 LangGraph thread_id。
- 每个 super-step 由 SqliteSaver 持久化。
- release_gate 调用 interrupt，payload 必须可 JSON 序列化。
- resume 接收 approval、reviewer、note。
- interrupt 前不执行非幂等写操作；人工证据 ID 对同一 run 保持稳定。
- 普通证据阻断运行保持不可变审计历史；补证据后创建新 run，避免静默重写旧结论。

## 5. 工作流版本

当前固化工作流为 autoresearch-default-v1，配置位于 configs/workflows/default.yaml。运行状态携带 schema_version。后续修改节点名称前必须提供 checkpoint 兼容/迁移方案，因为暂停线程依赖原节点名。
