# A2 Runtime Hardening Handoff

## 基本信息

- Owner：`member A`
- Branch：`codex/p1-a2-runtime-hardening`
- Base revision：`c1dbefc`
- Handoff revision：提交前暂存快照（commit 后以 Git revision 为准）
- 实际 revision：PR head `0730570`（A2）；合并 commit `4b7c7fa`（2026-09-09，PR #5，owner 在合并结果上复核通过）

## 必填内容

- L3 文件：`L3.md`
- changed paths：
  - `src/autoresearch/storage.py`
  - `src/autoresearch/capability.py`
  - `tests/a2_runtime_fixtures.py`
  - `tests/test_runtime_hardening.py`
  - `docs/rearchitecture/worktrees/A-runtime-hardening/`
  - `docs/tasks/P1-A-runtime-lane/tasks/A2-runtime-hardening/`
  - `.ai-team/tasks/P1-A2-RUNTIME-HARDENING.md`
- 测试命令和结果：
  - `ruff check src tests`：通过。
  - A2/A1 相关 pytest：24 passed。
  - 全量 `pytest -W error -q`：48 passed。
  - fault matrix：6 个场景，`overall_passed=true`，退出码 0。
  - 用户已运行完整 fault matrix；六个场景全部通过，`overall_passed=true`，退出码 0。
- fault matrix / diagnostic report：`docs/rearchitecture/worktrees/A-runtime-hardening/a2_fault_matrix.py`；报告样例为 `a2-fault-matrix-report.json`，schema 为 `p1-a2-fault-matrix/v1`。
- rollback 方式：A2 合并后使用 `git revert <A2-merge-commit>` 回滚；在合并前不对用户已有提交做 destructive 操作。
- 已知限制：故障矩阵使用本地 SQLite 和 fake connector，不代表真实网络供应商行为；A1 mutation acceptance 要求干净生产工作树，因此在当前 A2 未提交改动存在时会拒绝运行；pytest 生成的 `.a2-pytest-temp/` 为本地临时目录，不纳入提交。
- 对主线集成的要求：保持 A1 兼容语义，不修改 P1-B 独占路径
- 未解决的决策：无；failure cause 继续写入 diagnostics/audit，不新增第二套状态字段。

## 用户验收门禁

- [x] 用户确认 A2 实现方案并授权一次性完成开发。
- [x] 用户运行或复核故障矩阵。
- [x] 用户确认测试结果后，允许准备第二个 PR。
