# 01 Positioning and Delivery Horizon — R-005-S1-CLOSURE

## User and problem

- User：AutoResearch 维护者（项目负责人）+ 后续 S1 实现者（user/team）。
- 当前耦合造成的问题：S1 的目标边界（capability adapter）**部分已实现但在飞**——`PaperSearchCapabilityAdapter`、幂等 `reserve/finalize`、`EvidenceCandidate` 溯源字段都已存在且 20/20 测试通过，然而程序（R-004）的晋级证据链没有一条可复现的记录把"这些代码已关闭哪些 blocking findings、还缺哪些"讲清楚。结果是：R-003 的 closure review 无法进行（其 stop_rule 要求 restart/timeout/failure/parity 证据），程序触发条件悬空，S2 被无限期挡住。
- 本包解决的是**证据与合同的断层**，不是新架构问题：把"已证什么、未证什么、用什么命令证"冻结成 design，使下一个人只需执行而不是重新考古。

## First deployment boundary

不变（沿 R-002 UD-003）：单进程本地运行时；legacy `AutoResearchApplication` facade 在迁移窗口内继续可运行。本包不改变部署边界。

## 本增量交付（deliver）

1. 当前树 ↔ R-003/R-004 合同的对账（03：哪些 claims 已 established、哪些 conditional/open）。
2. S1 关闭所需的 **legacy/target parity + recovery 证据计划**（04 的开放 claim + 06 的 exact next task）：每个证据一条可重跑命令 + 结果落盘位置 + 归属 finding。
3. 决策记录（05）：repair-first 委托、增量选择、parity fixture 方案。

## 本增量明确推迟（defer）

- S1 证据的**实际生产与执行**（parity fixture、restart/timeout/unknown-outcome 测试）——需要实现授权，归下一个 implementation 包。
- S2 Audit Module / S3 lineage / S4 plugin（R-004 05-migration 的阶段表为 canonical owner）。
- 旧包 manifest 的 checker 结构修复（backlog，见 06）。

## Advancement trigger（observable）

`docs/rearchitecture/R003-paper-search-adapter` 的晋级证据存在且可复现：legacy/target parity 报告 + restart/timeout/unknown-outcome 恢复证据由冻结命令产出并落盘，R-003 ledger `R003-AR-005` 与 R-004 ledger `AR-OLD-002/004/005/006` 全部 `resolved`。届时 S1 可 promotion，S2 实现开工门解锁（R-004 stop_rule）。

## Stop rule

- parity 报告显示 legacy 与 target 在 receipt/持久化事实/checkpoint 语义不等价 → 停止，保留 legacy facade，修订 04 的 L2 合同而非强行晋级。
- 恢复证据显示 pending/unknown 调用可被静默标记成功 → 停止并按 finding 重新打开 R003-AR-002。
- 本包设计本身被 review 判 blocked 且无法在 design-only 范围内修复 → 停止并保留状态呈报用户（不自行授权实现）。
