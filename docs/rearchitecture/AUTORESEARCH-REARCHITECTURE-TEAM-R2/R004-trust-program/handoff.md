# Handoff

- Package: `R-004-TRUST-PROGRAM`（program 轨；S1 实现见 R-003）
- Profile: design+program
- State: self-review complete (8 findings, F-1..F-4/F-8 consumed, F-5/6/7 open with gates)
- Owner: user/team
- Next task: ① S0 剩余——新建 `scripts/dependency_inventory.py` 并产出 `evidence/inventory-baseline.txt`（同时闭环 F-5）；② 跟踪 R-003 closure review 与 parity 证据，其晋级后在本包消费为 S1 gate
- Stop rule: S1 任一晋级证据（parity/sole-writer/idempotency/recovery）失败即停，保留 legacy facade；S2 开工前必须 S1 晋级通过；ledger 中 open finding 未闭环前不得宣称对应能力完成
- 继承债务：INDEPENDENT 包 blocking findings AR-002/004/005/006（实现证据类）由 R-003 晋级证据闭环（见 07）
