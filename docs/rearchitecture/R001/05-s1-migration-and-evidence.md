# R-001-05 S1 迁移、验证与晋级

## 垂直切片

`Paper Search Capability -> Adapter -> EvidenceCandidate -> PaperRecord/Run receipt`

首个 target fixture 使用可控 fake capability；native `search_service.py` 作为 legacy fixture。真实远程 MCP 接入放在 parity 通过之后。

## 验收矩阵

| 类别 | Legacy fixture | Target fixture | 通过标准 |
|---|---|---|---|
| 输入/输出 | native connector | fake adapter | PaperRecord 语义等价 |
| 证据 | search service + EvidenceService | adapter candidate + Evidence Module | 只有 Evidence Module 写入 |
| 失败 | connector diagnostic | timeout/parse/unknown diagnostic | 不伪造成功 |
| 幂等 | 重复 native run | 重复 invocation id | 不重复 durable evidence |
| 恢复 | 旧 run checkpoint | target checkpoint | 同 run_id 可恢复 |
| 兼容 | CLI/API `run` | 新 Runtime facade | 外部结果和项目投影一致 |

## 可复现命令

```bash
python -m pytest tests/test_capability_adapters.py tests/test_workflow.py
python -m ruff check src tests
node .ai-team/check.mjs --base main
```

实现前需新增 target fixture 和测试；不要用“代码能 import”作为架构证据。

## 失败与回滚

- receipt、durable facts、checkpoint 或失败语义不等价：停止晋级，保留 legacy facade。
- 外部调用结果 unknown：标记 unknown，不自动重试或标记成功。
- Evidence Module 出现第二写入者：阻断发布，修订边界。
- 发生不可逆外部副作用：S1 不允许该类 capability。

## Promotion gate

只有以下证据齐全，S1 才能从 target promotion 为 current：

1. legacy/target contract、failure、idempotency、restart 测试通过。
2. 旧 API/CLI 与新 Runtime 的 bounded result、durable facts、receipt、checkpoint 等价。
3. Agent/Capability 不再直接写证据真相。
4. 文档、TASK、Project-to-Act 的 current/target 标记同步。

S1 证明的只是 paper-search boundary，不证明 reader/writer/plugin lifecycle 已完成。
