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

## Not closed

- **N2**：`_status()` 用诊断关键词（`failed`/`disabled`/`error`…）推断 `UNKNOWN_OUTCOME`（`capability.py:76-81`）。实测当前对零命中不可达（该路径不回显 query），但**未加防回归测试** —— 下一个在零命中诊断里写含关键词文本的人会踩中。
- 本包改动触及 `capability.py` / `invocation_contracts.py` / `contracts.py`（A8/A9 的禁区），故独立成包并显式声明 `allowed_paths`。
- **R3-3 的实质**：legacy `CrossrefConnector` 对无 DOI 记录的拒绝**已有诊断**（非完全静默），且 Crossref 作为 DOI 注册机构其记录恒有 DOI，故实际触发面很窄；但**"记录消失"现在至少有 `refused_records` 计数**（本轮已加）。未进一步改 Crossref 的标识选取。
- **收敛性未证明**：本包已历三轮审查，每轮都有实质发现（R1 凭据泄露 → R2 表面修复 → R3 消费点缺失）。**第四个轮次是否还有发现，我不知道。**
