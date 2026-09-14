# S4-A6 Bibliographic Claim & Partial Failure

- ID: `S4-A6-BIBLIOGRAPHIC-CLAIM`
- Title: `S4 evidence claims describe the actual material; partial provider failure is visible`
- Status: `active`
- Status note: 处置第二轮独立盲审提出的 **F4**（畸形/缺失命中铸成受信任 E1，且 claim 与 wiki 正文自相矛盾）与 **N1**（部分 provider 失败被静默：有 papers 即 COMPLETED）。两项均实测复现为真。修法：提取**共享书目写入函数**（A1 parity 由"两个编辑者记得同步"改为**结构性**保证）+ claim 按实际材料书写 + 不可归属的**检索命中**拒绝铸 E1（用户 seed 不受限）+ `InvocationReceipt.provider_failure` 把部分失败作为**事实**穿过 A4 边界（**不改 `_status()` 既有语义**）。基线 `1488cdd` 538 passed → **548 passed / 2 skipped / 0 error**（两轮：546 后经第 3 轮独立审查再修）。**判别力两轮合计 11 failed，全部判据型**（5 + 6）。
- Owner: `user/team`
- Next owner: `user/team`

## Goal

让「证据的声称」与「证据的实际内容」一致，并让「部分失败」在信任链上可见。两项都是本项目核心信任声明（"没证据不让你声称完成"）的直接支撑。

## Acceptance scenarios

- [x] 无 abstract 的命中：claim **不声称** abstract 存在（先前与同一调用写出的 wiki 正文 `"No abstract was supplied."` 矛盾）。
- [x] 有 abstract 的命中：claim **声称** abstract 存在，且 `metadata.abstract_present=True`。
- [x] 无 DOI/URL/provider id 的**检索命中**被**拒绝**，不铸 E1，且写诊断。
- [x] 无标识的**用户 seed** 仍被接受，`independent_source="user_supplied:<source>"`。
- [x] `"s:None"` 这类占位 provenance 不再产生。
- [x] 部分失败（主源挂 + 次源有产出）：`outcome.provider_failure=True`，且**穿过 A4 边界**后 `receipt.provider_failure=True`，同时 `receipt.status` 仍为 `COMPLETED`。
- [x] 健康运行不误报失败（flag 有区分度）。
- [x] 旧 idempotency 记录（无 `provider_failure` 字段）反序列化正常、replay 不受影响。

## Invariants

- 证据 claim 必须描述**实际存在的材料**；同一记录的两处陈述不得矛盾。
- 不可归属的**检索命中**不得铸 E1；用户 seed 的归属是用户本人。
- 部分失败是事实，必须可观测；不得因"有结果"而隐藏。
- 两条检索路径的持久化**同源**（A1 parity 结构性保证）。
- **不改 `_status()` 语义**（A1 决策：有 papers 即 COMPLETED）。
- **不改 `parity-report.json`**（A1 历史验收证据，改它等于伪造记录）。
- 不改 `contracts.py` / `storage.py` / `evidence.py` / `gates.py`。

## Decisions

- **D-A10-01 提取共享写入函数而非同步两份复制**（skill 3.5「照搬语义 ≠ 复用原语」）：`persist_bibliographic_record` 由两条路径共同调用。A1 的 `durable_facts_equal` 此前靠人工同步维持，**这正是矛盾 claim 能在两处同时存活的原因**。
- **D-A10-02 可归属判定放在调用点，不放 `_persist` 内**：A2 故障矩阵 override 的是 `_persist(self, paper)`（`tests/a2_runtime_fixtures.py:167`）。给它加 kwarg 会让 crash 注入**静默失效**（实测：两条 A2 测试变红，`recover_pending` 报 "already finalized"）。**这是「注入点会随实现迁移」的又一次实证。**
- **D-A10-03 拒绝而非抛错**：一个不可归属的命中只跳过 + 记诊断，不使整轮检索失败。
- **D-A10-04 用户 seed 豁免 provenance 要求**：`PaperRecord.doi/url` 是可选字段，合法 seed 可能没有标识。第一版无条件拒绝**连 seed 一起拒了**（测试当场抓到），属过度收紧。
- **D-A10-05 部分失败用独立布尔字段承载，不改 `_status()`**：status 是 A1 的既有语义（有 papers 即 COMPLETED）；"有源失败"是另一维度的事实，两者并存。
- **D-A10-06 `parity-report.json` 有意不更新**：它是 `p1-a-parity-report/v1` 的 A1 历史验收证据。claim 文案已变更一事记录在 `L3.md`，而非回填历史文件。

