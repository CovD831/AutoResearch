# AutoResearch 重构包：薄 Runtime、可插拔能力与独立证据模块

> 状态：入口摘要；完整 R-001 架构包见 [`docs/rearchitecture/R001/`](rearchitecture/R001/)。本文件不是完整重构包。  
> 增量：R-001 / 0.1.1 architecture boundary  练习  
> 日期：2026-09-03  
> 负责人：用户/项目负责人 + AutoResearch maintainer  
> 入口：本文件是本轮重构的短路径；当前实现仍以 `src/autoresearch/` 和 `docs/ARCHITECTURE.md` 为准。

> **[2026-09-03 目录更新]** 上文第 1–10 节描述的 R-001 已被后续程序取代：当前活动程序为 **R-004-TRUST-PROGRAM**（`docs/rearchitecture/R004-trust-program/`，含 R-002/R-003 双轨与继承 findings）。最新增量：**R-005-S1-CLOSURE**（design，`docs/rearchitecture/R005-s1-closure-design/`）——对账在飞 S1 adapter 实现并冻结 parity/recovery 证据计划；exact next task：`S1-CLOSURE-EVIDENCE`（owner: user/team）。

## 1. 本增量要解决什么

当前 foundation 已经验证五 Agent、LangGraph、SQLite checkpoint、基础证据门禁和项目账本可以联通，但产品能力仍集中在一个应用装配层：`AutoResearchApplication` 直接构造所有 Service、具体 Agent、SQLite checkpointer 和父图；Agent 又直接依赖具体 Service、`RecordStore`、`GateService` 和 `StateMachine`。

这会带来三个问题：

1. 用户不能低成本替换自己偏好的 skill、MCP 或成熟工具。
2. Runtime、科研能力和治理规则混在一起，改变一个能力容易牵动整个工作流。
3. “可信”已被实现为内部机制，但还没有成为可独立复用的证据产品能力。

本增量的目标不是重写所有功能，而是冻结新的边界，并选择一条真实纵向切片验证它。

## 2. 目标定位

AutoResearch 目标定位为：

> 一个面向科研 Agent 生态的薄运行时和可信交付层。

它不负责拥有所有论文搜索、阅读和写作能力；它负责把外部能力组合成可恢复、可追踪、可验证的研究运行，并把工具结果转换成统一的研究资产和证据引用。

### 本增量包含

- 薄 Runtime 的 L1 边界和依赖方向。
- 独立 Evidence Module 的责任、写入权和查询边界。
- Skill / Plugin / MCP 的适配接口，而不是具体插件实现。
- 当前模块到目标模块的迁移映射。
- 第一条迁移切片：`paper-search capability -> evidence adapter -> research run`。

### 明确不包含

- 不一次性重写五个 Agent。
- 不把每个 Service、函数或文件都改成插件。
- 不承诺动态卸载、热更新、同进程多版本隔离或分布式调度。
- 不在本增量内替换 SQLite 为 PostgreSQL/Neo4j。
- 不把外部 skill/MCP 的文本质量自动等同于科研事实。

## 3. L1 目标架构

```text
                    User / CLI / API / future UI
                              |
                    Thin Runtime API (orchestration)
                              |
             +----------------+----------------+
             |                                 |
      Capability Registry                Run/Checkpoint Adapter
             |                                 |
       +-----+------+------------------+       |
       |            |                  |       |
     Skills       MCPs          Native Adapters |
       |            |                  |       |
       +------------+------------------+       |
                    | typed results / receipts
                    v
            Research Domain Services
       search | reader | execution | writing
                    |
                    v
             Evidence Module (独立)
        claim/evidence/artifact/provenance
                    |
          Gate / audit / release policy
                    |
                    v
       Project Ledger + durable stores + files
```

### 所有权与依赖方向

