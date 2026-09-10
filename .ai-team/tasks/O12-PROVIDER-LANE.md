# O12 ProviderLane

- ID: `O12-PROVIDER-LANE`
- Title: `ProviderLane 与 LLM 调用底座（pi-ai 语义移植 + openpilot lane 约束）`
- Status: `reviewing`
- Status note: 段 1（S1.1–S1.5）+ 段 2（S2.0–S2.6）+ S3.1 真实 parity 本地完成；分支基于 `main@380bd49`（rebase 零冲突）。2026-09-11 提 PR 交成员 A 复审（不自批）。S3.4 registry 回写待合并后。
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
- [x] S1.4 漂移注入：`validate_lane_settings` + `provider.lane_drift` 判定；7 项 settings 篡改全被拒。
- [x] S1.5 parity fixture 骨架：mock / replay / real-skip 三路，real 标记 skip。
- [x] S2.0 账本：本文件（repo-task-sync 格式，`check.mjs` valid）。
- [x] S2.1 B4 对缝：`lane_llm_adapter.py`（74 行薄缝，复用 B4 类型，契约 diff=0）+ `CONTRACT-PARITY.md`。
- [x] S2.2 transport：httpx 同步 + retry 分类（429/408/5xx 指数退避；401/403/422 fail fast；client/sleep 可注入）。
- [x] S2.3 handoff + 档位：四规则（tool id 截 64 / 图片降级 / 孤儿 tool call 补全 / thinking→text）+ anthropic 两代 thinking 映射。
- [x] S2.4 constrained sampling：`make_strict_json_schema` 三规则 + 降级矩阵（prefer→json_object / require→`LaneStrictError`）。
- [x] S2.5 receipt 计价：共享 `TokenUsage`/`InvocationCost` 字段冻结并接入 A1 与 S3-A 两处 receipt；`receipt_usage_fields()` 供给。
- [x] S2.6 llm.py 替换：`LLMService` 内部改走 lane，构造/方法签名不变，orchestrator/writing_service 零改动。
- [x] S3.1 双 provider 真实 parity：WorkBuddy 自定义端点真实调用 2 模型，采集 usage；priced lane cost 与手算误差 0，unpriced lane 诚实归零。
- [x] S3.2 交付：本 PR（代码 + 账本 + `CONTRACT-PARITY.md`）。
- [ ] S3.3 复审：成员 A 人工复审（审核不自批，Owner 同为被审方）。
- [ ] S3.4 registry 回写：S3-A2-PROVIDER-LANE → integrated（合并后）。

## Invariants

- 不修改 B4 独占路径 `reader_writer_ports.py`；薄缝只读消费其契约，无镜像类型、无新增 port 方法。
- `LLMService(settings)` / `available` / `complete` / `complete_json` 签名与返回语义不变；消费方零改动。
- 不新增 Store、消息总线、scheduler、隐藏 Agent；不绕过 Evidence/Policy。
- 目录为 vendored 静态快照，离线可校验；网络仅出现在显式刷新脚本与真实 parity。
- fail-closed 方向不变：缺凭据 / 目录缺失 / 不支持档位 / strict 不满足 → 显式报错，不静默降级。
- 计价是信息性的：`tokens`/`cost` 为 None 不阻塞 admissibility，也不改变 Gate 判定。
- 真实调用的凭据只从 `~/.workbuddy/models.json` 读取，永不写入仓库或 fixture。

## Decisions

- **D-O12-01（薄缝零镜像）**：`lane_llm_adapter.py` 直接 import B4 的 `StructuredReadingPayload` / `StructuredDraftPayload` / `Structured{Reader,Writer}Adapter`，用 `is` identity 断言锁定，不做字段镜像。B4 L3「Known limits」把 live provider wiring 划归 O12，本缝即该缺口的全部实现。
- **D-O12-02（settings lane 显式凭据）**：`LaneTransport` 新增 `credential` 参数，显式凭据优先于 env 白名单。理由：`LLMService` 的 key 以 `SecretStr` 存在于 Settings，不发布为 env 变量，白名单读不到；不复用会使零破坏替换失败。未配置 catalog 条目的端点生成 unpriced 设置 lane（cost=0），保证调用可用且不静默编造价目。
- **D-O12-03（complete_json 保 json_object，偏离 PLAN §4.5；2026-09-11 Owner 已确认）**：PLAN 原文「`complete_json` 走 strict=require」；实现保留 `{"type":"json_object"}`（等价 `strict="prefer"` 降级）。理由：①deepseek lane `supports_strict_json_schema=False`，require 会 `LaneStrictError`，直接破坏 S2.6「零破坏」验收；②`complete_json` 无 schema，require 无语义。**补充（Owner 追问后澄清）**：「lane 支持则 require，否则 prefer」在本路径不可实施（无 schema 即无 require 语义）；有 schema 的路径（`lane_llm_adapter`）已由 `resolve_response_format` 自动对支持 strict 的 lane 发 `json_schema strict=True`，无需额外开关。结论：保持现状。
- **D-O12-04（receipt 计价 schema 冻结）**：`tokens={input,output,cache_read,cache_write,reasoning}`、`cost={input,output,cache_read,cache_write,total,currency,model,lane_id}`（PLAN §4.2 字段名）。A5 按其已预留条款实现；`test_a5_reserved_schema_field_names_are_stable` 锁定字段名。
- **D-O12-05（真实 parity 端点与口径）**：S3.1 真实调用使用 WorkBuddy 自定义端点（`workbuddy2api.henryai.top/v1`，OpenAI 兼容）。模型 id 命中 vendored catalog 时套用其价目（`deepseek-v4-pro` → input $0.435 / output $0.87 per 1M）；未命中则 unpriced（`glm-5.3`），**不编造价目**，误差以「cost 链 vs 手算」口径记录。第二条 provider 的官方价目对照受限于端点非官方直连，标记为已知限制。

