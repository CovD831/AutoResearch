# O12 自审报告（对抗性 + 钢人论证）

- 日期：2026-09-11（v2：钢人论证三条处置 + 官方价目对照；v3：独立盲审 + 4 项修复）
- 审查对象：PR #15（`owner/provider-lane`）
- 审查人：owner 侧（舵）；**v1/v2 为同源自查，v3 含独立子代理盲审**
- 结论：**自查 v1/v2 发现 6 项（5 修复 1 文档化）+ 独立盲审 v3 发现 4 项（全修复）**；钢人论证 5 条中 4 条已处置、1 条（跨 lane 修改）降级为待复审确认。修复后全量 `268 passed / 2 skipped`（`-W error` 口径）。
- **v2 最重要的一条**：把「官方价目对照」真的做了——**结果是不一致，最大偏差约 4.5×**（第 4.5 节）。这是 v1 用自证口径掩盖掉的真实问题。
- **v3 最重要的一条**：独立盲审在我**自己新写的 override 合并**里抓到 3 个 medium 缺陷，并戳破一个**我误报的「全绿」**——本机 shell 有 `DEEPSEEK_API_KEY`，一个测试因此带环境耦合，而我的计数脚本只数点阵、**看不见 `F`**。详见第 8 节。

---

## 1. 方法与独立性（先说弱点）

| 手段 | 状态 | 说明 |
|---|---|---|
| 需求对账（PLAN §4/§5/§6 逐条） | ✅ 执行 | 见第 2 节 |
| 对抗性边界实验（7 组） | ✅ 执行 | 见第 3 节 |
| 跨模块适配检查 | ✅ 执行 | 见第 5 节 |
| 钢人论证 | ✅ 执行 | 见第 4 节 |
| 官方价目对照（联网实测） | ✅ **v2 补做** | 见第 4.5 节，结论为**不通过** |
| **独立盲审（不知情第三方）** | ✅ **v3 执行** | 网络恢复后派子代理盲审**未提交增量**；与自查零重叠，见第 8 节 |

**独立性：v1/v2 自查，v3 已补独立盲审**。自查能发现自己的**事实性错误**，发现不了自己的**判断偏误**——v3 派不知情子代理盲审 v2 之后的**全部未提交改动**，它提出的 4 项发现与我的自查**零重叠**，正说明这一点。

两轮活证据：v1 我把「官方价目对照」写成「不可得」就收工，被追问后才真去抓官方定价页——**一抓偏差 4.5×**；v2 我自报「254 passed 全绿」，实际藏了 1 个 `F`，因为**计数脚本只数点阵、看不见失败**。自查最大的风险不是能力，而是**在麻烦的地方提前收手**，以及**工具本身看不见失败**。请复审人据此重点攻击第 4 节、第 6 节与第 8 节。

---

## 2. 需求对账

### 2.1 PLAN §6 验收步骤

| 步骤 | 判定 | 证据 / 说明 |
|---|---|---|
| S1.1 目录快照 | ✅ | `models_catalog.json` + `refresh_model_catalog.py`；`--catalog` 六 lane 离线实例化 |
| S1.2 骨架 | ✅ | `LaneIdentity` frozen + 校验；凭据白名单；异常族 |
| S1.3 计价器 | ✅ | 四档 + tiers；reasoning ⊂ output 不重复计价 |
| S1.4 漂移注入 | ✅ | 参数化 **7 个字段**篡改全被拒，与 PLAN「7 项」逐项对齐 |
| S1.5 parity 骨架 | ✅ | mock / replay / real-skip 三路 |
| S2.0 账本 | ✅ | `check.mjs` valid |
| S2.1 B4 对缝 | ✅ | 74 行（<80），`is` identity 断言 |
| S2.2 transport | ✅ | 重试分类矩阵；**预算档已接线**（v2） |
| S2.3 handoff + 档位 | ✅ | 四规则 + anthropic 两代映射 |
| S2.4 constrained sampling | ✅ | 三规则 + 降级矩阵 |
| S2.5 receipt 计价 | ✅ | 共享字段 + 来源/尝试次数（v2 补） |
| S2.6 llm.py 替换 | ✅ | 签名不变 + 全量回归；计价与 endpoint 解耦（v2 修） |
| S3.1 真实 parity | ⚠️ **部分** | 链路通、计价链通；但官方价目对照**不通过**（见 4.5） |
| S3.2 交付 | ✅ | 本 PR |
| S3.3 复审 | ⏳ | 待成员 A |
| S3.4 registry 回写 | ⏳ | 合并后 |

