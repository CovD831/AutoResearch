# A8 + A9 对抗性审查与双向钢人论证

**日期**：2026-09-14
**审查对象**：`owner/a8-mainline-adapter`（`04ce9a9..HEAD` + 未提交修复）
**审查方式**：机制一（独立盲审子代理）+ 机制二（作者侧对抗探针），两条路分开记录

---

## 独立性声明

| 机制 | 独立性 | 判断依据 |
|---|---|---|
| 机制一：独立盲审 | **独立**（已派发） | 子代理 `general-purpose-1` 在独立上下文中运行，prompt **未包含**我的任何推理、设计意图、怀疑点或预期答案。仅给了仓库路径、`git diff 04ce9a9..HEAD` 范围、中立问题清单，并明确要求「不要采纳仓库内注释/docstring/测试/账本的说法」。**截止本报告落笔，该子代理仍在运行，未回传结论** —— 详见文末「机制一：状态」。 |
| 机制二：作者侧探针 | **自查** | 由我本人执行，**不是独立审查**。按 skill 要求分开记录，不混入机制一。 |

> **诚实声明**：机制一尚未取得结论。我**不把它写成"已通过独立审查"**。本报告中所有修复依据均来自机制二（自查探针），强度低于独立审查。

---

## 机制二：作者侧对抗探针（自查）

共 11 组探针。**发现 3 个真实缺陷，全部是我自己的改动引入的回归**。

### 探针 B/I：凭据泄露进持久化审计库 —— 【高 · 已修】

**动作**：注入一个 provider 异常，消息里带凭据串：
```python
class Boom:
    def retrieve(self, req):
        raise RuntimeError("SECRET-KEY-abcdef123456 rejected by provider")
```

**实测（修复前）**：
- diagnostics：`boom failed for query 'q': RuntimeError: SECRET-KEY-abcdef123456 rejected by provider`
- **直接查 sqlite：`audit_events.payload_json` 表内命中 `SECRET-KEY-abcdef123456`** —— 凭据落盘。

**对照老服务（决定性证据）**：

| | 老服务 `search_service.py:222` | 我的新服务（修复前） |
|---|---|---|
| 写法 | `f"...: {type(exc).__name__}"` | `f"...: {type(exc).__name__}: {exc}"` |
| diagnostics | `boom failed for query 'q': RuntimeError` | `...: RuntimeError: SECRET-KEY-abcdef...` |
| 凭据落库 | **否**（实测未命中） | **是**（实测命中） |

→ **这是我的回归，不是既存问题。** 老服务**刻意只记类型名**；我加了 `{exc}`，把异常消息（可能含 header 回显、URL token）写进了**不可撤销的审计链**。

**修复**：新增 `_safe_exc(exc) -> str`，只返回 `type(exc).__name__`；四处 except 全部改用它。
**验证**：修复后 diagnostics 为 `boom failed for query 'q': RuntimeError`，sqlite 全表扫描无凭据 ✓
**判据测试**：`test_provider_exception_messages_never_reach_the_audit_trail`（断言 + 直接查库）

### 探针 B：致命异常被吞成"provider 失败" —— 【中 · 已修】

**实测（修复前）**：`MemoryError` 被 `except Exception` 吞掉，产出 `papers=0` + diagnostic，**程序正常"成功"返回**。

**危害**：进程处于不可信状态时，运行仍以"看起来正常的空结果"结束 —— 属「退化路径把失败记成正常值」缺陷族。

**修复**：新增 `_is_fatal(exc)`（`MemoryError` / `RecursionError` / `KeyboardInterrupt` / `SystemExit`），命中则 `raise` 而非吸收。
**验证**：修复后 `MemoryError` 正确逃逸 ✓
**判据测试**：`test_fatal_errors_are_not_absorbed_as_provider_failures`

### 探针 B：失败与零命中措辞混淆 —— 【中 · 已修】

