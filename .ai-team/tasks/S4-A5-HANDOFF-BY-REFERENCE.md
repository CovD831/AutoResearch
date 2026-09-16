# S4-A5 Handoff by Reference

- ID: `S4-A5-HANDOFF-BY-REFERENCE`
- Title: `S4 handoff envelope becomes a reference list instead of a content carrier`
- Status: `integrated`
- Status note: 已提交审查（PR #23，head `9510ac4`）。验收证据：本 commit 实测 **587 passed / 2 skipped**（base `main@b83cc56` 实测 539）。**已合并 `main@b5853bd`（PR #23，squash）。** 后续验收（accepted）挂 P2/认证层与跨进程并发。
- Status note: 缺陷由成员真实运行的 44 篇检索暴露（41 张阅读卡 / 164 证据号被 pydantic 拒绝，运行直接崩）。修法是**语义**而非数字：`HandoffEnvelope` 的 `artifact_refs`/`evidence_ids` 由「内容承载量级」重定义为「引用界」（20→500、100→2000，仍有限）；`paper_reader` 不再逐卡嵌入 `findings[0][:300]`；`paper_search` 的硬编码 `[:20]` 改为命名常量 + **可观测告警**，并顺手修掉 `summary=paper.title` 与 `ArtifactRef.summary` 上限 500 不符的同族缺陷。基线（A8 提交 `7b15997`）525 passed → 本包快照 (`b7635d7`) **532 passed / 2 skipped / 0 error**（新增 7）。**判别力 4 failed，全部判据型。**
- Owner: `user/team`
- Next owner: `user/team`

## Goal

让交接单在真实检索量级下不再崩，并回归它本来的语义——**引用名单**。在 A8（主链路切 A5 adapter）可用之后执行，因为 A9 的契约上限需要 A8 暴露的真实量级作依据。

## Acceptance scenarios

- [x] 41 `artifact_refs` + 164 `evidence_ids` 的交接单可构造（**就是崩溃现场的实测数字**）。
- [x] 引用界**有限**：501 条 refs 仍被拒，放宽不等于无界。
- [x] `paper_reader` 的 refs 只带 `artifact_id` + `kind`，不嵌 `findings` / `statement` 正文。
- [x] 被引用的阅读卡**可按 id 从 store 解析**（引用是地址，不是载荷）。
- [x] `paper_search` 的截断**写入 diagnostics**（`first 50 of 57`），且 `refs_attached` 进 `bounded_context`。
- [x] 未截断时**不产生**多余告警（不能把正常路径也报成异常）。

## Invariants

- 交接单是**引用名单**；生产者不得嵌入可读内容。
- 引用界必须有限；不得用「放宽」包装「无界」。
- 任何截断必须可观测；静默丢弃等于 fail-open。
- 不修改 `storage.py`、`evidence.py`、`gates.py`、`capability.py`、`capability_registry.py`、`search_service.py`、`adapter_search_service.py`、`.ai-team/TASK.md`。
- 不删除老服务；不改变 `PaperRecord` / `ReadingCard` 契约字段。

## Decisions

- **D-A9-01 交接单是引用界，不是内容界**：全仓实测**没有任何消费方读取 `artifact_refs`/`evidence_ids` 的内容**（`handoffs.py` 不读、四个 agent 只生产、`readiness.py` 只判空）。所以「只传引用」不是能力降级，而是让实现追上语义。数字放宽到 500/2000 是**引用容量**，并保留有限上界。
- **D-A9-02 不选「无限放宽」**：只把 20→200 这类改法治标——真实量级若到 500 再爆。语义修正后才谈数字。
- **D-A9-03 `paper_search` 的截断必须告警**：原 `outcome.papers[:20]` 是静默丢弃，下游读起来像"收到了全部"。改为 diagnostics + `refs_attached` 计数。
- **D-A9-04 顺手移除 `summary=paper.title`**：`ArtifactRef.summary` 上限 500 字符而 `PaperRecord.title` 无长度限制，超长标题会毫无理由地拒掉信封。属同一缺陷族的相邻位置。

## Completed

- `contracts.py`：`HandoffEnvelope` docstring 写明引用语义；`artifact_refs` 20→500、`evidence_ids` 100→2000（仍有限）。
- `agents/paper_reader.py`：refs 只传 `artifact_id` + `kind`。
- `agents/paper_search.py`：新增 `HANDOFF_REF_LIMIT = 50`；移除 `summary=paper.title`；截断写 diagnostics + `bounded_context`。
- `tests/test_handoff_by_reference.py`：7 条判据测试。
- 包内 `task-package.json` 与 `L3.md`。

## Pending

- 交接单「不得嵌内容」无法在 pydantic 层强制，只能靠测试与约定（见 Not closed）。

## Next step

- 与 A8 同分支提交（A9 依赖 A8 的形状），一并通过保护窗口合并。
- 合并后 A 线下一包为 A7（knowledge 向量检索）。

## Verification

| 项 | 命令 | 结果 |
|---|---|---|
| 聚焦 | `pytest tests/test_handoff_by_reference.py` | **7 passed** |
| 全量 | `pytest -q -o addopts="" -W error` | **532 passed / 2 skipped / 0 error**（基线 A8 `7b15997` = 525） |
| ruff | `ruff check src tests` | All checks passed |
| compileall | `compileall -q src` | exit 0 |
| 判别力 | A8 提交 `7b15997` 上只放 A9 测试（+ 常量 shim） | **4 failed，全部判据型** |

判别力 4 条：① 41/164 超界被拒（崩溃现场）② 上限不足 ③ reader 仍嵌正文 ④ 截断静默。

## Handoff note

- **判别力验证的坑**：测试在模块层 import `HANDOFF_REF_LIMIT`，基线会 ImportError（符号缺失型，口径上**不计入证据**）。需在基线注入**只补常量、不改行为**的 shim（`= 20`，与旧硬编码 `[:20]` 语义一致）才能取得判据型失败。
- 接手者注意：本包的「不得嵌内容」是**约定 + 测试**，不是契约强制。若未来有人再往 ref 里塞正文，只有 `test_reading_card_refs_are_resolvable_and_carry_no_content` 与 `test_reader_agent_handoff_drops_inline_summaries` 会拦。**这是本包最弱的一环。**

## Not closed

- 「交接单不得嵌内容」无静态强制手段；仅测试与约定约束。
- 引用界 500/2000 的依据是「单次真实检索量级」（实测量 44 篇 / 41 卡 / 164 证据号），更大规模下仍需重新评估。