### 2.2 PLAN §5 openpilot 采纳清单

| 项 | 判定 |
|---|---|
| frozen lane + `__post_init__` 校验 | ✅ |
| 凭据白名单 + 本地端点豁免 | ✅ |
| 漂移 fail-closed + `provider.lane_drift` 事件 | ⚠️ 判定函数与事件工厂已实现，**但无生产写入路径**（见 4.2） |
| tokenizer 身份校验（不移植） | ✅ 符合裁剪 |
| 准入模式 → cost/token 上限 | ✅ **v2 补修**：原先 `check_call_budget` 无调用点（见 4.2） |

### 2.3 PLAN §4 逐机制

| 机制 | 判定 | 说明 |
|---|---|---|
| 4.1 模型目录 | ✅ | |
| 4.2 usage→计价 | ✅ | 但价目**来源**与官方不一致（4.5） |
| 4.3 跨 provider handoff | ✅ | |
| 4.4 reasoning 档位 | ⚠️ 偏差 | PLAN 写「其余 format 抛 `NotImplemented`」，实现抛 `ProviderLaneError`（含 recovery）。语义等价、更贴合本项目异常族 |
| 4.5 constrained sampling | ⚠️ **偏离** | `complete_json` 用 `json_object` 而非 `strict=require`（D-O12-03）。**PLAN 原文已就地修订** |
| 4.6 auth 与重试 | ⚠️ 偏差 | ①无 `stored` 凭据层（项目无此概念）；②无 abort 语义（同步单发），`retryable` 承载分类 |
| S3.1「双 provider」 | ⚠️ 命名落差 | 实为**单端点双模型**。PLAN 正文允许「deepseek 双模型」，但标题写「双 provider」 |

---

## 3. 对抗性实验（实际运行，非推演）

| # | 攻击面 | 修复前 | 修复后 |
|---|---|---|---|
| E1 | `base_url` 尾部 `/` | PRICED ✓ | PRICED ✓ |
| E1 | `base_url` 带 `/v1` | **UNPRICED ❌** | PRICED ✓ |
| E1 | host 大小写不同 | **UNPRICED ❌** | PRICED ✓ |
| E2 | 模型不在目录 | UNPRICED（正确） | UNPRICED ✓ |
| E3 | `llm_base_url` 为空 | 抛笼统 `ProviderLaneError` | `LaneNotConfiguredError` + recovery ✓ |
| E4 | 显式空白凭据 | 接受 → 发无 auth 请求才 401 | 视同未提供 → fail closed ✓ |
| E5 | receipt 新字段 round-trip / 旧记录加载 | — | 相等 ✓ / 可加载 ✓ |
| E6 | 幂等指纹是否受 receipt 影响 | — | 不影响（只哈希 request）✓ |
| E7 | unpriced lane 是否编造价目 | — | 恒为 0 ✓ |

---

## 4. 钢人论证：反方最强理由 + 处置

> 按「反方辩手最强版本」写。**每条给出处置，而不是记录。**

### 4.1 反方：`complete_json` 违反 PLAN 明文 → **已就地修订 PLAN**

偏离成立且必要（无 schema ⇒ `require` 无语义；deepseek 不支持 strict ⇒ `require` 会让 `complete_json` 全线 fail-closed，推翻 S2.6 的「零破坏」验收）。已修订 PLAN §4.5 与 §4 决策 4 原文并标注原因——偏离可追溯，不是无声的。

### 4.2 反方：漂移校验与预算守卫是「带测试的死代码」，且文档撒谎 → **守卫已接线，漂移项保留为已知未接线**

`validate_lane_settings` 与 `check_call_budget` 在 `src/` 中曾无任何调用点，而 `LaneTransport` 文档声称「caps are enforced by the transport before dispatch」。不会执行的守卫 + 不成立的声明，比没有守卫更危险——下游会**以为**被保护。

处置：
- `LaneTransport.complete()` dispatch 前查 `max_calls_per_run`，事后累计 cost/tokens 并对 per-call 成本与 per-run token 上限 fail-closed（+3 测试）；
- 文档改为实际行为，并明写 per-call 成本只能事后判定（无 token 预估器）；
- **漂移校验仍无生产调用点**——settings 派生路径上 lane 与观测同源，没有漂移对象。已修订 PLAN 并标注为已知未接线项，补 `lane_drift_event` 工厂供将来持有冻结 preset lane 的消费方（A5/B6）使用。

### 4.3 反方：跨 lane 修改已 accepted 的 `capability_registry.py` → **已降低越界面，仍需复审确认**

