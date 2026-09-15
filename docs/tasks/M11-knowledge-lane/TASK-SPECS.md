# M11 知识库 lane — 任务规格（改进版）

> **版本**：v3（2026-09-15 14:30，就绪性审计后修订；v2 = 同日 owner 改进稿）
> **基础**：成员 A 提交的 `M11-MVP-01～04` 拆分（结构采纳）+ R-006 L2 契约（择优注入）
> **改动摘要**：见文末 §改动对照
> **权威关系**：本文件是 M11 lane 的执行权威；R-006 的 L1/L2 降为**参考设计**，只在本文件明确引用的地方生效。
> **v3 修订**：状态一律改为中文枚举（与 `.ai-team/check.mjs` 的 `VALID_STATES` 对齐）；补齐 6 项就绪性缺陷（见 §5）。

---

## v3 就绪性修订摘要（改动前状态：不可开工）

本版修掉 2026-09-15 就绪性审计发现的 6 项缺陷。**"不能开工"的两个阻塞项中，B2 已在本文件内解决；B1 需要 owner 决策（见 §5-B1）。**

| # | 缺陷 | 处置 |
|---|---|---|
| **B2** | MVP-01 的 `contracts.py` 归属自相矛盾（`task-package.json` 允许 vs `lane-manifest.json` 禁止） | **在本文件内裁决**：`contracts.py` 列为**条件允许**，并给出明确判据 |
| **M1** | P1 越界改了 4 个 `forbidden_paths` 文件且文档未列 | 新增 §6「P1 实际改动清单」，含 4 个文件的逐处说明 + 授权 |
| **M2** | 跨分区边拒绝侧测试在 `test_governance_services.py`（不在 allowed_paths） | 加入 MVP-01 的 `allowed_paths`；并在「必须满足」里显式点名 |
| **M3** | 三条 gate 命令不成立 | 全部修正，见 §7 |
| **L1** | 声明的 3 个交付路径不存在、账本埋在 `allowed_paths` 里 | 改为「待新建」显式标注；账本提到开工步骤 |
| **B1** | `owner/r006-l1-writer` 未合并 main 且无 PR | **需 owner 决策**，见 §5-B1（本文件只能给建议，不能替 owner 定） |

---

## 5. 就绪性缺陷的裁决与处置

### 5-B2【已裁决】`contracts.py` 归属 —— 条件允许

**原矛盾**：`task-package.json` 的 `allowed_paths` 含 `contracts.py`，`lane-manifest.json` 的 `forbidden_shared_paths` 也含 `contracts.py`，`SOURCE-AND-HANDOFF.md` 写「仅在 owner 批准下可改」但从未批准。

**裁决：`contracts.py` 对 MVP-01 列为「条件允许」——default deny，白名单式放行。**

判据如下，**每次修改都必须能对上其中一条**：

| 允许改的情形 | 例子 | 判据 |
|---|---|---|
| **A. `RetrievalHit` 新增字段** | MVP-02/03 的 `channel` / `score_breakdown` / `matched_stage` | 是**新增**，不是删改既有字段 |
| **B. 既有契约字段的 bug 修复** | P1 给 `WikiPage` 加 `author` 必填、`revision` / `supersedes` | 有**失败用例**证明不改会错 |
| **C. 新增契约模型** | 桥接边白名单的注册表类型（若需落成模型） | 不属 M11 四包以外的模块（不得引入 C2/C9） |

**禁止改的情形（改了就拒收）**：

- 删除或重命名 `RetrievalHit` 既有对外字段（违反 lane 不变量 3）；
- 改动 C2 `Statement` / C9 `ExperienceInjection` 的既有定义（**不在 M11 范围**，见 §0）；
- 借「顺手重构」改契约的组织方式（如移动文件、拆模块）——这类改动**必须单独开 PR**。

**执行要求**：
1. `task-package.json` 的 `allowed_paths` 保留 `contracts.py`，但**每条注释里带上命中 A/B/C 哪一条**；
2. `lane-manifest.json` 的 `forbidden_shared_paths` **移除** `contracts.py`，改为在 `notes` 里写明「条件允许，判据见 TASK-SPECS §5-B2」；
3. 成员每次改 `contracts.py` 必须在 PR 描述里逐条列出命中的判据。

> **为什么不全禁**：把 `contracts.py` 全禁会让 MVP-02/03 无法新增 `RetrievalHit` 字段（`channel` / `score_breakdown` 是 MVP-03 的硬交付），
> 那两个包就必然又要在别处重新发明一套平行结构 —— 这正是本项目「新模块绕过现成原语 = 新缺陷的根源」那一族。
> **为什么不全放**：全放会让人顺手改 C2/C9 或删字段，而 `RetrievalHit` 是**对外契约**（lane 不变量 3 明写不可删改名）。

### 5-B1【待 owner 决策】`owner/r006-l1-writer` 的合并时机

**实测状态**：

```
wt-l1-writer HEAD = 9c60043 (owner/r006-l1-writer)
git merge-base --is-ancestor HEAD origin/main  →  NO: NOT in main
远端存在 refs/heads/owner/r006-l1-writer，但无 PR
```

四包 `base_ref` 都写 `04ce9a9`（= main HEAD），而 P1 实际内容在 `9c60043`，**比 main 多 2 个 commit**。

