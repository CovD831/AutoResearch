# Task Package Registry

> 这是全局任务队列和集成索引，不替代任务包中的详细说明。

成员长期任务包：

- [P1-A Runtime Lane](../tasks/P1-A-runtime-lane/LANE-README.md)
- [P1-B Evidence/Domain Lane](../tasks/P1-B-evidence-lane/LANE-README.md)

两个 lane package 只包含成员 A/B 的任务序列；`I0–I4` 和 `MVP-CLOSED` 是负责人主线任务，不进入成员 ZIP。

| Task ID | Phase | Owner lane | Branch | Status | Base | Depends on | Merge after | Next package |
|---|---|---|---|---|---|---|---|---|
| P1-A-RUNTIME-RECOVERY | P1/S1 | runtime | merged via PR #2 | accepted | — | — | — | P1-A2 |
| P1-B-EVIDENCE-PIPELINE | P1/S1 | evidence/domain | merged via PR #1 | accepted | — | — | P1-A | P1-B2 |
| P1-A2-RUNTIME-HARDENING | P1/S1 | runtime | `codex/p1-a2-runtime-hardening` merged via PR #5 + owner follow-up PR #7 | accepted | P1-A | P1-A | — | S2-A |
| P1-B2-EVIDENCE-ADVERSARIAL | P1/S1 | evidence/domain | `codex/p1-evidence-adversarial` merged via PR #4 + owner follow-up | accepted | P1-B | P1-B | — | S2-B |
| S2-A-AUDIT-RUNTIME | S2 | runtime | `codex/s2-a-audit-runtime` merged via PR #8 (`dae10f3`) + owner follow-up PR #11（F-9/F-10） | accepted（O6 S2 promotion，2026-09-10：四项核验通过） | `main@6b706df`（实际 base `main@15a5490`） | S1 promotion | — | S3-A |
| S2-B-AUDIT-EVIDENCE | S2 | evidence/domain | `codex/s2-audit-evidence`（PR #9）经 owner D-S2-01 集成调整后以 PR #10 合入（`2d4029a`） | accepted（O6 S2 promotion，2026-09-10：四项核验通过） | `main@6b706df`（实际 base `main@dad4658`） | S1 promotion | — | S3-B |
| S3-A-CAPABILITY-ADAPTERS | S3 | runtime | `codex/s3-a-capability-adapters` merged via PR #12 (`f620915`) | accepted（O7 S3 promotion，2026-09-10：四项核验通过） | S2 promotion | S2 promotion | — | S3-A2 |
| S3-A2-PROVIDER-LANE | S3 | integration/lead（Owner O12，2026-09-10 重排：需参考本地 openpilot 代码故归 Owner 亲自实现；真实检索 adapter 归 A5） | `owner/provider-lane` merged via **PR #15** (`ba6fdf8`) | **integrated**（2026-09-14：owner 两轮代修（C1–C4 / P1-1~P2-2，共 8 条成员意见全部复现为真）+ 独立盲审 + 判别力实测；合并后 `main` 全量 481 passed / 0 error） | B4 accepted（LLM adapter contract）+ O7 | S3 promotion | — | S4-A |
| S3-B-READER-WRITER-PORTS | S3 | evidence/domain | `codex/s3-reader-writer-ports`（PR #13，superseded）经 owner 集成 PR #14 合入（`7b88e30`，D-SYNC-01 先例：rebase + 孤儿 map-key gate 检查 + 更名） | accepted（O7 S3 promotion，2026-09-10：四项核验通过） | S2 promotion | S2 promotion | — | S3-B2 |
| S3-B2-DATA-SOURCES | S3 | evidence/domain | `codex/s3-b2-data-sources`（PR #16，superseded）经 owner 集成 PR #17 合入（`7fdfb89`：撤稿判据改 `updated-by[]`、fixture 依真实 payload 重录、指标口径分离、解析层 fail-closed；记录见 `reviews/PR16-B5-deep-review.md` 与 `PR16-B5-fix-review.md`） | accepted（2026-09-11：owner 深审发现阻断缺陷后代修，独立对抗审查复核；聚焦 20 / 全量 166 passed） | B4 accepted + S3 promotion | S3 promotion | — | S4-B |
| S4-A-BENCHMARK-HARNESS | S4 | runtime | main | integrated（2026-09-11：owner 深审 + 代修（D-A5-12~16）+ owner 集成 **PR #19** squash 合入 `8f6e7de`，取代 #18） | S3 promotion | S3 promotion | — | S4-A2-EXPERIENCE-WIRING |
| S4-B-REAL-PILOT | S4 | evidence/domain | reserved | ready（O7 S3 promotion，2026-09-10；B6 EvoMap 交叉评审条款见 B 线 TASK-SPECS） | S3 promotion | S3 promotion | — | — |
| S4-A2-EXPERIENCE-WIRING | S4 | runtime | `owner/s4-a2-integration` merged via **PR #21** (`febd12d`)，supersedes #20 | **integrated**（2026-09-14：owner 三轮审查 + 三轮代修；1 高 + 4 中 + 1 低全部关闭；失败注入矩阵 `scripts/experience_sink_failure_matrix.py` 7/7） | A3/B3 accepted（已满足） | O7（已过） | — | — |
| S4-A3-KNOWLEDGE-VECTOR | S4 | runtime | reserved | planned（追加包 2026-09-10：sqlite-vec + bge-small 向量检索，原 O10 实现部分前移成员 A，见 A 线 TASK-SPECS A7） | A6 | — | — | — |
| O13-CAPABILITY-MANIFEST | S3 | integration/lead（Owner 亲自实施，2026-09-11：定性为 O 线变更——改写冻结 L2 §CapabilityManifest，成员包不得单方面改写） | `owner/o13-capability-manifest` merged via **PR #22** (`ac782d1`)，基于 `main@60a9ea4` | **integrated**（2026-09-14：owner 独立盲审后自修——修 D-O13-10（契约必备字段 `entrypoint`/`evidence_mode` 从未被校验，3 个 built-in 全未声明）；D-O13-11 判定为虚警并回退（空候选是 `D-F8-01` 的确定性终态成功）；D-O13-07/D-O13-08 两处偏离经 owner 批准按实现为准） | `main@1e7e196` | S3-A accepted（已满足） | — | O14-CAPABILITY-CATALOG |
| O14-CAPABILITY-CATALOG | S3 | integration/lead | reserved | planned（注册目录 + 内置多选；依赖 O13；首批仅 `paper_search` 单槽，含 PLAN §2.8 可插拔判据 P1–P5） | O13 | — | — | — |
| S4-A4-MAINLINE-ADAPTER | S4 | integration/lead（Owner 亲自实施，2026-09-14：执行 `D-A5-偏离-1` 选项 (a)，触及 `application.py` / `search_service.py` 等 A5 禁区文件） | `owner/a8-mainline-adapter`（未推送） | active（本地：新增 `AdapterBackedPaperSearchService` + `retrieve()` 原语 + 装配切换；基线 509 → **525 passed**、ruff/compileall/check.mjs 全绿、判别力 2 判据型） | `main@04ce9a9` | S4-A-BENCHMARK-HARNESS integrated（已满足） | — | S4-A5-HANDOFF-BY-REFERENCE |
| S4-A5-HANDOFF-BY-REFERENCE | S4 | integration/lead（Owner 亲自实施，2026-09-14：改写冻结的 `contracts.py` HandoffEnvelope 语义，成员包不得单方面改写） | `owner/a8-mainline-adapter`（与 A8 同分支，未推送） | active（本地：交接单由内容承载改为引用界；基线 A8 525 → **532 passed**、判别力 4 判据型） | `owner/a8-mainline-adapter`（A8） | S4-A4-MAINLINE-ADAPTER（已满足） | — | A10 |
| S4-A6-BIBLIOGRAPHIC-CLAIM | S4 | integration/lead（Owner 亲自实施，2026-09-14：处置第二轮独立盲审的 F4/N1，触及 `capability.py` / `invocation_contracts.py` 等 A8/A9 禁区） | `owner/a8-mainline-adapter`（与 A8/A9 同分支，未推送） | active（本地：共享书目写入函数 + claim 只描述实际材料 + 不可归属命中拒绝铸 E1 + `receipt.provider_failure`；基线 A9 538 → **546 passed**、判别力 5 判据型） | `owner/a8-mainline-adapter`（A9） | S4-A5-HANDOFF-BY-REFERENCE（已满足） | — | S4-A3-KNOWLEDGE-VECTOR |
| I0-SHARED-CONTRACT-INTEGRATION | MVP | integration/lead | `main` | integrated | P1-A + P1-B | P1-A, P1-B | I1 | — |
| I1-PIPELINE-ORCHESTRATION | MVP | integration/lead | `main` | integrated | I0 | I0 | I2 | — |
| I2-MAINLINE-E2E-AND-PROMOTION | MVP | integration/lead | `main` | integrated | I1 | I1 | I3 | — |
| I3-PROJECT-LEDGER-CLOSURE | MVP | integration/lead | `main` | integrated（首轮收口 2026-09-10：S2-A/S2-B 账本 accepted 对齐、演进协议 D-EVOL-01 Decisions 归档、Project-to-Act 阶段回写、check.mjs 全绿；最终 accepted 判定挂 O4/MVP-CLOSED 条件 5） | I2 | I2 | I4 | — |
| I4-MANUSCRIPT-DELIVERY-CHECK | MVP | integration/lead | `main` | planned | I3 + S4-B | I3, S4-B | MVP-CLOSED | — |
| MVP-CLOSED-MINIMAL-E2E | MVP | integration/lead | `main` | waiting-for-gate | A/B + I0-I4 | all MVP rows | — | — |

