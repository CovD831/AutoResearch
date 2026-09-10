# B4 Handoff

## Status

`handed-off` → **owner-integrated** (2026-09-10). Member handoff was reviewed
by the owner; the integration branch carries the member commit rebased onto
`main@b7fc3b7` plus owner fixes (orphan map-key gate check + adversarial test,
`adap_version` → `adapter_version`, consumer notes in L3). Original PR #13 is
superseded by the owner integration PR.

## Base and branch

- Integration branch: `owner/s3-b-integration` (member commit `55bda47`
  rebased onto `main@b7fc3b7`; member base was `main@437e15e`, 3 commits
  behind, which was why CI Task contract reported "not an ancestor").
- S2 promotion is complete (O6, 2026-09-10), so B4 is not speculative or
  waiting for a gate.

## Changed paths

```text
src/autoresearch/reader_writer_ports.py
tests/test_reader_writer_ports.py
docs/tasks/P1-B-evidence-lane/tasks/B4-reader-writer-ports/
.ai-team/tasks/S3-B-READER-WRITER-PORTS.md
```

## Implementation summary

- Typed `ReaderRequest`/`ReaderResult`, `WriterRequest`/`WriterResult`,
  `ReaderPort`/`WriterPort` protocols, and `AdapterKind` identity.
- `NativeReaderAdapter`/`NativeWriterAdapter` are the deterministic oracle and
  fallback; `StructuredReaderAdapter`/`StructuredWriterAdapter` wrap
  already-normalised LLM/external payloads without I/O.
- `bind_claims` enforces 100% evidence binding; `gate_compliance` fails closed
  on observed-result leakage, silently-unbound claims, and invisible lineage.
- `compare_writer_parity` reports contract-level parity (schema, binding,
  gate compliance, planned-only) across native/llm/external outputs; it never
  compares surface text.
- No adapter writes evidence records; reading output always carries an
  `EvidenceCandidate` for admission.

## Verification

- Focused: `python -m pytest tests/test_reader_writer_ports.py -q` → `8 passed`.
- Full: `python -m pytest -q -p no:cacheprovider` → `116 passed` (108 baseline + 8 new).
- Lint/format: `ruff check` and `ruff format --check` on the two B4 files → clean.
- Repository check: `node .ai-team/check.mjs --base 437e15e --json` → `valid: true`,
  8 changed files all within B4 allowed paths.
- Governance: Project-to-Act `--check` → configured/managed, no missing templates.
- Environment note: Python 3.13.9 with repo-local `var/_b4_deps` temp dependency
  directory (gitignored). Full-suite `-W error` collection is disturbed by a
  temporary click DeprecationWarning, so the clean `116 passed` uses
  `-p no:cacheprovider`; the 3 `ruff check src tests` UP038 findings are in
  pre-existing B3 (`audit_evidence.py`) and A-lane (`capability.py`) files, not
  B4.

## Review points

1. Confirm only the B4 allowed paths changed.
2. Confirm no adapter writes `evidence` records directly (sole-writer boundary).
3. Confirm non-native output stays a candidate until admission.
4. Confirm parity is contract-level, never text equivalence.
5. Confirm planned-only drafts reject observed results.

## Known limits

- No live LLM, MCP, or external provider wiring; the structured adapters wrap
  supplied payloads only. That integration is O12 ProviderLane / A4 scope.
- No application, CLI, or MCP entrypoint is added by design.

## Rollback

Remove only the B4 changed paths or revert the eventual B4 commit. Preserve
B1/B2/B3 implementation and records, and rerun the focused/full verification.

## Next owner action

Review the diff, commit the B4 changes, push `codex/s3-reader-writer-ports`, and
open a PR against `CovD831/AutoResearch:main`. Mark this task `integrated` only
after the PR is merged and the merged commit is verified on main.