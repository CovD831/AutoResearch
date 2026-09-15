# L-01 M01 L3 骨架（ContextAssembler / 状态迁移 / 交接回放）

> **层级**：L3 骨架 —— **开工者必须把它补全成完整 L3 后再写代码**（补齐方法见 R-007 `07-lane-kickoff-convention.md` §2）
> **上游权威**：R-007 `04-l2-contracts.md` **K5**（`ContextBudget`/`ContextSlice`）+ **K6**（`StateMigration`）
> **原表**：M01-05（`任务拆解书_详细版.md:121`）`ContextAssembler`、M01-02 迁移、M01-06 交接回放
> **base_ref**：`main@8dd8780`（**实测 537 passed / 2 skipped / 0 failed**，本 worktree 自测）
> **排他文件**：`context_assembler.py` `migration.py`（**新开新文件**）

---

## 1. Task source

| 子任务 | 原表要求 | 本包契约 |
|---|---|---|
| **M01-05** | 「**只装配当前任务必需上下文；超限时退回拆分而非堆砌全文**」 | **K5** |
| **M01-02** | `ResearchState` v1→v2 迁移 + 未知字段拒绝/保留策略 | **K6** |
| **M01-06** | 交接回放工具：按 run/thread 导出 envelope / Gate / artifact 引用 | 复用 `handoffs.py` 既有语义 |

---

## 2. 必须落地的契约

### K5 `ContextBudget` / `ContextSlice`

**字段**：`max_tokens` / `max_items_per_kind` / `reserved_ratio`（默认 0.2）
**`ContextSlice`**：`slice_id` / `kind`（`evidence`/`handoff`/`knowledge`/`guidance`）/ `refs`（**引用 ID，非内容**）/ `rendered`（可空）/ `truncated` / **`dropped_refs`（被丢弃的引用必须记录）**

**四条不变量**：

| # | 不变量 | 可校验 |
|---|---|---|
| K5-1 | **超限时退回拆分** —— 不得堆砌全文 | ✅ 装配器断言 `truncated ⟹ dropped_refs` 非空 |
| K5-2 | `truncated=True` ⟹ `dropped_refs` 非空或截断可追 | ✅ |
| K5-3 | **`kind="guidance"` 的 slice 不得进入事实论断** | ❌ **架构意图**（对齐 L1 §4.2 A1，靠输出侧追溯） |
| K5-4 | `refs` 只存引用 ID，不存全文 | ✅ 长度上限 + 类型校验 |

> ⚠️ **M01-05 是 M11-04（ContextPack 分级装配）的前置** →
> **本契约必须为「分级」留接口（`kind` + 预算分层），不要写死单级。**
> 这是 R-007 §2 对 L-01 的明确要求，违反会导致 M11-04 返工。

### K6 `StateMigration`

**字段**：`from_version` / `to_version` / `field_mapping` / `unknown_field_policy`（`reject`|`preserve`，**必须显式选择**）/ `defaults`

| # | 不变量 | 可校验 |
|---|---|---|
| K6-1 | **未知字段策略必须显式**，不得默认静默丢弃 | ✅ |
| K6-2 | 迁移必须可回放（同输入同输出） | ✅ |
| K6-3 | `to_version` 严格递增 | ✅ |

> **K6-1 是「静默丢弃」的正面防线** —— 本项目缺陷族之一。负例必须断言
> 「未知字段在 `preserve` 策略下**确实保留**」，而不是断言「没崩」。

---

## 3. 复用既有（**不得重造**）

- **交接回放**：参考 `handoffs.py`（R-007 原表述：既有 envelope 语义）→ **不要另造 handoff 类型**。
  ⚠️ **开工时先实测 `handoffs.py` 的行数与 envelope 字段**，再决定复用边界（不要照抄文档声称）。
- 引用 ID 口径与既有 handoff 纪律一致（**传引用不传内容**）。

---

## 4. 负例（**开工者补全**）

| # | 负例 | 断言什么 |
|---|---|---|
| N-1 | 预算不足以装下全部 item | **退回拆分**，且 `dropped_refs` **确实记录了被丢的引用**（不是空数组） |
| N-2 | 迁移遇到未知字段 + `policy="reject"` | **报错**（不是静默通过） |
| N-3 | 迁移遇到未知字段 + `policy="preserve"` | 未知字段**确实出现在结果里** |
| N-4 | `kind="guidance"` 的 slice | **不出现**在事实论断的 refs 里（若可测） |

---

## 5. Deliberate non-goals

- **不做** M11-04 的 ContextPack 分级装配本身（那是 L-06 的线）—— 本包只**留接口**。
- **不碰** `knowledge.py` / `storage.py` / `contracts.py`（R-007 §3.2 全局串行）。
- **不建**第二套 handoff 类型。

---

## 6. 判别力证据（收口必填）

新测试须在**实现前基线**上失败，且为**判据型**（非 `ImportError`/`AttributeError`）。
新模块首次引入时，需注入「**只补符号、不改行为**」的 shim 才能取得判据型（见 `07-lane-kickoff-convention.md`）。

---

## 7. 验收命令

```bash
PYTHONPATH=src python -m pytest tests/test_m01_*.py -q -o addopts="" -W error
PYTHONPATH=src python -m pytest -q -o addopts="" -W error    # 基线 537 passed 不得下降
ruff check src tests && compileall -q src
node .ai-team/check.mjs --base main
```

---

## 8. Contract deviations

（开工后逐条登记，**不得静默偏离**。）