v1 的处置是「请复审人表态」——这是把问题推给别人。v2 的做法：

- 把 `TokenUsage` / `InvocationCost` 的**定义**从 `invocation_contracts.py` 移到**共享 `contracts.py`**（该层明确由项目负责人维护），`invocation_contracts.py` 改为 re-export 保持向后兼容；
- 这样「新类型」不再是在 A 线文件里发明，而是落在共享契约层；
- `capability_registry.py` 的改动缩到最小：仅 import 共享类型 + 新增 2 个可选字段（默认 `None`）。

**残留**：那 2 个字段仍然落在 S3-A 的文件里，技术上仍是一次跨 lane 增量。我无法在满足 S2.5 的前提下消除它（A5 消费的正是这个 receipt）。**这一条仍需复审人确认**，但越界面已从「定义新类型」降到「引用共享类型 + 加可选字段」。

### 4.4 反方：retry 的成本与延迟没有被收口 → **已用 `attempts` 收口**

v1 处置是「转记录」。v2 的做法：

- `LaneResult.attempts` 记录为拿到结果一共发了几次请求；`LaneTransport` 在 dispatch 包装里计数；
- `InvocationCost.attempts`（默认 1，保证旧 receipt 仍合法）随 receipt 落地；
- 口径写明：失败的 retry 通常不计费，但 5xx 可能在 provider 已受理后返回，故 **`total × attempts` 是本次调用的成本上界**——这是可解释的估算，不再是空白。

延迟放大（失败时 +3.5s）是重试策略的固有代价，PLAN 明确要求重试分类，保留。

### 4.5 反方：「误差可解释」是自我定义的 → **实测：快照与官方价目不一致，最大偏差约 4.5×**

v1 说「官方价目对照不可得」。v2 真去抓了 DeepSeek 官方定价页（`api-docs.deepseek.com/quick_start/pricing`，2026-09-11 读取）：

| 模型 | 本项目 catalog 快照 | DeepSeek 官方 |
|---|---|---|
| `deepseek-v4-pro` input | $0.435 /1M | **$0.66**（off-peak）／**$1.32**（peak） |
| `deepseek-v4-pro` output | $0.87 /1M | **$1.98**／**$3.96** |
| `deepseek-v4-flash` input | $0.14 /1M | $0.15／$0.30 |
| `deepseek-v4-flash` output | $0.28 /1M | $0.60／$1.20 |

**三项结论**：

1. **偏差是系统性的，不是舍入误差**：`deepseek-v4-pro` 的 output 单价快照 $0.87 vs 官方 $1.98（off-peak）/ $3.96（peak），最高约 **4.5×**。
2. **结构差异**：官方已引入 **peak / off-peak 双档**（off-peak 为 peak 的一半），本项目的目录结构**只有单档**，无法表达该语义。
3. **模型生命周期已变**：官方文档称 `deepseek-v4-flash` 为 legacy 名（实际由 V4.1-Flash 服务），且 **2026-09-14 起 `deepseek-v4-pro` 将整体路由到 V4.1 Flash 并按其价目计费**。

**因此 S3.1 的「误差 0」只在「用我自己的价目算我自己的输入」这个自证口径下成立**——它证明计价器内部一致，**不证明**价格正确。反方是对的。

处置（v2）：
- `InvocationCost.price_source` 字段 + `ModelCatalog.price_source` 属性：每笔成本**必须**带出所依据的价目表与快照日期（如 `models.dev snapshot 2026-09-10`），让审计能回答「这个数字是按谁的价格算的」；
- `InvocationCost` / `receipt_usage_fields` 的文档明确写：**这是估算，不是 provider 账单**，快照可能滞后于公开价目；
- 本条**降级为「已机制化 + 已知限制」**：机制已就位，但快照与官方的偏差需要靠刷新脚本 + 定期对照来收敛，不能靠代码一次修好。

**v3 追加（Owner 拍板后落地）：**

- 口径定为 **tokens 为主、cost 为辅**：`tokens` 是事实（provider 返回），`cost` 是推断（本地折算）。纪律条款一律优先用 tokens 表达，cost 只在对外报数时引用且必须带 `price_source`。理由：预算纪律若建立在会过期的价目表上，等于没有纪律。
- 新增 **override 机制**（`src/autoresearch/data/price_overrides.json` + `ModelCatalog` 合并 + 按模型粒度的 `price_source`）：只覆盖**实际在用的模型**，不做全量同步；override 只替换已有条目的四档价目，指向未知条目时忽略而不崩溃。
- **内置模型按官方 peak 价钉住**：`deepseek/deepseek-v4-flash` → \$0.30 input / \$1.20 output / \$0.006 cache_read（来源 `api-docs.deepseek.com`，2026-09-11 核对）。取 peak 档是刻意保守——估算宁可高估不漏报。
- 政策与核对纪律落 `PRICE-POLICY.md`：人工核对（成本敏感实验前），不写官网爬虫。
- 计数器与来源的实测验证：`build_preset_lane("deepseek:chat:v1")` → cost `0.30/1.20/0.006`，`price_source = "override 2026-09-11 api-docs.deepseek.com"`；未覆盖的模型仍报 `models.dev snapshot 2026-09-10`。