**两个选项**：

| 选项 | 做法 | 代价 |
|---|---|---|
| **① 先合 P1，再开 MVP-01**（本文件建议） | 走保护窗口把 `9c60043` 合入 main；MVP-01 从新 main 切出 | 走一次保护窗口流程；MVP-01 开工延后约半天 |
| ② MVP-01 直接继承该分支，成果挂在同一条 PR 上 | `git switch -c codex/m11-mvp-01 origin/owner/r006-l1-writer`，P1 与 MVP-01 同一个 PR 交付 | **审查面从 +234 契约膨胀到 +4536**，且 MVP-02/03 还要继续往上叠 |

**建议 ①**，理由：P1（写入者基建，537 passed 自洽）与 M11（边界 + 检索）是两种性质的工作；
且 M11 是三包串行栈（02/03/04 都依赖 01），**把 P1 一起塞进去会让后续每个 PR 的 diff 都拖着 P1 的历史**。

**⚠️ 此项未决前，MVP-01 不得开工** —— 因为「从哪条分支切」直接决定产出能否合回 main。

### 5-M1【已处置】P1 实际改动清单（含 4 个 forbidden 文件）

见 §6。**这 4 个文件的改动经核实为 P1 的必要连带改动，现予以追认授权。**

### 5-M2【已处置】拒绝侧测试的位置

`tests/test_governance_services.py:114` 的 `test_partitioned_wiki_graph_retrieval`
含**跨分区无类型边被拒绝**的既有断言（第 154 行的 `pytest.raises(ValueError)`）。

- 该文件**已加入 MVP-01 的 `allowed_paths`**；
- 并在 MVP-01「必须满足」里显式点名（见该节第 9 条）。

> **为什么必须点名**：`ValidationError ⊂ ValueError`，所以**即使实现错了、白名单没生效，这条旧断言仍然会绿**。
> 执行人若不知道它在哪，就会漏掉「拒绝侧仍须成立」这个回归要求。

### 5-M3 / 5-L1【已处置】见 §7 开工步骤 与各包 `task-package.json`

---

## 0. 与 R-006 的关系（重要）

**R-006 已暂停 P2–P7，不再作为 M11 的验收依据。** 但 R-006 有三样东西经比对后优于原拆分，已注入本文件：

| 注入项 | 出处 | 注入位置 |
|---|---|---|
| **append-only 写入者**（`record_id = f"{page_id}:r{revision}"` + head 索引） | R-006 P1（**已实现，537 passed**） | MVP-01 |
| **受管桥接边白名单**（14 类） | R-006 C3（方向）+ 原设计 §12.3（清单） | MVP-01 |
| **`RecallAuditRecord`（L8 召回审计）** | R-006 C8 | MVP-02 |

**未注入的**：R-006 的 C2 `Statement`（暂缓，无消费方）、C9 `ExperienceInjection`（属 M12，不属 M11）。

---

## 1. lane 总览

| 包 | 对应原文 | 目标 | 依赖 | 规模 |
|---|---|---|---|---|
| **M11-MVP-01** | M11-01/02/03 | Wiki+Graph 规范来源与边界 | 无（承接 R-006 P1） | 3 |
| **M11-MVP-02** | M11-05 | 候选召回管线（三路） | MVP-01 | 5 |
| **M11-MVP-03** | M11-07 | 融合、去重、索引维护 | MVP-02 | 4 |
| **M11-MVP-04** | M11-08 | 固定回归与验收证据 | MVP-03 | 4 |

**lane 级不变量**（全部包都必须满足）：

1. **检索层只负责召回和排序，不判断内容真实性。**
2. **不得在检索层生成 `EvidenceItem` / `GateDecision` / 真实性结论。**
3. **不得改变 `KnowledgeService.retrieve()` 的输入签名与 `RetrievalHit` 的对外字段**（可新增字段，不可删除/改名既有字段）。
4. **所有行为可离线重复验证**（无网络依赖）。
5. **每个包的代码、测试、fixture、任务账本、验收证据、rollback 说明必须在同一交付快照中保持一致。**

---

## M11-MVP-01 — Wiki+Graph 规范来源与边界

- **状态**：`ready`（**⚠️ 但受 §5-B1 阻塞：owner 未定 base 分支前不得开工**）
- **对应原文**：M11-01、M11-02、M11-03
- **目标**：固定 Wiki+Graph 的分区、页面版本和图边边界，为后续检索建立唯一规范来源。
- **依赖**：M04-01（已落地）、**R-006 P1（已实现，`9c60043`，待合并——见 §5-B1）**

### 主要交付

- 分区边界（五分区保持）
- **WikiPage append-only 版本写入者**（承接 R-006 P1）
- **`wiki_page_head` 索引 + `get_page()` / `list_pages()` 解析入口**
- **GraphEdge 受管桥接边白名单**
- 来源与 `evidence_ids` 保留

### 必须满足

1. **保留 `papers`、`experiences`、`knowledge`、`profiles`、`projects` 五个 Wiki 分区**（不改分区语义）。
2. **Evidence 使用独立的 `kind`（`"evidence"`），不得进入 Wiki 检索结果。**
   > ⚠️ 措辞更正：原拆分写「Evidence 使用独立 RecordStore」——**实测是同一个 `RecordStore` 实例**（`evidence.py` 用 `kind="evidence"`，`knowledge.py` 用 `kind="wiki_page"`）。意图正确，措辞与实现对齐。
