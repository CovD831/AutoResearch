# B3 Handoff

## Status

`tested`; ready for owner scope review and PR preparation. It is not yet
committed, pushed, or integrated.

## Base and branch

- Branch: `codex/s2-audit-evidence`
- Base: `main@dad4658` (`feat(I2): mainline E2E + S1 promotion`)
- S1 promotion is complete, so B3 is not speculative or waiting for a gate.
- Current working tree contains only the B3 source, test, fixture, and
  task-local record changes listed below.

## Changed paths

```text
src/autoresearch/audit.py
tests/test_audit_module.py
tests/fixtures/audit/citations.jsonl
docs/tasks/P1-B-evidence-lane/tasks/B3-audit-evidence/
```

## Implementation summary

- Local versioned resolver and corpus snapshots prevent live network drift.
- Citation existence, publication status, evidence validity, and locator
  checks produce explicit deterministic `pass`, `fail`, or `unknown` results.
- Invalid, expired, or missing evidence is excluded from support but remains
  visible in reconciliation output.
- Unbound claims are reported as `[未验证]`.
- Model-assisted locator verdicts are separated and require confidence 0.8.
- In-runtime candidates go through `EvidenceService.admit_candidate()` only;
  standalone mode has no admission side effect.
- Reports are stored by a content-derived audit key and replay idempotently.

## Verification

- `pytest tests/test_audit_module.py -q`: `16 passed`.
- `pytest -W error -p no:cacheprovider -q`: `97 passed`, exit code 0.
- Plain `pytest -W error -q` reached 100% business-test completion but the
  local pytest cache provider raised a permission warning under `-W error`;
  the cache-disabled rerun is the authoritative clean result.
- `ruff check src tests`: passed.
- `node .ai-team/check.mjs --json`: `valid: true`.
- Project-to-Act `--validate`: `valid: true`, no issues.
- `git diff --check`: passed.

Full command details and scope checks are in `verification-report.json`.

## Review points

1. Confirm only B3 paths changed.
2. Confirm `AuditService` never writes the `evidence` record kind directly.
3. Confirm standalone/in-runtime semantics and duplicate/conflict outcomes.
4. Confirm unknown is preserved for unavailable resolver/full text.
5. Confirm deterministic/model-assisted verdict separation and the 0.8
   threshold.

## Known limits

- No application, CLI, or MCP entrypoint is included by design.
- No live resolver adapter or real corpus is included.
- A future integration task must wire the service without changing the
  Evidence sole-writer boundary.

## Rollback

Remove only the B3 changed paths or revert the eventual B3 commit. Preserve
B1/B2 implementation and records, and rerun the focused/full verification.

## Next owner action

Review the diff, commit the B3 changes, push `codex/s2-audit-evidence`, and
open a PR against `CovD831/AutoResearch:main`. Mark this task `integrated` only
after the PR is merged and the merged commit is verified on main.

## Owner integration record（2026-09-09，D-S2-01）

PR #9 经 owner 深审后未按原头合并：与 S2-A（PR #8）在 `src/autoresearch/audit.py`、
`tests/test_audit_module.py` 与 record kind `audit_report` 上结构性撞车（S2 包拆分缺陷，
非成员实现走样）。按 D-S2-01 裁决由 owner 完成集成调整：

- 模块改名 `src/autoresearch/audit_evidence.py`，测试改名 `tests/test_audit_evidence.py`，
  fixture 移至 `tests/fixtures/audit_evidence/`；A3 运行时保留 canonical `autoresearch.audit`。
- record kind 分家：`audit_report`（A 运行时）vs `audit_evidence_report`（本模块）；
  事件分家：`audit.*` vs `audit_evidence.*`。
- 集成修复：`_claim_matches_text` 空词条/空 claim 由隐式 PASS 改为 UNKNOWN（fail-closed），
  新增测试 `test_vague_claim_locator_is_unknown_not_fail_open`。
- 语义裁决（D-S2-01）：binding/未绑定 claim 沿用本模块严格语义（有效证据绑定才算绑定，
  未绑定报 `[未验证]`+UNKNOWN）；corrected/superseded 关系可追溯即 PASS；A3 运行时的
  对应类别在 S2 promotion 集成窗口对齐（owner follow-up）。
- 合并验证：owner 分支全量 105 passed、ruff clean、check.mjs valid；PR #9 以
  superseded 关闭，集成经 PR #10 合入。