---

## 5. 跨模块适配矩阵

| 关联模块 | 关系 | 判定 |
|---|---|---|
| `reader_writer_ports.py`（B4） | 薄缝消费其契约 | ✅ 零修改；`is` identity 断言；无新增 port 方法 |
| `capability_registry.py`（S3-A） | 引用共享类型 + 加 2 个可选字段 | ⚠️ 跨 lane 增量，越界面已最小化（4.3） |
| `capability.py` / `storage.py`（A1/A2） | receipt 持久化 | ✅ `model_dump_json` 兼容；新字段默认 `None`；旧记录可加载 |
| 幂等指纹（A1/A2） | 只哈希 request | ✅ 不受 receipt 新字段影响 |
| `orchestrator.py` / `writing_service.py` | `LLMService` 消费方 | ✅ `except Exception` 兜底；签名未变 |
| A5 Benchmark | 消费 receipt 计价字段 | ⚠️ 契约已冻结但未经真实消费；**成本是估算口径，A5 引用时必须带 `price_source`** |
| B6 Real Pilot | 消费 LLM 边界做交叉评审 | ✅ 可经 `LLMService` 或 `LaneLLMAdapter` |
| ADR-01 | 选型依据 | ✅ pi-ai 语义与目录许可（MIT）一致 |

---

## 6. 剩余风险（诚实清单）

1. **价目快照与官方价目系统性不符**（4.5，**最高优先级**）：最大偏差约 4.5×，且缺 peak/off-peak 结构。已机制化（`price_source`），但**收敛依赖定期对照**。在收敛前，任何对外承诺的成本数字都必须标注为估算。
2. **`normalize_usage_openai` 的语义假设**：假定 `prompt_tokens` 含 cache 命中（OpenAI/deepseek 成立）。**第三方兼容端点未验证**——WorkBuddy 端点本次未暴露该字段差异，不代表不存在。
3. **模型生命周期漂移**：官方已在弃用 `deepseek-v4-flash` 名、并将于 09-14 改路由 `deepseek-v4-pro`。刷新脚本不解决「模型被重定向到另一个模型」这类语义变化。
4. **`lane_drift_event` 无写入路径**（4.2）：事件形态已定义并锁定，但没有调用方把它写进审计链。
5. **`LLMService` 不跑漂移校验**：PLAN §4 决策 4 原文要求，已修订 PLAN 并标注原因，属**有意偏差**。
6. **重试的延迟放大**：失败路径多等 ~3.5s（策略固有，`attempts` 已使成本可解释）。
7. **无连接复用**：`LaneTransport` 未注入 client 时每次新建 `httpx.Client`。性能项。
8. ~~独立盲审缺席~~ → **v3 已执行**（第 8 节），其 4 项发现已全部修复。

---

## 7. 修复清单（v1/v2）

| 文件 | 变更 |
|---|---|
| `src/autoresearch/contracts.py` | `TokenUsage` / `InvocationCost` **定义迁入共享契约层**（4.3）；`InvocationCost` 增 `attempts`、`price_source`（4.4/4.5） |
| `src/autoresearch/invocation_contracts.py` | 改为 re-export 共享类型，删除本地定义（4.3） |
| `src/autoresearch/capability_registry.py` | 改从 `contracts` 引用共享类型（4.3） |
| `src/autoresearch/llm.py` | endpoint 规范化比较 + 按 model id 计价（F1）；空 settings 带 recovery（F2）；空白凭据 fail closed（F3）；透出 `price_source` |
| `src/autoresearch/provider_lane.py` | 预算守卫接线（G1）；`lane_drift_event`（G2）；`LaneResult.attempts` + 计数（4.4）；`ModelCatalog.price_source` + `LaneIdentity.price_source`（4.5）；文档改实 |
| `tests/test_llm_lane_replacement.py` | +5（endpoint 拼写、第三方端点计价、未知模型 unpriced、recovery、空白凭据） |
| `tests/test_provider_lane_transport.py` | +5（预算接线 3、重试计数 2） |
| `tests/test_provider_lane.py` | +1（drift 事件） |
| `tests/test_provider_lane_receipt.py` | +2（价目来源、attempts），字段集断言更新 |
| `docs/.../PLAN.md` | 修订 §4 决策 4 与 §4.5 的过时表述 |
| `src/autoresearch/data/price_overrides.json` | **v3 新增**：内置模型（DeepSeek V4.1 Flash）按官方 peak 价钉住 |
| `src/autoresearch/provider_lane.py` | **v3**：`ModelCatalog` 加载并合并 override，`price_source` 精确到模型粒度 |
| `docs/.../PRICE-POLICY.md` | **v3 新增**：三口径、override 规则、核对纪律、对下游的要求 |

