# P1-B2 Task Package: Adversarial Evidence and Rule Fixtures

## Metadata

```yaml
task_id: P1-B2-EVIDENCE-ADVERSARIAL
phase: P1/S1
owner_lane: evidence/domain
status: active
base_ref: main@c1dbefc
branch: codex/p1-evidence-adversarial
depends_on: [P1-B-EVIDENCE-PIPELINE]
merge_after: [P1-B]
next_package: S2-B-AUDIT-EVIDENCE
```

The branch is based on the B1-integrated remote `main` at `c1dbefc`. The B2
changes were restored into a fresh working tree from that base, so no B1 rebase
is pending.

## Goal

Prove that the B1 evidence and Evaluation section pipeline fails closed for
missing locators, invalid or expired evidence, missing concrete baselines,
planned-as-result leakage, and result-like numeric claims.

## Allowed paths

```text
src/autoresearch/evidence.py
src/autoresearch/readiness.py
src/autoresearch/benchmark_advisor.py
src/autoresearch/section_validator.py
src/autoresearch/writing_service.py
tests/test_evidence_adversarial.py
tests/test_fail_closed_rules.py
docs/tasks/P1-B-evidence-lane/tasks/B2-evidence-adversarial/
```

`pipeline_contracts.py` may be changed only if a test-proven B2 contract
cannot be represented by the existing B1 types. No such change is currently
planned.

## Forbidden paths and scope

```text
src/autoresearch/application.py
src/autoresearch/storage.py
src/autoresearch/contracts.py
src/autoresearch/capability.py
src/autoresearch/graph.py
src/autoresearch/agents/
.project-to-act/
.ai-team/TASK.md
```

Do not add agents, stores, buses, schedulers, network calls, Audit/S2
contracts, reader/writer ports, real papers, or observed experiment results.

## Deliverables

- candidate locators are required before EvidenceItem admission;
- invalidated, expired, and malformed-expiry evidence is excluded from valid
  support while remaining traceable;
- concrete benchmark baselines are required for readiness;
- planned benchmark output cannot carry observed results;
- result-like numeric claims are reported as revise unless they remain outside
  the plan-only section;
- adversarial offline tests and task-local verification records;
- rollback and rebase instructions in `HANDOFF.md`.

## Acceptance scenarios

1. Given a candidate with `None`, empty, or whitespace locator, when admission
   runs, then status is `blocked`, no EvidenceItem is written, and the reason
   identifies the locator.
2. Given an invalidated, expired, or malformed-expiry evidence item, when
   readiness resolves support, then the item is excluded; an invalidated item
   remains retrievable for audit tracing.
3. Given no concrete baseline, when readiness runs, then status is `blocked`.
4. Given a plan-only benchmark with an observed summary or a non-plan-only
   flag, when readiness or validation runs, then the result is never
   `verified`.
5. Given an Evaluation draft containing a result-like numeric claim without a
   separately supported result artifact, when validation runs, then the
   verdict is `revise` and the issue names the numeric claim.
6. Given a draft binding an invalid evidence ID, when validation runs, then
   the invalid binding is rejected and cannot produce `verified`.

## Required verification

```text
<project-python> -m pytest tests/test_evidence_adversarial.py tests/test_fail_closed_rules.py tests/test_evidence_admission.py tests/test_evaluation_pipeline.py tests/test_material_readiness.py tests/test_section_validation.py -q
<project-python> -m pytest -W error -q
<project-python> -m ruff check src tests
node .ai-team/check.mjs --json
git diff --check
```

The repository Project-to-Act validation is run when a usable project Python
runtime is available. Its result must be reported accurately; it must not be
represented as passed when the command cannot run.

## Stop conditions

Stop and record a boundary request if B2 requires a shared contract change,
application orchestration change, direct store write, network access, a new
agent/store/bus/scheduler, or a change to blocked-compose semantics.

## Rollback

Revert the B2 commit or remove only the B2 changes in the allowed paths. B1
behavior and the B1 task records must remain intact. Re-run the focused and
full verification after rollback.
