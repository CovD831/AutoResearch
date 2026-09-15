# L-09 M14+M15 L3 骨架（ACL / PII / 许可 / telemetry）

> **层级**：L3 骨架 —— **开工者必须把它补全成完整 L3 后再写代码**
> **上游权威**：R-007 `04-l2-contracts.md` **K11**（`AccessPolicy`）+ **K12**（`SensitivityClass`）+ **K13**（`TelemetryPoint`）
> **原表**：M14-03/04/05（ACL / PII / 许可）+ M15-02/04（日志脱敏 / 指标告警）
> **base_ref**：`main@8dd8780`（**实测 537 passed / 2 skipped / 0 failed**，本 worktree 自测）
> **排他文件**：`acl.py` `pii.py` `licensing.py` `telemetry.py`（**全部新建**）

---

## 0. 本包分两批（**这是唯一的顺序约束**）

| 批 | 子任务 | 文件 | 依赖 |
|---|---|---|---|
| **前半（本 worktree 可立即开工）** | M14-03 ACL / M14-04 PII / M14-05 许可 | `acl.py` `pii.py` `licensing.py` | **无** |
| **后半（等 K1/K13）** | M15-02 日志脱敏 / M15-04 指标告警 | `telemetry.py` | **K13 依赖 L-05 的 K1** |

→ **建议**：本 worktree 先做前半（3 个文件），`telemetry.py` 待 L-05 冻结 K1 后再做。
**这与 R-007 §2 的批次一致**（L-09 前半在第 2 批，后半在第 3 批）。

---

## 1. 三个契约

### K11 `AccessPolicy`（M14-03）

**字段**：`subject` / `resource_kind`（`project`|`partition`|`artifact`）/ `resource_id` / `actions`（`read`/`write`/`export`/`delete`）/ `granted`

| # | 不变量 | 可校验 |
|---|---|---|
| **K11-1** | **默认拒绝**（无策略 = 不可读） | ✅ |
| K11-2 | **越权必须可观测**（**不得静默返回空**） | ✅ |
| K11-3 | `export` / `delete` 需更高门槛 | ✅ |

> **实测**：`\bACL\b` = **0 行** → **完全从零建**。
> ⚠️ **存在性盘点必须用词边界**：`grep -niE "\bACL\b"`，**不是** `grep -i acl`
> （会被 `dataclasses` 误匹配 —— 本项目踩过）。

### K12 `SensitivityClass`（M14-04）

```python
class SensitivityClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"   # 禁止进入 embedding / 外部模型
```

🔴 **生效阶段标注（强制）**：

| 不变量 | 当前状态 | 标注 |
|---|---|---|
| `SENSITIVE` 禁 embedding | **空约束** —— **实测仓库无任何 embedding/向量实现** | **`【向量落地后生效】`** |

> **纪律（R-007 §5）**：**禁止为它写「通过」断言** —— 那会造出恒真假绿（R-006 §11.8 的教训）。
>
> **正确的做法**：字段与枚举**先落地**（参考 R-006 C6 的做法），
> 在 docstring 与 L3 里**显式标注生效阶段**，测试只覆盖**当前可违反的部分**
> （如「`export`/`delete` 可追溯」）。

### K13 `TelemetryPoint`（M15-02/04）

**字段**：`metric`（`blocked`/`denied`/`retry`/`latency_ms`/`cost_usd`）/ `dimensions`（project/run/node/agent/gate）/ **`value`（`float | None`，`None` = 未测）** / `threshold` / `redacted`

| # | 不变量 | 可校验 |
|---|---|---|
| **K13-1** | **`value=None` 表示未测，绝不用 0 代替** | ✅ |
| **K13-2** | **`cost_usd` 未命中价目时为 `None`**（TASK-SPECS:63 明文） | ✅ |
| K13-3 | **不得记录 prompt / 全文 / token / secrets**（`redacted=True` 且不含原文） | ✅ 正则扫描 + 字段白名单 |
| K13-4 | 超阈值触发 interrupt | ✅ |

> 🔴 **K13-1/K13-2 是本项目的血泪条款**：
> **凡 `except ...: return <正常值>` 处，必须有断言该退化路径结果正确的测试。**
> 实证：O12 `_recurrence_count`/usage 缺失；PR #20 `except: return 0`
> 使 `recurrence_count` 坍缩致 promotion 门槛**静默永不通过**。
>
> → **负例必须断言「未测得时 `value is None`」**，而**不是**断言「`value == 0`」。

**与 O12 ProviderLane 的对齐**：成本指标必须复用 **`price_source` + `attempts`** 口径；
**未命中价目一律 `None`，绝不用 0**（`docs/PRICE-POLICY.md` 全文）。

---

## 2. 复用既有（**不得重造**）

- **M15-02 的日志脱敏**：既有 `application.py` 的 `doctor()` 是现成健康检查雏形
  → **扩展它，不要另建**（R-007 原表述）。
  ⚠️ **开工时先实测 `application.py` 的行号与 `doctor()` 签名**，再决定扩展边界。
- **成本口径**：复用 O12 的 `price_source` / `attempts`（**实测 `provider_lane.py` 已实现**）。

---

## 3. 负例（**开工者补全**）

| # | 负例 | 断言什么 |
|---|---|---|
| **N-1（ACL）** | 无策略访问 | **默认拒绝**；**越权可观测**（不是静默空列表） |
| **N-2（PII）** | `value=None`（未测） | **`value is None`** —— **不得被补成 0** |
| **N-3（telemetry）** | `cost_usd` 未命中价目 | **`None`** —— **绝不用 0** |
| N-4（脱敏） | 尝试写入 prompt/全文/secrets | **被拒或被脱敏**（不得落盘原文） |
| N-5（许可） | 绕过付费墙 | **被拒**（与 L-04 的判定层分工：本包管**策略**） |

---

## 4. 与 L-04 的分工（**不得越界**）

| | L-04 `retraction.py` / `external_sources.py` | **本包 `licensing.py`** |
|---|---|---|
| 管什么 | **怎么判定**（撤稿/OA/许可的**事实**判定） | **策略与门禁**（谁能看/导出/删除） |

---

## 5. Deliberate non-goals

- **不实现** embedding / 向量（仓库无此能力，K12 是空约束）。
- **不实现** M15-05 备份恢复（依赖 M04-06）。
- **不碰** `storage.py` / `knowledge.py` / `contracts.py` / `provider_lane.py`。

---

## 6. 判别力 / 验收 / 偏离

```bash
PYTHONPATH=src python -m pytest tests/test_m14_*.py tests/test_m15_*.py -q -o addopts="" -W error
PYTHONPATH=src python -m pytest -q -o addopts="" -W error    # 基线 537 passed 不得下降
ruff check src tests && compileall -q src
node .ai-team/check.mjs --base main
```
