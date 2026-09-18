# R006-P0 基线测量资产（已归档）

> **本目录的代码不参与生产链路。** 它是一次**已放弃的对照实验**的留存资产。

## 这是什么

`experiments/r006-p0/experience_injection.py`（649 行）是 R006-P0 为回答一个问题而写的**唯一** drafting 侧代码：

> **「把历史经验注入起草步骤，会让论文产出更好吗？」**

它**刻意保持在 runtime（`benchmark.py`）与经验存储（`evolution_service.py` / `contracts.py`）之下**：
合成 `ExperienceRecord`，并提供两个**唯一差别**是有无经验文本的 `BenchmarkAgent` 实现
（`NoExperienceAgent` vs `ExperienceInjectingAgent`）。

它**不是**生产写作链路的模块。生产侧的「经验回流」是另一条 lane 的事
（参见 R008 `04-l2-contracts.md` F1）——**不要把这个模块当成那个功能的实现**。

## 为什么归档而不是删除：负向结果本身是知识

**结论：对照实验路线已放弃。** 完整记录见
`docs/rearchitecture/R006-knowledge-experience/tasks/P0-baseline-measurement/`（DESIGN / HANDOFF / REVIEW）。

**owner 原话**（2026-09-15）：

> 「质量提升**需要一个外部的标准去评判**，要不然无法判断是否提升了质量。」

原设计的阶梯里**没有**「证明经验有用」这一步 —— 它靠的是工程机制
（「每次晋级或降级都必须有回归集、证据 ID、审核结论、版本和回滚点」；
「模型只能提交 diff 提案，不能直接生效」）。
**用「跑一次对照实验证明效用」替代这套机制，是研究方法，不是工程机制；而在外部标准不存在时，自造指标测效用本质上是无判据的。**

### 四次错配（实测）

| 次 | 错配 | 证据 |
|---|---|---|
| 1 | agent 完全不调 LLM | 四条件指标完全相同 |
| 2 | 主指标 `hallucination_ratio` 与「草稿质量」无关 | 实测条件间均为 1.0 |
| 3 | 自造机械指标受跑间噪声支配 | `temperature=0` 实测 **5/5 输出不同**，长度波动 ±13% |
| 4 | 任务本身没有改进空间 | prompt 已把语料参考草稿整个喂给模型；「结构完整度」实测是在拿标题存在性评格式 |

叠加方法学结论：**24 case 严重欠功效**（检出 2–5pp 需 200–400 样本/组）。

### 仍有效的成果

| 成果 | 价值 |
|---|---|
| 机制验证 | 经验能到达 prompt、能改变产出 —— 真实 LLM 端到端冒烟通过 ✅ |
| **等长对照** | `experiments/.../EXPERIENCE_PLACEHOLDER` 与经验文本长度比 **1.05** ✅ |
| `benchmark.py` 的 `condition_agents` | 按条件分派 agent —— **通用能力**，非 P0 专用（已随本归档进入 `src/`） |

**为什么等长对照值得记**：注入经验必然让 prompt 变长，而 prompt 长度本身就会改变 LLM 输出。
拿「有经验」对比「无经验」会把**两个变量混在一起**。这个 placeholder 条件专门隔离「内容」变量——
这是本次实验里做对的一件事。

## 怎么跑

```bash
cd <repo root>
PYTHONPATH=src:experiments/r006-p0 python scripts/p0_smoke.py            # 三条件冒烟（需 LLM/网络）
PYTHONPATH=src:experiments/r006-p0 python scripts/p0_discriminating_power.py  # 判别力自检
```

## 维护约束

- **无人调用它**：它不在 `src/autoresearch/` 内，因此**不计入生产可达性门禁**，也不会被当成孤岛。
- **不要把它接进生产链路**：它回答的是一个评估问题，不是运行时需求。
- 若将来要重做对照实验，**先读 `P0-baseline-measurement/REVIEW.md` 的四次错配**，
  并解决欠功效问题（200–400 样本/组）——否则会重犯同样四个错误。
