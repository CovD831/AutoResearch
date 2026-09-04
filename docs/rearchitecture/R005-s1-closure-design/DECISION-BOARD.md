# R-005-S1-CLOSURE 决策板

> 状态：P1 共同决策已冻结（2026-09-04）。尚未授权成员直接修改运行时代码；下一步是各任务提交 L3、fixture、acceptance 和 rollback。
>
> 规则：本文件记录待决问题和决策过程；最终架构事实仍由 R005 正文、R-004 程序和代码证据拥有。

## 使用方式

团队成员先在“问题 / 备选方案 / 建议”列补充意见，不直接修改目标架构。负责人收集反馈后，在“负责人决策”列记录取舍，并把正式决定回写到对应 ADR 或 L3 合同。

## 决策总表

| ID | 决策项 | 为什么重要 | 当前建议 | 备选方案 | 负责人决策 | 决策门 | 影响 |
|---|---|---|---|---|---|---|---|
| D-01 | `unknown` 的语义 | 合法零结果和 provider 不确定不能被误认为同一种结果 | **已冻结：**拆成 `completed_empty` / `unknown_outcome` | 保持合并，但明确代价 | 已接受（UD-006） | L3 落地 | receipt、parity、恢复 |
| D-02 | pending recover 行为 | 防止 pending 被静默标记成功 | **已冻结：**默认失败收口；重执行需显式授权 | 允许自动重执行 | 已接受（UD-006） | L3 落地 | 幂等、恢复、数据一致性 |
| D-03 | Evidence 双表示 | legacy `_persist` 已写事实，adapter 又产 candidate，可能双写 | **已冻结方向：**优先 non-persisting search | fallback：reconcile/reference | 已接受（UD-006） | T3 L3 | sole-writer、parity |
| D-04 | invocation record 写入者 | 当前 adapter 经 Store 写幂等记录，与 R-004 L1 表述存在偏差 | **已冻结区分：**Runtime 写 run receipt，Adapter 写 invocation idempotency record；promotion 前同步 R-004 | 将幂等写收回 Runtime | 已接受（UD-006，promotion 前同步） | S1 promotion 前 | L1 一致性 |
| D-05 | parity 比较范围 | 防止测试只证明“两条路径都跑过” | 比较 receipt、paper、EvidenceItem、WikiPage、诊断和幂等行 | 由实现者临时决定 | 已由 R005 B-2 冻结 | implementation package | 验收可信度 |
| D-06 | 首个用户产品切片 | 让技术验证连接到真实用户价值 | **已冻结：**一个论文类型 + Evaluation 章节 + benchmark/材料检查 | 课程设计报告端到端 / 只做 Paper Search | 已接受（UD-006） | implementation package | 产品验收范围 |
| D-07 | WritingProfile 首版范围 | 防止“支持所有论文规则”失控 | **已冻结：**一种论文类型和有限版本化规则 | 同时支持多个 venue/学校模板 | 已接受（UD-006） | Writing Rule L3 | 规则验证复杂度 |
| D-08 | Benchmark Advisor 边界 | 区分推荐和真实实验结果 | **已冻结：**只输出计划、baseline、指标和材料清单 | 同时编排执行 benchmark | 已接受（UD-006） | Experiment L3 | 可信性、执行风险 |
| D-09 | Material Readiness Checker 阻断级别 | 防止材料不足时生成虚假结果 | **已冻结：**关键材料 `blocked`，非关键项 `needs_material` | 只提示不阻断 | 已接受（UD-006） | Readiness L3 | 章节生成安全性 |
| D-10 | 规则来源 | 决定章节验证依据 | **已冻结：**项目配置 + 版本化 WritingProfile | 只依赖 prompt/Skill | 已接受（UD-006） | Writing Rule L3 | 可重复性、审计 |
| D-11 | Paper Search 的位置 | 区分技术先行和产品先行 | **已冻结：**Paper Search 是技术基础，产品验收是 Evaluation Section Pipeline | 直接改做整篇论文 Agent | 已接受（UD-006） | P1 implementation | 交付节奏、范围 |

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

以下条件全部满足后，才允许成员进入运行时代码实现：

- D-01 到 D-04 已按 [UD-006](decisions/UD-006-p1-freeze.json) 冻结；
- L3 contract 已冻结；
- legacy/target fixture 场景已确定；
- acceptance、rollback 和 evidence 输出位置已确定；
- 负责人明确授权成员在独立 worktree 修改运行时代码；
- 每个 worktree 独占路径已登记，且共享集成路径由负责人持有。

成员可以自行编写本任务的 L3 并实施；但在合并到主线前，L3、测试、证据和 rollback 必须随 handoff 提交并由负责人检查。
