# S4-A2 Experience Wiring

- ID: `S4-A2-EXPERIENCE-WIRING`
- Title: `S4 失败经验自动沉淀接线（原 Owner O9 接线点①前移成员 A）`
- Status: `handoff`
- Status note: 2026-09-12 已 rebase 到最新 `origin/main@1e7e196`，并按顺序应用 schema 与 sink 补丁（两份补丁均已提交，包内保留仅作来源凭证）。事件消费仍是对已落地事件日志的只读消费；同因去重复用 A1/A2 `idempotency` 底座；自动沉淀记录恒为 `E0` 且永不调用 `promote`。2026-09-13 复核并修复两项边界缺陷：`recurrence_count` 按项目隔离；消费标记写入失败时降级并保留事件待重试。当前专项验证为 26 passed、全量验证为 301 passed。D-A6-01/D-A6-02 的实现差异将在 PR 中向负责人披露并请其审阅。本包有 **1 处 `forbidden_paths` 边界变化**（两个文件、两个 hunk，见 Invariants）；本次没有预先取得负责人授权。**尚未 push、未开 PR**。
- Owner: `member A`
- Next owner: `user/team`

## Goal

把 A3/B3 的 fail-closed 拦截事件流接到 `evolution_service.py` 的 `ExperienceService`，让失败经验**从第一次真实拦截开始自动沉淀**——A/B 线各自产生的拦截事实，自动变成 experiences 分区里可复现、可计数、可审计的经验记录，为 promote 的「复现 ≥2」门槛提供真实基数。数据飞轮的经验层上线。

本包**不做**：不改 `ExperienceService.promote` 的四门槛语义；不给自动晋级留任何路径；不写 experiences 以外的分区；不触碰 B 线 evidence 路径。

## Acceptance scenarios

- [x] 事件消费钩子：只读消费 `audit_events`（`evidence.candidate_blocked` / `audit_evidence.report_created` / `audit.report_created`），消费过程对审计链零写入。
- [x] 事件→经验映射表：把三类拦截事件归一化为 `ExperienceRecord`（problem / technique / outcome / evidence_ids），映射表作为交付物随包提交。
- [x] 重复拦截去重：同因拦截合并为同一条 record 并把 `recurrence_count` 递增，供 promote 的「复现 ≥2」门槛使用。
- [x] 四门槛不被绕过：自动沉淀写出的记录 `grade` 恒为 `E0`、`promoted` 恒为 `False`，且代码路径上不存在对 `promote` 的调用。
- [x] 幂等重放安全：同一事件重复消费不产生重复计数（复用 `idempotency` 底座）。
- [x] 静默降级：事件源不可用或单条 payload 畸形时返回诊断、不抛异常，主管线行为不变。
- [x] 生产可达：`Application` 方法 + HTTP 端点 + CLI 子命令三条真实触发通路（避免「接线了但生产上永不触发」）。
- [x] fixture 与离线测试：全部离线可重跑。
- [x] **失败经验的 `failure` 标签**（规格 `主要交付` 第 2 条原文的一半）：已通过共享 schema 与记录服务透传落地。`ExperienceRecord.tags` 由 schema 提供，`ExperienceService.record()` 透传到 WikiPage，sink 新建和合并记录均写入 `failure`。两条标签回归测试已加入；A6 专项 26 passed、全量 301 passed、`experience_sink.py` 200/200（100%）。

## Invariants

- 只读消费审计事件：本包对 `audit_events` 表只经 `RecordStore.events` 读取；`experience_sink.py` 的 AST 调用点集合里**不存在** `append_event`（`tests/test_experience_sink.py::test_sink_module_has_no_call_site_that_appends_events_or_promotes` 机械证明）。
  - 精确表述：新增的 `audit_events` 行只能来自被强制的写入通路 `ExperienceService.record` → `KnowledgeService.add_page`（事件类型 `knowledge.page_added`），实测一次 settle 新增的事件类型集合恒为 `{"knowledge.page_added"}`，**零条** `audit.*` / `audit_evidence.*` / `evidence.*`。