3. **WikiPage 修改不得覆盖已有 revision。**
   - 写入路径：`record_id = f"{page_id}:r{revision}"`，**每个 revision 一条记录**
   - 新 revision 必须 `revision = max(既有) + 1`
   - 裸 `page_id` 通过 `wiki_page_head` 索引解析（`{current_revision_id, revision}`）
   - 版本写入与 head 更新**必须同一事务**
4. **GraphEdge 的两个端点必须存在**（不改）。
5. **跨分区 GraphEdge 使用受管桥接类型（白名单），无类型跨分区边拒收。**
   - **受管桥接边（14 类，允许跨分区）**：
     `CITES`、`SUPPORTS`、`CONTRADICTS`、`INVALIDATES`、`DERIVED_FROM`、
     `APPLIES_TO`、`USES_METHOD`、`USES_DATASET`、`EVALUATES_ON`、`HAS_LIMITATION`、
     `EXTENDS`、`IMPROVES`、`CREATED_IN`、`PREFERS`
   - **同类边（3 类，不跨分区）**：`SUMMARIZED_BY`、`DUPLICATES`、`SUPERSEDES`
   - **白名单可经注册表扩展，不改代码**
   - **桥接边不传递等价性**（架构意图，需消费端保证）
6. **页面和图边保留 `project_id`、`partition`、`record_id`、`evidence_ids` 等追踪字段。**
7. **`list_pages` 必须为 O(1) 查询数**（不得每条 head 一次 `store.get`）。
8. **所有按裸 `page_id` 读取的地方必须走 `get_page()`**，包括 `add_edge` 端点解析与 `retrieve` 图扩展邻居解析。
   > **开工前必做**：先跑一次全仓枚举，确认没有漏网。命令见 §7「裸 id 读取点枚举」。
   > 依据：本项目硬检查「修一个缺陷族时必须枚举该族所有位置」——P1 已改了 4 个调用方文件（见 §6），漏一处就会静默返回 `None`。
9. **既有「跨分区无类型边被拒绝」的断言必须保持绿。**
   - 位置：`tests/test_governance_services.py:114` 的 `test_partitioned_wiki_graph_retrieval`，断言在第 154 行。
   - ⚠️ **这是回归要求，不是新功能**：`ValidationError ⊂ ValueError`，所以**旧断言不会因为你的改动而变红**——
     它绿不代表白名单生效，只代表你没破坏拒绝侧。**两条都要测**。
   - 该文件已加入本包 `allowed_paths`（原改进稿遗漏，见 §5-M2）。

### 禁止

- 改变现有分区语义；
- 将 Evidence、Experience 和 Paper 混成无类型数据；
- **在本包引入向量召回或排序逻辑**；
- **改回 `record_id = page_id`**（会使 append-only 失效）；
- **在 `add_edge` / `retrieve` 内直接 `store.get("wiki_page", 裸id)`**（head 索引后查不到）；
- **把桥接边白名单扩展成"任意字符串都可以"**。

### 验收

| 类型 | 项 |
|---|---|
| 正例 | 同一页面创建新版本时**旧版本仍可读取** |
| 正例 | **白名单类型跨分区边被允许**（⚠️ 新增，见下） |
| 正例 | 页面来源、分区和 `evidence_ids` 可被完整读取 |
| 负例 | **直接覆盖旧 revision 被拒绝** |
| 负例 | **跨分区无类型 GraphEdge 被拒绝** |
| 负例 | 端点不存在时拒绝 |
| 性能 | **N 页时 `store.get` 调用数 ≤ 常数**（对照：旧版为 0，不得退化到 N） |
| 回归 | **`tests/test_governance_services.py:114` 的既有拒绝侧断言保持绿**（`ValidationError ⊂ ValueError`，它绿不代表白名单生效，见「必须满足」第 9 条） |
| 一致性 | 所有行为可离线重复验证 |

> ⚠️ **必须补正向测试**：既有测试**只覆盖「拒绝」侧**（R-006 两关结论 Q2：「`ValidationError ⊂ ValueError`，既有测试仍绿」）。
> 白名单收窄后**必须新增「白名单类型跨分区被允许」的正向断言**，否则新语义无人校验。
> 同时需**新增**「裸 id 查不到 → `get_page` 能查到」的对照断言。

### MVP 边界

只完成 Wiki+Graph 规范来源和边界。**不实现** `Statement`（statement 级证据绑定，留待 M02-09 失效传播需要时）、ContextPack、向量检索和生产级图数据库。

---

## 6. 承接说明：R-006 P1 的处理

**R-006 P1 已实现本包的核心**（分支 `owner/r006-l1-writer` @ `9c60043`，worktree `wt-l1-writer`，实测 **537 passed / 2 skipped / 0 failed**）：

