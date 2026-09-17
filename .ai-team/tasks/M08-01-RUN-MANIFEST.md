# M08-01 RunManifest (K1 contract-first)

- ID: `M08-01-RUN-MANIFEST`
- Title: `R-007 L-05 第 1 步：K1 RunManifest 字段级冻结（src/autoresearch/run_manifest.py）`
- Status: `handoff`
- Status note: 2026-09-15 在 lane worktree `/Users/abab/Documents/ChatGPT/autoresearch/r007-l05-execution`（分支 `feat/r007-l05-execution`，base `main@8dd8780`）完成 K1 落地：13 字段逐字对齐、4 条不变量全部实现（K1-4 为架构意图，零 validator + 元级守卫）、4 条负例齐备。本 worktree 自测基线 `537 passed / 2 skipped` → 收口 `576 passed / 2 skipped / 0 failed`；`ruff check src tests` clean；判别力用「真基线 + 符号 shim + 4 个突变探针」三段取证（真基线只有符号型失败，计入 0 例 —— 如实记录）。**未 commit、未 push、未开 PR**（提交纪律，等 owner 许可）。**owner 2026-09-15 裁决：D-1（`exit_code` 输入域）/ D-2（`extra="forbid"`）两条均保留，性质由「强化项」改称「契约硬化」，见 L3 §2.5。** 另有 9 条未闭合项登记在 L3 §10（R-2/R-3/R-4/R-5 经 owner 明确免做，保留实测复现命令）。
- Owner: `impl-l05-execution`
- Next owner: `user/team`

## Goal

把 R-007 L2 已冻结的 **K1 `RunManifest`** 落地成可用的类型契约，作为其余 6 条 lane 的**共同运行标识**：L-02 `PrefetchRecord` 与 L-09 `TelemetryPoint` 都含运行维度，不先冻 schema，它们会各自发明一个「运行标识」（R-006 未合并时发生过）。

本次只做 K1（M08-01），**不做** K2/K3/K4（M08-03/04/06/07）。

## Acceptance scenarios

- [x] 13 字段逐字对齐 K1，不增不删：`run_id` / `project_id` / `work_package_id` / `code_revision` / `data_refs` / `environment` / `parameters` / `seeds` / `command` / `exit_code` / `output_hashes` / `rerun_of` / `created_at`（测试 `test_frozen_field_set_is_exactly_the_13_k1_fields` 机械断言）
- [x] 完整填充的 manifest 可校验、可 JSON 往返回读（`test_a_fully_populated_manifest_validates_and_survives_a_json_round_trip`）
- [x] **K1-1** `command` 必须是 argv 列表；`str` **被拒**（不 split、不静默通过）
- [x] **K1-2** `seeds` 不得为空；`[0]`（显式无随机性）通过
- [x] **K1-3** `exit_code is None` ⟺ 未执行；已执行必须有退出码（含非零）
- [x] **K1-4** `output_hashes` 真实性 = 架构意图：**零 validator**，docstring 显式标注交 M08-07，**未写「通过」断言**（只有一条反向守卫）
- [x] **实际复用既有原语**（非「照搬语义」）：`new_id`（`run_id` 默认）、`utc_now`（`created_at` 默认）、`WorkPackage`（`for_work_package`）、`ArtifactRef`（`output_refs`）—— 四个调用点各有测试佐证（L3 §6.4）
- [x] 4 条负例 N-1～N-4 齐备，且每条都有**判据型**失败证据（L3 §6.2）
- [x] 不改 `contracts.py` / `knowledge.py` / `storage.py` / `evolution_service.py`（实测 `git status` 无这些文件）
- [x] 全量 ≥ 537 passed / 0 failed、ruff clean、`compileall` 0
- [ ] owner 裁决：K1 类型是否上收 `contracts.py`（本包为「不上收」）
- [ ] owner 裁决：D-1（`exit_code` 输入域）/ D-2（`extra="forbid"`）两条**强化**是否保留

## Invariants

- **字段集是不变量**：`RunManifest.model_fields` 恰为 13 个且顺序与 K1 表一致（机械断言，防「顺手加字段」）。
- **K1-3 的语义不变量（本包核心）**：`exit_code=None` **绝不被补成 `0`**。写侧经 `mode="before"` 守卫显式保持 `None`；读侧 `executed` 属性把它变成可断言的接口；JSON 往返两次仍为 `None`（`test_k1_3_a_serialised_unexecuted_manifest_stays_unexecuted`）。**这就是本项目最顽固的缺陷族（退化路径上把未知/失败记成正常值）的正面狙击点。**
- **K1-4 不是不变量，是架构意图**：本模块**不存在** `output_hashes` 的 validator，且测试**不存在**关于 hash 真实性的「通过」断言 —— 只能被「有人加了 validator」违反（反向守卫可失败，故非恒真）。
- **不扩大范围**：`contracts.py` 等 7 个 `forbidden_paths` 文件零改动；新代码只在 `run_manifest.py`（不含既有实现逻辑）。
- **降级方向**：本包是「拒绝非法输入」，没有 `except … return <正常值>` 形式的降级路径；唯一可能被误当成降级的是 `exit_code=None`，而它**不是**降级值是**一等语义**（未执行）。

