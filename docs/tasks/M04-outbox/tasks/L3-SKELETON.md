# L-03 M04 L3 骨架（checkpoint 测试 / outbox / 迁移）

> **层级**：L3 骨架 —— **开工者必须把它补全成完整 L3 后再写代码**
> **上游权威**：R-007 `04-l2-contracts.md` **K9**（`OutboxEntry`）
> **原表**：M04-04（checkpoint 持久化测试）、M04-05（outbox + 幂等键）、M04-06（数据库迁移与兼容检查）
> **base_ref**：`main@8dd8780`（**实测 537 passed / 2 skipped / 0 failed**，本 worktree 自测）
> **排他文件**：`outbox.py`（**只新建这一个，不改 `storage.py`**）

---

## 🔴 0. 本包最重的一条硬约束

**不得改 `storage.py`。** 理由是 R-007 明列的全局串行点：

| 文件 | 占用方 | 本包怎么做 |
|---|---|---|
| **`storage.py`** | **L-06**（`transaction()`） | **不改** —— `OutboxEntry` 用 `RecordStore.put("outbox", ...)`，幂等靠**唯一约束** |

> 实测：`storage.py` 现 443 行，`knowledge.py` 205 行，均属 L-06 的写入路径。
> **本包若改 `storage.py`，会与 L-06 直接撞车**（R-007 三次事故中就有一次是这类）。

---

## 1. Task source

| 子任务 | 原表要求 | 本包契约 |
|---|---|---|
| **M04-04** | checkpoint 持久化：进程退出→重启→同 thread 恢复 | 不变量 **I7** |
| **M04-05** | outbox + 幂等键：「retry/resume 不重复写库/知识/实验/通知/发布」 | **K9** |
| **M04-06** | 数据库迁移与兼容：空库/旧库/部分失败可回滚；schema version 可审计 | **I7** 的持久化面 |

---

## 2. 必须落地的契约

### K9 `OutboxEntry`

**字段**：`outbox_id` / **`idempotency_key`（唯一约束）** / `effect_kind`（`knowledge_write`|`experiment_run`|`notification`|`publish`）/ `payload_ref`（**引用，非内联**）/ `status`（`pending`|`delivered`|`failed`）/ `attempts`（默认 0）/ `created_at` / `delivered_at`

| # | 不变量 | 可校验 |
|---|---|---|
| K9-1 | **`idempotency_key` 唯一** —— 重复投递被拒 | ✅ 唯一约束 |
| K9-2 | **`payload_ref` 是引用**，不内联 | ✅ |
| K9-3 | **`attempts` 有上限**；超限转 `failed`（**不无限重试**） | ✅ 计数器 |

> **K9-1 是本包的核心判据**：I7「resume/retry 不重复副作用」靠它落地。
> 负例必须断言「**重复投递被拒且副作用只发生一次**」，
> 而不是断言「`attempts == 1`」这类计数型断言（那是「缺失记成正常值」的同族）。

---

## 3. 复用既有原语（**不得重造**）

R-007 明确点名了一个反例（`05-execution-plan.md` §5 纪律 1 的同族）：

> **新模块绕过仓库现成原语 = 新缺陷的根源。**
> 实证：sink 曾自造一阶段 marker，而 A1/A2 早有 `reserve → mark_phase → finalize` 两阶段语义。
> **「照搬语义」≠「复用原语」** —— 判据是**代码里有没有出现那个机制的 API 名**。

**本包要求**：
1. **开工第一步**：实测仓库既有的幂等原语（`RecordStore` 的幂等接口、`storage.py` 的 `transaction()`）
   —— **列出 API 名、签名、行号**，写进 L3 的「复用既有」节。
2. 若 `transaction()` 不可用（属 L-06 的路径），**在 `outbox.py` 内用 `RecordStore` 的既有接口**，
   **不得自己实现一套事务/标记机制**。
3. L3 的验证节必须能**指认调用点**（哪个函数调了哪个既有 API）。

> ⚠️ 若开工时发现既有原语确实不够用，**不要静默自造** ——
> 登记为 Contract deviation 并在 PR 里请 owner 裁决。

---

## 4. 负例（**开工者补全**）

| # | 负例 | 断言什么 |
|---|---|---|
| **N-1** | 同一 `idempotency_key` 投递两次 | **第二次被拒**，且**外部副作用只发生一次**（不是断言计数） |
| N-2 | `attempts` 超上限 | 转 `failed`，**不再重试** |
| N-3 | `payload_ref` 指向不存在的 payload | **可观测的失败**（不是静默通过） |
| **N-4** | 部分失败（写了一半） | **可回滚**且状态可审计（M04-06） |

> **N-1 的断言写法**：断言「**副作用发生次数 == 1**」是**正确的**；
> 断言「`attempts == 1`」是**错误的**（那测的是计数器不是幂等语义）。

---

## 5. Deliberate non-goals

- **不改 `storage.py`**（见 §0）。
- **不做** M15-05 备份恢复演练（依赖本包的 M04-06，但本轮不开）。
- **不碰** `knowledge.py` / `contracts.py` / `evolution_service.py`。

---

## 6. 判别力 / 验收 / 偏离

```bash
PYTHONPATH=src python -m pytest tests/test_m04_*.py -q -o addopts="" -W error
PYTHONPATH=src python -m pytest -q -o addopts="" -W error    # 基线 537 passed 不得下降
ruff check src tests && compileall -q src
node .ai-team/check.mjs --base main
```

**并发缺陷特别注意**（R-007 §5 纪律 1 的同族教训）：
- **幂等/并发缺陷不可用天然竞态做证据** —— GIL 下窗口太窄。
- **必须插桩**（monkeypatch 在 check 与 inc 之间强制切走）才能取得确定判据。
- 无插桩的并发测试**只能当回归护栏**，docstring 要写明它**无判别力**。
