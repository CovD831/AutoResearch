# O12 ProviderLane 与 LLM 调用底座——实施计划

- Task ID: `O12-PROVIDER-LANE`（registry: S3-A2-PROVIDER-LANE）
- 状态：**段 1 speculative（设计与 fixture，waiting-for-gate 合规活动）**；段 2 待 O7 + B4 accepted 转 active
- 日期：2026-09-10（本计划依据：Owner QUEUE O12 · ADR-01 签字块 1（已签）· pi-ai 六机制源码规格（2026-09-10 调研）· openpilot 参考实现 · 现有 llm.py 盘点）
- 预估：1 天（段 1 今日下午 + 段 2 今晚 O7 后至 09-11 交付）；交付走 PR + **成员 A 人工复审**（审核不自批对 Owner 同样适用）

## 0. 任务包定义（原文边界）

`provider_lane.py`：lane 不可变身份 + pi-ai 语义（模型目录含 cost/contextWindow、usage→receipt 计价、reasoning 档位、跨 provider handoff、constrained-sampling 降级）+ openpilot lane 约束（预算档/凭据白名单/漂移 fail-closed）；`llm.py`（76 行）替换；A5 计价链与 B6 写作头切换的供给方；双 provider parity（真实/回放/mock）；计价与官方口径误差可解释；settings 漂移注入 fail-closed。

**不做**：B4 reader/writer port 实现（成员 B）、MCP adapter（S3-B 契约）、A5 benchmark 消费、工具执行 admission 整体移植（openpilot 852 行中约 700 行是工具注册表/文件范围校验，与 O12 范围不符——只采纳其准入 fail-closed 模式，供 L3 MCP 扩展位后续复用）。

## 1. 现状盘点（已核实）

- `src/autoresearch/llm.py`（76 行）：httpx 同步单发 `/chat/completions`；`complete(system,user,temperature,json_mode)` + `complete_json()`；**无流式、无计价、无 lane 身份、无重试**。
- 消费方仅三处：`application.py:143`（构造）、`orchestrator.py:65` 与 `writing_service.py:615`（都只调 `complete_json`）→ **保留 `LLMService` 门面签名即可零破坏替换**。
- receipt 现无成本字段；A5 SPECS 已预留 schema（端到端计价验收由本任务填充）。

## 2. 架构与分层

```
B4 writer port / B6 写作头（消费缝：LLMAdapter contract，目标 <80 行薄缝）
        ↓
LLMService 门面（签名不变：LLMService(settings) → complete/complete_json）
        ↓ 内部改走
provider_lane.py（O12 本体，五组件）
  ├─ LaneIdentity      frozen dataclass：lane_id/provider/endpoint/model/cost 四档/
  │                    context_window/max_tokens/reasoning 支持与档位映射/credential_env_names/
  │                    compat flags(thinkingFormat, supportsStrictMode)/budget_profile/max_rounds
  ├─ ModelCatalog      vendored 静态快照 models_catalog.json（离线可校验）+ 显式网络刷新脚本
  ├─ CostCalculator    usage→cost（四档单价 + tiers 阶梯；reasoning ⊂ output 不重复计价）
  ├─ CredentialResolver 白名单模式：只读 lane.credential_env_names（openpilot 同款），缺失→LaneNotConfiguredError
  ├─ DriftValidator    settings vs lane 逐字段比对，漂移→LaneDriftError + 审计事件 provider.lane_drift
  └─ LaneTransport     httpx 同步（与现网一致）+ handoff 消息转换 + retry（指数退避/可重试分类）
        ↓
invocation receipt（A2 幂等/审计基线，已有）← cost 字段由 O12 填充
```

**关键决策**（写代码前冻结）：
1. **同步 transport**：现有调用方全部同步，pi-ai 的 async iterator 语义移植为同步生成器；流式后置为 backlog。
2. **目录 vendored 快照**：`models_catalog.json` 进 repo（models.dev 口径，$ / 1M tokens 四档+tiers）；刷新脚本 `scripts/refresh_model_catalog.py` 显式网络运行，离线禁网不受影响。
3. **薄缝策略**：B4 契约未知 → provider_lane 暴露自有接口 `lane.complete(request) → LaneResult`；B4 契约落地后缝由 `LLMService`/adapter 层适配，lane 本体不动。
4. **llm.py 兼容**：`LLMService(settings)` 构造签名保留；内部从 settings 解析 lane 并跑漂移校验；`complete_json` 改走 constrained sampling（strict=require，见 §4.5）。

