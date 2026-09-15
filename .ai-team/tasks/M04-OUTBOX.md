# R007-L03-M04-OUTBOX

- ID: `R007-L03-M04-OUTBOX`
- Title: `R-007 L-03 lane —— M04 checkpoint 持久化测试 / outbox + 幂等键 / 数据库迁移与兼容`
- Status: `handoff`
- Status note: 2026-09-15 在 `feat/r007-l03-outbox`（base `main@8dd8780`）完成。新建 `src/autoresearch/outbox.py` + `tests/test_m04_outbox.py`，**未改 `storage.py` 一个字节**（L-06 的串行点）。实测：本包专项 **36 passed**（连跑 5 次稳定）、全量 **573 passed / 2 skipped / 0 failed**（基线自测 537/2/0，+36 无下降）、`ruff check src tests` 全绿。**未 commit、未 push、未开 PR。**
- Owner: `impl-l03-outbox`
- Next owner: `team-lead`

## Goal

按 R-007 `04-l2-contracts.md` **K9 `OutboxEntry`** 实现「意图与副作用分离」的持久化 outbox，使 **retry/resume 不重复副作用**（不变量 **I7**）：
重复投递被唯一约束拒绝（K9-1）、`payload_ref` 是引用而非内联（K9-2）、`attempts` 有上限且超限转 `failed` 不无限重试（K9-3）；
并落地 M04-04（进程退出 → 重启 → 恢复）与 M04-06（空库/旧库/部分失败可回滚 + schema version 可审计）在 **outbox 自身**的持久化面。

本包**不做**：不改 `storage.py` / `knowledge.py` / `contracts.py` / `evolution_service.py`；不新建 `migration.py`（L-01 排他文件）；不做 LangGraph 层 checkpoint 接线；不做生产接线（文件面不在本 lane）。

## Acceptance scenarios

- [x] **K9 字段契约**：`OutboxEntry` 含全部 8 个 K9 字段；唯一扩展为 `last_error`（审计用途，机械断言差值恰为该字段）。
- [x] **K9-1 唯一幂等键**：`reserve_idempotent(scope="outbox", key=idempotency_key, …)` —— 唯一性由既有 `idempotency` 表主键 `(scope, idempotency_key)` 提供；重复投递 **副作用只发生一次**。
- [x] **K9-2 引用而非内联**：`enqueue` **没有**接受 payload 本体的参数；payload 独立成 `outbox_payload` record；投递时解引用，引用失效 → 可观测失败。
- [x] **K9-3 有界重试**：槽位 = `outbox_attempt` scope 下 `{key}#a{n}` 行；预算耗尽 → 条目 `failed`，实测**不再调用 effector**。
- [x] **I7（M04-04）**：真实子进程 `os._exit` 崩溃 ×2 种窗口，新进程恢复；`service_started` 无结局 → **不重跑**（fail-closed）；`service_returned` 有 staged → **只收口不重跑**。
- [x] **M04-06（空库）**：空库只写 version record；`migrated=0`。
- [x] **M04-06（旧库）**：`sent→delivered` / `error→failed` / 补默认值；读不懂的行**不猜测**、计入 `skipped` 并原样保留。
- [x] **M04-06（部分失败可回滚 + 可审计）**：注入第 3 条写失败 → 版本号回滚为 0、旧行未被改写、`migration_failure` 留有原因；健康重试随后成功。
- [x] **前向不兼容拒动**：库版本高于本代码 → `refused=True` 零写入。
- [x] **判别力**：并发测试**全部插桩**并断言插桩生效；两条**常驻反向控制**（ledger-free 对照产生 2 次副作用 / 朴素计数器丢增量）证明生产断言非空洞；无插桩测试 docstring 明写**无判别力**。
- [x] **结构断言**：AST 证明 `outbox.py` 无 `append_event` / `connection` / `_initialize` 调用点；表集合恒为 `{records, audit_events, idempotency}`。

## Invariants

