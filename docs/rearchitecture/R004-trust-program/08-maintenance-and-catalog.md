# R-004-08 维护与目录

## 包目录（唯一权威链）

| 包 | 状态 | 说明 |
|---|---|---|
| R-001 | superseded（原 abandoned） | 首版设计，四个 L2 名词的出处，被 INDEPENDENT 取代 |
| SKILL-TEST-2026-09-03 | superseded | skill 试运行包，一轮独立审查 |
| INDEPENDENT-2026-09-03 | superseded | 两轮独立审查；L1/L3 被本包继承并修订 |
| R-002-LITERATURE-PILOT | active-design（blocked 于 review round 1） | 运行时改造线设计权威；UD-001..003 决策记录在此 |
| R-003-PAPER-SEARCH-ADAPTER | active-implementation（blocked 于 closure review） | S1 实现权威；parity/recovery 证据待补 |
| **R-004-TRUST-PROGRAM** | **active-program** | 当前程序权威：S0–S4 地平线、Audit Module、L1 修订、冻结清单 |

双轨规则：同一时刻最多一个 active-program 包与一条 active implementation 线（含其设计父包）；program 包的 L1/L2 修订必须被 implementation 线在下一 review round 消费后才成为该线权威。新包取号前必须检查本目录与 `.rearchitecture/dispatch-log`。

## 文档所有权

- manifest（`.rearchitecture-package.json`）：机器索引。
- `review-ledger.json`：R-002 及继承 finding 的消费权威。
- Markdown 文档：设计 rationale。
- 源码/测试/`.project-to-act`：current facts；target 文本只在 promotion 后并入。
- `docs/市场调研与定位分析_2026-09.md`：市场事实输入，非架构权威。

## 复审触发

任何 ownership、trust tier、checkpoint、deployment 或 audit 对外契约的修改必须开启新 review round；S2 promotion 前建议一次独立（非作者）复审。
