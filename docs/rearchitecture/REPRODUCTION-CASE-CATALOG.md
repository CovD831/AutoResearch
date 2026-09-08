# Case 册（v0.1）

> 目的：管理用于默认管线、论文生成和差异评测的 reproduction package。

## 1. Case 状态

```text
candidate → material_audit → package_ready → smoke_running
→ baseline_verified → benchmark_ready → accepted
```

## 2. Case 最小结构

```text
case.yaml
original_paper.pdf
paper_metadata.json
research_question.json
source_manifest.json
code/
data_manifest.json
environment/
run_commands/
original_results/
expected_schema/
allowed_references/
```

## 3. Gold 与生成输入

- generation input：代码、数据、配置、运行命令、结果 artifact 和允许的参考资料；
- evaluator gold：原论文正文、expected sections、research objects、procedure fields、claims、results、limitations；
- 原论文正文默认不直接提供给生成 Writer，避免把 reproduction 变成原文改写；
- 如果提供原文，必须标记为 `reference-conditioned` track。

## 4. 首轮候选

| 排序 | Case | 结论 |
|---:|---|---|
| 1 | [Re] FOCUS: Flexible Optimizable Counterfactual Explanations for Tree Ensembles | 首选 smoke case；材料和命令较完整，先跑单数据集/单模型/固定 seed |
| 2 | [Re] Towards Understanding Grokking | toy/MNIST 输出清楚，但训练和随机性风险较高 |
| 3 | [Re] Badder Seeds | 环境和 notebook 较完整，需锁定外部模型资源 |
| 4 | [Re] Pure Noise to the Rescue of Insufficient Data | 表格映射清楚，但 GPU 和外部模型成本较高 |

候选来源优先使用 ML Reproducibility Challenge、ReScience ML、OpenReview/arXiv artifact 和公开代码仓库。

## 5. Case 验收

- 所有输入材料有来源、许可和版本记录；
- 至少一个 smoke subset 可运行；
- 原始结果能抽取为 expected schema；
- 失败、偏差、unknown 和缺失材料可单独记录；
- 生成论文可以产出结构、过程、结果和 evidence 差异报告；
- 同一 case 可重复运行，且不依赖隐式 provider fallback。

## 6. FOCUS smoke case（材料审计草案）

### 6.1 来源与可提取材料

首选来源为公开复现仓库 `kyosek/focus-reproducibility`（master；正式冻结前记录具体 commit）。仓库 README 将其定义为 AAAI 2022 FOCUS 论文的 re-implemented codebase，并提供 Python 3.7、安装命令、参数说明、训练/运行/测试命令；目录中有 `data/`、`models/`、`retrained_models/`、`src/` 和 `tests/`。数据目录明确包含 `cf_german_test.tsv`、`cf_german_train.tsv`、`cf_heloc_*`、`cf_compas_num_*`、`cf_shop2_*` 和 `cf_wine_*`。citeturn0view0turn1view0turn1view1

`src/main.py` 的实际实现读取 `data/{data_name}.tsv` 和 `data/{data_name.replace("test", "train")}.tsv`，加载 `retrained_models/{model_type}_{train_name}.pkl`，运行 counterfactual generation，并写入 `results/{distance_function}/{data_name}/{model_type}/...`；同时写出 `*_cf_stats.txt` 和 `cfe_{model_type}_{train_name}.csv`。统计字段由 `evaluate.py` 明确给出：`dataset`、`distance_function`、`unchanged_ever`、`mean_dist`、`time (min)`。citeturn2view0turn2view1

### 6.2 Smoke 范围

```text
dataset: cf_german_test + cf_german_train
model_type: dt
distance_function: l1
num_iter: 1000
sigma: 10.0
temperature: 1.0
distance_weight: 0.01
lr: 0.001
opt: adam
seed: not exposed by upstream CLI; record as unknown unless wrapper fixes it
```

该范围只验证默认管线的输入读取、受控执行、结果 artifact、evidence/receipt 和复现报告生成，不宣称覆盖原论文全部实验。

### 6.3 `case.yaml` 草案

