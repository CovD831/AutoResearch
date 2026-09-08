# 02 L1 Target Architecture — R-005-S1-CLOSURE

Canonical owner of the program L1 claim: [../R004-trust-program/02-l1-target-architecture.md](../R004-trust-program/02-l1-target-architecture.md)。本文件按 checker 约束在包内做**有界重述**（摘要短于源），本增量对 L1 **零修改**——这正是设计要点：缺口在证据链，不在边界。

## 系统级事实（与 R-004 L1 一致，2026-09-03 对照当前树确认）

| L1 事实 | 目标 | 当前树状态（对照证据） |
|---|---|---|
| 主要子系统 | Thin Runtime → Capability/Domain → Evidence/Policy → Store | `application.py` 仍是大装配构造器；`capability.py::PaperSearchCapabilityAdapter` 已作为 Capability 边界插入（[03](03-current-to-target-map.md)） |
| 状态权威与唯一写入者 | Evidence 状态唯一写入者 = Evidence Module；GateDecision 唯一写入者 = Policy | `storage.py` 幂等表由 `reserve_idempotent/finalize_idempotent` 独占写；`evidence.py::EvidenceService` 仍是证据写入者。**当前树的 receipt 实际写入者是 adapter**（见下方 L1 delta） |
| 身份族 | `project_id`、`run_id`、`invocation_id` 三层身份保持区分；幂等键 = `run_id:invocation_id` + capability name（scope） | `capability.py` key = `f"{run_id}:{invocation_id}"`，scope = manifest.name；`candidate_id/evidence_id` 由契约生成 |
| 依赖方向 | Runtime → Capability/Domain → Evidence/Policy → Store，单向 | adapter 依赖 `search_service` + `storage`，不反向依赖 Agent；无新总线/scheduler |
| 入口与部署边界 | CLI/API 入口不变；单进程本地 | `cli.py`/`api.py` 未被本线修改 |
| 受控交互形式 | Command / typed transfer / query-view / receipt-evidence | adapter 返回 typed `PaperSearchInvocation`（receipt + papers + candidates），无自由文本 handoff |

## L1 delta（review AR5-002；相对 R-004 L1 的偏差，需程序 owner 裁决）

R-004 L1 的唯一写入者表规定 `invocation receipt | Thin Runtime`，且禁止 `Adapter → Store 直写`（[../R004-trust-program/02-l1-target-architecture.md](../R004-trust-program/02-l1-target-architecture.md) 唯一写入者表）。当前树与两者都不一致：`capability.py` 的 adapter 直接经 store 幂等方法写调用记录（reserve/finalize，含 receipt payload）。因此本包**不**声称 "L1 pass (unchanged)"，而记录一个待裁决的 L1 偏差：

- 拟议修订（本包推荐）：在 R-004 写入者表增补一行 `capability invocation idempotency record（含 receipt payload） | Capability Adapter（经 Store 幂等方法）`，与 `invocation receipt | Thin Runtime` 并存（后者指 run 级 receipt，前者指 capability 调用级记录）。
- Owner：R-004 程序 owner（user/team）。Decision gate：S1 promotion gate —— 晋级前必须把该行正式并入程序 L1 或责成实现包把幂等写收回 Runtime 侧。记录见 [05-adr.md](05-adr.md) ADR-7。

## 未决 L1 问题（本增量不新增）

全部继承 R-004，owner 与 decision gate 已在 R-004 记录，此处仅链接不复制：Audit Module 边界（S2 合同冻结 gate）、S3 lineage、S4 plugin lifecycle（各以真实消费者为 gate）。本包不重开、不裁决。

## 本增量的 L1 判定

无新子系统、无新部署形态；存在一处**已声明的写入者偏差**（上方 L1 delta，owner + gate 已命名）。复杂性预算零新增名词（见 [05-adr.md](05-adr.md) ADR-6 的否决记录）。
