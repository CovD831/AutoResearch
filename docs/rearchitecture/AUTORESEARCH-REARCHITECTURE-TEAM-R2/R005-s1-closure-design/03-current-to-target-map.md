# 03 Current-to-Target Map — R-005-S1-CLOSURE

对照基准：`46fbd7a + 在飞 S1 修改`（[evidence-baseline.txt](evidence-baseline.txt)），2026-09-03 对当前树逐项复核。本包只映射 S1 关闭实际消费的 hotspot；`graph.py`、`knowledge.py` 等未被本切片消费的行不在此次重述（canonical owner：[../R004-trust-program/03-current-to-target-map.md](../R004-trust-program/03-current-to-target-map.md)）。

## 关键新发现（本次对照才确认）

`PaperSearchCapabilityAdapter` 在 `src/autoresearch/application.py:76` 被**构造但从未被调用**；`EvidenceCandidate` 除 adapter 自身外**没有任何消费者**，也从未被提交给 `EvidenceService`。即：目标边界已存在但**悬空**——这正是 parity/recovery 证据无法自然产生的原因。证据：[evidence-consumers.txt](evidence-consumers.txt)。

## Hotspot 映射

| 当前实现 | 动作 | Current owner | Target owner | Removal gate / 备注 |
|---|---|---|---|---|
| `application.py::AutoResearchApplication` 大构造器 | **expose**（保留 facade；新增 `self.paper_search_capability` 暴露点，尚无调用方） | Project owner | Runtime composition（下一实现包） | 暴露点被 run 路径真实调用且 parity fixture 通过；否则该行是死装配 |
| `capability.py::PaperSearchCapabilityAdapter` | **adapt**（目标边界本体；reservation-first 已实现） | Adapter maintainer | 同左 | 不适用（target）；晋级门 = 04 的开放 claim 关闭 |
| `search_service.py::PaperSearchService` | **retain**（legacy 路径 = parity fixture 的 legacy 侧） | Search maintainer | 保持至 removal gate | gate：target 与 legacy 在同一场景 receipt/产物/checkpoint 等价后，才可讨论收缩 connector 直连路径 |
| `storage.py::reserve_idempotent / finalize_idempotent / get_idempotent`（215–233 行） | **retain + extend**（幂等状态表唯一写入者） | Store maintainer | 同左 | 不移除；扩展仅限恢复语义（pending → 显式 recover/fail 的操作路径） |
| `contracts.py::CapabilityManifest / InvocationReceipt / EvidenceCandidate`（206–233 行） | **retain**（S1 四名词中三个已落地；无新增名词） | Contracts owner | 同左 | 字段演进须走 L2 合同修订，不改语义 |
| `evidence.py::EvidenceService` + `gates.py` | **retain**（证据唯一写入者；注意：adapter 包装的 legacy 服务在内部经 `_persist` 写 `EvidenceItem`，adapter 另产候选——双表示归一见 04 的 B-1） | Evidence/Policy owner | 同左 | 候选**尚未接线**——接线与双表示裁决见 04 的 B-1；不得让 adapter 直写证据表 |
| `tests/test_capability_adapter.py`（replay 幂等 + 冲突拒绝） | **extend**（缺 recovery/parity 测试） | S1 implementer | 下一实现包 | R003-AR-005 / AR-OLD-002/004/005/006 关闭即解除 |

## 动作图例与继承

retain/expose/adapt 语义沿用程序映射（[../R004-trust-program/03-current-to-target-map.md](../R004-trust-program/03-current-to-target-map.md)）。本包未引入 split/consolidate/deprecate/remove 判定——没有消费证据支撑它们（doc-gates：无消费者的概念推迟）。