| 已实现 | 文件 |
|---|---|
| `WIKI_PAGE_HEAD_KIND` 常量 + append-only `add_page` | `knowledge.py:16` / `:33-77` |
| `get_page()` / `list_pages()` | `knowledge.py:78-117` |
| `add_edge` 改走 `get_page()` | `knowledge.py:118-136` |
| `retrieve` 图扩展改走 `get_page()` | `knowledge.py:148+` |
| `storage.transaction()` / `_write_record()` | `storage.py` |
| C1–C9 契约字段 | `contracts.py`（**实测 +234 / −2**；旧稿写「+236」不准确） |
| `tests/test_r006_contracts.py` | 17 passed |
| `tests/test_r006_l1_writer.py` | 11 passed |

### 6.1 P1 实际改动清单（含 4 个 `forbidden_paths` 文件）

`git diff main --stat` 实测 P1 改动 **29 文件 / +4536 −48**。其中**有 4 个文件属于 MVP-01 的 `forbidden_paths`**，
原改进稿的「P1 已实现什么」表**漏列了它们**。经逐处核实，全部为 append-only 上线后的**必要连带改动**，现追认授权：

| 文件 | 改动 | 性质 | 授权依据 |
|---|---|---|---|
| `evolution_service.py` | +9 | **真 bug 修复**：`record()` 从 `get_page()` 派生 `revision = max+1` + `supersedes` | 不改则**第二次 `record()` 必崩**（`experience_sink` 的 dedup/recurrence 会重复调，见 §6.2） |
| `reader_service.py` | +2 | 构造 `WikiPage` 时补 `author=`（P1 把 `author` 改为必填） | 契约要求，不改则 `ValidationError` |
| `profile_service.py` | +1 | 同上 | 同上 |
| `search_service.py` | +1 | 同上 | 同上 |

**执行要求**：
1. **这 4 个文件从 MVP-01 的 `forbidden_paths` 中移除**，改列入**新增的 `frozen_paths`**（含义：P1 已改好，本包**不得再动**）；
2. 原因：原来的 `forbidden` 与「P1 已经改过」并存会让执行人困惑——到底是不能碰，还是已经碰过了？
3. `frozen_paths` 的语义：**可以读、可以跑测试，但不得修改**；确需修改必须回 owner 确认。

### 6.2 ⚠️ 实测发现：L-06 与 L-07 已各自独立修了同一个 bug

**这是本次审计的额外发现，会影响 R-006 的合并顺序判断。**

| 分支 | `evolution_service.record()` 的 `revision` 处理 |
|---|---|
| `owner/r006-l1-writer`（L-06 / P1） | ✅ **已有**：`existing = get_page(...)`; `revision = existing.revision + 1 if ... else 1` |
| `owner/r006-l2-stage`（L-07 / P2） | ✅ **已有**：`current = get_page(...)`; `next_revision = (current.revision if ... else 0) + 1` |

**两处修法等价**（都从 head 派生，都设 `supersedes`），变量命名不同但语义一致。

→ **含义**：R-007 文档里写的「L-07 依赖 L-06 的 `get_page()`」**在代码层面已不成立**（L-06 自己也修了）。
合并时**不必担心 L-07 带病**，但也意味着**两分支合到一起时 `evolution_service.py` 会真冲突**（同区域改动）。
这是正常的 stacked 合并冲突，**按 L-07 的版本保留即可**（它的注释更完整，写明了「为什么不能传常数」）。

### 6.3 P1 的测试文件（别删）

- `tests/test_r006_contracts.py` — **17 passed**
- `tests/test_r006_l1_writer.py` — **11 passed**

### 本包的增量工作（P1 未做或做错的部分）

| # | 增量 | 说明 |
|---|---|---|
| **1** | **修 N+1** | `list_pages` 现为 `for head in heads: store.get(...)`；实测 200 页 = **200 次 `get` / 60ms**（旧版 1 次 `list` / **0.71ms**）。**改法**：`RecordStore` 加一个 JOIN 查询方法（一条 SQL 取 head + version） |
| **2** | **桥接边白名单** | P1 保留了一刀切禁止（`knowledge.py:126` 的 `raise ValueError("cross-partition graph edges are not allowed")`，实测仍是原样）。**本包需实现 14 类白名单 + 3 类同类边** |
| **3** | **正向测试** | 补「白名单跨分区被允许」+「`get_page` 能解析裸 id」两条正向断言 |
| **4** | **`contracts.py` 的增量** | P1 的契约改动已经在了；本包**只按 §5-B2 的 A/B/C 判据新增**，不做重构 |

### 6.4 分支与文件边界（v3 修订）

```
branch: codex/m11-mvp-01
allowed_paths:
  src/autoresearch/knowledge.py
  src/autoresearch/storage.py
  src/autoresearch/contracts.py           # 条件允许：判据见 §5-B2（A/B/C 三选一）
  tests/test_knowledge_boundary.py        # 【待新建】
  tests/test_r006_contracts.py            # 承接 P1 的测试
  tests/test_governance_services.py       # 【v3 新增】拒绝侧既有断言在这（§5-M2）
  tests/fixtures/knowledge_boundary/      # 【待新建】
  docs/tasks/M11-knowledge-lane/
  .ai-team/tasks/M11-MVP-01.md            # 【待新建】账本，gate 必需
frozen_paths:                             # 只读不得改（P1 已改好，见 §6.1）
  src/autoresearch/evolution_service.py
  src/autoresearch/profile_service.py
  src/autoresearch/reader_service.py
  src/autoresearch/search_service.py
forbidden_paths:
  src/autoresearch/evidence.py
  src/autoresearch/gates.py
  .ai-team/TASK.md
  .project-to-act/
```

