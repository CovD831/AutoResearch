# Current Task

- ID: `AR-002`
- Title: `Publish the public repository and add the detailed assignment task book`
- Status: `done`
- Owner: `zzg`
- Next owner: `user/team`

## Goal

把已完成的 AutoResearch foundation 发布到 GitHub public 仓库，并在仓库内增加可分配的模块化任务拆解书。任务书必须区分当前基础能力、待开发能力和真实论文/生产外部条件，不把规划写成已验收功能。

## Acceptance scenarios

- [x] `redmaplewww/AutoResearch` 已创建且可见性为 `PUBLIC`。
- [x] 已将包含 foundation 的 `main` 和保留开发上下文的 feature branch 推送到远程，未使用强制覆盖。
- [x] `docs/AutoResearch_任务拆解书.md` 覆盖治理、合同、证据、工作流、五 Agent、检索、阅读、创新、执行、写作、审核、知识、画像、自进化、API/UI、安全、运维、真实试点和生产化模块。
- [x] 每个模块至少拆到有 ID、依赖、负责人建议、规模、交付物和验收门的子任务粒度。
- [x] README、Project-to-Act 和 VibeCollab 任务状态指向新的任务书，且保留 AR-001 foundation 的非声明边界。
- [x] 任务书和协作文件不包含 token、密钥、私有来源、原始提示或虚构外部结果。

## Invariants

- public 仓库只发布当前允许公开的代码、文档和证据摘要；`.env.local`、`.venv`、运行时目录和嵌套参考仓库继续被忽略。
- 默认分支必须包含可运行 foundation；不能只发布空仓库或仅发布规划分支。
- 任务书是分配入口，不取代 `PROJECT_FEATURES.md` 的功能状态唯一性，也不改变五业务 Agent 边界。
- 未完成真实论文试点、实验、生产数据库、Web UI 和灾备的内容必须保持“待开发/外部阻塞”。

## Decisions

- 使用已认证的 `redmaplewww` GitHub 账号创建 `redmaplewww/AutoResearch`，设置为 public；不改用不确定的组织或仓库名。
- 由 `feat/ar-002-publish-task-plan` 承载本次文档和任务账本变更，完成后合并到 `main`；不重写 AR-001 提交。
- 任务拆解采用 M00–M17 模块和稳定子任务 ID，使用 W0–W7 波次表达依赖；每项以一个交付物和一个验收门为最小分配单位。

## Completed

- 创建 public 仓库：`https://github.com/redmaplewww/AutoResearch`。
- 将 `5fe43f4` foundation 快照推送到 `main` 和 `feat/ar-001-foundation`。
- 创建 `docs/AutoResearch_任务拆解书.md`，包含模块总览、详细子任务、角色/规模建议、波次、分配包、交接模板、Definition of Done 和分配台账。
- README 增加任务拆解书入口。
- 将本次交付切换到新的 VibeCollab 任务 AR-002，保留 AR-001 完成状态和非声明。

## Pending

- GitHub 分支保护、CI workflow、Issue/PR 模板和 release checklist 仍由 M00-05/M00-06 分配开发。
- 用户/团队需要依据任务书填写 owner、分支/PR、目标日期和实际 evidence ID。
- M16 真实论文试点仍等待 idea、领域、目标 venue、授权全文和实验资源边界。

## Next step

团队从 M00-05、M01-02、M02-07、M04-04 和 M16-01 中选择 owner，按任务书的交接模板建立第一个执行任务；真实试点前继续保持 Preview 边界。

## Verification

- [x] `gh auth status` 和 `gh api user --jq .login` — 已确认登录账号为 `redmaplewww`。
- [x] `gh repo view redmaplewww/AutoResearch --json visibility,isEmpty,defaultBranchRef,url` — 仓库为 `PUBLIC`，foundation 已进入 `main`。
- [x] `git push -u origin main` — 成功。
- [x] `git push -u origin feat/ar-001-foundation` — 成功。
- [x] `node .ai-team/check.mjs --base main` — AR-002 acceptance 6/6；本次运行在最终提交前已验证任务状态和变更范围。
- [x] Project-to-Act root validate、Ruff、`pytest -W error -q`、CLI doctor — root ledger valid；Ruff passed；18 tests passed；doctor 返回 `ok: true` 且 Agent 数为 5；基础快照已有 84% coverage 记录。

## Handoff note

- From: `zzg`
- To: `user/team`
- Summary: public GitHub 仓库已建立，foundation 已推送；详细任务拆解书已入库。后续按 M00–M17 子任务分配，任何真实论文或生产声明都必须重新通过对应 Gate。
