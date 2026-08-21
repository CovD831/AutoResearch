# 项目进度

> 记录当前执行状态与有效工作节点；普通查看、搜索和无状态变化的命令不写入。

## 当前任务

| 任务 | 状态 | 负责人 | 完成条件 | 证据 ID | 最后更新 |
|---|---|---|---|---|---|
| P0-01 现有框架与官方资料核验 | 已完成 | Codex | 本地相关测试通过；LangGraph/论文索引官方能力有来源 | E-BASE-001、E-WEB-001 | 2026-08-21 |
| P0-02 详细计划书与五 Agent 架构 | 已完成 | Codex | 计划书覆盖用户全部环节并通过结构检查 | E-PLAN-001 | 2026-08-21 |
| P0-03 功能表与验收基线 | 已完成 | Codex | 功能状态唯一、每项有优先级/依赖/完成条件 | E-PLAN-001 | 2026-08-21 |
| P0-04 论文项目文件夹模板 | 已完成 | Codex | 模板目录完整，子项目 `.project-to-act` 校验通过 | E-TPL-001 | 2026-08-21 |
| P1-01 状态/交接/证据/Gate 合同 | 进行中 | Codex | 基础 schema、单元测试和 fail-closed 已通过；历史迁移待补 | E-RUN-001 | 2026-08-22 |
| P1-02 最小 LangGraph 父图与五子图 | 进行中 | Codex | SQLite checkpoint/interrupt/resume 已通过；进程重启、分布式幂等待补 | E-RUN-001、E-JOURNEY-001 | 2026-08-22 |
| P2 论文搜索与读取纵向切片 | 进行中 | Codex | 三连接器、题录、阅读卡、locator、陪读已落地；gold corpus 和人工质量验收待补 | E-RUN-001、E-LIVE-001 | 2026-08-22 |
| P3 创新挖掘与工作执行 | 进行中 | Codex | hypothesis、反证条件和证据化 WorkPackage 已落地；RunManifest/真实实验待补 | E-RUN-001 | 2026-08-22 |
| P4 写作与审核 | 进行中 | Codex | 缺口稿、版本化修改/润色、L3 审核打回已通过；真实 claim audit 待补 | E-RUN-001、E-JOURNEY-001 | 2026-08-22 |
| P5 Wiki+Graph、画像与自进化 | 进行中 | Codex | 分区 Wiki/一跳图、画像、经验晋级和 proposal-only 已落地；向量/灰度/回滚待补 | E-RUN-001 | 2026-08-22 |
| P6 真实端到端试点与 v1.0 | 已规划 | 待指定 | `PROJECT_ACCEPTANCE.md` 全部运行时标准通过 | 无 | 未开始 |

## 阻塞项

| 阻塞 | 影响 | 解除条件 | 状态 |
|---|---|---|---|
| 尚未提供首个真实论文 idea | 无法建立 gold query、真实阅读集与端到端论文试点 | 用户在 P2 前提供 idea、领域、目标和资源边界 | 不阻塞 P0/P1，阻塞 P2 验收 |
| embedding 配置与检索模型未选定 | 无法进行真实向量召回质量评测 | 在取得真实论文 corpus 后按安全配置流程选择并锁定版本 | 不阻塞 foundation；阻塞向量验收 |
| 目标部署规模未确认 | Neo4j/对象存储/并发容量只能按默认单团队方案规划 | P1 明确本地单机、内网团队或云端部署 | 待决策 |

## 下一步

1. 由用户提供首个真实论文 idea、领域、目标 venue、可用全文与实验资源边界。
2. 用真实语料建立 gold query、ReadingCard/locator 人工基准和创新重复反例。
3. 补 RunManifest、artifact lineage、checkpoint 进程重启和分布式幂等测试。
4. 在生产化前引入 PostgreSQL/pgvector 与可重建图投影，不先扩建无证据 UI。

## 进度历史

按时间倒序追加：日期、完成事项、证据 ID、遗留问题、下一步和确认来源。不要覆盖旧记录。

- 2026-08-22｜交付 0.1.0 foundation：VibeCollab 管理的严格五 Agent LangGraph、证据/Gate/状态/handoff、三论文连接器、阅读/陪读/创新、工作包、写作/修改/审核、Wiki+Graph、画像、经验、自进化提案、CLI/API 和论文项目运行投影；18 tests、84% coverage、3 个核心 HTTP 旅程与 1 个健康旅程通过｜证据：E-RUN-001、E-JOURNEY-001、E-LIVE-001、E-PROJECT-001｜遗留：真实 idea/gold corpus/实验/生产数据库/灾备未验收｜下一步：真实论文试点｜确认来源：用户本轮构建指令。
- 2026-08-21｜完成 P0：初始化根 Project-to-Act；核验嵌套 DeepReason 候选底座与官方资料；交付详细计划、86 项功能表和论文项目模板；双层账本/结构/链接/字段/秘密扫描通过｜证据：E-BASE-001、E-WEB-001、E-PLAN-001、E-TPL-001｜遗留：产品运行时尚未实现，真实论文 idea 未提供｜下一步：P1 合同与最小父图｜确认来源：用户本轮指令。
