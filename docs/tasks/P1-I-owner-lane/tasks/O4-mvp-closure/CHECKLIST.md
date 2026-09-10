# O4 MVP-CLOSED 收官核对清单

- 起草：2026-09-10（S3 promotion 完成当晚，owner 预置）
- 执行：2026-09-13（B7 交付同日），09-14 为缓冲日
- 依据：`docs/rearchitecture/TASK-PACKAGE-REGISTRY.md`「MVP 闭环定义」七条件 + I4/MVP-CLOSED 职责
- 用法：09-13 照单执行，逐条打勾并附证据路径/命令；任何一条不满足即 MVP 延期并记录原因，不得粉饰

## 七条件核对表

| # | 闭环条件 | 当前状态（09-10） | O4 执行动作 |
|---|---|---|---|
| 1 | A/B 任务均 accepted | A1–A4、B1–B4 accepted；A5/B5 待 09-11 交付+审查；A6 09-12；**A7 平行增量不阻塞判定**（SPECS 已注记） | 核对 registry：关键路径行全 accepted（A7 允许 planned/ready） |
| 2 | I0–I1 共享合同 + 组装 + 编排 | integrated（75→80 passed 时代落库） | 复跑 I0 组合测试 + I1 编排测试（含于全量） |
| 3 | I2 最小 Evaluation Section E2E | VERIFIED（当前 146 passed 含 `test_mainline_e2e.py`） | 复跑 `python -m pytest tests/test_mainline_e2e.py -q`，verdict 须 VERIFIED |
| 4 | 六阶段状态与证据可追溯 | ✓（I2 验收通过） | 核对 E2E 输出：claim_evidence_map / readiness.evidence_ids / checked_evidence_ids 全部回溯到已准入证据 |
| 5 | I3 收口 | integrated（首轮 2026-09-10） | I3 → accepted；Project-to-Act 终版回写 |
| 6 | I4 manuscript/local delivery 检查 | **待做（O4 核心，依赖 B7 上午交付）** | 逐项：未执行结果、unknown、缺失材料**不得写成已完成事实**；本地交付产物可打开、可追溯 |
| 7 | blocking / 失败路径 / 回滚边界有记录 | ✓（F-1~F-10 全关 + D-F8-01 + D-S3-01 + B4 L3 注记；F-3 真实 connector 挂账 S4-B） | 核对 F-3：B6 真实 connector 已触发则闭环，未触发则再挂账说明 |

## 当日执行顺序（09-13）

1. 上午：成员 B 交付 B7（稿件组装按 ADR-01 槽位 10 pandoc、图数据出 evidence store）。
2. owner 深审 B7（对照 I3/B6 前置 + ADR-01 选型引用）。
3. owner 执行 I4 manuscript/local delivery 检查（条件 6）。
4. 七条件逐条核对（上表），全过 → registry `MVP-CLOSED-MINIMAL-E2E` 行 → accepted。
5. I3 → accepted；Project-to-Act 终版回写；`.ai-team/TASK.md` 收官条目。

## 已知缓冲与风险

- A7（向量检索升级）按计划落在 MVP 后（09-14 起），用于收官演示，不阻塞条件 1（SPECS 注记在案）。
- F-3（真实 connector 验收）：B6 若 09-12 用真实 connector 跑通试点即闭环；若 mock 试点则条件 7 挂账说明，不阻塞 MVP（真实试点属生产化 backlog）。
- O12 计价端到端补验：A5/B6 的 receipt 成本字段为 schema 预留位，O12（09-11）交付后补验——计价缺失不阻塞 A5/B6 accepted（SPECS 注记在案），MVP 不依赖端到端计价。
