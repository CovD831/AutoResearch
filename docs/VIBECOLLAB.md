# VibeCollab 协作约定

## 1. 来源与安装

本项目使用 redmaplewww/vibecollab 仓库中的 skills/repo-task-sync skill。安装时锁定上游 main 提交 f13ece435e41f143ccfc54dfde4c85ff8c05510e；本地安装路径由 Codex skill-installer 管理。

VibeCollab 采用纯文件、Git-native 协作。当前仓库没有经确认的 private remote，因此使用 non-private mode，不保存原始会话正文。

## 2. 当前任务事实

- AGENTS.md：入口和协作规则。
- .ai-team/PROJECT.md：稳定项目约束。
- .ai-team/TASK.md：当前单写者任务、验收条件、状态和 handoff。
- .ai-team/check.mjs：检查任务事实、变更范围和交接。
- .ai-team/archive：完成任务归档。

代码修改前先读 .ai-team/TASK.md。一个任务同一时间只有一个 writer。另一个协作者应提交结构化 handoff，而不是复制聊天上下文。

## 3. 与 Project-to-Act 的分工

- .ai-team：当前 Git 任务的短周期协作事实。
- 根 .project-to-act：AutoResearch 产品跨阶段目标、版本、功能状态和验收。
- paper-projects/<id>/.project-to-act：单篇论文项目的目标、进度、证据和 Gate。

三者不能互相替代。普通 commit 细节不写入 Project-to-Act；产品范围、里程碑、版本和验收变化才更新长期账本。

## 4. 完成检查

    node .ai-team/check.mjs --base main

检查通过后，TASK.md 应记录：

- 实际变更。
- 验证命令和结果。
- 未验证边界。
- 后续 handoff。
- 与代码同一 commit 的最终任务状态。

不要在 TASK.md 粘贴密钥、完整论文全文或原始用户会话。
