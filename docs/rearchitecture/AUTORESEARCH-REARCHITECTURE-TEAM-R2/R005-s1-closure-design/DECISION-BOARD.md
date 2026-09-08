# R-005-S1-CLOSURE 决策板

> 状态：团队反馈阶段（2026-09-04）。尚未进入实现硬门槛。
>
> 规则：本文件记录待决问题和决策过程；最终架构事实仍由 R005 正文、R-004 程序和代码证据拥有。

## 使用方式

团队成员先在“问题 / 备选方案 / 建议”列补充意见，不直接修改目标架构。负责人收集反馈后，在“负责人决策”列记录取舍，并把正式决定回写到对应 ADR 或 L3 合同。

## 决策总表

| ID | 决策项 | 为什么重要 | 当前建议 | 备选方案 | 负责人决策 | 决策门 | 影响 |
|---|---|---|---|---|---|---|---|
| D-01 | `unknown` 的语义 | 合法零结果和 provider 不确定不能被误认为同一种结果 | 拆成 `completed_empty` / `unknown_outcome` | 保持合并，但明确代价 | 待负责人决定 | L3 冻结前 | receipt、parity、恢复 |
| D-02 | pending recover 行为 | 防止 pending 被静默标记成功 | 默认失败收口，除非能证明重执行安全 | 允许显式重执行 | 待负责人决定 | L3 冻结前 | 幂等、恢复、数据一致性 |
| D-03 | Evidence 双表示 | legacy `_persist` 已写事实，adapter 又产 candidate，可能双写 | 优先评估 non-persisting search | 保留 `_persist`，candidate 做 reconcile/reference | 待负责人决定 | T3 开始前 | sole-writer、parity |
| D-04 | invocation record 写入者 | 当前 adapter 经 Store 写幂等记录，与 R-004 L1 表述存在偏差 | 在 R-004 L1 中明确 capability invocation record 的归属 | 将幂等写收回 Runtime | 待 R-004 owner/负责人决定 | S1 promotion 前 | L1 一致性 |
| D-05 | parity 比较范围 | 防止测试只证明“两条路径都跑过” | 比较 receipt、paper、EvidenceItem、WikiPage、诊断和幂等行 | 由实现者临时决定 | 已由 R005 B-2 冻结 | implementation package | 验收可信度 |

## 还需要团队确认的非架构问题

| ID | 问题 | 需要谁回答 | 截止时点 | 记录位置 |
|---|---|---|---|---|
| Q-01 | 当前 run 路径接入 adapter 的最小位置是什么？ | Runtime / integration | 分配 T4 前 | L3 contract |
| Q-02 | 哪些现有测试可以复用为 legacy fixture？ | 测试负责人 | T1 开始前 | implementation package |
| Q-03 | `_persist` 写入的 WikiPage 在 parity 中如何稳定比较？ | Evidence / 测试 | T1 开始前 | B-2 / acceptance |
| Q-04 | 失败恢复是否需要新增显式 API，还是复用 Store 操作？ | Runtime / Store | T2 开始前 | L3 contract / ADR |

## 负责人决策记录模板

每个决策完成后，补充一条：

```text
决策 ID：D-__
日期：YYYY-MM-DD
决策人：
决定：
拒绝的方案：
理由：
证据：
回写文件：
反转条件：
```

## 进入实施硬门槛的条件

以下条件全部满足后，才创建 implementation package 并正式分配代码任务：

- D-01 到 D-04 均有明确负责人决策；
- L3 contract 已冻结；
- legacy/target fixture 场景已确定；
- acceptance、rollback 和 evidence 输出位置已确定；
- 负责人明确授权成员修改运行时代码。

在此之前，团队可以继续提出意见，但不应把讨论中的方案当成已批准实现要求。
