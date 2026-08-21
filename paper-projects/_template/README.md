# 论文项目模板

这是 AutoResearch 的论文项目种子，不是一个已经开始的真实论文项目。复制后必须替换所有 `PAPER-TEMPLATE`、`待填写` 和示例路径。

## 使用顺序

1. 填写 `PROJECT_MANIFEST.yaml`；
2. 填写 `.project-to-act/PROJECT_OVERVIEW.md` 的目标、范围、非目标和验收边界；
3. 在 `00_intake/IDEA.md` 保存原始 idea，禁止后续覆盖；
4. 总控 Agent 生成 `01_scope/RESEARCH_CHARTER.md`；
5. 审核 Agent 通过 G0–G3 后，论文搜索 Agent 才能执行正式检索；
6. 每个 Agent 只通过 `handoffs/` 的结构化 envelope/result 交接；
7. 所有重要主张绑定 `evidence/` 中的 evidence ID；
8. 在阶段性里程碑更新 `.project-to-act`，普通运行事件不写入项目账本。

## 目录职责

| 目录 | 内容 |
|---|---|
| `.project-to-act/` | 本论文项目唯一治理账本 |
| `00_intake/` | 原始 idea、人工输入、约束 |
| `01_scope/` | 研究章程、假设、变量、验收标准 |
| `02_literature/` | 检索协议、搜索运行、筛选、阅读队列 |
| `03_innovation/` | 创新候选、最近似工作、反证结果 |
| `04_execution/` | 工作包、运行清单、结果引用 |
| `05_writing/` | 提纲、稿件、图表、参考文献 |
| `06_review/` | 审核意见、修订日志、Gate 决定 |
| `07_delivery/` | 本地交付、复现包和最终清单 |
| `evidence/` | 证据 manifest 与 bundle；大对象仅保存受控引用 |
| `handoffs/` | HandoffEnvelope/HandoffResult |
| `state/` | 人类可读的状态投影，不是 checkpoint 规范源 |
| `knowledge-links/` | 指向论文/经验/知识库的稳定 ID |

## Project-to-Act 校验

在复制后的论文项目根执行：

```powershell
python C:\Users\zzg\.codex\skills\project-to-act\scripts\init_project_management.py --project-root . --validate
```

校验失败时不得开始研究运行，也不得把模板状态写成真实项目完成状态。
