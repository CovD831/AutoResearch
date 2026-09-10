# Owner 线任务队列（P1-I Owner Lane）

Owner 职责定位（2026-09-09 确定）：成员 PR 审核与合并、小修不打回直接补 follow-up PR、独立裁决与集成收口。Owner 线与成员 A/B lane 并行推进，Owner 侧改动继续走 main 直推（保护窗口流程）或 follow-up PR，不改变现有集成流程。

本表为 Owner 全量工作视图：先列已完成（历史节选），再列未完成（排队，按触发时机排序）。

## 一、已完成（历史节选，详见 git log 与 .ai-team/TASK.md）

- 09-04 团队协作基线：repo-task-sync 体系、bot-first PR 审查工作流 + CI 审查检查、异步团队基线（8d821c0 / d26c54f / c0f8fbc / fd0f204）
- 09-04~06 P1 双 lane 拆分：任务包、验收标准、任务注册表（docs/tasks/ · TASK-PACKAGE-REGISTRY.md）
- 09-07 PR #1/#2 深度审查 → findings 转 B2/A2 Gate 条款（PR #3）
- 09-08 B2 follow-up PR #6（小修不打回直接补的职责先例）
- 09-09 A2 贴合度复审 + follow-up PR #7（F-4 审计原子化、StaleIdempotencyWriteError、recovery API 清理）
- 09-09 I0 契约统一（72fb544）→ I1 编排（6b706df）→ I2 主线 E2E + S1 promotion（dad4658，S2-A/S2-B 转 ready）
- 09-09 S2 MCP scope 裁决（15a5490，登记进 A3/B3 TASK-SPECS）

## 二、未完成（排队）

