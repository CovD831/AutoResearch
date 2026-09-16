# Experience API Gate Fix

- ID: `EXPERIENCE-API-GATEFIX-2026-09-15`
- Title: `Block self-promoted experience creation`
- Status: `integrated`
- Status note: merged to `main@81a35dd` via owner integration PR #34 (squash); PR #24 closed. Acceptance evidence is fresh; promotion to `accepted` awaits the P2 / authentication-layer Gate.
- Owner: `user/team`
- Next owner: `P2 (stage ladder) / authentication layer`

## Goal

Close the external API path that allowed a caller to create an experience with
`promoted=true` or an elevated maturity stage without using the promotion
workflow. Keep internal experience settlement and existing promotion behavior
unchanged. A caller-declared `grade` is deliberately NOT restricted here -- see
D-A7-02.

## Acceptance scenarios

- [x] `POST /experiences` with `promoted=true` returns HTTP 409.
- [x] A rejected self-promotion request creates neither an experience row nor a WikiPage.
- [x] `POST /experiences` with a non-`x0_raw` stage returns HTTP 409 and creates no record.
- [x] A normal experience creation returns HTTP 201 with `promoted=false`, `stage=x0_raw`.
- [x] Existing experience-sink and promotion behavior remains green.

## Invariants

- External experience creation may only create an unpromoted `x0_raw` record. `grade` is deliberately NOT restricted here (D-A7-02).
- Promotion remains owned by `ExperienceService.promote()` and its existing checks.
- Internal A6 settlement continues to call `ExperienceService.record()` directly.
- A rejected request must not persist an experience or its knowledge mirror.
- Evidence admission behavior is outside this change.

## Decisions

- Put the guard in `AutoResearchApplication.record_experience()` because it is
  the shared application boundary for external callers. Verified: this method has
  exactly one caller (`api.py`), so the guard cannot mis-fire on an internal path.
- Translate the boundary error to HTTP 409 in `api.py`, matching the existing
  promotion failure response.
- Do not reject these fields inside `ExperienceService.record()` globally;
  internal settlement must preserve existing promoted records when merging
  (D-A6-03), and that path is not the external boundary.

## Carried debt (D-A7-01, NOT closed by this PR)

The guards above close only the *direct write* of `promoted` / `stage` at the
creation endpoint. `promote()`'s four gates are still all caller-declared:

```
POST /experiences               {"grade": "H3", "recurrence_count": 2}
POST /experiences/{id}/promote  {"reviewer_approved": true, "human_approved": true}
```

Two ordinary POSTs therefore still yield a promoted experience, and the
repository has **no authentication layer** (`grep` for `approved_by` / auth
middleware returns nothing).

This is **pre-existing and by design for now** -- the identical script produces
byte-identical output on `main@8dd8780` (verified 2026-09-16). R006 §11.11
freezes `promote()`'s signature and failure semantics, and the prescribed fix is
the P2 stage ladder (`promoted` derived from `stage`, via `advance_stage`) plus
authenticated approval writes (`AutoResearch_详细计划书.md:100`: 人工批准只能由已认证的
项目角色写入).

### D-A7-02: the obvious shortcut is wrong -- do not take it

Blocking a caller-declared `grade` at the creation boundary looks like the same
fix as blocking `promoted`. **It is not, and it is actively harmful.**

Raised in owner review of #24 and then **measured and reverted** (2026-09-16):
adding `if item.grade is not EvidenceGrade.E0: raise PermissionError` leaves the
whole suite green (539 passed) and closes the grade field -- but it makes
promotion **gate 2 unreachable through the entire public API**, because:

- every non-`E0` grade write in the repository targets `EvidenceItem` /
  `EvidenceCandidate` (`graph.py:137`, `benchmark.py:1009`,
  `reader_writer_ports.py:216,339`, `external_sources.py:510`,
  `audit_evidence.py:694`) -- **none** targets an `ExperienceRecord`;
- `ExperienceSink` pins `E0` for created records and preserves it on merge
  (`experience_sink.py:754`, `763-774`) -- by design, per D-A6-03.

So an `E0`-only creation guard silently *disables* promotion instead of
securing it: `POST /experiences {"grade":"H3"}` → 409, then `/promote` → 404.
**Until an adjudicated path exists that raises an experience's grade, leaving
gate 2 caller-declarable is the lesser defect.** This is the same failure mode
as the D-F8-01 precedent, where an owner-applied blind-review finding turned 44
tests red.

Both obligations are recorded as Gate clauses for P2 / the authentication layer,
and the behaviour is pinned by
`test_api_experience_promotion_gates_are_caller_declared`, which is explicitly
documented as having **no discriminating power** and whose D-A7-02 assertion
fails loudly if someone re-adds the harmful guard.

## Completed

- Added application-layer checks for `promoted=true` and non-`x0_raw` stages.
- Added API error handling for the new boundary checks.
- Added API regression coverage for rejection, no-write behavior, and normal creation.
- Documented the external experience creation contract, including the carried debt.
- Manually verified `409 Conflict` followed by an empty experience search result.
- Integrated: squash-merged as `81a35dd` on 2026-09-16 after the member branch
  (`codex/experience-api-gatefix` @ `e327f1a`) was merged onto `main@8dd8780`
  with no conflicts. The member's guard was adopted verbatim; no new guard was
  added. The owner applied the D-A7-02 revert and the scope-accuracy wording.

## Pending

- Obtain the required approval from a reviewer with write access.
- **P2**: stage ladder so `promoted` derives from `stage` (`advance_stage`); this is the
  prescribed route for D-A7-01 and must not be pre-empted by creation-endpoint guards.
- **Authentication layer**: reviewer / human approval must be written by an authenticated
  project role rather than declared in a request body (`AutoResearch_详细计划书.md:100`).
- Handle the separate `/evidence` candidate-vs-direct-admission issue in a follow-up change.

## Next step

Review and merge this focused API boundary fix after the required checks and
approval pass.

## Verification

- [x] `main@81a35dd` `pytest -o addopts="" -q` — 539 passed, 2 skipped (measured in `/tmp/verify-main`).
- [x] `main@8dd8780` baseline `pytest -o addopts="" -q` — 537 passed, 2 skipped (measured in `/tmp/rev-base`); +2 net.
- [x] `ruff check src tests` — passed.
- [x] `compileall -q src` — passed.
- [x] `check_pr_contract.py --base <main sha>` — valid.
- [x] `node .ai-team/check.mjs --base <main sha>` — valid.
- [x] Manual API test — `promoted=true` returned `409 Conflict`; experience search returned `200 []`.

## Handoff note

Member A's implementation commit is `036265f`; the ledger commit is `e327f1a`.
The member branch is cross-fork (`Luminary-s1/AutoResearch`), so the owner could
not push to it and integrated through `owner/experience-gate-integration` ->
PR #34 -> squash `81a35dd`. `promoted`/`stage` guards are the member's, adopted
verbatim. The owner's contribution is scope accuracy plus the D-A7-02 revert
(the `grade` guard was written, measured as making promotion gate 2 unreachable,
and withdrawn). PR #24 is closed with a thank-you note.

Known limitations carried forward (do not describe as verified):
- D-A7-01 -- promotion gates are caller-declared; no authentication layer.
- The `/evidence` candidate-vs-direct-admission issue is untouched.