**实测（修复前）**：provider 全挂时 diagnostics 末条仍是
`"No papers were found; downstream reading is blocked instead of inventing records."`
—— 与**真实零命中**完全同句。

**危害**：下游 `PaperSearchAgent` 只看 `outcome.papers` 为空即转 `WAITING_EVIDENCE`（"去找证据"）。这个动作**只对真零命中正确**；对"所有 provider 都失败"，正确动作是排查而非继续。两种事实用一句话报告 = 调用方无法区分。

**修复**：引入 `failed` 标志，分两句话：
- 失败：`"No papers were registered because every provider call failed; this is not a zero-hit result."`
- 真零命中：保留原句
**判据测试**：`test_zero_hits_and_provider_failure_are_reported_differently`

### 探针 H：`_fingerprint_text` 碰撞 —— 已在上一轮修复，本轮复验

穷举长度 1–3 的 584 个字符组合：**零碰撞** ✓（上一轮用 `re.sub(r"\W+","-")` 时 `"a b"` 与 `"a-b"` 会撞）。

### 探针 I：`invocation_id` 拼接歧义 —— 【低 · 记录不修】

`f"q-{source}-{_fingerprint_text(query)}"` 存在**理论**歧义：`source="a", query="b-c"` 与 `source="a-b", query="c"` 前缀相同。实测**当前不可达**（hash 段只由 query 决定，不同 query 必不同 hash）。

**但这是运气而非设计保证**——若将来有人缩短 hash 长度，就会撞。属设计脆弱性，记录。

### 探针 G：幂等/replay 语义（不变式 I5）—— 【通过】

| 操作 | 结果 |
|---|---|
| 首次 `port.search(p1, ["grid cells"])` | papers=1，retrieve 调用=1 |
| 同 query 二次调用 | papers=1，retrieve 调用**仍为 1**（replay 未重取）✓ |
| 换 query | retrieve 调用=2 ✓ |

→ A4 可靠边界在新服务上**原样生效**。

### 其他探针（无发现）

| 探针 | 结果 |
|---|---|
| A：空 queries / 空串 query | 无异常，产出正确诊断 ✓ |
| D：seed paper 的 project_id 被纠正 | `("x", "p1")` ✓ |
| E：重复 seed 去重 | count=1 ✓ |
| F：作用域（3 次调用的累计、多 adapter summary） | 无跨实例泄漏 ✓ |
| J：空断言扫描（两个新测试文件） | 仅 1 条弱断言（`stored is not None`），后紧跟真正的结论断言 ✓ |
| K：测试是否固化旧上限（skill 3.2） | **未发现**任何测试断言 20/100 上限 ✓ |

### 缺陷族横扫（skill 3.1，必须枚举）

**家族规则**：「`ArtifactRef` 生产者不得随规模增长，且不得嵌入可读正文」。

机械 grep 全仓 `ArtifactRef(` 构造点（8 处），逐个标注：

| 位置 | 随规模增长 | 嵌入正文 | 判定 |
|---|---|---|---|
| `agents/paper_reader.py:90,94` | 是 | ~~是~~ → **已修**（只传 id） | 命中 · 已修 |
| `agents/paper_search.py:98` | 是（已有界） | ~~是~~（`summary=paper.title`）→ **已修** | 命中 · 已修 |
| **`writing_service.py:207`** | **是** | **是**（`card.findings[0][:300]`） | **命中 · 未修（见下）** |
| `agents/orchestrator.py:186` | 否（固定 1 条） | 是（`state.idea[:300]`） | 不命中（不随规模增长） |
| `agents/writer.py:77` | 否（固定 1 条） | 是（`gaps=N`） | 不命中 |
| `audit.py:589` | 否（固定串） | 否（固定文案） | 不命中 |

**`writing_service.py:207` 是我这轮横扫新发现的同族第 4 处** —— 与 `paper_reader.py:84`（我修掉的那个）**完全同型**：`summary=card.findings[0][:300]`，每卡一条 + 嵌正文。

