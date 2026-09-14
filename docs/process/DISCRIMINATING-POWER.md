# 判别力口径（全项目要求）

> owner 裁决 2026-09-11（PLAN-capability-metadata §0.1 第 7 条）：**判据型失败计入证据，符号缺失型失败不计入。**
>
> 适用：任何以「新增测试」作为修复/新增有效性证据的改动。

## 问题

新测试在旧代码上失败，常被当作「这个测试抓得住缺陷」。但失败有两种，价值天差地别：

| 类型 | 表现 | 证明什么 |
|---|---|---|
| **判据型** | 旧代码**允许**了不该允许的事：`DID NOT RAISE`、或对旧行为的值断言不符 | 规则**真的生效**了 |
| **符号缺失型** | `ImportError` / `AttributeError` / `KeyError`——新符号在旧代码上不存在 | 只证明**符号存在** |

典型误报：`pytest.raises(CapabilityManifestInvalidError)` 在旧代码上确实"失败"了，但失败原因是 `ImportError`——**一个断言都没跑**。若模块在 import 期就死，**整个文件的测试全部不可作为证据**。

## 测量方法（必做）

在基线 commit 上建 detached worktree，拷入新测试，注入**符号 shim**，再跑：

```bash
git worktree add /tmp/<probe> HEAD --detach
cp tests/<new_test>.py /tmp/<probe>/tests/
mkdir -p /tmp/<probe>/tests/fixtures/<...> && cp -r tests/fixtures/<...>/* /tmp/<probe>/tests/fixtures/<...>/
```

shim（`tests/_<probe>_shim.py`，只存在于探针 worktree）：把本改动**新增的符号**以惰性桩补到旧模块上，让测试模块能被 collect：

```python
import autoresearch.<module> as _m
if not hasattr(_m, "<NewError>"):
    class _Shim(_m.<ExistingBaseError>): pass
    _m.<NewError> = _Shim
if not hasattr(_m, "<new_func>"):
    _m.<new_func> = lambda *a, **k: []      # 惰性桩：不做任何事
```

以 `-p` 在 collection 之前加载（**这是关键**，`conftest` 里的普通 import 不够）：

```bash
PYTHONPATH=src:tests python -m pytest -p _<probe>_shim -o addopts="" -q --tb=line -rf tests/<new_test>.py
```

按异常类型分类：`DID NOT RAISE` / `AssertionError` → **判据型**；`AttributeError` / `KeyError` / `ImportError` → **符号型**。

**shim 会污染分类**：若 shim 把新属性补成了空值（如 `overridden_fields = ()`），一个本质是符号型的用例会表现为 `assert () == (...)`。**这类必须人工判回符号型**，不得计入判据型。

## 记录要求

账本的 `Verification` 必须**分开列两类**，并给出：

1. 探针用的基线 commit（本 commit 实测，**不得跨 worktree 搬运**）；
2. 判据型 N 例（计入）与符号型 M 例（不计入）；
3. 至少一条**可直接重跑的旧行为复现**（如「旧代码下该 manifest 注册成功且存储值被覆盖为空」）；
4. shim 导致的分类修正说明。

## 反例（本项目已发生）

- **O12/ProviderLane**：修复前连 `DEFAULT_MAX_CALLS_PER_RUN` 等符号都不存在，必须写 `/tmp` shim 注入后才拿到逐条结论。当时 16 个新测试中 12 个在修复前失败。
- **O13/CapabilityManifest**：16 failed / 8 passed；其中 10 例判据型、6 例符号型（含 2 例被 shim 伪装成判据型，已判回）。核心判据型证据 = 「`network_required=True` + 空白名单」在旧代码上**注册成功**。

## 附带纪律

- **测试计数**：`addopts` 会吃掉 summary → 用 `-o addopts=""`，并配合 `-W error`。
- **基线数字不得跨 worktree 引用**：`main` 与「`main` + 某分支」的计数不同（本项目曾把 413 误当 main 基线，实测为 275）。
- **`grep` 的 BRE `\|` 交替在本环境静默返回空**——会被误读成「文件里没有」。一律用 `Grep` 工具或 `grep -E`。