## Completed

- `search_service.py`：新增 `evidence_claim_for` / `independent_source_for` / `persist_bibliographic_record`；`_persist` 改为委托；`candidates` 带 `user_supplied` 标记。
- `adapter_search_service.py`：`_persist` 改为委托；调用点做可归属判定。
- `invocation_contracts.py`：`InvocationReceipt.provider_failure`。
- `capability.py`：`_outcome_parts` 返回该事实；`_build_result` 写入；异常路径与 `recover_pending` 置 `True`。
- `application.py`：`InvocationBoundedSearchPort` 读 `receipt.provider_failure`。
- `tests/test_adapter_search_service.py`：+8 条判据测试。
- 包内 `task-package.json` 与 `L3.md`。

## Pending

- N2（`_status()` 以诊断关键词推断状态）未处理，见 Not closed。

## Next step

- 与 A8/A9 同分支提交，一并通过保护窗口合并。
- 合并后 A 线下一包为 A7（knowledge 向量检索）。

## Verification

| 项 | 命令 | 结果 |
|---|---|---|
| 全量 | `pytest -q -o addopts="" -W error` | **546 passed / 2 skipped / 0 error**（基线 `1488cdd` = 538） |
| 聚焦 | `pytest tests/test_adapter_search_service.py` | 30 passed |
| ruff / compileall | — | clean / ok |
| `check.mjs` / `check_pr_contract` | — | valid / passed（18 paths / 2 ledgers） |
| 判别力 | 基线 `1488cdd` + 符号 shim | **5 failed，全部判据型** |

## Handoff note

- **判别力必须用 shim**：裸跑基线得 6 failed 但全是 `AttributeError`（符号缺失型，按口径不计入证据）。需注入**只补符号、不改行为**的 shim（receipt 补字段；补 `independent_source_for` 但不接入 `_persist`）才能取得判据型失败。**这是本项目第三次使用该手法**（A9 常量 shim、A8 字段 shim、本次）。
- **改动 `_persist` 签名会打断 A2 注入**：接手者若要在 `_persist` 上加参数，必须先跑 `tests/test_runtime_hardening.py`。
- `parity-report.json` 的 claim 文案与当前实现不一致，**属有意为之**，不要"顺手修正"。

## 第三轮独立审查（审本包修复本身）—— 抓出 3 条，全部为真

派发独立子代理审查 `764cab1`（skill M6：修完的改动本身要再过一遍独立审查）。回传 3 条，**逐条实测复现为真**：

| # | 级别 | 发现 | 实测证据 |
|---|---|---|---|
| **R3-1** | **高** | **N1 的决策级可见性未生效**：`provider_failure` 只在 `if not outcome.papers:` 分支内被读取（`paper_search.py:56`），而 **N1 的目标场景恰恰是「有论文 + 部分失败」** → 代码跳过整个分支，`lifecycle_state=literature_searched`、`blockers=[]`、照常发 handoff，**事实在决策点被丢弃** | 复现：stub 返回 `papers=[...], provider_failure=True` → `blockers=[]`、发 handoff |
| **R3-2** | 中 | **修复不对称**：legacy `PaperSearchService` 从不设 `provider_failure`（失败只写诊断文本），经 `PaperSearchCapabilityAdapter` 走 legacy 时部分失败永远不可见 | `legacy outcome.provider_failure = False` 即使有 connector 失败 |
| **R3-3** | 中 | **F4 在 legacy 路径过度收紧**：`CrossrefConnector` 的 `source_record_id = work.get("DOI")`，无 DOI 的记录两个标识都是 None → **被静默拒绝**（仅留文本诊断，下游不知情） | 静态确认 + 与 adapter 路径不一致 |

**审查者还指出我的测试给了假安全感**：`test_the_agent_branches_on_the_flag_not_on_the_wording` 的 stub 用 `papers` 默认空，**只覆盖零论文分支，从未覆盖 N1 的「有论文 + 部分失败」场景** —— 属「覆盖了但没锁住结论」。