---

## 7. 开工步骤（v3 修订：修正三条不成立的 gate 命令）

### 7.0 前置：确认 §5-B1 已由 owner 裁决

**未裁决前不要开工**（见 §5-B1）。

### 7.1 建立 worktree

```bash
# 情况 A：你在 fork 里开发（成员 A 的情况）
git remote add upstream https://github.com/CovD831/AutoResearch.git   # 一次性
git fetch upstream
git switch -c codex/m11-mvp-01 upstream/owner/r006-l1-writer
git worktree add ../AutoResearch-m11 codex/m11-mvp-01

# 情况 B：主仓 clone（owner / 集成人）—— 且 §5-B1 已选「先合 P1」
git fetch origin
git switch -c codex/m11-mvp-01 origin/main
git worktree add ../AutoResearch-m11 codex/m11-mvp-01
```

### 7.2 基线核对（**必须先跑，数字不对就别开工**）

```bash
cd ../AutoResearch-m11
PYTHONPATH=src /Users/abab/.workbuddy/binaries/python/envs/default/bin/python \
  -m pytest -q -o addopts="" -W error
PYTHONPATH=src /Users/abab/.workbuddy/binaries/python/envs/default/bin/python -m ruff check src tests
PYTHONPATH=src /Users/abab/.workbuddy/binaries/python/envs/default/bin/python -m compileall -q src
```

**期望**：`537 passed / 2 skipped / 0 failed`（在 `9c60043` 上实测所得）。
**⚠️ 注意**：这个数字**只对 `9c60043` 成立**。若 §5-B1 选了「先合 P1」，合并后的 main 数字会变，
**必须在本 worktree 上重新实测，不得搬运本文档的数字**（本项目硬约束：基线不可跨 worktree 搬运）。

### 7.3 裸 id 读取点枚举（**开工第一步**，防漏网）

```bash
grep -rn '"wiki_page"' src/
```

**期望输出**（在 `9c60043` 上实测）—— 只应有以下**合法**读取点：

| 位置 | 性质 |
|---|---|
| `storage.py:179` | `store.list` 的 `kinds` 默认参数（不是裸 id 读取） |
| `contracts.py:140` | 枚举 `RecordKind.WIKI_PAGE = "wiki_page"`（常量定义） |
| `knowledge.py:56` | `add_page` 内 `_write_record` 的 kind（写入，非读取） |
| `knowledge.py:84` | `get_page()` 内按 **`current_revision_id`** 读（合法：已是版本 id） |
| `knowledge.py:111` | `list_pages()` 内同上（**本包要改成 JOIN**） |

**若出现任何 `store.get("wiki_page", <裸 page_id>)` → 说明有漏网，必须先修。**

### 7.4 门禁命令（v3 修正）

| 命令 | v2 写法的问题 | v3 修正 |
|---|---|---|
| **pytest** | 第 2、3 条漏了 `PYTHONPATH=src`；`python` 在沙箱指向 3.9.6 | 统一写全：`PYTHONPATH=src /Users/abab/.workbuddy/binaries/python/envs/default/bin/python -m pytest -q -o addopts="" -W error` |
| **ruff / compileall** | 同上 | 补 `PYTHONPATH=src` 与解释器全路径 |
| **`node .ai-team/check.mjs --base main`** | ⚠️ **实测在 main 上也是 `Result: blocked`**（缺成员账本），作为验收命令会永远红 | **改为 `--base <P1 的 sha>`**（即 `9c60043`）；**且必须先建 `.ai-team/tasks/M11-MVP-01.md` 账本**，否则该 gate 必然 blocked |
| **M11-MVP-03 的 `scripts/m11_fusion_comparison.py`** | 既是待建交付物又是验收命令，顺序说不通 | 拆成两步：**先实现脚本 → 再把它作为验收命令**。已在 MVP-03 包内注明 |

**关于 `check.mjs` 的正确理解**（**已在 `wt-l1-writer` 端到端实测**）：

| 命令 | 实测输出 | 原因 |
|---|---|---|
| `--base 9c60043`（P1 自身） | `Code progress from 9c60043: 0 commits, 0 files` → **`Result: valid`** | base 与 HEAD 无差异 |
| `--base main` | `Code progress from main: 2 commits, 29 files, +4536/-48` → **`Result: blocked`** | P1 改了 29 文件但**没有成员账本** |

**→ 该 gate 检查的是「改了代码就要同步更新账本」，不是代码正确性。**
`--base main` 之所以 blocked，是因为 **P1 本身缺 `.ai-team/tasks/` 下的账本**，不是因为 M11 做错了什么。

**✅ 已修复**：本版已为 P1 补建 `.ai-team/tasks/R006-L1-WRITER.md`（在 `wt-l1-writer` 上），
补建后同一命令实测转 **`Result: valid`**（`2 commits, 30 files`）。全量回归仍 **537 passed / 2 skipped**。

> **为什么这必须修**：P1 分支自身带着这个 gate 缺陷。若 §5-B1 选「先合 P1」，
> 不补账本则合并进 main 后该 gate 在新的 base 上仍会 blocked —— 且**看起来像 M11 的问题**。
>
> **教训**：`check.mjs --base main` 返回 blocked 时，**先确认是哪个文件缺账本，不要默认是自己改坏了**。
> 实测定位方式：比较 `--base <自身 sha>`（应为 valid）与 `--base main` 的输出差异。

