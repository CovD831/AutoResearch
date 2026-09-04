# Task Package Template

## Metadata

```yaml
task_id: TASK-ID
phase: P1
owner_lane: runtime | evidence/domain | integration
status: planned
base_ref: main
branch: codex/task-id
depends_on: []
merge_after: []
next_package: null
```

## Deliverables

- 文件路径和接口变更；
- 测试和 fixture；
- 文档、证据报告和 rollback 说明；
- 不包含的内容。

## Work isolation

- allowed_paths：
- forbidden_paths：
- shared-boundary request：

## Acceptance

- Given / When / Then 场景；
- 必须通过的命令；
- 必须生成的证据；
- 失败时的停止条件。

## Handoff

- changed paths；
- verification results；
- known limitations；
- rollback；
- next owner / next package；
- rebase and integration notes。
