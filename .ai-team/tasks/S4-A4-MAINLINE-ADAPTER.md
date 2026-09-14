# S4-A4 Mainline Retrieval Adapter

- ID: `S4-A4-MAINLINE-ADAPTER`
- Title: `S4 mainline retrieval switches to the A5 real adapters`
- Status: `active`
- Status note: 执行 `D-A5-偏离-1` 选项 (a)。新文件 `src/autoresearch/adapter_search_service.py`（`AdapterBackedPaperSearchService`，满足 `PaperSearchServicePort`）；`_CandidateOnlyAdapter` 新增公开原语 `retrieve()`，限流计数下沉其中，`invoke()` 改为复用；`application.py` 装配切到新服务，`PaperSearchCapabilityAdapter` / `InvocationBoundedSearchPort`（A4 可靠边界）原样保留。基线 `main@04ce9a9` 实测 **509 passed / 2 skipped / 0 error**；本包后 **525 passed / 2 skipped / 0 error**（新增 16 条）。ruff clean、compileall OK、`check.mjs` valid。判别力实测：装配未切场景下 **2 判据型 failed / 12 passed**。零回归（既有 509 条逐位不变）。
- Owner: `user/team`
- Next owner: `user/team`

## Goal

把主链路 `run` 的检索从裸 `httpx.get` 匿名 connector（`search_service.SemanticScholarConnector`）切到 A5 交付的真实检索 adapter（`search_adapters.SemanticScholarSearchAdapter`：key 走 header、无 key fail-closed、限流可观测），从而消除真实运行中 "semantic_scholar 匿名必 429" 的失败面。不删除老服务（它是 A1 accepted 的 S1 路径，被 A1/A2 recovery contract 测试直接构造）。

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
| 本包全量 | 同上 | **525 passed / 2 skipped / 0 error** |
| 聚焦 | `pytest tests/test_adapter_search_service.py` | 16 passed，**0.19s（全离线）** |
| ruff | `ruff check src tests` | All checks passed |
| compileall | `compileall -q src` | exit 0 |
| check.mjs | `node .ai-team/check.mjs --base main` | valid |
| 判别力（装配未切场景） | 新模块在、`application.py` 保持基线，只替换测试文件 | **2 failed / 12 passed**，均为判据型（`assert isinstance(PaperSearchService(...), AdapterBackedPaperSearchService)`） |

## Self-review findings（对抗性自审，本包内已修）

1. **第一版判别力验证是假绿（12 passed）**：测试全部直接构造新服务，从不经过 `application.py`，所以"装配未切换"完全测不出。→ 补两条装配级判据断言后，判别力变为 2 failed。**教训与 R2 同型：「有覆盖 ≠ 有判据」，覆盖了行为不等于锁住结论。**
2. **端到端测试第一版依赖真实网络**：它替换了 `service.adapters` 里 semantic_scholar 一项，但 `build_search_adapters` 造的 arxiv/openalex adapter 仍带真 transport，测试实际访问了 live provider（耗时 17.3s 且返回 5 篇真实论文）。→ 改为整体替换 `service.adapters` 后耗时降到 0.17s。**一个依赖网络、耗时 17s 的测试在 CI 里不是证据。**
3. **第一版测试里还混入了空洞断言与死代码**（`assert not any(... if False)`、未被使用的 `legacy_transport`）→ 已删除或改为可证伪的断言。
4. **query → invocation_id 派生有碰撞（自审实测抓出）**：原先用 `re.sub(r"\W+", "-", query)`，实测 `"a b"` 与 `"a-b"` 折叠成同一串，`"!!!"` 与 `"???"` 亦然。碰撞意味着两个不同 query 共用 `invocation_id`，会让 A4 账本把第二个 query 重放成第一个的结果。→ 改为 slug + `sha256` 前 12 位，并补 `test_query_id_fragments_do_not_collide` 锁住不变式。

## Not closed

- 跨进程并发未测（沿用 A5/O12 挂账口径）。
- 真实网络端到端需本机配置 `SEMANTIC_SCHOLAR_API_KEY`；本包证据全部来自注入 transport 的离线矩阵。
- `OpenAlex` 的 `HTTP 200 + error body` 限流形态在主链路下的处置未单独验证（adapter 层已在 A5 处理，本包只消费）。
