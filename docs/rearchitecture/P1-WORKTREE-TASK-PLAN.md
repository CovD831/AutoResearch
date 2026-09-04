# P1 Worktree 实施任务分配

> 状态：已授权分工。两位成员各自在独立 worktree 自行编写 L3 并实施；项目负责人负责主线集成和最终验收。
>
> 基线：R005 `r2-consumption+p1-freeze-2026-09-04`。

## 异步推进补充

任务包不再按“提交后才临时分发下一包”运行。全局队列见 [IMPLEMENTATION-ROADMAP.md](IMPLEMENTATION-ROADMAP.md) 和 [TASK-PACKAGE-REGISTRY.md](TASK-PACKAGE-REGISTRY.md)。成员完成当前任务并提交 PR 后，可以立即领取同一工作线的 `ready-next` 任务；负责人异步进行审查和合并。

- 当前 PR：`active` / `submitted` / `reviewing`；
- 下一 PR：`ready-next`，可从当前分支堆叠；
- 跨阶段任务：前置 Gate 未通过时只能 `waiting-for-gate` 或 `speculative`；
- 合并前：每个任务必须 rebase 到最新 `main`，并通过自己的 task-local ledger 检查；
- 阶段晋级：仍由负责人执行 Promotion Gate，不因成员提前完成 speculative 代码而跳过。

正式任务包：

- [P1-A Runtime / Recovery](../tasks/P1-A-runtime-recovery/TASK-PACKAGE.md)
- [P1-B Evidence / Writing Pipeline](../tasks/P1-B-evidence-pipeline/TASK-PACKAGE.md)

## 共同目标

交付一条可验收链路：

```text
Paper Search → Evidence admission → Evaluation Section Plan
→ Benchmark / Material Readiness → Section Draft → Rule Validation
```

## 主线负责人：项目负责人

独占负责：

- `src/autoresearch/application.py` 最终集成；
- pipeline orchestrator、stage 状态和主流程；
- `src/autoresearch/contracts.py` 的公共导出面；
- Project-to-Act、`.ai-team/TASK.md` 和重构记录；
- worktree 合并、冲突裁决、端到端验收。

不要求预先替成员写完 L3；成员在 handoff 时提交 L3、测试和证据，由负责人检查是否符合 R005/UD-006。

## Worktree A：Runtime / Capability / Recovery

### 目标

完成 Paper Search 的可靠调用边界：幂等、receipt、replay、timeout、pending、unknown、restart/recovery、legacy/target parity。

### 独占路径

```text
src/autoresearch/capability.py
src/autoresearch/storage.py
src/autoresearch/invocation_contracts.py
tests/test_capability_adapter.py
tests/test_recovery_contract.py
tests/fixtures/paper_search/
docs/rearchitecture/worktrees/A-runtime-recovery/
```

### 禁止修改

```text
src/autoresearch/application.py
src/autoresearch/evidence.py
src/autoresearch/writing_service.py
src/autoresearch/pipeline/
src/autoresearch/contracts.py
```

### L3 和验收要求

- 定义 `completed_empty` / `unknown_outcome`；
- 定义 pending → explicit failure；
- reserve 先于外部副作用；
- 精确 replay 不重复调用 connector；
- 冲突 replay 拒绝；
- parity fixture 和 oracle 可重跑；
- handoff 包含 L3、测试、证据、rollback 和集成说明。

## Worktree B：Evidence / Writing Pipeline / Readiness

### 目标

完成第一条产品价值链：Evidence admission、Evaluation 章节计划、WritingProfile、benchmark 计划、材料缺口检查和章节规则验证。

### 独占路径

```text
src/autoresearch/evidence.py
src/autoresearch/writing_service.py
src/autoresearch/pipeline_contracts.py
src/autoresearch/readiness.py
src/autoresearch/benchmark_advisor.py
src/autoresearch/section_validator.py
tests/test_evidence_admission.py
tests/test_evaluation_pipeline.py
tests/test_material_readiness.py
tests/test_section_validation.py
docs/rearchitecture/worktrees/B-evidence-pipeline/
```

### 禁止修改

```text
src/autoresearch/application.py
src/autoresearch/capability.py
src/autoresearch/storage.py
src/autoresearch/contracts.py
tests/test_capability_adapter.py
tests/test_recovery_contract.py
```

### L3 和验收要求

- 定义 EvidenceCandidate → Evidence admission；
- 处理 legacy `_persist` 与 candidate 双表示；
- 定义 `SectionPlan`、`SectionDraft`、`WritingProfile`；
- Benchmark Advisor 只输出计划、baseline、指标和材料清单；
- 关键材料缺失返回 `blocked`，非关键缺失返回 `needs_material`；
- 章节规则结果为 `verified / revise / blocked`；
- 关键 claim 无 evidence 不能 verified；
- handoff 包含 L3、测试、证据、rollback 和集成说明。

## 共享边界规则

1. 不修改对方独占路径。
2. 不直接修改 `application.py`，统一由负责人集成。
3. 不直接修改共享 `contracts.py`；A 使用 `invocation_contracts.py`，B 使用 `pipeline_contracts.py`。
4. 不创建第二套 Store、总线、scheduler 或 Agent。
5. 不改变 UD-006 语义而不登记新的决策。
6. 必须修改共享文件时，先在 handoff 提出共享边界变更，由负责人在主线处理。

## Worktree 创建和合并

```text
冻结基线 commit
      ├── worktree-A/runtime-recovery
      └── worktree-B/evidence-pipeline
```

建议分支名：

```text
codex/p1-runtime-recovery
codex/p1-evidence-pipeline
```

合并顺序：

1. 两位成员从同一冻结基线创建 worktree。
2. A、B 并行编写 L3 和实施自己的边界。
3. A 先合并 Runtime/Recovery foundation。
4. B rebase 到 A 合并后的主线。
5. 负责人完成 `application.py` 和 pipeline 集成。
6. 重新跑完整 Evaluation Section Pipeline。
7. GitHub 机器人先做自动检查；负责人做最终审查和验收。成员只负责开发、测试和交接。

## 主线完成标准

- A 的 parity/recovery evidence 通过；
- B 的 Evidence、readiness、benchmark plan、section validation 通过；
- 主线跑通一个 Evaluation Section 场景；
- 重要 claim 都有 evidence 或明确 unresolved 标记；
- 结果、图表和数字可追到真实 artifact；
- failed、unknown、needs_material、blocked 都有测试；
- R003/R005 findings 有新的可重跑证据；
- 负责人完成 handoff 和下一阶段建议。
