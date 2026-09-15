# R-006 外部实践调研汇总

**日期**：2026-09-14
**目的**：为 L1/L2 的具体设计决策提供外部依据
**方法**：三路并行网络调研（经验沉淀与自进化 / 知识库 revision 与可追溯 / 经验回流机制）

> **标注约定**：【实证】= 有论文或真实系统支撑；【工程】= 厂商博客或工程经验，非独立实证；【主张】= 设计意见。
> **冲突项单独标出** —— 凡与本项目原设计不一致者，逐条记录。

---

## 一、最重要：经验沉淀**本身是危险的**

这一条改变了 R-006 的定性 —— 原设计（§15）把经验沉淀当作正向机制，但实证显示**不加约束会退化**。

| 证据 | 数字 | 来源 |
|---|---|---|
| 【实证】LLM 把经验抽象成规则时**系统性剥离适用条件** | WebShop 抽象记忆 **0.64 → 0.20**（128 条后**劣于无记忆基线**）；ARC-AGI GPT-5.4 **100% → 52.6%** | `arXiv 2605.12978` *Useful Memories Become Faulty When Continuously Updated by LLMs* |
| 【实证】盲目信过期记忆 | 失败率 **74.4%** vs 无记忆 **28%** —— **记错比不记坏 2.7 倍** | *When Memory Lies* (SpatialSTALE) |
| 【实证】过度注入反伤 | 连续 consolidated memory 呈**倒 U**；记忆折叠后对原已解题失败率 **54%** | Gravity7 综述 |
| 【实证】上下文中毒 | 陈旧缓存被当事实并**写回记忆永久污染** | Redis / Snyk 实测 |
| 【实证】Agent 老化 | 4 种老化（压缩/干扰/修订/维护），**数日即退化** | AgingBench (UT Austin) |

**对设计的直接影响**：

1. **原设计的「适用/不适用边界」要求有实证必要性** —— 不是洁癖，而是对抗"抽象剥离适用条件"这一系统性失效。
2. **必须有时效衰减 + 冲突消解 + 回滚** —— 这三条原设计**没有明说**，但实证要求必须有。
3. **"经验沉淀"的定性从"实现设计"改为"实现 + 加固"**。

**这同时是差异化机会**（调研者原话）：
> 「显式『适用条件可检索 + 反例抑制』是文献未成熟处，建议在 X1 去敏归因阶段就把 when-applicable / when-not 结构化落库 —— 这是你们可做的领先设计。」

---

## 二、经验成熟度阶梯的外部对应物

| 系统 | 机制 | 与 X0–X4 的关系 |
|---|---|---|
| **Reflexion** `arXiv 2303.11366`【实证】 | 失败信号存为情节记忆，下轮 prepend 反思文本 | 仅"候选→反思"两级，无固化/审核 |
| **ExpeL** `arXiv 2308.10144`【实证】 | 区分 episodic（成功轨迹）与 semantic（抽象 insight）；insight 经 ADD/EDIT/UPVOTE/DOWNVOTE 投票演化 | **最接近 X0→X3**，但无人工批准、无 canary、无回滚 |
| **Generative Agents** `arXiv 2304.03442`【实证】 | memory stream 按 `recency × relevance × importance` 检索 | 检索打分可借鉴 |
| **Voyager** `arXiv 2305.16291`【实证】 | 技能库=可执行代码，**环境验证通过才入库**，自动课程递进 | **最接近"沙箱复现 + 跨任务验证"** |
| continual learning【共识】 | 不应每次交互即时固化，**gated consolidation** 更稳 | 支持分段晋级 |

**结论**：我们的 X0–X4 比文献**更完整**（多了审核 / 灰度 / 回滚），等价于 ExpeL + Voyager 的叠加。**原设计在这一块是领先的，值得按原样实现。**

---

## 三、适用/不适用边界的落地

| 发现 | 来源 |
|---|---|
| 【实证】"每多检索一个反例（disabler），对规则的接受度**线性下降**" —— 反例是抑制错误泛化的有效信号 | De Neys et al., *Memory & Cognition* 2003, PMID 12872874 |
| Agent 侧雏形：ExpeL 同存成功/失败轨迹；Reflexion 存失败反思 | 见上 |
| **【缺口】未找到"把显式适用条件作为可检索字段、检索时做条件匹配"的成熟生产系统** | 调研者结论 |

**建议**：把 **applicability condition 作为独立索引字段**，否则会被抽象步骤丢弃。

---

## 四、RRF 与混合检索 —— **小语料上不应使用 RRF**

| 发现 | 来源 |
|---|---|
| RRF 源自 Cormack et al. SIGIR 2009，**k=60 是面向大语料的稳健默认**【实证/广用】 | — |
| **小语料（几十~几百条）k 应降到 10–20**，否则高排名被倒数压制【工程】 | theneuralbase / colehoffer.ai |
| **关键判据：RRF 只在两路检索信号「正交」时增值**；BM25 与向量排序高度相关则 RRF 不增值【工程】 | yobitel 综述 |
| 小语料两路**易高度相关** → RRF 收益有限 | 同上 |
| 替代方案：可校准时加权融合 `alpha·dense + (1-alpha)·sparse`；Qdrant DBSF 免手调 | 同上 |
| cross-encoder rerank 精度 +10–20% 但慢 | 同上 |

