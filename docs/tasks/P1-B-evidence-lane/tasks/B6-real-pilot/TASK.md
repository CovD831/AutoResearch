# B6 Real Pilot

状态：`planned`（S3 promotion 已于 2026-09-10 通过；**B5 真实数据源未交付前只能 mock 试点，不计入真实试点验收**）。完整目标、交付物、边界和验收见 `../../TASK-SPECS.md` 的 B6 节（2026-09-10 重排，原 B5）。

要点注记（2026-09-10 对抗审查条款）：双模型交叉评审 + 盲审依赖 O12 ProviderLane——O12 就绪前 llm.py 直连临时路径（不绕过 candidate 通道与审计），就绪后切 lane 补计价；EvoMap 条款（交叉评审盲审 / 双模型各生成一版 / 盲审差异入审计事件 / 仅 candidate 参考 INV-26 / 打回版本归档为失败经验）见 ADR-01 与 TASK-SPECS B6 节。
