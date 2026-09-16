# A7 书目写入的标识确定性与幂等

- ID: `A7-BIBLIOGRAPHIC-IDENTITY`
- Title: `A7 bibliographic identity is deterministic and the write is idempotent`
- Status: `submitted`
- Owner: `port-implementer-1`
- Next owner: `team-lead`

## Goal

修掉检索路径落库的标识不确定性：同一篇论文连续检索会产生多个重复的 wiki 页与 evidence。
根因是 `_to_record` 不传 `paper_id`，落到随机的 `new_id("paper")` 默认值。
按 owner 裁定的 **D1 = 幂等跳过**：同一篇已存在则不再写入（不写新 revision）。
第二轮按独立盲审 + owner 复核的 7 条缺口（①-⑦）逐条加固：并发临界区、legacy 路径、seed 路径、
自愈回填、失效证据抑制、冗余判定收敛、标题碰撞挂账。

## Acceptance scenarios

- [x] ① 同一 DOI 连跑 3 次 search → wiki 页 1（当前 3）、evidence 1（当前 3）、paper 1。
- [x] ② 不同 DOI 各自独立落库（实测 2 papers / 2 pages / 2 evidence）。
- [x] ②b 同一 DOI 在两个 project 各自独立落库（标识含 project，store 主键全局）。
- [x] ③ 全量测试不回归：基线 587 passed / 2 skipped → 596 passed / 2 skipped（+9 测试）。
- [x] ④ 判别力实测：回退修复 → 新测试变红且为判据型（第一轮 3 变体 + 第二轮 5 缺口）。
- [x] ⑤ ruff / compileall 干净（`All checks passed!` / exit 0）。
- [x] ⑥ 台账 9 节齐、元数据格式合法（`check.mjs --task` valid）。
- [x] ⑦ 审计①并发竞态：检查与写入收敛到同一临界区（2 线程 × 20 轮 20/20 clean）。
- [x] ⑦ 审计②legacy 路径派生标识；③seed 路径派生标识（显式 id 保留）。
- [x] ⑦ 审计④页存在而 evidence 缺失时以新 revision 回填引用，不留孤儿。
- [x] ⑦ 审计⑤失效 evidence 不再抑制重铸，也不再被当作当前记录返回。

## Invariants

- 同一 `(project, 书目键)` → 同一 `paper_id`，跨调用稳定，不引入新随机源。
- 同一 `(project, 书目键)` 的 paper / **有效** evidence / wiki 页各至多 1 份。
- 存在性检查与写入必须在同一临界区内（否则双写 evidence 或撞 append-only 崩溃）。
- 失效 evidence 不算「已落库」；页在而有效 evidence 缺失时必须回填引用，`evidence_ids` 不得悬空。
- 不同 project 的同一书目键互不影响。
- adapter / legacy / seed 三条入口共用同一标识派生实现（结构性一致）。
- `_persist(self, paper)` 签名不变（A2 崩溃注入依赖它）。
- 不改 `contracts.py` / `storage.py` / `evidence.py` / `knowledge.py`。

## Decisions

- **D1 幂等跳过**（owner 裁定）：检索路径只落库；完全落库时零写入，不写新 revision。
- **D2 不统一 `author` / `actor`**（owner 裁定）：`author`=模块名（`"search_service"`），
  `actor`=调用方标签；加测试钉住，防后人误修。
- **D3 标识含 `project_id`**（我提出，偏离规格文字，待背书）：store 主键 `(kind, record_id)`
  不含 project，`get_page` 走全局键；只用 `_dedupe_key` 会跨项目污染（CF-G 判据型失败）。
- **D4 自愈 + 新 revision 回填**：只补缺失的一半；页侧 append-only，只能以 `revision+1` 回填。
- **D5 保留「完全落库 → 提前返回」（与审计⑥ 指示相反，待裁定）**：实测删掉后重检索会改写
  已落库记录的 `retrieved_at`（False→True），使重检索非零写入，与 D1 逐字冲突。
- **D6 显式 id 优先于派生**：用户 seed / provider 自带 id 时保留，仅无显式 id 时派生。

## Completed

- `src/autoresearch/search_service.py`：新增 `bibliographic_paper_id`、`_identity_normalized`
  （`model_fields_set` 区分显式/默认 id）、`_persisted_bibliographic_evidence`（`valid_only=True`）；
  改写 `persist_bibliographic_record`：单一临界区（`store.transaction()`）+ 幂等短路 + 半写自愈
  + 新 revision 回填；`import hashlib`。
- `src/autoresearch/adapter_search_service.py`：`_to_record` **不再**派生 `paper_id`（收敛到唯一
  choke point），docstring 指明落点；移除 `bibliographic_paper_id` 导入。
