# S3-A Progress

## 实现

- [x] 基线核对：`codex/s3-a-capability-adapters` HEAD = `origin/main@80e2277`（ahead/behind 0/0，无需 rebase）；本地 `main` 已快进至 `80e2277`，使 `check.mjs --base main` 的差分只含本包改动。
- [x] `CapabilityManifest` 补齐 L2 必备字段（`entrypoint`/`inputs`/`outputs` + `evidence_mode`/`network_required`/`allowed_network_domains`）。
- [x] 实现 `CapabilityRegistry`：manifest registry、operator trust tier、adapter invocation receipt、candidate-only 限制、禁用网络默认策略。
- [x] native/MCP/skill/plugin 四协议统一调用边界；MCP 协议本体按 ADR-01 slot 14 留 L3 扩展位。
- [x] receipt 预留 `admitted` 字段（L2 ★补偿语义 schema 位，端到端验收留 I3）。

## 评审修复（用户选 B 方案：完整修复）

- [x] **R-1/W-1 重放极性丢失**：`CapabilityInvocationReceipt` 增加 `outcome_status`；`_receipt()` 恒等填充；重放路径只改写 `status=REPLAYED` 并保留 `outcome_status`。对齐 A1 既有约定。修复前实测：`failed→replayed`、`denied→replayed`；修复后实测：`status=replayed, outcome_status=failed|denied`。
- [x] **R-2/W-3 引用解析歧义**：新增 `CapabilityAmbiguousReferenceError`；裸 `name` 命中多版本时拒绝并要求 `name@version`。
- [x] **R-3/W-2 验收场景补测**：新增 11 个测试，覆盖此前无测试的分支——候选-only 无候选返回结构化值→FAILED（原 `351-353`）、adapter 异常与非类型化返回→FAILED receipt（原 `384-393`、`361`）、有候选时结构化 value 必须被丢弃、failed/denied 重放保留 `outcome_status`、多版本歧义、字符串 trust tier 强转、缺 invocation_id 拒绝、mapping/pydantic/raw request 指纹路径。
- [x] **R-4 文档化登记**：L2 偏离 D-1（`network` 字段拆分）、D-2（`project_id`/`run_id` 未落边界）、D-3/D-4（receipt 双形状，待 owner 裁决）、D-5（★补偿留 I3）、D-6（permissions 未执行）与越权保证边界，均写入 `L3.md` 与 `HANDOFF.md`。
- [x] **R-5 依据溯源校正**：`ADR-01 slot 14` 引用补全为可追溯路径 `docs/coord/adr-01-external-integrations.md:50`（该文件已随 `80e2277` 落库并签字），并核对 A4 满足其「白名单 + 显式授权 + fail-closed」必要条件。
- [x] **R-6 候选准入语义（事实记录 / 准入判据分离）**：探针实测发现两条 FAILED 路径对 adapter 已 emit 候选处理**相反**——异常路径丢弃（`candidate_count=0`）、契约违规路径保留（`candidate_count=1`），根因是聚合行 `:358` 位于 `raw = invoke(...)` 之后且同一 `try` 内，异常时不可达而两条 `except` 又未传 `candidates=`。修复：统一为「保留原始记录」，并新增 `CapabilityInvocationReceipt.candidates_admissible`（`computed_field`，判据 = `outcome_status == completed`，边界单点计算）与 `CapabilityInvocation.admissible_candidates`（安全入口）。选「保留 + 判据」而非「失败即清空」的理由：删信息不可逆、留信息可逆；与本包失败留痕哲学一致；清空会把「响亮失败」变「沉默空」。补 5 个测试（含重放后仍可准入 / 仍不可准入两个方向）。语义选择登记 `L3.md` D-7 待 owner 确认。

## 验证

