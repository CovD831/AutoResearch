# O12 ProviderLane

- ID: `O12-PROVIDER-LANE`
- Title: `ProviderLane 与 LLM 调用底座（pi-ai 语义移植 + openpilot lane 约束）`
- Status: `reviewing`
- Status note: 段 1 + 段 2 + S3.1 完成；2026-09-11 完成**对抗性自审**（6 发现 / 5 修复 / 1 转文档化偏差，见 `SELF-REVIEW.md`）后提 PR #15 交成员 A 复审（不自批）。S3.4 registry 回写待合并后。
- Owner: `user/team`
- Next owner: `member A`

## Goal

用一条可离线校验的 provider lane 替换 `llm.py` 的裸 httpx 单发：lane 不可变身份 + pi-ai
六机制（模型目录含 cost/contextWindow、usage→receipt 计价、跨 provider handoff、
reasoning 档位、constrained-sampling 降级、auth/重试分类）+ openpilot lane 约束
（预算档 fail-closed、凭据白名单、settings 漂移 fail-closed）。`LLMService` 公共签名不变，
成为 A5 计价链与 B6 写作头切换的供给方。

## Acceptance scenarios

- [x] S1.1 目录快照：`data/models_catalog.json`（models.dev MIT 快照）+ `scripts/refresh_model_catalog.py`；`python -m autoresearch.provider_lane --catalog` 六条 preset lane 离线实例化成功。
- [x] S1.2 模块骨架：`LaneIdentity`（frozen）+ `ModelCatalog` + `CredentialResolver` 白名单 + 异常族（fail-closed 带 recovery 提示）。
- [x] S1.3 计价器：`CostCalculator` 四档 tiers，reasoning ⊂ output 不重复计价，对照 pi-ai 样例。
- [x] S1.4 漂移注入：`validate_lane_settings` + `provider.lane_drift` 事件工厂；参数化用例覆盖 **7 个字段**篡改全被拒（与 PLAN 逐项对齐）。
- [x] S1.5 parity fixture 骨架：mock / replay / real-skip 三路，real 标记 skip。
- [x] S2.0 账本：本文件（repo-task-sync 格式，`check.mjs` valid）。
- [x] S2.1 B4 对缝：`lane_llm_adapter.py`（74 行薄缝，复用 B4 类型，契约 diff=0）+ `CONTRACT-PARITY.md`。
- [x] S2.2 transport：httpx 同步 + retry 分类（429/408/5xx 指数退避；401/403/422 fail fast；client/sleep 可注入）；**预算档已接线**（自审 G1：dispatch 前查调用上限、事后累计 cost/tokens）。
- [x] S2.3 handoff + 档位：四规则（tool id 截 64 / 图片降级 / 孤儿 tool call 补全 / thinking→text）+ anthropic 两代 thinking 映射。
- [x] S2.4 constrained sampling：`make_strict_json_schema` 三规则 + 降级矩阵（prefer→json_object / require→`LaneStrictError`）。
- [x] S2.5 receipt 计价：共享 `TokenUsage`/`InvocationCost` 字段冻结并接入 A1 与 S3-A 两处 receipt；`receipt_usage_fields()` 供给。
- [x] S2.6 llm.py 替换：`LLMService` 内部改走 lane，构造/方法签名不变，消费方零改动；**计价按 model id 从快照解析**（自审 F1：endpoint 拼写差异不再静默归零）。
- [x] S3.1 真实 parity：WorkBuddy 自定义端点真实调用 2 模型，采集 usage；priced lane cost 与手算误差 0，unpriced lane 诚实归零（**注**：单端点双模型，非双 provider；官方价目对照不可得）。
- [x] S3.2 交付：PR #15（代码 + 账本 + `CONTRACT-PARITY.md` + `SELF-REVIEW.md`）。
- [ ] S3.3 复审：成员 A 人工复审（审核不自批，Owner 同为被审方）。
- [ ] S3.4 registry 回写：S3-A2-PROVIDER-LANE → integrated（合并后）。

## Invariants

