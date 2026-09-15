# L-09 M14+M15 验证记录（原始输出）

环境：`/Users/abab/.workbuddy/binaries/python/envs/default/bin/python`，worktree `r007-l09-security`，
base `main@8dd8780`，日期 2026-09-15。

> **计数口径**：只抄 **summary 行 + 退出码**，不用点阵计数
> （`deliverable-verification-discipline`：点阵不可数、`-q` 的点数易被误读）。
> 每条命令同时记 `collected`（运行数）与 `passed/skipped`（结果），避免把「107 条用例」写成「106 条测试」。

---

## 1. 开工基线（本 worktree 自测，未搬运他人数字）

```
$ PYTHONPATH=src <python> -m pytest -q -o addopts="" -W error
........................................................................ [ 13%]
...
537 passed, 2 skipped in 27.04s
EXIT=0
```

## 2. 任务卡原命令（M14 + M15 glob）

```
$ PYTHONPATH=src <python> -m pytest tests/test_m14_*.py tests/test_m15_*.py -q -o addopts="" -W error
..........................s........                                      [100%]
106 passed, 1 skipped in 0.28s
EXIT=0
```

> **D-L09-05 的收尾**：开工时 `test_m15_*` 尚无文件、该 glob 会让 pytest 直接报错（exit 4），
> 当时只能实跑 `tests/test_m14_*.py`（55 → 56 passed）。后半交付后**原命令已可全跑**，上为其读数。

本包用例分布（逐个 `--collect-only` 实测）：

```
$ for f in tests/test_m14_acl.py tests/test_m14_pii.py tests/test_m14_licensing.py tests/test_m15_telemetry.py; do
    PYTHONPATH=src <python> -m pytest "$f" --collect-only -q -o addopts="" | grep -oE '[0-9]+ tests? collected'
  done
tests/test_m14_acl.py => 21 tests collected
tests/test_m14_pii.py => 19 tests collected
tests/test_m14_licensing.py => 16 tests collected
tests/test_m15_telemetry.py => 51 tests collected       # 其中 1 条为 K1 联调（见 §9）
```

| 文件 | 用例数 |
|---|---|
| `tests/test_m14_acl.py` | 21 |
| `tests/test_m14_pii.py` | 19（含 `parametrize` 展开） |
| `tests/test_m14_licensing.py` | 16（含 `parametrize` 展开） |
| `tests/test_m15_telemetry.py` | 51（含 `parametrize` 展开、1 条 K1 联调） |
| 合计 | **107**（106 passed + 1 skipped）✅ 与 §2 的 summary 行一致 |

## 3. 全量（基线不得下降）

```
$ PYTHONPATH=src <python> -m pytest -q -o addopts="" -W error
......................................................................   [100%]
643 passed, 3 skipped in 25.98s
EXIT=0
```

- passed：`537 → 643`（**+106，未下降**）
- skipped：`2 → 3`。**多出的 1 条是本包有意的 skip** —— `test_interop_with_the_real_k1_run_manifest`
  在 K1（`autoresearch.run_manifest`）不在本 worktree 路径上时 **skip**，而不是伪造一个 pass。
- `0 failed`。

## 4. 静态门禁

```
$ <python> -m ruff check src tests
All checks passed!
EXIT=0

$ <python> -m compileall -q src
ok
EXIT=0
```

## 5. 仓库门禁

```
$ <python> scripts/check_pr_contract.py --base main
PR contract check passed: 0 changed paths; 0 task ledger(s)
EXIT=0
```

> `0 changed paths` 是**本地全部改动尚未提交**（本包禁止 `git commit`）的正常读数；
> 提交后该数字才非零。如实记录，不解读为「零改动」。

```
$ node .ai-team/check.mjs --base main          # 建成员账本之前
Code progress from main: 0 commits, 14 files, +78/-11
Result: blocked
- Code or product files changed without updating .ai-team/TASK.md or a member ledger under .ai-team/tasks/ in the same PR

$ node .ai-team/check.mjs --base main          # 落盘 .ai-team/tasks/M14-15-SECURITY.md 之后（后半交付完成后复查）
Code progress from main: 0 commits, 18 files, +78/-11
Result: valid
```

> 两次读数之间文件数从 14 增至 18（`telemetry.py` + `test_m15_telemetry.py` + 两份 evidence 在同一次工作包内落地），
> 这是**同一批未提交改动**的两次快照，不是两次不同的提交。

（`node` = `/Users/abab/.workbuddy/binaries/node/versions/22.22.2-2/bin/node`）

## 6. 判别力（变异注入）

见 `mutation-check.md`（**17/17** 变异点「变异前绿 / 变异后红」，失败类型全部**判据型**）。

其中两处变异点对应**自审发现的真实问题**：

- **M10** —— K11-3 的 justification 原按「策略行」存，为 `export` 写的理由会顺带覆盖事后被加宽进来的 `delete`。
  已改为**逐动作**存，补用例 `test_a_justification_covers_only_the_action_it_was_written_for`；M10 把逐动作查找退化回行级查找，该用例即红。
- **M12/M16** —— K13 的两条血泪条款（未定价的 `cost_usd` 记成 `0.0`；未测的阈值判定记成 `False`）。

人工复核的**原始失败行**（不依赖脚本分类器）：