| 边界 | 唯一职责 | 唯一写入权 | 不负责 |
|---|---|---|---|
| Thin Runtime | 装配配置、调用 capability、驱动 run/checkpoint、返回 bounded result | run execution receipt、runtime config snapshot | 论文内容判断、证据评级、具体工具实现 |
| Capability Registry | 注册和解析 skill/plugin/MCP capability manifest | registry snapshot | 业务事实、Gate 决策 |
| Capability Adapter | 把外部工具/skill 输出转成 typed result/receipt | adapter invocation receipt | 直接修改证据真相 |
| Research Services | 领域操作，如搜索、阅读、写作、实验 | 对应领域产物 | 统一治理策略、插件发现 |
| Evidence Module | 保存 claim、source、artifact、provenance、失效和关联 | EvidenceItem/ClaimLink/ArtifactLink/audit | 搜索论文、写论文、运行模型 |
| Policy/Gate | 根据 Evidence Module 的事实作确定性判定 | GateDecision | 生成内容、替换证据 |
| Project Ledger | 保存项目目录、阶段和交付投影 | project/run index 与文件投影 | 重新解释证据 |

依赖必须单向：`Runtime -> Capability/Domain -> Evidence/Policy -> Store`。Evidence Module 可以被 Runtime、Domain Service、外部审核工具调用，但不能反向依赖某个具体 Agent。

### 受控交互形式

- `Command`：Runtime 调用 capability 或 domain service。
- `Typed transfer`：在 Agent/Service 间传递 bounded request/result。
- `Query/View`：读取证据、项目和运行状态。
- `Receipt/Evidence`：记录外部调用、来源、版本、定位和结果。

第一阶段不引入通用消息总线；明确调用者和唯一写入者优先。

## 4. L2 边界合同（第一版）

### 4.1 Capability Manifest

```yaml
name: paper-search
kind: mcp | skill | plugin | native
version: 0.1.0
entrypoint: configured-by-host
inputs: [research_query, project_id, run_id]
outputs: [paper_records, diagnostics, receipts]
evidence_mode: metadata | fulltext | derived
permissions: [network.read, project.write]
```

Manifest 是声明，不是信任证明。Runtime 只根据声明决定是否可调用；Evidence Module 仍必须根据实际输出单独记录来源和有效性。

### 4.2 Capability Invocation

- 输入必须包含 `project_id`、`run_id`、capability name/version 和 bounded request。
- 输出必须是 typed result，加上 invocation receipt；禁止把原始完整聊天作为 handoff。
- 相同 `run_id + invocation_id` 重放返回相同 receipt；冲突输入拒绝。
- capability 失败由 adapter 隔离并返回诊断，不得伪造空成功。
- 未知外部写入结果不得自动重试或标记成功；由 Runtime 保留 `unknown` 状态。

### 4.3 Evidence Module

- 接收 `EvidenceCandidate`，生成不可变 `EvidenceItem`。
- 只有 Evidence Module 能写入证据状态、失效、替代和 claim linkage。
- 能力模块可以提交候选，但不能自行提高 evidence grade 或通过 Gate。
- Evidence 查询只暴露 bounded view：evidence id、source、locator、claim、status、provenance。
- 证据正文和大型 artifact 留在受控文件/对象存储，证据模块保存引用和版本信息。

### 4.4 Agent / Skill / MCP 关系

- Agent 是稳定的业务角色（仍保留五个）。
- Skill 是可替换的方法/提示/脚本包，由 Agent 选择或由 workflow 配置绑定。
- MCP 是外部工具和数据连接，不拥有项目状态或 Gate 权限。
- Plugin 是打包格式，可以携带多个 skill、MCP 配置、命令和领域默认值。

## 5. 当前到目标映射

| 当前实现 | 动作 | 第一目标归属 | 保留的兼容路径 | 移除条件 |
|---|---|---|---|---|
| `AutoResearchApplication` 大型构造器 | split / expose | `RuntimeFactory` + capability registry + domain composition | 旧构造器保留 facade | 新旧路径同一纵向 fixture 的 receipt、state、checkpoint 等价 |
| `search_service.py` 内置三连接器 | adapt | `PaperSearchCapability` adapter | native adapter 继续可用 | MCP/native parity fixture 通过 |
| `evidence.py` + `gates.py` | split authority | 独立 Evidence Module + Policy adapter | 现有类提供兼容 facade | 外部能力不再直接触碰 `RecordStore` 证据表 |
| Agent 直接依赖 `RecordStore` | expose / adapt | typed ports + domain services | facade 注入旧 service | Agent contract 测试不再要求具体 store |
| `graph.py` 直接拼装具体 Agent 子图 | adapt | Runtime workflow plan | 旧 `build_research_graph` wrapper | capability composition fixture 通过 |
| CLI/API 直接实例化 Application | retain / adapt | Runtime entrypoint | `AutoResearchApplication` 作为兼容入口 | 新入口覆盖 doctor/run/status/resume |
| `knowledge.py` Wiki+Graph | retain, later adapt | Project knowledge capability | 当前本地实现 | 只有在外部知识适配器有真实消费者时再拆 |