| Task | 状态 | 依赖 / 触发时机 | 交付重点 | 预估 |
|---|---|---|---|---|
| O1 成员 PR 审核与 follow-up 集成 | active（常驻） | 成员每次提交；当前无悬挂 PR | 成员 PR 人工审查（bot 审查后）；小修改不打回、直接 follow-up PR 补齐（先例：PR #6、PR #7）；撞车裁决 owner 集成（先例：D-S2-01 / PR #10）；合并窗口与分支保护恢复；后续 S3/S4 PR 的深度审查并入本项。**PR 纯净性（PR #6 教训）：follow-up PR 只装代码小修；文档/归档批量入库单独开 docs PR，不得混装** | 每次 ≤0.5 天 |
| O2 F-8 R003 空结果语义裁决 | done（2026-09-10，D-F8-01） | — | 裁决文档 `docs/coord/empty-result-ruling.md`：`completed_empty` 为确定性成功终态、`unknown_outcome` 仅限中断恢复；R003 L3 已注记、TASK-SPECS A2 F-8 关闭 | 0.5 天 |
| O6 S2 promotion gate | done（2026-09-10） | S2-A/S2-B integrated | 四项核验通过（blocking 清零含 F-8 关闭 / E2E 绿 108 passed / 证据可重跑 / 下游合同稳定）→ S2-A/S2-B 转 accepted、S3-A/S3-B 转 ready（base main@535f208） | 0.5 天 |
| O7 S3 promotion gate | 未开始 | A4 + B4 均 accepted **当天** | 四项核验同上 → S4-A/S4-B 转 ready。gate 不过夜 | 0.5 天 |
| O3 I3 账本收口 | 未开始 | O6 通过后 ✅（<b>09-10 排期提优：提前至今日 09-10 下午完成</b>） | registry 终态回写、invariants.md 刷新、演进协议归档、validate_registry 校验（B6 的 I3 硬前置 09-10 晚闭环） | 0.5 天 |
| O5 F-3 真实 connector 验收标准 | 未开始 | S4 开工前（<b>09-10 排期提优：挪至 09-12 空窗完成</b>） | 异常→状态分类边界的复验标准定义（S4-B 真实试点验收前置，挂账见 A2 TASK-SPECS） | 0.5 天 |
| O4 B7 稿件审核 + I4 交付检查 + MVP-CLOSED 判定 | 未开始 | B7 交付后（09-13 晚，前移一天） | 稿件审核（审核不自批，owner 为审核方）、local delivery manifest 核对、MVP-CLOSED 判定、B7 成员任务映射确认 | 0.5–1 天 |
| O12 ProviderLane 与 LLM 调用底座（新增 2026-09-10） | **speculative·段1进行中（2026-09-10 下午开工，老板拍板不等前置）** | B4 accepted（LLM adapter contract）+ O7；<b>09-10 排期提优：09-10 晚 gate 后领取、09-11 交付（提前一天）</b>；B4 未 accepted 则顺延 09-12（gate 未过只 speculative）。实施计划见 `tasks/O12-provider-lane/PLAN.md`（pi-ai 六机制源码规格已调研完毕，段1=设计/快照/fixture 合规活动，段2=O7 后对缝实现） | `provider_lane.py`：lane 不可变身份 + pi-ai 语义（模型目录含 cost/contextWindow、usage→receipt 计价、reasoning 档位、跨 provider handoff、constrained-sampling 降级）+ 本地 openpilot 代码参考（`provider_lane.py` 预算档/凭据白名单/漂移 fail-closed、`provider_tool_admission.py` 准入决策）；`llm.py`（76 行裸调用）替换；A5 计价链与 B6 写作头切换的供给方；<b>建议走 PR + 成员 A 人工复审</b>（审核不自批原则对 Owner 同样适用，A 为 runtime 域复审人，且 09-12 在做 A6 有上下文） | 1 天 |
| O8 ADR-01 外部模块选型定稿（新增 2026-09-10） | **完成（2026-09-10，待提交确认）** | 09-10 下午（<b>09-10 排期提优提前</b>；原记载 09-11/09-12 不一致一并修正）；AGPL 签字＝09-11 B5 前置、pi-ai 决策＝09-10 晚 O12 依据 | 已落 `docs/coord/adr-01-external-integrations.md`（Accepted）：Owner 指令逐槽位充分调研 → 3 个并行调研代理复核 12 个争议槽位（证据 URL 内嵌），<b>9 维持 / 3 调整 / 1 更名</b>——槽位3 PDF 解析默认改 <b>docling(MIT)</b>（质量 0.86–0.88 vs pymupdf4llm 0.57–0.73，AGPL 规避成立，pymupdf 降兜底）、槽位2 <b>OpenAlex 降级可选</b>（2026-02 起强制 key+计费）、槽位11 <b>B5 自建 gold set 为主</b>（ScholarQABench 跑分需 LLM 裁判，违反零 API）、「CITE-AI」查无出处弃名改用 ScholarQABench 指标名；签字块 1（pi-ai 语义移植）、签字块 2（PDF 许可）均已签署（2026-09-10「按调研决定」），ADR-01 全文生效；消费方＝O12/A5/B5/B7（旧口径 A6/B7 已随重排修正）；待监控五项见 ADR 第 5 节 | 0.5 天 |
| O9 孤儿模块激活一期（09-10 缩减：接线点①实现前移成员 A6，映射表由成员拟定随 PR 提交，Owner 保留验收） | 未开始 | MVP-CLOSED 后（不占关键路径） | ②promoted 经验 → writer context 的 Markdown skill 注入（agentskills.io 形态，program.md 范式）③Evidence 准入 → papers 分库 WikiPage 镜像；ExperienceRecord 拆 rule 型（进 Gate 条款）/capsule 型（进 writer context） | 0.5–1 天 |
| O10 孤儿模块激活二期（09-10 缩减：向量检索实现前移成员 A7） | 未开始 | O9 后，依赖 A5（固定评估口径） | EvolutionService 补验证器设计与验收：proposal → A5 跑分 → 指标改进 accepted / 无改进 abandoned（生命周期加 abandon 终态，karpathy Ratchet 吸收）；全程 proposal-only + owner 批准（与 EvoMap knowledge_base 人工审核同构）；向量检索实现已在 A7 | 0.5–1 天 |
| O11 治理层公开 demo + 打榜准备（新增 2026-09-10） | 未开始 | O10 后或并行（非关键路径） | 「给 EvoMap 输出套治理层」公开对比 demo（借同名流量立差异化）；ScholarQABench 跑分与「换生成器不掉级」回归网演示；差异化叙事稿（可插拔治理 / 成本可审计 / 受控进化 / 数字可承诺） | 1–2 天 |

