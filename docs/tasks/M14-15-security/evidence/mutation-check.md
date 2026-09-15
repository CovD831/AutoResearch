# L-09 M14 判别力实测（变异注入）

生成脚本：`docs/tasks/M14-15-security/evidence/mutation_check.py`（可重跑，自带还原）

| 变异 | 目标不变量 | 命中测试 | 变异前 | 变异后 | 失败类型 |
|---|---|---|---|---|---|
| M1 | K11-1 默认拒绝（无策略 = 不可读） | test_no_policy_defaults_to_denied | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M2 | K11-2 越权可观测（不得静默返回空列表） | test_readable_resources_raises_for_an_unknown_subject_not_empty_list | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M3 | K11-3 export/delete 需更高门槛（授权时） | test_elevated_grant_without_justification_is_rejected | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M4 | K11-3 授权时复检 justification | test_elevation_added_after_the_grant_is_denied | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M5 | N-2 / K13-1 未测 = None（绝不用 0 顶替） | test_unmeasured_scan_keeps_none_not_zero | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M6 | K12(2) 导出/删除必须留因 | test_egress_without_a_reason_is_refused | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M7 | K12(2)/D-L09-06 未分类资源不得导出 | test_egress_of_an_unlabelled_resource_is_refused | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M8 | M14-05 unknown 不得当作 open | test_unknown_term_is_refused_and_never_treated_as_open | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M9 | N-5 绕过付费墙必须被拒 | test_paywalled_without_entitlement_is_refused | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M10 | K11-3 justification 是**逐动作**的（导出≠删除） | test_a_justification_covers_only_the_action_it_was_written_for | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M11 | K13-1 value 的默认值必须是 None（不能默认成 0） | test_a_point_cannot_default_its_way_into_a_zero | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M12 | K13-2 / N-3 未命中价目 -> value=None（不用 0.0 顶替） | test_unpriced_cost_is_none_never_zero | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M13 | K13-3 字段白名单（未列入的 key 一律拒绝） | test_non_whitelisted_dimension_key_is_refused | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M14 | K13-3 / N-4 secret 模式扫描 | test_secret_shaped_dimension_values_are_refused[sk-abcdefghijklmnop] | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M15 | K13-3 / N-4 全文（超长）不得入维度 | test_full_text_is_refused_by_length | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M16 | K13-4 未测时阈值判定必须是 None（不是 False） | test_threshold_with_an_unmeasured_value_is_a_gap_not_a_pass | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |
| M17 | K13-4 未测告警必须可见（不得静默丢弃） | test_threshold_with_an_unmeasured_value_is_a_gap_not_a_pass | PASS | FAIL | 判据型（AssertionError / DID NOT RAISE / 异常不匹配） |

结论：17 个变异点全部「变异前绿 / 变异后红」，且失败类型均为**判据型**（无一条是符号缺失或导入错误）。

> 方法说明：本包是全新文件，`main@8dd8780` 上跑新测试只会 `ModuleNotFoundError`（符号缺失型，不计判别力）；故反事实基线由变异注入建立。
