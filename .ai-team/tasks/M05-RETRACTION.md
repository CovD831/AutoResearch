# Current Task

- ID: `R007-L04-M05-RETRACTION`
- Title: `K10 retraction / correction / OA / licence facts (L-04 lane)`
- Status: `reviewing`
- Owner: `impl-l04-retraction`
- Next owner: `team-lead`

## Goal

按已冻结的 R-007 L2 契约 **K10 `RetractionStatus`** 落地 M05-06（撤稿、更正、OA 和许可检查）：
撤稿/更正/访问基础的事实判定，判据复用 B5 的 `updated-by[]`（不重写），
`RETRACTED` 必须真的触发 K8 传播，且 `UNAVAILABLE` 绝不等于 `ACTIVE`。

## Acceptance scenarios

- [x] K10 枚举与冻结契约逐值一致（`active`/`retracted`/`corrected`/`unavailable`）。
- [x] **K10-1**：网络不可用 / 超时 / 限流 / 403 / 500 / 503 / 404 / resolver 抛异常 → 全部 `UNAVAILABLE`，`confirmed_active is False`。
- [x] **K10-1 结构保证**：投影表全覆盖，`ACTIVE` 的原像恰好 `{FOUND}`；未映射成员抛错不返回默认值。
- [x] **投影层允许归并 / 审计层禁止归并**（owner D-M05-01 裁决附加条件）：`NOT_FOUND` 与 `UNKNOWN` 同投影为 `UNAVAILABLE`，但 `source_status`/`reasons` 可区分，有测试固化。
- [x] **K10-2**：`RETRACTED` 触发 K8 传播（记录调用形状与 `action`）；无 sink / 无 `source_evidence_id` → 抛错，不返回「看起来已传播」的状态。**`affected_claims` 空是正常情况**：blast radius 由 K8 从图推导（K8-2），不在本模块校验，空集不在此抛错（K8-3 守卫在 walk 实际发生处）。
- [x] **K10-3**：判据只在 `external_sources.py:254-255` 读取；AST 守卫禁止本模块重读关系数组。
- [x] **M05-06 正例**：OA / 受限 / 不可用三态可区分，且「有 `license[]`」不被当作开放。
- [x] **N-1（核心）**：不可用 → `UNAVAILABLE`，断言具体取值而非「没崩」。
- [x] **N-2**：`RETRACTED` 确实触发传播。
- [x] **N-3**：试图绕过付费墙 → 被拒（含开放作品），并按 K8 记 `permanent_block`。
- [x] **N-4**：用 2026-09-15 真实抓取的 payload 断言字段方向，并与 B5 fixture 逐字段比对；另含「互换数组 → 撤稿变 ACTIVE」反事实。
- [x] 测试离线可跑；`retraction.py` 结构上无法发起网络请求（AST 守卫）。
- [x] **D1 接缝**：真实 L-02 `InvalidationService`（`plan()`/`record()` 两步 API）经
      `K8InvalidationAdapter` 接通 L-04 checker，跑通 `RETRACTED`，`InvalidationPropagation` 与
      `invalidation.propagated` 审计事件**真的落库**（合并树 **54 passed / 0 skipped**）；
      拒绝路径实测**零落库**（结构性保证，非时序）。
- [x] **D2 一致性**：L-04 与 L-02 的 K8 reason 域、永久阻断集合、逐 reason action **双向相等**
      （运行时每次传播校验 + 跨模块测试）。

## Invariants

- `UNAVAILABLE ≠ ACTIVE`：任何「取不到/判不了」都不记成正常值（K10-1）。
- 撤稿判据只有一处实现（B5）；本包只消费，不复制（K10-3）。
- 未接 sink 时 `RETRACTED` **不得**被返回（K10-2，fail-closed）。
- 本包只做**事实判定**；「谁能看/导出/删除」是 K11 / L-09 `licensing.py`。
- 不碰 `search_service.py` / `contracts.py` / `storage.py` / `knowledge.py`；
  `external_sources.py` 只做纯追加，既有判据行与 `resolver_record` 一行未改。
- `RetractionStatus` 定义在本模块内（开工约定 §3.2），不写进共享 `contracts.py`。

## Decisions