- [x] Focused：`python -m pytest tests/test_capability_registry.py` — **29 passed**（原 13 → 修复后 24 → R-6 后 29）。
- [x] 覆盖率：`--cov=autoresearch.capability_registry` — **100%**（210 stmts / 0 miss；原 93% → 修复后 201 → R-6 后 210）。
- [x] 全量：`python -m pytest tests` — **137 passed**（原 121 → 修复后 132 → R-6 后 137；0 failed / 0 skipped / 0 xfail）。
- [x] `python -m ruff check src tests` — passed。
- [x] `python -m ruff format src/autoresearch/capability_registry.py tests/test_capability_registry.py` — 两个新文件已格式化。
- [x] `node .ai-team/check.mjs --task .ai-team/tasks/S3-A-CAPABILITY-ADAPTERS.md --base main` — valid。
- [x] **用户侧独立复跑（Step 1 仓库检查，R-A 显式 `--basetemp`）**：全量 `[100%]` 无 F/E、focused 24、`capability_registry.py` 201 stmts / 0 miss / 100%、ruff `All checks passed!`、check.mjs `valid`（`Functional progress: 17/17`、`Code progress from main: 0 commits, 9 files, +8/-2`）。唯一未观测项：精确 passed 计数（`pyproject.toml` 的 `addopts="-q"` 叠加命令行 `-q` 抑制 summary 行）；不影响结论。**注：本次复跑早于 R-6**，数字为 R-6 前快照。
- [x] **用户侧独立复跑（R-6 后，2026-09-10 20:46，用户回贴原始输出）**：focused `29 passed`、覆盖率 `210 stmts / 0 miss / 100%`、全量 `137 passed`（27.97s）、ruff `All checks passed!`、check.mjs `valid`（`Functional progress: 18/18`、`Code progress from main: 0 commits, 9 files, +8/-2`、`Private sessions: disabled`）。唯一 warning = `.pytest_cache` 的 `WinError 5`（ACL，benign）。**与 R-6 后预期值 29 / 210 / 137 / 18-18 完全一致 → Step 1 数值复跑 VERIFIED。**
- [x] 用户侧功能场景自测（场景 1–9，逐条 observed/not observed 判定）。
  - [x] **场景 1 注册边界 / 旁路=0 / 重复注册拒绝** — **obs 5/5，0 contradictory**：`registration view has 'adapter'` = False；`list()[0] has 'adapter'` = False；`registered count` = 1；未注册 → `CapabilityNotRegisteredError: capability is not registered: scenario-ghost`；重复注册 → `CapabilityRegistrationError: duplicate capability registration: scenario-alpha@1`（键为 `name@version` 形式）。
  - [x] **场景 2 trust tier 只能由 operator 指派** — **全部输出字段 observed，0 contradictory**：adapter 自述 `compliant_structured`，receipt `trust_tier=candidate_only`（生效值取 operator 指派，自述值零进入路径）；`status/outcome_status=completed`；`candidates=1`；`value=None`；diagnostics 逐字含 `adapter trust tier declaration ignored; operator assignment remains authoritative`。
  - [x] **场景 3 candidate_only 正例/负例** — **全部输出字段 observed，0 contradictory**：3a 丢弃证明成立（adapter 实际返回了 `value`，receipt 仍 `value=None` 且 `structured_result_available=False`，`status=completed`）；3b 契约违规 → `status=failed`、`candidates=0`、diagnostics 逐字含 `candidate_only adapter returned no EvidenceCandidate`。顺带记录：3a 的丢弃只在 `structured_result_available` 字段留信号，diagnostics 无额外留痕（符合验收标准）。
  - [x] **场景 4 compliant_structured 正例/负例** — **全部输出字段 observed，0 contradictory**：4a `structured_result_available=True`、`value={'query': 'q', 'kind': 'structured'}`、`candidates=0`、`completed`；4b 只给候选不给结构化结果 → `status=failed`、diagnostics 逐字含 `compliant_structured adapter returned no structured result`。**另记录一条待裁决观察**：4b 的 receipt 为 `failed` 但 `candidates=1`（`:358` 先聚合候选，`:377-379` 分支不清空），即"失败调用仍携带候选"——已由 R-6 处置（统一为保留原始记录 + 新增准入判据），语义选择登记 D-7。
  - [x] **场景 5–8 与场景 9（用户侧复跑，2026-09-10 20:50，用户回贴原始输出）**，结果全部符合预期：
    - **用户侧 5–9 复跑**（PowerShell `foreach` 循环，`scenario.py 1..9`）：
      - 5 越权直写：`write_evidence` / `write_gate_decision` 均 `status=failed`、`candidates=0`（未 emit 候选）、diagnostics 逐字含 `blocked_write_attempts=1` 与两条拦截语；`calls=1`（拦截发生在 adapter 调用之后，非绕过）。
      - 6 网络：6a 默认 `denied`、`calls=0`；6b `allow_network=True` → `completed`、`structured_result_available=True`、`calls=1`。
      - 7 幂等：首调 `failed` → 重放 `status=replayed, outcome_status=failed`（R-1 极性保持）；7b denied 重放保留 `denied`；异指纹 → `CapabilityInvocationConflictError`；裸 name → `CapabilityAmbiguousReferenceError: ... scenario-multi matches [scenario-multi@1, scenario-multi@2]`；`@2` 命中 `version=2`。
      - 8 四协议 + bridge：native/mcp/skill/plugin 均 `completed` 且 `receipt_kind` 与之一致；A1 bridge → `candidate_only`、`completed`、`candidates=1`、`value=None`、legacy `calls=1`。
      - 9 R-6：9a fresh `completed` → `candidates_admissible=True / admissible_candidates=1`；9a replay `status=replayed` 但 `outcome_status=completed` → 仍 `admissible=True`（证明判据挂 `outcome_status`）；9b `raw=2/count=2` 而 `admissible=False/admissible_candidates=0`（事实保留、准入关闭）；9c/9d 同形（`raw=1`、不可准入）；9e `denied` → 全 0、不可准入。
      - 判定：**场景 5–9 全部 PASS，0 contradictory**（用户侧独立复跑，非 AI 侧）。
    - 场景 5 / 7 会进入 R-6 改动的 `except` 分支，但其 adapter 在失败前 emit 数为 0 → 回退前后均打印 `candidates=0`；场景 4b 走的是 `try` 内契约分支（`:418-420`），R-6 未触碰。仅「先 emit 再有候选 × 随后失败」这一组合的打印会变，而它只在场景 9b/9c 出现（9 刻意置于 1–8 基线之外）。
