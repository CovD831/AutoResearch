# M11 lane — 拉取说明与待办清单

> **v4（2026-09-15 14:50）**：R-006 P1 已合并进 main，**阻塞解除，可以开工**。见 §0。
> **v3（2026-09-15 14:30）**：就绪性审计后修订。
> **本文件是给执行人的第一入口。** 分支里已经包含 R-006 P1 的完整实现，**不要重复实现 revision/head 那一块**。

---

## 0. ✅ 前置已解决：直接从 `main` 切分支

**R-006 P1 已合并进 main**（经保护窗口，`04ce9a9` → `ea1663b` → `f31d0dc`），
所以**不再需要 `upstream/owner/r006-l1-writer`** —— 那个分支的内容已经在 main 里了。

```bash
git fetch origin
git switch -c codex/m11-mvp-01 origin/main
git worktree add ../AutoResearch-m11 codex/m11-mvp-01
```

**基线数字**：`537 passed / 2 skipped / 0 failed`
（在合并后的 main 上实测；若你的 clone 落后于 `f31d0dc`，先 `git pull`）

> 历史记录：合并前曾有二选一（先合 P1 vs MVP-01 继承 P1 分支）。老板 2026-09-15 采纳「先合 P1」，
> 理由：P1（写入者基建）与 M11（边界 + 检索）性质不同，混一个 PR 会让审查面从 +234 膨胀到 +4536。

---

## 1. 这个分支包含什么

**分支**：`owner/r006-l1-writer` @ **`9c60043`**（从 `main@04ce9a9` 切出，**比 main 多 2 个 commit**）

| 内容 | 说明 |
|---|---|
| **R-006 P1 实现** | append-only wiki 写入者 + head 索引（见 §2） |
| **C1–C9 契约** | `src/autoresearch/contracts.py`（实测 +234 / −2） |
| **契约设计文档** | `docs/rearchitecture/R006-knowledge-experience/`（L1 架构 + L2 契约 + 调研 + 钢人论证） |
| **M11 任务包** | `docs/tasks/M11-knowledge-lane/`（本目录） |

**验证状态**（`wt-l1-writer` 实测）：全量 `537 passed / 2 skipped / 0 failed`（`pytest -q -o addopts="" -W error`）

> ⚠️ **这个 537 只对 `9c60043` 成立**。若 owner 选了「先合 P1」，你必须在**自己的 worktree 重新实测**，
> 不得搬运这个数字（本项目硬约束：基线不可跨 worktree 搬运）。

---

## 2. P1 已实现什么（**不要重做**）

| 能力 | 位置（实测行号） |
|---|---|
| `WIKI_PAGE_HEAD_KIND` 常量 | `knowledge.py:16` |
| **append-only `add_page`**：`record_id = f"{page_id}:r{revision}"`，拒绝 `revision <= max` | `knowledge.py:33-77` |
| **`wiki_page_head` 索引**：裸 `page_id` → `{current_revision_id, revision}` | `knowledge.py` |
| **`get_page()` / `list_pages()`**：裸 id 的**唯一**解析入口 | `knowledge.py:78-117` |
| `add_edge` 端点解析改走 `get_page()` | `knowledge.py:118-136` |
| `retrieve` 图扩展改走 `get_page()` | `knowledge.py:148+` |
| **写原子性**：版本 + head 同一事务 | `storage.py`（`transaction()` / `_write_record()`） |
| 契约字段 C1–C9 | `contracts.py` |

**测试**（已有，别删）：
- `tests/test_r006_contracts.py` — **17 passed**
- `tests/test_r006_l1_writer.py` — **11 passed**

### 2.1 P1 还改了 4 个文件（**v3 补录，原稿漏了**）

这 4 个文件在原改进稿里既未列入「已实现」、又在 MVP-01 的 `forbidden_paths` 里。
经核实是 append-only 上线后的**必要连带改动**，已改为 **`frozen_paths`（只读不得改）**：

| 文件 | 改动 | 为什么是必要的 |
|---|---|---|
| `evolution_service.py` | +9 | **真 bug 修复**：`record()` 从 `get_page()` 派生 `revision = max+1` + `supersedes`。不改则**第二次 `record()` 必崩** —— 而 `experience_sink` 的 dedup/recurrence 会重复调它 |
| `reader_service.py` | +2 | 构造 `WikiPage` 时补 `author=`（P1 把 `author` 改为必填） |
| `profile_service.py` | +1 | 同上 |
| `search_service.py` | +1 | 同上 |

**→ 你只能读、不能改。** 确需修改请先找 owner。

---

## 3. 还没做的（**M11-MVP-01 的剩余工作**）

| # | 待办 | 判据 |
|---|---|---|
| **1** | **修 `list_pages` 的 N+1** | 现状：`for head in heads: store.get(...)`。**实测 200 页 = 200 次 `get` / 60ms**；对照旧版 `main` = **0 次 get / 1 次 list / 0.71ms**。目标：**O(1) 查询数** |
| **2** | **跨分区边白名单（14 类受管桥接 + 3 类同类边）** | 现状仍是**一刀切禁止**（`knowledge.py:126` 的 `raise ValueError("cross-partition graph edges are not allowed")`，实测原样）。白名单见 `TASK-SPECS.md` MVP-01 |
| **3** | **补正向测试** | 现状只有「**被拒绝**」一侧。必须补：① 白名单类型跨分区**被允许**；② `get_page()` 能解析裸 id（而 `store.get("wiki_page", 裸id)` 不能） |
| **4** | **建账本 + 新测试文件** | `.ai-team/tasks/M11-MVP-01.md`（**gate 必需**）、`tests/test_knowledge_boundary.py`、`tests/fixtures/knowledge_boundary/` —— 三个都**尚不存在**，须新建 |