- **D-M05-01（已裁决：维持，不扩枚举）**：K10 无 `NOT_FOUND` 取值，本包投 `UNAVAILABLE`（投 `ACTIVE` 即是 K10-1 要禁的缺陷）。owner 2026-09-15 裁决理由：① K10 是冻结 4 值枚举，扩枚举＝改契约，属 owner 权限；② 404→`ACTIVE` 正是 K10-1 明文要禁的；③ 信息未丢失（保留在 `source_status`）。**附加条件已落地**：`test_not_found_and_unknown_merge_at_the_projection_layer_only` —— 投影层可归并、审计层不可归并。
- **D-M05-02（保持，已按 owner 要求加硬）**：快照兜底会把降级传输记成 `ACTIVE`（B5 有意设计）。不改 B5，改为暴露 `transport` / `transport_degraded`；**已在 `retraction.py` 模块 docstring 写死「`ACTIVE` 不蕴含今日可达，需要新鲜确认必须检查 `transport_degraded`」**，并配 `test_active_with_a_degraded_transport_is_flagged`。
- **D-M05-03**：许可判定规则（CC 标记 + `tdm` 否决 + 无元数据 → `UNAVAILABLE`）由 5 个真实 payload 支撑，方向一律 fail-closed。
- **D-M05-04**：2 个用例为派生（合成 CC+tdm、删 `license`），测试 docstring 已逐条标注。
- **D-M05-05**：`RetractionStatus` 放 `retraction.py` 而非 `contracts.py`（合规，非偏离）。
- **D-M05-06（已闭环）**：K8 接线走 `InvalidationSink` 端口（本 base 上 `invalidation.py` 不存在）。
- **D-M05-07（D1 阻断项，已修，改在 L-04 侧）**：L-04 端口 5 参 vs L-02 真实 3 参
  （`propagate(*, source_evidence_id, reason, actor="system")`，`invalidation.py:254-260`），
  且 L-02 **自己从图推导** blast radius（`:268-274`）。owner 裁决 L-02 更符合 K8 语义、**不改它**。
  本包修正：① `PropagationContext.affected_claims`/`affected_gates` 由必填改**可选**，空集**不再**抛错
  —— 原来那条「镜像 K8-3」的守卫是**错的**（强迫调用方编造它看不见的图事实，并把 K8-3 从 owner 手里搬走）；
  ② 新增 `K8InvalidationAdapter`（在 `retraction.py` 内），把 L-04 的参数当**断言**交叉校验而非丢弃；
  ③ `PropagationRequiredError` 的「无 sink 必须报错」保留。
- **D-M05-08（D2，已修）**：`PERMANENT_BLOCK_REASONS`/action 表两处实现。① 运行时每次传播
  交叉校验 action（不一致抛 `PropagationContractMismatchError`）；②
  `test_l04_and_l02_agree_on_the_k8_reason_domain_and_actions` 做**双向**集合 + 逐 reason 映射比对
  （新增公开 `K8_REASONS` 以支持双向比较）。
- **D-M05-09（实跑抓到，已根本修掉）**：适配器**最初**在 `service.propagate()` **返回之后**才交叉校验，
  而 L-02 **先落库后返回** → 事后再拒绝等于「错误报了、事实已落库」，负例实测 `assert 2 == 1`。
  L-02 按本包提的可选方案拆出 `plan()`/`record()` 后，适配器改为 **plan → 校验 → record**：
  落库对象**就是**被校验对象，**「拒绝 ⇒ 什么都没落」是结构性成立的**，竞态在构造上不可能存在。
  中间态（写前读 `service.graph`）已删除——它修好了时序但伸手进了 K8 内部属性。负例实测
  `records[invalidation_propagation] = 0`、`audit_events = 0`。**只有把两个真实模块合起来跑才会暴露。**
- **D-M05-10（实测发现，已裁决：不修，登记为契约缺口上报）**：**重试不安全**——`check()` 跑两次产出两条 K8 传播 +
  两条审计事件。实测 `attempt 1: records=1 audit_events=1` / `attempt 2: records=2 audit_events=2`；
  同一 plan 对象 `record()` 两次**不**翻倍（L-02 的幂等成立）。根因：`plan()` 每次新生成
  `propagation_id`，而 `record()` 的幂等键就是它。**K8 冻结契约没有幂等键** → **契约空白，不是实现 bug**。
  本包不擅自发明去重（那是改契约）；**也不为它写「断言重复」的测试**（会把待裁决现状固化成期望）。
  已写进 `check()` docstring + L3 §4 + §5.4。**owner 裁决：方向 ①（显式幂等键）才成立，但必须先由老板裁决
  「折叠语义是否成立」**——语义未定前技术选型无依据；方向 ②（确定性派生 id）有真实风险（会把时间演化的
  两次独立失效压成一条、丢失事实）。