> **这是我第三次犯"改了传递层、没改消费点"的错**（前两次：diagnostics 措辞、`_persist` 签名）。三次都是同一个形状：**事实被送到了某个地方，但没有任何决策读它**。

### R3 修复

1. **`ResearchState.warnings`**（非阻断告警通道，与 `blockers` 语义分离）：有论文但检索不完整时写入告警，**流程继续**（有论文就该继续读），但事实进入机器可读通道。
2. **`paper_search` 在成功路径消费该事实**：不再只在空结果分支里读。
3. **legacy 路径也置 `provider_failure`**：两个 connector 失败处置位，结尾写入 outcome。
4. **`SearchOutcome.refused_records` / `InvocationReceipt.refused_records`**：被拒记录**计数结构化**，穿过 A4 边界，agent 层进 warnings。

### R3 判别力

基线 `764cab1` + 符号 shim（补 `ResearchState.warnings` / `SearchOutcome.refused_records` / `InvocationReceipt.refused_records`，**均不改行为**）→ **6 failed，全部判据型**。裸跑为 8 failed 但全 `AttributeError`（符号缺失型，按口径不计入证据）。

### 去重

第 3 轮补测试时产生了 3 条与先前重复的用例，已删除（38 → 35 条聚焦测试；全量 554 → 548）。

## 第四轮独立审查 —— 抓出「比'没人读'更严重」的一条

派发独立子代理审查 `81cf131`。回传结论：**`warnings` 不只是没人读，它在运行时根本不存在。**

### 实测确认（两条都复现为真）

| 审查指控 | 实测 |
|---|---|
| `warnings` 无任何读取方 | `paper_search.py:76/96` 只写不读；全仓无 `ResearchState.warnings` 的消费者 |
| **本轮 HEADLINE 无测试守护** | **删掉 `paper_search.py` 的告警段后，548 个测试仍全绿** |

### 【最重的一条，比审查所述更严重】langgraph 静默丢弃未声明的 key

审查说"warnings 未加入 `WorkflowState`，是潜在契约不一致"。**实测证明它远不止"潜在"**：

```python
def node(state):
    out = dict(state)
    out["warnings"] = ["test warning"]
    out["paper_ids"] = ["p1"]
    return out
single_node_subgraph("n", node).invoke({"project_id": "x"})
# → 返回 keys 只有 ['paper_ids', 'project_id']，warnings 丢失
```

**langgraph 只保留 `WorkflowState` TypedDict 声明的 key。** 所以 `warnings` 在生产路径（`graph.invoke`）上**从未存活**——不是"没人读"，是**不存在**。

**此前所有测试都直接构造 agent（绕过图），所以看不到这一点。** 我上一轮宣称的 6 条"判据型"证据，测的是"直接调用时行为正确"，**没有一条穿过框架边界**。

### R4 修复

1. `WorkflowState` 声明 `warnings`（并内联写明"这个 key 是承重的，不是装饰"）。
2. `_save_run` 把 `warnings` **提到 run record 顶层**（与 `status` 并列），使"这次运行完成了、但检索不完整"成为运行记录的一等属性。
3. **测试改为穿过图**：`test_workflow_state_declares_warnings` + `test_incomplete_retrieval_warning_survives_the_graph`。
4. **决定性验证**：删掉告警段后，套件**从"548 全绿"变为失败**（此前是假绿）。

### 方法论教训（本包最有价值的一条）

> **不穿过框架边界的覆盖，不是对框架行为的覆盖。**
> 前几轮的判别力全部在"直接构造 agent"这一层取得，因此无法区分"通道可用"与"通道不存在"。**判别力验证必须覆盖事实实际流经的那条路径**，否则它证明的是别的东西。

## 第五轮独立审查 —— 承认「只闭合了一半」

审查 `cdc77d4` 回传：**R4 真修好了"被图丢弃"这一支**（有判别力证据），但**原始缺陷"没人读这条 warning"并未闭合** —— 我只是把事实从"没人读的 state 字段"搬到了"没人读的顶层字段"。

### 实测确认

| 审查指控 | 实测 |
|---|---|
| 生产图是 8 节点，我的测试只走单节点 subgraph | `graph.py:188-196` 确为 8 节点；此前测试用 `single_node_subgraph` |
| `warnings` 无消费方 | 全仓确认：写入方仅 `paper_search` + `_save_run` 搬运，**零读取方** |
| commit 称"first-class"夸大 | `_save_run` 写入后，`sync_run_projection` / `api.get_run` / `cli status` 均不基于它做任何事 |