## Decisions

- **D-L05-01（K1 定义落在新模块，不上收 `contracts.py`）**：`contracts.py` 被 L-06/L-07 占用（R-007 §5「三处必须串行」，本任务卡硬约束 1）。故 K1 类型定义在 `src/autoresearch/run_manifest.py`，是否上收由 owner 裁决。
- **D-L05-02（必填字段一律无默认值，含 `output_hashes`）**：K1 表把 `output_hashes` 标为 ✅ 且注明「未产出时 `{}`，不得填假值」。故要求调用方**显式传 `{}`**，与 K1-2「不得省略 seed」同一纪律：省略不得成为合法路径，否则「没记录」与「没产出」不可区分。`run_id` / `created_at` 例外（契约/任务卡明确给了默认值）。
- **D-L05-03（K1-1 双防线）**：字段声明 `list[str]` + `mode="before"` 守卫。实测（pydantic 2.13.4）：类型层单独就能拒 `str`；validator 的独有贡献是「与规则同名的显式报错」与「不依赖字段声明的独立性」——突变探针 M1 把类型放宽后，只剩守卫能拦（L3 §6.3 第 3 条）。
- **D-L05-04（K1-3 加 `executed` 派生属性）**：K1-3 写的是「⟺」，读侧没有接口时，N-4 只能断言「字段非 None」，**无法断言「没有被当作未运行」**。故加一个**非字段**的 `executed` property（不入 schema、不进 `model_dump()`、不改 13 字段形状）。
- **D-L05-05（强化 `exit_code` 输入域：`None` 保持、`bool`/`str` 拒绝）**：**实测 pydantic 2.13.4 lax 模式 `False → 0`、`True → 1`、`"0" → 0`**，即 `exit_code=False` 会被存成「执行成功」——正是 K1-3 要挡的坍缩。已登记为 L3 §9 **D-1**（强化，不放行/不改写任何契约合法输入，可逆：删一个 validator）。
- **D-L05-06（强化 `extra="forbid"`）**：未知字段名（如 `seed=0` 拼错）不得静默丢弃变成「没提供」。已登记为 L3 §9 **D-2**（同上，可逆：删一行 `model_config`）。
- **D-L05-07（K1-4 零 validator + 反向守卫）**：不给 `output_hashes` 写任何校验，也不写「通过」断言（那会造恒真假绿）；只写一条「**不存在** validator、且 validator 集合恰为 `{command, exit_code}`」的守卫，它在「有人加了假校验」时会失败。
- **D-L05-08（判别力方法：真基线 + shim + 突变三段）**：真基线（连模块都没有）只能得到 `ModuleNotFoundError`（符号型，**计入 0**）；按 `DISCRIMINATING-POWER.md` 注入「只补符号、不改行为」的 shim 后 N-1/N-2 得判据型，但 N-3/N-4 因 shim 缺 `executed` 仍是符号型；故再加 4 个**突变探针**（关掉/反转单条守卫）拿到严格对角的判据型证据 16/16。探针脚本随包提交（`tests/fixtures/run_manifest/probe_discriminating_power.py`），可重跑。

## Completed

