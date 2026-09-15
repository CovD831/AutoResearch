# M14-15-SECURITY

- ID: `M14-15-SECURITY`
- Title: `ACL / PII / 许可 / telemetry（R-007 L-09 lane）`
- Status: `handoff`
- Owner: `impl-l09-security`
- Next owner: `user`
- Branch / worktree: `feat/r007-l09-security` @ `../r007-l09-security`，base `main@8dd8780`
- Status note: 2026-09-15 交付 **M14-03/04/05 + M15-02/04**：`acl.py` / `pii.py` / `licensing.py` / `telemetry.py` + **107 条用例（106 passed + 1 skipped）**。
  开工时 K1 未冻结（`../r007-l05-execution/.../run_manifest.py` 不存在），故前半先做、后半挂起；
  **作业中途 K1 冻结**（同一路径出现 8768B 文件，untracked），复查后按任务卡条件分支继续做后半。
  两批之间**不写占位实现、不写空测试**（挂起期登记见 `L3.md` §5）。

## Goal

按 R-007 L2 的 K11/K12/K13 把 L-09 的安全与可观测层从零建起：
默认拒绝且越权可观测的访问控制（K11）、带空约束标注的敏感级别与可追溯出网（K12）、
`value=None`=未测的遥测点、O12 成本口径、日志脱敏与超阈中断（K13）。

## Acceptance scenarios

- [x] **K11-1** 无策略访问 → `allowed=False, reason="no_policy"`；`granted=False` 的行用**不同 reason**（`policy_not_granted`）区分。
- [x] **K11-2** `require()` 抛 `AccessDenied` 并写 `denials`；`readable_resources()` 对「无任何策略的主体」**抛异常而非返回 `[]`**（负例 N-1）。
- [x] **K11-3** `grant()` 拒无 justification 的 `export`/`delete`；授权时**复检**；justification **逐动作**存
      （为 `export` 写的理由不覆盖事后加宽进来的 `delete` —— 自审发现的真实漏洞，已修 + 变异点 M10）。
- [x] **K12①** `SENSITIVE` 禁 embedding —— **空约束，已标注 `【向量落地后生效】`，未写通过断言**。
- [x] **K12②** 导出/删除可追溯：未分类 → `UnclassifiedExport`；空 reason → `UntraceableExport`。
- [x] **M14-05** 许可门禁：`unknown` 恒拒（不得当 open）、`paywalled` 无权利 → `paywall`（负例 N-5）、无任何 bypass 参数。
- [x] **K13-1** `value=None`=未测、绝不用 0：`value` **默认即 `None`**；`breaches_threshold` 再做一层 `bool|None`（未测 = `None`，不是 `False`）。
- [x] **K13-2** `cost_usd` 未命中价目 → `None`（负例 **N-3**）：`cost_usd_point()` 复用 O12 `price_source`/`attempts` 口径。
- [x] **K13-3** 不得记录 prompt/全文/token/secrets：**字段白名单** + 超长/换行/secret/PII 扫描 + 拒绝 `redacted=False`（负例 **N-4** 的 schema 侧）。
- [x] **K13-4** 超阈 → `TelemetryInterrupt` + `ThresholdBreach`；**未测告警进 `.unmeasured` 而非被读成合格**。
- [x] **K1 挂接**：`dimensions["run"]` 取 `RunManifest.run_id`，**不自造运行标识**；**已用真实 K1 模块实证**（见 Verification）。
- [x] 聚焦 106 passed / 1 skipped + 全量 643 passed / 3 skipped / 0 failed（基线 537 未降）+ ruff clean + compileall ok + check.mjs valid。

## Invariants

- **不碰硬禁区**：`storage.py` / `knowledge.py` / `contracts.py` / `provider_lane.py` 零改动（`git status --porcelain` 这 4 个 0 行）。
- 不实现 embedding / 向量（仓库无此能力）；**不为空约束写「通过」断言**。
- **不 import** `autoresearch.run_manifest`（K1 只在 L-05 worktree，import 会致合并前不可导入）；K1 挂接走**结构依赖**（接受 `.run_id` 对象）。
- **不改** `application.py`（不在排他文件内）→ 脱敏只提供纯函数，接线等 owner 裁决（D-L09-07 / S-6）。
- 每个新测试必须**能红**：判别力由变异注入实测（`evidence/mutation-check.md`，**17/17 判据型**）。
- 断言的是**退化路径的正确结果**，不是「没崩」：`value is None`（**不是** `== 0`）、`DID NOT RAISE` 是可接受的失败类型。
- 不动 `.ai-team/TASK.md`（全局三处串行），只写本成员账本。

