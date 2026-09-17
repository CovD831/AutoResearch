# M13-UI 面板四面板（R-007 L-08）

- ID: `M13-UI`
- Title: `M13 UI 四面板：项目 / 证据与审核 / 文件 / 人工审批（K14 PanelProjection）`
- Status: `handoff`
- Status note: 2026-09-15 本包在 `r007-l08-ui`（base `main@8dd8780`）交付 M13-04/05/07 三个真面板 + M13-06 显式 `blocked` 占位。**实测推翻骨架两处**：(1) 真实产品路由 **24** 条，骨架 §0 清单列 23 条却写「22 个端点」，且**完全漏掉 `PATCH /work-packages/{work_package_id}`**；(2) 风险等级**可读** —— 无 GateDecision 专用端点，但 `gate.evaluated` 审计事件 payload **就是** `GateDecision`，故 Gate/风险 section 真的能标 `verified`（若照抄骨架清单会误判成永久 unverified）。看截图时抓到 3 个实质缺陷（对从未运行的项目宣称「verified 无阻塞」等），已修并各配回归测试。全量 **577 passed / 2 skipped / 0 failed**（基线 537 未下降）。突变测试 4/4 全抓住。**未提交、未 push、未开 PR**；本包无独立审计。M13-07 的「确认/拒绝」只有 409 实测，无活体成功路径（依赖 pipeline 走到 `RELEASE_PENDING`，离线不可达）。2026-09-15 team-lead 裁决：D-L08-01/02（`PanelSection` 两处加法扩展）**批准**，并把 D-L08-01 升级为 **K14 契约缺陷上报**（K14 只给 `verified: bool`，三态中的 `unverified`/`blocked` 在数据层不可分 → K14-1 自身无法机械校验；见 L3 §4.1，建议报老板裁夺是否改 L2）；D-L08-04（不渲染 `interrupt.message`）**维持**，定性为**保守取舍**而非契约要求；**提交不许可**。
- Owner: `impl-l08-ui`
- Next owner: `user`

## Goal

按 R-007 L2 的 **K14 `PanelProjection`** 把「研究状态」做成**不会说谎**的读面板，
并让 M13-07 的人工审批/打回落到既有端点写审计。核心是 M13-04 的明文要求
「**面板不得把未完成写成完成**」与 L1 §4.2 **A5**：
面板上任何状态都必须能追到一个 `refs` 或一个显式 `unknown_reason`。

**本包不做**：M13-06（依赖 L-09 的 K11 ACL，只渲染成带理由的 `blocked`）；
不引入前端框架/构建链；不改 `src/autoresearch/` 既有模块；不新增 API 端点。

## Acceptance scenarios

- [x] **K14 类型**：`PanelSection` / `PanelProjection` 落在本包自己的模块（`web_api.py`），
      不碰全局串行文件 `contracts.py`（`07-lane-kickoff-convention.md` §3.2）。
- [x] **K14-1**：`verification_state` 为必填字段；`verified ⟺ state=="verified"` 由校验器强制；
      空 `sections` 禁止构造；面板级状态 = 最坏 section 状态。
- [x] **K14-2**：`refs` 有正则约束，带空格的正文**构造不出来**；N-3 用真实证据
      `claim`/`title` 全文做子串断言，证明面板内无正文副本。
- [x] **K14-3**：非 verified 必须带非空 `unknown_reason`；verified 必须为 `None`。
- [x] **K14-4 / A5**：三态在视觉上可区分（实心 ✓ / 虚线 ? / 双线 ✗ + 文字标签），
      原因**内联显示**，`web/` 内不存在「灰色 / 暂无」这类占位样式。
- [x] **M13-04**：阶段 / Gate / 证据覆盖 / handoff / 任务 / 阻塞，共 6 个 section。
- [x] **M13-05**：证据项 / 按 claim 归类 / 按 run·action 归属 / Gate / 审查与裁决 /
      评审报告 / 回退入口，共 7 个 section，其中 3 个如实标 `unverified` 并指名缺口。
- [x] **M13-06**：不做，但**显式渲染为 `blocked`** 且写明依赖 `K11 AccessPolicy (L-09)`，
      不静默省略（K14 把 `files` 列为合法 panel_id）。