### 7.5 开工

读本文件 **M11-MVP-01** 一节 → 按 `tasks/M11-MVP-01/task-package.json` 的 `allowed_paths` / `frozen_paths` / `forbidden_paths` 动手。

---

## M11-MVP-02 — 候选召回管线

- **状态**：`planned`
- **对应原文**：M11-05
- **目标**：在现有分区化检索基础上增加向量召回，形成可解释、可过滤的 MVP 检索候选管线。
- **依赖**：M11-MVP-01

### 主要交付

- 词法召回（**升级为 FTS/BM25**，替换现有朴素子串）
- 向量召回
- 同分区图扩展（保留既有语义）
- Evidence 过滤
- **`RecallAuditRecord`（L8 召回审计）** ← 注入自 R-006 C8
- `RetrievalHit` 兼容

### 必须满足

1. **检索候选先经过 `project_id`、`partition` 和可用性边界过滤（L0）。**
2. **词法和向量召回都遵守同一分区边界。**
3. **`require_evidence=True` 时，任何没有 `evidence_ids` 的页面都不得进入结果**（两路都要过滤）。
4. **保留现有同分区图扩展语义。**
5. **每个结果保留 `record_id`、`partition`、`evidence_ids`、`retrieval_level`。**
6. **检索层只负责召回和排序，不判断内容真实性。**
7. **每次 `retrieve` 必须写一条 `RecallAuditRecord`**（可配置关闭，默认开）。
   - 字段：`audit_id`、`project_id`、`query`、`filters`、`candidates`、`deduped`、`reranked`、`final_hits`、`stage_timings_ms`、`created_at`
   - **不变量（可机械校验）**：`final_hits ⊆ reranked ⊆ deduped ⊆ candidates`（集合包含链）
8. **降级路径必须显式记录**：向量能力不可用时回退词法，并在结果中**明确标注降级状态**（`retrieval_level` 反映实际走的路）。

### 禁止

- 改变 `KnowledgeService.retrieve()` 的输入签名；
- 改变 `RetrievalHit` 的对外字段（可新增，不可删除/改名）；
- 跨分区合并无类型结果；
- 在检索层直接生成 `EvidenceItem`、`GateDecision` 或真实性结论；
- **把降级结果伪装成向量检索成功**。

### 验收

| 类型 | 项 |
|---|---|
| 正例 | 固定 fixture 中词法和向量两路均能产生**可追踪排序** |
| 正例 | `RecallAuditRecord` 的**集合包含链**成立（`final ⊆ reranked ⊆ deduped ⊆ candidates`） |
| 负例 | `require_evidence` 过滤**同时作用于两路**结果 |
| 负例 | 跨分区页面不会混入 |
| 负例 | 向量不可用时回退词法，且**结果中降级状态可见** |
| 一致性 | 相同输入和相同索引状态得到一致结果 |

### MVP 边界

只完成候选召回管线。不实现复杂 rerank、ContextPack 和真实领域质量结论。

### 分支与文件边界

```
branch: codex/m11-mvp-02
allowed_paths:
  src/autoresearch/knowledge_retrieval.py      # 新建
  src/autoresearch/recall_audit.py             # 新建
  src/autoresearch/knowledge.py                # 仅 retrieve() 内部
  tests/test_knowledge_retrieval.py            # 新建
  tests/fixtures/knowledge_retrieval/
  docs/tasks/M11-knowledge-lane/
  .ai-team/tasks/M11-MVP-02.md
forbidden_paths:
  src/autoresearch/contracts.py
  src/autoresearch/evidence.py
  src/autoresearch/gates.py
  src/autoresearch/storage.py
  .ai-team/TASK.md
  .project-to-act/
```

---

## M11-MVP-03 — 融合、去重和索引维护

- **状态**：`planned`
- **对应原文**：M11-07
- **目标**：完成多路结果的确定性融合、去重和派生索引维护。
- **依赖**：M11-MVP-02

### 主要交付

- 融合排序（算法**由证据决定**，见验收）
- 镜像去重
- 索引构建、增量同步、索引重建
- 版本追踪和降级路径
- **`RetrievalHit.score_breakdown` / `channel` / `matched_stage`** ← 注入自 R-006 C7

### 必须满足

1. **词法排序和向量排序使用确定性融合规则。**
2. **同一个 WikiPage 不得因多个镜像重复计权。**
3. **融合结果可以区分词法、向量和图扩展来源**（`channel` ∈ `{LEXICAL, VECTOR, GRAPH, FUSED}`）。
4. **`channel=FUSED` 时必须有 `score_breakdown`**（否则无法追溯融合来源）。
5. **向量索引只能由 WikiPage 规范内容派生。**
6. **WikiPage 新增或新 revision 产生后索引可以增量同步。**
7. **索引损坏或版本变化后可以从 WikiPage 重新构建。**
8. **向量能力不可用时回退词法检索，并明确记录降级状态。**

### 禁止

