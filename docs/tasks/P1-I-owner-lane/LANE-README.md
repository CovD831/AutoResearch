# Owner 线（P1-I Owner Lane）说明

- 职责边界：成员 PR 审核与合并窗口管理、小修不打回直接补 follow-up PR、独占裁决（空结果语义等）、主线集成任务（I0–I4）、promotion gate 裁决。
- 不做：成员 lane exclusive 源文件的直接开发（冲突经 handoff 提请）；与成员任务重复的实现工作。
- 任务队列见同目录 `TASK-QUEUE.md`；裁决与集成记录同步 `.ai-team/TASK.md`、`docs/rearchitecture/TASK-PACKAGE-REGISTRY.md` 与 Project-to-Act 进度历史。
- 与成员 lane 的关系：A/B lane 产出成员 PR；Owner lane 消费成员 PR（审/补/合并）并推进跨 lane 集成与裁决。三条 lane 并行，互不阻塞开发。
