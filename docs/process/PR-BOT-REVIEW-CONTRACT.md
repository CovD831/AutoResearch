# AutoResearch PR 机器人审核合同

## 目的

机器人负责可重复、可机械验证的 PR 预审；项目负责人负责最终代码、架构、证据和合并决定。成员不承担交叉审核职责。

## PR 必须提供的输入

- Task ID 和 lane；
- base ref、branch/worktree；
- changed paths；
- 交付物清单；
- 验收场景；
- 测试/静态检查命令及结果；
- evidence/report 路径；
- rollback 方式；
- 是否修改共享合同、架构或项目账本；
- 下一任务及其依赖。

## 机器人必须检查

### 确定性检查

- 格式、Lint、类型检查、构建和测试；
- 任务账本结构和状态；
- allowed/forbidden paths；
- 必填交付物、L3、PROGRESS、HANDOFF；
- secrets、临时数据库、无关生成物；
- 任务包 JSON 与 PR 输入一致；
- 分支是否基于正确 base ref。

### 风险提示

- 新增异常路径是否缺测试；
- timeout、pending、unknown、replay 和副作用是否有覆盖；
- 是否疑似扩大任务范围；
- 是否存在未解释的公共合同变化；
- 文档、测试和代码是否明显矛盾。

## 机器人不能替代的判断

- 是否符合 R004/R005 和用户已确认路线；
- 是否真的实现产品目标；
- Evidence/Policy 的唯一写入者是否成立；
- 实验、论文 claim 或 benchmark 结果是否可信；
- 是否通过 Promotion Gate 或 MVP Gate；
- 是否接受架构例外或 speculative 代码。

## 输出状态

机器人输出应为：

```text
PASS
FAIL
NEEDS-HUMAN-REVIEW
BLOCKED
```

机器人 `PASS` 只表示自动检查通过，不代表 PR 可以合并。只有项目负责人完成最终审查并满足 Merge Gate，PR 才能合并。

## 合并后

负责人合并后调用 `autoresearch-doc-maintenance`，根据 merged commit、测试、机器人报告和 HANDOFF 更新任务账本、注册表及必要的 Project-to-Act 文件。
