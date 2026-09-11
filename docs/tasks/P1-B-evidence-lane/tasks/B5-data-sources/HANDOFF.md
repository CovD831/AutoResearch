# B5 Handoff

## Status

`tested`; ready for owner scope review and PR preparation. Not yet committed,
pushed, or integrated.

## Base and branch

- Branch: `codex/s3-b2-data-sources`
- Base: `main@380bd49`
- S3 promotion complete (O7, 2026-09-10); B5 is not speculative.

## Changed paths

```text
src/autoresearch/external_sources.py
tests/test_external_sources.py
tests/fixtures/external_sources/doi_snapshot.json
tests/fixtures/external_sources/crossref_responses.json
docs/tasks/P1-B-evidence-lane/tasks/B5-data-sources/
.ai-team/tasks/S3-B2-DATA-SOURCES.md
```

## Implementation summary

- `CrossrefClient` (httpx, polite pool, injectable transport) + `CrossrefAdapter`
  resolve live DOI verdicts: 404 → deterministic `not_found`; `update-to[]`
  with `type=retraction` → `retracted`; other `update-to` → `corrected`.
- Fallback chain: live → offline `SourceSnapshot` → `unknown`. A
  `TransportOutcome` (ok/rate_limited/timeout/unavailable/partial) records why
  each non-definitive path resolved the way it did.
- `resolver_record()` projects a verdict into B3 resolver-snapshot material
  (status + related_source_ids) and reuses a supplied verdict to avoid a
  second network call.
- `PdfParser` docling-first, pymupdf4llm fallback, both optional imports,
  unavailable → `unknown`; `ParseEgress` admits through
  `EvidenceService.admit_candidate()` only.
- Gold-set metrics align with ScholarQABench: `hallucination_ratio` =
  unresolved/total; `citation_recall`/`citation_precision` computed from a
  supplied NLI "attributable" judgment, `None` + note when absent.

## Verification

- Focused: `python -m pytest tests/test_external_sources.py -q` → `11 passed`.
- Full: `python -m pytest -q -p no:cacheprovider` → green (see member ledger).
- Lint/format: `ruff check` + `ruff format --check` on B5 files → clean.
- Real smoke: live Crossref returned `found` for
  `10.1038/s41586-025-10072-4` and `retracted` (+ `update-to[]`) for
  `10.1016/S0140-6736(10)60175-4`.
- Repository check: `node .ai-team/check.mjs --base 380bd49 --json` → valid.
- Governance: Project-to-Act `--check` → configured/managed.

## Review points

1. Confirm only B5 allowed paths changed.
2. Confirm live Crossref is polite-pool only; no paid tier, no key required.
3. Confirm retraction/correction flows through B3 resolver material, not a
   second verification path, and never writes evidence directly.
4. Confirm `hallucination_ratio` uses the unresolved/total definition and that
   recall/precision require the NLI judge (no fabricated attribution).
5. Confirm docling-first selection and AGPL fallback recording match ADR-01.

## Known limits

- `citation_recall`/`citation_precision` need the external NLI judge; this layer
  only consumes supplied judgments.
- docling weights not downloaded; shared A7 offline pre-provisioning pending.
- Live calls are polite-pool; real rate-limit handling policy recorded in the
  transport matrix, no paid tier used.

## Rollback

Remove only the B5 changed paths or revert the eventual B5 commit. Preserve
B1–B4 implementation; rerun focused/full verification.

## Next owner action

Review the diff, commit, push `codex/s3-b2-data-sources`, open a PR against
`CovD831/AutoResearch:main`. Mark `integrated` only after merge and verification.