## 3. 预置 lane 目录（ADR-01 §1.1 用户 key 插槽）

| lane_id | endpoint | 模型示例 | 凭据 env（白名单序） |
|---|---|---|---|
| deepseek:chat:v1 | https://api.deepseek.com | deepseek-chat / deepseek-reasoner | AUTORESEARCH_DEEPSEEK_API_KEY, DEEPSEEK_API_KEY |
| openai:chat:v1 | https://api.openai.com/v1 | gpt-4o-mini 等（按快照） | AUTORESEARCH_OPENAI_API_KEY, OPENAI_API_KEY |
| anthropic:messages:v1 | https://api.anthropic.com | claude 系（按快照） | AUTORESEARCH_ANTHROPIC_API_KEY, ANTHROPIC_API_KEY |
| kimi:chat:v1 | https://api.moonshot.cn/v1 | kimi 系 | AUTORESEARCH_KIMI_API_KEY |
| qwen:chat:v1 | DashScope 兼容端点 | qwen 系 | AUTORESEARCH_QWEN_API_KEY |
| vllm:local:v1 | http://localhost:8000/v1 | 用户自部署 | （无外部凭据，本地端点豁免白名单） |

首版 API 族只覆盖 **openai-completions 兼容族**（deepseek/openai/kimi/qwen/vllm 五条全适用）；anthropic messages 族标注「transport 二期」（目录仍登记，计价可算）。

## 4. pi-ai 语义移植映射（六机制 → 实现与测试锁定）

| # | 机制 | pi-ai 行为（源码规格） | Python 实现要点 | 测试锁定 |
|---|---|---|---|---|
| 4.1 | 模型目录 | `Model<TApi>`：id/name/api/provider/baseUrl/reasoning/thinkingLevelMap/input/cost(四档 $/1M + tiers 按 inputTokensAbove 阶梯)/contextWindow/maxTokens/compat；来源 models.dev api.json，静态 `models.generated.ts`（500+ 模型） | `models_catalog.json`（vendor 快照，来源 models.dev——**MIT 许可已确认**（anomalyco/models.dev，SST 维护），文件头标注来源/拉取日期/许可）→ `ModelCatalog.get(model_id)` → 构造 LaneIdentity；tier 选择=遍历取被超过的最高 `inputTokensAbove` | 目录 JSON schema 校验；六条预置 lane 可从快照实例化；离线可跑 |
| 4.2 | usage→计价 | usage={input,output,cacheRead,cacheWrite,reasoning(⊂output),totalTokens}；cost=各档 rate/1e6×tokens，total=四项和；abort 携带 partial usage 与已算 cost；Anthropic 1h cacheWrite 按 2×input | `CostCalculator.calculate(usage, cost_tiers) → UsageCost`；receipt 填充 `cost.{input,output,cache_read,cache_write,total}` + `tokens.{...}` | 用 pi-ai tokens.test 已知样例对照数字一致；aborted partial 样例；tier 越档样例 |
| 4.3 | 跨 provider handoff | 统一 Message（User/Assistant/ToolResult × Text/Image/Thinking/ToolCall）；tool call id 归一化（`[^a-zA-Z0-9_-]`→`_`，截 64）；非视觉模型图片降级占位文本；孤儿 tool call 补合成 toolResult；**跨模型 Thinking→Text（有损）、redacted thinking 丢弃** | `handoff.py`：`normalize_tool_call_id` / `degrade_images` / `synthesize_orphan_results` / `convert_thinking` 四规则，同模型 replay 保留 thinkingSignature | 归一化样例表驱动；图片降级；孤儿补全；跨模型 thinking 有损断言 |
| 4.4 | reasoning 档位 | 枚举 minimal/low/medium/high/xhigh/max + off；`clampThinkingLevel` 经 thinkingLevelMap 钳制；openai-completions 按 compat.thinkingFormat 分发（openai→reasoning_effort、deepseek→thinking{type}、qwen→enable_thinking 等）；**anthropic 两代规格（2026-09-10 官方文档查明）：≤4.5 手动模式 `thinking:{type:"enabled",budget_tokens}`（min 1024、常规须 <max_tokens、thinking tokens 按 output 计价 [usage.output_tokens_details.thinking_tokens]）；4.6+ adaptive 模式 `output_config:{effort:"high"…}` 档位原生** | 档位枚举 + per-lane `thinking_level_map`；首版只实现 `openai` 与 `deepseek` 两种 format，其余 format 抛 NotImplemented（fail fast）；anthropic 映射表按两代规格预写（manual：档位→budget_tokens 且钳 ≥1024 与 <max_tokens；adaptive：档位 1:1、xhigh/max 钳到 high） | 档位钳制表驱动；deepseek payload 断言；不支持档位显式报错；anthropic 映射表单测 |
| 4.5 | constrained sampling | `{type:"json_schema", strict:"prefer"\|"require"}`；supportsStrictMode 时 makeStrictJsonSchema（补 additionalProperties:false、全 required、nullable→anyOf）；**require+不支持→显式抛错（fail fast）；prefer 永不抛，最多降普通 function**；grammar 优先 lark 后 regex，不支持则降级 | `complete_json` 走 strict=require；`make_strict_json_schema` 移植（三规则）；grammar 首版不实现（backlog）；降级矩阵表 | 三条 makeStrict 规则单测；require+不支持→LaneStrictError；prefer 降级不断言错误 |
| 4.6 | auth 与流/重试 | 凭据优先级：显式 > stored > env（无静默回退）；坏配置 `ModelsError("auth")`；流事件 start/text*/thinking*/toolcall*/done/error；retry：指数退避 base×2^(n-1) cap 60s，可重试（overloaded/429/5xx/network）vs fail fast（quota/billing/usage limit），abort 不重试 | `CredentialResolver`（白名单 env 序）；缺 key→`LaneNotConfiguredError`；`retry.py` 同分类常量表；流式后置 → transport 单发 + retry | 白名单序断言；缺 key 报错；重试分类表驱动（mock 429/500/401）；退避序列断言 |

