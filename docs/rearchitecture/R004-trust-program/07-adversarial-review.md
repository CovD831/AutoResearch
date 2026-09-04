# R-004-07 对抗性审查与双向钢人论证

> 审查方式：作者自审（fresh pass，逐文档重读后攻击）。**无独立 reviewer——此为已披露的限制**；且本仓库存在并行包生产线（Codex），F-8 即由其暴露——后续包创建应先检查 `.rearchitecture/dispatch-log` 与目录再取号；建议 S2 promotion 前由未参与本包的上下文执行一次独立复审。审查发现 F-1 至 F-4 已在本包内即时消费（修订见各文档），F-5 至 F-7 保持 open 并由后续门禁闭环。

## 对抗性审查发现

| Finding | Evidence | Severity | Decision | Consuming action | Owner/gate |
|---|---|---|---|---|---|
| F-1 capability trust tier 是新增概念但未列入复杂度预算 | 02 修订 2 引入 tier，01 预算表初版缺失 | blocking（预算完整性） | accept（已消费） | 01 预算表补报第二名词及理由 | 复杂度 gate / 已闭环 |
| F-2 AuditReport artifact 持久化无唯一写入者，与 sole-writer 表冲突 | 02 初版表格行含糊 | blocking（重复权威风险） | accept（已消费） | 02 表：内容归 Audit Module 经 Persistence Port，ArtifactLink 归 Evidence Module | L1 gate / 已闭环 |
| F-3 幂等声明被活查询破坏：resolver 状态变化会使同稿两次审计结果不同 | 04 初版"相同 manuscript hash + corpus 版本" | blocking（契约可验证性） | accept（已消费） | 04：resolver 响应缓存为带版本快照，幂等定义覆盖快照版本 | S2 合同冻结 / 已闭环 |
| F-4 外部 MCP 调用者无项目上下文，standalone 场景下 admission/receipt 语义未定义 | 04/Audit 出口定义 | blocking（对外契约空洞） | accept（已消费） | 04：新增 in-runtime / standalone 双形态及各自语义 | S2 合同冻结 / 已闭环 |
| F-5 继承的当前事实（application 集中装配、search 混合持久化、Agent 直连 Store）来自被取代包，本轮未对照源码复核 | 00/03 的 current claims | non-blocking | accept（保持 open） | S0 inventory 脚本产出须与三条 claim 一致，不一致则修订 03 | S0→S1 gate |
| F-6 `model_assisted` verdict 一致性阈值未冻结，Audit L2 保持 conditional 是诚实但悬空的 | 04 状态标记 | non-blocking | accept（保持 open） | S2 实现时用标注 fixture 冻结阈值后方可去 conditional | S2 promotion |
| F-7 benchmark 作者=评测者的循环偏差只记录为 limitation，未消除 | 05 S4 | non-blocking | accept（保持 open） | S4 报告必须使用外部标注集 + 公开 harness；邀请至少一位外部复核 | S4 promotion |
| F-8 初稿包编号 R-002 与并行线的 R-002-LITERATURE-PILOT 冲突，且初稿把 S1 声明为本包下一实现任务，与 in-flight 的 R-003 重复 | 包目录与 git status（capability.py、20 passed 证据） | blocking（权威链冲突） | accept（已消费） | 改名 R-004-TRUST-PROGRAM；S1 实现权威移交 R-003；ADR-2 决策权威改引 UD-001..003；08 目录改双轨规则 | 目录 gate / 已闭环 |

## 继承 finding 的处置（INDEPENDENT-2026-09-03）

| 旧 finding | 主题 | R-002 处置 |
|---|---|---|
| AR-001 / AR-001-C2 | 包完整性与 manifest 一致性 | 本包 manifest/documents/gates 对齐；07+ledger 构成闭环证据 |
| AR-002 / AR-003-C2 | S1 不是可执行合同 | 04b 冻结（typed 模型、补偿语义、命令、验收）；实现证据仍 open → S1 promotion |
| AR-003 | typed paper-search 合同 | 并入 04b；测试证据 open → S1 |
| AR-004 / AR-004-C2 | 事务/unknown 恢复语义停留在散文 | 04b 补偿语义 + tests/test_recovery_contract.py（待建）→ S1 promotion |
| AR-005 | 恢复/回滚契约 | 同上 → S1 promotion |
| AR-006 | legacy/target parity fixture | 05 S1 fixture + inventory 对照（待建）→ S1 promotion |
| AR-007 / AR-008 | 信任边界 / 接纳契约 | 02 修订 2（operator 指派 tier）+ 04 接纳上限；测试 open → S1/S2 |
| AR-009 | projection 顺序 | non-blocking；Project Ledger 投影顺序在 S2 复核 |
| AR-010 / AR-006-C2 | 用户决策无持久记录 | 06-adr ADR-2 即持久记录（2026-09-03 批准）→ 已闭环 |
| AR-002/005/007/008-C2 | ledger 消费证据缺失 | 本文件 + review-ledger.json（每条含 status/resolution）→ 已闭环 |

**门禁状态**：F-5/6/7 保持 open；AR-002/004/005/006 的实现证据类 open 且由 R-003 线闭环（本包消费其结果）——design/实现入口 gate 对 S0/S1 开放，S1 promotion 与 S2 开工 gate 关闭直至对应证据存在。这是本包的诚实状态，不是缺陷豁免。

## 双向钢人论证

### 最强支持论证

R-002 把市场已验证的稀缺能力（可审计的信任层：Google 46%→4% 伪造率模块、Claude Science auditable artifacts 均为闭源）确立为系统的固定核心，同时把已被生态做好的认知层（检索/阅读/写作 skill 与 MCP）全部变成可替换槽位——项目不再与 K-Dense/AI Scientist 拼认知质量，而是成为它们缺的那层。S1 足够小（一个 adapter 切片）且完全可证伪：parity、sole-writer、幂等、恢复任一失败即回滚。保守排除（无 plugin lifecycle、单进程、SQLite、冻结清单）防止过度建设；AuditVerdict/trust tier 各有两个真实消费者，复杂度预算第一次在包内自洽。

### 最强反对论证

这是一天内产出的第四个设计包，作者自审——前三个包的结局（abandoned/blocked/blocked）表明该项目的真实瓶颈是"设计多于实现"。R-002 的 S2–S4 篇幅远大于 S1，重演"程序包宏大、落地缓慢"的风险真实存在；且市场窗口有限（闭源巨头占位后预计 12–18 个月出现开源模仿者）。若 S1 证据迟迟不落地，R-002 只是更精美的债务清单。另外：外化 Audit 的对外契约（MCP schema、fail-closed SLA）在只有零外部用户时就承诺版本化，可能是过早契约负担。

### 综合结论

方向与合同成立，但本包的价值完全取决于 S1 是否立即实施。建议：S0 剩余项（inventory 脚本）与 S1 应作为下一个工作会话的第一任务，不插入新的设计包；S2 开工前执行一次独立复审（同时检验 F-6 阈值冻结）。若 S1 在合理窗口内无法产出晋级证据，按 05 全局停止规则保留 legacy facade并重估 S2–S4 篇幅。