- **D-M05-11（上报 owner）**：`/tmp/r007-frozen` 快照里的 `retraction.py`（`0278d049…`）是**迁移前的 ② 版**
  （读 `service.graph` 的写前校验），**不含**本轮 ③ 迁移。**当前交付 hash =
  `d071a503ceef7fc788e055ad0b5a300bd7d8e127e87b351248953273bc4c63ed`**
  （含 ③ 迁移 + 「结构性」宣称的限定 + D-M05-13 端口守卫）。→ **需以该 hash 重新冻结**。
  本包无权改他人的冻结快照，只报 hash + 差异。
- **D-M05-12（信息同步）**：L-02 的 live `invalidation.py`（`391644fe…`，382 行）≠ 其声明的交付 hash
  （`9a8ecaf4…`，332 行，＝冻结快照里那份）。live 版新增 `plan(..., propagation_id=None)` ——
  把「重试是否折叠」的**杠杆交给调用方**（方向 ③）。**本包适配器与两个修订都兼容**（各自 54 passed），
  且**刻意不传 `propagation_id`**（传它＝由 L-04 单方面决定折叠语义成立）。
- **D-M05-13（P2 残留，falsify-r007 独立复核发现，已修）**：`InvalidationSink` 是 `runtime_checkable`
  Protocol，而 `isinstance` **只查成员名不查签名** → 裸 `InvalidationService` **通过 isinstance 绿灯**，
  首次调用才抛裸 `TypeError`。**本包在当前修订上独立复现成立**（不是只看被复核的旧快照）。
  修法：① 协议加判别成员 `implements_retraction_sink`（`isinstance` 由 `True` → **`False`**）；
  ② `RetractionChecker.__init__` 接线期守卫，消息带修法（`wrap it: sink=K8InvalidationAdapter(service)`）；
  ③ 协议 docstring 写死规则 + 两条测试（离线形参测试 + 在**真实** service 上的陷阱测试）。
  **超出 reviewer 方案 (b) 之处（请 owner 知悉）**：把「绿灯」本身修掉并提前到**接线期**，
  而不是只标注成「有守卫的坑」；用既有 `PropagationRequiredError`，未新增错误类型。

## Completed

- 开工第 1 步：本 L3 写就（`docs/tasks/M05-retraction/tasks/L3.md`）。
- 开工第 2 步：`external_sources.py` 下游读取方清单（**实测**）。结论：`src/` 内**0 个生产导入方**，
  唯一既有消费者是 `tests/test_external_sources.py`（20 passed，未回归）；
  `scripts/`/`web/`/`configs/` 无引用；记下 1 个假朋友（`benchmark_trust.py` 的
  `hallucination_ratio` 来自 `benchmark.py`，与本模块同名函数无关）。
- 实现 `src/autoresearch/retraction.py`（337 行）：K10 枚举、全覆盖投影表、`RetractionChecker`、
  `InvalidationSink` 端口、`RetrievalDecision`、`k8_action_for`。
- 扩展 `src/autoresearch/external_sources.py`（673 → 869 行；`git diff --numstat` 实测
  **+196 / -0，纯追加**）：`AccessStatus`、`LicenceVerdict`、许可 helper、`verdict_from_message()`、
  `licence()`。
- `tests/test_m05_retraction.py`（46 条）+ `tests/fixtures/m05_retraction/crossref_responses.json`
  （**2026-09-15 真实抓取的 5 个 DOI**，含关系数组与 `license[]` 逐字保留）。
- 判别力实测：基线=符号缺失型（不计证据）；MUT-1（`UNKNOWN→ACTIVE`）**10 failed**；
  MUT-2（任何许可→`OPEN`）**11 failed**；MUT-3（抹平 `source_status`）**5 failed**，均为判据型。
- owner 复核后追加（2026-09-15）：① 补「投影可归并 / 审计不可归并」测试
  （`test_not_found_and_unknown_merge_at_the_projection_layer_only`）；
  ② `retraction.py` docstring 写死「`ACTIVE` 不蕴含今日可达」+ `test_active_with_a_degraded_transport_is_flagged`；
  ③ 新增 MUT-3 探针，证明第 ① 条真的拦得住「抹掉 `source_status`」的变异。
