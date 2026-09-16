# O16 Progress

## 基本信息

- Package：`O16-ARTIFACT-CORRECTNESS`
- Branch：`codex/o16-artifact-correctness`
- Base：`b83cc56`
- Owner：member B（承接）

## 进度

- [x] 缺陷 A：抽取失败结构化（`findings=[]`），写作侧跳过 + 计入 gaps
- [x] 缺陷 B：Related Work / References 去重（与 claims 口径一致）
- [x] 缺陷 C：DRAFT_v1.md 归档 + DRAFT.md 恒最新，停写 MANUSCRIPT_REVISION_*
- [x] 判别力测试：`tests/test_artifact_correctness.py` 6 用例
- [x] 判别力验证：新测试在改动前代码上 6 个全部 assertion 失败（判据型）
- [x] ruff / compileall 通过
- [ ] 全量回归（含 .env.local 隔离后的干净复跑）
- [ ] HANDOFF 交 owner

## 验证结果

| 项 | 结果 |
|---|---|
| ruff check src tests | All checks passed |
| compileall -q src | exit 0 |
| 新测试 tests/test_artifact_correctness.py | 6 passed |
| 判别力（改动前跑新测试）| 6 failed，全 assertion（判据型）|

## 已知事故记录（如实）

判别力验证时曾用 `git checkout b83cc56 -- <src>` 还原改动，因未 commit/stash 导致
4 处修复丢失，后已逐一重做并 **git add 暂存**。最终状态已核对 4 文件齐备。

## 待办

- 干净复跑全量（移开 .env.local，因它会污染 LLMService 离线测试）。
- 按 O16 任务包 §8.6 解释基线差值（新增 gap 是否引起下游测试变红）。