**注意**：`contracts.py` 里含 **C2 `Statement` / C9 `ExperienceInjection`** —— 这两个在 M11 任务包里**明确不在范围**。
**先留着别删**；`contracts.py` 现在是**「条件允许」**（判据见 `TASK-SPECS.md` §5-B2 的 A/B/C），
但**动 C2/C9 一律禁止**。觉得碍事请找 owner 确认。

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

**开工第一步先枚举确认**：

```bash
grep -rn '"wiki_page"' src/
```

**期望**只应有 5 处**合法**命中（`storage.py` 的 `kinds` 默认参数、`contracts.py` 的枚举常量、
`knowledge.py` 的三处写入/按 `current_revision_id` 读取）。
**若出现 `store.get("wiki_page", <裸 page_id>)` → 有漏网，先修。**

### 坑 2：`list_pages` 的 N+1

见 §3 第 1 项。**这是 P1 引入的性能退化**，不是实现失误 —— 是「version 表 + head 索引」的必然代价，修法是一条 JOIN 查询。

### 坑 3：正向测试缺失

跨分区边从「全禁止」收窄为「白名单允许」后，**既有测试只覆盖拒绝侧**（`ValidationError ⊂ ValueError`，所以旧断言仍绿）。
→ 新语义**必须补正向断言**，否则切换了行为却没人测。

**而且拒绝侧的断言在 `tests/test_governance_services.py:114`**（`test_partitioned_wiki_graph_retrieval`，断言在第 154 行）
—— **不在原 `allowed_paths` 里，v3 已补入**。
⚠️ 它绿**不代表白名单生效**，只代表你没破坏拒绝侧。**两侧都要测。**

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

> ✅ **§0 的前置已解决** —— 直接从 `origin/main` 切分支。
>
> ℹ️ **remote 说明**：早期版本要求加 `upstream` 指向主仓，那是因为 P1 当时只在主仓的未合并分支上。
> **现在 P1 已在 main 里**，只要你的 `origin` 指向主仓（或已 fork 同步），直接 `git fetch origin` 即可。

### 主仓 clone（owner / 集成人）

```bash
git fetch origin
git switch -c codex/m11-mvp-01 origin/main
git worktree add ../AutoResearch-m11 codex/m11-mvp-01
```

### 在 fork 里开发（**成员 A 的情况**）

```bash
# 1) 一次性：把主仓加为 upstream（如果已有可跳过）
git remote add upstream https://github.com/CovD831/AutoResearch.git

# 2) 从主仓 main 拉取（P1 已在其中）
git fetch upstream
git switch -c codex/m11-mvp-01 upstream/main

# 3) 建独立 worktree（推荐）
git worktree add ../AutoResearch-m11 codex/m11-mvp-01
```

### 基线核对（**必须先跑，数字不对就别开工**）

```bash
cd ../AutoResearch-m11
PYTHONPATH=src /Users/abab/.workbuddy/binaries/python/envs/default/bin/python \
  -m pytest -q -o addopts="" -W error
PYTHONPATH=src /Users/abab/.workbuddy/binaries/python/envs/default/bin/python -m ruff check src tests
PYTHONPATH=src /Users/abab/.workbuddy/binaries/python/envs/default/bin/python -m compileall -q src
```

**期望**：`537 passed / 2 skipped / 0 failed`。若不是这个数字，先别开工，来找我。

> **v3 修正**：原稿写 `PYTHONPATH=src python -m pytest`，但沙箱内 `python` 指向 3.9.6，
> 必须用上表的解释器全路径。

### 开工

读 `docs/tasks/M11-knowledge-lane/TASK-SPECS.md` 的 **M11-MVP-01** 一节，
然后按 `tasks/M11-MVP-01/task-package.json` 的 `allowed_paths` / `conditional_paths` / `frozen_paths` / `forbidden_paths` 动手。

**第一步先做这两件事**：
1. 跑 §4 坑 1 的 `grep -rn '"wiki_page"' src/` 枚举，确认没有漏网；
2. 建 `.ai-team/tasks/M11-MVP-01.md` 账本（**否则 `check.mjs` 门禁必然 blocked**）。

---

## 8. 边界（与 `task-package.json` 同步）

**不要改**（`forbidden_paths`）：
```
src/autoresearch/evidence.py
src/autoresearch/gates.py
.ai-team/TASK.md
.project-to-act/
```

**只读不得改**（`frozen_paths`，P1 已改好 —— 见 §2.1）：
```
src/autoresearch/evolution_service.py
src/autoresearch/profile_service.py
src/autoresearch/reader_service.py
src/autoresearch/search_service.py
```

**条件允许**（`conditional_paths`，每个 hunk 须命中 A/B/C 之一 —— 见 `TASK-SPECS.md` §5-B2）：
```
src/autoresearch/contracts.py
```

**完整边界**：`tasks/M11-MVP-01/task-package.json` 的 `allowed_paths` / `conditional_paths` / `frozen_paths` / `forbidden_paths`。

