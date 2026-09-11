# S4-A2 Experience Wiring

- ID: `S4-A2-EXPERIENCE-WIRING`
- Title: `S4 失败经验自动沉淀接线（原 Owner O9 接线点①前移成员 A）`
- Status: `handoff`
- Status note: 2026-09-11 开工并完成实现。基线 `origin/main@66aba64`（**不是**本地 `main`，后者停在 `380bd49`）。已定案：事件消费钩子实现为**对已落地事件日志的只读消费**（产生侧在 B3/A3 独占路径上，A6 禁触），同因去重复用 A1/A2 `idempotency` 底座，自动沉淀写出的记录恒为 `E0` 且永不调用 `promote`。验收命令全绿（focused 22 / 全量 188 / 新模块覆盖率 100% / ruff / check.mjs valid），**未 push、未开 PR**（用户明令），等 owner 复核与 D-A6-01 裁决。
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

## Invariants

- 只读消费审计事件：本包对 `audit_events` 表只经 `RecordStore.events` 读取；`experience_sink.py` 的 AST 调用点集合里**不存在** `append_event`（`tests/test_experience_sink.py::test_sink_module_has_no_call_site_that_appends_events_or_promotes` 机械证明）。
  - 精确表述：新增的 `audit_events` 行只能来自被强制的写入通路 `ExperienceService.record` → `KnowledgeService.add_page`（事件类型 `knowledge.page_added`），实测一次 settle 新增的事件类型集合恒为 `{"knowledge.page_added"}`，**零条** `audit.*` / `audit_evidence.*` / `evidence.*`。
- 不改变审计链语义：不修改 `audit.py` / `audit_evidence.py` / `evidence.py`（均在 `forbidden_paths`），且 `experience_sink.py` 不 import 任何产生侧模块（AST 断言）。
- 写入只经 `ExperienceService.record`（它自身只落 `KnowledgePartition.EXPERIENCES` 的 record + WikiPage 镜像）。
- 自动沉淀不得降低 promote 门槛：新记录 `grade` 恒 `E0`、`promoted` 恒 `False`；合并已存在记录时 `grade`/`promoted` **原样保留**（只允许把 `recurrence_count` 往上取 max）；不调用 `promote`。
- 降级方向是 fail-closed：钩子故障 → 永不向上抛，主管线不受影响；写入失败的事件**不标记已消费**，下次 settle 重试。
- 不新增 Store、不新建表、不新增消息总线 / scheduler / 隐藏 Agent（R005）。实测 settle 后 `sqlite_master` 的表集合仍为 `{records, audit_events, idempotency}`。

## Decisions

- **D-A6-01（无推送钩子，改为只读消费事件日志）**：规格原文写「订阅 `audit_evidence.*` / fail-closed 拦截事件」。实测：`evidence.candidate_blocked` 的产生点在 `src/autoresearch/audit_evidence.py`（B3 独占 allowed path，属 B 线 evidence 路径），`audit.report_created` 的产生点在 `src/autoresearch/audit.py`（A3 独占）——**产生侧对 A6 是禁止触碰的**，故任何 `subscribe`/`callback` 式推送钩子都无法在不越界的情况下落地。且全仓确无订阅抽象（无 `subscribe/listener/publish/hook` 实现），只有 `RecordStore.events(project_id)` 这一读取口。因此「事件消费钩子」实现为**对已落地事件日志的只读拉取**：既满足「只读消费 / 不改审计链」，又使越界在机制上不可能。此为对规格措辞的偏离，**报 owner 裁决**。
- **D-A6-02（复用 idempotency 底座做消费标记）**：重放安全不采用「新表 / 游标文件」方案，直接用 A1/A2 既有的 `RecordStore.remember_idempotent(scope, key, result)`（`INSERT OR IGNORE`，返回是否新插入）以 `event_id` 为 key 标记已消费。追加决定：**`recurrence_count` 是派生的，不是自增的** —— `1 + (同因的已消费标记数)`。理由：自增计数器在「写记录成功、写标记前崩溃」时会重复计数；派生使重跑自愈，且标记表不可读时降级为 1（下次健康 settle 自动纠正）。见 `_recurrence_count`。
- **D-A6-03（自动沉淀永不触及晋级路径）**：写出的记录 `grade` 取 `ExperienceRecord` 默认值 `E0`；重复拦截只递增 `recurrence_count`，不回填 grade；`promoted` 字段在合并时**原样保留**（已晋级记录不被自动合并降级）。`evolution_service.py` 列入 `forbidden_paths`，使「不改 promote 语义」由 diff 机械可证，而非仅靠承诺。

