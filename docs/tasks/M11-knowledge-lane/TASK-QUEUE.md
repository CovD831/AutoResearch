# M11 知识库 lane — 任务队列

| Task | 状态 | 依赖 | 交付重点 |
|---|---|---|---|
| M11-MVP-01 Wiki+Graph 规范来源与边界 | **ready** | — （承接 R-006 P1） | append-only revision、head 索引、受管桥接边、N+1 修复 |
| M11-MVP-02 候选召回管线 | planned | MVP-01 | 词法 FTS + 向量 + 图扩展、L0 过滤、L8 召回审计 |
| M11-MVP-03 融合、去重、索引维护 | planned | MVP-02 | 确定性融合、镜像去重、索引重建、融合对比证据 |
| M11-MVP-04 固定回归与验收证据 | planned | MVP-03 | fixture 语料、词法 vs 混合对比、遗漏分类 |

## 状态定义

- `ready`：依赖满足，可以创建 worktree 开工。
- `planned`：依赖未满足，不可开工。
- 每个任务独立 PR；本表只描述顺序，不替代 `TASK-SPECS.md` 的详细验收。

## 与 R-006 的关系

R-006 的 P2–P7 已暂停，不再作为本 lane 的验收依据。
R-006 P1 的成果（append-only 写入者 + head 索引，实测 537 passed）由 **M11-MVP-01 承接**，不重复实现。

## 三个必须注意的坑（每个都有实测依据）

1. **`list_pages` 的 N+1**：R-006 P1 现为 `for head in heads: store.get(...)`，实测 200 页 = 200 次 get / 118ms（旧版 1 次 list / 1.03ms）。**MVP-01 必须修**。
2. **裸 `page_id` 查不到**：head 索引后 `store.get("wiki_page", 裸id)` 返回 `None`。**所有裸 id 读取必须走 `get_page()`**，包括 `add_edge` 与 `retrieve` 图扩展。
3. **正向测试缺失**：既有测试只覆盖「跨分区边被拒绝」。收窄为白名单后，**必须补「白名单类型跨分区被允许」的正向断言**。