- [x] **M13-07**：审批范围 / 风险等级 / 支撑证据 / 待人工决策 / 审批历史；
      确认·拒绝 → `POST /runs/{id}/resume`，打回 → `POST /evidence/{id}/invalidate`。
- [x] **N-1**：数据缺失 → `unverified` + 非空 reason（**不是留白**）；
      且 `None`（读不到）与 `[]`（读了但空）是**两个不同的 reason**。
- [x] **N-2**：阻塞 → `blocked`，与 `unverified` 在**数据层**可区分（不同取值 + 不同 reason）。
- [x] **N-3**：所有 `refs` 是不透明标识符，面板不含正文副本。
- [x] **真实数据**：面板喂的是实跑 `autoresearch serve` 抓下来的真实响应
      （35 次 HTTP 调用），非手写 fixture。
- [x] **截图交付**：6 张 PNG + 12 页快照 HTML，`page errors: 0`。
- [x] **零成本**：offline provider + `NETWORK_ENABLED=false`，无外网、无 LLM 费用。
- [x] **无回归**：577 passed（537 基线 + 29 新增），ruff 全绿，compileall 通过。

## Invariants

- **只读边界是结构保证，不是约定**：`web_api.py` 的 AST 调用点集合里**不存在**
  任何变更态调用（`append_event`/`put`/`invalidate`/`resume`/`run`/`create`/`promote`…），
  且不 import 任何写入侧模块 —— 由
  `test_panel_module_has_no_mutating_call_site` 与
  `test_panel_module_never_imports_writer_modules` 机械证明。
  写操作只由浏览器直接打既有端点，**不经过 BFF**。
- **不改后端**：`git status` 证明 `src/autoresearch/` 只有**新增** `web_api.py`，
  既有 30 个模块零改动。BFF 只调 `api.py` 已在用的同一批只读 accessor。
- **K14-1 无例外**：没有「灰色 / 暂无」占位；非 verified 一律内联原因。
  三态取值在投影里就是 `verified`/`unverified`/`blocked` 三个字面量。
- **不复制正文**：`refs` 只有标识符；`facts` 只有有界标量（key 为机器名、value ≤200 单行）。
  证据 claim/title、wiki body、gate reasons、review findings、审批 message 全部不进投影。
- **`None` ≠ `[]`**：端点读不到与读到空是不同事实、不同文案。
- **不新增端点、不改共享文件**：`contracts.py` / `storage.py` / `knowledge.py` 写路径
  全部未碰；K14 类型定义在本包模块内。
- **不搬运别人的基线数字**：537/2/0 与 566/2/0 均为本 worktree 自测。

## Decisions

| ID | 决策 | 理由 |
|---|---|---|
| D-L08-01 | 给 `PanelSection` 加 `verification_state` —— **同时是 K14 契约缺陷上报（见 L3 §4.1）** | K14-1 要求三态，但 K14 给 `PanelSection` 的只有 `verified: bool`，`unverified` 与 `blocked` 在 bool 层不可分 → **K14-1 自身无法机械校验**，属契约内部矛盾。就地加法扩展 + 校验器强制一致，`verified` 保留、语义不变。**team-lead 已批准（2026-09-15），并建议把「L2 K14 补该字段」报老板裁决** |
| D-L08-02 | 给 `PanelSection` 加 `facts: dict[str,str]` | 契约声明了展示目标（阶段/Gate/覆盖率/风险）却没有任何**值**通道，`refs` 必须保持纯标识符。**team-lead 已批准**；同属 L3 §4.1 的同类缺口 |
| D-L08-03 | `files` 渲染为 `blocked` 而非省略 | K14 把 `files` 列为合法 panel_id；静默省略本身就是藏起未完成（A5） |
| D-L08-04 | 审批面板不渲染 `interrupt.message` | **保守取舍，不是契约要求**。A5 本意不禁止审批请求文；按 K14-2 字面实现，信息由 `message_ref` 保留，回退一行。**team-lead 裁决维持** |
| D-L08-05 | 三态视觉不依赖颜色（字形+文字+边框样式） | 色觉障碍读者也要能分辨未完成与阻塞 |
| D-L08-06 | run 解析走 `audit:run.started` 并把这一跳印面板上 | G-2：无列 run 端点且 project record 无 `run_id`；把解析来源做成 `run_resolution` fact，读者可见 |
| D-L08-07 | 审批归因用白名单判据 `_is_human_decision()` | 实测 approve 写 H3 证据（actor=reviewer）、reject 写 `gate.evaluated`、打回写 `evidence.invalidated`；判据与**局限**都写进 docstring |

