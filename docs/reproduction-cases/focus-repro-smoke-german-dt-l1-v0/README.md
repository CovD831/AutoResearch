# FOCUS reproduction smoke case

状态：`candidate`，尚未 `package_ready`。

这是一个不包含上游论文正文、代码仓库副本、数据文件或模型二进制的输入包骨架。它只记录经过核对的输入契约、来源和待完成的材料审计，避免把外部材料未经许可复制进项目。

## Upstream

- Original paper: AAAI 2022, “FOCUS: Flexible Optimizable Counterfactual Explanations for Tree Ensembles”.
- Reproduction repository: `kyosek/focus-reproducibility`.
- Repository ref: `master` 仅作定位；进入 `package_ready` 前必须替换为固定 commit。

## Smoke scope

```text
dataset: cf_german_test / cf_german_train
model: dt
distance: l1
num_iter: 1000
seed: unknown (upstream CLI does not expose one)
```

## Files

- `case.yaml`：输入、参数、输出和状态；
- `expected_schema.json`：gold schema 草案，不包含伪造数值；
- `run_commands/README.md`：已核对的命令和前置条件。

## Package-ready blockers

1. 固定 upstream commit；
2. 核对原论文、复现论文、代码和数据许可；
3. 确认依赖在隔离环境中可安装；
4. 确认 retrained model pickle 可读取；
5. 运行一次 smoke，并记录真实 stdout/stderr/exit code；
6. 从原论文主表提取 table/figure IDs、指标、数值和容差；
7. 决定 seed unknown 的处理方式。

