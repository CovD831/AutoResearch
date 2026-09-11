# ADR-01：外部模块选型定稿（全管线可插拔点）

- 编号：ADR-01
- 状态：Accepted（2026-09-10；Owner 指令「对每一个外部模块的选型做好充分调研，明确哪个在目前来说能力比较好，并且适合接入」后定稿）
- 日期：2026-09-10
- 依据：workspace《autoresearch-生态调研-2026-09》第九节初稿 + 2026-09-10 逐槽位复调研（3 个并行调研代理覆盖 12 个有争议槽位；matplotlib/pandoc 为事实标准未复研。全部证据 URL 见各条）
- 消费方：**O12**（ProviderLane，09-10 晚开工）、**A5**（benchmark + 检索 adapter）、**B5**（数据源与 PDF 解析，09-11 领取）、**B7**（稿件组装）、**O9/O10**（MVP-CLOSED 后）
- 生效规则：本 ADR 生效后，各环节首选即任务包默认实现；更换首选须开新 ADR 或留 owner 裁决记录，成员任务包内不得私改选型。

## 1. 决策原则（三层接入）

> 治理层是产品本体，外部工具全是可换件。

- **L1 内置默认**：免费 API 直连 + 本地开源库，零依赖开箱即用（零成本路线）。
- **L2 可换实现**：同一 port 多实现（双轨写作头/多检索源），Gate 语义不随实现变，防供应商锁定。
- **L3 MCP 扩展位**：用户自带数据源/工具，走 A3 stdio 边界 + S3-B MCP adapter contract + A4 trust tier 准入。

核心环节一律 L1 直连（MCP 反而多一层进程边界），MCP 留给「用户自己的内部数据」。MCP 规范（2026-07-28 修订）明示 **stdio 非沙箱**、子进程继承父环境凭证——本项目的凭据白名单 + settings 漂移 fail-closed 因此是接入的必要条件，不是增强项。

### 1.1 API 与密钥政策（2026-09-10 Owner 澄清，三层口径）

1. **内置默认栈：0 付费**。免费档 API（含注册免费 key：Semantic Scholar、Crossref polite pool 等）+ 本地开源库；不含任何付费依赖。对外开放后，内置栈同样维持 0 付费。
2. **内部跑通（第一阶段）**：模块需要 API 的一律申请免费档，不回避注册 key；LLM 调用是唯一付费项，用自有 key 经 ProviderLane（DeepSeek/OpenAI/Anthropic/Kimi/Qwen/vLLM 兼容端点均入模型目录），成本入 receipt 可审计。
3. **用户 key 插槽（开放后）**：ProviderLane 预置可选供应商目录，用户在对应供应商槽位填自有 key 即用——lane 不可变身份 + 凭据白名单 + 漂移 fail-closed 即为此设计（O12 交付范围）。
4. 免费档限额变化（如 S2 政策）只允许走降级路径（备选轨顶上），不得静默改变 Gate 语义（见第 5 节待监控）。

### 1.2 范围注记：skill 的三层定位（本 ADR 覆盖哪层）

- **skill 作为协议**：A4 Capability Adapters（S3-A）的 native/skill/MCP/plugin 四协议统一调用边界——属架构实现，不在本 ADR 选型范围。
- **skill 作为经验注入形态**：槽位 13 已定（agentskills.io SKILL.md 标准），注入接线在 A6/O9 接线点②。
- **skill 作为内容库**（论文写作技能包：related work 写法、审稿风格、期刊规范等）：**不在本 ADR 范围**——它是内容生产问题而非供应商选型问题。首批素材按计划由 B6 真实试点 + A6 失败沉淀自然产生（数据飞轮），MVP-CLOSED 后 O9 接线点②把 promoted 经验编译为 skill 文件；届时若需系统性技能库规划，另立 ADR-02。

## 2. 十四环节选型表（2026-09-10 定稿）