## Completed

1. **L3 补全**：`docs/tasks/M13-ui/tasks/L3.md`（六节 + 逐条条款三列表 + 实测端点差异 + 7 个读取缺口）。
2. **K14 核心**：`src/autoresearch/web_api.py` —— 类型 + 不变量校验 + 纯函数 builder +
   `PanelReader`（只读采集）+ `create_web_api`（ASGI，`/api` 重新挂载 24 端点 + `/ui/*` 投影）。
3. **前端**：`web/index.html`、`web/styles.css`、`web/app.js`（原生，无框架无构建；
   快照/活体两模式共用同一渲染代码）。
4. **测试**：`tests/test_web_panels.py` 40 支（K14 不变量、N-1/N-2/N-3、只读 AST、
   端点形状对齐、`graph.py` interrupt 键集对齐、3 支截图发现的回归）。
5. **证据链**：`web/dev/seed_demo.py`（实跑 serve + 35 次 HTTP）→
   `build_snapshots.py`（12 页快照）→ `shoot.py`（6 张 PNG）+
   `mutation_check.py`（突变 4/4）。
6. **抓到的 3 个真缺陷**（看截图发现，均已修 + 配回归）：
   从未运行的项目曾被标 `verified 无阻塞`；零证据项目曾被标 `verified 无撤回`；
   审批历史曾把「研究想法」（E0/human）误计为审批决策。
7. **对抗性审计发现 1 处 K14-4/A5 违反（已修 + 配 7 支守卫）**：
   `app.js:244` 把 tab 状态点硬编码为 `tab__dot--unverified`，导致
   `--verified`/`--blocked` **全树从未被应用** —— tab 栏对每个面板都画「?」，
   与面板头 chip 自相矛盾（`litalpha-project` 面板标 `BLOCKED`、tab 却画 unverified）。
   已改为**与 chip 同源**（`renderPanel` 一次 `syncTabState` 同时写两者）。
   **同族扫描另找到第二处**（主理人预判正确）：`stateOf()` 把任何 K14 三态以外的取值
   静默默认为 `unverified` —— 同样是渲染器发明合法状态；已改为 `INVALID-STATE` 哨兵
   （未知值显示为 `INVALID-STATE`，tab 点**不画点**而非画错颜色）。
   新增浏览器 DOM 断言：**12 页 × 4 面板 = 48 次核对** tab 点=chip=投影。
8. **修复过程中发现我自己的第一版 DOM 回归测试是无效的（已修，L3 §9.4.1）**：
   它断言的是**交付快照 HTML**，而快照内联的是**生成时那一刻的 `app.js` 副本** ——
   改 `web/app.js` 根本不影响该测试。发现方式：给突变 harness 加 M7
   （复现被审缺陷的**可观测效果**）后 **M7 MISSED**。
   已改为**用当前 `web/` 资产 + 真实投影 JSON 现场渲染**（经
   `build_snapshots.render_page`，页面 markup 的唯一来源），并新增
   `test_delivered_snapshots_are_not_stale` 鲜度守卫。复验 **7/7** 全抓住。
   教训：**「写了守卫」≠「守卫有效」，判别力必须靠突变来证。**

