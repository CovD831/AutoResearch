# O12 自审报告（对抗性 + 钢人论证）

- 日期：2026-09-11
- 审查对象：PR #15（`owner/provider-lane`，commit `719f034` 起）
- 审查人：owner 侧（舵），**被审方与审查方同源**
- 结论：**6 项发现，5 项已修，1 项转为文档化偏差**；修复后全量 `248 passed / 2 skipped`（`-W error` 口径）。建议进入复审，但复审前请知悉第 6 节的独立性削弱说明。

---

## 1. 方法与独立性（先说弱点）

| 手段 | 状态 | 说明 |
|---|---|---|
| 需求对账（PLAN §4/§5/§6 逐条） | ✅ 执行 | 见第 2 节 |
| 对抗性边界实验（7 组） | ✅ 执行 | 见第 3 节 |
| 跨模块适配检查 | ✅ 执行 | 见第 5 节 |
| 钢人论证 | ✅ 执行 | 见第 4 节 |
| **独立盲审（不知情第三方）** | ❌ **未执行** | 子代理派发失败：`copilot.tencent.com` 无法解析（网络不可用） |

**独立性削弱，必须如实说**：本轮自审是「主审自查」。我能发现自己的**事实性错误**（下面 6 项都是可判定的），但**发现不了自己的判断偏误**——比如我为什么会觉得 `strict=require` 该改掉、为什么接受"跨 lane 修改 S3-A 产物"。这正是需要成员 A 复审的原因：请重点攻击第 4 节的钢人论证，而不是复述第 3 节的实验。

---

## 2. 需求对账

### 2.1 PLAN §6 验收步骤

| 步骤 | 判定 | 证据 / 说明 |
|---|---|---|
| S1.1 目录快照 | ✅ | `models_catalog.json` + `refresh_model_catalog.py`；`--catalog` 六 lane 离线实例化 |
| S1.2 骨架 | ✅ | `LaneIdentity` frozen + 校验；凭据白名单；异常族 |
| S1.3 计价器 | ✅ | 四档 + tiers；reasoning ⊂ output 不重复计价 |
| S1.4 漂移注入 | ✅ | `test_drift_rejects_each_tampered_field` 参数化 **7 个字段**，与 PLAN「7 项」逐项对齐 |
| S1.5 parity 骨架 | ✅ | mock / replay / real-skip 三路 |
| S2.0 账本 | ✅ | `check.mjs` valid |
| S2.1 B4 对缝 | ✅ | 74 行（<80），`is` identity 断言 |
| S2.2 transport | ✅ | 重试分类矩阵 |
| S2.3 handoff + 档位 | ✅ | 四规则 + anthropic 两代映射 |
| S2.4 constrained sampling | ✅ | 三规则 + 降级矩阵 |
| S2.5 receipt 计价 | ✅ | 两处 receipt 共用字段，字段名锁定测试 |
| S2.6 llm.py 替换 | ✅ | 签名不变 + 全量回归（消费方零改动） |
| S3.1 真实 parity | ⚠️ **部分** | 见 2.3 |
| S3.2 交付 | ✅ | 本 PR |
| S3.3 复审 | ⏳ | 待成员 A |
| S3.4 registry 回写 | ⏳ | 合并后 |

### 2.2 PLAN §5 openpilot 采纳清单

| 项 | 判定 |
|---|---|
| frozen lane + `__post_init__` 校验 | ✅ |
| 凭据白名单 + 本地端点豁免 | ✅ |
| **漂移 fail-closed + `provider.lane_drift` 事件** | ⚠️ 判定函数与事件工厂已实现，**但无生产写入路径**（见 4.2 打回理由 2） |
| tokenizer 身份校验（不移植） | ✅ 符合裁剪 |
| 准入模式 → cost/token 上限 | ✅ **本轮补修**：原先 `check_call_budget` 无调用点（见 4.2 打回理由 3） |

### 2.3 PLAN §4 逐机制

| 机制 | 判定 | 说明 |
|---|---|---|
| 4.1 模型目录 | ✅ | |
| 4.2 usage→计价 | ✅ | |
| 4.3 跨 provider handoff | ✅ | |
| 4.4 reasoning 档位 | ⚠️ 偏差 | PLAN 写"其余 format 抛 `NotImplemented`"，实现抛 `ProviderLaneError`（含 recovery 提示）。语义等价且更贴合本项目异常族，属可接受偏差 |
| 4.5 constrained sampling | ⚠️ **偏离** | `complete_json` 用 `json_object` 而非 `strict=require`（D-O12-03）。**PLAN 原文已就地修订**，否则文档与实现永久矛盾 |
| 4.6 auth 与重试 | ⚠️ 偏差 | ①无 `stored` 凭据层（项目无该概念），实现为「显式 > env 白名单」；②无 abort 语义（同步单发），故"abort 不重试"未实现，`retryable` 标志承载可重试分类 |
| S3.1「双 provider」 | ⚠️ 命名落差 | 实为**单端点（WorkBuddy）双模型**（deepseek-v4-pro / glm-5.3）。PLAN 正文允许「deepseek 双模型」，但标题写「双 provider」，且第二条 provider 的官方价目对照不可得 |