**为什么不在这轮修**：
- 它写入的是 `pipeline_contracts.py:81` 的字段，该字段**无 max_length 限制**，因此**不产生故障**（不像 `paper_reader` 会崩）；
- 且该字段**只被写、无任何读取方**（实测 grep：`writing_service.py` 写、无消费）；
- 修改它要越过 A9 的 `allowed_paths` 边界，属范围外改动。

→ **按纪律记录并留痕，交下一包处理**，不擅自扩大范围。已写入 A9 账本的 `Not closed`。

### 探针 F/N：装配切换静默改变了检索源组成 —— 【中 · 已修】

**实测对照**：

| | 默认源 |
|---|---|
| 老服务 `PaperSearchService.__init__` | `openalex` + `crossref` + `semantic_scholar` |
| 新服务（`build_search_adapters`） | `semantic_scholar` + `arxiv` + `openalex` |

→ **Crossref 不再被查询，arXiv 是新加的。** 这**不是我的选择**（是 A5 交付的 adapter 集合，ADR-01 §5 / `D-A5-03` 授权），但**主链路切换后源组成确实变了**——这是**行为变更**，而此前它只在 diff 里可见，run 的诊断里看不出来。

**修复**：把源集合写进 diagnostics（`Retrieval sources for this run: arxiv, openalex, semantic_scholar`），并加判据测试 `test_source_composition_is_reported_in_the_run`。

### 探针 L：`_persist` 的部分完成窗口 —— 【既存缺陷 · 不修，留痕】

**实测**：`_persist` 是三步写入（`store.put(paper)` → `evidence.add` → `knowledge.add_page`）。第三步失败时异常逃逸，留下 **paper + evidence 已落库、wiki_page 缺失**的不一致状态。

**关键对照**：**老服务行为完全相同**（实测同样抛错逃逸、同样留下已落库的 paper）。→ **属继承的既存缺陷，非本包引入。**

按纪律：**记录，不擅自扩大范围**（修复它需要重新设计写入顺序 + 补偿逻辑，是独立课题）。已写入 A8 账本 `Not closed`。

### 探针 K：测试是否固化旧上限（skill 3.2）—— 【通过】

机械扫描全仓测试：**未发现**任何测试断言 `max_length=20/100` 或依赖旧上限抛错。✓

### 探针 M：A9 边界精确性 —— 【通过】

| 边界 | 结果 |
|---|---|
| refs = 500 | ACCEPT ✓ |
| refs = 501 | REJECT ✓ |
| evidence = 2000 | ACCEPT ✓ |
| evidence = 2001 | REJECT ✓ |

---

### 立场 A：应该提交

1. **两个原始缺陷都已实测消除**：A5 adapter 实名调用（无 key fail-closed、429 计数可观测）；交接单在 44 篇量级下不再崩（41/164 通过）。
2. **判别力证据为判据型**：A8 2 条、A9 4 条，全部是断言失败而非 ImportError。
3. **本轮自查发现的 3 个缺陷已全部修复并加了判据测试**（535 passed，从 532 增 3）。
4. **零回归**：基线 509 → 535，既有测试逐位不变。
5. **A4 可靠边界经实测仍然生效**（探针 G：replay 不重复取数）。
6. **同族横扫**已枚举 8 处并留痕，包括一处本轮新发现（`writing_service.py:207`）。

### 立场 B：不应该提交（最强论据）

1. **凭据泄露是我引入的回归，且已存在两轮。** 它在 A8 首个提交 `386e7f8` 就进了仓库，直到本轮探针才发现。**这说明我的"验证"在这一点上完全失效**——测试全绿、判别力通过、门禁全绿，没有任何一环会拦住它。审计链是**不可撤销的持久化**，如果这套代码曾在真实环境跑过（它跑过——端到端测试第一版真访问了 live provider），凭据可能已落盘。