## 6. 第一条真实迁移切片（R-001-S1）

### 选择

把“论文搜索”作为首条切片，而不是先重构全部 Agent。它同时具备：外部能力替换需求、明确输入输出、已有 native implementation、可生成 evidence receipt、容易构造 legacy/target 对照 fixture。

### 必须证明

1. native paper search 和一个外部 capability adapter 都可以接入同一 Runtime。
2. 两条路径都产出相同语义的 `PaperRecord`、diagnostic 和 invocation receipt。
3. 证据写入只经过 Evidence Module，Gate 仍由 Policy 决定。
4. 旧 `AutoResearchApplication.run` 继续可用。
5. 重启/重放不会重复写入同一个 invocation 的证据。

### 不得声称

- 不证明外部 MCP 的检索质量优于 native connector。
- 不证明整个五 Agent 工作流已经插件化。
- 不证明生产部署、动态更新或跨进程隔离已经完成。

## 7. 迁移阶段与停止条件

### S0：合同冻结（本增量）

- 交付：本文件、Capability Manifest 草案、当前到目标映射、S1 验收矩阵。
- 停止条件：如果用户不接受 Runtime/Evidence/Capability 三层边界，不进入代码迁移。

### S1：Paper Search Adapter

- 新增最小 registry、adapter port、invocation receipt 和 EvidenceCandidate 转换。
- 旧 native connector 作为 legacy fixture；新增一个可控 fake capability 作为 target fixture。
- 通过后才允许接入真实 MCP。

### S2：Reader / Writer capability ports

- 将 Reader、Writer 的具体 service 依赖改为 typed ports。
- 外部 skill 可以替换方法层，但所有 claim 仍经 Evidence Module。

### S3：Experiment / Manuscript lineage

- 把 Git、实验运行、artifact、图表和稿件 claim 关联起来。
- 目标是形成 `Claim -> Evidence -> Experiment -> Manuscript` 闭环。

### S4：Plugin packaging

- 只有当至少两个真实 capability consumers 需要统一安装/版本/权限管理时，才引入正式 plugin lifecycle。

### 回滚边界

- 每个阶段保留旧 facade 和 legacy fixture。
- 若 target receipt、持久化事实、checkpoint 或失败语义不等价，停止晋级，恢复旧入口，修订合同。

## 8. 初步复杂度预算

本增量只增加四个核心名词：`CapabilityManifest`、`CapabilityAdapter`、`InvocationReceipt`、`EvidenceCandidate`。每个名词都有 S1 的真实消费者；不提前新增 scheduler、bus、plugin loader、sandbox 或第二套数据库。

## 9. 开放决策（需要用户确认）

以下选择会影响 L1/L2 和迁移顺序：

1. **首个垂直场景**：推荐 ML/Systems 的“实验到论文”；替代方案是 systematic review 或生物医学文献工作流。
2. **外部能力边界**：推荐先支持本地 skill + MCP adapter，不在第一阶段承诺任意远程插件执行。
3. **Runtime 部署边界**：推荐先保持单进程/本地可运行，插件若有冲突版本或不可信脚本再单独设计进程隔离。

在用户确认前，S0 只冻结设计和测试合同；不迁移生产代码。

## 10. Promotion gate

本设计增量只有在以下条件满足后，才可把 target 文本提升为 current architecture：

- S1 legacy/target fixture 都通过 contract、failure、idempotency、restart 测试。
- 旧 CLI/API 结果和新 Runtime 的 bounded result、durable facts、receipt、checkpoint 语义等价。
- `Evidence Module` 成为证据唯一写入者，Agent/Capability 不再直接改证据真相。
- `.ai-team/TASK.md`、`docs/ARCHITECTURE.md` 和 Project-to-Act 的当前状态同步更新。

当前结论：**继续到 S1，但先等待第 9 节的三项产品边界确认。**