**⚠️ 与既有方案的冲突**：先前讨论把 L5 RRF 当作统一融合层。**实测数据支持调研结论** —— 用 5 条经验条目测试时，词法路经常全 0 或与向量路完全一致（信号非正交）。

**修正后的分层**：
- **论文证据大语料** → 走 L5 RRF（k=60）
- **经验/画像小语料** → **不走 RRF**，改用「向量 + 适用条件字段过滤」

---

## 五、回流层：必须**双通道**，否则破核心约束

| 发现 | 来源 |
|---|---|
| Grounded Generation 用「source-only instruction + 强制引用」，每条事实带 `[SRC-n]` | zeroentropy.dev |
| **【关键冲突】推理时 RAG 并不能从结构上阻止模型把上下文当事实；必须训练/对齐才能"因文档而推理"** | *Grounding is not a prompt*（blog.phagyul.ai） |
| MemGPT/Letta 分层记忆（core/recall/archival），agent 自管理 | 2025.4 white paper |
| Voyager skill library 按 embedding 检索 top-5 复用 | `arXiv 2305.16291` |

**调研者原话（重要）**：
> 「**⚠️ 与你的硬约束直接冲突**：回流层若把经验当普通上下文注入，模型极易把"经验性建议"当事实引用 —— 这正是你『经验不能替代论文/实验事实』约束的脆弱缝。**必须双通道分离**。」

**修正后的设计**：

| 通道 | 内容 | 进入位置 | 约束 |
|---|---|---|---|
| **事实通道** | 检索/实验结果，带引用 | system prompt 的 `evidence` 段 | 可被论文引用；有 grounding 约束 |
| **经验通道** | 历史经验，带 tier + 适用边界 | system prompt 的 `guidance` 段 | **显式标注 experiential**；**不进入事实声明** |

### 成熟度门控应为「乘数 + 地板」而非硬过滤

调研给出的做法（【主张】，但有多家工程实践）：
```
score = sim × tier_weight × recency
另设 MIN_TRUSTED_SCORE 地板
低成熟度经验：可因高相关浮现，但禁入事实通道
```

依据：dev.to 四档（SYSTEM/OPERATOR/CORROBORATED/UNVERIFIED）、tmls.nyc 的 `TRUST_WEIGHT` 乘数 + `MIN_TRUSTED_SCORE` 地板。

---

## 六、可追溯知识库：revision 有大规模实证

| 发现 | 来源 |
|---|---|
| **Wikidata** 是真实落地的 append-only 知识库：每个实体完整 revision history（author/timestamp/comment）；**restore/undo 生成新 revision 而非删除旧记录** | `arXiv 2210.15495`；Wikidata History Query Service |
| Event Sourcing + CQRS：事件即真相，当前态由回放派生 | Microsoft 模式库 |
| **⚠️ 粒度冲突**：Wikidata 的 revision 是**实体级全量快照**，而我们要 **claim 级证据绑定**。需把证据包挂到 **statement/edge 级**（Wikidata 支持 per-statement references，但 revision 模型非 claim 粒度） | 调研者结论 |
| 建议：事件流以"**知识单元**"为聚合根，而非整页 | 同上 |

**裁决（owner 2026-09-14）：采纳折中方案 (c)**
> 页级 revision + **statement 级证据绑定**
> 理由：原文 §12.2 说「Wiki 页使用不可覆盖 revision」（**版本粒度=页级**），同节又说「知识页可以引用论文页和证据」（**证据绑定需更细**）。(c) 同时满足两者，且不引入 statement 级全版本化的复杂度。

---

## 七、跨分区边禁令：**应收窄，不应取消**

| 发现 | 来源 |
|---|---|
| Named Graphs + 多租户隔离是真实做法，但业界**允许受控的跨图链接**（SPARQL `SERVICE` 联邦查询），而非一刀切禁止 | ai-definitions / tesseract.academy |
| **⚠️ 与设计冲突**：六库若禁止一切跨分区边，会切断核心价值 —— **论文必须 CITES 证据、经验必须 REFERENCE 论文** | 调研者结论 |

**核实原始意图**（`docs/KNOWLEDGE_AND_EVOLUTION.md:15`）：
> 「跨分区 GraphEdge 被拒绝，**防止一个经验页被伪装成论文证据**」

**两者不矛盾** —— 原文防的是**伪装**，缺的是**中间层设计**：

- **禁止**：无类型的任意跨分区边（防伪装）
- **允许**：**受管桥接边** —— 边类型本身声明语义（`REFERENCE` ≠ `EQUIVALENT`），由 schema 校验