## Completed

- `src/autoresearch/provider_lane.py`（~1130 行）：身份/目录/计价/凭据/漂移/预算/anthropic 档位 + transport/handoff/sampling + `receipt_usage_fields`。
- `src/autoresearch/lane_llm_adapter.py`：O12↔B4 薄缝。
- `src/autoresearch/llm.py`：替换为 lane 后端（`lane_from_settings` + `LaneTransport`），公共签名不变。
- `src/autoresearch/invocation_contracts.py`：新增共享 `TokenUsage` / `InvocationCost`，`InvocationReceipt` 增 `tokens`/`cost`。
- `src/autoresearch/capability_registry.py`：`CapabilityInvocationReceipt` 增同名字段（复用共享类型）。
- `src/autoresearch/data/models_catalog.json` + `scripts/refresh_model_catalog.py`。
- `scripts/parity_real_lane.py`：S3.1 真实 parity 采集/录制脚本（凭据外置）。
- 真实录制 fixture：`replay_workbuddy_deepseek-v4-pro.json`、`replay_workbuddy_glm-5_3.json`。
- 测试：`test_provider_lane.py` / `_transport` / `_parity` / `_receipt`、`test_lane_llm_adapter.py`、`test_llm_lane_replacement.py`。
- 文档：`PLAN.md`、`CONTRACT-PARITY.md`；`TASK-QUEUE.md` 与 registry 的 O12 状态更新。

## Pending

- S3.3 成员 A 人工复审（本 PR，审核不自批）。
- S3.4 registry 回写（S3-A2-PROVIDER-LANE → integrated，合并后执行）。
- D-O12-03 已闭环（2026-09-11 Owner 确认保持 `json_object`，见 Decisions）。
- backlog（范围裁剪，已知）：流式 async iterator、grammar（lark/regex）、anthropic-messages transport、本地 token 估算器、Anthropic 1h cacheWrite 计价。

## Next step

成员 A 复审本 PR（重点：`lane_llm_adapter.py` 的零镜像、`llm.py` 的零破坏、receipt 字段 schema）；复审通过并合并后回写 registry（S3.4）。

## Verification

- [x] `PYTHONPATH=src python -m pytest -q` → **239 passed, 2 skipped**（基于 `main@380bd49`；两个 `real_api` 用例默认 skip）。
- [x] `python -m ruff check src tests` → All checks passed。
- [x] `PYTHONPATH=src python -m autoresearch.provider_lane --catalog` → 六条 preset lane 离线实例化通过。
- [x] `pytest tests/test_provider_lane_receipt.py -q` → 6 passed（`-k receipt` 覆盖）。
- [x] `pytest tests/test_lane_llm_adapter.py -q` → 7 passed（含 B4 类型 identity 断言）。
- [x] `pytest tests/test_llm_lane_replacement.py -q` → 5 passed（签名不变 + 确走 lane）。
- [x] rebase 至 main：零冲突（分支原为 main 祖先；main 无 O12 同名文件、未改 `TASK-QUEUE.md`）。
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/O12-PROVIDER-LANE.md --base main` → valid。
- [x] **S3.1 真实 parity（WorkBuddy 自定义端点）**：`deepseek-v4-pro` 真实调用返回 `PONG`，usage `input=22 / output=2`；套 catalog 价目（$0.435/$0.87 per 1M）得 `cost.total=1.131e-05 USD`，与手算 **delta = 0**。fixture `replay_workbuddy_deepseek-v4-pro.json` 已录制（不含凭据）。
- [x] **S3.1 诚实负结果**：`glm-5.3` 真实调用成功（usage `input=30 / output=20 / reasoning=15`）但端点模型无 vendored catalog 条目 → `cost.total=0.0`（unpriced，未编造价目）。记录入 `replay_workbuddy_glm-5_3.json`。
- [x] `AUTORESEARCH_LANE_REAL=1 pytest tests/test_provider_lane_parity.py -q` → 6 passed（含 2 个真实调用用例）；默认模式 4 passed + 2 skipped。
- [ ] 第二条 provider 的官方价目表对照：受限于 WorkBuddy 端点非官方直连，暂以 catalog 价目 + 手算口径替代（已知限制，待官方 key 可用时补）。

## Handoff note

- From: `user/team`
- To: `member A`
- Summary: O12 段 1/段 2/S3.1 已完成并回归，本 PR 交你复审（Owner 为被审方，审核不自批）。请重点看三处接缝：①`lane_llm_adapter.py` 对 B4 契约的零镜像（`CONTRACT-PARITY.md`）；②`llm.py` 替换的零破坏（公共签名与 orchestrator/writing_service 零改动）；③receipt 计价字段 schema（D-O12-04，A5 按此实现）。已知偏离：D-O12-03（`complete_json` 保 `json_object`）已由 Owner 确认，理由见 Decisions。