验证（v2 时点）：`pytest -W error -q` → 254 passed, 2 skipped；`ruff check src tests` → clean；`check.mjs` → valid。**注：该计数漏记 1 个 `F`（见第 8 节）；v3 修复后的真实基线为 268 passed / 2 skipped。**

---

## 8. 独立盲审（v3）与修复

网络恢复后派出**不知情子代理**盲审「v2 之后的未提交增量」——只给仓库路径、审查范围与六个问题，不给任何实现意图。它独立提出 **4 项发现，与我的自查零重叠**，且全部落在**我这一轮新写的代码**上。

| # | 危级 | 发现 | 处置 |
|---|---|---|---|
| B1 | 中 | 只带 `note`、不带任何价目的 override 仍打 `override` 来源标签，而价格实际来自滞后快照 → **假来源**，恰好摧毁 `price_source` 存在的意义 | 只在**实际 patch 了 ≥1 档价目**时才打 override 标签（+1 测试） |
| B2 | 中 | 负数价目被静默写入目录，只有该模型被 lane 构建时才拒 → 一个永不构建的模型会**长期携带负价** | `_coerce_override_rate`：负数/NaN/±inf/非数值一律 `LaneCatalogError` fail-closed（+7 参数化测试） |
| B3 | 中 | 畸形 override（非 dict 条目、`models` 为 list、`"abc"` 价目）抛裸 `AttributeError`/`ValueError`，**炸掉整个离线目录**，与「未知条目忽略而非崩溃」的承诺矛盾 | 加载期显式 `isinstance` 校验 + 清晰错误（+4 参数化测试） |
| B4 | 低 | `if rate_field in entry` 对字符串条目是子串匹配 | 被 B3 的守卫一并覆盖 |

**它还戳破了一个我误报的事实**：一条我加的测试（F3 空白凭据 fail closed）在**我的开发机上实际是红的**——本机 shell 有 `DEEPSEEK_API_KEY`，空白 settings key 会回落到环境白名单并成功构造。我的计数脚本只数点阵（`.` / `s`）、**看不见 `F`**，于是上一轮报出的「254 passed 全绿」漏掉了一个失败。

处置：该测试改为 **monkeypatch 清环境**使其自包含，并**补一条反向断言**（环境里有 key 时应取用而非发空 Bearer）——把「环境耦合」变成**显式契约**；计数改用 summary 行 + 退出码。

override 三个缺陷我写完自己过了两遍没看出来，B4 部分更是我误报的——这是「独立性削弱」被真正补上的证据：**独立审查抓的不是我不够仔细，是我的盲区。**

---

## 9. 结论

v1 发现 6 项缺陷（5 修 1 文档化）；v2 把钢人论证里**三条「只记录未解决」的项真的处置掉了**，并且在处置过程中发现了一条 v1 刻意绕开的硬事实：

> **本项目 vendored 的价目快照与 provider 官方价目存在最高约 4.5× 的系统性偏差，且缺少 peak/off-peak 结构。**

这条比 v1 报告的任何一项都重要——因为它直接影响「成本可审计」这个产品叙事。机制（`price_source` + `attempts`）已就位，但**快照与官方的收敛不是一次代码修改能解决的**，需要定期对照与刷新纪律。

**请复审人优先攻击第 4.5 节（价目口径）与第 6 节第 1、2 条**——那是这份报告里唯一还没有闭合、且影响下游 A5 的部分。

**v3 追加**：独立盲审的 4 项发现（第 8 节）全部落在本轮新增的 override 机制上，已在推送前修复。修复后的真实基线为 **268 passed / 2 skipped（0 failed，`-W error` 口径）**、ruff clean、`check.mjs` valid、`check_pr_contract` passed。至此「独立性削弱」这个弱点已补齐——报告同时包含自查与独立盲审两路证据。