**现状证据**：全仓只建过一种边 `summarized_by`（`reader_service.py:156`），因为原始设计要求的 16 类边中**必然跨分区**的那些（`DERIVED_FROM` / `APPLIES_TO` / `CITES`）全被禁令挡住。

---

## 八、类型系统：枚举核心 + 注册表扩展

| 发现 | 来源 |
|---|---|
| **OpenAlex** 用受控词表给 work 定 13 类，原则是"我们不定边界，只标准化标签" | OpenAlex work-types 文档 |
| **PROV-O**（W3C 标准）核心仅 Entity/Activity/Agent 少量类，靠 `specializationOf` 扩展 | `https://www.w3.org/TR/prov-o/` |
| **硬编码枚举进代码的代价 = 演进成本**。建议：稳定核心类型用枚举 + **SHACL shape 做校验层**，新增类型走**注册表 + 版本化**，不碰业务代码 | 调研者结论 |

---

## 九、证据失效：级联重审，不删除

| 发现 | 来源 |
|---|---|
| PROV-O 有 `wasInvalidatedBy`；Graphiti/Zep 用 **bitemporal 边** —— 失效时**置 `invalid_at` 而非删除** | Graphiti temporal model 文档 |
| 建议：证据撤销 → 依赖它的 claim 置 `CONTRADICTED/NEEDS_REVIEW`，**保留历史**，触发重审队列 | 调研者结论 |
| **SciFact**（1409 条，claim↔abstract 标 Supports/Refutes + 句子级 rationale）、**FEVER**（18.5 万条）证明 **claim-level + sentence-level 证据绑定是成熟范式**【实证】 | `arXiv 2004.14974`；NCBI PMC10919922 |

**可与 R-004 的 evidence invalidation 机制对接。**

---

## 十、冷启动：有公开教训

| 发现 | 来源 |
|---|---|
| 失败链：**空平台 → 内容不足 → 搜索无果 → 用户流失 → 更没人写**。根因是"贡献摩擦 + 无治理 + 与日常工作割裂" | timewell.jp / affine.pro / iiminfo.org【主张，含具名案例】 |

**可执行建议**：
1. 用 **15–20 篇高频"种子内容"** 冷启动，不做大而全迁移
2. **把写入嵌入 agent 流水线**（知识作为工作副产物捕获，而非额外步骤）
3. 治理（owner / 复审周期 / 采纳指标）**上线即建**
4. 用"证据改变论文结论"的强激励驱动贡献

> **对本项目的意义**：第 2 条正好是我们的优势 —— 经验由 `experience_sink` 从审计事件自动捕获，**不需要额外人工步骤**。这规避了调研记录的主要失败根因。

---

## 十一、自进化安全边界：与 X4 高度一致

| 发现 | 来源 |
|---|---|
| 【实证】自进化 agent 出现 **reward hacking / memory poisoning / objective drift**；要求不可变审计日志 + 版本化 + 回滚 + 核心目标修改触发人工审查 | `arXiv 2509.26354` *Your Agent May Misevolve* |
| 统一结论：①评估权独立于优化器；②仅"窄范围、影响有界、分钟级可回滚"的改动才自动晋升；③安全指标是**硬约束非优化目标**；④高危动作/权限/合规变更**必须人工批准**；⑤shadow + canary + 自动回滚 | progressiverobot / AgentC2【工程】 |

**结论**：我们的 X4（提案 → 审核 + 人工批准 → 灰度 canary → 回滚）**与全部安全文献一致**，无需大改。

**补充一条**（调研建议）：**评估集与阈值必须独立于自进化流程**，"通过验证"的定义要防 reward hacking（不能只看指标）。

---

## 十二、修正清单（对先前 L1 草案）

| # | 原草案 | 修正 | 依据 |
|---|---|---|---|
| 1 | §15 定性为"按设计实现" | 改为「**实现 + 加固**」：补时效衰减 / 冲突消解 / 反例抑制 | §一 |
| 2 | L5 RRF 作统一融合层 | **分层**：论文大语料走 RRF；经验/画像小语料走「向量 + 字段过滤」 | §四 |
| 3 | 回流层单一通道 | **双通道**（事实 / 经验物理分离） | §五 |
| 4 | 跨分区全禁 | **收窄为**"禁无类型跨边，允许受管桥接边" | §七 |
| 5 | 类型硬编码枚举 | **枚举核心 + 注册表扩展** | §八 |
| 6 | 证据失效未定义 | **级联重审，不删除**（bitemporal） | §九 |

---

## 十三、调研未能回答的问题（如实记录）

- 「经验注入必然有益」**证据不足** —— 反有倒 U 与中毒实证。**必须靠自己的离线对照验证因果收益。**
- 「适用条件作为可检索字段」**无成熟生产系统先例** —— 我们若做，属领先设计，**无外部经验可借鉴**。
- 成熟度分级门控（乘数 + 地板）**多为设计主张**，缺严格实证。