## Completed

- `src/autoresearch/experience_sink.py`（199 stmts）：`MAPPING_RULES` 三条映射规则 + `FailureCause` / `SinkSettlement` / `MalformedEventPayload`；`ExperienceSink.failure_causes`（只读观测）与 `ExperienceSink.settle`（消费 + 合并 + 写入）。
- 三条生产触发通路：`AutoResearchApplication.settle_failure_experiences(project_id)`、`POST /projects/{project_id}/experiences/settle`、`cli settle-experiences [--dry-run]`。
- `tests/fixtures/experience_sink/event_log.json`：冻结的离线事件切片（3 类拦截事件 + 2 条诱饵 + 1 条无关事件，共 9 条），payload 形状对齐产生侧 dump。
- `tests/test_experience_sink.py`：22 个测试，覆盖 8 条验收场景。

## Pending

- 规格偏离 D-A6-01 待 owner 裁决。
- registry 行 `S4-A2-EXPERIENCE-WIRING` 状态仍为 `ready`（`docs/rearchitecture/TASK-PACKAGE-REGISTRY.md` 为共享文档，本包未改，报 owner 回写）。
- 用户侧独立复跑（数值 + 功能场景）未做 —— 本包只完成 AI 侧验收。
- D-A6-02 的派生式 `recurrence_count` 是对「复现 ≥2」门槛基数的**语义选择**，owner 若要「事件计数与记录计数严格一致」，需复核 `_recurrence_count`。

## Next step

owner 复核 D-A6-01 裁决 → 用户侧复跑验收命令与功能场景 → 通过后由 owner 决定 push / 开 PR。下一包 `S4-A3-KNOWLEDGE-VECTOR`。

## Verification

命令均在 `F:\AutoResearch\.worktrees\s4-a2-experience-wiring` 下、以该 worktree 自己的 venv 执行；公共参数 `-o addopts="" -p no:cacheprovider`（前者让 summary 行可见，后者消 Windows `WinError 5`），并显式 `--basetemp="C:/Users/94461/AppData/Local/Temp/a4-verify-basetemp"`。

- [x] Focused：`.venv/Scripts/python.exe -m pytest tests/test_experience_sink.py -o addopts="" -q -p no:cacheprovider --basetemp=...` → **22 passed**。
- [x] 全量：`.venv/Scripts/python.exe -m pytest tests -o addopts="" -q -p no:cacheprovider --basetemp=...` → **188 passed**（基线 `origin/main@66aba64` 为 **166**，本包 +22）。
- [x] 覆盖率：`--cov=autoresearch.experience_sink --cov-report=term-missing` → **199 stmts / 0 miss / 100%**。
- [x] `.venv/Scripts/python.exe -m ruff check src tests` → `All checks passed!`。
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/S4-A2-EXPERIENCE-WIRING.md --base origin/main` → `valid`，`Functional progress: 8/8 / Code progress from origin/main: 6 commits, 9 files`。
- [x] `--base main` 口径说明：本地 `main` 停在 `380bd49`，`--base main` 会把新基线已含的 B5 提交算进本包 diff（本包真实改动用 `--base origin/main` 看）。
- [x] `python scripts/check_pr_contract.py --base origin/main` → `PR contract check passed: 11 changed paths; 1 task ledger(s)`（exit 0）。
- [x] 功能场景 harness（未跟踪、不进 PR）：`F:\AutoResearch\.workbuddy\a6-scenarios\scenario.py`（12 场景）与 `user-scenario.py`（端到端业务场景）实跑，逐字段输出符合预期，0 异常。

## Handoff note

实现完成、已 commit 在 `codex/s4-a2-experience-wiring`，**未 push、未开 PR**。owner 需先裁决 D-A6-01（规格写「订阅」，本包按只读拉取落地），再看 D-A6-02 的派生计数是否符合对角色的定义。三个触发通路都已实测可达，不存在 O12 式「接线了但生产上永不触发」。详见 `docs/tasks/P1-A-runtime-lane/tasks/A6-experience-wiring/HANDOFF.md`。
