# R-002 范围与权威

状态：target design；日期：2026-09-03；负责人：用户/项目负责人。

权威顺序：当前源码与测试 > `.ai-team/PROJECT.md`、`.ai-team/TASK.md` 与 `.project-to-act/` > `docs/ARCHITECTURE.md` > 本包 target 文档。上一轮 R-001、independent 和 skill-test 包均为历史/blocked，不得当作已批准实现。

本增量针对 0.2.0 Literature Pilot，范围是一个真实但尚待用户指定的论文检索→阅读→证据记录纵向切片，以及其运行恢复、幂等和兼容边界。包含 Runtime/Capability/Evidence 的设计合同、现状映射、迁移与验收计划；不改业务代码，不替换 SQLite，不实现远程 MCP，不承诺真实检索质量。

硬约束：恰好五个业务 Agent；Evidence/Gate/State/Handoff 是确定性服务；旧 `AutoResearchApplication` facade 在迁移窗口可运行；默认离线、fail-closed、不得伪造论文或实验结果。