- [x] **R-6 零回归机械验证**（把原先的肉眼比对照升级为机械 diff）：脚本把 worktree `src` 拷到临时目录，在副本中**仅回退 R-6 的两条 `except` 分支**（按起止锚点整段替换，保留成功路径既有 `candidates=` 传参；新增 `computed_field`/属性为纯追加，保留），生成指向副本的 harness，逐场景跑「回退版 vs 当前版」并 `difflib.unified_diff`。结果：**场景 1–8 输出 byte-identical**（`RESULT: scenarios 1-8 byte-identical`）。即 R-6 的改动在 1–8 上可观测行为零改变，行为变化被精确限定在场景 9 所覆盖的「失败前已 emit 候选」路径。只读原仓库，未改动 worktree。
- [ ] Owner review 与 S3 promotion。

## Current boundary

实现与评审修复（R-1~R-6）完成于本隔离分支；用户侧 Step 1 数值复跑与场景 1–9 自测均已通过，commit/PR 材料已备，待提交。

## Handoff to owner（记录级）

`docs/tasks/P1-A-runtime-lane/TASK-SPECS.md:48` 中 A4 状态仍为 `planned`，与 `TASK-QUEUE.md:8` 和 `TASK-PACKAGE-REGISTRY.md` 的 `ready` 不一致。该文件属 owner 维护的共享任务规范，本包未修改，仅上报。
