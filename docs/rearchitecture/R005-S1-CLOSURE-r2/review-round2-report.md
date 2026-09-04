# R005 第二轮对抗审查 + 双向钢人论证（外部）

> 审查人：R-004 程序包作者会话（fresh pass，逐文档重读 + 源码逐行核验）。身份披露：审查者不是 R005 作者，但同属本项目维护者，非完全独立第三方。
> 输入：R005 全部文档 + `src/autoresearch/capability.py`、`search_service.py`、`application.py`、`contracts.py`、`tests/test_capability_adapter.py`、R-004 ADR。
> 纪律：不修改 manifest/ledger——本报告的 findings 消费是 R005 owner 的动作；本文件仅落盘审查产物。

## 一、事实核验（对抗审查第一步：现有事物与代码对不对得上）

| R005 claim | 核验结果 |
|---|---|
| A-1 reserve 先于副作用（capability.py:68） | ✅ 与源码一致（:68 reserve → :73 search） |
| A-2 重放/冲突拒绝有测试 | ✅ 两个命名测试均存在 |
| A-3 pending 残留 → RuntimeError，且缺构造性测试 | ✅ 代码路径在（:57-58, :72），测试确缺 |
| A-5 重放覆写 outcome | ✅ :65 `model_copy(update={"status":"replayed"})`，真 bug |
| B 边界未接线（无消费者） | ✅ `application.py:76` 构造后无调用方 |
| B-1 双表示（_persist 写 EvidenceItem actor=paper_search + WikiPage；adapter 另产候选） | ✅ `search_service.py:160-195` 逐行证实 |
| ADR-7 L1 写入者偏差 | ✅ adapter 直写幂等表属实，与 R-004 写入者表冲突，已如实申报 |

**结论：无一处事实造假或 target/current 混淆。R005 的诚实性核验通过。**

## 二、新发现（R005 未自查到）

| Finding | Evidence | Severity | Decision | Consuming action | Owner/gate |
|---|---|---|---|---|---|
| F-R5-2-01 receipt 的 `unknown` 语义混淆两种本质不同的情形：provider 结果不确定（该 fail-closed）与"检索完成、合法零命中"（这是一个**确定的**结果，领域规则只禁止编造论文，不禁止空结果）。`capability.py:79` 把两者都写成 `unknown`，diagnostics 里的区分被 status 抹平 | capability.py:79 + A-4 的表述 | non-blocking（设计层），**建议在 L3 冻结时升为必答** | accept | B-2 归一化规则或 L3 增加裁决：拆分 `completed_empty` 与 `unknown_outcome`（或明确声明合并语义及其代价），否则 parity 会把该混淆冻结进断言 | S1 implementer / S1 L3 冻结 |
| F-R5-2-02 B-2 冻结清单遗漏 knowledge 页，而 `_persist` 的写入物（paper 记录、EvidenceItem、WikiPage 三件）在设计时完全可枚举——ADR-8 后果条款自己预言了"若发现清单遗漏（如 knowledge 页）"，明知可枚举而不枚举，等于把 wriggle room 冻结进"无 wriggle room"的断言 | search_service.py:_persist + 04 B-2 清单 | non-blocking | accept | 按 L2 修订流程现在补入 WikiPage 比较项（一行事），不等实现发现 | R005 author / 即时消费 |
| F-R5-2-03 B-1 两方案的崩溃窗口不对称未记录：方案 (b) 下 durable 证据在 receipt finalize **之前**落盘（_persist 在 search 内部执行），崩溃会留下"有证据、无 receipt"的 pending 记录；且恢复操作的语义（recover=标记失败 还是 重执行？）只列为任务，没有命名 decision gate——这是任务清单里唯一欠规格的新 API | 04 B-1 约束 + 06 task 2 | non-blocking | accept | 06 task 2 补"恢复操作语义"gate；B-1 裁决时评估两方案的崩溃窗口 | S1 implementer / S1 L3 |
| F-R5-2-04 编号线谱系事实错误：05-adr 称"R-004 用 06-adr-r002 的 ADR-1..3"，实际 R-004 有 ADR-1..4（含 Audit 外化） | R004/06-adr-r002.md | non-blocking（doc nit） | accept | 修一句 | R005 author / 即时消费 |

另记一个未立 finding 的观察：任务 1（parity）产出在任务 3（B-1 接线）改变持久化行为后会过期，"advancement trigger 要求可复现命令"隐含了晋级前重跑，但建议 06 明说"任务 3 后必须重跑任务 1 命令"。

## 三、双向钢人论证

### 最强支持论证

R005 把"考古"变成了"执行清单"，而它真正的决定性美德是在设计包最常撒谎的三个点上选择了诚实：(1) 代码与自家程序 L1 冲突时（adapter 直写幂等表 vs R-004 写入者表），它没有宣称"L1 无变化"而是自报偏差并挂 promotion gate（ADR-7）——这是对**自己所在权威链**的背叛式诚实，整个仓库此前的包都没做到；(2) 它把 parity 断言模型冻结在设计层（ADR-8），剥夺了实现者悄悄弱化测试的自由；(3) 它的考古发现了在飞实现自己都不知道的真 bug（A-5 重放抹掉原始 outcome）和"边界根本没接线"这一根本事实。规模纪律同样成立：零新名词、拒绝 exception、S2 继续上锁、每个 open 项有 owner 和 gate。作为交接文档，它把下一个会话的自由度压缩到恰好两个设计决定（B-1 二选一、A-5 修法），其余全是照写测试。**这正是"开发就绪"的形态。**

### 最强反对论证

R005 是一个元产物：一个以"产出证据的计划"为交付物的设计包，坐在一条已经六个包深、**零次 promotion** 的链条顶端。用程序自己的北极星（S1 晋级 → S2 解锁 → Audit 产品）度量，R005 是团队与"运行代码"之间的第七道守门文档——一个纪律严整的实现者直接写测试关闭 R-003 findings，很可能比"写 R005 + 审一轮"更快地产出同样的证据。它的"无 wriggle room"主张至少在三处言过其实：冻结的 parity 清单漏掉了 `_persist` 明明白白写的 knowledge 页（ADR-8 自己的后果条款承认了这一点——冻结一个已知不完整的清单，就是冻结 wriggle room 本身）；`unknown` 语义把合法零命中和 provider 不确定混为一谈，"fail-closed"的表层声明下面藏着一个会在实现中途爆炸的领域语义决定；恢复操作的语义只有任务名没有决定门。最后，它的审查由作者本人消费、closure cycle 未花——本包的全部质量主张建立在单轮未复验的审查上。**一个纸面完美但把程序推向"第七个包"的文档，可能是对"设计多于实现"这一已知病因的又一次喂养。**

### 综合结论

维持上轮判定：**R005 可以作为进入开发阶段的文档包**。四条新 finding 全部 non-blocking，其中 F-R5-2-01（unknown 语义）应在 S1 L3 冻结时作为必答题处理，F-R5-2-02/004 可即时消费，F-R5-2-03 归入 L3。反对论证的分量主要落在程序节奏而非包质量上：R005 之后**不应再有第八个设计包**——下一个产物必须是跑通 F-R5 所列命令的实现证据，否则钢人论证的反对侧将自动成立。
