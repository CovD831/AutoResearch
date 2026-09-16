# S4-A4 Mainline Retrieval Adapter

- ID: `S4-A4-MAINLINE-ADAPTER`
- Title: `S4 mainline retrieval switches to the A5 real adapters`
- Status: `integrated`
- Status note: 已提交审查（PR #23，head `9510ac4`）；本 commit 实测 **587 passed / 2 skipped**（base `main@b83cc56` 实测 539）；四门全绿。**已合并 `main@b5853bd`（PR #23，squash）。** 后续验收（accepted）挂 P2/认证层与跨进程并发。
- Status note（包级设计）: 执行 `D-A5-偏离-1` 选项 (a)。新文件 `src/autoresearch/adapter_search_service.py`（`AdapterBackedPaperSearchService`，满足 `PaperSearchServicePort`）；`_CandidateOnlyAdapter` 新增公开原语 `retrieve()`，限流计数下沉其中，`invoke()` 改为复用；`application.py` 装配切到新服务，`PaperSearchCapabilityAdapter` / `InvocationBoundedSearchPort`（A4 可靠边界）原样保留。基线 `main@04ce9a9` 实测 **509 passed / 2 skipped / 0 error**；本包完成后 **546 passed / 2 skipped / 0 error**（快照 commit `7b15997`；后续 A9/A10 改动使其继续增长，见文末 Integration head）。ruff clean、compileall OK、`check.mjs` valid。判别力实测：装配未切场景下 **2 判据型 failed / 12 passed**。零回归（既有 509 条逐位不变）。
- Owner: `user/team`
- Next owner: `user/team`

## Goal

把主链路 `run` 的检索从裸 `httpx.get` 匿名 connector（`search_service.SemanticScholarConnector`）切到 A5 交付的真实检索 adapter（`search_adapters.SemanticScholarSearchAdapter`：key 走 header、无 key fail-closed、限流可观测），从而消除真实运行中观察到的 **semantic_scholar 429** 失败面 —— 无 key 走共享匿名额度确实**不稳定且已被真实运行观察到** 429（本机 2026-09-11 实测），但官方说明大部分端点允许无 key 访问、仅受共享限流，因此准确表述是「匿名共享额度不适合作为可靠主链路」，而非「匿名必失败」。不删除老服务（它是 A1 accepted 的 S1 路径，被 A1/A2 recovery contract 测试直接构造）。

## Why a separate package

`A5-benchmark-runtime/task-package.json` 的 `forbidden_paths` 含 `application.py` / `search_service.py` / `capability.py` / `capability_registry.py` / `contracts.py`。本包要动的文件里三个在 A5 禁区，故 A5 当年无法自行接线——`D-A5-偏离-1` 的存在理由是边界所迫，不是疏忽。

## Acceptance scenarios

- [x] 主链路装配指向新服务：`application.py` 的 `self.search` 为 `AdapterBackedPaperSearchService`，不再是 `PaperSearchService`。
- [x] A4 可靠边界不丢：`self.search_capability` 仍是 `PaperSearchCapabilityAdapter`，且其 `.service` 是新服务；`self.search_port` 仍是 `InvocationBoundedSearchPort`。
- [x] 端到端链路可达：从 `paper_search_agent.search`（即 `search_port`）出发能实际触达检索 adapter，且同 invocation 身份二次调用走 replay 不重复取数。
- [x] **abstract 正文不丢**：落库 `PaperRecord.abstract` 非空（候选路径会把 abstract 降级成 `abstract_present` 布尔，reader 会退化成只读标题）。
- [x] 无 key **不发请求**：断言 transport 调用为空 + 诊断含凭据缺失。
- [x] 限流（429）**被计数且可观测**：`rate_limit_summary()["rate_limit_events"] >= 1`，`last_retry_after_seconds` 读取 provider 提示。
- [x] `retrieve()` 不吞异常：调用方可据此分类（`RetrievalRateLimited` 冒泡）。
- [x] 落库副作用与老路径等价：paper 记录 + E1 EvidenceItem + WikiPage（partition=papers）三者齐全。
- [x] DOI 去重：同一论文经两个 query 返回只落一条记录。
- [x] 离线模式**显式**：`network_enabled=False` 时不触网并写出 "disabled" 诊断；seed papers 仍被处理。
- [x] 测试全离线可复现（无网络、无凭据）。

## Invariants