- `src/autoresearch/run_manifest.py`（新增，~150 行）：`RunManifest`（13 字段）+ `_command_must_be_argv` + `_exit_code_semantics` + `executed` + `for_work_package` + `output_refs`；模块 docstring 含 K1-4 的架构意图声明。
- `tests/test_run_manifest.py`（新增，39 项）：N-1～N-4 + 正向 + 4 个复用调用点佐证 + 3 条强化项 + 1 条 K1-4 反向守卫。
- `tests/fixtures/run_manifest/probe_discriminating_power.py`（新增）：判别力探针（4 突变 + shim + 真基线，可重跑）。
- `docs/tasks/M08-execution/tasks/M08-01-run-manifest/`：`L3.md` 补全 `Implemented design`（§2.4）/ `Deliberate non-goals`（§5.1）/ `Contract deviations`（§9）/ `判别力证据`（§6）/ `验证记录`（§7.1）/ `已知边界与遗留`（§10）。
- `docs/tasks/M08-execution/tasks/M08-01-run-manifest/evidence/`：`discriminating-power.log` + `.json`（探针原始输出，落盘留证）。
- `.ai-team/tasks/M08-01-RUN-MANIFEST.md`（本文件）。
- 本包改动文件全集（**8 个路径**，全部在 `allowed_paths` 内）：2 个源码/测试文件
（`src/autoresearch/run_manifest.py`、`tests/test_run_manifest.py`）+ 1 个 fixture 探针
（`tests/fixtures/run_manifest/probe_discriminating_power.py`）+ 4 个任务文档/证据
（`L3.md`、`task-package.json`、`evidence/discriminating-power.json`、`evidence/discriminating-power.log`）
+ 1 个账本。**`forbidden_paths` 零触碰。**

  > 原记「7 个路径」，漏计了 `task-package.json` —— 实测 `gh api .../pulls/26/files` 返回 8 项。

## Pending

- **提交状态：已 commit `2931bcb`、已 push 分支 `feat/r007-l05-execution`、已开 PR #26**。
  > 原记「未 commit / 未 push / 未开 PR」（R-007 §6 提交纪律下的当时状态）；
owner 已许可并完成提交，本行按事实更新。
- [x] **owner 裁决（2026-09-15）：D-1 / D-2 均保留为契约硬化条款**（裁决理由见 L3 §2.5：不是加严，是补掉真实坍缩通道 / 不可观测的静默丢失）；措辞已由「强化项」改称「契约硬化」，来源已注明。
- [x] **owner 明确免做**：K1 不上收 `contracts.py`；R-2/R-3/R-4/R-5 不修（不属本包管辖 —— K1 只管「记录得像不像样」，不管「命令该不该跑」）；R-9 空判决口径由 owner 写进最终汇编。四条遗留的**实测复现命令**保留在 L3 §10。
- [ ] owner 裁决后启动下一包：`M08-02-EXECUTOR`（K2）。
- L3 §10 的 9 条未闭合项：R-1（K1-4 交 M08-07）、R-2（空串标识未禁）、R-3（`sh -c` argv 属 M08-03）、R-4（`rerun_of` 血缘属 M08-04）、R-5（seed 取值域）、R-6（建议 M08-03 复用 D-1 守卫）、R-7（真基线无判据型证据）、R-8（下游引用承诺待验）、R-9（`check_pr_contract` 空判决）。
- 建议下一包：`M08-02-EXECUTOR`（K2）。

## Next step

1. owner 审 `run_manifest.py` 的 13 字段与 4 条不变量（**重点审 D-1/D-2 两条强化**：它们是本包唯一的「契约外」行为面）。
2. owner 裁决后，其余 6 条 lane 可开始引用 `RunManifest.run_id`（L-02 / L-09 不得自造运行标识）。
3. 若 owner 许可提交：本包已自测全绿，可直接 commit（**但需 owner 明确指示**）。

## Verification

命令均在 lane worktree `/Users/abab/Documents/ChatGPT/autoresearch/r007-l05-execution` 下执行；公共参数 `-o addopts="" -W error`（前者让 summary 行可见，后者让警告升级为错误）；Python = `/Users/abab/.workbuddy/binaries/python/envs/default/bin/python`（3.13.12，pydantic 2.13.4）。

- [x] **改动前基线（本 worktree 实测，非搬运）**：`pytest -q -o addopts="" -W error` → **537 passed, 2 skipped in 28.58s**（exit 0）。
- [x] 本包聚焦：`pytest tests/test_run_manifest.py -q -o addopts="" -W error` → **39 passed in 0.05s**（exit 0）。
- [x] 全量：`pytest -q -o addopts="" -W error` → **576 passed, 2 skipped in 24.92s**（exit 0）。**0 failed / 0 error，基线数未下降**（537 + 39）。
- [x] `ruff check src tests` → `All checks passed!`（exit 0）。
- [x] `python -m compileall -q src` → 无输出（exit 0）。
- [x] `node .ai-team/check.mjs --base main` → **`Result: valid`**（exit 0；`Code progress from main: 0 commits, 12 files, +78/-11`）。**首跑为 `blocked`**（「changed without updating `.ai-team/TASK.md` or a member ledger」）—— 写入本账本后转为 `valid`，即该门禁确实在要求账本，不是空跑。
- [x] `python scripts/check_pr_contract.py --base main` → `PR contract check passed: 0 changed paths; 0 task ledger(s)`（exit 0）。**但须注明：它统计的是已提交 diff，运行时本包尚未 commit ⇒ 那次 `passed` 是空判决，
不能当证据**（遗留 R-9）。**2026-09-17 更新**：本包现已 commit `2931bcb`（PR #26），
该检查自此有了判别力；上面那行保留为当时的记录。
- [x] 改动面核查：`git status` 显示本包只新增 `run_manifest.py` / `test_run_manifest.py` / fixture 探针 / 任务文档 / 本账本；`contracts.py` 等 7 个 `forbidden_paths` **零改动**。

