# P1-A Handoff

## 基本信息

- Owner：成员 A
- Branch：`codex/p1-runtime-recovery`
- Base revision：`c0f8fbce89c8094fb02c022b2918a2c04e04380e`
- Handoff revision：以包含本文件的最新分支提交为准

## 必填内容

- L3 文件：`L3.md`
- changed paths：`src/autoresearch/capability.py`、`src/autoresearch/storage.py`、`src/autoresearch/invocation_contracts.py`、A1 测试/fixture、`parity_report.py`、本任务账本文件。
- 测试命令和结果：`ruff check src tests docs/rearchitecture/worktrees/A-runtime-recovery/parity_report.py` 通过；`compileall -q src` 通过；A1 专项 9 passed；`pytest -W error -q` 27 passed。
- parity report：运行 `python docs/rearchitecture/worktrees/A-runtime-recovery/parity_report.py` 生成 `parity-report.json`，报告 `overall_equal=true`，覆盖 paper、Evidence、Wiki、diagnostics、receipt 和幂等行的脱敏语义投影。
- recovery evidence：`tests/test_recovery_contract.py` 覆盖 pending 显式 fail、跨 `RecordStore` 实例 replay、pending 行枚举和 legacy/target parity；`tests/test_capability_adapter.py` 覆盖 reserve-first、exact replay、冲突、空结果/未知结果和 timeout。
- rollback 方式：整体回滚 A1 提交即可；旧 `PaperSearchService` 和 `remember_idempotent` 保留，删除 adapter/合同/fixture/测试不会影响旧 facade。
- 已知限制：尚未接线 `AutoResearchApplication`；真实网络 connector、跨进程锁、partial-write fault injection 和 Evidence admission 仍留给后续任务/主线集成。
- 对主线集成的要求：保持 `application.py`、共享 `contracts.py`、Evidence/Writing/Pipeline 路径不变；负责人先审查 B-1 evidence 表示，再将 adapter 接入 Evaluation Section Pipeline，并在 A 合并后让 P1-B rebase。
- 未解决的决策：S1 promotion 前需确认 receipt/idempotency 写入者表；B-1 需选择 non-persisting search 或 legacy reference/reconcile；是否把 parity JSON 固定纳入主线 evidence 目录。

## 自动审查与负责人审查

- 机器人报告：task-local `node .ai-team/check.mjs --task .ai-team/tasks/P1-A-RUNTIME-RECOVERY.md --base main` 通过；项目级 `--base main` 暂阻塞，因为全局 `.ai-team/TASK.md` 由主线负责人维护。
- 项目负责人结论：待审查。
