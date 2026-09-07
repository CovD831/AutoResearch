# A1 实例反证验收

这个工具用于独立验收 `P1-A Runtime / Recovery`，不把“pytest 通过”直接当成结论。

## 运行位置

必须在：

```text
F:\AutoResearch\.worktrees\p1-runtime-recovery
```

运行：

```powershell
& "C:\Users\94461\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" `
  docs\rearchitecture\worktrees\A-runtime-recovery\a1_real_acceptance.py
```

## 判定规则

每个模块必须满足三步：

1. 原始代码下目标测试通过；
2. 临时破坏该模块后，目标测试失败；
3. 自动还原后，目标测试再次通过。

只有三步都成立，模块才算验收有效。

脚本会在临时目录生成测试数据库和临时测试文件，结束时自动删除。它拒绝在三个正式生产文件已有未保存改动时运行，避免破坏用户工作。

## 覆盖范围

M1–M14 共 17 个反证项，覆盖：

- fingerprint 和 seed 内容冲突；
- reserve、阶段迁移和 pending；
- exact replay 和跨 Store 重启 replay；
- completed_empty、unknown_outcome、timeout、provider failure；
- staged result recovery、显式 fail、非法 recovery；
- legacy/target parity；
- audit event 和幂等行可见性。

最后还会重新运行整组 A1 测试和 parity report。预期最后一行类似：

```text
SUMMARY {"baseline_passed": true, "final_passed": true, "mutation_count": 17, "mutation_failures_as_expected": 17, "parity_passed": true, "restores_passed": 17}
```

反证阶段出现测试失败是预期行为；真正的失败是“破坏后仍通过”或“还原后不通过”。
