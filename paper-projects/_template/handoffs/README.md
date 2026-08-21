# 交接目录

每次跨 Agent 交互必须保存通过 schema 的 `HandoffEnvelope` 和 `HandoffResult`。完整聊天、整篇全文和未裁剪工具日志不能作为交接 payload；使用 artifact/evidence/claim ID 按需读取。
