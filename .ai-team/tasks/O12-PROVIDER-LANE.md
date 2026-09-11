# O12 ProviderLane

- ID: `O12-PROVIDER-LANE`
- Title: `ProviderLane 与 LLM 调用底座（pi-ai 语义移植 + openpilot lane 约束）`
- Status: `reviewing`
- Status note: 段 1 + 段 2 + S3.1 完成；经**对抗性自审 v2**（6 缺陷 + 钢人论证 5 条处置）+ **独立子代理盲审 v3**（4 缺陷，全修复）+ 价目口径政策，见 `SELF-REVIEW.md` / `PRICE-POLICY.md`。提 PR #15 交成员 A 复审（不自批），S3.4 registry 回写待合并后。v3 改动**停在本地未提交未推送**。 【2026-09-11 owner 代修】成员 A 复审提出 3 条技术意见（全部复现为真），owner 追加 C1–C4 修复并 rebase 至 `main@66aba64`（冲突仅记录文件，按并集解决）：全量 **304 passed / 2 skipped**、ruff 绿、`check.mjs` 与 `check_pr_contract` 双 valid；新增 16 个测试实例中 12 个在修复前失败。见 D-O12-11~14。
- Owner: `user/team`
- Next owner: `member A`

## Goal

用一条可离线校验的 provider lane 替换 `llm.py` 的裸 httpx 单发：lane 不可变身份 + pi-ai
六机制（模型目录含 cost/contextWindow、usage→receipt 计价、跨 provider handoff、
reasoning 档位、constrained-sampling 降级、auth/重试分类）+ openpilot lane 约束
（预算档 fail-closed、凭据白名单、settings 漂移 fail-closed）。`LLMService` 公共签名不变，
成为 A5 计价链与 B6 写作头切换的供给方。

## Acceptance scenarios

- [x] S1.1 目录快照：`data/models_catalog.json`（models.dev MIT 快照）+ `scripts/refresh_model_catalog.py`；`--catalog` 六条 preset lane 离线实例化成功。
- [x] S1.2 模块骨架：`LaneIdentity`（frozen）+ `ModelCatalog` + `CredentialResolver` 白名单 + 异常族（fail-closed 带 recovery 提示）。
- [x] S1.3 计价器：`CostCalculator` 四档 tiers，reasoning ⊂ output 不重复计价。
- [x] S1.4 漂移注入：`validate_lane_settings` + `provider.lane_drift` 事件工厂；参数化用例覆盖 **7 个字段**篡改全被拒。
- [x] S1.5 parity fixture 骨架：mock / replay / real-skip 三路。
- [x] S2.0 账本：本文件（repo-task-sync 格式，`check.mjs` valid）。
- [x] S2.1 B4 对缝：`lane_llm_adapter.py`（74 行薄缝，复用 B4 类型，契约 diff=0）+ `CONTRACT-PARITY.md`。
- [x] S2.2 transport：httpx 同步 + retry 分类；**预算档已接线**（自审 G1：dispatch 前查调用上限、事后累计 cost/tokens）。
- [x] S2.3 handoff + 档位：四规则 + anthropic 两代 thinking 映射。
- [x] S2.4 constrained sampling：`make_strict_json_schema` 三规则 + 降级矩阵。
- [x] S2.5 receipt 计价：共享 `TokenUsage`/`InvocationCost`（定义在共享 `contracts.py`）+ 两处 receipt 可选字段 + `receipt_usage_fields()`；**含价目来源与尝试次数**（自审 v2）。
- [x] S2.6 llm.py 替换：`LLMService` 内部改走 lane，签名不变、消费方零改动；计价按 model id 解析（自审 F1）。
- [x] S3.1 真实 parity：WorkBuddy 端点真实调用 2 模型采集 usage，计价链与手算一致；**官方价目对照实测为不一致**（见 Verification，偏差最高约 4.5×）。
- [x] S3.2 交付：PR #15（代码 + 账本 + `CONTRACT-PARITY.md` + `SELF-REVIEW.md`）。
- [x] S3.3 复审：成员 A 人工复审**已完成**（审核不自批，Owner 同为被审方）→ 提出 3 条技术意见，**全部经 owner 探针复现为真**：①默认预算未生效 ②重试未计入预算 ③异常未进统一错误体系。owner 另发现 1 条（`usage` 为 list 时 `AttributeError` 逃逸）与 2 条预算作用域问题。
- [x] S3.5 owner 代修（C1–C4，2026-09-11）：异常面收口 + 预置 lane 完整预算 + 预算作用域改 run + 预算按网络请求计；修完 rebase 至 `main@66aba64`。见 D-O12-11~14 与 Verification。
- [ ] S3.4 registry 回写：S3-A2-PROVIDER-LANE → integrated（合并后）。