- 不修改 `contracts.py`、`invocation_contracts.py`、`capability.py`、`capability_registry.py`、`evidence.py`、`gates.py`、`storage.py` 或 `.ai-team/TASK.md`。
- **不删除 `search_service.py`**：它是 A1 accepted 的 S1 路径，被 A1/A2 recovery contract 测试直接构造。
- 主选检索源不得由本包单方面更换（ADR-01 §1）；本包只换**装配目标**，providers 集合与优先级不变。
- 凭据只从 `Settings` 读，永不进入 request、fingerprint、receipt、日志或仓库。
- 主链路不得经候选通道取数（`CANDIDATE_ONLY` 的 `value` 被 registry 清空，且候选不带 abstract 正文）。
- 失败路径不得被写成通过；空结果按 D-F8-01 记为确定性成功，限流（查询未执行）**不得**被写成"零命中"。
- 不新增业务 Agent；本包是 Runtime 装配改动。

## Decisions

- **D-A8-01 新增公开原语 `retrieve()`，而不是让主链路经候选通道**：`CANDIDATE_ONLY` 注册的 `value` 会被 registry 强制清空（`capability_registry.py:645-648`，D-F8-01 相关，有意设计），且 `_candidate()` 只带 `abstract_present` 布尔。主链路若走候选路径，44 篇论文会全部退化成"只有标题"（`reader_service.py:69-71` 的 `source_text = full_text or paper.abstract` 兜底到 `paper.title`）。这属于本项目反复出现的「退化路径把缺失输入记成正常值」缺陷族，必须在设计阶段挡掉。`invoke()` 的候选语义不变。
- **D-A8-02 限流计数下沉到 `retrieve()`**：原先只在 `invoke()` 的 except 里递增。下沉后 `invoke()` 与新主链路共享同一个 limit-monitor 面，不新增第二套计数器。
- **D-A8-03 不删 `search_service.py`**：它是 A1 accepted 的 S1 路径，被 `tests/a2_runtime_fixtures.py`、`tests/test_recovery_contract.py`、`tests/test_capability_adapter.py` 直接构造。删除会破坏既有基线。本包只换主链路装配目标。
- **D-A8-04 保留 `PaperSearchCapabilityAdapter` 包裹新服务**：该 adapter 只依赖 `PaperSearchServicePort` 这个 Protocol（鸭子类型），换实现无需改动它，A4 的幂等/replay/recovery 语义因此原样保留（端到端测试已断言 replay 不重复取数）。
- **D-A8-05 `network_enabled=False` 时显式诊断而非静默跳过**：沿用老服务语义（只处理 seed papers），但把"网络关闭"写进 diagnostics，避免与"网络开了但零命中"混淆。

## Verification

| 项 | 命令 | 结果 |
|---|---|---|
| 基线（`04ce9a9`，本 worktree 实测） | `pytest -q -o addopts="" -W error` | **509 passed / 2 skipped / 0 error** |
| 本包全量（快照 `7b15997`） | 同上 | **546 passed / 2 skipped / 0 error** |

### Integration head（PR #23 合并前）

| 项 | commit | 结果 |
|---|---|---|
| base | `main@b83cc56` | **539 passed / 2 skipped**（本 worktree 实测） |
| PR head | `9510ac4` | **587 passed / 2 skipped**（本 worktree 实测） |

> 包级历史数字属各自提交上的快照，**不要求彼此相同**；上面每行都标了它自己的 commit，便于复算。
| 聚焦 | `pytest tests/test_adapter_search_service.py` | 20 passed，**全离线** |
| ruff | `ruff check src tests` | All checks passed |
| compileall | `compileall -q src` | exit 0 |
| check.mjs | `node .ai-team/check.mjs --base main` | valid |
| 判别力（装配未切场景） | 新模块在、`application.py` 保持基线，只替换测试文件 | **2 failed / 12 passed**，均为判据型（`assert isinstance(PaperSearchService(...), AdapterBackedPaperSearchService)`） |

## Self-review findings（对抗性自审，本包内已修）

1. **第一版判别力验证是假绿（12 passed）**：测试全部直接构造新服务，从不经过 `application.py`，所以"装配未切换"完全测不出。→ 补两条装配级判据断言后，判别力变为 2 failed。**教训与 R2 同型：「有覆盖 ≠ 有判据」，覆盖了行为不等于锁住结论。**
2. **端到端测试第一版依赖真实网络**：它替换了 `service.adapters` 里 semantic_scholar 一项，但 `build_search_adapters` 造的 arxiv/openalex adapter 仍带真 transport，测试实际访问了 live provider（耗时 17.3s 且返回 5 篇真实论文）。→ 改为整体替换 `service.adapters` 后耗时降到 0.17s。**一个依赖网络、耗时 17s 的测试在 CI 里不是证据。**
3. **第一版测试里还混入了空洞断言与死代码**（`assert not any(... if False)`、未被使用的 `legacy_transport`）→ 已删除或改为可证伪的断言。
4. **query → invocation_id 派生有碰撞（自审实测抓出）**：原先用 `re.sub(r"\W+", "-", query)`，实测 `"a b"` 与 `"a-b"` 折叠成同一串，`"!!!"` 与 `"???"` 亦然。碰撞意味着两个不同 query 共用 `invocation_id`，会让 A4 账本把第二个 query 重放成第一个的结果。→ 改为 slug + `sha256` 前 12 位，并补 `test_query_id_fragments_do_not_collide` 锁住不变式。

