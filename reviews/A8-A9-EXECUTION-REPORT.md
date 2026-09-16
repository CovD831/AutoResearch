# A8 + A9 执行完成报告

**日期**：2026-09-14
**分支**：`owner/a8-mainline-adapter`（3 个提交，**未推送**，等老板许可）
**基线**：`main @ 04ce9a9`
**状态**：两个包均已完成并本地提交，四门禁全绿

---

## 一句话结论

按老板裁决串行执行完毕：**A8 把主链路检索切到 A5 真实 adapter**，**A9 把交接单从"内容承载"改回"引用名单"**。两者共 3 个提交，`04ce9a9` 的 509 passed → **532 passed / 2 skipped / 0 error**，零回归；判别力均为**判据型**失败（A8 2 条、A9 4 条）。

---

## 提交清单

| commit | 内容 |
|---|---|
| `386e7f8` | A8：主链路切 A5 真实 adapter（`retrieve()` 原语 + `AdapterBackedPaperSearchService` + 装配切换） |
| `7b15997` | A8：补齐 PR contract 要求的 ledger 章节 |
| `b7635d7` | A9：交接单改为引用名单（契约语义重定义 + 生产者只传 id + 截断告警） |

改动面：17 文件 / +1670 −26。

---

## A8 / S4-A4：主链路切 A5 adapter

### 设计决策（三条关键）

1. **新增公开原语 `retrieve()`，不让主链路走候选通道。**
   实测 `capability_registry.py:645-648` 会把 `CANDIDATE_ONLY` 注册的 `value` **强制清空**（有意设计），且 `_candidate()` 只带 `abstract_present` 布尔。而 `reader_service.py:69-71` 在无 abstract 时**降级到只读标题**。若走候选路径，44 篇论文会全部退化成"只有标题"——正是本项目反复出现的「退化路径把缺失记成正常值」缺陷族。限流计数一并下沉到 `retrieve()`，两路共享一个监控面。

2. **不删 `search_service.py`。**
   全仓引用面核实：`capability.py`、`application.py`、`agents/paper_search.py`、以及 **A1/A2 recovery contract 测试直接构造它**。删除会破坏既有基线。

3. **`PaperSearchCapabilityAdapter`（A4 幂等/replay/recovery 边界）原样保留。**
   它只依赖 `PaperSearchServicePort` 这个 Protocol，换实现无需改动。端到端测试**实测断言 replay 不重复取数**，证明边界仍在工作。

### 验证

| 项 | 结果 |
|---|---|
| 基线（本 worktree 实测，不跨树搬运） | 509 passed / 2 skipped / 0 error |
| 本包 | **525 passed / 2 skipped / 0 error**（+16） |
| 判别力（新模块在、装配保持基线） | **2 failed，判据型** |
| ruff / compileall / check.mjs | 全绿 |

---

## A9 / S4-A5：交接单改为引用名单

### 缺陷现场

真实运行检索回 44 篇 → `paper_reader` 铺 41 张阅读卡 refs + 164 证据号 → **pydantic 直接拒绝，程序崩**。

**同族枚举结果**（纪律要求）：全仓四个 `artifact_refs` 生产者中，`paper_reader.py:84`（无截断，爆炸点）与 `paper_search.py:86`（硬编码 `[:20]`）会随规模增长；`orchestrator.py:185` 与 `writer.py:76` 是固定单条，无风险。

### 设计决策

**关键实测发现：没有任何消费方读取 `artifact_refs` / `evidence_ids` 的内容。** `handoffs.py` 完全不碰；四个 agent 只生产；`readiness.py:71` 只判空。→ **"只传引用"不是能力降级，而是让实现追上它本来的语义。**

1. 契约语义重定义：`artifact_refs` 20→**500**、`evidence_ids` 100→**2000**，**仍有限**（放宽 ≠ 无界），docstring 写明"这是引用界，不是内容界"。
2. `paper_reader`：refs 只传 `artifact_id` + `kind`，不嵌 `findings[0][:300]`。
3. `paper_search`：硬编码 `[:20]` → `HANDOFF_REF_LIMIT = 50`，截断**写 diagnostics + `refs_attached`**（静默丢弃等于 fail-open）。
4. **顺手修掉一个同族缺陷**：`summary=paper.title` 但 `ArtifactRef.summary` 上限 500 而 `PaperRecord.title` 无长度限制——超长标题会毫无理由地拒掉信封。

### 验证

| 项 | 结果 |
|---|---|
| 基线 = A8 提交 `7b15997` | 525 passed |
| 本包 | **532 passed / 2 skipped / 0 error**（+7） |
| 判别力 | **4 failed，全部判据型**（41/164 被拒、上限不足、reader 仍嵌正文、截断静默） |
| ruff / compileall / check.mjs / check_pr_contract | 全绿（17 paths / 2 ledgers） |

---

## 自审抓到并在本包内修掉的问题（5 条）

| # | 问题 | 性质 |
|---|---|---|
| 1 | **第一版判别力验证是假绿（12 passed）**：测试全部直接构造新服务，从不经过 `application.py`，"装配未切"完全测不出 | 与 R2 同型——**有覆盖 ≠ 有判据** |
| 2 | **端到端测试第一版依赖真实网络**：只替换了一个 adapter，arxiv/openalex 仍带真 transport，实测访问了 live provider（17.3s、返回 5 篇真实论文） | 依赖网络的测试在 CI 里不是证据 |
| 3 | **query → `invocation_id` 派生有碰撞**：`"a b"` 与 `"a-b"` 折叠成同一串，会让 A4 账本把一个 query 重放成另一个 | 改用 slug + sha256 前缀 |
| 4 | 测试混入空洞断言与死代码（`assert not any(... if False)`、未使用的变量） | 已删除/改为可证伪 |
| 5 | `pytest.raises(Exception)` 盲捕获 | ruff 抓到，改为精确异常类型 |

---

## 未闭合（如实记录）

- **A9 最弱一环**：交接单"不得嵌内容"**无静态强制手段**，只有测试与约定。未来若有人再嵌正文，仅靠 2 条测试拦截。
- **跨进程并发未测**（沿用 A5/O12 挂账口径）。
- **真实网络端到端需本机 `SEMANTIC_SCHOLAR_API_KEY`**；本次全部证据来自注入 transport 的离线矩阵。（附带一个有价值的观察：A8 端到端测试第一版意外跑到真实网络时**成功检索并落库了论文**，说明链路在真实网络下是通的。）
- 引用界 500/2000 的依据是单次真实检索量级（44 篇 / 41 卡 / 164 证据号），更大规模需重新评估。

---

## 下一步

1. **等老板许可后推分支并开 PR**（走 `github-protection-window` 合并）。
2. 合并后 A 线下一包按原计划为 **A7**（knowledge 向量检索）。
3. 账本已同步：`D-A5-偏离-1` 从「待裁决」改为「已裁决 → 已解决 (a)」；`TASK-QUEUE.md` 增 A8/A9 两行；`TASK-PACKAGE-REGISTRY.md` 登记两包。
