# 00 Scope and Authority — R-005-S1-CLOSURE

> Size: `design`（documentation only，不含实现授权）。本包不修改任何运行时代码。
> Owner: user/team（delegated）；Author: rearchitecture workflow session 2026-09-03。

## Source hierarchy（架构权威次序）

1. `AGENTS.md`（repo 协作规则；要求先读 `.ai-team/PROJECT.md`、`.ai-team/TASK.md`）
2. `.ai-team/PROJECT.md`（稳定事实：五业务 Agent、契约/存储/证据门禁职责）
3. `docs/ARCHITECTURE.md`（当前架构权威；target 文本在其晋级前仍是 intent）
4. 活动重构程序：`docs/rearchitecture/R004-trust-program/`（manifest `status: active`；canonical owner of L1/L2/S1 gate claims）
5. `.ai-team/TASK.md` 与重构包记录是任务/增量记录，不是架构权威（skill Do-not 条款）。

## Baseline revision

- Git HEAD：`46fbd7a43c01bebb312a1239368980cb2f6db0bb`
- 工作树：含用户在飞的 S1 修改（`src/autoresearch/capability.py`、`tests/test_capability_adapter.py` 新增；`application.py`/`contracts.py`/`storage.py` 修改；`.ai-team/TASK.md` 修改）。这些是在基线，不是本包产物，本包不回退、不重写。
- 全量记录：[evidence-baseline.txt](evidence-baseline.txt)；测试证据：[evidence-pytest.txt](evidence-pytest.txt)（20 passed，2026-09-03T15:54:08Z）。

## Earlier rearchitecture programs（现状恢复）

| 包 | 状态（manifest） | 与本包的关系 |
|---|---|---|
| R-001 | superseded（by R-004） | 仅历史；`docs/REARCHITECTURE.md` 仍把它列为完整包入口（见 06 的 discoverability 债） |
| R-002-LITERATURE-PILOT | blocked；review ledger R002-AR-001..008 全部 pending | 设计线已被 R-004 取代（R-004 `supersedes` 未列 R-002，但 `defers_to` 引用之）；其 8 条 pending findings 归 R-002 owner，不在本包消化 |
| R-003-PAPER-SEARCH-ADAPTER | blocked；S1 实现 + 评审 | **本包的直接前置**：S1 晋级证据缺口即本包要设计关闭的对象 |
| R-004-TRUST-PROGRAM | **active** 程序 | 本包是其下一个最小 design 增量；stop_rule 约束继承 |
| INDEPENDENT / SKILL-TEST-2026-09-03 | superseded（by R-004） | 继承 findings 以 AR-OLD-* 形式记录于 R-004 ledger |

程序推进触发条件（R-004）："S1 legacy/target fixture、sole-writer、idempotency、recovery 证据全部通过" —— **未满足**（R003-AR-005、AR-OLD-002/004/005/006 open）。

## Resume decision（UD-004，用户已委托）

按 skill step 1 呈报了未满足的推进门与选项；用户委托选择（"按推荐"）→ **repair first**，不授予 exception：

- [decisions/UD-004-resume.json](decisions/UD-004-resume.json)：reason、approver（用户委托）、reversal condition。
- 已执行的 repair（仅记录级，不动运行时代码）：
  1. 用当前树的新证据复核 R-003 ledger：`R003-AR-002`、`R003-AR-004` 有实现 + 测试证据，改记 `resolved`（附 repair_note）；`R003-AR-003` 的 resolution_ref 一并改为指向请求规范化代码 `src/autoresearch/capability.py::PaperSearchCapabilityAdapter.invoke`（request 含 seed_papers；review AR5-006 指出原引用的测试文件并不覆盖 seed 规范化，seed 内容重放/冲突测试缺口记入 06 的 next task 2）。`R003-AR-005` 维持 pending —— 它正是本包要设计的缺口。
  2. R-002 的 8 条 pending findings 不在本包处理（归 R-002 owner；R-004 stop_rule 已把它们排除在 S1 晋级路径外）。
  3. 记录旧包与新 checker（v0.31.0）的结构漂移为修复 backlog：三包均 `FAIL`（`profile` vs `size` 字段、R-003 跨包文档映射、review 状态字段位置）。证据：[evidence-checker-prior-packages.txt](evidence-checker-prior-packages.txt)。本包不重写旧 manifest（避免改写历史状态；owner 见 06）。

## In scope

- S1（Paper Search capability adapter）关闭所需的设计：当前树 ↔ R-003/R-004 合同的对账、legacy/target parity 与 recovery/unknown-outcome 证据计划（design only）。
- L2 合同仅覆盖本包消费的两个边界（见 04）；不为未消费模块造 L2/L3。

## Out of scope

- 任何运行时代码修改；S1 的实现与实现授权（本包以 recommendation 收尾）。
- S2 Audit Module、S3 lineage、S4 plugin packaging（R-004 stop_rule：S1 晋级证据通过前不得开工 S2）。
- 修复旧包 checker 结构漂移（记录为 backlog，owner 见 06）。