- 不修改 B4 独占路径 `reader_writer_ports.py`；薄缝只读消费其契约，无镜像类型、无新增 port 方法。
- `LLMService(settings)` / `available` / `complete` / `complete_json` 签名与返回语义不变；消费方零改动。
- 不新增 Store、消息总线、scheduler、隐藏 Agent；不绕过 Evidence/Policy（`lane_drift_event` 只产事件，写入权留给调用方）。
- 目录为 vendored 静态快照，离线可校验；网络仅出现在显式刷新脚本与真实 parity。
- fail-closed 方向不变：缺凭据 / 目录缺失 / 不支持档位 / strict 不满足 / 预算超限 → 显式报错，不静默降级。
- 计价是信息性的：`tokens`/`cost` 为 None 不阻塞 admissibility，也不改变 Gate 判定。
- 真实调用的凭据只从 `~/.workbuddy/models.json` 读取，永不写入仓库或 fixture。

## Decisions

- **D-O12-01（薄缝零镜像）**：`lane_llm_adapter.py` 直接 import B4 的 `StructuredReadingPayload` / `StructuredDraftPayload` / `Structured{Reader,Writer}Adapter`，用 `is` identity 断言锁定，不做字段镜像。
- **D-O12-02（settings lane 显式凭据）**：`LaneTransport` 的 `credential` 参数优先于 env 白名单；**空白凭据视同未提供**（自审 F3），走 fail-closed 而非发出空 Bearer。未配置 catalog 条目的端点生成 unpriced lane（cost=0），不静默编造价目。
- **D-O12-03（complete_json 保 json_object，偏离 PLAN §4.5；Owner 已确认）**：无 schema ⇒ `require` 无语义；deepseek lane 不支持 strict，`require` 会破坏「零破坏」验收。有 schema 的路径（`lane_llm_adapter`）已自动对支持 strict 的 lane 发 `json_schema strict=True`。**PLAN §4.5 与 §4 决策 4 原文已就地修订**，消除文档与实现的矛盾。
- **D-O12-04（receipt 计价 schema 冻结）**：`tokens={input,output,cache_read,cache_write,reasoning}`、`cost={input,output,cache_read,cache_write,total,currency,model,lane_id}`（PLAN §4.2 字段名）。A5 按其已预留条款实现；字段名由测试锁定。
- **D-O12-05（真实 parity 端点与口径）**：WorkBuddy 自定义端点（OpenAI 兼容）；模型 id 命中 vendored catalog 时套用其价目，未命中则 unpriced，不编造。**第二条 provider 的官方价目对照不可得**（端点非官方直连），记为已知限制。
- **D-O12-06（计价来源与 endpoint 解耦；自审 F1）**：价目是**模型属性**而非 endpoint 属性。`llm.py` 因此按 model id 从快照解析价目，`endpoint` 仅用于复用 preset lane 的身份元数据，且比较时容忍尾斜杠、`/v1` 后缀与主机大小写。修复前 `.../v1` 或大小写差异会导致**计价静默归零**。
- **D-O12-07（预算守卫必须接线；自审 G1）**：`check_call_budget` 原先无生产调用点，而 `LaneTransport` 文档却声称已强制。现于 dispatch 前查 `max_calls_per_run`，事后累计 cost/tokens 并对 per-call 成本与 per-run token 上限 fail-closed；文档同步改为实际行为（per-call 成本只能事后判定，无 token 预估器）。

## Completed

- `src/autoresearch/provider_lane.py`（~1180 行）：身份/目录/计价/凭据/漂移/预算/anthropic 档位 + transport（含预算接线）+ handoff/sampling + `receipt_usage_fields` + `lane_drift_event`。
- `src/autoresearch/lane_llm_adapter.py`：O12↔B4 薄缝。
- `src/autoresearch/llm.py`：lane 后端（`lane_from_settings` + `LaneTransport`），公共签名不变；计价按 model id 解析、endpoint 规范化比较。
- `src/autoresearch/invocation_contracts.py`：共享 `TokenUsage` / `InvocationCost` + `InvocationReceipt.tokens/cost`。
- `src/autoresearch/capability_registry.py`：`CapabilityInvocationReceipt` 同名字段（复用共享类型）。
- `data/models_catalog.json` + `scripts/refresh_model_catalog.py` + `scripts/parity_real_lane.py`。
- 真实录制 fixture：`replay_workbuddy_deepseek-v4-pro.json`、`replay_workbuddy_glm-5_3.json`。
- 测试：`test_provider_lane.py` / `_transport` / `_parity` / `_receipt`、`test_lane_llm_adapter.py`、`test_llm_lane_replacement.py`。
- 文档：`PLAN.md`（已修订）、`CONTRACT-PARITY.md`、`SELF-REVIEW.md`；`TASK-QUEUE.md` 与 registry 状态更新。

## Pending

