# O12 计价口径政策（PRICE-POLICY）

- 日期：2026-09-11
- 适用：O12 ProviderLane 及其下游（A5 benchmark、B6 real pilot、I 线交付）
- 决议：Owner 2026-09-11（三口径 / 只覆盖内置模型 / peak 档 / 人工核对）

---

## 1. 三口径（结论先行）

| 口径 | 字段 | 性质 | 默认 | 用途 |
|---|---|---|---|---|
| **token 用量** | `tokens.{input,output,cache_read,cache_write,reasoning}` | **事实**（provider 响应） | **必填，主口径** | 预算纪律、用量审计、跨轮次比较 |
| 成本估算 | `cost.{input,output,cache_read,cache_write,total}` + `price_source` + `attempts` | **推断**（本地价目折算） | 可选；未命中价目即 `None` | 对外报数字、成本上限告警 |
| 账单对账 | provider billing / 后台账单 | 事实 | 不入 receipt | 事后抽查 |

**纪律条款一律优先用 tokens 表达。** 例如「固定调用预算」应写成「每轮 ≤ N tokens」，而不是「每轮 ≤ $X」——钱依赖一张会过期的价目表，tokens 不依赖。

**cost 只在需要对外报数时引用，且必须带 `price_source`。** 任何对外承诺的数字都要能回答「按谁的价格算的」。

## 2. 为什么不追实时价目

三条路都试过或评估过：

| 方案 | 问题 |
|---|---|
| models.dev 聚合（快照来源） | 会滞后。实测 2026-09-11：`deepseek-v4-pro` 输出价快照 \$0.87 vs 官方 \$1.98/\$3.96，**差约 4.5×**；且无 peak/off-peak 结构 |
| 各家官网爬虫 | 每家页面结构不同、无 API、随时会碎；本项目在用的 provider 只有一两个，写 6 个解析器不划算 |
| provider billing API | 是真账单不是价目表，覆盖窄、有延迟 |

另有一个更硬的理由：本项目跑真实调用的 `workbuddy2api.henryai.top` 是**第三方转发端点**，其计费价目既非官方价、也不在 models.dev 里，**官网查不到**。这类端点只能标 unpriced——这不是缺陷，是诚实。

## 3. override 机制（规则）

文件：`src/autoresearch/data/price_overrides.json`

规则：

1. **只覆盖、不新增**。override 只替换**已存在**的目录条目的四档价目；指向未知条目的 override 被忽略（不崩溃、不凭空造模型）。
2. **只覆盖在用的模型**。不做全量同步——每多覆盖一个，就多一处会过期的数据。
3. **必须带来源**：`source`（页面 URL）、`source_host`、`checked_at`、`note`。
4. **加载即合并**，`price_source` 按模型粒度标注：
   - 被覆盖 → `override <checked_at> <source_host>`
   - 未覆盖 → `models.dev snapshot <fetched_at>`
5. 快照刷新（`scripts/refresh_model_catalog.py`）**不影响** override；两者独立。

## 4. 核对纪律

- **人工核对**，不写爬虫。核对时机：
  - 成本敏感实验（A5 跑分、B6 试点）开始前；
  - provider 发布价格变更公告时；
  - 距上次核对超过一个季度时。
- 核对动作：打开 provider 官方定价页 → 对比 `price_overrides.json` 当前值 → 更新 `checked_at` 与数值 → 记 `note`。
- 核对结果**必须如实**：涨价就改高，降价就改低；查不到就标 unpriced，不要猜。

## 5. 当前生效的 override（2026-09-11）

| 目录键 | input | output | cache_read | 来源 |
|---|---|---|---|---|
| `deepseek/deepseek-v4-flash` | \$0.30 | \$1.20 | \$0.006 | `api-docs.deepseek.com/quick_start/pricing`（peak 档） |

依据与说明：

- 本项目**内置模型就是 DeepSeek V4.1 Flash**；`deepseek-v4-flash` 是官方仍接受的 legacy 别名，**实际由 DeepSeek-V4.1-Flash 服务、按 Flash 价计费**，故不必改模型名。
- **取 peak 档**（off-peak 为半价：\$0.15/\$0.60/\$0.003）。理由：估算成本宁可高估不漏报，超预算告警才有意义。该选择记录在 `_meta.pricing_basis`。
- 快照原值 \$0.14/\$0.28，与官方 output 价差 **约 4.3×**。

## 6. 对下游的要求

- **A5**：评估纪律中的「固定调用预算」以 **tokens** 为主口径写；引用 cost 时必须带 `price_source`，且理解其为**估算**而非账单。
- **B6**：交叉评审的双模型对比，优先比 tokens 与结论差异；若比成本，需声明价目基准。
- **任何对外材料**：不得把 `cost` 表述为「实际花费」，应表述为「按 <价目表> 估算」。

## 7. 已知限制（诚实清单）

1. override 是**人工维护的数据**，会过期；本政策不提供自动保鲜，只提供可追溯性。
2. peak/off-peak **双档在目录结构中不可表达**，只能按单一档位记录（当前取 peak）。
3. provider 可能**变更模型路由**（如官方公告 `deepseek-v4-pro` 自 2026-09-14 起整体路由到 V4.1 Flash），这类语义变化刷新脚本无法发现，只能靠人工核对时发现。
4. 第三方转发端点**无从查证价目**，只能 unpriced。
