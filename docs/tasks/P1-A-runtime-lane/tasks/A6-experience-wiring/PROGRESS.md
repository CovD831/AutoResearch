# S4-A2 Progress

## 实现

- [x] 基线与隔离：A6 分支已 rebase 到最新 `origin/main@1e7e196`，避免重演 PR #15 的「分支落后 main → CI Task contract 必红」；`.venv` 可用。
- [x] 任务包与账本：`docs/tasks/P1-A-runtime-lane/tasks/A6-experience-wiring/{task-package.json,TASK.md}`、`.ai-team/tasks/S4-A2-EXPERIENCE-WIRING.md`（`check.mjs` 首轮即 `valid`）。
- [x] `src/autoresearch/experience_sink.py`：`MAPPING_RULES` 三条映射规则；`FailureCause` / `SinkSettlement` / `MalformedEventPayload`；`failure_causes`（只读观测）与 `settle`（消费 + 去重合并 + 写入）。
- [x] 三条生产触发通路：`Application.settle_failure_experiences` / `POST /projects/{project_id}/experiences/settle` / `cli settle-experiences [--dry-run]`。
- [x] `tests/fixtures/experience_sink/event_log.json`：9 条冻结事件（3 类拦截 × 多条 + 2 条诱饵 + 1 条无关事件），payload 形状对齐产生侧 dump。
- [x] `tests/test_experience_sink.py`：26 个测试，逐条对应 9 条验收场景，包含 `failure` 标签记录层和 WikiPage 镜像层断言，以及跨项目计数隔离、消费标记写入失败降级回归。
- [x] **owner 授权的 schema 半（D-A6-05 (a)）**：`src/autoresearch/contracts.py`（`ExperienceRecord` 加 `tags` 字段位）与 `src/autoresearch/evolution_service.py`（`record()` 的 tags 由硬编码改为透传）—— 两文件均在本包 `forbidden_paths` 上，由 owner 按其裁决修改，共 2 个 hunk，是本包唯一越界改动（已在账本 Invariants 显式登记为例外）。

## 实现期发现并修掉的两个设计坑

- [x] **畸形 payload 曾被静默跳过、没有诊断**。第一版 `_match` 把「解析器抛异常 / payload 非对象」与「这条事件不是失败」都折叠成同一个 `return None`，于是验收场景 6（「单条 payload 畸形时返回诊断」）在实现上不成立。修法：新增 `MalformedEventPayload`，`_match` 对映射表内的事件类型在 payload 不可读时**抛**，`settle` 捕获后记诊断 + `unreadable` 计数 + 消费该事件（不重复刷屏），`failure_causes` 捕获后静默跳过。
- [x] **`_recurrence_count` 会穿透 `settle` 的降级保证**。`if 1 + (同因标记数)` 的读取在循环内，标记表不可读时 `list_idempotent` 的异常会逃出 `settle`，与「永不向上抛」冲突。修法：`_recurrence_count` 内部兜底返回 0（视为首次出现），下次健康 settle 自动纠正 —— 这条修法只有在「计数是派生的」前提下才安全，是 D-A6-02 的直接收益。
- [x] **防御性读取**：`_string_list` 让裸字符串 / dict / None 的字段退化为空列表（否则 `for reason in "abc"` 会按字符迭代出垃圾）；`unknown_count` 非数字退化 0。

## 验证

- [x] Focused：`pytest tests/test_experience_sink.py -o addopts="" -q -p no:cacheprovider --basetemp=...` → **26 passed**。
- [x] 全量：`pytest tests -o addopts="" -q -p no:cacheprovider --basetemp=...` → **301 passed**。
- [x] 覆盖率：`--cov=autoresearch.experience_sink --cov-report=term-missing` → **200 stmts / 0 miss / 100%**。
- [x] `ruff check src tests` → `All checks passed!`。
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/S4-A2-EXPERIENCE-WIRING.md --base origin/main` → `valid`。
- [x] `python scripts/check_pr_contract.py --base origin/main` → `PR contract check passed`（exit 0）。
- [x] 功能场景 harness（`F:\AutoResearch\.workbuddy\a6-scenarios\`，未跟踪、不进 PR）：`scenario.py` 12 个字段级场景 + `user-scenario.py` 端到端业务场景（`proj_llm_eval`），全部实跑并逐字段核对，0 异常、0 拒绝写入。场景 2/6/7/8/10/12 是判据最硬的几条（同因合并计数、门槛仍关、晋级不被降级、降级不抛、写失败可重试、AST 结构证明）。
- [x] 用户侧独立验收（2026-09-13）：全量 **301 passed in 846.57s**、exit 0；场景 1–12 一次性运行完成，未出现 `RAISED` / `Traceback`、exit 0。日志保存在 workspace 外，不进入 PR。
- [x] 冒烟脚本（`.workbuddy` 外、临时目录，非交付物）实跑复核了 10 个行为：首拦截 → 建记录、重跑 → 零写入、同因第二次 → 计数 2、pass/clean 诱饵不产出、fail/unknown/audit unknown 各产出、人工升过级的记录合并后 `grade`/`promoted` 保持、事件日志不可读 → 降级不抛、dry-run 零写入。

## 边界与非目标

- 未 push、未开 PR（用户明令）。
- 用户侧独立复跑已经完成；当前等待整理并提交 PR。
- 未改任何共享文档：registry 行状态、`TASK-SPECS.md` 的 A6 措辞、`TASK-QUEUE.md` 的落后项都只上报不改。
- **唯一的 `forbidden_paths` 例外**：`contracts.py` / `evolution_service.py` 两文件由 owner 授权改动（D-A6-05 (a)）。注意 `forbidden_paths` 清单没有任何工具在机械校验——`check_pr_contract.py` 只拦 `var/` 前缀，`check.mjs` 只看勾选与提交数——所以这条例外是靠文字登记而不是靠检查发现的。
- 两份 `.patch` 文件已应用，保留在包内只作来源凭证，**不要重复 `git apply`**。

## Handoff to owner（记录级）

- **D-A6-01**：规格写「订阅」，实现为只读拉取。产生侧（`audit_evidence.py` / `audit.py`）都在 `forbidden_paths` 上，全仓无 `subscribe/listener/publish/hook` 抽象，push 式钩子无法在不越界的情况下落地。请裁决措辞是否需要回写。
- **D-A6-02**：`recurrence_count` 是「已消费的同因事件数」的派生量，不是「记录被写的次数」的自增量。请确认这符合对角色的定义。
- registry 行 `S4-A2-EXPERIENCE-WIRING` 仍为 `ready`（`docs/rearchitecture/TASK-PACKAGE-REGISTRY.md` 为共享文档，本包未改）。
- **D-A6-05 已闭环**：`failure` 标签已按 (a) 落地（schema + sink 两半均已应用、已提交、已被两条回归测试守住）。若 owner 决定把 schema 半改走「自己单独提交 / 先落主线」，本包需 `git checkout -- src/autoresearch/contracts.py src/autoresearch/evolution_service.py` 并等主线带上字段后 rebase。
