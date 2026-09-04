# P1-A 任务包：Runtime / Capability / Recovery

> Package ID：`P1-A-RUNTIME-RECOVERY`
>
> Worktree：`codex/p1-runtime-recovery`
>
> Owner：成员 A
>
> Reviewer：成员 B；最终集成：项目负责人

## 1. 任务目标

把 Paper Search 的调用边界做可靠，交付可重跑的幂等、receipt、replay、timeout、pending、unknown、restart/recovery 和 legacy/target parity 证据。

这不是“重写所有 Runtime”，而是为 P1 的 Evaluation Section Pipeline 提供可靠的技术基础。

## 2. 用户价值

用户重复提交、网络超时或进程重启后，系统必须能明确告诉用户：

- 这次调用是否真的执行过；
- 结果是完成、确定空结果、失败还是未知；
- 是否可以安全恢复；
- 是否产生了重复副作用。

## 3. 允许修改的范围

```text
src/autoresearch/capability.py
src/autoresearch/storage.py
src/autoresearch/invocation_contracts.py
tests/test_capability_adapter.py
tests/test_recovery_contract.py
tests/fixtures/paper_search/
docs/rearchitecture/worktrees/A-runtime-recovery/
```

如 `invocation_contracts.py` 尚不存在，由本任务新增。不要为了方便直接修改共享 `contracts.py`。

## 4. 禁止修改的范围

```text
src/autoresearch/application.py
src/autoresearch/evidence.py
src/autoresearch/writing_service.py
src/autoresearch/pipeline/
src/autoresearch/contracts.py
tests/test_evidence_admission.py
tests/test_evaluation_pipeline.py
```

若发现必须修改共享文件，先在 handoff 中记录“共享边界变更请求”，由项目负责人在主线处理。

## 5. 冻结的架构约束

- `completed_empty` 与 `unknown_outcome` 必须区分；
- pending 默认显式失败收口，重执行必须是单独授权的操作；
- reserve 必须先于 connector 副作用；
- 精确 replay 不得再次调用 connector；
- 冲突 replay 必须拒绝；
- adapter 不直接写 Evidence 状态或 GateDecision；
- legacy facade 继续可运行；
- 不新增第二套 Store、总线、scheduler 或 Agent。

## 6. 成员自行决定的 L3 内容

成员自行在 `L3.md` 中确定：

- invocation request/result 的具体类型；
- 状态枚举和迁移表的代码表达；
- Store transaction / lock 的实现方式；
- recovery API 的命名和内部结构；
- fixture builder 和 fake connector 的组织方式；
- parity report 的具体生成实现。

这些决定不能违反第 5 节约束。

## 7. Definition of Ready

开始编码前，成员确认：

- 已阅读 R004 L1、R005 L2-A 和本任务包；
- 已确认独占路径和禁止路径；
- 已在 `L3.md` 写出状态、输入输出、持久化、恢复和验收草案；
- 已列出至少一个 legacy fixture 和一个 target fixture；
- 已说明如何模拟 timeout、pending、unknown 和 restart；
- 已明确 rollback 边界。

## 8. 验收标准

### Invocation

- Given 相同 invocation identity 和 request fingerprint，When 重复调用，Then 返回同一业务结果且 connector 只调用一次；
- Given 相同 invocation identity 但 fingerprint 冲突，When 再次调用，Then 明确拒绝；
- Given connector 返回确定的零结果，When finalize，Then 状态为 `completed_empty`；
- Given provider 结果不确定，When finalize，Then 状态为 `unknown_outcome`。

### Recovery

- pending 记录不会被自动标为成功；
- timeout、restart 和 unknown 都有可重跑测试；
- 显式 recover/fail 操作的结果可审计；
- 恢复不会重复写 durable facts 或再次产生未授权 connector 副作用。

### Parity

- legacy 和 target 使用独立 Store；
- 比较 receipt、paper、EvidenceItem、WikiPage、diagnostics 和幂等行；
- 自动生成 ID 按 R005 B-2 规则归一化；
- parity 报告落盘并能用一条命令重跑。

## 9. Definition of Done

- L3.md 已完成并在 handoff 中说明；
- 代码、测试和 fixture 只修改本任务范围；
- 单元、合同、失败和 recovery 测试通过；
- parity report 已生成；
- `ruff`、项目测试和相关 package checks 通过；
- handoff 写明 changed paths、证据、限制、rollback 和集成步骤；
- 成员 B 完成交叉审查；
- 项目负责人确认可以 rebase 到主线。

## 10. 依赖与交付顺序

本任务可与 P1-B 并行设计和实施，但建议先合并本任务的 Runtime/Recovery foundation；P1-B 随后 rebase 到合并后的主线。

## 11. 失败和停止条件

遇到以下情况立即停止扩大范围，并写入 `HANDOFF.md`：

- 无法区分确定空结果和未知结果；
- recovery 只能靠隐式重试；
- parity 只能证明两条路径“都运行过”；
- 需要修改 P1-B 独占路径；
- 需要新增全局状态 owner 或第二套持久化机制。
