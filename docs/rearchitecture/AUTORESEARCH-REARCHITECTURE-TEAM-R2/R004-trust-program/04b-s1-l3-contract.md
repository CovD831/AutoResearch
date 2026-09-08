# R-004-04b S1 Paper Search L3 程序侧对照基线

继承 INDEPENDENT-2026-09-03/04b 并按其审查 finding 补强。**实现权威为 R-003-PAPER-SEARCH-ADAPTER 的 L3**（in-flight）；本文件作为程序侧对照基线，两者冲突时以 R-003 下一 review round 消费后的版本为准，差异须回写本文件。

## Typed 模型（pydantic，落于 `capabilities/contracts.py`）

```text
PaperSearchRequest:  project_id, run_id, invocation_id, query, limit
PaperSearchResult:   papers[PaperRecordLite(title, paper_id, doi|None, source)],
                     diagnostics[Diagnostic],
                     receipt{invocation_id, status: receipt_committed|admitted|admitted=false,
                             adapter, adapter_version, request_fingerprint},
                     evidence_candidates[EvidenceCandidateLite(claim, source_id, locator, independent_source)]
```

## 授权与持久化顺序

1. Runtime 校验 manifest scope 与 operator trust tier → 授权，adapter 不能升级。
2. Runtime 先提交 invocation receipt（`receipt_committed`）。
3. Evidence Module admission candidate；Paper Domain 写 PaperRecord；Knowledge 投影由 Project/Knowledge service 写入。
4. 跨表无法原子提交时：终态 `admitted=false` + compensation 记录，允许同 invocation_id 重放 admission；禁止静默成功。

## 验收（全部通过才允许 S1 promotion）

- native 与 fake adapter 对同一 fixture 产生语义等价 PaperRecord；
- 重复 invocation 不重复 receipt/evidence；冲突 request 拒绝；
- timeout / parse error / provider unavailable / unknown outcome 均有确定终态；unknown 不标成功；
- 进程重启后同 run_id 可查 receipt 并恢复；
- Agent/Adapter 不直接 import concrete Store/Evidence（architecture dependency 测试强制）；
- 依赖清单 before/after 对照存在且方法可重跑。

## 可复现命令

```bash
python scripts/dependency_inventory.py   # S0 产出 baseline，S1 产出 target 对照
python -m pytest tests/test_capability_adapters.py tests/test_recovery_contract.py \
                 tests/test_architecture_dependencies.py tests/test_workflow.py
python -m ruff check src tests
node .ai-team/check.mjs --base main
```

S1 证明的只是 paper-search 接入边界 + Evidence 唯一写入者；不证明 reader/writer/audit/plugin lifecycle。