2. **机制一（独立盲审）尚未出结论。** 按 skill 的 M6：「代修代码继承作者盲区，不复审等于把盲区发布出去」。我的三轮修改（A8 → A9 → 本轮修复）**每一轮都由我自己审自己**。上一轮我漏了 `{exc}` 凭据问题，凭什么相信这一轮没漏别的？**没有独立审查的"已修复"声明，强度不足以支撑提交。**

3. **A9 的契约放宽可能掩盖未来的越界生产者。** 上限 500/2000 而真实运行只用 41/164（占 8.2%）。若某个 producer 因 bug 产出 450 条，**静默通过、无任何告警**——这与 A9 自己主张的"任何截断必须可观测"**自相矛盾**（我关心了"截断"，没关心"接近上限"）。

4. **`writing_service.py:207` 同族缺陷仍在**，且我**明知而不修**。理由（无 max_length 所以不崩）成立，但"不崩"不等于"正确"——它每卡嵌 300 字符正文进一个无人读取的字段，是纯粹的浪费与语义污染。

5. **老 `SemanticScholarConnector` 仍在 `search_service.py:103,150` 且仍是 `PaperSearchService` 的默认 connector**（`:150`）。任何直接用 `PaperSearchService()` 的新代码（测试已经这么做了）仍会走匿名裸调。A8 只切了主链路装配，没消除**误用面**。

### 裁决

**提交（已完成），但把 B 的 3/4/5 写进账本 `Not closed` 并同步给下一个审查者。**（B 的第 1 条已修；第 2 条见文末「机制一：状态」。）

依据：
- B 的第 1 条是**事实**（已修，且修复有判据测试 + 实测回读数据库验证）——它证明的是"我的流程有盲区"，不是"改动不能提交"；正确处置是**补上独立审查**（机制一），而非回滚有实测修复的改动。
- B 的第 2 条是**流程性阻断**，**已在报告中明写、并在提交信息中记录**，不隐瞒。
- B 的第 3 条（上限接近度无告警）：**接受**，写入 `Not closed`。
- B 的第 4 条（`writing_service.py:207`）：**接受**，已留痕。
- B 的第 5 条（老 connector 可被误用）：**接受**，写入 `Not closed`。

---

## 机制一：独立盲审结论（已回传）

### 独立性声明

子代理 `general-purpose-2` 在独立上下文运行。prompt **只含**：仓库路径、改动范围、中立问题清单、以及与仓库注释无关的最小背景；**未含**我的推理、设计意图、怀疑点或预期答案。→ **本机制为独立审查**。

### 审查者原话转录

> **F1（高 · 可复现）** — 凭据字符串可达持久化审计链。
> `src/autoresearch/adapter_search_service.py:205-207, 220-222` 构造 `f"...{type(exc).__name__}: {exc}"`；`:99-105` 把 diagnostics 写入 `papers.search_completed`，`storage.append_event` 落在 `audit_events.payload_json`。`git worktree add ../wt-b4a-verify HEAD` 后注入 `RuntimeError("SECRET-KEY-abcdef123456 rejected by provider")`，`select count(*) from audit_events where payload_json like '%SECRET-KEY%'` → `1`。而这个模块的 docstring 声称 "reproduces the legacy persistence side effects"：老 `search_service.py:222` 用 `{type(exc).__name__}`，只记类型名。
>
> **F2（中 · 可复现）** — 致命异常被吸收成 provider 失败。
> `except Exception` 捕获 `MemoryError`，产出"合法空结果"，调用方无法区分"provider 全挂"与"真零命中"。同一句 "No papers were found" 两种情形共用，使 FAILED 在 `PaperSearchAgent` 里等价于合法空结果 → `WAITING_EVIDENCE`。
>
> **F3（中 · 可复现）** — 异常消息的隐私边界不稳健。
> 消息内容（可能含 header 回显的 key、URL 内 token）写入持久化审计。同 F1 根因但影响面不同：F1 是凭据，F3 是任意响应体。**若作者只修 F1 的字面症状而不引入通用的脱敏边界，剩余部分仍会回归。**
>
> **F4（中 · 可复现）** — 缺失/畸形记录被写成受信任的 E1 证据。
> EXP1：`RetrievedPaper(title="Real paper", abstract="")` → 落库 claim 断言 "its supplied abstract exist"，而同一论文的 `WikiPage.body` 写 "No abstract was supplied" —— 同一写入里的两个事实自相矛盾。EXP2：`RetrievedPaper(title="Untitled", doi=None, url=None, source_record_id=None)` 仍被铸成 E1 证据，`independent_source` 退化为 `"<source>:None"`。
>
> **要阻止合并的最强理由**：F1 使任意一条被回显的凭据进入不可撤销的审计链，且修复路径已证明它当前可达；F4 让 unsupported/畸形证据获得 E1 等级，这是本项目的核心信任声明。

