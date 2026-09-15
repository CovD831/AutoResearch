# M11 lane — 拉取说明与待办清单

> **本文件是给执行人的第一入口。** 分支里已经包含 R-006 P1 的完整实现，**不要重复实现 revision/head 那一块**。

---

## 1. 这个分支包含什么

**分支**：`owner/r006-l1-writer`（从 `main@04ce9a9` 切出）

| 内容 | 说明 |
|---|---|
| **R-006 P1 实现** | append-only wiki 写入者 + head 索引（见 §2） |
| **C1–C9 契约** | `src/autoresearch/contracts.py`（+236 行） |
| **契约设计文档** | `docs/rearchitecture/R006-knowledge-experience/`（L1 架构 + L2 契约 + 调研 + 钢人论证） |
| **M11 任务包** | `docs/tasks/M11-knowledge-lane/`（本目录） |

**验证状态**：全量 `537 passed / 2 skipped / 0 failed`（`pytest -q -o addopts="" -W error`）

---

## 2. P1 已实现什么（**不要重做**）

| 能力 | 位置 |
|---|---|
| `WIKI_PAGE_HEAD_KIND` 常量 | `knowledge.py` |
| **append-only `add_page`**：`record_id = f"{page_id}:r{revision}"`，拒绝 `revision <= max` | `knowledge.py` |
| **`wiki_page_head` 索引**：裸 `page_id` → `{current_revision_id, revision}` | `knowledge.py` |
| **`get_page()` / `list_pages()`**：裸 id 的**唯一**解析入口 | `knowledge.py` |
| `add_edge` 端点解析改走 `get_page()` | `knowledge.py` |
| `retrieve` 图扩展改走 `get_page()` | `knowledge.py` |
| **写原子性**：版本 + head 同一事务 | `storage.py`（`transaction()` / `_write_record()`） |
| 契约字段 C1–C9 | `contracts.py` |

**测试**（已有，别删）：
- `tests/test_r006_contracts.py` — **17 passed**
- `tests/test_r006_l1_writer.py` — **11 passed**

---

## 3. 还没做的（**M11-MVP-01 的剩余工作**）

| # | 待办 | 判据 |
|---|---|---|
| **1** | **修 `list_pages` 的 N+1** | 现状：`for head in heads: store.get(...)`。**实测 200 页 = 200 次 `get` / 118ms**；对照旧版 `main` = **0 次 get / 1 次 list / 1.03ms**。目标：**O(1) 查询数** |
| **2** | **跨分区边白名单（14 类受管桥接 + 3 类同类边）** | 现状仍是**一刀切禁止**（`knowledge.py` 里 `raise ValueError("cross-partition graph edges are not allowed")`）。白名单见 `TASK-SPECS.md` MVP-01 |
| **3** | **补正向测试** | 现状只有「**被拒绝**」一侧。必须补：① 白名单类型跨分区**被允许**；② `get_page()` 能解析裸 id（而 `store.get("wiki_page", 裸id)` 不能） |
| **4** | **`contracts.py` 是否上收** | P1 的契约改动在 `contracts.py`（+236）。**由 owner 决定**，不要自行调整 |

**注意**：`contracts.py` 里含 **C2 `Statement` / C9 `ExperienceInjection`** —— 这两个在 M11 任务包里**明确不在范围**。
**先留着别删**（`contracts.py` 在 `forbidden_paths`）；觉得碍事请找 owner 确认，不要自行删除。

---

## 4. 三个已知的坑（都有实测依据）

### 坑 1：裸 `page_id` 查不到

head 索引上线后，`store.get("wiki_page", page_id)` **返回 `None`**（因为 `record_id` 现在是 `f"{page_id}:r{revision}"`）。

**实测**：
```
store.get('wiki_page', 'p1') -> None      # 裸 id 查不到
list("wiki_page") -> 2 条，page_ids: ['p1','p1']   # 按页去重前是 N 条
```

→ **所有按裸 id 读取的地方必须走 `get_page()`**，包括 `add_edge` 端点解析与 `retrieve` 图扩展邻居解析。
（P1 已改，但**新增代码时容易漏**。）

### 坑 2：`list_pages` 的 N+1

见 §3 第 1 项。**这是 P1 引入的性能退化**，不是实现失误 —— 是「version 表 + head 索引」的必然代价，修法是一条 JOIN 查询。

### 坑 3：正向测试缺失

跨分区边从「全禁止」收窄为「白名单允许」后，**既有测试只覆盖拒绝侧**（`ValidationError ⊂ ValueError`，所以旧断言仍绿）。
→ 新语义**必须补正向断言**，否则切换了行为却没人测。

---

## 5. 判别力证据（如实标注）

把 `tests/test_r006_l1_writer.py` 放到修复前基线 `04ce9a9` 上：

| 方式 | 结果 | 性质 |
|---|---|---|
| 裸放（不补符号） | `ImportError: cannot import name 'WIKI_PAGE_HEAD_KIND'` | ⚠️ **符号缺失型 —— 不计入判据型证据** |
| **注入 shim**（只补符号、不改行为） | **9 failed / 2 passed** | ✅ **判据型** |

**2 条在 shim 下仍通过 → 判别力弱，只作回归护栏**：
- `test_add_edge_and_retrieve_use_head_index`
- `test_retrieve_graph_channel_not_silently_broken_by_versioning`

---

## 6. 契约原文在哪

| 文件 | 内容 |
|---|---|
| `docs/rearchitecture/R006-knowledge-experience/04-l2-contracts.md` | **C1–C9 的字段级定义 + 不变量 + 可机械校验性** |
| `.../02-l1-architecture.md` | L1 架构（分层 / 边界 / 不变量） |
| `.../01-external-research.md` | 外部调研（RRF 小语料、跨分区边、双通道等的依据） |
| `.../00-scope-and-authority.md` | 范围与决策 |

> **注意**：R-006 的 P2–P7 已暂停，**不再作为 M11 的验收依据**。
> C1–C9 中只有被 `TASK-SPECS.md` 明确引用的部分生效（C1 的 revision/head、C3 的桥接边方向、C7 的 `score_breakdown`、C8 的 `RecallAuditRecord`）。
> **C2 `Statement` / C9 `ExperienceInjection` 不在 M11 范围。**

---

## 7. 开工步骤

```bash
# 1) 拉取
git fetch origin
git switch -c codex/m11-mvp-01 origin/owner/r006-l1-writer

# 2) 建 worktree（推荐，避免污染）
git worktree add ../AutoResearch-m11 codex/m11-mvp-01

# 3) 跑一遍基线
cd ../AutoResearch-m11
PYTHONPATH=src python -m pytest -q -o addopts="" -W error     # 期望 537 passed / 2 skipped
python -m ruff check src tests
python -m compileall -q src

# 4) 开工 —— 先读 docs/tasks/M11-knowledge-lane/TASK-SPECS.md 的 M11-MVP-01
```

---

## 8. 边界（`forbidden_paths`）

**不要改**：
```
src/autoresearch/evolution_service.py
src/autoresearch/profile_service.py
src/autoresearch/reader_service.py
src/autoresearch/search_service.py
src/autoresearch/evidence.py
src/autoresearch/gates.py
.ai-team/TASK.md
.project-to-act/
```
`src/autoresearch/contracts.py` **仅在 owner 批准下**可改。

**完整边界**：`tasks/M11-MVP-01/task-package.json` 的 `allowed_paths` / `forbidden_paths`。