## Completed

- 新增公开原语 `_CandidateOnlyAdapter.retrieve(request) -> list[RetrievedPaper]`，含限流计数；`invoke()` 改为复用（候选语义不变）。
- 新增 `src/autoresearch/adapter_search_service.py`：`AdapterBackedPaperSearchService`，满足 `PaperSearchServicePort`；经 A5 adapters 取数、`RetrievedPaper`→`PaperRecord`、复刻落库副作用（paper + E1 evidence + wiki page）、DOI 去重、按异常类型分流 diagnostics、`network_enabled=False` 显式离线模式、`rate_limit_summary()` 聚合。
- `application.py` 装配切到新服务；`PaperSearchCapabilityAdapter` / `InvocationBoundedSearchPort` 原样保留。
- 测试 `tests/test_adapter_search_service.py` 16 条，全部离线可复现。
- 账本回写：`A5-benchmark-runtime/L3.md` 的 `D-A5-偏离-1` 由「待裁决」改为「已裁决 → 已解决 (a)」；`TASK-QUEUE.md` 增 A8/A9 两行；`TASK-PACKAGE-REGISTRY.md` 登记两包。
- 本包 `task-package.json` 与 `L3.md` 设计记录。

## Pending

- 真实网络端到端（需本机 `SEMANTIC_SCHOLAR_API_KEY`）。
- 跨进程并发（沿用挂账口径）。
- OpenAlex `HTTP 200 + error body` 限流在主链路下的行为未单独验证。

## Next step

- 开 PR（`owner/a8-mainline-adapter` → main），走保护窗口合并。
- 合并后启动 **A9 / S4-A5-HANDOFF-BY-REFERENCE**（交接单只传引用），它依赖本包先拿到真实检索量级。

## Handoff note

- 本包为 **owner 线**（触及主链路装配与 A4 可靠边界，同 O12/O13 先例），不派成员。
- A9 可派成员，但**必须在本包合并后**开：`paper_search.py` 是两包的唯一交叠文件，且 A9 的契约上限需要本包提供的真实量级作依据。
- 接手者注意：`search_service.py` 虽已不被主链路调用，但**仍在库内且仍被测试使用**，不要顺手删除。
- 下一位 owner 若要验证真实检索，需 `SEMANTIC_SCHOLAR_API_KEY`；无 key 时新路径会 **fail-closed 且不发请求**（这是期望行为，不是故障）。

## Adversarial review（机制二：作者侧探针，2026-09-14）

**发现 3 个真实缺陷，全部由本分支引入**，且**全部未被测试套件、判别力检查或门禁拦住**：

| # | 缺陷 | 级别 | 修复 |
|---|---|---|---|
| 1 | 异常消息 `{exc}` 被写入 diagnostics 并**持久化进 `audit_events.payload_json`**（实测凭据串落库）。老 connector 刻意只记 `type(exc).__name__`，本分支丢失了该保护 | **高** | `_safe_exc()` 只回类型名；判据测试直接回读数据库 |
| 2 | `MemoryError` 被 `except Exception` 吞成"provider 失败"，运行以看似正常的空结果结束 | 中 | `_is_fatal()` 重抛 |
| 3 | 检索全失败与真实零命中**用同一句话报告**，下游无法区分（`WAITING_EVIDENCE` 只对后者正确） | 中 | 分两句 |

另修：**源的组成**写进 run diagnostics（老路径 openalex+crossref+semantic_scholar → 新路径 semantic_scholar+arxiv+openalex，是行为变更，此前只在 diff 里可见）。

判别力：本轮 4 条新测试在 `b7635d7` 上 **4 failed，全部判据型**。

**同族横扫（机械枚举 8 处 `ArtifactRef(` 构造点）新发现第 4 处：`writing_service.py:207`**（`summary=card.findings[0][:300]`，每卡一条 + 嵌正文，与已修的 `paper_reader.py:84` 完全同型）。**本包未修**：该字段（`pipeline_contracts.py:81`）无长度上限故不产生故障，且**无任何读取方**；修它需越过本包 `allowed_paths`。已留痕交下一包。