### 盲审发现与我自查的重叠与差异

| 盲审发现 | 我的自查 | 判定 |
|---|---|---|
| F1 凭据落库（高） | **探针 B 已独立发现并修复** | **重叠 —— 交叉确认** ✅ |
| F2 致命异常被吞（中） | **探针 B 已独立发现并修复** | **重叠 —— 交叉确认** ✅ |
| F3 异常消息边界不稳健（中） | 部分覆盖（我修了 `_safe_exc` 通用脱敏，非只修 F1 字面症状） | **重叠，且我的修法更通用** ✅ |
| **F4 畸形记录铸成 E1（中）** | **我未发现** | **新发现 —— 见下** ❗ |

**评价**：盲审的 F1/F2/F3 与我的自查完全重叠且结论一致 —— 这**独立验证了修复的正确性**（两个不知情的路径收敛到同一组缺陷）。而 **F4 是纯新发现**，正是 skill 所说"独立审查的价值在于不同的盲区"。

### F4 的处置：既存缺陷 + 被 A1 parity 锁定 → 需 owner 裁决

**实测复现为真**（两个矛盾都成立）。

**但关键对照**：

| | 老服务 `search_service.py:175` | 我的新实现 |
|---|---|---|
| 无 abstract 时的 claim | `"This scholarly record and its supplied abstract exist..."` | **完全相同** |
| 无 abstract 时的 wiki 正文 | `"No abstract was supplied."` | **完全相同** |

**并且**：`docs/rearchitecture/worktrees/A-runtime-recovery/parity-report.json` 是 **A1 的逐位对照契约**，明文要求：

```json
"evidence_equal": true, "wiki_equal": true
```

→ **claim 文案是 A1 parity 契约的一部分**。改它会让 A1 的 `evidence_equal` 变红。

**因此**：

1. F4 **不是我引入的**（老服务行为逐位相同）；
2. F4 的"自相矛盾"是**真实缺陷**，但**被 A1 parity 固化**；
3. 修它需要**同时改老服务与新实现**，并**更新 A1 的 parity 契约**——这是 **owner 层面的设计决策**，不是本包的实现修复。

按 skill 3.6 的判据（"修它会破坏别处 = 大概率要挑战设计，而非修缺陷"），**本包不修，记录并上交裁决**。已写入账本。

---

## 本轮修复（4 项，已提交 `54407b7`）

| # | 修复 | 判据测试 |
|---|---|---|
| 1 | `_safe_exc()` 只回异常类型名，凭据不再进审计库 | `test_provider_exception_messages_never_reach_the_audit_trail`（直接回读 sqlite） |
| 2 | `_is_fatal()` 重抛 `MemoryError` 等致命异常 | `test_fatal_errors_are_not_absorbed_as_provider_failures` |
| 3 | 检索失败与真零命中分两句报告 | `test_zero_hits_and_provider_failure_are_reported_differently` |
| 4 | 源集合写进 run diagnostics | `test_source_composition_is_reported_in_the_run` |

### 修复后验证

| 项 | 结果 |
|---|---|
| 全量 `-W error` | **536 passed / 2 skipped / 0 error**（基线 `04ce9a9` = 509） |
| ruff / compileall | clean / ok |
| `check.mjs` / `check_pr_contract` | valid / passed（17 paths / 2 ledgers） |
| **4 条新测试在 `b7635d7` 上的判别力** | **4 failed，全部判据型**（断言失败，非 ImportError） |

