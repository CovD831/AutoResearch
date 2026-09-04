# R-001-01 定位、范围与复杂度预算

## 要解决的问题

AutoResearch 当前已经有很多科研功能，但多数能力通过具体 Python 类和大型 Application 装配。结果是替换一个用户偏好的 Skill/MCP 时需要触碰 Runtime、Agent、Service 和 Store 多层代码；证据和治理也容易被当成各个 Agent 的私有逻辑。

## 目标用户

- 使用自有 Skill、MCP 或本地科研工具的研究者。
- 需要把搜索、阅读、实验和写作串成可复现交付的研究团队。
- 需要审计、复核或人工发布批准的高风险科研场景。

## 价值假设

1. 用户可替换能力而不改 Runtime 主流程。
2. 工具输出可转换成统一的研究资产和证据引用。
3. 可信机制变成可独立复用的 Evidence Module，而不是散落在 Agent 中。
4. 一条真实领域切片可以同时证明能力质量和治理质量。

## 非目标

- 不和 Elicit、STORM、PaperQA、Overleaf 等产品在每个单点能力上竞争。
- 不默认把每个模块做成插件。
- 不在 R-001 承诺动态卸载、热更新、远程任意代码执行或分布式调度。
- 不在没有真实消费者前增加通用 bus、scheduler、sandbox 或第二套数据库。

## 复杂度预算

R-001 只新增四个 L2 核心名词：

| 名词 | 真实消费者 | 解决的问题 |
|---|---|---|
| `CapabilityManifest` | Registry / Runtime | 描述 skill、MCP、plugin、native 能力及权限 |
| `CapabilityAdapter` | Paper Search S1 | 隔离外部工具协议，把结果转成 typed result |
| `InvocationReceipt` | Runtime / Evidence | 记录调用、版本、重放和未知结果 |
| `EvidenceCandidate` | Adapter / Domain Service | 让外部结果提交证据候选而非直接写证据真相 |

删除这四个名词会重新把外部工具协议、调用审计和证据写入混回 Application/Agent，因此它们通过 over-design gate。除此之外的 plugin lifecycle、进程隔离和动态加载延后。