- 不改变审计链语义：不修改 `audit.py` / `audit_evidence.py` / `evidence.py`（均在 `forbidden_paths`），且 `experience_sink.py` 不 import 任何产生侧模块（AST 断言）。
- 写入只经 `ExperienceService.record`（它自身只落 `KnowledgePartition.EXPERIENCES` 的 record + WikiPage 镜像）。
- 自动沉淀不得降低 promote 门槛：新记录 `grade` 恒 `E0`、`promoted` 恒 `False`；合并已存在记录时 `grade`/`promoted` **原样保留**（只允许把 `recurrence_count` 往上取 max）；不调用 `promote`。
- 降级方向是 fail-closed：钩子故障 → 永不向上抛，主管线不受影响；写入失败的事件**不标记已消费**，下次 settle 重试。
- 不新增 Store、不新建表、不新增消息总线 / scheduler / 隐藏 Agent（R005）。实测 settle 后 `sqlite_master` 的表集合仍为 `{records, audit_events, idempotency}`。
- **`forbidden_paths` 边界说明**：`contracts.py`（+1 行：`ExperienceRecord.tags` 字段位）与 `evolution_service.py`（1 行改动：`record()` 的 tags 由硬编码改为透传）实际被修改，用于落实任务书要求的 `failure` 标签。两文件属于本包声明的 `forbidden_paths`，本次没有预先取得负责人授权；PR 中向负责人说明修改原因并请其审阅。这是本包唯一越出 `forbidden_paths` 的改动，合计 2 个 hunk；`evolution_service.py` 中被改的只有 tags 展开那一行，`promote` 的方法体、调用点与语义均未被触碰（本包自己的 AST 断言仍证明 `experience_sink.py` 不存在 `promote` / `append_event` 调用点）。

## Decisions