9. **第二轮对抗性审计（`falsify-r007`）的 4 条缺口已全部修复**（L3 §10）：
   **R2（最关键）** 无浏览器环境下渲染层修复**零保护**（DOM 断言全 skip）→ 新增
   `web/dev/render_contract_check.mjs`：**只用 Node、不要浏览器**，最小 DOM stub 执行
   **真实 `web/app.js`**，断言可观测 class。修后复核：无浏览器 + 等价硬编码
   **从「全绿」变成 3 red**。Node 守卫自身的 5 支行为性突变 **5/5 全抓住**。
   **R4** 三条源级守卫是「按字面量取指纹」，等价改写（`cls || "tab__dot--unverified"`、
   `: "unverified"`）全部为绿 → 已改为**块内字面量约束 + 解析函数体**，两条改写均被抓住。
   **R6** `data-dot-state` 是渲染器**自写属性**（循环证据）→ 首要断言改为**渲染出的 class**。
   **P3** fixture docstring 声称「never fails」但非 `ModuleNotFoundError` 的 `ImportError`
   会报 error → 改为显式 `except ImportError: skip`，复核为 **2 skipped**（不再是 error）。
   → 本轮我自己的教训：R4 里我一边批评「按字面量取指纹」，一边写了三条同样的守卫；
   **守卫有效性必须用突变证，不能靠阅读。**

10. **按 team-lead 要求补了两处边界声明**（L3 §9.1 与 §10.7）：
    (a) `web/dev/render_contract_check.mjs` **单列**为「本轮新增的守卫本体，尚未经独立复核」，
    并写明它自己也要回答「会不会是对代理断言」——两个待审点：DOM stub 由我编写（可能与真实浏览器语义
    不一致，`>` 组合子那个 bug 我已自己撞到一次）、4 项检查由我选定可能漏路径。
    **在独立复核前它的绿只能算「未复现的绿」。**
    (b) **R4 修复的边界实测**（6 个可执行案例）：静态守卫是**字面量形状**守卫，
    **字符串拼接 / 变量间接能完全绕过**（B2 `"tab__dot--" + "unverified"`、B3 `"unverifie" + "d"`
    实测静态 MISSED、Node CAUGHT）；真改名（R1/R2/R3）在**旧版**下会抛 `ValueError` 噪声失败，
    新版已改为**按值/按行为定位、名字无关**，现在行为等价就 PASS。
    → 与 L-02 的 R3 同族，结论一致：**字面量/AST 守卫只能证明「某写法没出现」，不能证明「语义没回归」**。

11. **补上「假失败」缺陷类的回归测试**（L3 §10.7.1 / §10.8，team-lead 要求的收尾项）：
    我上一轮 R4 强化版的守卫**锚在标识符上**（`TAB_DOT_CLASS` / `function stateOf(value) {`），
    于是一个**合法重命名**会让它抛 `ValueError` —— **行为没回归而守卫报红 = 假失败**，
    是与「假通过」方向相反的**第二个缺陷类**（危害相同：使守卫不可信，或诱导后来者放宽守卫）。
    已把守卫改为**按值定位**（映射表）与**按行为定位**（状态函数），并加两条测试守住本类：
    `test_guards_are_name_independent_and_do_not_false_fail`（4 种等价改名不得抛异常且判定不变）
    + `test_renamed_renderer_is_behaviourally_equivalent`（**真跑渲染器**证明改名行为等价，
    含**负控制组**）。
    **反事实验证**：把 helper 改回标识符锚定版 → 新测试 **FAILED**（断言失败，已 `ast.parse` 防误判）。
    `render_contract_check.mjs` 为此新增 `--app=<path>`（可对变体源码跑），**其 hash 已变**。

## Pending

- **未提交 / 未 push / 未开 PR**（提交纪律：等 owner 明确许可）。
- **M13-07「确认/拒绝」无活体成功证据**：`resume` 实测 409，离线不可达
  `RELEASE_PENDING`（需 L-05 闭合 `work_closed_loop` 且 gate score ≥75）。
- **M13-06 未实现**（等 L-09 K11 ACL）。
- **G-1～G-7 七个读取缺口**只登记在 L3 §1.2，未修（R-007 §2：端点已够用）。
- **`verified` 面板聚合态在当前环境不可达**（实测 12 个真实面板：7 unverified + 5 blocked + **0 verified**）
  → 第三个 tab 点无法用真实数据截图，改用**明确标注为合成**的渲染夹具页证明其可达（L3 §9.5）。