- S3.3 成员 A 人工复审（本 PR，审核不自批）。
- S3.4 registry 回写（S3-A2-PROVIDER-LANE → integrated，合并后执行）。
- **自审未闭合项（诚实清单，详见 `SELF-REVIEW.md` §6）**：①重试可能重复计费（上界 4 次调用），receipt 未记录重试次数；②`normalize_usage_openai` 假定 `prompt_tokens` 含 cache 命中，第三方端点未验证；③官方价目对照缺失（仅有快照价目 + 手算一致性）；④`lane_drift_event` 无生产写入路径；⑤`LLMService` 不跑漂移校验（settings 派生路径无漂移对象，已修订 PLAN 标注）。
- **待复审人裁决**：跨 lane 增量修改已 accepted 的 `capability_registry.py`（新增 2 个可选字段）。
- backlog（范围裁剪）：流式 async iterator、grammar（lark/regex）、anthropic-messages transport、本地 token 估算器、Anthropic 1h cacheWrite 计价。

## Next step

成员 A 复审本 PR。**请优先攻击 `SELF-REVIEW.md` §4（钢人论证）与 §6（剩余风险）**，而非复述 §3 的对抗实验；另请对「跨 lane 修改 S3-A 产物」明确表态。复审通过并合并后回写 registry（S3.4）。

## Verification

- [x] `PYTHONPATH=src python -m pytest -W error -q` → **248 passed, 2 skipped**（CI 同口径；两个 `real_api` 用例默认 skip）。
- [x] `python -m ruff check src tests` → All checks passed。
- [x] `python -m compileall -q src` → exit 0。
- [x] `PYTHONPATH=src python -m autoresearch.provider_lane --catalog` → 六条 preset lane 离线实例化通过。
- [x] `pytest tests/test_provider_lane_receipt.py -q` → 6 passed（`-k receipt` 覆盖）。
- [x] `pytest tests/test_lane_llm_adapter.py -q` → 7 passed（含 B4 类型 identity 断言）。
- [x] `pytest tests/test_llm_lane_replacement.py -q` → 10 passed（含 endpoint 拼写、第三方端点计价、未知模型 unpriced、空白凭据）。
- [x] `pytest tests/test_provider_lane_transport.py -q` → 28 passed（含预算接线 3 用例）。
- [x] rebase 至 `main@380bd49`：零冲突。
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/O12-PROVIDER-LANE.md --base main` → valid。
- [x] **对抗性自审**：7 组边界实验实际运行；发现 F1（计价静默归零，中危）、F2（空 settings 错误无提示，低危）、F3（空白凭据 fail-late，低危）、G1（预算守卫死代码 + 文档不实声明，中危）、G2（drift 事件缺失，中危）、G3（LLMService 未跑漂移校验，文档化偏差）；F1–F3、G1 已修并被测试锁定，G2 补形态，G3 修订 PLAN。**独立盲审未执行**（子代理派发因网络不可用失败），独立性削弱已在 `SELF-REVIEW.md` §1 如实标注。
- [x] **S3.1 真实 parity（WorkBuddy 自定义端点）**：`deepseek-v4-pro` 真实调用返回 `PONG`，usage `input=22 / output=2`；套 catalog 价目（$0.435/$0.87 per 1M）得 `cost.total=1.131e-05 USD`，与手算 **delta = 0**。
- [x] **S3.1 诚实负结果**：`glm-5.3` 真实调用成功（usage `input=30 / output=20 / reasoning=15`）但无 catalog 条目 → `cost.total=0.0`（unpriced，未编造）。
- [x] `AUTORESEARCH_LANE_REAL=1 pytest tests/test_provider_lane_parity.py -q` → 6 passed；默认 4 passed + 2 skipped。
- [ ] 第二条 provider 的官方价目表对照：端点非官方直连，暂无官方价目可比（待官方 key 可用时补，脚本无需改动）。

## Handoff note

- From: `user/team`
- To: `member A`
- Summary: O12 段 1/段 2/S3.1 已完成，并已通过一轮**对抗性自审**（6 发现 / 5 修复，详见 `SELF-REVIEW.md`）。本轮自审为「主审自查」——**独立盲审因网络不可用未执行**，故请重点攻击 `SELF-REVIEW.md` §4 的钢人论证与 §6 的剩余风险，那里才是真正需要第二双眼睛的地方。另需你对「跨 lane 增量修改 S3-A 的 `capability_registry.py`」表态。已知偏离：D-O12-03（`complete_json` 保 `json_object`）已确认，PLAN 原文已同步修订。
