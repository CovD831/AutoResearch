# P1-A Runtime Lane

这是成员 A 的长期 Runtime worktree 任务包。它代表一条责任线，不是一个巨大 PR。

## 使用方式

1. 从 `origin/main` 创建 `codex/p1-runtime-recovery` worktree。
2. 先实施 A1；A1 提交审查后，可以继续 A2，不必等待负责人合并。
3. 后续任务必须在前置任务合并后 rebase 到最新 `main`。
4. S2/S3/S4 任务在前置 Promotion Gate 前只能准备或标记 `speculative`。

## 责任边界

成员 A 负责 Runtime、Capability、Recovery、Audit runtime 和 Benchmark runtime；不得修改成员 B 的独占路径、`application.py`、共享 `contracts.py` 或项目级账本。

## 任务入口

见 [TASK-QUEUE.md](TASK-QUEUE.md)、[TASK-SPECS.md](TASK-SPECS.md)、[lane-manifest.json](lane-manifest.json) 和各任务包目录。当前 A1 详细包仍是 `docs/tasks/P1-A-runtime-recovery/`。
