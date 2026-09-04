# Task Package Registry

> 这是全局任务队列和集成索引，不替代任务包中的详细说明。

成员长期任务包：

- [P1-A Runtime Lane](../tasks/P1-A-runtime-lane/LANE-README.md)
- [P1-B Evidence/Domain Lane](../tasks/P1-B-evidence-lane/LANE-README.md)

两个 lane package 只包含成员 A/B 的任务序列；`I0–I4` 和 `MVP-CLOSED` 是负责人主线任务，不进入成员 ZIP。

| Task ID | Phase | Owner lane | Branch | Status | Base | Depends on | Merge after | Next package |
|---|---|---|---|---|---|---|---|---|
| P1-A-RUNTIME-RECOVERY | P1/S1 | runtime | `codex/p1-runtime-recovery` | ready | `8d821c0` | — | — | P1-A2 |
| P1-B-EVIDENCE-PIPELINE | P1/S1 | evidence/domain | `codex/p1-evidence-pipeline` | ready | `8d821c0` | — | P1-A | P1-B2 |
| P1-A2-RUNTIME-HARDENING | P1/S1 | runtime | reserved | ready-next | P1-A | P1-A | — | S2-A |
| P1-B2-EVIDENCE-ADVERSARIAL | P1/S1 | evidence/domain | reserved | ready-next | P1-B | P1-B | — | S2-B |
| S2-A-AUDIT-RUNTIME | S2 | runtime | reserved | waiting-for-gate | P1 promotion | S1 promotion | — | S3-A |
| S2-B-AUDIT-EVIDENCE | S2 | evidence/domain | reserved | waiting-for-gate | P1 promotion | S1 promotion | — | S3-B |
| S3-A-CAPABILITY-ADAPTERS | S3 | runtime | reserved | planned | S2 promotion | S2 promotion | — | S4-A |
| S3-B-READER-WRITER-PORTS | S3 | evidence/domain | reserved | planned | S2 promotion | S2 promotion | — | S4-B |
| S4-A-BENCHMARK-HARNESS | S4 | runtime | reserved | planned | S3 promotion | S3 promotion | — | — |
| S4-B-REAL-PILOT | S4 | evidence/domain | reserved | planned | S3 promotion | S3 promotion | — | — |
| I0-SHARED-CONTRACT-INTEGRATION | MVP | integration/lead | `main` | planned | P1-A + P1-B | P1-A, P1-B | I1 | — |
| I1-PIPELINE-ORCHESTRATION | MVP | integration/lead | `main` | planned | I0 | I0 | I2 | — |
| I2-MAINLINE-E2E-AND-PROMOTION | MVP | integration/lead | `main` | planned | I1 | I1 | I3 | — |
| I3-PROJECT-LEDGER-CLOSURE | MVP | integration/lead | `main` | planned | I2 | I2 | I4 | — |
| I4-MANUSCRIPT-DELIVERY-CHECK | MVP | integration/lead | `main` | planned | I3 + S4-B | I3, S4-B | MVP-CLOSED | — |
| MVP-CLOSED-MINIMAL-E2E | MVP | integration/lead | `main` | waiting-for-gate | A/B + I0-I4 | all MVP rows | — | — |

## 状态定义

- `planned`：只有路线和目标。
- `waiting-for-gate`：可以准备，不可正式实现或合并。
- `ready-next`：当前任务完成后可立即领取。
- `ready`：依赖满足，可以创建 worktree。
- `active`：成员正在实施。
- `submitted` / `reviewing`：已提交，等待负责人审查。
- `integrated`：已合并到主线。
- `accepted`：完成阶段验收并有新鲜证据。
- `speculative`：接口冻结后的隔离预研，不得进入主线。

## MVP 闭环定义

`MVP-CLOSED-MINIMAL-E2E` 不是成员任务包，而是负责人最终验收项。只有以下条件全部满足，才能将其标记为 `accepted`：

1. A 线任务和 B 线任务均已 `accepted`；
2. `I0–I1` 完成共享合同、application 组装和 pipeline 编排；
3. `I2` 在合并后的主线上跑通一条最小 Evaluation Section 场景；
4. Paper Search、Evidence、材料就绪、BenchmarkPlan、SectionDraft、RuleValidation 的状态和证据可追溯；
5. `I3` 完成 Project-to-Act、task ledger、artifact 和验收证据收口；
6. `I4` 完成最小 manuscript/local delivery 检查，未执行结果、unknown 和缺失材料没有被写成已完成事实；
7. 所有 blocking findings、失败路径和回滚边界均有处理记录。

MVP 闭环完成后，仍允许存在生产化、性能、多论文类型、多 venue、完整 UI 和长期知识库等优化 backlog；这些不应阻塞最小端到端 MVP，除非它们违反可信边界。

## 更新规则

1. 成员只更新自己任务的 task-local ledger 和任务包。
2. 负责人更新本表、`.ai-team/TASK.md` 和 Project-to-Act 的阶段状态。
3. 状态变化必须带证据路径或命令。
4. ZIP 是分发载体；解压后的任务包源文件必须进入成员分支并与代码一起交接。
