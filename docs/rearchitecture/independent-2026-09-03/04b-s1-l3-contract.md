# S1 Paper Search L3 Contract

## Request

```json
{"project_id":"string","run_id":"string","invocation_id":"string","query":"string","limit":1}
```

## Result

```json
{"papers":[{"paper_id":"string","title":"string","doi":"string|null","source":"string"}],"diagnostics":[],"receipt":{"invocation_id":"string","status":"receipt_committed","adapter":"string","adapter_version":"string"},"evidence_candidates":[{"claim":"string","source_id":"string","locator":"string","independent_source":"string"}]}
```

## Authorization and persistence

Runtime 按 manifest scope 授权；Adapter 不能升级权限。Runtime 先提交 invocation receipt，再由 Evidence Module admission candidate；Paper Domain 写 PaperRecord，Knowledge projection 由 Project/Knowledge service 写入。跨表无法原子提交时必须返回明确 compensation/unknown，不得静默成功。

## Acceptance

- native 与 fake adapter 对同一 fixture 产生语义等价 PaperRecord；
- 重复 invocation 不重复 receipt/evidence；冲突 request 被拒绝；
- timeout、parse error、provider unavailable、unknown outcome 均有确定结果；
- 进程重启后同 run_id 可查询 receipt 并恢复；
- Agent 不直接 import concrete Store/Evidence；
- `tests/test_capability_adapters.py`、`tests/test_recovery_contract.py`、`tests/test_architecture_dependencies.py` 和 inventory report 均存在并通过。
