# Parallel task ledgers

本目录保存每个并行代码任务的 task-local ledger。`.ai-team/TASK.md` 只保存当前集成批次、全局队列和负责人动作；成员不要互相覆盖同一个 task-local ledger。

每个 ledger 必须包含：`Goal`、`Acceptance scenarios`、`Invariants`、`Decisions`、`Completed`、`Pending`、`Next step`、`Verification`、`Handoff note`。

任务包 ZIP 是传输格式；解压后的 `task-package.json`、`L3.md`、`PROGRESS.md`、`HANDOFF.md` 和对应 ledger 必须随任务代码提交。
