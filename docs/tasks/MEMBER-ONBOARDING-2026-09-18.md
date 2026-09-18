# 成员开工须知（2026-09-18）

> 面向成员 A / 成员 B / Owner 的派发前置说明。**先读完本页再开工。**
> 本页只讲「怎么开工/怎么交」，任务内容一律以各包 `task-package.json` 为准。

---

## 0. 现状基线

- 主仓：`https://github.com/CovD831/AutoResearch`
- 派发基线：`main`
- **唯一派发依据 = `docs/tasks/<MODULE>/tasks/<ID>-WIRE/task-package.json` 的 `status` 字段**（`docs/rearchitecture/TASK-PACKAGE-REGISTRY.md` 下方表格是历史世代，不再作为派发依据）。
- `status: ready` 才能接；`status: blocked` **不要开工**，卡点写在包内 `blocked_reason`，等 owner 裁决后翻 `ready`。

---

## 1. 提 PR 的方式（**最关键，搞错会丢掉 AI 审查**）

**不要从你的 fork 开 PR。** 本仓 `.github/workflows/ai-review.yml` 用「head 仓库是否等于本仓」判断，
不等则整条审查链跳过。原文（`ai-review.yml:19-22`）：

> Fork pull requests cannot read repository secrets, so they are skipped explicitly …
> Member PRs come from forks, so their reviews need to be triggered from a same-repo branch …

判据代码在 `ai-review.yml:107-113`（`if [ "$head_repo" = "$REPO" ]` → `same_repo`），
`:145` 处 `if: needs.resolve.outputs.same_repo == 'true'` 直接 gate 掉整个 review job。

⚠️ **手动重放救不了 fork PR** —— `workflow_dispatch` 路径同样要 `gh api repos/$REPO/pulls/$N` 取
`head.repo.full_name`（`:91-95`），fork 照样 `same_repo=false`。

**正确做法**：接受 `CovD831/AutoResearch` 的协作者邀请（permission = write，**需在 GitHub 上点接受，未接受不算**）后，**直接在主仓建分支**：

```bash
git clone https://github.com/CovD831/AutoResearch
cd AutoResearch
git checkout -b <包内 branch 字段> main
```

分支名用包内 `branch` 字段，不要自创。推上去后从**主仓分支**开 PR 到 `main`。

---

## 2. 必须带任务账本（否则必需检查必红）

`scripts/check_pr_contract.py` 的规则（实测）：

- `:33` 禁止改动 `var/` 下的产物路径，否则直接 fail。
- `:37-45` **只要 PR 里有产品改动，就必须带一份 `.ai-team/tasks/<ID>.md` 账本**。
  「产品改动」= 路径不以 `.ai-team/`、`.github/`、`docs/`、`scripts/` 开头的改动。
  所以**你的 `src/` / `tests/` 改动一定需要账本**。
- 每个账本还会被 `node .ai-team/check.mjs --task <路径> --base <base>` 逐份校验。

### 账本的硬格式（`.ai-team/check.mjs` 实测）

**元数据 5 个字段，一个不能少、不能为空**（`check.mjs:109-118`，字段名区分大小写）：

```
- ID: `<TASK-ID>`
- Title: `<一句话>`
- Status: `reviewing`
- Owner: `<你的名字>`
- Next owner: `<下一手；status 不是 handoff 时可写 unassigned>`
```