- **D1/D2 接缝修复 + `plan()`/`record()` 迁移（2026-09-15）**：新增 `K8InvalidationAdapter` +
  9 条跨 lane 测试（见 D-M05-07/08/09/10）。**8 条跨 lane 测试在本 base 上 `importorskip`**；
  当天用**合并树**取证（L-02 真实 `invalidation.py`，sha256 `9a8ecaf4…`）：
  **54 passed / 0 skipped / 0 failed**，且实拍到 `InvalidationPropagation` 落库 +
  `invalidation.propagated` 审计事件，负例路径零落库。

## Pending

- team-lead / owner 审阅合入。
- **合入时必做**：删掉 `tests/test_m05_retraction.py:744`（`_k8()` 内）那**一处**
  `pytest.importorskip`——它服务 **9** 条跨 lane 测试；不删则接缝回归可以「跳过到全绿」。
- **D-M05-10 待裁决**：K8 传播的重试语义（是否加幂等键 / `propagation_id` 是否确定性派生）。
- 本包提出的「plan/record 两步拆分」建议**已被 L-02 采纳并落地**，本包适配器已迁到新 API
  （不再读 `service.graph`）。

## Next step

team-lead 审阅后决定是否合入；D-M05-01 已裁决维持并落地完毕；D1/D2 已修并取证。

## Verification

- [x] 基线（改动前，本 worktree）`537 passed / 2 skipped / 0 failed`
- [x] focused `pytest tests/test_m05_retraction.py -q -o addopts="" -W error` → `49 passed, 9 skipped`
- [x] 全量 `pytest -q -o addopts="" -W error` → `586 passed / 11 skipped / 0 failed`
- [x] **合并树**（我的 `retraction.py` `d071a503…` + L-02 `invalidation.py` `391644fe…`）→ `58 passed, 0 skipped / 0 failed`
- [x] 端口守卫实测（合并树）：`isinstance(raw InvalidationService, InvalidationSink)` `True` → **`False`**；
      直传裸 `TypeError` → **`PropagationRequiredError`**（消息带修法）
- [x] 折叠语义三场景实测（A 折叠返回原始记录 / B 变宽抛 `InvalidationContractError` 且零半写 / C 身份含 blast radius ⇒ 新事实无硬错误），已记入 L3 §5.6 供 owner 裁决
- [x] **跨 lane 测试的 skip↔pass 对应关系已逐 ID 核实**：本 worktree 里 9 条 skip；
      同一 9 个测试 ID 在合并树上单跑 → `9 passed`；`49 + 9 = 58`（= 收集总数）
- [x] 兼容性：与 L-02 的 live 修订（`391644fe…`）同样 `54 passed / 0 skipped`
- [x] `/tmp/r007-frozen` 里的 `retraction.py` = `0278d049…`（**② 迁移前版本，非本轮交付**）→ 已上报 D-M05-11
- [x] 负例不落库实测：`records[invalidation_propagation] = 0` / `audit_events = 0`
- [x] B5 回归 `pytest tests/test_external_sources.py -q -o addopts=""` → `20 passed`
- [x] `ruff check src tests` → `All checks passed!`
- [x] `compileall -q src` → exit 0
- [x] 断网探针（socket 全封）`pytest tests/test_m05_retraction.py -p m05_nonet` → `46 passed, 7 skipped`
- [x] `node .ai-team/check.mjs --base main` → `Result: valid`
- [x] 禁区核对：`search_service.py`/`contracts.py`/`storage.py`/`knowledge.py`/`application.py`/
      `api.py`/`cli.py`/`tests/test_external_sources.py`/`tests/fixtures/external_sources/` 实测
      **UNTOUCHED**
- [x] 探针 1/2/3/4（符号缺失型 / MUT-1 / MUT-2 / MUT-3）输出已记入 L3 §5.3

## Handoff note

- From: `impl-l04-retraction`
- To: `team-lead`
- Required: `external_sources.py` 下游读取方清单、K10 三条不变量落地、四条负例各自断言什么、
  N-4 字段方向的真实 payload 验证路径、判别力实测数字、**D1/D2 接缝修复与合并树取证**、
  **合入时删 `importorskip` 的提醒**、未闭合项（D-M05-02~05、Sink 竞态分支）。
- 未提交、未推送；改动停在本地 worktree。
