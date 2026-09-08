# R-005-S1-CLOSURE 团队阅读指南

> 用途：让第一次接触重构包的成员在 10 分钟内理解背景、目标、边界和待决问题。
>
> 这是一份解释入口，不是新的架构权威。架构事实以 R005 正文、R-004 程序和代码证据为准。

## 先看结论

我们要重构的是**整个 AutoResearch 项目**。R-004-TRUST-PROGRAM 是全项目总计划，负责目标架构和 S1–S4 路线；R005 只是其中第一个可实施的真实纵向切片：S1（Paper Search capability）进入实施前的收口设计。

因此，R005 里大量出现 paper search，不代表项目只做论文搜集，而是因为重构不能一开始同时改完整个系统，必须先用一个真实场景验证边界、契约、幂等和恢复。

当前结论：

- 目标架构方向成立：薄 Runtime、Capability、Evidence、Policy、Store 分工。
- S1 的部分代码已经存在，但 adapter 还没有接入真实 run 路径。
- 当前不能宣布 S1 完成，因为 legacy 路径和 target 路径还没有 parity 证据。
- 当前不能启动 S2 Audit Module。
- 下一步应先完成一次 implementation package，而不是继续增加设计包。

## 为什么要重构

现在的系统里，一个较大的 facade 同时承担流程编排、能力调用、持久化和部分证据处理。这样会带来三个问题：

1. 重复调用可能产生重复副作用。
2. 出错后难以判断是哪一层负责恢复。
3. 证据、判断和存储的责任边界不够清楚。

重构的目标不是增加更多抽象，而是让每个责任只有一个明确的主人。

## 重构后的系统怎么分工

```text
CLI / API / MCP
       ↓
Thin Runtime：安排顺序、授权、保存调用收据
       ↓
Capability：接入搜索等外部能力，执行幂等控制
       ↓
Domain Services：处理搜索、阅读、写作等领域动作
       ↓
Evidence Module：保存可追溯事实
Policy / Gate：按规则做判断
       ↓
SQLite Store：可靠持久化
```

### Thin Runtime

像导演，负责“先做什么、后做什么”。它不应该替 Evidence 写证据，也不应该替 Policy 做结论。

### Capability

像工具适配器，把 Native、MCP、Skill 等能力接入系统。它负责调用边界、幂等键和显式失败/未知结果。

### Evidence Module

像档案员，负责保存论文、来源、定位信息和其他可追溯事实。Evidence 状态不能由 adapter 或 Agent 直接改写。

### Policy / Gate

像裁判，只按照已经定义的规则判断，不负责制造事实。

### Store

像仓库，保存幂等记录、领域事实和恢复所需状态。

### Legacy Facade

迁移期间继续保留，确保旧入口可运行。只有在 target 与 legacy 的行为和持久化事实证明等价后，才讨论收缩旧路径。

## S1 这次到底要做什么

只做一条真实纵向切片：Paper Search。

它需要证明：

- 相同输入下，legacy 路径和 target adapter 路径得到等价结果。
- 重复调用不会再次触发 connector 副作用。
- 冲突 replay 会被拒绝。
- timeout、pending、unknown outcome 能被明确记录和恢复。
- Evidence 不会因为 legacy `_persist` 和 adapter candidate 同时存在而被重复写入。

## 目前还没有决定的事情

这些问题必须在正式实施前回答，但现在团队可以先提出意见：

1. `unknown` 是否拆成 `completed_empty` 和 `unknown_outcome`。
2. pending invocation 的 recover 是标记失败，还是允许重执行。
3. Evidence 双表示采用 non-persisting search，还是采用 reconcile/deduplicate。
4. capability invocation idempotency record 的最终写入者如何与 R-004 的 L1 规则对齐。

## 成功是什么样

成功不是“代码文件变少”，而是以下证据全部可重跑：

- parity report；
- recovery/unknown-outcome 测试；
- sole-writer 证明；
- idempotency 和 replay 证明；
- R-003/R-004 对应 review findings 全部关闭。

## 失败时怎么办

如果出现以下任一情况，就保留 legacy facade，不强行晋级：

- legacy 和 target 的 receipt 或 durable facts 不等价；
- unknown/pending 被静默标记为成功；
- Evidence 出现双写或多个事实主人；
- 恢复行为无法解释或无法重放。

## 团队反馈格式

请不要只写“感觉有风险”，而是尽量使用下面格式：

```text
位置：R005 的哪一节 / 哪个边界
问题：具体哪里不清楚或可能出错
证据：代码、测试或文档路径
建议：你建议保留、修改或删除什么
影响：会影响哪个门禁或哪个实现任务
```

## 详细材料入口

- 管理层摘要：[EXECUTIVE-SUMMARY.md](EXECUTIVE-SUMMARY.md)
- 目标架构：[02-l1-target.md](02-l1-target.md)
- 当前到目标映射：[03-current-to-target-map.md](03-current-to-target-map.md)
- L2 边界契约：[04-l2-contracts.md](04-l2-contracts.md)
- 下一步与门禁：[06-handoff.md](06-handoff.md)
- 决策板：[DECISION-BOARD.md](DECISION-BOARD.md)