## Invariants

- 不修改 B4 独占路径 `reader_writer_ports.py`；薄缝只读消费其契约，无镜像类型、无新增 port 方法。
- `LLMService(settings)` / `available` / `complete` / `complete_json` 签名与返回语义不变；消费方零改动。
- 不新增 Store、消息总线、scheduler、隐藏 Agent；不绕过 Evidence/Policy（`lane_drift_event` 只产事件，写入权留给调用方）。
- 目录为 vendored 静态快照，离线可校验；网络仅出现在显式刷新脚本、官方价目对照与真实 parity。
- fail-closed 方向不变：缺凭据 / 目录缺失 / 不支持档位 / strict 不满足 / 预算超限 → 显式报错，不静默降级。
- 计价是信息性的：`tokens`/`cost` 为 None 不阻塞 admissibility，也不改变 Gate 判定。
- 真实调用的凭据只从 `~/.workbuddy/models.json` 读取，永不写入仓库或 fixture。

## Decisions

- **D-O12-01（薄缝零镜像）**：`lane_llm_adapter.py` 直接 import B4 的 payload/port 类型，用 `is` identity 断言锁定，不做字段镜像。
- **D-O12-02（settings lane 显式凭据）**：`credential` 参数优先于 env 白名单；空白凭据视同未提供（F3）。未配置 catalog 条目的端点生成 unpriced lane（cost=0），不静默编造价目。
- **D-O12-03（complete_json 保 json_object，偏离 PLAN §4.5；Owner 已确认）**：无 schema ⇒ `require` 无语义；deepseek lane 不支持 strict。有 schema 的路径自动对支持 strict 的 lane 发 `json_schema strict=True`。**PLAN 原文已就地修订**。
- **D-O12-04（receipt 计价 schema 冻结）**：`tokens={input,output,cache_read,cache_write,reasoning}`；`cost={input,output,cache_read,cache_write,total,currency,model,lane_id,attempts,price_source}`。类型定义位于**共享 `contracts.py`**（治理：不由 A 线文件发明新类型），`invocation_contracts.py` re-export 保持兼容。
- **D-O12-05（真实 parity 端点与口径）**：WorkBuddy 自定义端点（OpenAI 兼容）；模型 id 命中 catalog 时套用其价目，未命中则 unpriced。
- **D-O12-06（计价来源与 endpoint 解耦；自审 F1）**：价目是**模型属性**。按 model id 从快照解析，`endpoint` 仅用于复用 preset lane 的身份元数据，比较时容忍尾斜杠、`/v1` 后缀与主机大小写。修复前 `.../v1` 或大小写差异会导致**计价静默归零**。
- **D-O12-07（预算守卫必须接线；自审 G1）**：dispatch 前查 `max_calls_per_run`，事后累计 cost/tokens 并对 per-call 成本与 per-run token 上限 fail-closed；文档同步改为实际行为。
- **D-O12-08（成本必须自证来源；自审 v2）**：每笔计价携带 `price_source`（价目表 + 快照日期）与 `attempts`（为拿到该结果发出的请求数）。原因：官方价目实测对照显示快照与 provider 公开价目**系统性不符**（见 Verification），`total × attempts` 是成本上界，`price_source` 是审计追溯锚点。`InvocationCost` 文档明示：**这是估算，不是 provider 账单**。
- **D-O12-09（计价口径与 override 政策；v3，Owner 拍板）**：①**tokens 为主口径、cost 为辅**——tokens 是事实（provider 返回），cost 是推断（本地折算）；纪律条款一律优先用 tokens 表达，cost 仅在对外报数时引用且必须带 `price_source`。②`price_overrides.json` 人工覆盖：**只覆盖实际在用的模型**，只替换已有条目的四档价目（不新增模型、未知目标忽略）。③内置模型 DeepSeek V4.1 Flash 按**官方 peak 档**钉住（\$0.30/\$1.20/\$0.006，来源 `api-docs.deepseek.com`，2026-09-11 核对）；取 peak 是刻意保守，估算宁可高估不漏报。④核对走**人工**（成本敏感实验前），不写官网爬虫。全文见 `PRICE-POLICY.md`。
- **D-O12-11（预置 lane 一律带完整预算；成员复审 C2）**：六个预置 lane 的 `max_calls_per_run` / `max_tokens_per_run` / `max_cost_per_call_usd` **全部为 `None`**，而 `LaneBudgetProfile` docstring 声称 caps 「are enforced」、transport docstring 声称「dispatch 前查 per-run 调用上限」——**文档声称 vs 实现**。现在由 `default_budget_profile()` 从 **lane 自身目录条目**推导：`max_calls_per_run=240`（与 A5 `ResourceBudget.max_calls` 同数，计价链两端认同一个数字）、`max_tokens_per_run=240×(context+max_output)`、`max_cost_per_call_usd=` 满窗调用按该 lane **最坏档**费率计价 ×1.5 余量。推导而非拍数：上限等于「这条 lane 合法情况下可能产生的最大值」，所以只可能拦失控、不会误伤；`context` 未知（0）时用兜底窗口。本地 vllm lane 同样带头预算——无凭据不等于无限。
- **D-O12-12（预算作用域是 run，不是 transport；成员复审 C3）**：计数器原挂在 `LaneTransport` 实例上，而 `lane_llm_adapter.py` 与 `llm.py` **各自**新建 transport → 同一 run 的预算被复制成 N 份，每份都能跑满上限（实测两实例各限 1，两次调用都成功）。现在抽出 `LaneRunLedger`，`LaneTransport(ledger=...)` 与 `LLMService(settings, ledger=...)` / `LaneLLMAdapter(lane, ledger=...)` 可共享同一份；缺省仍为每 transport 一份（单次调用与单测的正确作用域，并有测试记录该缺省）。**注**：`LLMService` 新增的是**可选**关键字参数，既有 `LLMService(settings)` 调用语义不变（属超集，非破坏）——若 owner 坚持签名逐字不变，可回退为仅在 adapter 侧注入。`calls_made` 保留为属性（= `requests_made`），既有消费方零改动。
- **D-O12-13（预算按网络请求计，不按成功数；成员复审 C4，Owner 口径 2026-09-11）**：`attempts` 逐请求自增，但预算只在 `complete()` 成功返回后 +1（429→200 时 `network_requests=2 / attempts=2 / calls_made=1`）。口径定为**按网络请求计**：预算的目的是**保护**（provider 配额与账单），不是支付记录；按成功计则一个持续 429 的 run 可无限发请求而永不触顶。现在 `check_call_budget` 移入 `_dispatch`，**每次请求前**判、逐请求 +1，超限的请求不会出网。支付口径不变：`LaneResult.attempts` 仍记录真实请求数，`InvocationCost.attempts` 语义不变。
- **D-O12-14（provider 应答不可读 → `LaneResponseError`；成员复审 C1）**：`ProviderLaneError` 是声明唯一的错误面，实测却有**三类异常逃逸**：非 JSON body →`json.JSONDecodeError`、`usage` 非数值 →`ValueError`、`usage` 为 list / `*_details` 为 str →`AttributeError`（第三类是 owner 发现的）。下游没炸只因 `orchestrator`/`writing_service` 用 `except Exception` 兜底——**那是下游仁慈，不是接口正确**。现在非 JSON body、非对象 body、畸形 `choices`、不可读 `usage` 一律抛 `LaneResponseError`（继承 `LaneTransportError` 以保既有 `except` 不破），且 **`retryable=False`**：2xx + 畸形 body 是确定性结论，重试只会再付一次钱。`Usage.__post_init__` 的负值 fail-closed 消息不被覆盖。
- **D-O12-10（override 数据必须自校验；独立盲审 v3）**：override 只在**实际 patch 了 ≥1 档价目**时才给模型打来源标签（否则 receipt 会声称一个并未提供数字的价目表，`price_source` 的意义被摧毁）；价目字段严格校验——负数 / NaN / ±inf / 非数值一律 `LaneCatalogError` fail-closed；畸形条目（非 dict、`models` 非对象）在**加载期显式报错**而非抛裸 `AttributeError`/`ValueError`。理由：价目是每个成本数字的审计依据，坏数据必须响，不能静默。