- **不改 `storage.py`**（R-007 全局串行点，L-06 占 `transaction()`）：`git diff --stat` 中不含该文件。本包对它的使用是**只读调用**，唯一私有依赖 `_write_record` 已登记（D-L03-02）。
- **不新增表、不新增 Store**：全部落到既有 `records` / `idempotency` 两张表（机械断言）。
- **审计事件只走原子转移**：`reserve_idempotent` / `mark_idempotent_phase` / `finalize_idempotent` 的 `events=` 参数；**从不调 `append_event`**（无条件 append 非幂等，A6 D-A6-07 实证会让行翻倍）。实测：第二次投递**零新增审计行**。
- **两阶段语义复用既有词表**：槽位状态即 A1/A2 的 `pending`/`finalized` 与 `reserved → service_started → service_returned`；**不自造 marker 词汇**（A6 D-A6-06c 的最终教训）。
- **`attempts` 是派生值**（= 已占槽位数），非自增计数器 → 计数器丢失不丢预算（实测把条目计数清零后预算仍精确）。
- **fail-closed 方向**：`service_started` 无结局 ⇒ UNKNOWN，**绝不重跑**，需 `resolve_unknown` 显式放行。降级/缺失**不记成正常值**：`delivered_at=None`、version record 不可解析则抛错而**不降级为 0**。
- **effector 抛异常 ⇒ 有界重试**（明确的语义边界，D-L03-06）：本包把「抛异常」理解为「本次尝试未确认」；若下游副作用可能在抛异常前已发生，须由 effector 自身幂等或 owner 改判。

## Decisions

- **D-L03-01（扩展字段 `last_error`）**：K9 未列，但「为何没投出去」必须可观测。判为非偏离（不违反任何 K9 不变量），并有机械断言把扩展集合钉死为 `{"last_error"}`。
- **D-L03-02（`migrate` 依赖私有 `_write_record`）**：`transaction()` + `_write_record()` 是仓库现成的**唯一**多记录原子写路径，不用它则「部分失败可回滚」无法落地。代价：`storage.py` 若改该私有签名本模块会红。**未改 `storage.py` 一个字节**。退路：①在 `outbox.py` 内用 `transaction()` 裸连接自行 INSERT（更差，重复 SQL）；②请 owner 把 `_write_record` 升为公开 API。**请 owner 裁决。**
- **D-L03-03（重复投递用返回值而非异常）**：`DeliveryOutcome(delivered=True, replayed=True)`，判据是「**副作用未发生**」。抛异常会让「已送达」看起来像错误；测试断言的是外部副作用次数而非 `replayed` 字面量。
- **D-L03-04（`delivered_at: datetime | None`）**：未投递必须为 `None`，否则就是「把缺失记成正常值」（纪律 3）。
- **D-L03-05（上限来源）**：`max_attempts` 构造参数（默认 3）；「超限」表现为全部槽位已占。
- **D-L03-06（effector 异常的可重试性）**：见 Invariants；这是本包对 K9-3 的落地解释，**请 owner 复核分界**。
- **D-L03-07（并发下条目 `status` 是 last-writer-wins）**：已缓解未消除 —— 抢槽失败的 worker **只在整本槽账终局且未送达时**才写 `failed`，抢槽瞬间的败者一律不写标签。**权限在 `idempotency` 行**，故条目字段只失去观测精度，不会让副作用重跑。
- **D-L03-08（`finalize_idempotent` 不幂等 → 靠复查 + 容忍 `already finalized`）**：由无插桩护栏测试**实际抓到**：两个 worker 同时观察到 `service_returned`（一个正常收口、一个恢复）会双双 finalize 同一条 a1 行 → 其中一个 `RuntimeError`。修法：`_finalize_attempt` 先点查状态、并容忍 `already finalized` 拒绝，返回「是否由本人完成」；`_resolve_existing` 的恢复分支改为**回读账本实际值**上报，而不是上报自己准备写的值。**该错误消息文本匹配是脆弱点**，登记在 L3 §8。
- **D-L03-09（迁移的原子性依赖 `connection()` 的隐式事务）**：`transaction()` 不显式 `BEGIN/ROLLBACK`；异常时 `connection()` 的 `finally` 只 `close()`、跳过 `commit()` → sqlite 隐式事务回滚。**已实测**（版本号回到 0、旧行未被改写），不是假设。

## Completed

- `src/autoresearch/outbox.py`（新建）：`EffectKind` / `OutboxStatus` / `OutboxEntry`（K9）/ `DeliveryOutcome` / `SchemaMigrationReport` / `PayloadRefNotFoundError` / `OutboxConflictError` / `OutboxSchemaError` / `Outbox`（`register_payload` / `payload` / `enqueue` / `entry` / `entries` / `pending` / `deliver` / `resolve_unknown` / `schema_version` / `migrate` / `migration_failure`）。
- `tests/test_m04_outbox.py`（新建）：**36 个测试**，含 4 条并发测试（3 条插桩 + 1 条明标无判别力）、2 条常驻反向控制、2 条真实子进程崩溃测试（`os._exit(2)`/`os._exit(3)`）、4 条迁移测试组、2 条 AST/表结构断言。
- `docs/tasks/M04-outbox/tasks/L3.md`：完整 L3（含「复用既有」实测清单：API 名 + 行号 + 调用点 + **不复用清单及理由**）。
- `docs/tasks/M04-outbox/tasks/task-package.json`、本账本。

