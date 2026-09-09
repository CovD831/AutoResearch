# S2-A Audit Runtime

- ID: `S2-A-AUDIT-RUNTIME`
- Title: `Audit CLI/stdio runtime and resolver persistence`
- Status: `active`
- Owner: `member A`
- Next owner: `user/team`

## Goal

完成 A3/S2 Audit Runtime 的本地调用边界：保留既有 Audit CLI 与直接调用兼容性，
补齐 transport-agnostic 的 JSON-lines stdio/selftest、版本化 resolver 快照持久化，以及经 Persistence Port
保存 AuditReport artifact；不直接写 EvidenceItem 或 GateDecision。

## Acceptance scenarios

- [x] JSON-lines stdio 可直接从 envelope 产出 AuditReport，`--selftest` 离线自检通过（MCP `initialize`/`tools/list`/`tools/call` 生命周期已按 S2 scope 裁决移除，移交 S3/A4）。
- [x] resolver 快照按版本写入现有 SQLite，新 Store/new adapter 可加载，同版本不同内容拒绝覆盖。用户观察到 `saved_record=true`、`new_store_loaded=true`、`same_checksum=true`、`resolved_status=found` 和 `ResolverSnapshotConflictError`；本次未单独验证操作系统级进程重启。
- [x] AuditRuntime 通过 Persistence Port 保存报告、幂等记录和审计事件；旧 `RecordStore` 构造方式继续可用。用户观察到首次 `completed`、再次 `replayed`、报告/事件各写入一次，旧构造方式成功。
- [x] bounded evidence view 仍为只读；Audit 不写 `EvidenceItem`，不产生 `GateDecision`。用户观察到 `view_unchanged=true`、locator `pass`、`candidate_count=1`，且 Evidence/GateDecision 行数均为 0。
- [x] 存在性、撤稿、更正、locator、网络不可用 fixture 可重跑，网络不可用保持 `unknown`。用户观察到 8 个场景均符合预期，第二轮 `runs_equal=true`，网络场景保持 `unknown`。

## Invariants

- 不修改 `application.py`、共享 `contracts.py`、Evidence/Writing 路径、全局 `.ai-team/TASK.md` 或 B 线独占路径。
- 继续使用现有 SQLite `RecordStore`，不新增第二套数据库、消息总线、scheduler 或业务 Agent。
- Audit 只消费 bounded evidence view；EvidenceItem/ClaimLink/ArtifactLink 仍由 Evidence Module 管理。
- 保留既有 `AuditRuntime(store, resolver)`、CLI `audit` 命令和旧 JSON-lines envelope 兼容路径。
- 网络或 resolver 不可用时必须 fail-closed，不能把未知转换为通过。

## Decisions

- stdio 采用 transport-agnostic 的 JSON-lines 边界；MCP 协议实现按 S2 scope 裁决移交 S3/A4，不在本任务交付。
- `ResolverSnapshotRepository` 使用 `resolver_snapshot` kind 写入现有 SQLite；版本是稳定键，插入采用冲突不覆盖，checksum 用于完整性校验。
- `AuditPersistencePort` 隔离 AuditRuntime 与具体存储；`RecordStoreAuditPersistence` 是当前 SQLite 实现，保留旧构造器作为兼容入口。
- 自动化测试结果与用户验收分开记录；本账本不把本地测试通过写成用户验收通过。

## Completed

- 已实现 `AuditPersistencePort` 与 `RecordStoreAuditPersistence`，AuditRuntime 的持久化调用已改走该边界。
- 已实现 `ResolverSnapshot`、checksum 校验、`ResolverSnapshotRepository` 和从现有 SQLite 加载的 `SnapshotResolverAdapter`。
- 已实现 transport-agnostic 的 JSON-lines stdio/selftest 边界；按 S2 scope 裁决移除 MCP 协议实现。
- 已更新 CLI：快照文件先持久化，再从现有 RecordStore 加载；没有快照时继续保持不可用即 `unknown`。
- 已增加快照不可变性和 MCP 生命周期测试，保留原有 Audit fixture 测试。

## Pending

- 用户已逐步骤审阅实际实现、设计理由和任务书覆盖情况。
- 用户已自行执行 CLI、MCP stdio、快照、Persistence Port、bounded view 和 fixture 重跑场景并反馈真实输出。
- S2 promotion/合并门仍由负责人按全局路线判定；本分支未标记 accepted/done。

## Next step

完成 task-local 验收记录同步后，进行提交前覆盖审查并准备 PR 材料；S2 promotion 和合并仍等待负责人判定。

## Verification

- [x] `python -m pytest tests/test_audit_module.py -q`（使用项目运行时与 `PYTHONPATH=src`，6 passed）。
- [x] `python -m pytest tests -q`（使用项目运行时与 `PYTHONPATH=src`，全量通过）。
- [x] `python -m ruff check src tests`（通过）。
- [x] `python -m autoresearch.audit_stdio --selftest`（通过；报告 `receipt_status=completed`）。
- [x] 用户执行 CLI、JSON-lines stdio selftest、重启加载和冲突拒绝场景并确认输出；同时完成 Persistence Port、bounded view、fixture 矩阵和两轮重跑验收。
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/S2-A-AUDIT-RUNTIME.md --base main` 在本账本更新后复跑并确认 `valid`。

## Handoff note

- From: `member A`
- To: `user/team`
- 当前代码和 task-local ledger 均在 `codex/s2-a-audit-runtime`；尚未 commit、push 或创建 PR。
- 本次实现范围仅为 A3 三个已批准缺口，未修改 A1/A2 既有路径；用户验收和 promotion 判定仍未完成。
