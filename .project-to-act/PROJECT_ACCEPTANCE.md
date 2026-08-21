# 项目验收

> 执行测试、交付或声明完成前必须读取本文件。没有新鲜证据时不得写成通过。
> 不粘贴密钥、完整个人信息、原始顾客对话或未脱敏工具输出。

## 当前验收结论

- 结论：P0 规划交付通过；AutoResearch 产品运行时未实现、未验收
- 验收范围：本轮仅验收详细计划书、功能表、根 Project-to-Act 和论文项目模板
- 最后检查：2026-08-21（P0 收口检查）
- 遗留问题：所有产品运行时标准待后续阶段；真实论文 idea、模型配置和部署规模尚待确认

## 验收标准

### P0 规划交付验收标准

| 标准 ID | 标准 | 状态 | 验证方法 | 证据 ID |
|---|---|---|---|---|
| A-P0-001 | 根 Project-to-Act 唯一事实源配置有效 | 已通过 | 根目录运行 `--validate` | E-PLAN-001 |
| A-P0-002 | 详细计划覆盖用户指定全部环节与严格五 Agent | 已通过 | 标题/关键词/角色/约束结构检查 + 人工复核 | E-PLAN-001 |
| A-P0-003 | 功能表是状态唯一清单，包含优先级、依赖、完成条件 | 已通过 | 解析 `PROJECT_FEATURES.md` 并检查功能 ID 唯一 | E-PLAN-001 |
| A-P0-004 | 论文项目模板包含独立 `.project-to-act` 并验证 | 已通过 | 模板根运行 `--validate` | E-TPL-001 |
| A-P0-005 | 模板覆盖 intake/scope/literature/innovation/execution/writing/review/delivery/evidence/handoff/state | 已通过 | 目录与必需文件 allowlist 检查 | E-TPL-001 |
| A-P0-006 | 现有底座能力与缺口基于当前文件和测试，而非推测 | 已通过 | 运行 28 项相关 unittest；检查模板 Agent 数与 pyproject | E-BASE-001 |
| A-P0-007 | LangGraph 与学术检索选择有当前官方来源 | 已通过 | 核对 LangGraph/OpenAlex/Crossref/Semantic Scholar 官方文档 | E-WEB-001 |
| A-P0-008 | 计划未把文档或候选底座写成产品已完成 | 已通过 | 搜索完成/已实现/验收措辞并人工复核 | E-PLAN-001 |

### 产品运行时验收标准

| 标准 ID | 标准 | 状态 | 验证方法 | 证据 ID |
|---|---|---|---|---|
| A-RUN-001 | 业务 Agent 恰好五个且职责/权限隔离 | 待检查 | 配置 schema + 权限/路由测试 | 无 |
| A-RUN-002 | LangGraph checkpoint 可恢复，interrupt 可人工继续 | 待检查 | 崩溃恢复与 resume 集成测试 | 无 |
| A-RUN-003 | 跨 Agent 交接 100% 结构化且无完整上下文堆砌 | 待检查 | schema/负例/大小限制测试 | 无 |
| A-RUN-004 | 证据 H/P/X/R 分级、claim 绑定、失效/替代可追溯 | 待检查 | 数据模型、迁移与查询测试 | 无 |
| A-RUN-005 | L0–L4 门禁 fail-closed，证据不足/未闭环/打回不能前进 | 待检查 | policy table + bypass/adversarial 测试 | 无 |
| A-RUN-006 | L3/L4 危险动作先检索证据并按需 interrupt | 待检查 | 审计 trace 与无证据负例 | 无 |
| A-RUN-007 | 论文搜索多源、去重、版本、撤稿/更正和检索日志完整 | 待检查 | gold queries + 手工标注集 | 无 |
| A-RUN-008 | 论文读取支持全文 locator、总结、陪读、claim map 和创新候选 | 待检查 | 固定论文集人工盲审 | 无 |
| A-RUN-009 | 创新候选完成最近似工作和反向检索，不把 UNKNOWN 写成创新 | 待检查 | 已知重复 idea 和反例回归 | 无 |
| A-RUN-010 | 工作包与 RunManifest 可复核，未执行计划不能变成结果 | 待检查 | fake-run/adversarial + 实际运行测试 | 无 |
| A-RUN-011 | 写作只消费已放行 claim，关键事实/数字/结果证据绑定 100% | 待检查 | manuscript claim-citation audit | 无 |
| A-RUN-012 | 审核可定向打回并在修订后复验，无自批或改证据放行 | 待检查 | reviewer/gate 权限测试 | 无 |
| A-RUN-013 | paper/experience/knowledge/user/project/evidence 分区与 ACL 生效 | 待检查 | 跨分区污染和权限负例 | 无 |
| A-RUN-014 | Wiki revision、Graph 投影、vector/FTS 检索可重建且一致 | 待检查 | outbox 水位、重建和一致性测试 | 无 |
| A-RUN-015 | 经验 X0–X4 有复现、反例、晋级/降级、灰度和回滚 | 待检查 | evolution proposal 回归 | 无 |
| A-RUN-016 | 用户画像区分 explicit/inferred/confirmed，可查看/修改/删除 | 待检查 | 隐私与生命周期测试 | 无 |
| A-RUN-017 | 外部副作用幂等，checkpoint 恢复不重复投稿/发送/写入 | 待检查 | 故障注入与 outbox 测试 | 无 |
| A-RUN-018 | 真实论文试点从 idea 到本地稿件完成并保留证据链 | 待检查 | 端到端验收 | 无 |
| A-RUN-019 | 外部投稿/发布、删除/覆盖和高成本操作有 H3 人工批准 | 待检查 | E2E 负例 + audit | 无 |
| A-RUN-020 | 备份、恢复、迁移、秘密扫描、许可和操作手册通过 | 待检查 | 发布清单 | 无 |

