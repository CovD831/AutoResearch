# B5 Progress

| Date | State | Change | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-11 | ready | O7 S3 promotion passed; B4 accepted; B5 unblocked on `main@380bd49` | TASK-SPECS B5; registry S3-B2; `4e63022` | Implement real data sources + parsing |
| 2026-09-11 | implemented | First slice: offline snapshot verdict/search/parse + candidate egress | `external_sources.py` | Re-do against live-network + real-DOI + standard-metric requirements |
| 2026-09-11 | implemented | Rewrote to live Crossref (httpx) first + snapshot fallback + transport matrix (rate-limit/timeout/partial/404) + gold-set metrics (ScholarQABench hallucination ratio / citation recall / precision) | `external_sources.py`; `crossref_responses.json`; `doi_snapshot.json` | Run focused + full verification |
| 2026-09-11 | tested | Focused `11 passed`; real Crossref smoke (WRONG expectation, see next row) | `tests/test_external_sources.py`; live smoke output | Owner review |
| 2026-09-11 | **reviewed — blocking defect found** | Owner deep review: the retraction predicate read `update-to[]`, which inverts the direction — the retracted article resolved `found` while the notice resolved `retracted`. Reproduced against the live API and documented in `reviews/PR16-B5-deep-review.md`. | `reviews/PR16-B5-deep-review.md` | Owner integration fix |
| 2026-09-11 | **fixed (owner)** | Predicate now reads `updated-by[]`; fixtures rebuilt from live payloads with the two Lancet DOIs kept distinct; `hallucination_ratio` counts only `not_found` (`undetermined_ratio` added); recall/precision de-duplicated; per-backend parser diagnostics; locator fails closed instead of a placeholder. Focused `20 passed`, full `166 passed`, ruff clean. | `external_sources.py`; `tests/fixtures/external_sources/`; `tests/test_external_sources.py` | Owner re-verification + merge |

## Boundary result

No forbidden path was changed. B5 does not modify `config.py`, shared
`contracts.py`, `application.py`, storage, gates, CLI/API, A-lane paths
(capability/capability_registry), B3 `audit_evidence.py`, or B4
`reader_writer_ports.py`. Real network calls are issued through an injectable
``httpx`` transport only; tests use ``httpx.MockTransport``. All parsed/fetched
output remains candidate-only until admitted by EvidenceService.

## Scope note (correcting earlier over-reach)

The previous slice placed Semantic Scholar / arXiv search inside B5; those
belong to A5 (TASK-SPECS A5:58). This redo scopes B5 to ADR-01 slot 7
(Crossref retraction/correction), slot 3 (PDF parsing), and slot 11 (gold set
metrics), per B5's own specification.