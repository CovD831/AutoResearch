# 05 ADR — R-005-S1-CLOSURE

一选择一 ADR；状态与后果如下。编号沿用程序线（R-004 的 06-adr-r002 含 ADR-1..4：合并、用户决策、冻结清单、Audit 外化）。

## ADR-4：Resume 选择 repair-first，不授予 exception

- Status：accepted（2026-09-03）
- Decision：对未满足的程序推进门（R-003 AR-005 pending、R-002 8 条 pending、R-004 AR-OLD-002/004/005/006 open）采取 **repair-first**：用当前树新证据把可闭环的记录闭环（R003-AR-002/004 → resolved），其余保持 open 并由本包设计其关闭路径。不把缺失证据记为 exception。
- Alternatives：(a) 授予 exception 晋级 S1 —— 拒绝：parity/recovery 语义从未被验证，违反 R-004 stop_rule；(b) 放弃 S1 —— 拒绝：在飞实现已覆盖大半缺口，弃用是更大浪费。
- Consequences：程序触发条件仍 unmet，S2 继续被挡；R-002 的 8 条 pending 不在本包处理（其 owner 未动）。旧包对新 checker 的结构漂移（`profile` vs `size` 等，[evidence-checker-prior-packages.txt](evidence-checker-prior-packages.txt)）只记录为 backlog、不重写旧 manifest——改写历史包的状态字段会伪造当时门禁状态。
- Delegation：UD-004（[decisions/UD-004-resume.json](decisions/UD-004-resume.json)），用户委托，approver = user（委托）；reversal condition：用户改选 exception 时按 review.md 补 approver 记录。

## ADR-5：下一个最小 design 增量 = S1-closure（本包），S2 继续推迟

- Status：accepted（2026-09-03）
- Decision：新包 R-005-S1-CLOSURE（design size）作为 R-004 程序的下一增量；内容限定为"对账 + parity/recovery 证据计划"。
- Alternatives：(a) S2 Audit Module design —— 推迟：R-004 stop_rule 要求 S1 晋级证据先行，在未验证的地基上叠设计违反 doc-gates（无消费者证据的概念推迟）；(b) 只做 orientation —— 不足：L1/L2 无变化，但 open claims（04 A-5/B-1/B-2）没有着落点，下次会话仍需重新考古。
- Consequences：本包以 recommendation 收尾（implementation-candidate），不授权实现；S2 的开工门不变。
- Delegation：UD-005（[decisions/UD-005-next-increment.json](decisions/UD-005-next-increment.json)），用户委托选择推荐项。

## ADR-6：证据计划用"冻结命令 + 落盘结果"，不引入新验证框架

- Status：accepted（2026-09-03）
- Decision：S1 关闭所需证据按 delivery.md 迁移证据规则由**一条可重跑命令**产出并落盘（见 06 的 exact next task）：pytest 扩展文件（recovery/unknown/parity 参数化测试）+ parity 报告文本。每个证据绑定归属 finding（R003-AR-005、AR-OLD-002/004/005/006）。
- Alternatives：新建 `scripts/verify_s1.py` 或独立验证框架 —— 拒绝：一个测试文件 + 一条 pytest 命令即可复现，新增机制无独立消费者（doc-gates over-design gate）。
- Consequences：实现包的验收矩阵直接引用这些命令；不新增名词、不新增 runner。复杂度预算增量 = 0 个新名词。（修订：原"parity fixture 断言集推迟到实现层"由 ADR-8 取代——review AR5-003 判定断言模型必须现在冻结。）

## ADR-7：声明 L1 写入者偏差（adapter 经 store 幂等表写调用记录），交程序 owner 裁决

- Status：proposed → 待 R-004 程序 owner 在 S1 promotion gate 裁决（2026-09-03，review AR5-002）
- Decision：如实记录当前树与 R-004 L1 的偏差：R-004 规定 `invocation receipt | Thin Runtime` 且禁止 `Adapter → Store 直写`，而 `capability.py` 的 adapter 直接写幂等记录（含 receipt payload）。本包推荐在程序 L1 增补写入者行 `capability invocation idempotency record | Capability Adapter（经 Store 幂等方法）`，与 run 级 receipt 写入者并存。
- Alternatives：(a) 责成实现包把幂等写收回 Runtime 侧 —— 保留为裁决备选；若 S1 L3 选此路，本 ADR 作废；(b) 维持"零修改"表述 —— 拒绝：那会掩盖真实偏差（review 判 blocking 成立）。
- Consequences：02-l1-target 不再声称 "L1 pass (unchanged)"；S1 晋级前该偏差必须有正式归属。Owner：R-004 程序 owner（user/team）；gate：S1 promotion。

## ADR-8：parity 断言模型现在冻结（取代 ADR-6 的推迟部分）

- Status：accepted（2026-09-03，review AR5-003）
- Decision：parity 的比较对象与归一化规则在 design 阶段冻结（隔离双库、自动生成 ID 按形态比较、durable facts 精确清单、checkpoint 按 run 状态投影比较）。全文见 [04-l2-contracts.md](04-l2-contracts.md) B-2。
- Alternatives：推迟到实现包 L3 —— 拒绝：parity 是本包存在的理由，比较对象不定义则实现者必然自行发明断言，评审无法核对其证明力。
- Consequences：实现包可以直接写测试；若实现时发现清单遗漏（如 knowledge 页），按 L2 修订流程补充而非静默扩大。