## Decisions

- **D-L09-01**：开工时 K1 未冻结 → `telemetry.py` 挂起（按任务卡指令）；**K1 冻结后已闭合**。全程留痕（L3 §0.1/§0.2）。
- **D-L09-02**：`SensitivityClass.SENSITIVE` 的禁 embedding **只登记不断言**：`DEFERRED_INVARIANTS`（`MappingProxyType`）+ docstring 双标注；
  唯一相关测试断的是**标注字符串还在**（删标注即红），docstring 明写「这不是不变量的证据」；另有 tripwire 断本模块无 embedding/vector API。
- **D-L09-03**：`AccessPolicy.actions` 由 `list[str]` 收窄为 `list[ResourceAction]`（类型对齐；非法动作转 `ValidationError`）。
- **D-L09-04**：`PiiScanResult.value` 用 `int | None`（K13 的 `value` 是 `float | None`）；共享的是判据不是类型。
- **D-L09-05**：验收命令的 `test_m15_*` glob 开工时无匹配（实跑 `test_m14_*.py`）；后半交付后**原命令已可全跑**（106 passed）。
- **D-L09-06**：`SensitivityLedger` 取严：未分类资源不得导出（L2 只要求「可追溯」）。
- **D-L09-07**：**M15-02 脱敏未写进 `application.py` 的 `doctor()`** —— 该文件不在排他文件内。提供可接线纯函数，
  **等 owner 授权**。⚠️ **这是本包唯一的开口项（S-6）**。
- **D-L09-08**：K13-4 的 interrupt 实现为**异常**，不是 langgraph interrupt；graph 接线属调用方（M15-04 集成）。
- **D-L09-09**：**没有** ACL → telemetry 适配器 —— K13 维度白名单无资源标识槽位，塞进 `gate` 会**记错维度**。以契约观察 **O-L09-01** 上报。
- **D-L09-10**：`pii._PHONE_RE` 收紧为「必须有格式」（`+`E.164 或带分隔），精度优先；代价是未格式化号码漏报（登记为已知边界）。
  触发原因：原正则命中 `run_0123456789abcdef`，使**每个消费方的 id 都像 PII**。
- **边界**：`licensing.py` 只做**策略与门禁**（不判定许可事实，那属 L-04）；ACL（允不允许）/ `SensitivityLedger`（留没留痕）/ `LicenseGate`（许可门禁）**互不调用**，各自独立可测。
- **契约观察 O-L09-01/O-L09-02** 见 `L3.md` §4.1（维度白名单缺资源槽位；`threshold` 无方向语义）→ 回契约作者裁决。

## Completed

- 新建 `src/autoresearch/acl.py`（K11）、`pii.py`（K12）、`licensing.py`（M14-05）、`telemetry.py`（K13/M15-02/M15-04）。
- 新建 `tests/test_m14_acl.py`(21) / `test_m14_pii.py`(19) / `test_m14_licensing.py`(16) / `test_m15_telemetry.py`(51) ＝ **107 条用例**（106 passed + 1 skipped）。
- 补全 L3：`docs/tasks/M14-15-security/tasks/L3.md`（§0 批次与 K1 实测、§2 实现、§4 偏离 D-L09-01..10 + 契约观察、§5 S-1..S-7 闭合记录）。
- 判别力证据：`evidence/mutation-check.md` + 可重跑脚本 `evidence/mutation_check.py`（**17 变异点**，自带还原 + 逐文件比对）。
- 验证记录：`evidence/verification.md`（含 K1 合并包互操作实跑）。
- **自审修正（1 处真实漏洞）**：K11-3 justification 由「按策略行」改「按动作」——原实现下为 `export` 写的理由会覆盖事后加宽的 `delete`。已修 + 补用例 + 变异点 M10。
- **自审修正（1 处误报）**：`pii._PHONE_RE` 收紧（否则每个 run id 都被判成 PII）。

## Pending

- **S-6 / D-L09-07（唯一开口项）**：把 `redact_health_report()` / `doctor_diagnostics()` 接进 `application.py:432 doctor()`。
  **需要 owner 明确授权**（`application.py` 不在本 lane 排他文件内）。当前只交付纯函数。