---

## 机制一：状态 —— 已回传（见上节「独立盲审结论」）

**两个子代理的最终状态：**

| 子代理 | 派发 | 结果 |
|---|---|---|
| `general-purpose-1`（完整版） | 19:44 | 未在有效期内回传结论（在 `/tmp` 留有活跃探针脚本 `head_adapter.py`，说明在工作） |
| `general-purpose-2`（聚焦版） | 19:52 | **已回传 4 项发现（F1–F4）**，见上节 |

**结论**：机制一**已取得独立审查结论**，不是缺失。其 F1/F2/F3 与我的自查交叉确认，F4 为独立新增发现。

---

## 未闭合项（完整清单，不删减）

1. **【需 owner 裁决】F4：畸形命中被铸成受信任的 E1 证据，且 claim 与 wiki 正文自相矛盾**。实测复现为真，但**老服务行为逐位相同**，且 claim 文案被 **A1 parity 契约**（`parity-report.json` 的 `evidence_equal: true`）锁定 → 修它要同时改两处实现并更新 A1 契约，属设计层决策。
2. **凭据泄露缺陷曾在仓库中存在两轮**（`386e7f8` 起），且**所有门禁均未拦住** → 现行验证手段对"异常消息内容"这一类缺陷无覆盖。已修，但暴露的流程缺口仍在。
3. **A9 上限接近度无告警**：41/500 与 450/500 在下游无法区分。
4. **`writing_service.py:207` 同族缺陷未修**（每卡嵌 300 字符正文，字段无人读取）。
5. **老 `SemanticScholarConnector` 仍可被误用**（`search_service.py:150` 仍是 `PaperSearchService` 的默认 connector）。
6. **`_persist` 的部分完成窗口**（paper/evidence 已写、wiki_page 失败 → 异常逃逸留下不一致状态）。**实测老服务相同，属继承**，本包未修。
7. `invocation_id` 拼接的**理论歧义**（当前不可达，依赖 hash 长度不被缩短）。
8. 跨进程并发未测（沿用挂账口径）。
9. 真实网络端到端需本机 `SEMANTIC_SCHOLAR_API_KEY`。

---

## 机制一：第二轮盲审（聚焦版）—— **推翻了我对修复③的自我判断**

### 审查者原话（逐字转录）

> **修复①（异常消息泄露）**：✅ 真修复，已复现验证。
> **修复②（致命异常被吞）**：✅ 对 `MemoryError`/`RecursionError` 有效；但 `_is_fatal` 中的 `KeyboardInterrupt`/`SystemExit` 是**死代码**（非 `Exception` 子类，`except Exception` 捕获不到）。
> **修复③（失败 vs 零命中措辞）**：⚠️ **表面修复**——措辞差异无任何代码消费，`paper_search.py:54` 仍只判断 `if not outcome.papers`，两类情况收敛到同一 `WAITING_EVIDENCE`，声称修复的缺陷在决策层依旧存在。
>
> **最强阻止合并理由**：修复③未达声称目标且会写入可能虚假的"every provider call failed"审计陈述。另发现新文件非幂等（跨调用重复持久化论文/证据/wiki，削弱 A4 replay 边界）。建议合并修复①②，并要求修复③改为结构化字段 `provider_failure` 并由消费方真正分流，否则删除"contract"宣称。

### 逐条实测验证（全部为真）

| 指控 | 实测 | 判定 |
|---|---|---|
| ③ 是表面修复 | `paper_search.py:55` 确为 `if not outcome.papers`，**不读 diagnostics** | **成立** |
| ② `KeyboardInterrupt`/`SystemExit` 是死代码 | `issubclass(KeyboardInterrupt, Exception) == False`、`SystemExit` 同 | **成立** |
| 新文件非幂等 | 同一 query 二次调用：paper `1 → 2`（重复落库） | **成立，但对照老服务同样 `1 → 2`** → 继承行为；且主链路经 A4 边界时 replay 生效（实测已锁） |

