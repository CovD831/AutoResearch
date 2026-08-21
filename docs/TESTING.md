# 测试与验收

## 1. 当前自动化结果

基础测试覆盖 18 个场景，当前语句覆盖率 84%：

- Agent registry 恰好五个。
- 自交接、超长上下文被拒绝。
- Gate 按独立来源去重并 fail-closed。
- L4 缺人工批准返回 INTERRUPT。
- 明确打回返回 DENY；失效证据不再计分。
- 状态机拒绝从 INTAKE 越级到 DRAFT_WRITTEN。
- Wiki+Graph 分区和跨区边负例。
- 项目模板实例化且不覆盖已有项目。
- 推断画像置信度上限。
- 自进化 proposal-only。
- 工作包无证据不能完成。
- 无论文在搜索后停止。
- 摘要可形成阅读卡和缺口稿，但 L3 阻断。
- 陪读答案带 locator/evidence。
- 修改版本继承证据且不可发布。
- 全文 + E3 实验 lineage 可到 DRAFT_REVIEWED。
- L4 interrupt 可用同 thread 恢复。
- FastAPI、CLI doctor 与秘密摘要边界。

执行：

    .venv\Scripts\ruff.exe check src tests
    .venv\Scripts\pytest.exe

## 2. 自动化没有证明什么

本套测试没有证明：

- 三个外部论文源在所有网络/限流情况下可用。
- 检索召回、总结正确率或创新质量达到发表要求。
- 任一真实实验或论文结果成立。
- 外部投稿成功。
- 生产并发、灾备、安全合规或成本达标。
- LLM 提供商在当前凭据下可用。

## 3. 下一阶段验收

1. 提供一个真实 idea、研究领域、目标 venue 和资源边界。
2. 建立人工标注 gold queries 和 20–50 篇许可明确的 paper corpus。
3. 人工盲审 ReadingCard、locator、冲突综合和 InnovationCandidate。
4. 运行真实 baseline/ablation，登记 RunManifest、hash 和失败结果。
5. 做稿件 claim-evidence audit。
6. 做 checkpoint 进程重启、故障注入和备份恢复演练。
7. 再决定是否升级 Project-to-Act 中尚未达到严格完成条件的功能。