| # | 环节 | 决策 | 形态 | 关键理由（2026-09 调研） | 消费方 |
|---|---|---|---|---|---|
| 1 | LLM 调用底座 | **自研 provider_lane.py**（移植 pi-ai 语义 + openpilot lane 约束） | L2 库移植 | pi-ai v0.81.1（MIT）模型目录含 DeepSeek/Qwen/Kimi/GLM 计价、vLLM 经 OpenAI 兼容 baseUrl 覆盖；LiteLLM 2026 年三项硬伤：许可边界争议（issue #34241）、2026-03 PyPI 投毒事件、预算计数器并发静默失效（#12977），且无 lane 不可变身份/凭据白名单原生对应 | O12 |
| 2 | 论文检索 | **Semantic Scholar API（免费 key）主选 + arXiv 补充**；OpenAlex 降为可选 | L1 API | S2 免费 key 5000 req/5min、236M+ 论文、citation context 独家字段；**OpenAlex 2026-02（Alice）起强制 key + 用量计费**，原「10 万/天 polite pool」作废 | A5 |
| 3 | PDF→Markdown | **docling（MIT）默认**；pymupdf4llm 轻量兜底 | L1 本地库 | docling 综合质量 0.86–0.88 vs pymupdf4llm 0.57–0.73（OpenDataLoader 2026-06 基准，200 真实 PDF）；MIT 规避 AGPL；首次运行需下载模型权重（离线预置机制与 A7 bge-small 共用） | B5 |
| 4 | 阅读→ReadingCard | 吸收 OpenScholar 管线策略（稠密检索→重排→迭代自检→引用接地） | L2 策略吸收 | Nature 2026（DOI 10.1038/s41586-025-10072-4）；OpenScholar-8B 正确性超 GPT-4o 6.1%、超 PaperQA2 5.5%，引用准确度达人类专家；Apache-2.0 | B4/B6 |
| 5 | 大纲/计划 | 吸收 STORM 思想（多视角提问→大纲），不引系统 | prompt 策略 | NAACL 2024 / Co-STORM EMNLP 2024；LOGIC（EMNLP 2025）与 Logic-RL（ACL 2026）效果更强但依赖模型训练，吸收成本高于纯 prompt 策略 | B6 |
| 6 | 章节写作头 | 第一轨：frontier LLM + 我方结构化证据包；**第二轨：OpenScholar 写作头（可补 PaperQA2 RCS 组件）** | L2 | OpenScholar 为当前最强开源学术合成系统；PaperQA2（Apache-2.0）RCS 为差异化写作组件（RAG-QA Arena 科学榜 SOTA）；两者只取组件形态，不部署模型 | B4/B6 |
| 7 | 引用/撤稿核验 | **Crossref REST + Retraction Watch** | L1 API | RW 2025-01-29 已并入 Crossref REST API；**单篇判定「本文是否被撤稿」读 works JSON `updated-by[]`（本文被谁更新），`update-to[]` 是本文更新了谁（撤稿声明用），`filter=update-type:retraction` 用于列表发现**——方向 2026-09-11 经真实 API 复核，见下方勘误；polite pool 单条 10 req/s、列表 3 req/s | B5（经 B3 verdict 流） |
| 8 | 评审 | RuleValidation + Gate；LLM-as-judge 仅 candidate 参考 | 内置 | INV-26 红线：自评不得覆盖 Gate | 已有 |
| 9 | 图表生成 | matplotlib（图数据出 evidence store，不得手填） | L1 本地库 | 事实标准 | B7 |
| 10 | 稿件组装导出 | pandoc（md→docx/pdf/LaTeX） | L1 本地工具 | 事实标准 | B7 |
| 11 | 评测 | **B5 自建 gold set 为主**；ScholarQABench 数据辅助（ODC-BY） | 公开数据 + 自建 | ScholarQABench 真实存在（Nature 2026，2,967 专家问句 + 208 长答，MIT 代码/ODC-BY 数据），但官方跑分依赖 LLM 裁判（prometheus/OpenAI API），零 API 约束下不可完整跑 | A5/B5 |
| 12 | 知识库向量检索 | **sqlite-vec + bge-small（MIT）+ RRF 双路融合** | L1 本地库 | bge-small-en-v1.5 MTEB 62.17 居 small 梯队首位（gte-small 61.36 / e5-small-v2 59.93）；RRF（k=60）为词法+向量混合检索通行融合算法；sqlite-vec 0.1.10-alpha.4 仍 pre-v1，锁版本使用 | A7 |
| 13 | 经验注入 | promoted 经验 → **Markdown skill 文件（agentskills.io SKILL.md 标准）** | skill 形态 | Agent Skills 已成事实标准：2026-03 约 32 个工具支持同一 SKILL.md（Claude Code/Cursor/Codex/Gemini CLI/Copilot 等），核心格式稳定（Skills 2.0 仅加评估层）；出处范式 = karpathy program.md + pi-mono skills 同标准 | O9/A6 |
| 14 | 用户自带数据源/内部工具 | MCP stdio 扩展位 | L3 MCP | 规范 2026-07-28 修订仍推荐 stdio 为本地 transport（"Clients SHOULD support stdio whenever possible"）；stdio 非沙箱 → 白名单 + 显式授权 + fail-closed 必须 | A4/S3-B 契约 |

选题 / charter 环节不选型：判断层归 owner（Gate），是设计论点不是缺口。

> **勘误 1（2026-09-11，Owner，PR #16 深度审查落定）**：槽位 7 原表述以 works JSON `update-to[]` 作为撤稿判定字段，**方向有误**。真实 Crossref API 复核（同日）：
> - 被撤稿论文（`10.1016/S0140-6736(97)11096-0`）→ `update-to = null`，`updated-by = [{type: correction}, {type: retraction}]`；
> - 撤稿声明（`10.1016/S0140-6736(10)60175-4`）→ `update-to = [{type: retraction, DOI: "…(97)11096-0"}]`，`updated-by = null`。
>
> 故：**判定「本文被撤稿」读 `updated-by[]`**；`update-to[]` 表示本文是更新者（即声明本身，应判为正常存在的记录）；`filter=update-type:retraction` 是列表发现用法。**选型本身（Crossref + Retraction Watch）不变**，仅修正字段语义。B5 实现、fixture、测试与账本证据已同步更正。

## 3. 与第九节初稿的差异（逐项复调研结论）

