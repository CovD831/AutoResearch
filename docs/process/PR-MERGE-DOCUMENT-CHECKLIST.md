# AutoResearch PR 合并后文档维护准则

## 目的

保证成员 PR 合并后，代码、任务状态、全局注册表和项目长期账本保持一致。本文是负责人调用 `autoresearch-doc-maintenance` skill 时的人工可读检查入口。

## 成员提交 PR 前

成员必须在同一个 PR 中更新：

- 代码和测试；
- `.ai-team/tasks/<TASK-ID>.md`；
- 任务包的 `L3.md`、`PROGRESS.md`、`HANDOFF.md`；
- 可重跑的验证命令和证据路径。

## 负责人审核 PR 时

先完成代码审查和 Merge Gate，不要在未合并前把项目长期状态标记为完成。确认：

- changed paths 未越界；
- 验收场景与测试结果一致；
- 失败、unknown、blocked 和 rollback 有记录；
- 没有未经授权的共享合同或架构变化。

## 合并后立即维护

合并后调用文档维护 skill，按以下顺序：

1. 记录 merged commit 和 PR/task ID；
2. 将任务状态更新为 `integrated`；
3. 验收证据通过后再更新为 `accepted`；
4. 更新 `TASK-PACKAGE-REGISTRY.md` 和 `.ai-team/TASK.md` 的队列、依赖和下一任务；
5. 只有项目里程碑、功能状态、版本或 Gate 发生变化时，才更新对应 Project-to-Act 文件；
6. 如果架构或范围发生变化，新增 decision record，不覆盖旧决策；
7. 如果任务合同发生变化，重新生成对应 lane ZIP；普通代码进度不重新打包。

## 任务状态含义

```text
submitted → reviewing → integrated → accepted
                         ↘ changes-requested / blocked
```

`integrated` 只表示已经进入目标分支；`accepted` 还要求验收条件和新鲜证据全部通过。

## 最小更新集合

普通 PR 合并通常只需更新：

```text
.ai-team/tasks/<TASK-ID>.md
docs/rearchitecture/TASK-PACKAGE-REGISTRY.md
.ai-team/TASK.md
```

阶段晋级时再增加：

```text
.project-to-act/PROJECT_PROGRESS.md
.project-to-act/PROJECT_FEATURES.md
.project-to-act/PROJECT_ACCEPTANCE.md
```