```yaml
case_id: focus-repro-smoke-german-dt-l1-v0
status: candidate
track: reproduction_generation
upstream:
  paper_title: "FOCUS: Flexible Optimizable Counterfactual Explanations for Tree Ensembles"
  venue_year: AAAI-2022
  reproduction_repository: https://github.com/kyosek/focus-reproducibility
  repository_ref: master  # replace with pinned commit before package_ready
  license: unknown_pending_audit
inputs:
  paper_gold: original_paper.pdf
  data:
    test: data/cf_german_test.tsv
    train: data/cf_german_train.tsv
  model: retrained_models/dt_cf_german_train.pkl
  environment: environment/requirements.txt
  run_command: run_commands/focus-smoke.sh
  allowed_references: allowed_references/
parameters:
  model_type: dt
  num_iter: 1000
  sigma: 10.0
  temperature: 1.0
  distance_weight: 0.01
  lr: 0.001
  opt: adam
  data_name: cf_german_test
  distance_function: l1
outputs:
  result_dir: results/l1/cf_german_test/dt/
  stats_glob: results/**/*_cf_stats.txt
  cfe_glob: cfe_dt_cf_german_train.csv
  run_manifest: artifacts/run_manifest.json
  expected_schema: expected_schema/focus-smoke.json
known_risks:
  - upstream README shows key=value examples, while src/main.py declares positional argparse arguments; wrapper must use verified positional form
  - upstream parser does not expose a random seed; reproducibility must record seed state or mark unknown
  - Python 3.7 and pinned legacy dependencies (including tensorflow==2.11.0) may require an isolated environment
  - model pickle compatibility and path conventions must be checked before execution
```

### 6.4 经过代码核对的运行命令

README 给出的示例使用 `model_type=dt ...` 形式，但 `src/main.py` 当前用的是无 `--` 的 positional `argparse` 参数。因此 smoke wrapper 在不修改上游代码的前提下，应先采用下面的实际 positional 形式，并把 README 形式记录为待核对风险：

```bash
python src/main.py dt 1000 10.0 1.0 0.01 0.001 adam cf_german_test l1
```

运行前置条件：工作目录为上游仓库根目录；`data/cf_german_{test,train}.tsv` 存在；`retrained_models/dt_cf_german_train.pkl` 存在；依赖按上游 `requirements.txt` 安装。依赖版本当前包括 `matplotlib==3.5.3`、`numpy==1.21.6`、`optuna==3.0.5`、`pandas==1.3.5`、`pytest==7.2.0`、`scikit-learn==1.0.2`、`seaborn==0.12.1` 和 `tensorflow==2.11.0`。citeturn3view0turn2view1

### 6.5 `expected_schema/focus-smoke.json` 草案

```json
{
  "case_id": "focus-repro-smoke-german-dt-l1-v0",
  "research_object": {
    "task": "counterfactual explanation generation for tree ensembles",
    "dataset": "cf_german_test",
    "train_dataset": "cf_german_train",
    "model_type": "dt",
    "method": "FOCUS",
    "distance_function": "l1"
  },
  "procedure": {
    "num_iter": 1000,
    "sigma": 10.0,
    "temperature": 1.0,
    "distance_weight": 0.01,
    "lr": 0.001,
    "optimizer": "adam",
    "seed": {"value": null, "status": "unknown"}
  },
  "required_artifacts": [
    "stats_json_or_txt",
    "counterfactual_distance_csv",
    "run_manifest",
    "stdout_stderr_log",
    "environment_record"
  ],
  "observed_fields": [
    "dataset",
    "distance_function",
    "unchanged_ever",
    "mean_dist",
    "time_min"
  ],
  "comparison_targets": [
    "original_result_table_refs",
    "reproduction_result_table_refs",
    "numeric_difference",
    "direction_consistency",
    "unsupported_or_missing_claims"
  ],
  "not_yet_frozen": [
    "original paper table/figure IDs",
    "gold numeric tolerances",
    "license and commit pin",
    "seed policy"
  ]
}
```

### 6.6 进入 `package_ready` 前的阻塞检查

1. 固定仓库 commit，并核对上游论文 PDF、复现论文/报告和许可。
2. 确认 README 命令与 `src/main.py` positional parser 的差异；以可执行 wrapper 为准，不改写上游结果。
3. 确认 `dt_cf_german_train.pkl` 是否存在且可被当前 Python/sklearn 读取。
4. 运行一次 dry-run/smoke，记录 wall time、stdout/stderr、退出码和所有实际输出路径。
5. 从原论文主结果表抽取 gold 的表/图 ID、指标、数值、方向和允许误差；在此之前 expected schema 只能标记为 draft。
6. 明确随机性策略：若上游没有 seed 参数，则把 seed 不可控作为 reproduction limitation，而不是伪造确定性。

### 6.7 当前输入包骨架

已建立不含外部论文正文、代码副本、数据文件或模型二进制的候选输入包：

`docs/reproduction-cases/focus-repro-smoke-german-dt-l1-v0/`

其中的 `case.yaml`、`expected_schema.json` 和 `run_commands/README.md` 只记录已核对的契约、路径和待办，不包含未经许可复制的外部材料或伪造结果。输入包当前状态仍为 `candidate`。
