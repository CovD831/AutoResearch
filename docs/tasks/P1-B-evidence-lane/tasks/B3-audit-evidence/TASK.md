# B3 Audit Evidence

状态：`tested`。S1 promotion 已在 `main@dad4658` 通过，B3 已完成审计核心实现和离线验证，尚未提交、推送或创建 PR。

## 目标

完成 S2-B Audit Module 的 Evidence reconciliation、引用核验、locator 核验、撤稿/更正/版本状态核验、未绑定 claim 报告和 candidate 回流。

## 本次交付

- `AuditVerdict`、`AuditReport` 以及版本化 `ResolverSnapshot` / `CorpusSnapshot`；
- 确定性 `pass` / `fail` / `unknown` 判定；
- `deterministic` 与 `model_assisted` verdict 分离，并冻结 0.8 置信度阈值；
- standalone 与 in-runtime 两种运行模式；
- in-runtime 结论只能通过 `EvidenceService.admit_candidate()` 回流；
- 离线 synthetic audit fixture 和可重跑测试。

## 边界

只修改 B3 自有模块、测试、fixture 和本任务目录。不得修改共享 contracts、application 编排、storage、Gate、CLI/MCP、reader/writer 或项目账本；不添加网络请求、真实论文、Agent、Store、bus 或 scheduler。

## 验收状态

- B3 专测：`16 passed`；
- 全量测试：`97 passed`，`-W error` 退出码 0（禁用 pytest cache 插件以绕过本机 `.pytest_cache` 权限告警）；
- `ruff check src tests`：通过；
- `node .ai-team/check.mjs --json`：`valid: true`；
- Project-to-Act validate：`valid: true`；
- `git diff --check`：通过。

下一步是负责人复核范围和报告内容，然后提交 B3、推送 `codex/s2-audit-evidence` 并创建 PR；在 PR 合并前不得标记为 `integrated`。
