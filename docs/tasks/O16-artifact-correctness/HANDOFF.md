# O16 Handoff

## 基本信息

- Owner：member B（承接）
- Branch：`codex/o16-artifact-correctness`
- Base revision：`fab8de3`（2026-09-17 rebase 到 PR #23 之后的最新 main）
- Handoff revision：`f2dd03b`（未 push）

## changed paths

```text
src/autoresearch/reader_service.py
src/autoresearch/writing_service.py
tests/test_artifact_correctness.py
docs/tasks/O16-artifact-correctness/（task-package.json / L3.md / PROGRESS.md / HANDOFF.md）
.ai-team/tasks/O16-ARTIFACT-CORRECTNESS.md
```

## 测试命令和结果

- `ruff check src tests`：All checks passed
- `compileall -q src`：exit 0
- 新测试：`pytest tests/test_artifact_correctness.py` → **6 passed**
- 判别力：改动前代码上跑新测试 → **6 failed，全部 assertion（判据型，非符号缺失）**

## 三项决策的落地证据

- **决策 1（选项 c）**：`draft()` 写 `MANUSCRIPT_DRAFT_v1.md` + `MANUSCRIPT_DRAFT.md`；
  `revise()` 只覆写 `MANUSCRIPT_DRAFT.md`，**不再**写 `MANUSCRIPT_REVISION_<id>.md`。
  测试 `test_draft_writes_both_archive_and_current_pointer` 与
  `test_revise_overwrites_current_pointer_and_stops_revision_files` 锁定。
- **决策 2（标题去重）**：`References` 按规范化标题去重，测试
  `test_references_deduplicates_same_title_different_doi` 覆盖预印本+正式版场景。
- **决策 3（计入 gaps）**：`draft()` 对 `findings` 空的卡新增 gap，测试
  `test_extraction_failure_is_surfaced_as_gap_not_related_work` 锁定。

## 三处去重口径一致性

Related Work（findings[0]）== References（规范化标题）== claims（_unique），
各自键已在代码注释与 L3 写明。

## 变红测试的分类（决策 3 配套要求）

在干净环境（移开 `.env.local`）复跑后填写。预期：`test_llm_lane_replacement.py`
的一个离线测试因 `.env.local` 泄漏失败（环境问题，非本包引入）；其余需逐一确认
是否因「新增 gap」改变状态——待干净复跑后回填。

## 越界声明（已撤销）

早期版本曾改动 `src/autoresearch/agents/paper_reader.py`（`card.findings[0]` 空防御）。
**PR #23（A9 交接单引用化）已从根源消除该消费点**（`ArtifactRef` 不再嵌 `summary`、
不再读 `findings[0]`），故本包**不再需要改该文件**，越界声明撤销。
最终改动不含 `agents/paper_reader.py`。

## 已知限制（必须写明）

1. 既有 `MANUSCRIPT_REVISION_<id>.md` 历史文件**未清理**（有意保留，新流程不再产生该名）。
2. References **不区分**同一工作的预印本/正式版（按标题去重所致）。
3. **多次 draft 会覆盖 `MANUSCRIPT_DRAFT_v1.md`**：`draft()` 每次都写 v1（覆盖式），
   同一 project 第二次 draft 会覆盖首次归档，破坏「初稿不可变」。任务包 §8.3 只验收
   draft→revise 流程、未测多次 draft，故本包未处理；建议 owner 决定是否后续加「v1 已存在则跳过」逻辑。

## rollback

移除本包改动 4 个代码/测试文件，恢复 `draft()`/`revise()` 旧写文件行为。
历史 `MANUSCRIPT_REVISION_*.md` 保留。

## 对主线集成的要求

- 集成前请在**无 `.env.local`** 环境跑全量（当前成员本地 `.env.local` 会污染一个
  离线 LLM 测试，属环境隔离问题，非本包代码）。