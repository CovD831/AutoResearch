# R-001-08 文档维护与目录规则

## Canonical owner

| 内容 | 唯一文档 |
|---|---|
| R-001 目标、边界、迁移和审查 | 本目录 `README.md` 与分文件 |
| 当前运行事实 | `docs/ARCHITECTURE.md`、源码、测试 |
| 项目范围/进度/验收 | `.project-to-act/PROJECT_*.md` |
| 当前短周期任务 | `.ai-team/TASK.md` |

摘要文件只能链接到 canonical owner，不能复制整段策略。

## 状态规则

- `current`：代码、测试和账本已共同证明。
- `target`：设计意图，未实现。
- `proposed`：等待决策或晋级证据。
- `superseded`：由后续 ADR 替代，保留链接和原因。

## 复审触发

- 新增第二个 capability consumer。
- 修改证据写入权、Runtime 部署边界或 checkpoint 合同。
- S1 parity 失败或出现独立 reviewer blocking finding。
- 引入插件安装、版本共存、隔离、热替换或远程执行。

## 下一个增量

S1 Paper Search Adapter 的 task-local L3 contract。负责人：用户/team 指定；触发条件：第 9 节三项产品边界确认。
