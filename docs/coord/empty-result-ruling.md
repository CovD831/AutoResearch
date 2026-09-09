# D-F8-01 · R003 空结果语义裁决（F-8 关闭）

- 裁决日期：2026-09-10
- 裁决人：Owner（授权领航执行核验与文书）
- 关闭对象：TASK-SPECS A2 节 F-8 挂账（来源：PR2-A1-deep-review.md F-8，minor）
- 关联：O6 S2 promotion gate 前置（blocking findings 清零）

## 1. 冲突描述

- `docs/rearchitecture/R003-paper-search-adapter/01-l3-paper-search-adapter.md`（S1 实现权威，R004-04b 确认）：
  **"An empty result is `unknown`, never successful invention."**
- A1 实现（TASK-PACKAGE §8 / `capability.py`）：connector 正常返回且结果集为空 → **`completed_empty`**（确定性终态）。
- 两份权威语义相反；A1 语义已被 S1 promotion、主线 E2E 与全量回归（108 passed）锁定。

## 2. 裁决

**以 A1 实现语义为准，R003 L3 文档回写。**

### 2.1 权威定义

- **`completed_empty`**：invocation 正常执行至 `finalized`、外部副作用已收口、返回结果集为空。它是**确定性成功终态**，语义为「查询合法执行且确定无命中」。
- **`unknown_outcome`**：仅由**执行中断**产生——timeout、进程重启、`service_started` 之后崩溃且外部副作用不可知；只能经 `recover_pending`（phase 感知）显式收敛，禁止由正常执行路径声明。

### 2.2 边界规则

1. 二者互斥，终态由 phase 推导（A2 F-2 决策表：`reserved → failed`；`service_started → unknown`；`service_returned → finalize staged`）。
2. `completed_empty` 的 run 对下游（readiness/B 线）语义 = **材料缺失** → `needs_material` / `blocked`，不得静默通过，不得虚构内容。
3. `unknown_outcome` 的 run 在显式恢复前**不得被任何消费方读取业务结果**（A1 契约测试已锁定）。

## 3. R003 立法本意的保留

R003 原句的意图是防止把空结果包装成成果（"never successful invention"）。该意图在实现侧由更强机制承载：

- `completed_empty` 不产生任何 EvidenceItem / candidate（Evidence sole-writer 边界）；
- INV-10：work package `completed` 须有本项目 valid 证据；
- B 线 fail-closed：材料不足 → `blocked` / `needs_material`，正文保留缺口。

因此**意图完整保留，标签修正**：确定性空结果不再误用 `unknown` 标签（`unknown` 保留给真正不可知场景，与 A2 phase 决策表一致）。

## 4. 回写清单（本裁决同步完成）

| 回写点 | 状态 |
|---|---|
| R003 L3 文档加裁决注记（不改历史正文） | ✅ 本提交 |
| TASK-SPECS A2 节 F-8 → 已关闭（指向本文件） | ✅ 本提交 |
| TASK-PACKAGE-REGISTRY 挂账行关闭 | ✅ 随 O6 回写 |
| T 线回归基准引用本文件（INV-10/A1 契约测试已覆盖） | ✅ 既有测试即为断言载体 |

## 5. 下游约束（S3/S4 消费方必读）

- B4 Reader/Writer Ports、A4 adapter receipt 在遇到 `completed_empty` 时按「材料缺失」路径处理；
- 禁止任何 lane 重新引入「空结果 = unknown」的解释（M7：语义全仓库唯一权威，禁止私约）。