## 状态定义

- `planned`：只有路线和目标。
- `waiting-for-gate`：可以准备，不可正式实现或合并。
- `ready-next`：当前任务完成后可立即领取。
- `ready`：依赖满足，可以创建 worktree。
- `active`：成员正在实施。
- `submitted` / `reviewing`：已提交，等待负责人审查。
- `integrated`：已合并到主线。
- `accepted`：完成阶段验收并有新鲜证据。
- `speculative`：接口冻结后的隔离预研，不得进入主线。

## MVP 闭环定义

`MVP-CLOSED-MINIMAL-E2E` 不是成员任务包，而是负责人最终验收项。只有以下条件全部满足，才能将其标记为 `accepted`：

1. A 线任务和 B 线任务均已 `accepted`；
2. `I0–I1` 完成共享合同、application 组装和 pipeline 编排；
3. `I2` 在合并后的主线上跑通一条最小 Evaluation Section 场景；
4. Paper Search、Evidence、材料就绪、BenchmarkPlan、SectionDraft、RuleValidation 的状态和证据可追溯；
5. `I3` 完成 Project-to-Act、task ledger、artifact 和验收证据收口；
6. `I4` 完成最小 manuscript/local delivery 检查，未执行结果、unknown 和缺失材料没有被写成已完成事实；
7. 所有 blocking findings、失败路径和回滚边界均有处理记录。

MVP 闭环完成后，仍允许存在生产化、性能、多论文类型、多 venue、完整 UI 和长期知识库等优化 backlog；这些不应阻塞最小端到端 MVP，除非它们违反可信边界。

## 更新规则

1. 成员只更新自己任务的 task-local ledger 和任务包。
2. 负责人更新本表、`.ai-team/TASK.md` 和 Project-to-Act 的阶段状态。
3. 状态变化必须带证据路径或命令。
4. ZIP 是分发载体；解压后的任务包源文件必须进入成员分支并与代码一起交接。