- 把向量索引作为规范数据源；
- 直接修改 WikiPage 的事实内容；
- 通过外部付费或网络服务完成必要检索；
- **让降级结果伪装成向量检索成功**；
- **默认上 RRF 而不给对比证据**（见验收）。

### 验收

| 类型 | 项 |
|---|---|
| 正例 | 相同两路输入得到**稳定一致的融合排序** |
| 正例 | 重复镜像**不会重复增加分数** |
| 正例 | 新增 WikiPage 后可以被检索 |
| 正例 | 从规范 WikiPage 重建索引后结果一致 |
| 正例 | 索引版本变化可以被识别 |
| 正例 | 向量能力不可用时词法回退**可重复验证** |
| **决策证据** | **必须产出「纯词法 vs 混合检索」的对比报告**，并据此决定融合策略 |

> ⚠️ **关于 RRF 的硬要求**：本包的分区（`experiences` / `knowledge` / `profiles`）**属于小语料**（几十~几百条）。
> 调研实证：**小语料两路信号高度相关时，RRF 不增值甚至为负**。
> **因此本包不得默认采用 RRF** —— 必须给出「RRF vs 简单加权融合 vs 字段过滤」的对比证据，由证据决定分层策略。
> （大语料走 RRF、小语料走加权/字段过滤，是**待验证的假设**，不是结论。）

### MVP 边界

不实现生产级 pgvector、复杂 reranker、跨项目质量评测和自动策略变更。

### 分支与文件边界

```
branch: codex/m11-mvp-03
allowed_paths:
  src/autoresearch/knowledge_fusion.py         # 新建
  src/autoresearch/knowledge_index.py          # 新建
  src/autoresearch/knowledge.py                # 仅 retrieve() 内部
  tests/test_knowledge_fusion.py               # 新建
  tests/fixtures/knowledge_fusion/
  scripts/m11_fusion_comparison.py             # 新建（对比报告生成器）
  docs/tasks/M11-knowledge-lane/
  .ai-team/tasks/M11-MVP-03.md
forbidden_paths:
  src/autoresearch/contracts.py
  src/autoresearch/evidence.py
  src/autoresearch/storage.py
  .ai-team/TASK.md
  .project-to-act/
```

---

## M11-MVP-04 — 固定回归与验收证据

- **状态**：`planned`
- **对应原文**：M11-08
- **目标**：建立最小固定语料和回归证据，验证检索变化没有破坏分区、Evidence 和结果追踪语义。
- **依赖**：M11-MVP-03

> **本包为 A7 的独立验收包。** 原拆分写得好，本改进稿**基本保留原样**，只补两处。

### 主要交付

- 固定 fixture 语料
- 固定查询
- 相关页面标注
- 词法与混合检索对比
- 遗漏分类
- 检索审计记录

### 必须满足

1. **每个查询都有固定的预期相关页面。**
2. **测试可以比较纯词法和混合检索结果。**
3. **报告记录命中、漏召回、跨分区污染、Evidence 缺失和重复计权。**
4. **结果保留查询、过滤条件、候选和最终排序。**
5. **相同代码、语料和索引状态可以重复得到相同报告。**

### 禁止

- 用 fixture 结果宣称真实论文领域质量达标；
- 用排序变化直接推断内容真实性；
- 把未测得的真实 Recall、MRR 或 nDCG 写成已达标；
- 跳过失败、遗漏和降级结果；
- **（新增）把 `RecallAuditRecord` 的集合包含链当作召回质量证据** —— 它只证明审计记录自洽，不证明召回正确。

### 验收

| 类型 | 项 |
|---|---|
| 正例 | 固定查询可以重复执行 |
| 正例 | 纯词法与混合检索差异可被记录 |
| 正例 | 索引或模型变化能够触发回归报告 |
| 负例 | 关键负例可以稳定复现 |
| 诚实性 | 报告**明确区分**已验证项、未验证项和后续任务 |

### MVP 边界

只建立最小离线回归证据。真实领域 gold set、人工盲审和生产质量目标延期处理。

### 分支与文件边界

```
branch: codex/m11-mvp-04
allowed_paths:
  tests/test_m11_regression.py                 # 新建
  tests/fixtures/m11_regression/               # 新建
  scripts/m11_regression_report.py             # 新建
  docs/tasks/M11-knowledge-lane/
  .ai-team/tasks/M11-MVP-04.md
forbidden_paths:
  src/autoresearch/                            # 本包只加测试与 fixture，不改实现
  .ai-team/TASK.md
  .project-to-act/
```

---

## 2. 任务关系

```
MVP-01（规范来源与边界）
   ↓
MVP-02（候选召回：词法 + 向量 + 图）
   ↓
MVP-03（融合、去重、索引维护）
   ↓
MVP-04（固定回归与验收证据）← A7 的独立验收包
```

- 所有包均**不改变** Evidence Module、Gate 和 Experience 的职责。
- 每个包的代码、测试、fixture、任务账本、验收证据和 rollback 说明必须在**同一交付快照**中保持一致。
- **MVP-01 是硬前置**（其余三包都依赖它的边界）。

---

## 3. 改动对照（相比成员原稿）