## 5. openpilot 约束采纳清单

| openpilot 来源 | 采纳 | 改造点 |
|---|---|---|
| `provider_lane.py` frozen `ProviderLane` + `__post_init__` 非空/正数校验（L13-36） | 直接移植（命名/字段按 §2 LaneIdentity 扩展） | 增加 cost/context_window/compat 字段；lane_id 含版本段 `provider:model:reasoning:v1` |
| `credential_from_env` 白名单只读（L65-76） | 直接移植 | 加「本地端点豁免」分支（vllm:local） |
| `validate_lane_settings` 漂移 fail-closed（L104-119） | 移植 + 升级：ValueError → `LaneDriftError` + `provider.lane_drift` 审计事件 | 比对字段集按 §2 新字段扩展 |
| `validate_lane_tokenizer` 身份一致（L122-129） | 暂不移植（我们不算本地 token，usage 由 provider 返回） | backlog：本地 token 估算器 |
| `provider_tool_admission.py` 准入管线（registry→input-contract→permission→runtime-budget） | **只采纳模式**：fail-closed 错误对象（含 error_message/suggested_recovery）+ 预算计数器形态 | 工具执行/文件范围校验不移植；预算档改为 **cost/token 上限**（lane.budget_profile：max_cost_per_call、max_calls_per_run、max_tokens_per_run，超限 fail-closed）——对齐 A5 评估纪律「固定调用预算入 receipt」 |

## 6. 实施步骤与验收

### 段 1｜今天下午（speculative，分支 `owner/provider-lane`，不合 main）
| 步骤 | 产出 | 验收命令 |
|---|---|---|
| S1.1 目录快照 | `src/autoresearch/data/models_catalog.json`（models.dev 拉取一次，显式网络）+ 生成脚本 | `python -m autoresearch.provider_lane.selftest --catalog`（schema 校验 + 六 lane 实例化） |
| S1.2 模块骨架 | `provider_lane.py`（LaneIdentity/ModelCatalog/CredentialResolver/DriftValidator 纯结构）+ 异常类 | `pytest tests/test_provider_lane.py -q`（结构/校验用例） |
| S1.3 计价器 | `CostCalculator` + tiers | 对照 pi-ai 已知样例：`pytest -k cost` 全过 |
| S1.4 漂移注入 | DriftValidator + 审计事件 | `pytest -k drift`：7 项 settings 篡改全被拒 |
| S1.5 parity fixture 骨架 | 回放/mock fixture 目录 + 三路 parity 测试骨架 | `pytest -k parity -m "not real_api"` 过（真实路标记 skip） |