## Completed

- `src/autoresearch/provider_lane.py`（~1200 行）：身份/目录/计价/凭据/漂移/预算/anthropic 档位 + transport（预算接线 + 重试计数）+ handoff/sampling + `receipt_usage_fields` + `lane_drift_event` + `ModelCatalog.price_source`。
- `src/autoresearch/lane_llm_adapter.py`：O12↔B4 薄缝。
- `src/autoresearch/llm.py`：lane 后端，公共签名不变；计价按 model id、endpoint 规范化、透出 `price_source`。
- `src/autoresearch/contracts.py`：新增共享 `TokenUsage` / `InvocationCost`（含 `attempts` / `price_source`）。
- `src/autoresearch/invocation_contracts.py`：re-export 共享类型 + `InvocationReceipt.tokens/cost`。
- `src/autoresearch/capability_registry.py`：`CapabilityInvocationReceipt` 引用共享类型 + 2 个可选字段。
- `data/models_catalog.json` + `data/price_overrides.json`（内置模型官方价目，v3）+ `scripts/refresh_model_catalog.py` + `scripts/parity_real_lane.py`。
- 真实录制 fixture：`replay_workbuddy_deepseek-v4-pro.json`、`replay_workbuddy_glm-5_3.json`。
- 测试：`test_provider_lane.py` / `_transport` / `_parity` / `_receipt`、`test_lane_llm_adapter.py`、`test_llm_lane_replacement.py`。
- 文档：`PLAN.md`（已修订）、`CONTRACT-PARITY.md`、`SELF-REVIEW.md`（v2/v3）、`PRICE-POLICY.md`（v3）；`TASK-QUEUE.md` 与 registry 状态更新。

