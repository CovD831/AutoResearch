# S3-B Reader/Writer Ports

- ID: `S3-B-READER-WRITER-PORTS`
- Title: `Typed reader/writer ports, offline adapters, claim binding and parity`
- Status: `handoff`
- Owner: `member B`
- Next owner: `user/team`

## Goal

建立 reader/writer 两个 Domain Port 的 typed 合同与三个传输中立 adapter（native 确定性 oracle、llm 结构化、external 结构化），在任何非 native 输出上保持「候选通道」约束，并用 100% claim/evidence binding 与 fail-closed gate 合规规则做三路契约级 parity。

## Acceptance scenarios

- [x] typed `ReaderRequest/ReaderResult`、`WriterRequest/WriterResult`、`ReaderPort/WriterPort` protocol 与 `AdapterKind` identity 齐全。
- [x] native reader/writer 为确定性实现；structured reader/writer 包装已归一化 payload 且零 I/O、零 record 写入。
- [x] 非 native reader 输出始终携带 `EvidenceCandidate`，不经 `EvidenceService.add` 直写证据（sole-writer 边界）。
- [x] `bind_claims` 对缺失/失效证据 fail-closed（partial/unbound，绝不冒充 bound）；`gate_compliance` 阻断 observed-result 泄漏、静默无绑定 claim、不可见 lineage。
- [x] `compare_writer_parity` 对 native/llm/external 三路产出做契约级 parity（schema/binding/gate/planned-only），不做文本等价。
- [x] 聚焦测试 + 对抗性 binding/gate 测试通过；全量、ruff、check.mjs、Project-to-Act 验证记录见 Verification。

## Invariants

- 不新增第六个领域角色；reader/writer 是既有 Domain Port 的实现。
- 端口与 adapter 不得调用 `EvidenceService.add` 或 `RecordStore.put("evidence", ...)`；正式证据唯一写入者是 EvidenceService。
- 外部/LLM 输出一律 candidate 通道，先降级后准入，不直写、不冒充正式证据。
- 不修改 `reader_service.py`、`writing_service.py`、共享 `contracts.py`、`application.py`、storage、gates、cli/api、A 线路径、`.ai-team/TASK.md` 或 `.project-to-act/`。
- 不执行真实网络调用、不入真实语料/模型响应/实验观测结果。
- `completed_empty` 上游材料按「材料缺失」处理，不重新解释为 unknown、不虚构结果。

## Decisions

- 单文件 `src/autoresearch/reader_writer_ports.py` 承载合同与 adapter（B4 无 Owner 字段级裁决，依 B3 单文件先例）。
- parity 采用严格结构规则（schema、100% evidence binding、gate 合规、planned-only），不使用文本相似度阈值。
- structured adapter 的 payload 字段命名沿用既有 `ReadingCard`/`SectionDraft` 语义，不发明新领域实体。
- non-native reader candidate 分类为 PAPER/E1；正式评级仍由 admission（EvidenceService）在准入时决定。

## Completed

- 新增 `src/autoresearch/reader_writer_ports.py`：typed reader/writer 请求响应、protocol、adapter identity、native + structured 三路 adapter、`bind_claims`、`gate_compliance`、`compare_writer_parity`。
- 新增 `tests/test_reader_writer_ports.py`：三路 parity、observed-result 阻断、unbound/missing evidence fail-closed、compose 类型一致性用例；聚焦测试 8 passed。
- 新增 B4 任务包 `task-package.json`/`TASK.md`/`L3.md`/`PROGRESS.md`/`HANDOFF.md` 与本成员账本。

## Pending

- Owner 审查、commit、push、开 PR；`integrated`/`accepted` 由 owner 按全局路线判定，本成员不标记。
- O12 ProviderLane / A4 capability adapter 就绪后，structured adapter 接入真实 payload 供给方的时机由 owner 排期。

## Next step

Owner review scope diff → commit B4 paths → push `codex/s3-reader-writer-ports` → PR against `CovD831/AutoResearch:main`。

## Verification

- [x] 聚焦测试 `python -m pytest tests/test_reader_writer_ports.py -q`：`8 passed`（Python 3.13.9 + 临时依赖目录 `var/_b4_deps`）。
- [x] 全量 `python -m pytest -q -p no:cacheprovider`：`116 passed`（108 基线 + 8 新增 B4），Python 3.13.9。
- [x] `ruff check src/autoresearch/reader_writer_ports.py tests/test_reader_writer_ports.py`：`All checks passed!`；`ruff format --check` 通过。
- [x] `node .ai-team/check.mjs --base 437e15e --json`：`valid: true`（8 个改动文件全部在 B4 allowed_paths，无禁改路径）。
- [x] Project-to-Act `--check`：`configured: true, mode: managed`，无 missing_templates。
- 环境注记：全量 `ruff check src tests` 对既有的 `audit_evidence.py`（B3）与 `capability.py`（A 线）报 3 处 UP038，与本任务无关（ruff 0.12 较项目锁定版本更严）；B4 新增文件单独通过。`-W error` 全量收集被临时依赖目录里的 click 版本 DeprecationWarning 干扰，改用 `-p no:cacheprovider` 取得干净 116 passed。

## Handoff note

- From: `member B`
- To: `user/team`
- Summary: B4 交付 typed reader/writer ports 与三路离线 adapter contract；native 为确定性 oracle/fallback，llm/external 输出走 candidate 通道，claim/evidence 100% binding + fail-closed gate 合规 + 契约级 parity。本轮不提交、不推送、不开 PR；回滚仅移除 B4 allowed paths 内文件。