复调研覆盖 12 个有争议槽位，结果：**9 项维持、3 项调整、1 项更名**。

1. **槽位 3（PDF 解析）调整：pymupdf4llm → docling（MIT）默认。**
   OpenDataLoader 2026-06 基准（200 真实 PDF）：docling 综合 0.86–0.88（版面/阅读顺序/表格 TableFormer/公式/OCR 全覆盖）vs pymupdf4llm 0.57–0.73（无 OCR、无公式、阅读顺序弱）。docling 为 MIT 且质量更高——**AGPL 规避与质量提升同时成立**。pymupdf4llm 降为极轻兜底（纯 CPU 零权重，docling 权重不可用的离线场景）。证据：pypi.org/project/docling、github.com/docling-project/docling、docs.bswen.com/blog/2026-06-04-benchmark-comparison。
2. **槽位 2（检索）调整：OpenAlex 降级可选。** OpenAlex 2026-02 发布 Alice 起强制 API key + 用量计费（search $0.001/次，免费额度 $1/天），原零成本前提失效；S2 免费 key 5000 req/5min 额度最宽裕且 citation context 独家。证据：blog.openalex.org（usage-based pricing）。
3. **槽位 11（评测）调整：B5 自建 gold set 为主，ScholarQABench 辅助。** 基准真实（Nature 2026）但完整跑分需 LLM 裁判，违反零 API 约束；其 citation recall / citation precision / hallucination ratio 三指标采纳为内部指标口径。证据：github.com/AkariAsai/ScholarQABench。
4. **更名：初稿「CITE-AI 指标」查无权威出处，弃用该名**，改用 ScholarQABench 指标名（见槽位 11）。

## 4. 一致性校验（三条，沿用初稿并更新）

1. **每个 L2 换件都有 Gate 兜底**：换写作头/检索源不改变 fail-closed 语义——「下限由治理保证，上限由外部模块放大」的机制化。
2. **计价全链贯通**：#1 的 usage.cost.total → receipt → A5 汇总；#2/#7 的 API 调用走 invocation receipt；#3/#9/#10/#12 为本地运行，无 API 计价项（#3 模型权重一次性下载成本入 A5 资源预算）。
3. **全部零许可风险**：首选栈全部 MIT/Apache/免费 API；唯一 AGPL 项（pymupdf4llm）降为兜底并条款化（见签字块 2）。

## 5. 待监控与未能确认（诚实清单）

| 项 | 状态 | 处置 |
|---|---|---|
| Semantic Scholar 免费档长期政策（2025-01 归档 s2-folks 支持仓库） | 未能确认是否有降配计划 | A5 实现加限流监控与降级路径（OpenAlex 可选轨顶上） |
| sqlite-vec pre-v1（0.1.10-alpha.4） | 已知 breaking change 风险 | A7 锁定版本 + 接口隔离 |
| MinerU 许可（网传 3.1 改 Apache 类自定义） | 未能确认，按 AGPL 对待 | 不作默认；如需 CJK 强化再评估 |
| PubPeer 公开 API | 未能确认（FAQ 称"soon"） | 不纳入核验链 |
| bge-m3 / jina-embeddings-v3（多语）、sqliteai/sqlite-vector（license 未确认） | 后续评估 | 语料确认多语需求后重估 |
| OpenAlex 计费政策波动 | 政策多变 | 仅可选轨，不入关键路径 |

## 6. 签字块

### 签字 1｜pi-ai 语义移植决策（O12 依据，已确认）

- 决策：**Python 自研 `provider_lane.py`，移植 pi-ai 语义（模型目录含 cost/contextWindow、usage→receipt 计价、reasoning 档位、跨 provider handoff、constrained-sampling 降级），合体 openpilot lane 约束（预算档/凭据白名单/漂移 fail-closed）；替换 `llm.py`（76 行裸调用）。不引 TypeScript 包本体，不引 LiteLLM。**
- 依据：槽位 1 调研（LiteLLM 供应链攻击史 + 预算静默失效 + 许可边界不清；pi-ai MIT、目录覆盖我方 provider 集）。
- Owner 确认：2026-09-10（当日 03:48 三项定夺指令②，本 ADR 复调研后维持）。

### 签字 2｜PDF 解析许可决策（B5 前置，待 Owner 终审）

- 决策：**默认 docling（MIT）**；模型权重离线预置（与 A7 bge-small 共用 vendor 预下载机制，首跑前就位）。
- 兜底条款：pymupdf4llm（AGPL-3.0）仅限「docling 权重不可用」的离线场景作轻量兜底；使用范围=本地工具链、不随产品分发、不链接进任何分发产物——在此范围内不触发 AGPL 传染义务；若未来分发内容含 pymupdf，切换 pdfminer.six（MIT）并接受质量下降，或另购商业许可。
- B5 执行要求：corpus 许可审查时一并复核本条款仍成立；AGPL 兜底一旦启用，须在 receipt/PROGRESS 记录启用原因。
- Owner 终审：**已确认——2026-09-10 指令「按照目前的这个调研来决定」**（docling 默认 + pymupdf 兜底 AGPL 条款一并生效，ADR-01 全文生效）。
