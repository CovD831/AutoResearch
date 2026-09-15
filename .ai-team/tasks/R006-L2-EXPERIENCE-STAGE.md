# R006 L2 Experience Maturity Stage

- ID: `R006-L2-EXPERIENCE-STAGE`
- Title: `Experience maturity ladder (X0->X4) + the record()/append-only cross-lane fix`
- Status: `active`
- Status note: `contracts.py` +11 行 validator（P2C 相对 P1P 的唯一净增）；`evolution_service.py` 新增 `advance_stage` / `StageEvidence` 并修复 `record()` 的 revision 递增。**本分支是 stacked（基 = `owner/r006-l1-writer`），不能独立于 L-06 单独合并。**
- Owner: `owner`
- Next owner: `member A`（M12 承接）

## Goal

把经验成熟度从「一个 `promoted` 布尔」升格为**可机械校验的逐级阶梯**（X0_RAW → X1_ATTRIBUTED → X2_REPRODUCED → X3_CROSS_PROJECT → X4_POLICY，§11.3/§11.5/§11.11），并修复它叠到 append-only wiki 写入者（L-06 / C1 / §11.9）之后暴露的**跨线硬冲突**。

## Cross-lane conflict fixed (R-007 L2 §10.5)

L-07 的 `ExperienceService.record()` 构造 `WikiPage(...)` 时**未传 `revision`**（默认 1），而 `page_id` 固定 = `experience.experience_id`。L-06 的 `add_page` 是 append-only（`revision` 必须 > 当前 max），因此**同一经验第二次写入直接 `ValueError`**。

```
第 1 次 record OK
第 2 次 record 失败 -> ValueError: revision 1 must be > current max 1
                      for page e1 (append-only: revisions are never overwritten)
```

这不是边缘场景：`experience_sink.py:547` 明确会重复调 `record()`，`:755` 用
`recurrence_count=max(1, recurrence)` —— 去重合并时重录同一条经验是 A6 的核心路径。

**修复**：`record()` 从 head 派生 `revision`（`get_page(page_id).revision + 1`，首次为 1），
并写入 C1 的 `supersedes` 指向前一 revision。禁止传递定值。

## Acceptance scenarios

- [x] A1 完整阶梯 X0→X1→X2→X3→X4 逐级推进成功（`test_full_ladder_x0_to_x4`）。
- [x] A2 跳级被拒：`advance_stage` 只允许 `+1`（`test_skip_level_rejected`）。
- [x] A3 X3→X4 必须走 `promote()`（后者带四道晋级门槛）（`test_x3_x4_must_use_promote`）。
- [x] A4 每级门槛的**判别力**：边界缺失 / 无回归集 / 沙箱未通过 / 无跨项目复现 / 无反面案例 → 各自被拒（5 条测试）。
- [x] A5 X3→X4 四门槛：`recurrence_count`、等级、reviewer、human 审批，缺一即拒（`test_x3_x4_four_gates_rejected`）。
- [x] A6 `promoted` 与 `stage` 一致性：`promoted == (stage == X4_POLICY)`，且 `promoted=True` 但 stage 非 X4 的非法态在 load 时被重新派生（`test_promoted_stage_consistency`）。
- [x] **A7（§10.5 新增）同一 `experience_id` 连续 `record()` 两次 → 两次都成功**，`wiki_page` 有 2 个 revision（r1/r2），head 指向 r2，r1 仍可读，`supersedes == "exp_rr:r1"`（`test_record_same_experience_twice_appends_two_revisions`）。
- [x] **A8（§10.5 新增）`revision` 是派生而非定值**：连续 4 次写入得到 `[1,2,3,4]`（`test_record_derives_revision_not_constant`）。
- [x] A9 `test_experience_sink` 的 mirror-page 断言改走 `get_page()`，并改为**页级（head）计数 + 逐 revision 校验**，反映 append-only 语义。
- [x] 回归：全量 `549 passed / 2 skipped / 0 failed`（`-W error -o addopts=""`），ruff `All checks passed!`，`compileall -q src` 干净。

## Invariants

- **`revision` 必须是派生值**。本包任何写 `WikiPage` 的路径（`record()` / `advance_stage()` / `promote()`）都不得传递 `revision` 常量；违反会在第二次写入时崩，或（更糟）静默覆盖。
- **本分支是 stacked，不得独立合并**。修复依赖 L-06 的 `get_page()`；在无 P1 的分支上单独跑会 `AttributeError`（实测 10 failed）。合并顺序必须是 L-06 → L-07。
- **`contracts.py` 的 `_derive_promoted_from_stage` validator 必须保留**。P2 相对 P1 在 `contracts.py` 上只多这 11 行；若叠加时被 P1 版本覆盖，`test_promoted_stage_consistency` 立刻失败（实测过 —— 这正是 R-007 L1 §5「语义耦合」预警的 `contracts.py` 冲突）。
- **裸 `page_id` 不得用于读 `wiki_page`**。C1 之后 record_id 是 `f"{page_id}:r{revision}"`，`store.get("wiki_page", 裸id)` 返回 `None`。唯一合法入口是 `get_page()`。
- `advance_stage` 只做 `+1`，X3→X4 归 `promote()`；两级不得混淆。
- 门槛检查只读 `ExperienceRecord` 与 `StageEvidence`，不触碰 Knowledge/Evidence/Gate 的职责。

## Decisions

- D-L2-01 成熟度用**独立枚举 `ExperienceStage`** 而非复用 `promoted` 布尔；`promoted` 降级为**派生投影**（§11.3）。依据：布尔无法表达"到哪一级"与"每级门槛不同"。
- D-L2-02 派生用 pydantic `@model_validator(mode="after")`，保证**任何构造路径**（service 调用 / 原始 dict / `model_copy`）都不能进入非法态。`model_copy` 不重跑 validator，故 `advance_stage` / `promote` 里显式同步两个字段。
- D-L2-03 §11.5 的门槛表分**两级生效**：字段级（边界/回归集/反面案例）现在可校验；沙箱复现与跨项目证据属 P3 交付，当前用 `StageEvidence` 显式建模以便**今天就检查门槛**，P3 用真实复现日志填充同一形状。
- D-L2-04 **`record()` 的 revision 派生是本包对跨线冲突的修复**，不是可选项。实测证据见上；契约要求与验收负例已写入 R-007 L2 §10.5。
- D-L2-05 `test_experience_sink` 里 `len(pages) == len(records)` 的原断言**固化了 upsert 语义**（append-only 后 N 次写入 → N 个 revision、M 个 head）。改为页级计数 + 逐 revision 校验，语义正确且更严。
- D-L2-06 `contracts.py` 的 C5 字段（stage / applicability / validity / regression）属共享契约，**由 owner 决定是否上收**；本包只保证不与 L-06 的 C1 字段冲突。

## Verification

```
PYTHONPATH=src python -m pytest -q -o addopts="" -W error      # 549 passed, 2 skipped
python -m ruff check src tests                                  # All checks passed!
python -m compileall -q src                                     # clean
node .ai-team/check.mjs --base 04ce9a9
```

判别力（§10.5 的两条新测试）：在**修复前的组合分支**上运行时
`test_record_same_experience_twice_appends_two_revisions` 以
`ValueError: revision 1 must be > current max 1` 失败（判据型，非符号缺失型）。
单独在 L-07（无 P1）上跑不构成判别力 —— `add_page` 是 upsert，重复写入"成功"是错误原因造成的假绿。
