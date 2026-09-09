# S2-B Task Package: Audit Evidence

## Metadata

```yaml
task_id: S2-B-AUDIT-EVIDENCE
phase: S2
owner_lane: evidence/domain
status: tested
base_ref: main@dad4658
branch: codex/s2-audit-evidence
depends_on: [P1-B2-EVIDENCE-ADVERSARIAL, S1-promotion]
next_package: S3-READER-WRITER-PORTS
```

S1 promotion is proven by the current mainline commit `dad4658`. This package
contains the B3 implementation on that base; it is not integrated until its
PR is reviewed and merged.

## Goal

Implement the Evidence-domain Audit Module described by R004 L2. The module
must audit a bounded manuscript/claim view using versioned local snapshots,
produce traceable verdicts and an AuditReport artifact, and optionally return
EvidenceCandidate objects for the existing Evidence admission boundary.

## Allowed paths

```text
src/autoresearch/audit.py
tests/test_audit_module.py
tests/fixtures/audit/citations.jsonl
docs/tasks/P1-B-evidence-lane/tasks/B3-audit-evidence/
```

Existing `EvidenceService`, `RecordStore`, and shared models may be consumed;
their source files are not changed by B3.

## Forbidden paths and scope

```text
src/autoresearch/application.py
src/autoresearch/contracts.py
src/autoresearch/storage.py
src/autoresearch/capability.py
src/autoresearch/gates.py
src/autoresearch/cli.py
src/autoresearch/api.py
src/autoresearch/reader_service.py
src/autoresearch/writing_service.py
.project-to-act/
.ai-team/TASK.md
```

Do not add network calls, live resolver behavior, real-paper retrieval,
observed experiment results, direct Gate integration, a second store, a bus,
a scheduler, an Agent, or reader/writer ports.

## Frozen behavior

- Citation existence and publication status use only the supplied local
  resolver snapshot. Missing or unavailable resolver data is fail-closed:
  unavailable data is `unknown`, while a known missing citation is `fail`.
- Retracted/withdrawn evidence is `fail`. Corrected, superseded, or versioned
  sources remain `pass` only when their related source IDs are traceable.
- Locator comparison is `unknown` when local full text is unavailable, and
  `fail` when a known locator is missing or its text does not support the
  claim.
- Claims without valid evidence bindings are reported as `[未验证]` and get
  an `unknown` unbound-claim verdict.
- Deterministic and model-assisted verdicts are stored in separate report
  lists. Model-assisted locator output below the frozen 0.8 confidence
  threshold is `unknown`.
- `standalone` returns a report without admission. `in-runtime` converts only
  passing, traceable citation conclusions to `EvidenceCandidate`, then calls
  `EvidenceService.admit_candidate()`; it never writes `EvidenceItem`.
- The audit identity includes the canonical input, corpus version, resolver
  snapshot version, and mode. A repeated identity returns the same report;
  changing a snapshot version creates a distinct report.

## Acceptance matrix

1. Existing citation: deterministic existence `pass`.
2. Missing/fabricated citation: deterministic existence `fail`.
3. Retracted source: deterministic publication-status `fail`.
4. Corrected source: relation remains traceable.
5. Resolver unavailable: existence/status `unknown`, never fail-open.
6. Missing local full text: locator `unknown`; mismatch: locator `fail`.
7. Unbound claim: `[未验证]` plus `unknown`.
8. In-runtime candidate: admission occurs through EvidenceService only.
9. Duplicate/conflict admission outcomes remain visible.
10. Standalone mode has no evidence admission side effect.
11. Same input/snapshot versions are idempotent; changed version is distinct.
12. Deterministic and model-assisted methods remain separate.

## Verification and rollback

The exact commands and results are recorded in `verification-report.json`.
Rollback removes only the B3 source, test, fixture, and task-local records;
the B1/B2 behavior and shared project records remain untouched.