- **D-A6-01（无推送钩子，改为只读消费事件日志）**：规格原文写「订阅 `audit_evidence.*` / fail-closed 拦截事件」。实测：`evidence.candidate_blocked` 的产生点在 `src/autoresearch/audit_evidence.py`（B3 独占 allowed path，属 B 线 evidence 路径），`audit.report_created` 的产生点在 `src/autoresearch/audit.py`（A3 独占）——**产生侧对 A6 是禁止触碰的**，故任何 `subscribe`/`callback` 式推送钩子都无法在不越界的情况下落地。且全仓确无订阅抽象（无 `subscribe/listener/publish/hook` 实现），只有 `RecordStore.events(project_id)` 这一读取口。因此「事件消费钩子」实现为**对已落地事件日志的只读拉取**：既满足「只读消费 / 不改审计链」，又使越界在机制上不可能；该实现差异将在 PR 中向负责人披露。
- **D-A6-02（复用 idempotency 底座做消费标记）**：重放安全不采用「新表 / 游标文件」做法，直接用 A1/A2 既有的 `RecordStore.remember_idempotent(scope, key, result)`（`INSERT OR IGNORE`，返回是否新插入）以 `event_id` 为 key 标记已消费。`recurrence_count` 继续采用派生值：`1 + (同项目同因的已消费标记数)`，而不是记录上的自增计数器。理由：自增计数器在「写记录成功、写标记前崩溃」时会重复计数；派生使重跑自愈。该实现差异将在 PR 中向负责人披露。见 `_recurrence_count`。
- **D-A6-03（自动沉淀永不触及晋级路径）**：写出的记录 `grade` 取 `ExperienceRecord` 默认值 `E0`；重复拦截只递增 `recurrence_count`，不回填 grade；`promoted` 字段在合并时**原样保留**（已晋级记录不被自动合并降级）。`evolution_service.py` 列入 `forbidden_paths`，使「不改 promote 语义」由 diff 机械可证，而非仅靠承诺。
- **D-A6-05（`failure` 标签）**：`ExperienceRecord.tags` 已加入共享 schema，`ExperienceService.record()` 已把自定义标签透传到 WikiPage，sink 已在新建和合并路径写入 `failure`。两条回归测试分别验证记录层字段和镜像页标签；该项现已完成。落地方式：实际修改了两个 `forbidden` 文件（`contracts.py` / `evolution_service.py`），因为任务书要求失败经验带有 `failure` 标签；本次没有预先取得负责人授权，PR 中说明修改原因并请负责人审阅。若负责人决定改走「自己单独提交 / 先落主线」的路线，本包只需 `git checkout -- src/autoresearch/contracts.py src/autoresearch/evolution_service.py` 并等主线带上该字段后 rebase（sink 半在没有字段时会红，这正是不能先合 sink 半的原因）。
- **D-A6-06（owner 代修；标记表读不可用不得重置计数）**：`_recurrence_count` 原在 `list_idempotent` 抛异常时 `return 0`，于是 `settle` 里 `recurrence = 0 + 1 = 1` 对每个事件生效——**同一份 fixture，健康态 `max(count)=2`、达标记录 1 条；读不可用态 `max(count)=1`、达标记录 0 条**。`recurrence_count >= 2` 是四道 promotion gate 之一（D-A6-03），这条路径让它**静默永不通过**，而 `recorded` 与健康态完全相同，结算报告看起来一切正常。修法两层：① 读失败时回退到**已存记录自身的 `recurrence_count`**（`_stored_recurrence`），保持单调；② `settle` 内维护 `settled_in_run` 进程内累积器——因为「同因的第 2 个事件」在同一批里看不到第 1 个的标记（标记只在第 1 个结算后才存在），跨 store 读是不够的。既有测试 `test_unavailable_consumption_markers_degrade_instead_of_crashing` 只断言 `degraded`/`recorded`/diagnostic，**对计数零断言**——有覆盖无判据，已补 `test_degraded_marker_read_still_counts_recurrences` 等两条断言**结论**的测试。
- **D-A6-07（owner 代修；先占位再写入）**：原顺序是**先 `record` 后 `_consume`**。`record` 成功而标记写失败时事件未消费，下次结算重跑 `record`：`store.put` 是 upsert 所以经验行仍是 1 条，**但 `record` 会追加一个 `knowledge.page_added` 审计事件，而那不是幂等的**——实测 `page_added` 从 6 变 **12**（精确翻倍）。改为**先 claim 再 record**：claim 失败则什么都没发生、干净重试；record 失败则用 `delete_idempotent` **释放 claim**（该方法的 docstring 正是为此场景而设——「能证明无外部副作用的调用方可以回收」），事件回到未消费。既有测试只投放**一条**事件，覆盖不到多事件部分失败，已补 `test_a_retry_after_a_partial_failure_does_not_duplicate_audit_events`。
- **D-A6-08（owner 代修；读不懂的 payload 不得被消耗）**：`MalformedEventPayload` 分支原先是**先 `_consume` 再 `continue`**，于是坏 payload 的事件被永久标记为已消费，**它代表的失败永远不会沉淀**，也不再重试。这与 `record` 失败路径（`continue` 而不 consume，留给重试）**处置不一致**。sink 的全部职责就是归档失败，静默丢弃一个失败是最坏的降级，故改为**不 consume、只计入 `unreadable` 并留待重试**。既有测试 `test_malformed_payload_degrades_per_event_and_keeps_processing_the_rest` 把 fail-open 写成了期望（断言 `rerun.unreadable == 0`）——**测试名对、断言错**，已改为断言事件未被消耗且下次仍可见。
- **D-A6-09（owner 代修；`-W error` 下零 error）**：`tests/test_experience_sink.py` 用 `with sqlite3.connect(...)` 读表，但 **`sqlite3.Connection` 的上下文管理器只管事务、不管关闭**——句柄活到 GC，`-W error` 把它变成 `PytestUnraisableExceptionWarning`，且报在**下一条**测试的 setup 上（`main` 基线 275 passed / 0 error，本 PR 变成 300 passed + **1 error**）。改为显式 `try/finally: connection.close()`。

## Completed

- `src/autoresearch/experience_sink.py`（200 stmts）：`MAPPING_RULES` 三条映射规则 + `FailureCause` / `SinkSettlement` / `MalformedEventPayload`；`ExperienceSink.failure_causes`（只读观测）与 `ExperienceSink.settle`（消费 + 合并 + 写入），并写入 `failure` 标签。
- 三条生产触发通路：`AutoResearchApplication.settle_failure_experiences(project_id)`、`POST /projects/{project_id}/experiences/settle`、`cli settle-experiences [--dry-run]`。
- `tests/fixtures/experience_sink/event_log.json`：冻结的离线事件切片（3 类拦截事件 + 2 条诱饵 + 1 条无关事件，共 9 条），payload 形状对齐产生侧 dump。
- `tests/test_experience_sink.py`：24 个测试，覆盖 9 条验收场景。
- D-A6-05 的两份补丁已按顺序应用：共享 schema 增加 `ExperienceRecord.tags` 并由 `ExperienceService.record()` 透传；sink 新建/合并路径写入 `failure` 标签。
- 本包改动文件全集（16 个路径）：新增 `experience_sink.py` / `test_experience_sink.py` / `fixtures/experience_sink/event_log.json` / 6 份任务包与账本文档 / 2 份补丁；改动既有 `application.py` / `api.py` / `cli.py`；另外修改 `contracts.py`（+1 行）/ `evolution_service.py`（1 行）以提供 `failure` 标签通道，两个文件属于声明的 `forbidden_paths`，原因与边界已写明。

