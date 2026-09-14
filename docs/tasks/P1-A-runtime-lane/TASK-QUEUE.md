# A 线任务队列

| Task | 状态 | 依赖 | 交付重点 |
|---|---|---|---|
| A1 P1-A Runtime/Recovery | ready | — | 幂等、replay、recovery、parity |
| A2 P1-A Runtime Hardening | ready-next | A1 | fault injection、边界回归、证据自动化 |
| A3 S2 Audit Runtime | waiting-for-gate | S1 promotion | audit CLI、resolver、运行时接线 |
| A4 S3 Capability Adapters | ready | S2 promotion | registry、trust tier、外部 adapter |
| A5 S4 Benchmark Runtime | planned | S3 promotion | benchmark harness、运行资源和审计、Semantic Scholar 真实检索 adapter |
| A6 S4 经验沉淀接线（追加包 2026-09-10，原 O9 接线点①前移） | planned | A3/B3 accepted（已满足） | audit 拦截事件 → ExperienceService.record 自动失败沉淀 |
| A7 S4 knowledge 向量检索升级（追加包 2026-09-10，原 O10 实现部分前移） | planned | A6（串行） | sqlite-vec + bge-small 本地 embedding + RRF，替换纯词法检索 |
| A8 S4 主链路检索 adapter（2026-09-14，执行 `D-A5-偏离-1` 选项 (a)） | active | A5 integrated（已满足） | 主链路从裸 `httpx.get` 匿名 connector 切到 A5 真实 adapter；新增 `retrieve()` 原语与 `AdapterBackedPaperSearchService` |
| A9 S4 交接单只传引用（2026-09-14，真实运行暴露的契约上限缺陷） | active | A8（已满足） | `HandoffEnvelope` 由内容承载改为引用界；`paper_reader.py` 不再逐张铺卡；`paper_search.py` 的静默 `[:20]` 截断加可观测告警 |
| A10 S4 书目声称与部分失败（2026-09-14，第二轮独立盲审的 F4 + N1） | active | A9（已满足） | 共享书目写入函数（parity 结构化）；claim 只描述实际材料；不可归属的检索命中拒绝铸 E1；`receipt.provider_failure` 让部分失败可见 |

每个任务独立 PR；本表只描述顺序，不替代详细验收。
