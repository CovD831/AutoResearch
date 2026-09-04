# P1-B 任务包：Evidence / Writing Pipeline / Readiness

> Package ID：`P1-B-EVIDENCE-PIPELINE`
>
> Worktree：`codex/p1-evidence-pipeline`
>
> Owner：成员 B
>
> Reviewer：成员 A；最终集成：项目负责人

## 1. 任务目标

完成第一条产品价值链：Evidence admission、Evaluation 章节计划、WritingProfile、benchmark 计划、材料缺口检查和章节规则验证。

这不是“重写全部 Writing Agent”，而是把一条可审计的 Evaluation Section Pipeline 做出来。

## 2. 用户价值

用户应当能看到：

- 这一节要回答什么；
- 每个重要 claim 来自哪里；
- 还缺哪些数据、baseline、指标或结果；
- 推荐做什么 benchmark；
- 生成的章节是否符合当前规则；
- 哪些内容仍然是未知或待补充。

## 3. 允许修改的范围

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

如文件不存在，由本任务新增。不要为了方便直接修改共享 `contracts.py`。

## 4. 禁止修改的范围

```text
src/autoresearch/application.py
src/autoresearch/capability.py
src/autoresearch/storage.py
src/autoresearch/contracts.py
tests/test_capability_adapter.py
tests/test_recovery_contract.py
```

若发现必须修改共享文件，先在 handoff 中记录“共享边界变更请求”，由项目负责人在主线处理。

## 5. 冻结的架构约束

- Evidence Module 是 EvidenceItem、ClaimLink、ArtifactLink 的唯一写入者；
- adapter 只能提交 EvidenceCandidate，不直接写正式证据；
- 第一版只支持一种论文类型和一个 Evaluation 章节；
- WritingProfile 必须版本化；
- Benchmark Advisor v1 只输出计划、baseline、指标和材料清单；
- 未执行的实验不能进入论文结果；
- 缺关键材料返回 `blocked`，非关键缺失返回 `needs_material`；
- 章节验证结果为 `verified / revise / blocked`；
- 不新增第二套 Store、总线、scheduler 或 Agent。

## 6. 成员自行决定的 L3 内容

成员自行在 `L3.md` 中确定：

- Evidence admission 的具体数据 shape；
- candidate 去重和 reconcile 策略；
- `SectionPlan`、`SectionDraft`、`WritingProfile` 的字段；
- benchmark 推荐规则和候选排序；
- 材料检查器的规则组织；
- 章节验证器的实现方式；
- 测试 fixture 和报告格式。

这些决定不能违反第 5 节约束。

## 7. Definition of Ready

开始编码前，成员确认：

- 已阅读 R004 L1、R005 L2-B 和本任务包；
- 已确认独占路径和禁止路径；
- 已在 `L3.md` 写出数据 shape、验证规则、阻断语义和 rollback 草案；
- 已定义一个 Evaluation Section 的最小 fixture；
- 已列出至少一个缺关键材料和一个非关键材料场景；
- 已明确 benchmark 只生成计划、不生成结果。

## 8. 验收标准

### Evidence admission

- candidate 有来源、locator、claim 和 provenance；
- 重复 candidate 不产生第二条 EvidenceItem；
- 冲突 candidate 不覆盖已有事实；
- adapter 无法直接改变 Evidence 状态。

### Section planning and generation

- SectionPlan 明确目标、claims、evidence、实验依赖和缺口；
- SectionDraft 只能消费已允许的 claims/evidence/artifacts；
- Writer 不能新增无证据数字或结果；
- unknown、failure、limitation 保留在输出中。

### Readiness and benchmark

- 缺数据集、baseline、指标或结果等关键材料时返回 blocked；
- 非关键缺口返回 needs_material 和行动清单；
- BenchmarkPlan 给出 benchmark、baseline、metrics、required materials 和 risks；
- planned benchmark 不能被写成 observed result。

### Rule validation

- 验证章节结构、WritingProfile、claim-evidence 覆盖和实验结果绑定；
- 失败时返回可定位的问题和 revise/block 结果；
- 验证命令可重跑并产生报告。

## 9. Definition of Done

- L3.md 已完成并在 handoff 中说明；
- 代码、测试和 fixture 只修改本任务范围；
- Evidence、readiness、benchmark、section validation 测试通过；
- 生成一个 Evaluation Section 的可审计 fixture；
- handoff 写明 changed paths、证据、限制、rollback 和集成步骤；
- 成员 A 完成交叉审查；
- 项目负责人确认可以 rebase 到主线。

## 10. 依赖与交付顺序

本任务可与 P1-A 并行设计和实施。最终集成时，使用 A 合并后的 Runtime foundation 重新跑 Evaluation Section Pipeline。

## 11. 失败和停止条件

遇到以下情况立即停止扩大范围，并写入 `HANDOFF.md`：

- 需要直接写 EvidenceItem 的旁路；
- benchmark 建议无法区分计划和结果；
- 材料缺失只能靠生成文字掩盖；
- 章节规则无法产生可解释的失败原因；
- 需要修改 P1-A 独占路径；
- 需要新增全局 Agent、Store 或总线。
