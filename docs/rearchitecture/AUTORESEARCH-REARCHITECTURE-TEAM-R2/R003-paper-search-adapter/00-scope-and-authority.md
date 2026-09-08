# R-003 scope and authority

Status: implementation slice, target behavior not yet promoted.

Baseline is the working tree on September 3, 2026. The legacy authority remains
`PaperSearchService` and `AutoResearchApplication`. This increment adds a
target adapter around that service for one bounded query invocation.

In scope: typed capability manifest, invocation receipt, evidence candidates,
exact replay and conflicting-replay rejection. Out of scope: changing the five
Agent registry, remote plugin loading, distributed deployment, or replacing
the legacy facade.

User-delegated defaults from R-002 remain authoritative: Paper Search is the
first slice, local native/fake connectors are trusted, and runtime is a single
process with SQLite.