### 段 2｜今晚 O7 通过后（B4 accepted 当天，speculative→active）
| 步骤 | 产出 | 验收 |
|---|---|---|
| S2.0 账本 | `.ai-team/tasks/O12-PROVIDER-LANE.md`（repo-task-sync 六段格式） | `check.mjs --task …` valid |
| S2.1 B4 对缝 | LLMAdapter 薄缝（<80 行）+ 契约比对记录 | 缝接口与 B4 契约 diff=0 |
| S2.2 transport | httpx 同步 + retry 分类 | mock 重试矩阵过（429/500 重试、401/403 fail fast） |
| S2.3 handoff + 档位 | §4.3/4.4 移植 | 表驱动用例全过 |
| S2.4 constrained sampling | §4.5 移植（json_schema 优先） | 降级矩阵用例全过 |
| S2.5 receipt 计价 | receipt schema 增 cost/tokens 字段 + 填充 | `pytest -k receipt`；A5 消费字段就绪 |
| S2.6 llm.py 替换 | LLMService 内部改走 lane，签名不变 | 全量 pytest 回归（orchestrator/writing_service 零改动） |

### 段 3｜09-11 交付
| 步骤 | 产出 | 验收 |
|---|---|---|
| S3.1 双 provider parity | 真实调用 deepseek + openai（或 deepseek 双模型）：同 prompt 结果/usage 采集，cost 对照官方价目表 | 误差可解释记录（写入账本 Verification）；mock/回放两路 exit 0 |
| S3.2 交付物 | PR（代码+账本+文档）+ PROGRESS/HANDOFF | CI Task contract 绿 |
| S3.3 复审 | 成员 A 人工复审（runtime 域复审人） | 复审记录入 PR |
| S3.4 registry 回写 | S3-A2-PROVIDER-LANE → integrated | registry/任务板同步 |

## 7. 测试矩阵（全量清点）

结构校验 / 目录 schema / 六 lane 实例化 / 计价（含 tiers、aborted、1h-cacheWrite 规则）/ 白名单序 / 缺 key 报错 / 漂移注入（7 字段）/ 预算超限 fail-closed / retry 分类与退避 / handoff 四规则 / 档位钳制与映射 / strict schema 三规则 / prefer-require 降级矩阵 / receipt cost 填充 / llm.py 消费方回归 / parity（mock+回放+真实）。

## 8. 风险与开放问题（诚实清单）

| 风险/开放点 | 状态 | 处置 |
|---|---|---|
| B4 LLM adapter contract 未冻结 | 今晚 B4 交付后消解 | 薄缝策略（§2 决策 3）；缝改动不影响 lane 本体 |
| models.dev 数据许可 | **已定案（2026-09-10）**：MIT（anomalyco/models.dev，SST 维护，数据 TOML 同仓库同许可） | 快照文件头标注来源/拉取日期/MIT 许可即合规 |
| Anthropic thinking 规格 | **已查明（2026-09-10 官方文档）**：≤4.5 手动模式 `budget_tokens`（min 1024、常规 <max_tokens、按 output 计价）；4.6+ adaptive `output_config.effort` 档位原生；manual 模式 final assistant turn 须以 thinking block 开头、改预算会断 prompt cache | anthropic 档位映射按两代规格预写（§4.4）；messages transport 仍二期 |
| grammar（lark/regex）变体未实现 | 范围裁剪 | backlog；json_schema 覆盖 B 线结构化输出需求 |
| 流式（async iterator）未实现 | 范围裁剪 | backlog；首版单发同步与现网一致 |
| 双 provider parity 第二家 | **已定案（2026-09-10）**：openai（老板拍板，后续可调） | 目录齐、compat 基准；如无 key 换 kimi/qwen 免费档 |
| 真实调用产生 API 成本 | 已获批口径 | 内部自有 key、入 receipt（ADR-01 §1.1 第 2 条），成本记录在账本 Verification |

## 9. 时间线

| 时点 | 事件 |
|---|---|
| 09-10 14:40–18:00 | 段 1（S1.1–S1.5），分支 `owner/provider-lane` speculative |
| 09-10 晚 | A4/B4 深审 + O7 gate；通过后 S2.0–S2.2 |
| 09-10 深夜–09-11 上午 | S2.3–S2.6（handoff/档位/降级/receipt/替换） |
| 09-11 白天 | S3.1 真实 parity + S3.2 PR |
| 09-11 晚 | O12 交付（提前一天），成员 A 复审；B6 写作头切换供给方就绪 |

> 纪律：段 1 产物不合 main、不宣称完成（roadmap speculative 规则）；O7 未过不得转 active；提交遵循 09-10 提交纪律（Owner 确认后推送）。