---

## 3. 对抗性实验（实际运行，非推演）

脚本：一次性的 lane 解析与契约探针（不入库，结果如下）。

| # | 攻击面 | 修复前 | 修复后 |
|---|---|---|---|
| E1 | `base_url` 尾部 `/` | PRICED ✓ | PRICED ✓ |
| E1 | `base_url` 带 `/v1` | **UNPRICED ❌** | PRICED ✓ |
| E1 | host 大小写不同 | **UNPRICED ❌** | PRICED ✓ |
| E2 | 模型不在目录（`deepseek-chat` / 虚构名） | UNPRICED（正确） | UNPRICED ✓ |
| E3 | `llm_base_url` 为空 | 抛笼统 `ProviderLaneError` | `LaneNotConfiguredError` + recovery 提示 ✓ |
| E4 | 显式空白凭据 | 接受 → 发无 auth 请求才 401 | 视同未提供 → fail closed ✓ |
| E5 | receipt 新字段 round-trip | — | 相等 ✓ |
| E5 | 旧 receipt 记录加载（无新字段） | — | 默认 `None`，可加载 ✓ |
| E6 | 幂等指纹是否受 receipt 影响 | — | 不影响（只哈希 request）✓ |
| E7 | unpriced lane 是否编造价目 | — | 恒为 0，不编造 ✓ |

---

## 4. 钢人论证：如果要打回这个 PR，最强的理由

> 以下按「反方辩手最强版本」写，不是我的自辩。每条给出反方论证与我的裁决。

### 4.1 ~~反方最强：`complete_json` 违反 PLAN 明文~~ → **已就地修订 PLAN**

反方：PLAN §4.5 白纸黑字「`complete_json` 走 strict=require」，实现没做，就是未完成。
裁决：偏离成立且必要（无 schema ⇒ require 无语义；deepseek 不支持 strict ⇒ require 会让 `complete_json` 全线 fail-closed，直接推翻 S2.6 的「零破坏」验收）。**但反方有一点是对的：不能让 PLAN 和实现长期矛盾**——已修订 PLAN §4.5 与 §4 决策 4 的原文并在其中标注原因。现在偏离是可追溯的，不是无声的。

### 4.2 反方最强：**漂移校验与预算守卫是「带测试的死代码」，且文档撒了谎** → **部分成立，已修**

反方：`validate_lane_settings` 与 `check_call_budget` 在整个 `src/` 里**没有任何调用点**，只有测试直接调用它们；而 `LaneTransport` 的文档字符串声称「caps … are enforced by `check_call_budget` (and by the transport in 段 2 before dispatch)」。一个不会被执行的守卫 + 一句不成立的声明，比没有守卫更危险——它会让下游（A5）**以为**预算已被强制。
裁决：**这条打回理由完全成立，是本轮最有价值的发现。** 处置：
- `LaneTransport.complete()` 现在 dispatch 前查 `max_calls_per_run`，事后累计 cost/tokens 并对 `max_cost_per_call` / `max_tokens_per_run` fail-closed（+3 测试）；
- 文档改为实际行为，并明写 per-call cost 只能事后判定（无 token 预估器），不假装能事前拦截；
- 漂移校验**仍无生产调用点**：settings 派生路径上 lane 与观测同源，没有漂移对象。这件事我不粉饰——已在 PLAN §4 决策 4 与账本标注为**已知未接线项**，并补了 `lane_drift_event` 工厂供将来持有冻结 preset lane 的消费方（A5/B6）使用。

### 4.3 反方最强：**跨 lane 修改已 accepted 的 `capability_registry.py`**

反方：S3-A 已 accepted 并合入 main，O12 却改了它的 `CapabilityInvocationReceipt`。这是 owner 越界——凭什么动别人验收过的产物？
裁决：**治理上反方有道理，技术上是纯增量**。改动只是新增两个可选字段（默认 `None`），不改任何既有语义，且不改就无法满足 S2.5（A5 消费的正是这个 receipt）。但「需要改」不等于「可以自己改」——**请复审人明确表态**：接受这次跨 lane 增量，还是要求改为 A5 侧适配。我倾向接受，但这应由不由我定。

### 4.4 反方最强：**retry 引入的成本与延迟没有被收口**

反方：原实现失败即刻降级；现在 429/5xx 会退避重试 3 次（0.5+1+2s）。在 `orchestrator` / `writing_service` 的降级路径上意味着失败时多等 ~3.5s；更糟的是若 provider 已受理但返回 5xx，**重试会重复计费**，而 receipt 只记录最后一次调用。
裁决：**成立，未修，转为记录**。理由：chat.completions 是只读幂等操作，重复计费的上界是 4 次调用成本；PLAN 明确要求重试分类。已列入第 6 节风险，建议 A5 在评测时把「重试次数」也纳入 receipt（当前未记录），否则成本口径会有系统性低估。

