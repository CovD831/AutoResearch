# O16 Artifact Correctness

- ID: `O16-ARTIFACT-CORRECTNESS`
- Title: `Fix manuscript artifact correctness: extraction failure, dedup, delivery file`
- Status: `integrated`（2026-09-18 人工审查通过并合入 main；原 `handoff`）
- Owner: `member B`
- Next owner: `user/team`

## Goal

修复阅读链与写作链中导致产物不正确的三处缺陷：抽取失败不得伪装成合法发现；Related Work / References 去重口径与 claims 一致；交付文件与注册表最新版本不再分叉。

## Acceptance scenarios

- [x] 抽取失败表达为 `findings=[]`（空列表），不产出 "No extractable finding..." 哨兵字符串。
- [x] 抽取失败的卡不进 Related Work，改计入 `unresolved_gaps`（决策 3）。
- [x] Related Work 按 `findings[0]` 去重；References 按规范化标题去重；claims 沿用 `_unique`（三处口径一致）。
- [x] `draft()` 同时写 `MANUSCRIPT_DRAFT_v1.md`（归档）+ `MANUSCRIPT_DRAFT.md`（最新）；`revise()` 覆写 DRAFT、停写 `MANUSCRIPT_REVISION_<id>.md`（决策 1 选项 c）。
- [x] 判别力测试 6 个，改动前代码上全部 assertion 失败（判据型）。
- [x] ruff / compileall 通过。

## Invariants

- 不碰 `contracts.py`（forbidden）；用空列表表达抽取失败，不加字段。
- 不改 `unresolved_gaps` 语义（Gate 输入 `work_closed_loop`）。
- 不改 `gates.py`（O15 范围）、不接 LLM（O17 范围）。
- `agents/paper_reader.py`：早期曾越界改动，**该越界声明已撤销**（见 `docs/tasks/O16-artifact-correctness/HANDOFF.md` §「越界声明（已撤销）」——PR #23 已从根源消除消费点，本包最终改动**不含**该文件）。本行原写「已加入 allowed_paths」与 HANDOFF 撤销后的实施相反，2026-09-18 审查更正。

## Decisions

- （§10 已定，照做）交付语义选项 c；References 按标题去重；抽取失败计入 gaps。
- （实现层自定）抽取失败用 `findings=[]` 表达，不用哨兵字符串、不加字段。

## Completed

- 修复 reader_service.py：findings 空列表 + claim 诚实题录声明。
- 修复 writing_service.py：_citations 去重+跳过空、references 标题去重、gaps 计失败、draft 双写、revise 覆写。
- 修复 agents/paper_reader.py：findings 空防御。
- 新增 tests/test_artifact_correctness.py（6 判别力测试）。
- 判别力验证：改动前 6 failed 全 assertion。
- 填 L3/PROGRESS/HANDOFF/成员账本。

## Pending

- 干净环境全量复跑（移开 .env.local）+ 基线差值逐条解释。
- owner 复核 agents/paper_reader.py 越界、复核 §5 vs §8.1 措辞冲突。

## Next step

Owner 复核 → 干净全量 → commit → push `codex/o16-artifact-correctness` → PR。

## Verification

- [x] `ruff check src tests`：All checks passed。
- [x] `python -m compileall -q src`：exit 0。
- [x] `pytest tests/test_artifact_correctness.py`：6 passed。
- [x] 判别力（改动前跑新测试）：6 failed，全 assertion。
- [ ] 干净全量（移开 .env.local）——待复跑。

## Handoff note

- From: `member B`
- To: `user/team`
- Summary: O16 三处缺陷已修复 + 判别力测试 + 任务记录。`agents/paper_reader.py` 为越界改动（缺陷 A 闭环必然牵动），已在 HANDOFF 声明。本轮不 commit/push；回滚移除 4 个代码/测试文件即可。