## Pending

- S3.3 **已完成**（成员 A 复审，3 条意见全部复现为真）→ 剩 S3.4。
- S3.4 需在合并后执行。
- S3.4 registry 回写（S3-A2-PROVIDER-LANE → integrated，合并后执行）。
- **价目口径已定（v3，Owner 拍板）**：tokens 为主口径、cost 为辅（带 `price_source`）；内置模型 DeepSeek V4.1 Flash 按官方 peak 价钉住（\$0.30/\$1.20/\$0.006，见 `price_overrides.json`）；核对走人工（成本敏感实验前），不写官网爬虫。政策见 `PRICE-POLICY.md`。
- **价格收敛仍需机制**（未闭合）：override 只钉住在用模型，其余模型仍用快照价；peak/off-peak 双档在目录结构中不可表达；provider 变更模型路由（如 09-14 `deepseek-v4-pro` 改路由）刷新脚本发现不了，只能人工核对时发现。
- **待复审人裁决**：跨 lane 增量修改 S3-A 的 `capability_registry.py`（引用共享类型 + 2 个可选字段，越界面已最小化）。
- **自审未闭合项（详见 `SELF-REVIEW.md` §6）**：①`normalize_usage_openai` 假定 `prompt_tokens` 含 cache 命中，第三方端点未验证；②模型生命周期漂移（官方将弃用 `deepseek-v4-flash` 名、09-14 改路由 `deepseek-v4-pro`）；③`lane_drift_event` 无生产写入路径；④`LLMService` 不跑漂移校验（有意偏差，PLAN 已修订）。
- backlog（范围裁剪）：流式 async iterator、grammar（lark/regex）、anthropic-messages transport、本地 token 估算器、Anthropic 1h cacheWrite 计价。

## Next step

