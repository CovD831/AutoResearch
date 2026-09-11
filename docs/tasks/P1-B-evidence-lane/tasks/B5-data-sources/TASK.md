# B5 真实数据源与解析层

状态：`active`（O7 S3 promotion 已完成，B4 accepted；依赖「B4 accepted + S3 promotion」均已满足）。完整目标、交付物、边界和验收见 `../../TASK-SPECS.md` 的 B5 节（2026-09-10 重排编号，原追加包 B7）。

选型一律以 ADR-01（`docs/coord/adr-01-external-integrations.md`）为准：PDF→Markdown 默认 docling（MIT）、pymupdf4llm 仅作轻量兜底；Crossref 经 B3 verdict 流；解析产物一律 candidate 通道。