## Follow-up：A10 / S4-A6（2026-09-14）

本包审查提出的 **F4**（畸形/缺失命中铸成受信任 E1，claim 与 wiki 正文矛盾）与 **N1**（部分 provider 失败被静默）已由 **A10 / S4-A6-BIBLIOGRAPHIC-CLAIM** 处置（老板 2026-09-14 裁决「修复 F4 和 N1」）。

要点：
- **复核修正**：本包先前判定 F4「被 A1 parity 契约锁定」**过重**。`tests/test_recovery_contract.py:193` 比对的是老服务 vs 老服务（同源），且**全仓无测试断言 claim 字符串**；`parity-report.json` 是 A1 历史验收证据。→ 两处同步修改即可。
- 修复方式：提取**共享书目写入函数**，使 A1 parity 由"人工同步"变为**结构性**保证。
- 判别力：5 failed，全部判据型（需符号 shim，见 A10 ledger）。

## Not closed

- 跨进程并发未测（沿用 A5/O12 挂账口径）。
- 真实网络端到端需本机配置 `SEMANTIC_SCHOLAR_API_KEY`；本包证据全部来自注入 transport 的离线矩阵。
- `OpenAlex` 的 `HTTP 200 + error body` 限流形态在主链路下的处置未单独验证（adapter 层已在 A5 处理，本包只消费）。
- **`writing_service.py:207` 同族缺陷未修**（见上）。字段无读取方，属语义污染而非故障。
- **`_persist` 的部分完成窗口**：paper 已落库、evidence 已落库、`add_page` 失败 → 异常逃逸，留下不一致状态。**实测老服务行为相同**，属继承而非本包引入；本包未修。
- **凭据泄露缺陷曾在 `386e7f8` 起存在两轮，所有门禁均未拦住** → 现行验证手段对"异常消息内容"这一类缺陷无覆盖。
- **【已由 A10 / S4-A6 处置】F4（独立盲审发现）**：畸形/缺失命中被铸成受信任的 E1 证据。实测两个矛盾：① `RetrievedPaper(title="Real paper", abstract="")` 落库 claim 声称 "its supplied abstract exist"，而同一论文的 `WikiPage.body` 写 "No abstract was supplied"；② `title="Untitled", doi/url/source_record_id 全 None` 的命中仍被铸成 E1，`independent_source` 退化为 `"<source>:None"`。**实测老服务 `search_service.py:175` 行为逐位相同**，且 claim 文案被 **A1 parity 契约**（`docs/rearchitecture/worktrees/A-runtime-recovery/parity-report.json` 的 `evidence_equal: true` / `wiki_equal: true`）锁定。→ 修它需同时改两处实现并更新 A1 契约，**属 owner 层设计决策**。

## Independent review（机制一，2026-09-14）

独立子代理盲审（prompt 不含作者推理）回传 4 项发现：F1 凭据落库（高）、F2 致命异常被吞（中）、F3 异常消息边界不稳健（中）、F4 畸形记录铸成 E1（中）。

**F1/F2/F3 与作者侧自查完全重叠且结论一致** —— 两条不知情路径收敛，是修复正确性的最强证据。**F4 为独立新增发现**，见上方裁决项。

**第二轮盲审推翻作者自评**：「修复③（失败 vs 零命中）」原为**表面修复**——只改措辞，而 `paper_search.py:55` 仍只判 `if not outcome.papers`，两情形收敛到同一 blocker；且作者当时的测试**断言字符串**，把表面修复固化成了期望（skill 3.2 同型第三次）。已按盲审建议重做：`SearchOutcome.provider_failure` 结构化字段 + 消费方真正分流 + `InvocationBoundedSearchPort` 从 receipt `outcome_status` 推导，使标志穿过 A4 边界。另修 `_is_fatal` 死代码（`KeyboardInterrupt`/`SystemExit` 非 `Exception` 子类）。**判别力**：字段 shim 后取得**判据型**证据（`assert 'No real paper records...' != 'No real paper records...'`）。

**第二轮另记录两条未修**：N1 部分失败被静默（主源 fail-closed + 次源有产出 → `provider_failure=False`，属 `capability.py:74-76` 既有语义）；N2 `_status()` 用诊断关键词推断状态（实测当前不可达，但**未加防回归测试**）。

报告：`reviews/A8-A9-ADVERSARIAL-REVIEW.md`。
