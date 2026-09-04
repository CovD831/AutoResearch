# AutoResearch 团队 SOP 采用说明

## 公共基线

AutoResearch 采用公共团队工程 SOP：

- 仓库：`CovD831/team-engineering-sop`
- 采用版本：`e81d2eb` 初始版本
- 作用：提供与项目、人数和 AI 工具无关的任务包、worktree、PR、审查、合并和 Gate 流程。

公共 SOP 是参考基线；AutoResearch 的具体路线、成员责任线和 MVP 条件仍以本仓库的 Project-to-Act、`.ai-team`、重构文档和任务注册表为准。

## 项目适配

AutoResearch 增加以下项目专用规则：

- A/B 两条长期 lane worktree；
- task-local ledger 和异步 stacked task；
- R004/R005 与 UD-006/UD-007 架构约束；
- 负责人 I0–I4 集成线；
- `MVP-CLOSED-MINIMAL-E2E` 闭环 Gate。

这些规则由 `skills/autoresearch-team-workflow/` 提供负责人侧 AI 协作支持。成员不需要安装该项目 skill，只需使用仓库内的 `repo-task-sync` 规则和所分发的 lane package。

## 版本同步

公共 SOP 发生变化时，负责人评估影响并更新本文件的采用版本；不得把公共 SOP 的变更默默当作 AutoResearch 项目决策。