### 判别力实测（`tests/fixtures/run_manifest/probe_discriminating_power.py --base 8dd8780`）

探针树 = `git archive 8dd8780` 展开（**不含本包改动**）+ 只拷入 `tests/test_run_manifest.py`。

| probe | 是什么 | 汇总 | N-1 | N-2 | N-3 | N-4 |
|---|---|---|---|---|---|---|
| P0-nomodule | 真基线（无模块） | `1 error` | not-run(symbol) | 同左 | 同左 | 同左 |
| P1-shim | 只补符号（无 validator / 无 helper） | `28 failed / 11 passed` | criterion\* | criterion | symbol-missing | symbol-missing |
| M1 | 去 K1-1（类型放宽 + 守卫置空） | `5 failed / 34 passed` | **criterion ×5** | pass | pass | pass |
| M2 | 去 K1-2（删 `min_length=1`） | `1 failed / 38 passed` | pass | **criterion ×1** | pass | pass |
| M3 | K1-3 坍缩（`None → 0`） | `5 failed / 34 passed` | pass | pass | **criterion ×5** | pass |
| M4 | K1-3 反向坍缩（非 0 → `None`） | `5 failed / 34 passed` | pass | pass | pass | **criterion ×5** |

**分类与计数（按 `docs/process/DISCRIMINATING-POWER.md`）**

- **判据型（计入）**：P1 = 16 例（其中 N-1 的 5 例**人工判回不计入**，见下）；**M1–M4 = 16 例**（5 + 1 + 5 + 5），严格对角，判据型 16/16。
- **符号缺失型（不计入）**：P0 = 1 例（`ModuleNotFoundError`，整个文件 collection 期即死，**一条断言未跑**）；P1 = 12 例（`AttributeError: 'RunManifest' object has no attribute 'executed' / 'output_refs' / 'new_id'` 等）。
- **shim 导致的分类修正（必读）**：P1 下 N-1 的失败是 `assert 'argv' in "1 validation error … Input should be a valid list"` —— shim **已经拒绝了字符串**（靠 `list[str]` 类型声明），只是报错文案没有 `argv`。故 **N-1 的承重证据不记 P1，记 M1**（把类型放宽 + 关守卫后字符串才真被接受，`DID NOT RAISE`）。**未被 shim 伪装成判据型的用例**：其余 P1 criterion 均由 `DID NOT RAISE` 造成，属真实判据型。
- **可直接重跑的旧行为复现（M3，最贴近本项目缺陷族）**：`None → 0` 突变下 `assert 0 is None` / `assert 0 != 0` / `assert 0 is None`（JSON 往返）失败 —— 即**「未执行」被写成「执行成功」**；M4 反向：`assert None == 1` 失败，即**「失败」被写成「未执行」**。
- 原始输出落盘：`docs/tasks/M08-execution/tasks/M08-01-run-manifest/evidence/discriminating-power.log`（文本）与 `.json`（机器可读）。

## Handoff note

本包交付 K1 `RunManifest` 字段级冻结（`src/autoresearch/run_manifest.py`）。

**待 owner 裁决两项**（原先直接写在 `Next owner` 字段行尾，已移至此）：

1. **K1 是否上收 `contracts.py`** —— 本包按 R-007 §5 的串行约束**未上收**，独立成 `run_manifest.py`。
2. **D-1 / D-2 是否保留** —— 见 `Decisions` 节。

**给后续接手者的注意事项**：

- 台账元数据字段（`ID` / `Title` / `Status` / `Owner` / `Next owner`）的格式由
  `.ai-team/check.mjs` 的 `field()` 用严格正则解析，形如：

  ```text
  正则：^- Name: `([^`]+)`$
  要求：① 值被一对反引号包住  ② 值内部不得再有反引号  ③ 行尾即闭合反引号，不得有明文
  ```

  **不要把「人读的注解」写进这五个字段** —— 会导致整值解析为 `null`，
  进而报出「missing metadata」这类与真实原因无关的错误。
  注解请写在 `Next step` 或本节。

- 判别力口径见 `docs/process/DISCRIMINATING-POWER.md`：
  **判据型失败计入证据，符号缺失型（`ImportError` / `AttributeError: no attribute`）不计入。**