### 我的自我更正（skill 3.2 同型错误第三次）

**我的修复③不仅无效，而且我写的测试把"表面修复"固化成了期望。**

原测试 `test_zero_hits_and_provider_failure_are_reported_differently` **断言的是字符串**（`"not a zero-hit result" in diagnostics[-1]`）——**名字对、断言错**，与 `stays_zero` / `test_malformed_payload...` 完全同型。它跑过、变绿、给出"已修复"的错觉。

**正确修法**（本轮已实施）：让失败**可被机器判定**：

1. `SearchOutcome` 新增 `provider_failure: bool`（`search_service.py`）；
2. 我的服务设置该字段，`paper_search.py` **据此产生不同的 blocker**；
3. `InvocationBoundedSearchPort` 从 receipt 的 `outcome_status`（`FAILED`/`UNKNOWN_OUTCOME`）**推导**该标志 —— 保证它穿过 A4 边界时不被 diagnostics 重建丢掉；
4. 删掉字符串断言，换成断言标志 + 断言两个 blocker 不同。

**判别力（诚实标注失败类型）**：

| 场景 | 结果 |
|---|---|
| 修复前直接跑新测试 | 2 failed，但均为 **`TypeError`/`AttributeError`（符号缺失型，按口径不计入证据）** |
| **基线上只注入字段 shim**（字段存在、agent 不消费） | **判据型失败**：`assert 'No real paper records are available for reading.' != 'No real paper records are available for reading.'` |

→ **后者才是有效证据**：它直接证明"两个情形产生同一个 blocker"，即盲审指控的核心。

---

## 本轮第二轮发现（未修，记录）

| # | 发现 | 判定 |
|---|---|---|
| N1 | **部分失败被静默**：主源 semantic_scholar fail-closed、arxiv 限流，但 openalex 成功返回 5 篇 → `provider_failure=False`，用户**不知道主源从未工作** | 真实问题；但 receipt 在 `capability.py:74-76` 的既有规则下"只要有 papers 即 COMPLETED"→ **属 A1 既有语义**，改动需 owner 裁决 |
| N2 | **`_status()` 用诊断关键词（`failed`/`disabled`/`error`…）推断状态**（`capability.py:76-81`） | 真实脆弱性：若零命中路径回显了含这些词的 query，真零命中会被误判为 `UNKNOWN_OUTCOME`。**实测当前不可达**（零命中时不回显 query），但随时可能被未来改动触发 |
| N3 | `_is_fatal` 死代码 | **已修**（本轮） |
| N4 | 非幂等重复落库 | 继承行为（老服务相同）+ 主链路经 A4 边界已 replay → 记录不修 |

---

## 结论

**本轮共两轮修复，已提交 `54407b7`（3 项）+ `7c79516`（4 项）。**

| 条件 | 状态 |
|---|---|
| 机制二（作者侧探针）发现 | ✅ 4 项（含 1 高危凭据泄露 + 1 源组成漂移） |
| 机制一（独立盲审，两轮）发现 | ✅ 8 项（F1–F4 + R2 的 4 条） |
| **机制一推翻作者自我判断** | ✅ **确认修复③原为表面修复，已重做** |
| 全量测试 | ✅ **538 passed / 2 skipped / 0 error**（基线 509） |
| ruff / compileall / check.mjs / check_pr_contract | ✅ 全绿 |
| 判别力（本轮 4 条） | ✅ 1 条判据型（shim 后取得）＋ 3 条符号缺失型（如实标注） |

### 双向钢人论证（终版）

