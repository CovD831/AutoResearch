# 论文项目目录

每个真实论文项目使用独立目录：

```text
paper-projects/<project-id>-<slug>/
```

创建步骤：

1. 复制 `_template`，不要直接在 `_template` 中开展真实研究；
2. 修改 `PROJECT_MANIFEST.yaml` 的项目 ID、标题、负责人和路径；
3. 将模板内 `.project-to-act` 的“模板”状态改为真实项目目标、范围和验收标准；
4. 运行 Project-to-Act 校验脚本；
5. 只有校验通过后才能启动 LangGraph 项目线程。

边界：`.project-to-act` 管理目标、范围、功能状态、版本和验收；LangGraph checkpoint 管理节点运行状态；evidence ledger 管理证据和 Gate 历史。三者不复制同一事实字段。

模板入口：[`_template/README.md`](_template/README.md)