| # | 项 | 原稿 | 改进 | 理由 |
|---|---|---|---|---|
| **1** | revision 不可覆盖的实现 | 只写验收，未说怎么实现 | **补 append-only 写入者 + head 索引 + `get_page`/`list_pages`** | 底层 `ON CONFLICT DO UPDATE` 不换写入者就做不到；**R-006 P1 已实现，直接承接** |
| **2** | 跨分区边 | 一刀切禁止 | **14 类白名单 + 3 类同类边** | 原设计 §12.3 的 16 类边中 ≥11 类必然跨分区；一刀切会让图不成立 |
| **3** | 正向测试 | 只有拒绝侧 | **补「白名单跨分区被允许」+「`get_page` 解析裸 id」** | 收窄语义后必须有正向断言，否则新行为无人校验 |
| **4** | N+1 | 未提及 | **新增硬条款：`list_pages` 必须 O(1) 查询数** | 实测退化：200 页 60ms vs 0.71ms |
| **5** | Evidence 独立存储 | 「独立 RecordStore」 | **改为「独立 `kind`」** | 实测是同一个 `RecordStore`，靠 `kind` 区分 |
| **6** | L8 召回审计 | 只在 MVP-04 提"审计记录" | **提到 MVP-02 作为契约 + 集合包含链不变量** | 可机械校验，且是 MVP-03/04 的输入 |
| **7** | RRF | 默认使用 | **改为「由对比证据决定」** | 小语料上 RRF 不增值甚至为负（有实证） |
| **8** | `score_breakdown` | 未提 | **MVP-03 补 `score_breakdown`/`channel`/`matched_stage`** | 融合来源可追溯；`channel=FUSED` 时必须给 |
| **9** | `Statement` | 未提 | **MVP-01 的 MVP 边界明确「不实现」** | 无消费方，避免过度设计 |
| **10** | 任务包机器可读 | 只有 md | **补 `task-package.json`（`allowed_paths`/`forbidden_paths`）** | 把文件边界从口头约定变成机器可查 |

## 3b. v3 改动对照（相比 v2，就绪性修订）

v2 的 10 处改动**全部保留**。下表是 v3 新增的 8 处，全部来自 2026-09-15 的就绪性审计：

| # | 项 | v2 | v3 | 理由 |
|---|---|---|---|---|
| **11** | `contracts.py` 归属 | `task-package.json` 允许 vs `lane-manifest.json` 禁止，**自相矛盾** | **统一为「条件允许」+ A/B/C 判据**（§5-B2） | 未决问题不该写进 `ready` 的包；全禁会让 MVP-03 的 `score_breakdown` 无处落地 |
| **12** | 4 个服务文件的边界 | 列在 `forbidden_paths`，**但 P1 已经改过** | **改列 `frozen_paths`**（只读不得改）+ 逐处说明授权（§6.1） | 「禁止」与「已改过」并存会让执行人困惑；且原稿**漏列**了这 4 处改动 |
| **13** | 拒绝侧测试的位置 | 只说「既有测试只覆盖拒绝侧」，**没说在哪** | 点名 `tests/test_governance_services.py:114` + **加入 allowed_paths** | 执行人按原 allowed_paths 动手**永远碰不到它**，改了语义却看不到有测试在断言 |
| **14** | `base_ref` | 四包全写 `04ce9a9`（= main） | 改 `9c60043`（P1 实际所在）+ 注明待 §5-B1 统一更新 | `04ce9a9` 上**没有 P1 的代码**，基线指向错误 |
| **15** | gate 命令 | `python -m pytest`（沙箱指向 3.9.6、缺 `PYTHONPATH`）；`check.mjs --base main`（**在 main 上也 blocked**） | 补解释器全路径 + `PYTHONPATH=src`；`--base` 改传 P1 的 sha（§7.4） | 原命令**跑不过或永远红**，作为验收命令会误导 |
| **16** | 待新建交付物 | 与已存在文件混在 `allowed_paths` 数组里 | 标 `CONSTRUCTED:` + 账本提到开工步骤（§7.5） | `.ai-team/tasks/M11-MVP-01.md` 是 gate 必需项，埋在数组里会导致 gate 必然 blocked |
| **17** | 状态枚举 | 各包 `ready`/`planned` 混用，未对齐 `check.mjs` | 与 `.ai-team/check.mjs` 的 `VALID_STATES` 对齐 | 该 gate 会校验状态字面量 |
| **18** | 开工前置 | 无 | **新增 §5-B1**：P1 未合并 main 且无 PR，base 取舍未定 | 未定则产出可能合不回 main —— 这是**唯一无法由本文件自行解决的阻塞项** |

> **v3 的 8 处改动里，7 处可由本文件自行裁决，1 处（#18）必须由 owner 决定。**
> 原判「不能开工」的两个阻塞项中，B2（#11）已解决；B1（#18）仍待裁决。

## 4. 未采纳的建议（留痕，防重复提出）

| 项 | 为什么未采纳 |
|---|---|
| R-006 C2 `Statement` | 无消费方；等 M02-09 失效传播真需要 statement 级绑定再补 |
| R-006 C9 `ExperienceInjection` | 属回流层（M12），不属 M11 |
| R-006 的 7 包切分（P1–P7） | 成员的 4 包更紧凑，且每包带 MVP 边界 |
| R-006 的分层融合作为**结论** | 它只是**假设**（小语料 RRF 不增值有实证，但"该用加权"未被验证）→ 改为**要求对比证据** |
