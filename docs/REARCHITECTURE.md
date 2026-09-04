# AutoResearch 重构程序索引

> 本文件是**纯索引**，不是重构包正文。历史叙述（R-001 时代的十节正文）已归档：[archive/REARCHITECTURE-r001-era.md](archive/REARCHITECTURE-r001-era.md)。

## 当前活动程序

团队统一阅读入口：[AUTORESEARCH_ARCHITECTURE_GUIDE.md](AUTORESEARCH_ARCHITECTURE_GUIDE.md)。它整合全项目目标、L1/L2、论文生成 pipeline、阶段路线和协作账本入口；不覆盖 R-004/R-003/R-005 的权威记录。

**R-004-TRUST-PROGRAM**（active-program）：[docs/rearchitecture/R004-trust-program/](rearchitecture/R004-trust-program/)
目标：薄 Runtime · 可插拔 Capability（Skill/MCP/Plugin/native）· 独立 Evidence/Policy 信任层 · 可外化 Audit Module。

最新增量：**R-005-S1-CLOSURE**（design，implementation-candidate）——S1 晋级证据计划已冻结；exact next task：`S1-CLOSURE-EVIDENCE`（owner: user/team）。见其 [06-handoff](rearchitecture/R005-s1-closure-design/06-handoff.md)。

## 包目录（权威表：R004-trust-program/08）

| 包 | 状态 | 一句话 |
|---|---|---|
| R-001 / SKILL-TEST / INDEPENDENT-2026-09-03 | superseded | 早期设计与 skill 试运行；findings 已由 R-004 ledger 继承 |
| R-002-LITERATURE-PILOT | active-design（blocked at review） | 运行时改造线设计父包；UD-001..003 决策记录在此 |
| R-003-PAPER-SEARCH-ADAPTER | active-implementation（blocked at closure） | S1 实现 in-flight；parity/recovery 证据待补 |
| **R-004-TRUST-PROGRAM** | **active-program** | 程序权威：L1/L2、S0–S4 地平线、冻结清单 |
| R-005-S1-CLOSURE | 最新增量（design） | S1 关闭设计 + parity 断言模型冻结；含两轮审查 |

规则：一个 active-program + 一条 active implementation 线；新包取号前查本目录与 `.rearchitecture/dispatch-log`；完整规则见 [R004-trust-program/08-maintenance-and-catalog.md](rearchitecture/R004-trust-program/08-maintenance-and-catalog.md)。

## 文档权威地图

| 问题 | 唯一权威 |
|---|---|
| 当前实现架构 | `docs/ARCHITECTURE.md` |
| 目标架构（未晋级） | `docs/rearchitecture/R004-trust-program/02-l1-target-architecture.md` |
| 功能状态 | `.project-to-act/PROJECT_FEATURES.md`（86 项账本） |
| 重构包状态 | 各包 `.rearchitecture-package.json` + R004/08 目录表 |
| 市场定位依据 | `docs/市场调研与定位分析_2026-09.md` |
| 历史（2026-08 产品基线） | `docs/AutoResearch_详细计划书.md`（带历史横幅）· `docs/archive/` |
