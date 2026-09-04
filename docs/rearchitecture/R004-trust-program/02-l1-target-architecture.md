# R-004-02 L1 目标架构

> 配图：[diagram/autoresearch-architecture-r004.png](diagram/autoresearch-architecture-r004.png)（SVG 源与可编辑数据：`diagram/architecture.svg` / `diagram/architecture-data.json`，fireworks-tech-graph Style 1 生成，已通过全部几何/构图/碰撞校验门）。

继承 INDEPENDENT-2026-09-03 的 L1（构造/依赖/交互/唯一写入者），本文件是其后继权威版本，并做四处修订。

## 边界图（修订后）

```text
CLI / API / audit CLI / MCP server (stdio, 本地)
        |
   Thin Runtime (compose, invoke, receipt, checkpoint)
        |
   Capability Registry (manifest + operator 指派的 trust tier)
        |
   Native / MCP / Skill adapters
        |
   Research Domain Ports: search | reader | writer | reviewer
        |
   Evidence Module <---- Policy / Gate
        |                      ^
   Audit Module --AuditVerdict/EvidenceCandidate--+
        |
   Project Ledger / Store / Artifacts
```

## 修订 1：Audit Module 边界

- Audit Module 是 Evidence Module 的**只读消费者 + candidate 提交者**：读取 bounded evidence view，执行引用存在性、locator 一致性、撤稿/版本/时效核验；核验结论以 `AuditVerdict` 进入 Policy 输入，并以 `EvidenceCandidate` 回流 Evidence Module。
- Audit Module 不直接写 EvidenceItem、不产生 GateDecision；报告本体是 artifact。
- 对外出口仅两种本地形态：CLI 子命令与 stdio MCP server。不提供远程监听。

## 修订 2：Capability trust tier 由 operator 指派

- manifest 自述 `evidence_mode` 只是声明；生效的信任层级（`candidate_only` / `compliant_structured`）由 operator 在项目配置中注册时指派，并记录为 H2 人工证据。
- `candidate_only` 能力产出上限 P0/H1，须过 Audit Module 核验后才可晋级；`compliant_structured` 能力的 typed 产出可直接进入接纳检查（仍由 Evidence Module 定级）。

## 修订 3：五 Agent 不变量改写（领域模型化）

- 原约束（D-001）：运行时恰好五个业务 Agent。
- 新约束：恰好五个**领域角色** `search | reader | writer | reviewer | orchestrator`；前四个是 Domain Port 上的能力组合，orchestrator 的协调职责（范围、派单、进度）属于 Thin Runtime 与领域服务，不是独立 Agent 节点。
- 不变量精神不变：能力模块不得引入第六个业务角色；服务节点不得伪装成角色。
- 该修订需用户批准（已获，见 06-adr ADR-2），并在 S1 promotion 时同步 `PROJECT_OVERVIEW.md` 与 `docs/AutoResearch_详细计划书.md` §2。

## 修订 4：部署边界重申与收紧

单进程、本地、SQLite 为规范存储；远程能力仅通过显式 MCP adapter 接入且默认关闭网络；Audit Module 的核验请求走 manifest 声明的 resolver adapter（Crossref/OpenAlex/Asta），未配置网络时 verdict 必须为 `unknown`，不得 fail-open。

## 唯一写入者（继承 + 增补行）

| 事实 | 唯一写入者 |
|---|---|
| capability manifest/version | Capability Registry |
| invocation receipt | Thin Runtime |
| PaperRecord/ReadingCard/Manuscript | 对应 Domain Service |
| EvidenceItem/ClaimLink/ArtifactLink/invalidations/AuditVerdict 回流候选 | Evidence Module |
| GateDecision | Policy/Gate |
| AuditReport artifact 内容 | Audit Module（经 Persistence Port 写 artifact；与其的 ArtifactLink 由 Evidence Module 持有） |
| run lifecycle/checkpoint | Runtime + Checkpoint Adapter（各自边界内） |
| project file projection | Project Ledger |

禁止反向依赖与越权：Agent/Skill/MCP/Adapter → Store 直写、→ GateDecision；Gate → Writer；Audit → EvidenceItem 直写。