⚠️ **格式陷阱（实测踩过，PR #35 就是栽在这）**：字段解析正则是
`` ^- <名称>: `([^`]+)`$ ``（`check.mjs:62-65`，**行尾带 `$` 锚**）。
**闭合反引号后必须立刻换行**。写成 `` - Status: `reviewing`（注解） `` ⇒ 解析为空 ⇒
报错是 `TASK.md is missing metadata: status`，**看起来像漏了字段，实际是格式错**。

⚠️ **第二条陷阱**：报错信息里的文件名被硬编码成 `TASK.md`（`check.mjs:118` 字面量），
即使校验的是你那份 `.ai-team/tasks/<ID>.md`。**别按它给的文件名去找问题。**

**`Status` 只能是这些值之一**（`check.mjs:29-47`）：
`planning` `planned` `waiting-for-gate` `ready-next` `ready` `active` `active-next`
`submitted` `reviewing` `changes-requested` `speculative` `integrated` `accepted`
`handoff` `blocked` `superseded` `done`

附带规则：`active` / `handoff` / `blocked` / `done` 要求 `Owner` 不能是 `unassigned`；
`handoff` 要求 `Next owner` 已指派；`done` 要求所有验收与验证复选框都打勾。

**必须出现的 9 个小节，且不能为空**（`check.mjs:17-27`，标题要精确一致）：

```
## Goal
## Acceptance scenarios
## Invariants
## Decisions
## Completed
## Pending
## Next step
## Verification
## Handoff note
```

**复选框格式**（`check.mjs:133-139`）：`## Acceptance scenarios` 下**至少要有一条**
`- [ ] ` 或 `- [x] ` 开头的行；`## Verification` 同格式。

---

## 3. 验收命令：先用解释器自检

每个包的 `acceptance_commands` 字段是**唯一权威**，直接照抄。其中：

- 第 1 条 = 全量回归（前置，不是判据）
- **第 2 条 = 本包的判别力测试（唯一判据型命令）**
- 第 3 条 = lint
- 第 4 条 = `reach.py` 可达性报告（**附带项，单独不构成判据**）

⚠️ **第 4 条目前在成员侧跑不了**：`reviews/island-audit-2026-09-18/` 整个目录
**尚未入库**（`git ls-files` 计数为 0），clone 之后拿不到 `reach.py`。
它是**附带项、不影响验收**——成员侧直接跳过第 4 条即可，以第 1/2/3 条为准；
需要看可达性报告时向 owner 要。该目录是否入库由 owner 另行决定。

⚠️ **先自检解释器**。裸 `python` / `python3` 可能指向一个**没装项目依赖**的解释器，实测报：

```
ModuleNotFoundError: No module named 'langgraph'
No module named ruff
```

开工第一步先跑：

```bash
python -c "import langgraph, pytest, ruff; print('ok')"
```

报错就换成你环境里装了依赖的那个解释器（owner 侧沙箱用
`/Users/abab/.workbuddy/binaries/python/envs/default/bin/python`）。详见各包 `acceptance_commands_note`。

---

## 4. 判别力自证（**本轮新增的硬要求**）

本轮起，每条判据都必须绑定一条**可执行命令**，且该命令**必须在「未接线」的基线上失败**。
原因：此前 10 个包共用同一组三条通用命令，**在完全没接线的树上就全绿**，判据实际只写在散文里。

每个 `ready` 包都要求你交付一个**判别力测试**：

- 路径见包内 `deliverables`（每包 exclusive，不要与其他包合用一个文件）
- 短路形态、变红的断言点、自证方法见包内 `discriminating_power` 字段
- 该测试文件已在包内 `allowed_paths` 里，不会越界

**交付时随 PR 附上两段输出**：

1. 在**未接线基线**上跑第 2 条命令 → 必须**失败**
2. 接线后跑同一条 → 必须**通过**

且失败必须是**判据型**（断言不成立，如 `AssertionError`），
**不得是符号缺失型**（`ImportError` / `AttributeError` / collection error 指向「接线后才存在的符号」）——
后者只证明代码不存在，不证明判据抓得住缺陷。

---

## 5. 边界与提交纪律

- `allowed_paths` / `forbidden_paths` 是硬边界。`contracts.py` **全包禁改**；`graph.py` 仅 `M04` / `M08` 合法；`agents/base.py` 除 `M04` / `M08` 外全禁。
- 不得 `--no-verify`，不得 force push 到共享分支。
- **不要读仓库或项目的 `.env`**，不要把任何 key 写进代码、测试或提交信息。
- 提交信息里凡是「已通过/已修复」的声称，都要能对应到你自己跑过的命令输出。

---

## 6. 卡住怎么办

- 包内 `status: blocked` 的**不要开工**。
- 开工后方向确认不了 → 回一句「卡在哪、缺什么、我的两个候选方案」，**不要静默硬做**。
- 不确定某条判据怎么核对 → 问，不要自己放宽。
