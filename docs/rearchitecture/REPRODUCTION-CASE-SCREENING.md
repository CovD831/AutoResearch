# 首个 Reproduction Case 筛选计划（v0.1）

## 目标

选择一篇公开、低成本、可重跑的实证论文，构造成 AutoResearch 的第一个 reproduction package。它用于验证输入输出 contract、默认能力、论文生成和结构化差异报告，不用于证明系统在所有学科都有效。

## 必须满足

- 公开论文和许可清楚；
- 公开代码或明确可执行实现；
- 数据集公开或可通过稳定 manifest 获取；
- 一个主任务、一个主方法、2–4 个 baseline、2–4 个指标；
- 至少一张主结果表和一个可重复的消融或对照；
- CPU 或单张消费级 GPU 可在可接受时间内运行；
- 不依赖私有 API、付费墙、个人数据或人工受试者；
- 原论文结果可以被抽取成结构化 expected schema；
- 运行失败、结果偏差和环境差异可以被明确记录。

## 推荐论文形态

优先选择标准机器学习/自然语言处理任务上的实证系统论文，而不是理论论文、综述、大模型预训练论文或复杂人类研究。

首个 case 的最小形态：

```text
1 dataset
1 main task
1 main method
2–4 baselines
2–4 metrics
1 main result table
1 ablation / control
1 reproducible command
```

## 候选来源与当前建议

- OpenReview、arXiv 和公开 GitHub artifact repository：便于同时获取论文、代码和版本信息；
- ML reproducibility / artifact evaluation 类项目：优先选择已经有人验证过可运行的 case；
- Benchopt 类 benchmark repository：适合提取统一的 command、dataset、metric 和 result schema。

当前首轮候选可从 ML Reproducibility Challenge / ReScience ML 复现条目中筛选。初步排序如下：

1. **[Re] FOCUS: Flexible Optimizable Counterfactual Explanations for Tree Ensembles**：仓库包含 data、models、retrained_models、src、tests，README 有 Python 版本、参数、训练/复现命令和 results 输出；最适合作为首个 smoke case。需要先验证旧 TensorFlow 依赖和运行时间。
2. **[Re] Towards Understanding Grokking**：toy model 和 MNIST 两套实验，命令和 CSV 输出清楚，输入/输出容易结构化；但训练时间和随机性风险更高。
3. **[Re] Badder Seeds**：环境文件、数据说明、配置、notebook 和结果路径完整，CPU 成本较低；但语言模型版本和外部资源需要锁定。
4. **[Re] Pure Noise to the Rescue of Insufficient Data**：复现脚本和表格映射清楚；GPU 成本和外部模型下载风险较高。

首选建议：先对 FOCUS 做 smoke subset（1 dataset × 1 model × 固定 seed），确认输入包、运行命令和结果表能完整抽取，再决定是否扩展完整实验。

每个候选都要先执行：材料可得性、运行成本、结果表可解析性、许可、复现风险和输入字段覆盖检查；候选名称在完整 package 审核前不视为冻结。

## 评估 gold

原论文正文主要作为 evaluator gold。生成阶段使用 reproduction package；评估阶段额外读取：

- expected sections；
- expected research objects；
- expected procedure fields；
- expected claims；
- expected result tables；
- expected limitations；
- original run metadata。