### 4.5 反方最强：**真实 parity 名不副实，「误差可解释」是自我定义的**

反方：S3.1 叫「双 provider parity」，实际只有一个第三方端点、两个模型；而且价目对照用的是你自己 vendored 的快照，不是 provider 官方价目表——所谓「误差 0」只是「我的公式算我自己的输入」。
裁决：**成立。** 真实情况是：端到端链路（真实网络 → usage 归一化 → 计价 → receipt 字段）已验证，**但「快照价目 vs 官方价目」的一致性没有被验证**——因为 WorkBuddy 端点非官方直连，没有官方价目可比。已在账本 Verification 末条留空标注待补，不写成已完成。复审人若要求，可换官方 deepseek key 重跑，届时 `parity_real_lane.py` 无需改动。

---

## 5. 跨模块适配矩阵

| 关联模块 | 关系 | 判定 |
|---|---|---|
| `reader_writer_ports.py`（B4） | 薄缝消费其契约 | ✅ 零修改；`is` identity 断言；无新增 port 方法 |
| `capability_registry.py`（S3-A） | 加同名字段 | ⚠️ 跨 lane 增量（见 4.3） |
| `capability.py` / `storage.py`（A1/A2） | receipt 持久化 | ✅ `model_dump_json` 兼容；新字段默认 `None`；旧记录可加载 |
| 幂等指纹（A1/A2） | 只哈希 request | ✅ 不受 receipt 新字段影响 |
| `orchestrator.py` / `writing_service.py` | `LLMService` 消费方 | ✅ `except Exception` 兜底，异常类型漂移不破坏；签名未变 |
| A5 Benchmark | 消费 receipt 计价字段 | ⚠️ **契约已冻结但未经真实消费**（A5 未实现）。字段名由测试锁定，A5 按此实现 |
| B6 Real Pilot | 消费 LLM 边界做交叉评审 | ✅ 可经 `LLMService` 或 `LaneLLMAdapter` |
| ADR-01 | 选型依据 | ✅ pi-ai 语义与目录许可（MIT）一致 |

---

## 6. 剩余风险（诚实清单）

1. **重试的重复计费**（4.4）：上界 4 次调用；receipt 不记录重试次数 → 成本口径可能系统性低估。建议 A5 补计数。
2. **`normalize_usage_openai` 的语义假设**：注释假定 `prompt_tokens` 含 cache 命中（OpenAI/deepseek 成立）。**第三方兼容端点未验证**——WorkBuddy 端点本次真实调用未暴露该字段差异，不代表不存在。若第三方语义不同，`input/cache_read` 会错分。
3. **官方价目对照缺失**（4.5）：仅有 vendored 快照价目 + 手算一致性，无官方对照。
4. **`lane_drift_event` 无写入路径**（4.2）：事件形态已定义并锁定，但没有任何调用方把它写进审计链。
5. **`LLMService` 不跑漂移校验**：PLAN §4 决策 4 的原文要求，已修订 PLAN 并标注原因，属**有意偏差**。
6. **无连接复用**：`LaneTransport` 在未注入 client 时每次新建 `httpx.Client`。性能项，非缺陷。
7. **独立盲审缺席**：见第 1 节。

---

## 7. 本轮修复清单

| 文件 | 变更 |
|---|---|
| `src/autoresearch/llm.py` | endpoint 规范化比较；计价改按 model id 解析（F1）；空 settings 抛带 recovery 的错（F2）；空白凭据视同未提供（F3） |
| `src/autoresearch/provider_lane.py` | `LaneTransport` 接线预算守卫 + 运行计数器（G1）；空白凭据视同未提供；新增 `lane_drift_event` 工厂（G2）；修正文档中不实的预算声明 |
| `tests/test_llm_lane_replacement.py` | +5 用例（endpoint 拼写变体、第三方端点计价、未知模型 unpriced、recovery 提示、空白凭据） |
| `tests/test_provider_lane_transport.py` | +3 用例（调用上限事前拦截、per-call 成本上限、运行计数累计） |
| `tests/test_provider_lane.py` | +1 用例（drift 事件仅在漂移时产生） |
| `docs/.../PLAN.md` | 就地修订 §4 决策 4 与 §4.5 的过时表述 |

验证：`pytest -W error -q` → **248 passed, 2 skipped**；`ruff check src tests` → clean；`check.mjs` → valid。

---

## 8. 结论

本轮自审**发现并修复了 3 类真实缺陷**（计价静默归零、预算守卫死代码 + 文档不实声明、凭据 fail-late），并把 2 处 PLAN 与实现的矛盾就地消除。同时**保留 3 项未闭合事项**（重试计费口径、官方价目对照、漂移事件无写入路径）与 1 项待裁决（跨 lane 修改 S3-A 产物）。

不建议以「自审通过」作为放行依据——**请复审人优先攻击第 4 节与第 6 节，而不是复述第 3 节。**
