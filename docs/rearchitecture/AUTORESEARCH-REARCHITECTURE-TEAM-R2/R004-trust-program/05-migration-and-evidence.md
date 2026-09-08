# R-004-05 迁移与证据计划（S0–S4）

每片声明：交付物、fixture/oracle、晋级证据（命令）、中止/回滚。S2–S4 是**方向承诺不是实现承诺**：各自开工前须满足前片晋级证据并通过本包 review gate 的增量确认。

## S0 合并与基线（本包完成，代码零改动）

- 交付：本包；三旧包标 superseded；`scripts/dependency_inventory.py`；`evidence/inventory-baseline.txt`（checked-in）。
- oracle：脚本对 `application.py`/`agents/`/`search_service.py` 的 import 扫描结果与人工抽查一致。
- 命令：`python scripts/dependency_inventory.py > evidence/inventory-baseline.txt`。
- 中止：脚本不可重跑或结果不稳定 → 修复后再进 S1。

## S1 Paper Search 切片（实现权威：R-003，in-flight）

- 交付：由 R-003 承担（截至本包创建：`capability.py` + `test_capability_adapter.py` 20 passed；restart/timeout/failure parity 与 closure review 待补）。本包消费 R-003 晋级证据作为 S1 gate，不重复实施。
- 程序侧交付：`evidence/inventory-target.txt` 对照与治理同步清单（下述）。
- fixture：同一 paper-search 场景 legacy（native `search_service` 直连）与 target（port + adapter）双跑。
- oracle：04b 验收列表（语义等价、幂等、失败终态、重启恢复、依赖测试）。
- 命令：见 04b。
- 晋级附加项（治理同步）：`PROJECT_OVERVIEW.md` D-001 增补（五角色改写）、`docs/ARCHITECTURE.md`、`docs/FUNCTION_MATRIX.md`、`.project-to-act/PROJECT_VERSIONS.md` 同步 current 标记。
- 中止/回滚：parity、sole-writer、unknown 或 recovery 任一失败 → 停止 promotion，保留 facade 与 native 路径。

## S2 Evidence/Audit 外化

- 交付：`evidence/`、`policy/` 模块化拆分；`audit/` Audit Module；`autoresearch audit` CLI 子命令；stdio MCP server 入口。
- fixture：`fixtures/audit/citations.jsonl` —— 标注集：真实引用、编造引用（占位作者/残缺 ID/Frankenstein 拼接）、已撤稿条目、有更正条目；标签为 ground truth。外部来源优先（公开撤稿清单、GPTZero 失败类型分类），自造样本须标注 provenance。
- oracle：存在性/撤稿类 verdict 与标签 100% 一致（确定性类别）；locator 一致性 `model_assisted` 类别报告一致率与阈值（conditional，实现时冻结阈值）。
- 命令：`python -m pytest tests/test_audit_module.py`；MCP stdio 冒烟：`python -m autoresearch.mcp --selftest`。
- 晋级证据：fixture 检出报告 + 离线场景全部 verdict=unknown（fail-closed 证明）。
- 中止：确定性类别出现 fail-open（网络不可达却判 pass/fail）→ 阻断发布。

## S3 Reader/Writer 槽位 LLM 化 + 真实外部能力

- 交付：reader/writer domain port 后的 LLM 实现（受信模块契约：typed ReadingCard、claim 绑定）；接入一个真实外部能力（候选：Asta MCP 作为 search 备选源）验证两级信任（外部输出 → candidate_only 降级 → Audit 晋级路径）。
- fixture：同一组论文的阅读卡三路产出（native 确定性 / LLM / 外部能力）。
- oracle：**契约级 parity**（schema 有效、claim 绑定率、gate 合规、审计通过率），不做内容等价（不同实现的输出内容不要求相同）；native 确定性实现保留为机制 oracle 与 fallback。
- 命令：`python -m pytest tests/test_reader_writer_ports.py tests/test_audit_module.py`（新增）。
- 中止：外部能力产出未走 candidate 通道（出现第二写入者）→ 阻断。

## S4 可信闭环试点 + 公开 benchmark

- 交付：端到端尖刀场景（研究问题→检索→阅读卡→related-work 草稿，全部陈述绑定证据或标 `[未验证]`，附审计报告）；`scripts/benchmark_trust.py`；公开对比报告。
- fixture：外部可标注任务集 + 幻觉注入集；benchmark harness 与 fixture 随发布公开。
- oracle：三组对比（裸 LLM / AutoResearch gate 关 / gate 开）的幻觉引用率、claim-原文一致率；报告须载明基线、样本、局限（作者即评测者偏差，explicit limitation）。
- 命令：`python scripts/benchmark_trust.py --report evidence/benchmark-report.json`。
- 晋级：一个真实论文试点通过 `.project-to-act` 验收 + benchmark 报告公开。

## 全局停止规则

- 任一片 parity / sole-writer / fail-open / recovery 失败：该片 promotion 停止，保留 legacy facade，修订合同后重审。
- S2 不得早于 S1 晋级开工（Audit 依赖 Evidence 接纳边界的正确性）；S3 不得早于 S2；S4 不得早于 S3。
- 预算外新名词/新权威（bus、scheduler、第二数据库、动态加载）出现 → 触发 complexity gate 复审。
