# A2 Runtime Hardening Progress

| 日期 | 状态 | 完成事项 | 证据 | 风险/阻塞 | 下一步 |
|---|---|---|---|---|---|
| 2026-09-07 | active | 从最新 `origin/main` 建立 A2 worktree/分支，完成任务书要求映射和 L3 草案 | `codex/p1-a2-runtime-hardening`；基线 `c1dbefc` | F-1/F-2/F-3 尚未实现；failure cause 判定需先冻结 | 用户确认 L3 方案后建立 fault fixtures 和常规 pytest 回归 |
| 2026-09-08 | active | 建立可重复的 `service_started` 后进程退出 fixture；使用真实 capability API 和本地 SQLite 验证中间状态可观测 | `tests/a2_runtime_fixtures.py`、`tests/test_runtime_hardening.py`；专项 pytest：`1 passed in 2.39s`；全量 pytest（显式使用 A2 `src`）：`35 passed in 7.81s`；fixture 快照：退出码 `37`、`pending/service_started`、connector 调用 `1` | 仅完成 crash 复现；timeout、partial-write、F-1/F-2/F-3 尚未实现 | 增加 reserved/service_started/service_returned 故障矩阵，再实现 phase-aware recovery |
| 2026-09-08 | active | 用户首次运行专项测试在 pytest setup 阶段遇到 `PermissionError: WinError 5`；确认是默认 Temp 目录权限，不是 fixture 失败；已验证 worktree 内 `--basetemp` 命令可通过 | 用户实际输出：默认 `C:\Users\94461\AppData\Local\Temp\pytest-of-94461` 拒绝访问；修正命令实测：`1 passed in 3.37s` | 用户验收需使用可写临时目录重新运行 | 统一后续 Windows 验收命令的 `PYTHONPATH` 和 `--basetemp`，再继续故障矩阵 |
| 2026-09-08 | active | 用户使用修正后的命令完成真实验收；同一专项测试连续运行两次均通过，确认 crash-after-service-started fixture 在用户环境可重复运行 | 用户实际输出两次均为：`test_crash_after_service_started_is_reproducible PASSED`、`1 passed, 1 warning in 3.28s` | warning 未提供具体内容，暂记为非阻断警告；A2 其余 7 项仍未完成 | 先向用户讲解并确认下一步，再增加 reserved/service_returned/partial-write 故障场景 |
| 2026-09-08 | active | 完成 A2 生产修复、故障矩阵、诊断命令和常规回归；F-1/F-2/F-3 均有对应实现与 pytest | `src/autoresearch/storage.py`、`src/autoresearch/capability.py`、`tests/a2_runtime_fixtures.py`、`tests/test_runtime_hardening.py`、`docs/rearchitecture/worktrees/A-runtime-hardening/a2_fault_matrix.py`；全量 pytest：`48 passed in 73.32s`；fault matrix：6 场景 `overall_passed=true`，退出码 `0` | 用户最终验收和报告复核尚未完成；A1 mutation acceptance 因本地生产改动被脚本拒绝运行 | 用户运行 fault matrix 和专项测试，确认结果后准备 A2 PR 材料 |
| 2026-09-08 | active | 完成实现收尾和交接材料；九项功能验收条款已勾选，保留用户验收门禁 | `TASK.md`、`L3.md`、`HANDOFF.md`、`PROGRESS.md`；自动化证据沿用上行记录 | `.a2-pytest-temp/` 是测试临时目录，未能由受限清理命令删除，明确不纳入提交；用户完整 fault matrix 尚未运行 | 执行 `node .ai-team/check.mjs --base origin/main`，再交给用户运行最终命令 |
| 2026-09-08 | handoff-prep | 用户已运行完整 fault matrix，六个场景全部通过并确认开始 PR；A2 独立任务记录和 PR 草稿已准备 | 用户实际报告：`overall_passed=true`、退出码 `0`；PR 草稿和暂存清单保存在 F 盘项目笔记目录 | 全局 `.ai-team/TASK.md` 按用户确认排除在 A2 PR 外；`.a2-pytest-temp/` 与 fault matrix 生成 SQLite/日志不纳入提交 | 按暂存清单 stage，运行 task-local check，提交并推送 A2 分支，然后创建 PR |
| 2026-09-09 | integrated | Owner 审查合并 PR #5：F-1 CAS-on-snapshot、F-2 phase 决策表、F-3 分类与 diagnostics 均与冻结 L3 一致；分支基于 `c1dbefc`，与 PR #4/#6 后的 main 干净合并 | Owner approve 记录在 PR #5；合并结果上独立复现：全量 `69 passed`、ruff 通过、check.mjs `--task` valid（8/8）、fault matrix 6 场景 `overall_passed=true` | `recover_pending` 的 `outcome_status` 参数在 phase 决策下已成死参数（API 清理归 owner 后续）；P1-A 注册表行同步修正 | Project-to-Act 进度历史、注册表与共享 TASK.md 由 owner 同步 |

## 记录规则

- 每一步写明任务书条款、变更路径和验证命令。
- 自动化测试结果不替代用户真实验收。
- 遇到共享边界问题先记录，不直接修改 P1-B、`application.py`、共享 `contracts.py` 或全局 `.ai-team/TASK.md`。