- `licensing.LicenseGate.violations` 与 `pii.SensitivityLedger.traces` 尚无遥测消费方（`denied` 指标的接入受 O-L09-01 阻塞）。
- K13 维度白名单缺资源槽位（O-L09-01）→ 等契约裁决后，ACL/许可的 `denied` 点才能真正落地。
- **提交与合并**：本包所有改动停在本地，**未 `git commit` / `git push`**，等 owner 明确许可。
- **合并顺序注记**：`telemetry.py` 在 K1 缺位时也能独立工作（不 import），但 `test_interop_with_the_real_k1_run_manifest` 在 K1 合并前会 skip；
  K1（L-05 的 `run_manifest.py`，当前 untracked）先落 main 才能让该联调由 skip 转 pass。
- registry / `TASK.md` 回写由 owner 执行（共享文档，本包未改）。

## Next step

`team-lead` 报用户确认 → 决定是否提交；并对 S-6（是否授权改 `application.py`）与 O-L09-01（维度白名单）给出裁决。

## Verification

- [x] 基线（开工实测，本 worktree）：`537 passed, 2 skipped`（`main@8dd8780`）。
- [x] **任务卡原命令**：`pytest tests/test_m14_*.py tests/test_m15_*.py -q -o addopts="" -W error` → **106 passed, 1 skipped**（107 collected）。
- [x] 全量：`pytest -q -o addopts="" -W error` → **643 passed, 3 skipped, 0 failed**（646 collected）；
      passed `537 → 643`（**+106，未下降**），skipped `2 → 3`（+1 = K1 联调测试，K1 不在本 worktree 路径上时**跳过而非通过**）。
- [x] `ruff check src tests` → `All checks passed!`；`compileall -q src` → ok。
- [x] `python scripts/check_pr_contract.py --base main` → `passed: 0 changed paths; 0 task ledger(s)`（本地未提交，故 0）。
- [x] `node .ai-team/check.mjs --base main` → 建账本前 `blocked`；落账本后 **`valid`**。
- [x] **K1 互操作实证**（把 L-05 的 `run_manifest.py` 软链进临时合并包后实跑）：
      `RunManifest.run_id = run_df237de8be1f47d1` → `dimensions_for(run=manifest) == {'project':'demo','run':'run_df237de8be1f47d1'}`
      → `ASSERT OK: dimensions["run"] == RunManifest.run_id`；M15 在合并包下 **51 passed**（互操作测试由 skip 转实跑）。
- [x] 判别力：**17** 个变异点全部「变异前绿 / 变异后红」，失败类型**全部判据型**（无符号缺失）。
      人工复核原始失败行：`assert 0 is None`（M5）、`DID NOT RAISE AccessDenied`（M2）、`assert 0.0 is None`（M12）、`assert False is None`（M16）。
- [x] 硬禁区零改动：`git status --porcelain` 对 `storage.py`/`knowledge.py`/`contracts.py`/`provider_lane.py` 输出 0 行。

## Handoff note

**本节的来历**：原 `Status` 字段写作 `` `delivered`（前半 M14 + 后半 M15 均已交付；
1 项等 owner 裁决 = S-6 接线） ``，有两处不合规：

1. **`delivered` 不在 `.ai-team/check.mjs` 的 `VALID_STATES` 里** → 状态值非法；
2. **值后有行尾明文** → `field()` 的严格正则 `^- Status: `([^`]+)`$` 解析失败，整值判为缺失。

已改为 `Status: `handoff``，行尾交付说明移至本节。

**交付状态**：前半 M14（ACL / PII / 许可）与后半 M15（telemetry）**均已交付**；
**1 项等 owner 裁决 = S-6 接线**。

**给后续接手者的注意事项**：

- 台账元数据字段（`ID` / `Title` / `Status` / `Owner` / `Next owner`）不得含**内层反引号**，
  也不得在闭合反引号后追加明文 —— 两者都会让整值解析为 `null`，
  并报出与真实原因无关的「missing metadata」错误。注解请写在 `Next step` 或本节。
- **本 lane 的空约束纪律**（不得丢失）：K12 的 embedding 禁入是**空约束**
  （仓库当前无向量实现），必须标注 `【向量落地后生效】`，
  **不得写「K12 通过」这类断言**；成本未测一律 `None`，**绝不用 `0`**。
