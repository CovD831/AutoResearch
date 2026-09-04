# R-001 重构架构包

> 状态：design package / target，不代表代码已完成迁移。
> 基线：`main` 当前工作树，foundation 0.1.0。
> 目标：薄 Runtime、可插拔 Skill/MCP/Plugin 能力、独立 Evidence Module。
> 交付地平线：先完成 S0 合同冻结，再以 Paper Search 为首条真实迁移切片。

## 阅读路线

1. [00-scope-and-authority.md](00-scope-and-authority.md) — 当前事实、范围和权威来源。
2. [01-positioning-and-complexity.md](01-positioning-and-complexity.md) — 为什么重构、非目标和复杂度预算。
3. [02-l1-target-architecture.md](02-l1-target-architecture.md) — L1 边界、所有权、依赖方向和部署边界。
4. [03-current-to-target-map.md](03-current-to-target-map.md) — 当前类/模块到目标边界的迁移动作。
5. [04-l2-contracts.md](04-l2-contracts.md) — Capability、Evidence、Runtime 和 compatibility 合同。
6. [05-s1-migration-and-evidence.md](05-s1-migration-and-evidence.md) — 首条切片、legacy/target fixture、验收、回滚和晋级门。
7. [06-adr-r001.md](06-adr-r001.md) — 本增量的材料决策记录。
8. [07-adversarial-and-steelman.md](07-adversarial-and-steelman.md) — 对抗性审查与双向钢人论证。
9. [08-maintenance-and-catalog.md](08-maintenance-and-catalog.md) — 文档所有权、状态、复审和后续增量规则。

## 当前结论

R-001 设计包可以进入用户决策/实现 handoff，但不能宣称 Runtime 已经薄化或 Evidence Module 已经独立实现。S1 的实现闸门是：用户确认首个垂直场景、外部能力边界、部署边界，并通过 05 的 legacy/target 合同比较。

## 交付记录

| 项目 | 状态 |
|---|---|
| L1 target architecture | complete / target |
| Current-to-target mapping | complete / target |
| L2 contracts | complete for S1; later modules open |
| S1 migration and evidence plan | complete / target |
| ADR | proposed |
| Adversarial review | complete with non-blocking findings |
| Implementation | not started |
