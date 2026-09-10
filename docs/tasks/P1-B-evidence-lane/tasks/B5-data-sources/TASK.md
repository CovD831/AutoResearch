# B5 真实数据源与解析层

状态：`ready`（O7 S3 promotion 已于 2026-09-10 完成，B4 reader/writer ports 已 accepted；`task-package.json` 由成员实现时按实际命名填写，参照 B4 先例）。完整目标、交付物、边界和验收见 `../../TASK-SPECS.md` 的 B5 节（2026-09-10 重排编号，原追加包 B7）。

要点注记（选型一律以 ADR-01 为准，2026-09-10 已签字生效）：

- PDF→Markdown 默认 **docling（MIT，ADR-01 槽位 3）**，pymupdf4llm 降为轻量兜底；AGPL 条款：仅本地工具链不分发。
- Crossref **S2 免费 key 主选**（2026-02 起强制 key + 用量计费，原 polite pool 作废）+ arXiv 补充（ADR-01 槽位 2）；Retraction Watch 经 **B3 verdict 流**（audit_evidence 通道），不得直写证据。
- 解析与抓取结果一律 **candidate 通道**（B4 port 已交付：`bind_claims` fail-closed + `gate_compliance`；消费走 `admissible_candidates` 单点判据）。
- 空结果遵循 D-F8-01（`completed_empty` 为确定性成功终态）；限流/离线矩阵化。
