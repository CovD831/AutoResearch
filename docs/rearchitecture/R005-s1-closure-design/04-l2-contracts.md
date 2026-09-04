# 04 L2 Boundary Contracts — R-005-S1-CLOSURE

本包消费两个稳定边界，各立一份 L2。交互词汇：Command / typed transfer / query-view / receipt-evidence（无总线）。Claim 标注：**established**（有当前树证据）/ **conditional**（部分证据）/ **open**（有命名 gate）。

## A. Capability Invocation 边界（adapter ↔ store 幂等表）

- Owner（唯一写入者）：adapter 经 `RecordStore` 幂等方法独占 `scope=manifest.name, key=run_id:invocation_id` 的状态。非职责：证据状态写入、Gate 判定、connector 实现。
- Current classes：`src/autoresearch/capability.py::PaperSearchCapabilityAdapter`；`src/autoresearch/storage.py::reserve_idempotent / finalize_idempotent / get_idempotent`；`src/autoresearch/contracts.py::CapabilityManifest / InvocationReceipt / PaperSearchInvocation`。
- Provided/required services：adapter 提供 `invoke(...) -> PaperSearchInvocation`（typed transfer + receipt-evidence）；requires `PaperSearchService.search`（legacy，Command）与幂等表（Command/query）。

| # | Claim | 状态 | 证据 / 命名 gate |
|---|---|---|---|
| A-1 | 幂等准入先于副作用：reserve 成功才调用 legacy service；finalize 落盘 receipt+papers+candidates | **established** | `capability.py:68`（reserve 先于 `self.service.search`）；[evidence-pytest.txt](evidence-pytest.txt)（20 passed，含 `tests/test_capability_adapter.py::test_target_adapter_replays_without_second_connector_call`） |
| A-2 | 精确重放返回相同 receipt（status 记 `replayed`）且不产生第二次 connector 调用；冲突重放被拒绝 | **established** | 同上测试 + `::test_target_adapter_rejects_conflicting_replay` |
| A-3 | 失败被 adapter 隔离：空 query/越界 limit → `ValueError`；pending 残留 → `RuntimeError("invocation outcome is unknown; recover explicitly")`，不伪造成功 | **conditional** | 代码路径存在（`capability.py:41-72`）；**缺**：pending 残留的构造性测试与显式恢复/失败操作路径。Gate：S1 实现包 recovery 证据（对应 R003-AR-005、AR-OLD-004/005） |
| A-4 | 零结果调用以 `status="unknown"` 收尾，不自动重试、不标成功 | **conditional** | `capability.py:79`；gate 同 A-3（unknown-outcome 证据） |
| A-5 | 重放 receipt 的 status 覆写为 `replayed`，**丢失原始 outcome**（completed/failed/unknown 不可再区分） | **open** | 本包对照 `capability.py:59-66` 发现；修法（如在 receipt 增加 `outcome_status` 只读字段）由 S1 实现包 L3 冻结。Owner：adapter maintainer；Gate：S1 L3 冻结 + 晋级证据。关联 R-004 F-4（standalone 调用 receipt 语义） |

## B. Evidence Admission 边界（adapter 候选 → Evidence Module）

- Owner（唯一写入者）：`src/autoresearch/evidence.py::EvidenceService` 是证据状态唯一写入者。非职责（**修正后的表述**，review AR5-001）：adapter 确实不直接调用 `EvidenceService`，但当前 `adapter.invoke` 包装的 `search_service.search` 在内部经 `_persist` 写入 paper 记录、`EvidenceItem`（actor=`paper_search`）和知识页（`src/autoresearch/search_service.py::PaperSearchService._persist`）——即**目标路径的持久证据今天产生自被包装的 legacy 服务内部**，adapter 产出的 `EvidenceCandidate` 是第二套并存的溯源表示。
- Current classes：`contracts.py::EvidenceCandidate`（candidate_id/evidence_id/checksum/source_uri/locator/claim，**established**，证据：`contracts.py:211`）；`capability.py:89-105`（候选构造）；`search_service.py:160-195`（内部持久化）。
- **已建立的事实**：该边界当前**未接线**——`paper_search_capability` 在 `application.py:76` 构造后无调用方；无任何代码把候选提交给 `EvidenceService`。证据：[evidence-consumers.txt](evidence-consumers.txt)。

| # | Claim | 状态 | 证据 / 命名 gate |
|---|---|---|---|
| B-1 | 候选准入与双表示归一：谁（run 流程哪一步）、何时（finalize 前/后）、以何种幂等键（candidate_id）把候选提交给 `EvidenceService`；且必须先裁决 `_persist` 内生 `EvidenceItem` 与 adapter `EvidenceCandidate` 的双表示问题——二选一：(a) 目标路径改调非持久化 search 变体，持久化统一走候选准入；(b) 保留服务内持久化，候选降级为引用/补充字段。两者都不得让 adapter 直写证据状态 | **open** | Owner：S1 implementer + Evidence owner；Gate：S1 实现包 L3 冻结（双表示裁决先于接线）。约束：准入必须幂等（重复提交同一 candidate_id 不产生第二条证据），失败不得回滚已 finalize 的 receipt（receipt 与证据准入是两个 owner 的两个事实） |
| B-2 | Legacy/target parity：同一场景下 legacy 直连路径与 adapter 路径等价。**parity 断言模型（本包冻结，review AR5-003）**：① 隔离——legacy 与 target 各用独立 `RecordStore`（tmp_path 两个库）；② 归一化——自动生成 ID（paper_id/evidence_id/candidate_id/checksum/时间戳）按"形态存在"比较，不按值比较，其余字段按值比较；③ 比较对象（精确清单）——对外结果（`outcome.papers` 的 title/abstract/authors/year/doi/url/source/source_record_id 集合）、durable facts（`paper` store 记录集合、`EvidenceItem` 的 type/grade/claim/locator/independent_source/source 集合、`_persist` 同步写入的 **WikiPage（page_id/partition/title/tags/evidence_ids 关联）**——round2 审查 F-R5-2-02 补入，`_persist` 的全部三类写入物必须同列）、receipt 语义（`InvocationReceipt.status/paper_ids/diagnostics`，capability 路径额外断言 `replayed` 行为）；checkpoint 等价以 run 状态投影比较，不比较 SQLite 字节。④ 产出——一条 pytest 命令 + 落盘 parity 报告（见 06） | **open**（断言模型 established） | Owner：S1 implementer；Gate：R003-AR-005 / AR-OLD-006 关闭。established 部分：legacy 路径保持可运行（`application.py` run 路径未改，测试全绿） |

## 兼容与迁移注记

兼容路径：`AutoResearchApplication` 旧构造与 run 行为不变（本包与在飞修改均未触碰 run 路径语义）。B-2 的 removal gate 满足前，任何"收缩 legacy 直连路径"的动作都越权。推迟到实现层的决定：B-1 的接线点、A-5 的字段修法、parity fixture 的具体断言集（06 给出最小集）。
