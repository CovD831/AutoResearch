# A7 / S4-A3 Knowledge Vector — 范围界定（owner 裁决 2026-09-14）

> 本文档的目的是**防止范围混淆**。它记录了一次真实发生的误判，以及裁决结果。

---

## 0. 裁决（老板 2026-09-14）

| 问题 | 裁决 |
|---|---|
| A7 的模块归属 | **`knowledge` 模块** —— 它是**经验沉淀模块**，不是论文检索模块 |
| A7 检索什么 | **只做内部知识库检索**（`knowledge.retrieve`） |
| `papers` 分区 | **不纳入向量化** |
| 论文检索 | **全部交给外部模块**（或由检索论文的 Agent 调用）。本模块**不碰论文检索** |

---

## 1. 被澄清的混淆（真实发生过）

系统里有**两个名字都叫「检索」的东西**，它们目标不同、不得混为一谈：

| | **外部论文检索** | **内部知识库检索**（A7 的范围） |
|---|---|---|
| 模块 | `search_service.py` / `search_adapters.py` | **`knowledge.py`** |
| 查什么 | **外部学术数据库**（Semantic Scholar / arXiv / OpenAlex） | **本地 Wiki 页**（`store.list("wiki_page")`） |
| 关键参数 | `query` / `per_connector_limit` | `partitions` / `level` / `require_evidence` |
| 调用方 | `PaperSearchAgent` → `search_port` → A4 adapter | CLI `search` / API `/search` |
| 产出 | `PaperRecord` + E1 证据 | `RetrievalHit` |
| 是否本包范围 | **否** | **是** |

**owner 侧曾用 `search_service` 的探针数据去论证 A7 的价值 —— 那是用错了模块。** 相关探针结论作废，不得作为 A7 的验收证据。

---

## 2. 五个分区的画像与归属

| 分区 | 写入方 | 内容性质 | A7 是否向量化 |
|---|---|---|---|
| `papers` | `search_service.py` / `reader_service.py` | 论文书目 + 摘要 | **否**（裁决：论文检索归外部模块） |
| `experiences` | `evolution_service.py` | **经验沉淀** | **是**（本模块的核心目标） |
| `knowledge` | `reader_service.py` | 挖掘出的知识 | **是** |
| `profiles` | `profile_service.py` | 用户画像 | **是** |
| `projects` | （当前无写入方） | 空 | 无需（保持接口一致） |

> `experiences` 由 `evolution_service` 写入，与 A6（经验沉淀接线）同域 —— 这正是 A7 规格中「依赖 A6，同属**孤儿模块域**」的含义。

---

## 3. 对 A7 设计的直接影响

1. **向量索引的构建范围**：只对非 `papers` 分区的 Wiki 页建索引。`papers` 页即使存在也不进入向量路。
2. **`partitions` 参数语义不变**：调用方仍可传任意 `KnowledgePartition`。若传入 `papers`，该分区**只走词法路**（无向量路），并在 `retrieval_level` 中如实标注。
3. **不得新增外部调用**：A7 不引入任何外部检索依赖（规格「禁止引入付费/网络 embedding API」同向）。
4. **报告口径**：召回对比报告必须**按分区**给出，`papers` 分区应显示为"仅词法"。

---

## 4. 待确认项（留给实现阶段）

- 传入 `papers` 分区时的 `retrieval_level` 标签具体怎么写（如 `lexical` vs `lexical+vector`），需与既有测试契约对齐。
- 若未来需要"已入库论文的语义检索"，那属于**另一个包**（且需先论证与外部检索的职责边界），不在 A7 内。