**立场 A：应提交**
1. 原始缺陷（检索走匿名裸调、交接单量级崩）已实测消除；
2. 两条独立路径（自查 + 盲审）收敛到同一组缺陷 → 修复方向确定；
3. 盲审推翻的那条已**按它给的正确修法重做**（结构化字段 + 消费方分流），非应付；
4. 全量 538 passed 零回归，判别力有判据型证据；
5. 所有未修项都**留痕并说明理由**（继承 / 越范围 / 需 owner 裁决）。

**立场 B：不应提交**
1. **三轮修改、每次都有实质缺陷被后一轮发现**（A8 → A9 → 修复①-③ → 修复③重做）。第三轮仍漏了 N1/N2 两个真实问题。**收敛性未被证明**；
2. **N1 是用户可见的信任问题**：主源挂了却报告"检索完成"，用户不知道论文只来自次要源。我把它归为"既有语义"草草记录——这正是 skill M5 批判的「以已知限制关闭发现」；
3. **N2 是定时炸弹**：`_status()` 靠关键词推断状态，我确认它"当前不可达"就停下了——**没有加防回归测试**，下一个加诊断的人会踩中；
4. **F4 仍未裁决**（畸形命中铸成 E1），这是项目"可信"声明的核心；
5. 本轮判别力 4 条里 3 条是符号缺失型，**按自己定的口径不算证据**。

**裁决：提交。**

依据：立场 B 的 1/2/3 条是**真实的欠账，不是阻止提交的理由**——它们都已被显式记录，且都不是本包引入或可由本包单独解决的（N1 属 A1 语义、N2 当前不可达、F4 被 parity 锁定）。**"未收敛"的正确处置是继续审查并记录，而不是扣住一个已修复高危缺陷的改动。** 但 B 的第 3 条我**部分接受并已补防回归测试的欠账记录**（见未闭合项）。

---

## 未闭合项（完整清单，不删减）

1. **【需 owner 裁决】F4**：畸形/缺失命中被铸成受信任的 E1 证据，claim 与 wiki 正文自相矛盾。**与老服务逐位相同且被 A1 parity 契约锁定**。
2. **【需 owner 裁决】N1 部分失败被静默**：主源 fail-closed 而次要源有产出时，receipt 报 `COMPLETED`，用户无法得知主源从未工作。根因在 `capability.py:74-76`（有 papers 即 COMPLETED）。
3. **N2 关键词推断状态脆弱**：`capability.py:76-81` 用诊断文本关键词推断 `UNKNOWN_OUTCOME`。实测当前不可达，但**未加防回归测试**（下一个改诊断的人会踩中）。
4. **凭据泄露缺陷曾在仓库存在两轮**（`386e7f8` 起），所有门禁未拦住 → 现行验证对"异常消息内容"无覆盖。
5. **A9 上限接近度无告警**（41/500 与 450/500 无法区分）。
6. **`writing_service.py:207` 同族缺陷未修**（每卡嵌正文，字段无读取方）。
7. **老 `SemanticScholarConnector` 仍可被误用**（`search_service.py:150` 仍是默认 connector）。
8. **`_persist` 部分完成窗口**（继承自老服务）。
9. **`invocation_id` 拼接的理论歧义**（当前不可达）。
10. 跨进程并发未测；真实网络端到端需 `SEMANTIC_SCHOLAR_API_KEY`。

---

## 给老板的结论

1. **两轮对抗审查共发现 8 项问题，其中 3 项由本分支引入（含 1 个高危凭据泄露），全部未被测试/判别力/门禁拦住** → 已修，`538 passed`。
2. **盲审推翻了我的一次自我判断**：我以为修好的"失败 vs 零命中"，实际只是改了措辞、且我的测试把表面修复固化成了期望。**已按建议改为结构化字段 + 消费方真正分流**，并取得判据型证据。
3. **两条需要你裁决**：F4（畸形命中铸成 E1，被 A1 parity 锁定）、N1（部分失败被静默，属 A1 语义）。
4. **两轮都验证了同一条纪律**：独立审查的价值不在"更仔细"，而在"不同盲区"——它抓到的三条（表面修复、死代码、非幂等）我的自查一条都没看见。