## Pending

- 规格偏离 D-A6-01 待在 PR 中向负责人披露并审阅。
- D-A6-05 已裁决并完成，当前验收清单为 `9/9`。
- registry 行 `S4-A2-EXPERIENCE-WIRING` 状态仍为 `ready`（`docs/rearchitecture/TASK-PACKAGE-REGISTRY.md` 为共享文档，本包未改，报 owner 回写）。
- 用户侧独立复跑已完成：全量 **301 passed in 846.57s**、exit 0；功能场景 1–12 全部执行，未出现 `RAISED` / `Traceback`，场景脚本 exit 0。
- D-A6-02 的派生式 `recurrence_count` 是对「复现 ≥2」门槛基数的**语义选择**；PR 中向负责人披露其与直接自增的差异并请其审阅。

## Next step

**owner 代修已完成（2026-09-14）**，请成员 A 复核 D-A6-06 / 07 / 08 / 09 四条是否彻底。

**请优先攻击这三处**：

1. **先 claim 再 record 的顺序**（D-A6-07）——这是本轮最大的行为变更。claim 成功而 record 失败时靠 `delete_idempotent` 释放；若你认为「释放」这个动作本身可能失败或留下中间态，请指出。
2. **`_recurrence_count` 的两层修法**（D-A6-06）——回退到已存记录的 count + settle 内累积器。请检查：跨多次结算、跨进程、以及「记录被手工清理」这几种情形下计数是否仍然单调正确。
3. **M2 改为不 consume 后，坏 payload 事件会在每次结算时重复出现**——这是刻意的（留待重试），但意味着 `unreadable` 会持续计数。若你认为需要退避或上限机制，请给出建议。

PR 审核后由 owner 回写共享 registry。下一包 `S4-A3-KNOWLEDGE-VECTOR`。

## Verification

命令均在 `F:\AutoResearch\.worktrees\s4-a2-experience-wiring` 下、以该 worktree 自己的 venv 执行；公共参数 `-o addopts="" -p no:cacheprovider`（前者让 summary 行可见，后者消 Windows `WinError 5`），并显式 `--basetemp="C:/Users/94461/AppData/Local/Temp/a4-verify-basetemp"`。

