# R006 L1 Writer — append-only wiki writer + head index

- ID: `R006-L1-WRITER`
- Title: `Append-only wiki page writer + wiki_page_head index (C1 / §11.9)`
- Status: `active`
- Status note: `append-only 写入者与 head 索引已落地（537 passed / 2 skipped）；已推送 origin/owner/r006-l1-writer，未合并 main。M11-MVP-01 承接本分支并完成剩余 3 项（N+1 修复、桥接边白名单、正向测试）。本 ledger 为补齐 check.mjs 门禁而建。`
- Owner: `owner`
- Next owner: `member A`（M11-MVP-01 承接）

## Goal

把 WikiPage 从「同 page_id 就地 upsert」改为**追加式版本存储**（每个 revision 一条记录），
并用一张 `wiki_page_head` 索引把裸 `page_id` 解析到当前 revision。
这是 R-006 契约 C1 / 架构 §11.9 的基础：不换写入者，底层 `ON CONFLICT(kind, record_id) DO UPDATE`
会让「revision 不可覆盖」这条验收**根本无法实现**。

## Acceptance scenarios

- [x] A1 同一 `page_id` 写两次 → `wiki_page` 有 2 条记录（`p:r1` / `p:r2`），**旧 revision 仍可读取**。
- [x] A2 `revision <= current_max` 被拒（append-only：revision 永不被覆盖）。
- [x] A3 裸 `page_id` 经 `wiki_page_head` 解析到当前 revision；`get_page()` / `list_pages()` 是唯一合法入口。
- [x] A4 版本写入与 head 更新在**同一事务**（`storage.transaction()` / `_write_record()`），崩溃不会留下 head 指向缺失版本。
- [x] A5 `add_edge` 端点解析与 `retrieve` 图扩展改走 `get_page()`。
- [x] A6 崩溃留下的悬空 head：`get_page()` 返回 `None` 而非抛错，`list_pages()` 跳过该条。
- [x] 回归：全量 `537 passed / 2 skipped / 0 failed`（`-W error -o addopts=""`），ruff `All checks passed!`，`compileall -q src` 干净。

## Invariants

- **`record_id = f"{page_id}:r{revision}"`**，每个 revision 一条记录；不得改回 `record_id = page_id`（会使 append-only 失效）。
- **新 revision 必须 `> 当前 max`**（严格递增，拒绝定值与回退）。
- **裸 `page_id` 不得用于 `store.get("wiki_page", ...)`** —— head 索引上线后该调用返回 `None`。
  唯一合法入口是 `get_page()`；新增代码尤其容易漏（已在 `add_edge` / `retrieve` 处修过）。
- **version 与 head 必须同一事务**写；不得拆成两次独立写。
- **`author` 是 WikiPage 的必填字段**（本包引入）；所有构造点都必须传值。

## Decisions

- D-L1-01 `record_id` 用 `f"{page_id}:r{revision}"` 而非复合主键 —— 复用既有 `(kind, record_id)` 索引，不动 `storage.py` 的表结构。
- D-L1-02 head 单独一条 `wiki_page_head` 记录（`{page_id, current_revision_id, revision}`），而不是在 `wiki_page` 表上加 `is_current` 列 —— 后者在 append-only 下需要更新既有行，与不覆盖语义冲突。
- D-L1-03 `author` 改为必填（无默认值）：追加式版本必须能追溯"谁写的这一版"；代价是 4 个既有构造点需要补字段（见下）。
- D-L1-04 `get_page()` 对悬空 head 返回 `None` 而非抛错：head 是权威，缺失版本视为页面不存在，避免读取路径因历史崩溃而整体失败。

## Known limitations（**交接给 M11-MVP-01**）

1. **`list_pages` 有 N+1 查询**：现为 `for head in heads: store.get(...)`。
   实测 200 页 = **200 次 get / 60ms**（旧版 1 次 list / 0.71ms）。
   这是「version 表 + head 索引」的必然代价，**不是实现失误**；修法是一条 JOIN SQL。
2. **跨分区 GraphEdge 仍是一刀切禁止**（`knowledge.py:126`）。
   需按原设计 §12.3 收窄为**14 类受管桥接 + 3 类同类边**白名单。
3. **正向测试缺失**：既有测试只覆盖「跨分区边被拒绝」一侧。
   收窄为白名单后必须补「白名单跨分区**被允许**」+「`get_page()` 解析裸 id」两条正向断言。

## Cross-file companion changes

`author` 改为必填后，本包改了 4 个文件（**均属 M11-MVP-01 的 `forbidden_paths`，现应视为 `frozen`**）：

| 文件 | 改动 | 性质 |
|---|---|---|
| `evolution_service.py` | +9 | **真 bug 修复**：`record()` 从 `get_page()` 派生 `revision = max+1` + `supersedes`。不改则第二次 `record()` 必崩（`experience_sink` 的 dedup/recurrence 会重复调） |
| `reader_service.py` | +2 | 构造 `WikiPage` 补 `author=` |
| `profile_service.py` | +1 | 同上 |
| `search_service.py` | +1 | 同上 |

> **注意**：`evolution_service.py` 的 revision 派生修复与 `owner/r006-l2-stage`（L-07）**各自独立实现了同一处修复**。
> 两分支合并时 `evolution_service.py` 会真冲突，按 L-07 版本保留即可（其注释更完整）。

## Verification

```
PYTHONPATH=src python -m pytest -q -o addopts="" -W error      # 537 passed, 2 skipped
python -m ruff check src tests                                  # All checks passed!
python -m compileall -q src                                     # clean
node .ai-team/check.mjs --base <本分支的父 sha>
```

判别力（`tests/test_r006_l1_writer.py`，放在修复前基线 `04ce9a9` 上）：

| 方式 | 结果 | 性质 |
|---|---|---|
| 裸放（不补符号） | `ImportError: cannot import name 'WIKI_PAGE_HEAD_KIND'` | ⚠️ **符号缺失型 —— 不计入判据型证据** |
| **注入 shim**（只补符号、不改行为） | **9 failed / 2 passed** | ✅ **判据型** |

**2 条在 shim 下仍通过 → 判别力弱，只作回归护栏**：
`test_add_edge_and_retrieve_use_head_index`、
`test_retrieve_graph_channel_not_silently_broken_by_versioning`。

## Handoff note

M11-MVP-01 基于本分支开工，**不要重做** append-only 写入者与 head 索引。
剩余 3 项见上「Known limitations」。边界与验收见
`docs/tasks/M11-knowledge-lane/TASK-SPECS.md` §6 与 `tasks/M11-MVP-01/task-package.json`。