分工说明：MVP 推进不是 Owner 独占——A5/B6/B7 为成员任务；Owner 独占的是裁决、验收与 LLM 底座（O12），总量约 4 天，全部踩在关键路径或紧后增量上：成员两条线都卡在 Owner 的 gate 上，gate/审核不过夜就是最大的提速杠杆。

> 2026-09-10 排期提优（老板拍板）：O3/O8 提前至 09-10 下午；O12 提前至 09-10 晚 gate 后领取、09-11 交付；O5 挪 09-12 空窗。收益：A5 计价链当轮真验收、B6 无 llm.py 直连临时路径、09-12 整天空出作 B5→B6→B7 最重一串的机动日。

每个裁决/收口任务产出独立文档或 registry 回写，审查类工作（O1）以 PR review 记录为准，不单独开 PR。

## 三、外部项目吸收点 → 落位任务映射（2026-09-10，老板要求显式化）

| 吸收点 | 来源项目 | 落位任务 | 状态 |
|---|---|---|---|
| 三约束评估纪律（单一主指标 / 固定语料与预算 / 口径冻结须 owner 裁决） | karpathy（单文件/5 分钟预算/val_bpb） | **A5 评估纪律条款** | 已落包 |
| Ratchet 棘轮验证器（proposal → 跑分 → 改进保留/退化 abandon） | karpathy Ratchet | **O10** | 已落包 |
| 失败显式沉淀（被拦截/被打回的产物归档为失败经验，不得丢弃） | karpathy FAILED.md | **O9 接线点①** + **B6 交叉评审条款**（被打回版本归档） | 已落包 |
| program.md 范式（经验编译为人类可读可 git 的 Markdown skill，非 API 参数） | karpathy program.md | **O9 接线点②**（agentskills.io 形态） | 已落包 |
| Gene/Capsule 两粒度经验（rule 型进 Gate 条款 / capsule 型进 writer context） | Evolver（EvoMap 生态） | **O9**（ExperienceRecord 拆分） | 已落包 |
| ≥3 模型交叉评审 + 独立盲审（仅 candidate 参考，不进 Gate） | EvoMap | **B4 契约**（writer port 支持多模型调用形态）+ **B6 交叉评审条款**（双版本生成、盲审差异入审计事件） | 已落包（本轮补） |
| knowledge_base 人工审核后才纳入 | EvoMap | **O10**（proposal-only + owner 批准的设计背书，非新增工作） | 设计已有 |
| 全落盘可恢复 / 负结果保留 | EvoMap | 已内建（A lane receipt/replay + D-F8-01 completed_empty）——**O11 对比 demo 的正面素材**，非新增工作 | 已有 |
| 中间结果经主 Agent 转述保留率仅 55.5% → 结构化通道必要性 | EvoMap 蜂群实验 | 论文论据（审计事件即结构化通道）——O11 叙事稿素材 | 素材 |
| 指标设计决定群体行为（防经验注入回音室） | EvoMap 蜂群实验 | O10 设计时考虑（经验注入的展示与排序规则由 owner 定） | 备忘 |

> 本表与 workspace `docs/autoresearch-生态调研-2026-09.md` 第七节同源；吸收点若新增，先登记本表再落任务包。