- [x] Rebase：A6 分支已 rebase 到 `origin/main@1e7e196`。
- [x] Focused：`pytest tests/test_experience_sink.py ...` → **26 passed**。
- [x] 全量：`pytest tests ...` → **301 passed**。
- [x] 覆盖率：`--cov=autoresearch.experience_sink --cov-report=term-missing` → **200 stmts / 0 miss / 100%**。
- [x] `.venv/Scripts/python.exe -m ruff check src tests` → `All checks passed!`。
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/S4-A2-EXPERIENCE-WIRING.md --base origin/main` → `valid`。
- [x] `python scripts/check_pr_contract.py --base origin/main` → `PR contract check passed`（exit 0）。
- [x] D-A6-05：两份补丁已应用，并通过标签专项测试、全量测试和覆盖率检查。
- [x] **反向验证（补丁的守卫是真的）**：只应用 sink 补丁而不应用 schema 补丁时，两条新测试**失败**（`AttributeError: 'ExperienceRecord' object has no attribute 'tags'`）——证明它们不是「跟着实现写绿的空断言」。这也是 schema 与 sink 两部分必须一起交付的原因。
- [x] 功能场景 harness（未跟踪、不进 PR）：`F:\AutoResearch\.workbuddy\a6-scenarios\scenario.py`（12 场景）与 `user-scenario.py`（端到端业务场景）实跑，逐字段输出符合预期，0 异常。
- [x] **用户侧独立验收（2026-09-13）**：全量 `pytest tests` → **301 passed in 846.57s**、exit 0，日志保存在 workspace 外的 `F:\AutoResearch.workbuddy\a6-user-full-20260913-225909.log`；场景 1–12 一次性运行完成，未出现 `RAISED` / `Traceback`、exit 0，日志保存在 `F:\AutoResearch.workbuddy\a6-user-scenarios-20260913-230226.log`。日志不进入 PR。
- [x] **收口复核（2026-09-13，member A 独立复跑，非引用自述数字）**：focused **26 passed**、`experience_sink.py` **200 stmts / 0 miss / 100%**、全量 **301 passed**、`ruff check src tests` → `All checks passed!`、`check.mjs --base origin/main` → `valid` + `Functional progress: 9/9 (100%)`、`check_pr_contract.py --base origin/main` → exit 0。另用 `git diff --check` 校验无空白错误。此次增加了跨项目计数隔离与消费标记写入失败降级回归测试。
- [x] **补丁文件状态**：schema / sink 补丁已应用，保留在包内仅作**来源凭证**（记录两部分具体修改内容），**不要再 `git apply` 它们**（对当前 HEAD 会报 already applied）。

### owner 代修验证（2026-09-14，隔离 worktree `/tmp/pr20fix/wt`，基线 `5df98d1e`）

- [x] 全量：`PYTHONPATH=src pytest -o addopts="" -W error -q` → **306 passed, 0 error**（修复前 **300 passed + 1 error**；`main@1e7e196` 基线为 275 passed / 0 error）。
- [x] `ruff check src tests` → All checks passed；`compileall -q src` → exit 0。
- [x] `check.mjs --base origin/main` → valid；`check_pr_contract.py --base origin/main` → passed（16 paths / 1 ledger）。
- [x] **判别力实测**：改后的 `test_experience_sink.py` 放到**修复前的 `5df98d1e`** 上跑 → **5 failed / 26 passed**；修复后 **31 passed**。五个失败逐条对应：`test_degraded_marker_read_still_counts_recurrences`（H1）、`test_degraded_marker_read_counts_repeats_within_one_settlement`（H1）、`test_a_retry_after_a_partial_failure_does_not_duplicate_audit_events`（M1）、`test_malformed_payload_degrades_per_event_and_keeps_processing_the_rest`（M2）、`test_consumption_marker_write_failure_degrades_and_leaves_event_for_retry`（M1 顺序变更）。L1 不是断言失败而是 `-W error` 下的 error，已单独对照验证（`main` 0 error → 原 PR 1 error → 修复后 0 error）。
- [x] **行为面实测（同一份 fixture 对照）**：
  - H1：健康态 counts `[1,1,1,1,2]`、达标 1 条；读不可用态**同样 `[1,1,1,1,2]`**（修复前为 `[1,1,1,1,1]`、达标 0 条）。
  - M1：`knowledge.page_added` 重试后 = **6**（修复前 **12**）；第三次结算 `consumed=0 recorded=0`、page_added 仍为 6。
  - M2：损坏 payload 第 2 次结算 `unreadable=1`（修复前 `0`）、marker 数 **0**（未被消耗）。
  - 回归：`record` 失败时 claim 被释放（markers=0），重试 `consumed=1 recorded=1`。

## Handoff note

- From: `user/team`
- To: `member A`
- Summary（2026-09-14 owner 代修后更新）: 你对 D-A6-01 / D-A6-02 / D-A6-05 的披露质量很高——**D-A6-01 与 D-A6-05 我审查后均认可，不需要改**（`failure` 标签放共享 schema 正确，我实测旧 schema 记录可正常反序列化、向后兼容无破坏）。深度审查共发现 1 高 / 2 中 / 1 低，已全部代修：**H1** 标记表读不可用致 `recurrence_count` 坍缩（同一 fixture 健康 `max=2` / 退化 `max=1`，`recurrence_count>=2` 门槛静默永不通过）、**M1** 先 record 后 claim 致重试时 `knowledge.page_added` 翻倍（6→12）、**M2** 损坏 payload 被消耗致失败永久丢弃（fail-open）、**L1** `with sqlite3.connect(...)` 不关连接致 `-W error` 下 1 error。全量 306 passed / 0 error；新测试在修复前基线上 5 条失败。**请优先攻击 Next step 里的三点**（claim/record 顺序、两层计数修法、坏 payload 重复出现）。以下为原始交付说明：实现完成并已基于最新 `origin/main@1e7e196` 验证，**未 push、未开 PR**。三个触发通路、failure 标签、两项边界缺陷修复、自动检查和用户侧独立验收均已完成；当前只剩整理 PR，并在 PR 中向 owner 记录 D-A6-01/D-A6-02。详见 `docs/tasks/P1-A-runtime-lane/tasks/A6-experience-wiring/HANDOFF.md`。