## 证据索引

| 证据 ID | 时间 | 方法或命令 | 退出状态 | 版本或文件哈希 | 结果摘要 | 证据位置 | 有效期 |
|---|---|---|---|---|---|---|---|
| E-BASE-001 | 2026-08-21 | `python -m unittest tests.test_evidence_and_gates tests.test_knowledge_memory_evolution tests.test_workflow_spec -v`；解析 AutoResearch JSON 与 pyproject | 0 | 嵌套仓库当前工作树 clean；hash 待最终收口 | 28 tests OK；现有模板 14 Agent；LangGraph 为 optional dependency | `DeepReason-Agents-Framework/` 与本轮工具日志 | 30 天或底座变更前 |
| E-WEB-001 | 2026-08-21 | 官方文档核验 | 0 | URL/抓取日期 2026-08-21 | 核验 LangGraph persistence/subgraphs/interrupts 与 OpenAlex/Crossref/S2 API 边界 | `docs/AutoResearch_详细计划书.md` 官方链接 | 90 天；实现启动时刷新 |
| E-PLAN-001 | 2026-08-21 | 根 `--validate`；22 术语/五角色/功能 ID/字段/相对链接/措辞/秘密样式检查 | 0 | 计划 SHA-256 `2b0b0d84...60c1b`；功能表 `6708f591...cb0203` | 计划 529 行；五角色恰好 5；86 个功能 ID 唯一且 7 字段合法；链接通过 | `evidence/P0_PLANNING_EVIDENCE.md` | 文件变化前 |
| E-TPL-001 | 2026-08-21 | 模板 `--validate`；20 个必需路径；外部发布默认关闭；秘密样式检查 | 0 | 模板树 SHA-256 `8e9926a6...3688a2`；21 files | 模板账本有效、结构完整、无密钥样式内容 | `evidence/P0_PLANNING_EVIDENCE.md` | 模板变化前 |

## Gate 记录

| Gate ID | 日期 | Gate | 对象 | 结果 | 证据 ID | 豁免与确认人 |
|---|---|---|---|---|---|---|
| G-P0-001 | 2026-08-21 | P0 规划交付 | 计划书、功能表、根账本、论文项目模板 | PASS | E-PLAN-001、E-TPL-001 | 无豁免 |

## 验收记录

按时间倒序追加：日期、检查范围、证据 ID、结果、遗留问题和结论。失败、跳过与过期证据也必须如实记录。

- 2026-08-21｜P0 收口：计划书、86 项功能表、根/模板 Project-to-Act、模板结构、相对链接、字段、密钥样式和现有底座核验｜E-BASE-001、E-WEB-001、E-PLAN-001、E-TPL-001｜P0 PASS｜遗留：产品运行时全部阶段尚未实现；真实论文试点未开始｜结论：规划交付完成，项目产品不可声明完成。