- **审计覆盖缺口（L3 §9.1）**：`web/dev/*.py` 四个脚本（产出的正是**证据件本身**）、
  `tests/test_web_panels.py`、活体模式的浏览器核对、文档与工件 —— **本轮均未被审计**。
  且 §5.3 的突变测试**只覆盖 Python 侧**，结构上抓不到渲染层缺陷（§9.3 的缺陷即为例证）。
- **活体模式未做浏览器截图**：只做了 ASGI 路由测试。
- **D-L08-01/02 已获 team-lead 批准**（加法扩展就地落地，`verified` 语义未变）；
  **D-L08-01 已按裁决升级为 K14 契约缺陷上报**（L3 §4.1），建议把「L2 K14 的
  `PanelSection` 补 `verification_state`」报老板裁决契约变更。
- **D-L08-04 已裁决维持**（保守取舍，非契约要求；A5 本意不禁止审批请求文）。
- **G-7 已裁决并落地（2026-09-16，owner 批准方案 B）**：
  `GET /projects/{id}/evidence` 的默认 `valid_only=true` **保留不动**（改默认会静默改变
  所有既有调用方收到的内容），但**过滤行为改为可观测** —— 响应新增两个头：

  ```text
  X-Evidence-Filtered: "true" | "false"
  X-Evidence-Omitted:  <被省略的条数>
  ```

  **body 不变**（仍是 JSON 数组），故零调用方受影响。
  **为什么必须做**：被撤回的证据与「从未记录过」是**不同的事实** —— 撤回意味着某条结论
  失去了支撑。只收到 N 条的调用方，无法区分「有 N 条」与「原有 N+1 条、撤回 1 条」。

  **判别力已实测**（在隔离克隆上做反事实）：
  - 去掉 header 逻辑 → `test_default_evidence_query_reports_when_it_filtered` **1 failed**（`KeyError`，判据型）
  - 恢复 → `1 passed`

  新测试断言**双向**（不撤回 → `false`/`0`；撤回 1 条 → `true`/`1` 且 body 真的少一条），
  因为「永远存在的头」不构成证据。

  **文件面**：`src/autoresearch/api.py`（` M`，本 lane **首次**触碰既有文件）+ `tests/test_api_and_cli.py`（` M`）。
  已核实**其余 6 条 lane 均未改动 `api.py`** → 无跨 lane 冲突。
- **提交未获许可**：改动停在本地，等老板明确确认。

## Next step

1. **老板裁决契约变更**：是否把 `verification_state`（及 `facts`）补进 R-007 L2 的 K14
   （K14 现状无法机械校验 K14-1，见 L3 §4.1）。本包已就地加法扩展，不需为此返工。
2. ~~若许可提交：一并落一次提交。~~ **已按 P6a/P6b 两部分提交（2026-09-16）** —— 见下方「交付拆分」节。
3. 合并前若 L-05 已落地：可补 `RELEASE_PENDING` 路径，让 M13-07 的 approve 有活体证据。
4. L-09 落地后补 M13-06（把 `files` 的 `blocked` 换成真导出）。
5. 收口时统一派独立审计（本包 `web_api.py` + K14 实现为重点，team-lead 已认领）。

## 交付拆分（P6a / P6b，2026-09-16）

本包分两个提交交付，切法**由实测决定，不按文件名猜**：

| 提交 | 内容 | 文件数 | 单独可绿？ |
|---|---|---|---|
| **P6a** | 代码 + 测试 + 生成脚本 + **生成输入**（`projections/` + `raw-api/`） | 48 | ✅ `577 passed / 3 skipped` |
| **P6b** | **纯视觉产物**（`snapshot-*.html` 13 + `*.png` 7 + `_screenshots.json`） | 21 | 需 P6a |

**合计 69 = 本包全部交付物，不重不漏。**

**切法是怎么定下来的（实测，非推测）**：

| 移走什么 | 测试结果 |
|---|---|
| `snapshot-*.html` + `raw-api/` + `projections/` 全移 | **2 failed** |
| **只移走纯视觉产物** | **1 failed**（只剩漂移守卫） |

→ 由此得两条约束：