```
# M5：把「未测」记成 0（PII 扫描）
tests/test_m14_pii.py:117: in test_unmeasured_scan_keeps_none_not_zero
    assert result.value is None
E   AssertionError: assert 0 is None

# M2：越权时静默返回空列表
tests/test_m14_acl.py:188: in test_readable_resources_raises_for_an_unknown_subject_not_empty_list
    with pytest.raises(AccessDenied) as excinfo:
E   Failed: DID NOT RAISE AccessDenied

# M12：未命中价目的 cost_usd 被补成 0.0（N-3）
tests/test_m15_telemetry.py:113: in test_unpriced_cost_is_none_never_zero
    assert point.value is None
E   AssertionError: assert 0.0 is None

# M16：未测的阈值判定被读成「合格」
tests/test_m15_telemetry.py:253: in test_threshold_with_an_unmeasured_value_is_a_gap_not_a_pass
    assert point.breaches_threshold is None
E   AssertionError: assert False is None
```

变异后均还原；脚本内置还原 + 逐文件比对，事后 `git status` 复核一致（§8）。

## 7. 空约束（K12①）的标注状态 —— **没有被写成「通过」断言**

```
$ grep -rniE "embedding|vector|faiss|chromadb|sentence_transformers" src | wc -l
11          # 全部误报：contracts.py:159 的 VECTOR 枚举值（自带【P4 后生效】、不可达）
            # + 其注释 + data/models_catalog.json 的 9 行**价目表数据**
```

- 全仓**无**向量存储 / embedding 调用点 / 相似度检索 → K12① 确为空约束。
- `pii.DEFERRED_INVARIANTS["K12.SENSITIVE_FORBIDS_EMBEDDING"]` 登记生效阶段（`MappingProxyType`，不可变 + 有测试断言其不可变）。
- 唯一相关测试守卫的是**标注字符串仍在**，其 docstring 明写「**这不是不变量的证据**」；
  另有一条 tripwire 断言本模块**无 embedding/vector API**（生效条件是否触发）。**没有任何恒真假绿。**

## 8. 工作区状态（无残留变异、无越界改动）

```
$ git status --short
 M docs/rearchitecture/R007-parallel-modules/04-l2-contracts.md     # 开工前既有的未提交改动，非本包
 M docs/rearchitecture/R007-parallel-modules/06-dispatch-sheet.md  # 同上
 M docs/rearchitecture/R007-parallel-modules/README.md             # 同上
?? .ai-team/tasks/M14-15-SECURITY.md                               # 本包账本
?? docs/rearchitecture/R007-parallel-modules/07-lane-kickoff-convention.md   # 同上（开工前即存在）
?? docs/tasks/M14-15-security/                                     # 本包（L3 + evidence）
?? src/autoresearch/acl.py                                         # 本包
?? src/autoresearch/licensing.py                                   # 本包
?? src/autoresearch/pii.py                                         # 本包
?? src/autoresearch/telemetry.py                                   # 本包
?? tests/test_m14_acl.py                                           # 本包
?? tests/test_m14_licensing.py                                     # 本包
?? tests/test_m14_pii.py                                           # 本包
?? tests/test_m15_telemetry.py                                     # 本包
```

- **硬禁区零改动**：`git status --porcelain` 对 `storage.py` / `knowledge.py` / `contracts.py` / `provider_lane.py` 输出 **0 行**。
- `application.py` **未改**（D-L09-07 / S-6 等 owner 裁决）。
- `__pycache__` 已被 `.gitignore:3` 覆盖，无编译残留入版本库。

## 9. K1 互操作实证（**不是「合并后应该能用」**）

K1（`run_manifest.py`）当前只存在于 L-05 的 worktree（untracked），本 worktree 与 main 都没有。
为验证「`dimensions["run"]` 真的取 `RunManifest.run_id` 而不是自造标识」，把 L-05 的文件软链进一个**临时合并包**后实跑：

```
$ MERGED=/tmp/l09-k1-merged
$ mkdir -p $MERGED/autoresearch
$ for f in src/autoresearch/*; do ln -s "$PWD/$f" "$MERGED/autoresearch/$(basename $f)"; done
$ ln -sf /Users/abab/Documents/ChatGPT/autoresearch/r007-l05-execution/src/autoresearch/run_manifest.py \
         $MERGED/autoresearch/run_manifest.py
$ PYTHONPATH=$MERGED <python> -m pytest tests/test_m15_telemetry.py -q -o addopts="" -W error
51 passed in 0.06s                      # 互操作测试由 skip 转为实跑

$ PYTHONPATH=$MERGED <python> -c "..."  # 直读输出
K1 run_id        = run_df237de8be1f47d1
telemetry dims   = {'project': 'demo', 'run': 'run_df237de8be1f47d1'}
unpriced point   = {'project': 'demo', 'run': 'run_df237de8be1f47d1'} value= None breach= None
ASSERT OK: dimensions["run"] == RunManifest.run_id (no invented id)
```

→ **结论**：`telemetry` 在 K1 缺位时也能独立工作（不 import），K1 到位后真实 `RunManifest` 直接可用，且**运行标识确实来自 K1**。

## 10. 未闭合

- **S-6 / D-L09-07（唯一开口项）**：`redact_health_report()` / `doctor_diagnostics()` **未接进 `application.py:432 doctor()`**
  （该文件不在本 lane 排他文件内，等 owner 授权）。
  → 因此 **N-4 的「不得落盘原文」在落盘侧尚未保证**：本包只保证了 schema 级拒绝与纯函数级脱敏，**不把它当作落盘级保证**。
- **O-L09-01**：K13 维度白名单缺资源标识槽位 → ACL 侧 `denied` 点无法诚实落地（D-L09-09），等契约裁决。
- 授权/遥测数据**不持久化**（不碰 `storage.py`）；`denials` / `violations` / `traces` / `points` 均为进程内，重启即失。
- ACL × `SensitivityLedger` × `LicenseGate` **无组合出口**（三者独立可测，组合归后续包）。
- `pii._PHONE_RE` 收紧后，**未格式化的电话号码会漏报**（D-L09-10 的已知代价）。