**先推 owner 代修**（rebase 已改写历史，需 `--force-with-lease` 更新 PR #15），再请成员 A 复核 C1–C4 的修复是否彻底（尤其是 `default_budget_profile` 的推导口径与 D-O12-12 中 `LLMService` 可选签名那一处偏离）。原始复审要求：**请优先攻击 `SELF-REVIEW.md` §4.5（价目口径）与 §6 第 1、2 条**——那是唯一未闭合且影响 A5 的部分；另请对「跨 lane 引用共享类型 + 加可选字段」表态。§8 记录了独立盲审的 4 项发现及其修复，可一并复核。复审通过并合并后回写 registry（S3.4）。

## Verification

- [x] `PYTHONPATH=src python -m pytest -W error -q` → **268 passed, 2 skipped, 0 failed**（CI 同口径；计数改用 summary 行 + 退出码——v2 曾因只数点阵而漏报 1 个 `F`）。
- [x] `python -m ruff check src tests` → All checks passed。
- [x] `python -m compileall -q src` → exit 0。
- [x] `PYTHONPATH=src python -m autoresearch.provider_lane --catalog` → 六条 preset lane 离线实例化通过。
- [x] 聚焦：`test_provider_lane_receipt.py` 8 passed · `test_lane_llm_adapter.py` 7 passed · `test_llm_lane_replacement.py` 10 passed · `test_provider_lane_transport.py` 30 passed。
- [x] rebase 至 `main@380bd49`：零冲突。
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/O12-PROVIDER-LANE.md --base main` → valid；`python scripts/check_pr_contract.py --base main` → passed。
- [x] **对抗性自审 v1/v2**：7 组边界实验实跑；6 项缺陷（F1 计价静默归零 / F2 空 settings 错误无提示 / F3 空白凭据 fail-late / G1 预算守卫死代码 + 文档不实 / G2 drift 事件缺失 / G3 LLMService 未跑漂移校验）——5 修 1 文档化。
- [x] **独立子代理盲审 v3**（不知情第三方，审 v2 之后的增量 diff）：**4 项发现与自查零重叠**——B1 override 零 patch 仍打来源标签（假来源）、B2 负数价目静默入库、B3 畸形 override 炸离线目录、B4 子串匹配（被 B3 覆盖）。全部修复 + 12 项新测试；并据此修正 v2「254 passed 全绿」的误报。详见 `SELF-REVIEW.md` §8。
- [x] **S3.1 真实 parity（WorkBuddy 端点）**：`deepseek-v4-pro` 真实调用 `PONG`，usage `input=22 / output=2`；套 catalog 价目得 `cost.total=1.131e-05 USD`，与手算 delta=0（**注：这是自证口径，只证明计价器内部一致**）。
- [x] **S3.1 诚实负结果**：`glm-5.3` 真实调用成功但无 catalog 条目 → `cost=0`（unpriced，未编造）。
- [x] **官方价目对照（自审 v2，联网实测）**：抓取 DeepSeek 官方定价页（2026-09-11）。结果 **不一致**：`deepseek-v4-pro` input 快照 $0.435 vs 官方 $0.66(off-peak)/$1.32(peak)；output 快照 $0.87 vs $1.98/$3.96（**偏差最高约 4.5×**）；`deepseek-v4-flash` 官方 output $0.60/$1.20 vs 快照 $0.28。官方另有 peak/off-peak 双档结构（目录不支持），且官方声明 `deepseek-v4-flash` 为 legacy 名、`deepseek-v4-pro` 自 2026-09-14 起整体路由到 V4.1 Flash。→ 已机制化为 `price_source` / `attempts`；快照收敛列为未闭合项。
- [x] `AUTORESEARCH_LANE_REAL=1 pytest tests/test_provider_lane_parity.py -q` → 6 passed；默认 4 passed + 2 skipped。
- [x] **override 机制实测（v3）**：`build_preset_lane("deepseek:chat:v1")` → cost `0.30 / 1.20 / 0.006`、`price_source = "override 2026-09-11 api-docs.deepseek.com"`；未覆盖的模型仍报 `models.dev snapshot 2026-09-10`；指向未知条目的 override 被忽略且不崩溃（+2 测试）。
- [x] **override 边界（v3 盲审修复）**：零 patch 不打 override 标签 · 负数/NaN/±inf/非数值 fail-closed · 畸形条目（非 dict、`models` 为 list）加载期显式报错 · 部分 patch 只改指定档——共 +12 测试。
- [x] **owner 代修 C1–C4 复验（2026-09-11）**：全量 `-W error` → **304 passed / 2 skipped**（修复前 288 + 新增 16）；`ruff check src tests` → All checks passed；`check.mjs` → valid；`check_pr_contract` → valid（29 paths / 1 ledger）；rebase 至 `main@66aba64` 后基线 288 保持不变（说明 4 处改动零回归）。
- [x] **新测试判别力实测（关键）**：新增 16 个测试**实例**在**修复前**的代码下 **12 个失败**——唯一需要 shim 的原因只是修复前连 `DEFAULT_MAX_CALLS_PER_RUN` / `LaneResponseError` / `LaneRunLedger` 都不存在。未失败的 4 个是**刻意的非缺陷断言**：常量锚（240）、显式 profile 覆盖、缺省作用域记录、以及「JSON 非对象」路径（该路径原本就已被 `except (KeyError, IndexError, TypeError)` 接住）。→ 既有 288 条测试对这四个缺陷**一个都抓不到**，这正是补测的理由。
- [x] **C1 逃逸面实测**：非 JSON body / 非对象 body / `usage=[1,2]` / `usage.prompt_tokens="n/a"` / `prompt_tokens_details="cached"` 五类 payload 全部以 `ProviderLaneError` 回来（修复前分别以 `JSONDecodeError` / `ValueError` / `AttributeError` 逃出）。
- [x] **C4 口径实测**：429→200 且 `max_calls_per_run=1` → 第二次请求**未出网**即被拒（修复前会发出且 `calls_made` 仍为 1）；正常预算下 `attempts=2` 且 `calls_made=2`、`calls_completed=1`。
- [x] **C3 作用域实测**：两个 transport 共享一个 ledger、cap=1 → 第二个 transport 的请求未出网即被拒（修复前两实例各自跑满，两次都成功）。
- [x] **C2 实测**：`PRESET_LANE_IDS` 六条 lane 的三项 cap 全部非 `None`；`max_cost_per_call_usd ≥ 该 lane 满窗调用按基础费率计价`（推导自证），且显式 profile 仍可覆盖默认。
- [x] **环境耦合修复（v3 盲审）**：`test_empty_key_fails_closed…` 改为 monkeypatch 清环境自包含（本机 shell 的 `DEEPSEEK_API_KEY` 曾使它假红），并补反向断言「环境有 key 时取用而非发空 Bearer」。

## Handoff note

- From: `user/team`
- To: `member A`
- Summary（2026-09-11 owner 代修后更新）: 成员 A 复审提出的 3 条意见**全部复现为真**，owner 已修 C1–C4 并 rebase 至 `main@66aba64`（全量 304 passed，新增测试 16 个实例中 12 个在修复前失败）。**本次请重点复核**：① `default_budget_profile` 的推导口径（`max_calls_per_run=240` 与 A5 对齐、成本上限按满窗×最坏档×1.5 余量）是否合理；② D-O12-12 给 `LLMService` 加了**可选** `ledger=`（既有调用语义不变，但确实动了签名）——如判定违反「签名不变」不变量，可回退为仅在 adapter 侧注入；③ `LaneResponseError` 继承 `LaneTransportError` 的兼容性处理是否恰当。以下为原始交付说明：O12 段 1/段 2/S3.1 已完成，并通过**两轮自审 + 一轮独立盲审**（`SELF-REVIEW.md` v2 / §8）。**最需要你看的是 §4.5**：真去抓了 DeepSeek 官方定价页，**发现本项目价目快照与官方最高差约 4.5×、且缺 peak/off-peak 结构**——这条直接影响 A5 的成本口径，已机制化（`price_source` / `attempts`）但未收敛。§8 是独立盲审在 override 机制上抓到的 4 项缺陷（已修复），可复核其修复是否彻底。另需你对「跨 lane 引用共享类型 + 加可选字段」表态。已知偏离：D-O12-03（`complete_json` 保 `json_object`）已确认，PLAN 原文已同步修订。