### 但有一条是我自己验证出的**正向**结果

审查担心"warnings 穿过 8 节点靠未测试的不变量"。**实测注入部分失败跑完整图，warnings 确实存活到终点**并出现在 run record 顶层：

```
run record 顶层 keys: ['interrupts','project_id','run_id','state','status','warnings']
rec['warnings']: ['Retrieval was incomplete: ...']
```

→ **不变量实际成立，但确实未被测试守护**。审查说得对：任一 agent 改为重建 dict 就会静默失效。

### R5 修复

1. **`cli status` 把每条 warning 打到 stderr**（stdout 保持可解析 JSON）。这是**第一个真正的消费方**——operator 不再需要手动翻 raw record。
2. **测试改为穿 8 节点生产图**（`test_warning_survives_the_full_production_graph`），而非单节点 subgraph。
3. 补 `test_cli_status_is_quiet_when_there_are_no_warnings`。

### 【自查发现的又一个空断言】

CLI 测试第一版写的是 `"..." in result.stderr or "..." in result.output` —— **`or` 兜底让它恒真**（JSON 文档里含同一句话）。**删掉 CLI 告警后测试仍绿**。改为只断言 `result.stderr` 后，判别力成立（删告警 → 1 failed）。

**注意：这个空断言是我在本轮犯的，不在任何审查者的清单里。** 说明假绿风险对"新写的测试"是持续存在的，不只在历史代码里。

## 第六轮独立审查 —— 通过，建议合并

审查 `4edaeee`（含此前的 8 节点图测试）。结论：**两条新测试的判别力经独立验证为真**（移除对应代码即失败）——这是本项目第一次由独立审查确认"判别力不是自证"。

它留下的项与我的处置：

| 审查项 | 处置 |
|---|---|
| 运行投影（`sync_run_projection`）不读 `warnings` | **已修**：投影里 `blockers` 有而 `warnings` 没有，属不对称；已补齐 + 判据测试 |
| `test_the_agent_branches_on_the_flag_not_on_the_wording` 仍是旧绕图测试（低） | **未改**：保留它作为 agent 层单元测试，其数据准确性由穿图测试承接。**已知冗余，如实记录。** |

### 本轮补的两条不变量测试（比修 bug 更有价值）

1. **`test_the_warning_never_disappears_between_nodes`**：用 `graph.stream` **逐节点**断言"warnings 一旦出现就不得在后续节点消失"。它**不依赖具体节点名**，因此自动适应图的演进。
   **背景**：实测发现四个下游 agent（orchestrator / paper_reader / reviewer / writer）**无一显式保留 `warnings`**，全靠 `model_copy` 的隐式语义。实测确认风险真实：
   ```
   model_copy 后          -> 保留 ✓
   重建构造后              -> [] 静默丢失 ✗
   ```
   任何 agent 改成"显式重建"（一个看起来正常的重构）都会重新引入该缺陷。
2. **`test_run_index_projection_carries_warnings`**：投影层也不得隐藏非阻断告警。

## Not closed

- **N2**：`_status()` 用诊断关键词（`failed`/`disabled`/`error`…）推断 `UNKNOWN_OUTCOME`（`capability.py:76-81`）。实测当前对零命中不可达（该路径不回显 query），但**未加防回归测试** —— 下一个在零命中诊断里写含关键词文本的人会踩中。
- 本包改动触及 `capability.py` / `invocation_contracts.py` / `contracts.py`（A8/A9 的禁区），故独立成包并显式声明 `allowed_paths`。
- **R3-3 的实质**：legacy `CrossrefConnector` 对无 DOI 记录的拒绝**已有诊断**（非完全静默），且 Crossref 作为 DOI 注册机构其记录恒有 DOI，故实际触发面很窄；但**"记录消失"现在至少有 `refused_records` 计数**（本轮已加）。未进一步改 Crossref 的标识选取。
- **收敛性未证明**：本包已历三轮审查，每轮都有实质发现（R1 凭据泄露 → R2 表面修复 → R3 消费点缺失）。**第四个轮次是否还有发现，我不知道。**