- `tests/test_adapter_search_service.py`：+9 测试（幂等、独立落库、跨项目隔离、D2 钉子、
  并发竞态、legacy 幂等、seed 幂等 + 显式 id、回填、失效重铸）。
- `docs/tasks/P1-A-runtime-lane/tasks/A7-bibliographic-identity/L3.md`：L3 文档（两轮）。
- 本台账。

## Pending

- **已在 commit `8500bd3` 落盘**；PR 契约门禁补跑 `valid / 5 changed paths; 1 task ledger(s)`。
- **待合并**：本分支基于 PR #23 的 head（`9510ac4`），须待 PR #23 合入 main 后再生效；
  否则本分支的基线悬空。**这是唯一的合并前置条件。**
- **已裁定（owner）**：
  - **D3** 标识含 `project_id` —— **背书**。硬依据：`storage.py` 主键 `PRIMARY KEY (kind, record_id)`
    不含 project，`get_page` 走该全局键；不加会跨项目污染。已独立复现跨项目隔离。
  - **D5** 保留早退 —— **不删**。删除后 `store.put` upsert 会改写已落库记录的 `retrieved_at`，
    使「幂等跳过」不再是零写入，与 D1 措辞冲突（两次 `retrieved_at` 相同 = 被保护，已实测）。
    另：`:211-214` 两个连续 `if independent_source is None` 是**不同语义**（条件早退 / 兜底赋值），非冗余。
- **另立独立任务（不属 A7，决定不改本分支）**：
  - **跨进程竞态**：实例级 `RLock` 不覆盖多进程共享 db。**且生产代码内无多进程写作**
    （全仓 `multiprocessing` / `Process(` / `subprocess` 零命中），属存储层基础设施议题，
    且需引入 `BEGIN IMMEDIATE` 改 SQLite 隔离级别 —— 动全局存储层，收益远小于风险。
  - **标题归一化碰撞**：`re.sub(r"\W+", "", title)` 下 `"A B"` 与 `"AB"` 同键，
    对无 DOI 论文是「静默合并」活限制。属既有归一化类，与 A7 的「重复写」是不同问题。

## Next step

- 等 **PR #23 合入 main** 后，本分支 rebase 到新 main 并开 PR。
- 若需处理「跨进程竞态 / 标题碰撞」，另开独立任务（见 Pending 末条），**不在本分支追加**。

## 未解决（如实列出，见 L3 §8，**均为已声明的边界或证据强度缺口，非缺陷**）

- 跨进程竞态未闭合（已另立任务）
- 并发测试是**概率性**判据型，非确定性
- 标题归一化碰撞（已另立任务）
- evidence 存在性查询 O(n)；provider 自带 `paper_id` 不被派生
- 「evidence 在、page 缺失」这半边自愈无测试（难经公共 API 构造，无记录删除接口）

## Verification

- [x] 聚焦：`pytest tests/test_adapter_search_service.py` → 50 passed（HEAD 41 + 9 新）。
- [x] 全量：`pytest -q -o addopts="" -W error` → 596 passed / 2 skipped。
- [x] ruff `All checks passed!`；compileall exit 0；`check.mjs --task` valid。
- [x] 判别力第一轮：变体 P 判据型（`assert 3 == 1`）、变体 S 崩溃型（不计入）、
      变体 G 判据型（跨项目同 id）。
- [x] 判别力第二轮：①`round 2 raised [ValueError …]`、②③`assert 3 == 1`、
      ④`assert 'ev_…' in ['ev-dangling']`、⑤`assert 'ev_8c48…' != 'ev_8c48…'` —— **5/5 判据型**。
- [x] 竞态探针：2 线程 × 20 轮 → 修复后 20/20 clean（0 重复 / 0 异常）。
- [x] D5 探针：重检索后落库 `retrieved_at` 保留早退 False / 删除早退 True。

## Handoff note

- 回退实验在 `/tmp/a7-cf2` 用**文本补丁**做（`cp -R` 只复制 `src`/`tests`，不含 `.git`，不在那里
  执行 git 命令）；`git show HEAD:<path> > <path>` 亦可用。变体 S 是 `ValueError` 崩溃型，
  按口径**不计入**判别力证据。
- **D5 是本包唯一「未按审计指示执行」的点**，证据见 L3 §7 探针；需裁定。
- 想改标识为全局（去 `project_id`）者：先跑 `test_the_same_paper_in_two_projects_stays_independent`。
- 想在 `_persist` 加参数者：先跑 `tests/test_runtime_hardening.py`。
- **残留竞态**：进程内已闭合；跨进程（多进程共享同一 db）未闭合。
- 已知未覆盖：标题键归一化碰撞现会**永久共用一页**；provider 自带 `paper_id` 不被派生。
