# R-004-TRUST-PROGRAM 重构程序包

> 状态：design+program / active-program；取代 R-001、SKILL-TEST、INDEPENDENT 三个包；与 R-002-LITERATURE-PILOT（设计轨）/ R-003（S1 实现轨）并存，S1 实现权威在 R-003。
> 目标：薄 Runtime、可插拔 Capability（Skill/MCP/Plugin/native）、独立 Evidence/Policy、可外化 Audit Module。
> 交付地平线：S0 合并与依赖基线 → S1 Paper Search 冻结合同 → S2 Audit 外化 → S3 LLM 槽位与真实外部能力 → S4 信任闭环试点与公开 benchmark。

## 阅读路线

1. [00-scope-and-authority.md](00-scope-and-authority.md) — 基线、来源优先级、范围与已解决决策。
2. [01-positioning-and-complexity.md](01-positioning-and-complexity.md) — 问题、用户、价值假设、复杂度预算（新增仅 `AuditVerdict`）。
3. [02-l1-target-architecture.md](02-l1-target-architecture.md) — L1 与四处修订（Audit 边界、trust tier、五角色、部署边界）。
4. [03-current-to-target-map.md](03-current-to-target-map.md) — 全仓映射与冻结清单。
5. [04-l2-contracts.md](04-l2-contracts.md) — 五个 L2 合同（含新增 Audit Module，conditional）。
6. [04b-s1-l3-contract.md](04b-s1-l3-contract.md) — S1 冻结实现合同。
7. [05-migration-and-evidence.md](05-migration-and-evidence.md) — S0–S4 计划：每片 fixture/oracle/命令/晋级证据/中止规则。
8. [06-adr-r002.md](06-adr-r002.md) — 合并决策、用户决策记录（ADR-2，引用 UD-001..003）、冻结清单、Audit 外化。
9. [07-adversarial-review.md](07-adversarial-review.md) — 作者自审（无独立 reviewer，已披露）+ 双向钢人 + ledger。
10. [08-maintenance-and-catalog.md](08-maintenance-and-catalog.md) — 包目录与复审规则。

## 当前结论

R-004 完成 S0 的合并与决策回填部分；S0 剩余项（`scripts/dependency_inventory.py` 与 baseline 产出）为下一任务；S1 实现由 in-flight 的 R-003 承担，本包消费其晋级证据。S2–S4 是方向承诺，各自开工前须前片晋级证据通过。本包不声称任何运行时行为已改变。
