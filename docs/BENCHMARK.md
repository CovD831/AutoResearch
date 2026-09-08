# AutoResearch 统一 Benchmark（v0.1）

## 定位

`GateService` 的 `score` 是一次动作的证据充分性分数，不等于论文质量，也不适合直接比较两个版本。统一 benchmark 通过固定任务集、固定 rubric 和版本化报告来支持回归比较。

首版报告分成两个 family：

| Family | 评测问题 | 推荐指标 |
| --- | --- | --- |
| `paper` | 生成的 Evaluation 章节是否可信、完整、可复现 | claim–evidence 一致性、引用可定位率、结果/数值绑定率、baseline 覆盖、复现成功率、限制披露完整度 |
| `mechanism` | AutoResearch 的机制是否按设计工作 | fail-closed 阻断率、false-pass 率、证据 provenance 完整度、audit 完整度、replay/idempotency 成功率、recovery 成功率 |

代码入口是 `autoresearch.benchmark.BenchmarkHarness`。它只消费观测值并计算分数，不执行实验、不写 Store；因此可以在离线 fixture、真实运行和外部人工标注集上复用。

## 评分规则

- 每个指标为 0–100，带正权重；family 分数和总分均为加权平均。
- `observed` 才进入分数；`planned` 和 `unavailable` 会计数并写入 warning，不能伪装成结果。
- 总分不应替代 peer review。建议论文同时报告两个 family、每个 case、样本数和置信区间。
- 机制指标优先使用对抗 fixture（无证据数字、失效证据、越级 Gate、重复执行、恢复中断），并报告 false-pass，而不是只报告平均分。

## 建议的最小对比矩阵

同一任务集运行四个条件：

1. bare LLM；
2. AutoResearch，Gate 关闭；
3. AutoResearch，Gate 开启；
4. AutoResearch，Gate 开启 + recovery/replay。

每个条件都固定模型、prompt、材料、预算和随机种子；只改变待研究的机制变量。论文应同时公布任务 fixture、标注协议、版本化 rubric、原始逐 case 结果和重跑命令。

## 与成熟论文评测体系的对齐

设计借鉴 NeurIPS checklist 对 reproducibility、transparency、ethics 和 societal impact 的关注，以及 ACM artifact review 对 artifact 可用、可运行、可复用和结果复现的分层思路。它们应作为论文层的 checklist/badge 证据，而不是被压成一个不可解释的总分。

