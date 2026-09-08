# 任务包拆分规则：AB Lane 与包内 PR

> 本文整理 AutoResearch 重构期间 A/B 两个系列任务包的拆分依据，以及任务包内部 PR 的拆分与编排规则。
> 原始出处：`docs/rearchitecture/P1-WORKTREE-TASK-PLAN.md`、`docs/rearchitecture/TASK-PACKAGE-REGISTRY.md`、`docs/rearchitecture/IMPLEMENTATION-ROADMAP.md`、`docs/tasks/P1-*-lane/`。

## 1. 总原则

- **Lane 是长期责任线，不是一次性任务包。** A/B 的划分贯穿 P1 → S2 → S3 → S4 全阶段，成员领取的是一条线的任务序列，不是孤立的一包活。
- **按代码的独占文件边界切，不按功能模块数量或人天切。** 每条 lane 有明确的 exclusive paths、禁改清单和自己的合同文件，保证两个 worktree 可以并行开发、互不踩线。
- **集成收口永远在主线负责人。** 成员只交 L3 + 测试 + 证据的 handoff 包；`application.py`、pipeline 编排、冲突裁决、Promotion Gate 均归负责人。

## 2. AB 包拆分规则（lane 级）

### 2.1 两条线的定位

| | P1-A Runtime Lane | P1-B Evidence/Domain Lane |
|---|---|---|
| 切分依据 | **基础设施可靠性**：调用层的确定性 | **业务价值链**：从证据到章节的领域流水线 |
| 目标 | Paper Search 的可靠调用边界：幂等、receipt、replay、timeout、pending、unknown、restart/recovery、legacy/target parity | 第一条产品价值链：Evidence admission → Evaluation 章节计划 → WritingProfile → benchmark 计划 → 材料缺口检查 → 章节规则验证 |
| 独占代码 | `capability.py`、`storage.py`、`invocation_contracts.py` | `evidence.py`、`writing_service.py`、`pipeline_contracts.py`、`readiness.py`、`benchmark_advisor.py`、`section_validator.py` |
| 独占测试 | `test_capability_adapter.py`、`test_recovery_contract.py` | `test_evidence_admission.py`、`test_evaluation_pipeline.py`、`test_material_readiness.py`、`test_section_validation.py` |
| 全阶段延伸 | A3 Audit Runtime、A4 Capability Adapters、A5 Benchmark Runtime | B3 Audit Evidence、B4 Reader/Writer Ports、B5 Real Pilot、B6 Manuscript Delivery |

### 2.2 五条硬规则

1. **文件级互斥**：每条 lane 有 exclusive paths + 禁改清单；对方独占路径、`application.py`、共享 `contracts.py`、项目级账本（`.project-to-act/`、`.ai-team/TASK.md`）都在禁改名单内。
2. **合同分离**：共享 `contracts.py` 双方都不能直接改——A 使用自己的 `invocation_contracts.py`，B 使用 `pipeline_contracts.py`，从源头避免合同冲突。
3. **集成收口在主线**：`application.py`、pipeline orchestrator、stage 状态、worktree 合并、Promotion Gate 全部由负责人独占；成员不改共享文件，需要改时在 handoff 提出边界变更申请。
4. **合并有序**：从同一冻结基线（`8d821c0`）创建 worktree；A 先合并 Runtime/Recovery foundation，B rebase 到 A 合并后的主线，最后负责人完成端到端集成。
5. **lane 贯穿全阶段**：A 线持续负责 runtime/capability/benchmark harness，B 线持续负责 evidence/domain/reader-writer/真实试点；集成任务 `I0–I4` 与最终验收 `MVP-CLOSED` 属负责人主线，不进入成员任务包。

### 2.3 分支与 worktree 约定

```text
冻结基线 8d821c0
      ├── worktree-A  ../AutoResearch-p1-a   codex/p1-runtime-recovery
      └── worktree-B  ../AutoResearch-p1-b   codex/p1-evidence-pipeline
```

## 3. 包内 PR 拆分规则

### 3.1 一个任务 = 一个 PR

- 每条 lane 是一个任务队列（`lane-manifest.json` 的 `task_queue`），队列中每个任务单独开 PR、单独分支、单独验收。
- 任务即最小 PR 粒度，**任务内部不再拆 PR**。
- 拆分依据是**验收目标闭环**：每个任务有独立的目标、主要交付、必须满足、禁止项和验收条款，恰好构成一个可独立审查的 PR。
- lane README 明确「它代表一条责任线，不是一个巨大 PR」——大颗粒被拆成任务序列，而不是塞进一个巨型 PR。

### 3.2 单 PR 的原子性约束（交付门槛）

代码、测试、fixture、task-local ledger、证据报告和 rollback 说明**必须在同一 PR**。PR 不是只交代码——L3、测试、fixture、账本、证据、回滚是一个不可分的验收单元，缺一项即不完整。

A 线队列：A1 Runtime Recovery → A2 Runtime Hardening → A3 S2 Audit Runtime → A4 S3 Capability Adapters → A5 S4 Benchmark Runtime

B 线队列：B1 Evidence Pipeline → B2 Evidence Adversarial → B3 S2 Audit Evidence → B4 S3 Reader/Writer Ports → B5 S4 Real Pilot → B6 MVP Manuscript Delivery

### 3.3 PR 之间的编排（stacked PR）

- **异步推进**：成员完成当前 PR 提交后，无需等待合并，可立即在同一分支上堆叠下一个 `ready-next` 任务（如 A2 堆在 A1 分支上）。
- **rebase 纪律**：前置 PR 合并后，后续 PR 必须 rebase 到最新 `main`，并通过自己的 task-local ledger 检查。
- **Gate 控制**：跨阶段任务（S2/S3/S4）在前置 Promotion Gate 未通过时只能标记 `speculative` 或 `waiting-for-gate`，不允许正式实现或合并。
- **合并顺序**：A 先合 foundation → B rebase 后合 → 负责人做 `application.py` / pipeline 集成 → 重跑完整 Evaluation Section Pipeline。

### 3.4 审查流与验收回写

- GitHub 机器人先做自动检查 → 负责人做最终审查和验收；成员只负责开发、测试和 handoff。
- 验收发现的问题以 **Owner review 补充条款**回写进下一个任务的规格（例：2026-09-07 深度审查的 F-1/F-2/F-3 写入 A2 规格，F1/F2/F3 写入 B2 规格），作为该 PR 的 Gate 前置条件。
- 状态机：`planned → waiting-for-gate → ready-next → ready → active → submitted/reviewing → integrated → accepted`；另有 `speculative`（冻结后的隔离预研，不进主线）。

## 4. 一句话总结

**Lane 按独占文件边界切（基础设施可靠性 vs 业务价值链），任务队列是 PR 序列，每个任务一个原子 PR，堆叠推进、Gate 控合并、集成收口在主线。**
