# AutoResearch 实施路线与异步推进规则

> 状态：team operating draft
>
> 权威关系：R004/R005 与 UD-006/UD-007 冻结架构和阶段 Gate；本文定义任务如何提前准备、异步实施和进入主线。

## 1. 目标

负责人维护全局路线、集成队列和阶段 Gate；成员在独立 worktree 中持续开发，不等待负责人完成上一项合并后才拿到下一项任务。

```text
全局路线提前定义
        ↓
任务包进入队列
        ↓
成员 active / continuing-next
        ↓
负责人异步审查、合并
        ↓
阶段 Gate 控制 promotion
        ↓
下一阶段立即激活
```

## 2. 阶段队列

| 阶段 | 目标 | 当前状态 | 可提前准备 | 正式实施/合并条件 |
|---|---|---|---|---|
| S0 | 基线、依赖盘点和协作基建 | integrated | — | 已完成 |
| P1/S1 | Evaluation Section Pipeline 与 Runtime/Recovery | active | — | 当前阶段 |
| S2 | Audit Module 与 Evidence reconciliation | waiting-for-gate | L3、fixture、CLI 合同、测试计划 | S1 promotion |
| S3 | Reader/Writer Domain Ports 与外部能力 | planned | port 草案、LLM/MCP fixture、风险清单 | S2 promotion |
| S4 | 真实论文试点、可信 benchmark 与本地交付 | planned | 材料清单、标注协议、benchmark harness 设计 | S3 promotion |

负责人集成线不放入成员 A/B ZIP，但属于全局注册表和 MVP 必经路径：

```text
I0 Shared Contract Integration
→ I1 Pipeline Orchestration
→ I2 Mainline E2E and Promotion
→ I3 Project Ledger Closure
→ I4 Manuscript Delivery Check
→ MVP-CLOSED
```

只有 A/B 两条成员线和 `I0–I4` 全部 `accepted`，才能声明最小端到端 MVP 闭环；S2–S4 的后续优化仍可在 MVP 之后继续。

`waiting-for-gate` 允许阅读、设计、fixture 和接口评审；如需提前编码，必须标记为 `speculative`，隔离在独立分支，不得合并或宣称完成。

## 3. 两条成员工作线

### Runtime 线（成员 A）

```text
P1-A Runtime/Recovery
→ P1-A2 Fault Injection/Parity Automation
→ S2-A Audit CLI/Runtime
→ S3-A Capability Registry/External Adapter
→ S4-A Benchmark Harness/Runtime
```

### Evidence/Domain 线（成员 B）

```text
P1-B Evidence/Evaluation Pipeline
→ P1-B2 Adversarial Evidence/Rule Fixtures
→ S2-B Audit Core/Evidence Reconciliation
→ S3-B Reader/Writer Domain Ports
→ S4-B Real Pilot/Claim Audit
```

### 负责人集成线

```text
I0 Shared Contract Integration
→ I1 Pipeline Orchestration
→ I2 Mainline E2E and Promotion
→ I3 Project Ledger Closure
→ I4 Manuscript Delivery Check
```

负责人集成线不作为成员任务包发放；它记录在全局注册表中，由项目负责人在主线完成。

每位成员最多同时持有：一个 `active` 任务、一个 `ready-next` 任务和一个 `waiting-for-gate` 任务。

## 4. 任务生命周期

```text
planned → ready → active → submitted → reviewing → integrated → accepted
                         ↘ speculative
```

允许的辅助状态：`changes-requested`、`blocked`、`superseded`。

任务的开发状态和集成状态分开记录。例如成员可以处于 `active-next`，而前一个任务仍处于 `reviewing`。

## 5. 堆叠分支规则

- 每个任务包有独立分支，分支名使用 `codex/<task-id>`。
- 同一成员的后续任务可以从前一任务分支堆叠，提交后立即继续开发。
- 跨成员任务只能依赖已冻结的 L2 合同、fixture 或 mock；不得依赖未合并的私有实现。
- 前一任务合并后，后续分支必须 rebase 到最新 `origin/main` 再请求集成。
- 每个 PR 都必须能单独审查、测试和回滚。

## 6. Gate 分类

### Ready Gate

开始编码前确认：任务包、owner、base_ref、独占路径、禁止路径、依赖、交付物和验收命令齐全。

### Submit Gate

提交前确认：L3、代码、测试、fixture、PROGRESS、HANDOFF 和真实验证证据已更新。

### Merge Gate

负责人合并前确认：

- changed paths 未越界；
- required checks 通过；
- acceptance 场景有证据；
- 无秘密、原始敏感材料或生成数据库；
- 无第二 Store、总线、scheduler 或隐藏 Agent；
- 机器人报告、负责人审查和 rollback 说明完成。

### Promotion Gate

阶段晋级前确认：前置阶段所有 blocking findings 已关闭；主线端到端场景通过；证据报告可重跑；后续阶段依赖的合同已经稳定。

## 7. 负责人集成节奏

负责人不负责逐条催促成员，而是维护 `TASK-PACKAGE-REGISTRY.md` 的集成队列：

1. 按 `merge_after` 和依赖顺序审查 PR；
2. 合并通过 Merge Gate 的任务；
3. 发现问题时退回 `changes-requested`，保留证据和原因；
4. 阶段条件满足后执行 Promotion Gate；
5. 将下一个 `waiting-for-gate` 任务改为 `ready`。

## 8. 不允许的捷径

- 不因为成员已经写完代码就跳过 Promotion Gate；
- 不把 speculative 分支当作主线能力；
- 不在多个 worktree 同时修改同一共享合同；
- 不用 ZIP 代替 Git 中的任务状态和交接记录；
- 不以代码行数或 AI 生成速度代替验收证据。
