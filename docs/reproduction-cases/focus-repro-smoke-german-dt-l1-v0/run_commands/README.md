# FOCUS smoke command

工作目录必须是 `kyosek/focus-reproducibility` 仓库根目录，且已经安装其隔离环境和 requirements。

```bash
python src/main.py dt 1000 10.0 1.0 0.01 0.001 adam cf_german_test l1
```

该命令来自 `src/main.py` 的 positional argparse 定义。README 中的 `key=value` 示例不能直接作为已验证命令使用。

预期输入路径：

```text
data/cf_german_test.tsv
data/cf_german_train.tsv
retrained_models/dt_cf_german_train.pkl
```

预期输出：

```text
results/l1/cf_german_test/dt/...
cfe_dt_cf_german_train.csv
```

运行前必须由 runner 记录：command、environment、stdout、stderr、exit code、wall time、seed 状态和实际输出文件列表。

