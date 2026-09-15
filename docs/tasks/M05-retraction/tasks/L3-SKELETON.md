# L-04 M05 L3 骨架（撤稿 / OA / 许可检查）

> **层级**：L3 骨架 —— **开工者必须把它补全成完整 L3 后再写代码**
> **上游权威**：R-007 `04-l2-contracts.md` **K10**（`RetractionStatus`）
> **原表**：M05-06（撤稿、更正、OA 和许可检查）
> **base_ref**：`main@8dd8780`（**实测 537 passed / 2 skipped / 0 failed**，本 worktree 自测）
> **排他文件**：`retraction.py`（**新建**）+ `external_sources.py`（**扩展**）

---

## 0. 本包是「扩展」不是「新建」（**实测确认**）

**`external_sources.py` 已存在，实测 673 行**（本 worktree `wc -l` 实测，与 R-007 L1 §5 声称一致）。

> ⚠️ **这是 L-07 踩过的坑**：R-007 L1 §5 初版把 `evolution_service.py`/`profile_service.py`
> 标为 L-07「**新建**」排他文件，实测二者**已存在**且被多处读取 → **"排他文件"论据失效**，
> 被第 1 关审查 B2 判为真缺陷。
>
> **本包不要重犯**：改 `external_sources.py` 前，**先列出它的下游读取方并逐个检查**
> （R-007 §3「文件面检查必须配语义耦合检查」）。**这是本包开工的第 2 步。**

---

## 1. Task source

| 子任务 | 原表要求 | 本包契约 |
|---|---|---|
| **M05-06** | 「撤稿、更正、OA 和许可检查」；正：OA/授权/不可用三态可区分；负：**拒绝绕过付费墙** | **K10** |

---

## 2. 必须落地的契约

### K10 `RetractionStatus`

```python
class RetractionStatus(StrEnum):
    ACTIVE = "active"           # 未撤稿、未更正
    RETRACTED = "retracted"
    CORRECTED = "corrected"     # 有更正但未撤稿
    UNAVAILABLE = "unavailable" # 无法获取（网络/权限）
```

| # | 不变量 | 可校验 |
|---|---|---|
| **K10-1** | **`UNAVAILABLE` ≠ `ACTIVE`** —— 不可用**不得当作「正常」** | ✅ |
| K10-2 | `RETRACTED` 必须触发 **K8 传播** | ✅ |
| K10-3 | 判据**复用 B5 的 `updated-by[]`** | ✅ |

> 🔴 **K10-1 是本包的核心判据，直击本项目最顽固的缺陷族**：
> **「退化路径上把未知/失败记成正常值」**。
> 「取不到」与「确认未撤稿」**是两个不同的结论**，不得坍缩。
>
> 负例必须断言：「网络不可用/权限不足时 → `UNAVAILABLE`」，
> **而不是**断言「返回了 `ACTIVE`」或「没崩」。

---

## 3. 复用既有（**不得重写**）

**B5 已实现撤稿判据 `updated-by[]`**（PR #17，`7fdfb89`，**真实验收**）。

> **关键历史（必须知道，否则会重犯）**：B5 的**任务包规格本身**曾把判据写反 ——
> 读的是 `update-to[]`，导致「被撤稿的论文判 `found`、撤稿声明判 `retracted`」方向反转。
> owner 深审时用**真实 API payload 复核**才确认。修复中另发现 `resolver_record()`
> 对 `not_found` 的 fail-open（**成员原版即有，owner 两轮自查漏报**，由独立盲审抓出）。
>
> **教训**：撤稿判据的**字段方向**必须用**真实 payload** 验证，不能靠推理；
> 且 **`not_found` 路径必须 fail-closed**（不得 fail-open）。

**本包要求**：
1. **开工先读 `external_sources.py` 里 B5 的既有实现**，确认 `updated-by[]` 的读取点行号。
2. **复用，不重写** —— 若发现既有实现有问题，登记 deviation，**不静默改动**。
3. **许可策略分工**（R-007 明文）：
   - **本包管「怎么判定」**（撤稿/OA/许可的事实判定）
   - **L-09 的 `licensing.py` 管「策略与门禁」**
   → 不要越界实现策略层。

---

## 4. 负例（**开工者补全**）

| # | 负例 | 断言什么 |
|---|---|---|
| **N-1** | 网络不可用 / 权限不足 | 返回 **`UNAVAILABLE`**（**不是 `ACTIVE`**） |
| N-2 | `RETRACTED` 的论文 | **确实触发 K8 传播**（不是只标记状态） |
| **N-3** | 试图绕过付费墙 | **被拒**（原表明文「拒绝绕过付费墙」） |
| N-4 | 真实 payload 的字段方向 | 用**真实录制 payload** 断言方向正确（防 B5 式反转） |

> **N-4 是本包的特有要求** —— B5 的教训是「纯读文档看不出方向错」。

---

## 5. Deliberate non-goals

- **不重写** B5 的撤稿判据。
- **不实现**策略/门禁层（那是 L-09 的 `licensing.py`）。
- **不碰** `search_service.py`（R-007 §5 列为 L-04 的禁止触碰项）。
- **不新建** `external_sources.py`（它是**扩展**）。

---

## 6. 判别力 / 验收 / 偏离

```bash
PYTHONPATH=src python -m pytest tests/test_m05_*.py -q -o addopts="" -W error
PYTHONPATH=src python -m pytest -q -o addopts="" -W error    # 基线 537 passed 不得下降
ruff check src tests && compileall -q src
node .ai-team/check.mjs --base main
```

**离线可用性**：本包的测试**必须离线可跑**（真实 API 调用不得进入测试路径；
真实 payload 用 fixture 录制）。
