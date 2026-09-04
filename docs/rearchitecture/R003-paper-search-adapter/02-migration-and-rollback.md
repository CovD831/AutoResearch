# Migration and rollback

The adapter is additive and can be exercised beside the legacy service. Target
fixtures use a controlled fake connector; legacy fixtures continue to call
`PaperSearchService.search`. Compare paper IDs/titles, diagnostics, evidence
candidate count, receipt status and replay behavior.

Rollback is deleting the adapter call site and retaining the legacy facade. A
pending reservation is intentionally retained as an unknown outcome; recovery
must inspect it before any retry, preventing accidental duplicate writes.
No schema rollback is required because the existing idempotency table is reused.
Promotion is blocked until tests show one external connector call for exact
replay and rejection for conflicting replay.
