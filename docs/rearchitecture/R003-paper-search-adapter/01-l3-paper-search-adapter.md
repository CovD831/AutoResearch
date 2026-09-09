# L3 contract: Paper Search capability adapter

`PaperSearchCapabilityAdapter.invoke` accepts `project_id`, `run_id`, a unique
`invocation_id`, one non-empty query, a limit from 1 to 100, and optional seed
records. It returns typed papers, bounded diagnostics, evidence candidates, and
an `InvocationReceipt`.

The adapter reserves invocation identity before external calls and finalizes
the reservation after the call; a pending reservation is treated as an unknown
outcome and requires explicit recovery. EvidenceService
remains the sole writer of durable evidence. The idempotency key is
the storage tuple `(scope=paper_search, key=run_id:invocation_id)`. Exact replay returns the stored papers
and candidates with receipt status `replayed`; changed input raises a conflict.
An empty result is `unknown`, never successful invention. Legacy service
behavior and facade construction remain unchanged during the migration window.

> **Owner ruling D-F8-01（2026-09-10，supersedes the sentence above）**：
> A deterministic empty result is `completed_empty`, NOT `unknown`. `unknown_outcome`
> is reserved for interrupted executions (timeout / crash after `service_started`)
> and is only reachable via explicit `recover_pending`. The anti-invention intent
> is preserved by stronger mechanisms: `completed_empty` yields no EvidenceItem,
> downstream readiness maps it to `needs_material` / `blocked`, and INV-10 requires
> valid evidence for any `completed` claim. Authority: `docs/coord/empty-result-ruling.md`.
