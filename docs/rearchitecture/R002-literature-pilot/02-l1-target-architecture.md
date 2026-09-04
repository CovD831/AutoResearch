# L1 目标架构

```text
CLI/API -> Thin Runtime -> Capability Registry/Adapter -> Research Services
                                      |                         |
                                      +---- typed result/receipt-+
                                                v
                                      Evidence Module -> Policy/Gate
                                                v
                                      Project Ledger + Store/Files
```

Runtime 唯一拥有 run orchestration、checkpoint 和 invocation receipt；Registry 只解析 manifest；Adapter 只转换外部结果；Research Service 拥有 PaperRecord/ReadingCard 等领域产物；Evidence Module 是 EvidenceItem、ClaimLink、ArtifactLink、失效和 provenance 的唯一写入者；Policy/Gate 只做确定性判定；Project Ledger 写项目/run 投影。依赖单向 `Runtime -> Capability/Domain -> Evidence/Policy -> Store`。

身份必须分离：`run_id`、`invocation_id`、capability identity/version、source locator、evidence_id、agent identity。跨边界只允许 command、typed transfer、query/view、receipt/evidence。