## Pending

- **本包没有生产触发通路**（无 `Application` 方法 / HTTP 端点 / CLI 子命令）：`application.py` / `api.py` / `cli.py` 不在本 lane 排他清单（L-08 拥有 `api.py`）。A6 教训说明「接线但永不触发」是真实失效模式，故明报。**需 owner 指派接线包**。
- **D-L03-02**（私有 `_write_record` 依赖）与 **D-L03-06**（effector 异常的语义分界）待 owner 裁决。
- `node .ai-team/check.mjs --base main` 已在本 worktree 运行：`Result: valid`（`Functional progress: 11/11 (100%)`）。首次运行因本账本 `Next owner` 字段缺反引号而被判 `blocked`，已修正（该判据要求 `^- Next owner: \`…\`$` 精确匹配）。
- 未 commit / 未 push / 未开 PR（提交纪律：等 owner 明确许可）。

## Next step

1. owner 裁决 D-L03-02 / D-L03-06。
2. owner 指派接线（`application.py` + `api.py` + `cli.py`）或明确本包不做。
3. 决定是否 commit 本 lane（当前改动全部停在本地工作区）。

## Verification

```bash
PYTHONPATH=src <python> -m pytest tests/test_m04_outbox.py -q -o addopts="" -W error
#   36 passed in 1.60s        （连跑 5 + 3 次：36/36 稳定，无 flaky）

PYTHONPATH=src <python> -m pytest -q -o addopts="" -W error
#   baseline（本 worktree 自测）: 537 passed, 2 skipped in 31.89s
#   after   （本包改动后）     : 573 passed, 2 skipped in 27.64s   → +36，0 failed，无下降

<python> -m ruff check src tests        → All checks passed!  (exit 0)
<python> -m compileall -q src           → OK
PATH=<node>:$PATH node .ai-team/check.mjs --task .ai-team/tasks/M04-OUTBOX.md --base main
#   → Result: valid; Functional progress: 11/11 (100%)
PATH=<node>:$PATH <python> scripts/check_pr_contract.py --base main
#   → PR contract check passed: 0 changed paths; 0 task ledger(s)

# 反向验证 A（临时副本，未进仓库）：_claim_attempt 换成朴素「读后 +1」版
#   → 15 failed, 20 passed，失败类型 = 符号缺失型（KeyError: unknown idempotency record）
# 反向验证 B（临时副本，未进仓库）：删掉 _resolve_existing（K9-1 守卫）
#   → 4 failed；N-1 的失败是**判据型**：result={'sink_rows': 2}，即外部 sink 收到 2 行
```

`<python>` = `/Users/abab/.workbuddy/binaries/python/envs/default/bin/python`

## Handoff note

- **复用原语是机械可证的，不是文字承诺**：`outbox.py` 的 AST 调用点集合里出现 `reserve_idempotent` / `mark_idempotent_phase` / `finalize_idempotent` / `transaction` / `_write_record`，且**没有** `append_event`（`test_outbox_uses_no_api_outside_the_existing_store`）。
- **并发结论只由插桩测试承担**（`_Gate` 强制交错 + 断言 `len(gate.threads) == 2`）；无插桩的那条 docstring 明写**无判别力**。
- **判别力是实测的**，且区分类型：套件内常驻两条反向控制（ledger-free 对照实测产生 **2 次**外部副作用，生产为 1 次）；临时副本反向验证 B（删掉 K9-1 守卫）使 N-1 以**判据型**失败（`result={'sink_rows': 2}`）；反向验证 A（朴素计数器）虽使 15 条测试红，但失败类型是**符号缺失型**，故**不作为**判据型证据使用。
- **请优先攻击这三处**：
  1. `_spend_budget` 的「整本槽账终局才写 `failed`」条件是否真的排除了「败者写错标签」（D-L03-07 的残留窗口）。
  2. `_finalize_attempt` 对 `RuntimeError("already finalized")` 的**文本匹配**（D-L03-08）：换一个上游措辞即失效。
  3. `migrate` 对私有 `_write_record` 的依赖（D-L03-02）：owner 若认为不可接受，请给替代路径。
