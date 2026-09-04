# R-004-00 范围与权威基线

## 基线

- 代码基线：`main` 工作树，2026-09-03，foundation 0.1.0；R-002 不改变任何运行时行为。
- 决策输入：`docs/市场调研与定位分析_2026-09.md`（本项目信任层定位的依据，非架构权威）。
- 既有并行线：`R-002-LITERATURE-PILOT`（设计，blocked 于 review round 1，含 UD-001..003 决策记录）与 `R-003-PAPER-SEARCH-ADAPTER`（实现，in-flight，20 tests passed、parity 待补）。本包**不取代**这两包；S1 实现权威在 R-003。
- 本包取代 R-001、SKILL-TEST-2026-09-03、INDEPENDENT-2026-09-03 三个包（见 06-adr ADR-1 与 08 目录）；与 R-002-LITERATURE-PILOT / R-003 是 program 与 implementation 两轨关系（08）。

## 来源优先级

1. 当前源码与测试：实现事实。
2. `AGENTS.md`、`.ai-team/PROJECT.md`、`.ai-team/TASK.md`：仓库约束与当前任务。
3. `.project-to-act/PROJECT_*`：长期范围、进度与验收事实。
4. `docs/ARCHITECTURE.md`、`docs/FUNCTION_MATRIX.md`：当前/目标说明，按状态标记区分。
5. 前三个 rearchitecture 包：被取代的设计输入；其未决 finding 由本包 ledger 继承（见 07）。
6. 本目录：R-002 目标设计与迁移计划，不得当作当前实现。

## 范围

- R-004 是**程序包**（program package）：定义薄 Runtime + 可插拔 Capability + 独立 Evidence/Policy + 可外化 Audit 的目标架构，以及 S0–S4 增量序列；只有 S1 拥有冻结的 L3 实现合同。
- S0：包合并与决策回填（本包已完成）；依赖清单脚本与 baseline（待建，见 handoff）；治理文档同步清单（05 S1 晋级附加项）。
- S1：Paper Search capability 切片（合同冻结于 04b）。
- S2：Evidence/Audit 外化（Audit Module + CLI/MCP 出口）。
- S3：Reader/Writer 槽位 LLM 化 + 一个真实外部能力接入（两级信任实证）。
- S4：可信闭环试点 + 公开 trust benchmark。

## 不在范围

- 不实现远程任意代码执行、热卸载、进程隔离、通用 bus、微服务、多租户或 Web UI。
- 不在 S1–S4 内做检索/阅读/写作算法本身的科研质量提升（它们是可替换能力）。
- 冻结项见 03 冻结清单：evolution/profile/Wiki+Graph 投影/pgvector/Neo4j/Postgres 迁移。

## 已解决的未知项

- 首切片/能力边界/部署边界三项：canonical 记录为 R-002-LITERATURE-PILOT 的 UD-001/002/003（`decisions/*.json`），本包引用不复制。
- 五 Agent 不变量改写为五领域角色：记录于本包 06-adr ADR-2（S1 promotion 时同步 PROJECT_OVERVIEW D-001）。
- S4 垂直领域（可信文献综述 / related-work 写作）：记录于本包 06-adr ADR-2。
