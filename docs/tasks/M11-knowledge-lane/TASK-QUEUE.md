# M11 知识库 lane — 任务队列

> **v4（2026-09-15 14:50）**：R-006 P1 已并入 main（`f31d0dc`），**阻塞解除，MVP-01 可开工**。
> **v3（2026-09-15 14:30）**：状态枚举与 `.ai-team/check.mjs` 的 `VALID_STATES` 对齐；补齐就绪性修订（详见 `TASK-SPECS.md` §5–§7）。

| Task | 状态 | 依赖 | 交付重点 |
|---|---|---|---|
| M11-MVP-01 Wiki+Graph 规范来源与边界 | **ready** ✅ 可开工 | — （P1 已并入 main） | append-only revision、head 索引、受管桥接边、N+1 修复 |
| M11-MVP-02 候选召回管线 | planned | MVP-01 | 词法 FTS + 向量 + 图扩展、L0 过滤、L8 召回审计 |
| M11-MVP-03 融合、去重、索引维护 | planned | MVP-02 | 确定性融合、镜像去重、索引重建、融合对比证据 |
| M11-MVP-04 固定回归与验收证据 | planned | MVP-03 | fixture 语料、词法 vs 混合对比、遗漏分类 |

**`base_ref` = `main`（语义引用，不写死 sha）**。四包均从 `origin/main` 切分支。
> 不写死 sha 的原因：为修正该字段而提交会让 HEAD 再变一次（自指循环），字面 sha 永远落后一步。

## 状态定义

- `ready`：依赖满足，可以创建 worktree 开工。
- `planned`：依赖未满足，不可开工。
- 每个任务独立 PR；本表只描述顺序，不替代 `TASK-SPECS.md` 的详细验收。

## 与 R-006 的关系

R-006 的 P2–P7 已暂停，不再作为本 lane 的验收依据。
R-006 P1 的成果（append-only 写入者 + head 索引，实测 537 passed）**已由 owner 合并进 main**
（`04ce9a9` → `ea1663b` → `f31d0dc` → `49fcffb`，经保护窗口，恢复后 12/12 项核对一致）。
**M11-MVP-01 承接它，不重复实现。**

## 三个必须注意的坑（每个都有实测依据）

1. **`list_pages` 的 N+1**：R-006 P1 现为 `for head in heads: store.get(...)`，实测 200 页 = **200 次 get / 60ms**
   （旧版 1 次 list / **0.71ms**）。**MVP-01 必须修**。
2. **裸 `page_id` 查不到**：head 索引后 `store.get("wiki_page", 裸id)` 返回 `None`。
   **所有裸 id 读取必须走 `get_page()`**，包括 `add_edge` 与 `retrieve` 图扩展。
   → 开工第一步先跑 `TASK-SPECS.md` §7.3 的枚举命令确认没有漏网。
3. **正向测试缺失**：既有测试只覆盖「跨分区边被拒绝」。收窄为白名单后，**必须补「白名单类型跨分区被允许」的正向断言**。
   → 拒绝侧既有断言在 **`tests/test_governance_services.py:114`**（不在原 allowed_paths，v3 已补入）。

## v3 新增注意项

4. **`contracts.py` 是「条件允许」**：MVP-01 可改，但每个 hunk 必须命中 `TASK-SPECS.md` §5-B2 的 A/B/C 之一，
   并在 PR 描述里逐条列出。禁止删改 `RetrievalHit` 既有对外字段、禁止动 C2/C9。
5. **4 个服务文件已 frozen**：`evolution_service.py` / `profile_service.py` / `reader_service.py` / `search_service.py`
   —— P1 已经改过（见 `TASK-SPECS.md` §6.1），**本 lane 只读不得改**。
6. **基线数字不可搬运**：`537 passed` 只对 `9c60043` 成立。若选择「先合 P1」，合并后的 main 数字会变，
   必须在自己的 worktree 重新实测。