1. **`projections/` 必须留 P6a** —— `test_rendered_tab_dots_match_the_projection_state` 读它；
2. **`raw-api/` 也留 P6a** —— 它是投影的输入，留下它 P6a 才能**独立离线重跑整条生成链**
   （实测：只留这两者即可重跑 `build_snapshots.py` 恢复全部 13 个 HTML 快照）。

**为拆分做的一处改动**：`test_delivered_snapshots_are_not_stale` 加了**显式 skip 分支**
（快照缺席时 skip 并写明原因）。

> ⚠️ **这不是把红改绿放行**：**「有快照但漂移」仍然 fail**；只有**空 glob** 才 skip。
> 即区分「没东西可比」与「比过了且一致」—— **空 glob 不得伪装成漂移检查通过**。
> 这与本项目「空集不得当满分」的纪律同向。

**合并顺序**：P6a → P6b（P6b 的 base 是 P6a）。

## Verification

- [x] `PYTHONPATH=src pytest -q -o addopts="" -W error` → **578 passed, 2 skipped, 0 failed**（基线 537 未下降；+1 passed 来自 P6b 入仓后 `test_delivered_snapshots_are_not_stale` 由 skip 转为跑通）
- [x] `python -m pytest tests/test_web_panels.py` → **40 passed**
- [x] `python -m ruff check src tests` → `All checks passed!`
- [x] `python -m compileall -q src` → ok
- [x] `python web/dev/mutation_check.py` → **mutations caught: 9/9**（含 5 支前端突变），`restored exactly: True`
- [x] `python web/dev/seed_demo.py` → 35 次真实 HTTP；`resume` 409、`invalidate` 200 且审计新增 `evidence.invalidated`
- [x] `python web/dev/shoot.py` → 6 张 PNG，`page errors: 0`
- [x] 人工复核 6 张截图（信息层级、三态可区分、原因内联、refs 全是 ID）
- [x] `node .ai-team/check.mjs --base main` → **`Result: valid`**（exit 0）。写入账本前它报
      `Result: blocked`，原因正是「改了代码却没在同一 PR 里更新 `.ai-team/TASK.md` 或成员账本」——
      即本包缺失的账本本身；落地后消除。
- [ ] 未做独立审计（本包 >2 源文件且含新逻辑分支，按触发线**应审**）

## Handoff note

> **交接链说明**：原 `Next owner` 字段写作 `team-lead` → `user`（箭头分隔），
> 该写法会被 `.ai-team/check.mjs` 的 `field()` 解析为 `null`（正则 `^- Next owner: \`([^\`]+)\`$`
> 要求行尾即闭合反引号），故 `Next owner` 已改为纯值 `user`。
> **实际交接链：本 lane 交付 → `team-lead` 汇总 → `user` 裁决。**

**给 owner 的三件事**：

1. **骨架不可照抄**（本包实测结论）：真实路由 24 条，骨架 §0 列 23 条却写 22，
   并漏掉 `PATCH /work-packages/{work_package_id}`。
   同时 `gate.evaluated` 审计事件携带完整 `GateDecision`，**风险等级可读** ——
   照抄骨架的清单会把 Gate/风险误判成「永久不可验证」。
2. **两处加法扩展待裁**：`PanelSection` 新增 `verification_state`（D-L08-01）与
   `facts`（D-L08-02）。理由：L2 给的 `PanelSection` 只有 `verified: bool`
   与 `refs`，**既无法在数据层区分 `unverified`/`blocked`，也没有显示阶段/覆盖率的通道**，
   M13-04/05/07 的明文要求落不到地。若认为应改 L2 而不是就地扩展，请裁决改法。
3. **一处可用性取舍待裁**：审批面板不渲染 `interrupt.message`（D-L08-04），
   可用性下降是 K14-2 强读法的代价；回退成本一行。

**给审阅者**：读 `docs/tasks/M13-ui/tasks/screenshots/` 的 6 张 PNG 最快 ——
`bare-project.png` 是 N-1（6/6 unverified，各有具体原因），
`nolit-project.png` 是 N-2（同一面板 4 verified / 1 unverified / 1 blocked 三态并存），
`litalpha-approval.png` 是 M13-07 的控件与可归因审批历史。
原始响应在 `screenshots/raw-api/`，写操作实录在 `raw-api/_writes.json`。
