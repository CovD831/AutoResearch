# Migration and Evidence Plan

## S1 Paper Search

Legacy：现有 `PaperSearchService`。
Target：fake capability + `CapabilityAdapter` + EvidenceCandidate + InvocationReceipt。

## 必须比较

- 输入/输出语义：PaperRecord 与诊断等价；
- 持久化事实：project/run/evidence 记录等价；
- 失败：timeout、parse、provider unavailable、unknown outcome；
- 幂等：重复 invocation 不重复写证据；
- 恢复：同一 run_id/checkpoint 可继续；
- 可见行为：旧 CLI/API 仍可用。

## 回滚

任一 parity、唯一写入权或恢复测试失败，保留旧 facade，不晋级 target，不接入真实远程 MCP。

## 晋级证据

需要 target/legacy fixture、合同测试、故障测试、重放测试、重启测试和 `node .ai-team/check.mjs --base main`。
