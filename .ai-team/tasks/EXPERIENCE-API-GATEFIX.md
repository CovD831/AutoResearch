# Experience API Gate Fix

- ID: `EXPERIENCE-API-GATEFIX-2026-09-15`
- Title: `Block self-promoted experience creation`
- Status: `reviewing`
- Owner: `user/team`
- Next owner: `repository maintainer`

## Goal

Close the external API path that allowed a caller to create an experience with
`promoted=true` or an elevated maturity stage without using the promotion
workflow. Keep internal experience settlement and existing promotion behavior
unchanged.

## Acceptance scenarios

- [x] `POST /experiences` with `promoted=true` returns HTTP 409.
- [x] A rejected self-promotion request creates neither an experience row nor a WikiPage.
- [x] `POST /experiences` with a non-`x0_raw` stage returns HTTP 409 and creates no record.
- [x] A normal experience creation returns HTTP 201 with `promoted=false` and `stage=x0_raw`.
- [x] Existing experience-sink and promotion behavior remains green.
- [x] The separate `/evidence` caller-supplied grade issue is explicitly deferred to a separate API decision.

## Invariants

- External experience creation may only create an unpromoted `x0_raw` record.
- Promotion remains owned by `ExperienceService.promote()` and its existing checks.
- Internal A6 settlement continues to call `ExperienceService.record()` directly.
- A rejected request must not persist an experience or its knowledge mirror.
- Evidence admission behavior is outside this change.

## Decisions

- Put the guard in `AutoResearchApplication.record_experience()` because it is
  the shared application boundary for external callers.
- Translate the boundary error to HTTP 409 in `api.py`, matching the existing
  promotion failure response.
- Do not reject `promoted=true` inside `ExperienceService.record()` globally;
  internal settlement must preserve existing promoted records when merging.
- Keep the `/evidence` grade-authority redesign out of this focused fix because
  it requires a separate Evidence API contract decision.

## Completed

- Added application-layer checks for `promoted=true` and non-`x0_raw` stages.
- Added API error handling for the new boundary checks.
- Added API regression coverage for rejection, no-write behavior, and normal creation.
- Documented the external experience creation contract.
- Manually verified `409 Conflict` followed by an empty experience search result.

## Pending

- Obtain the required approval from a reviewer with write access.
- Handle the separate `/evidence` caller-supplied grade issue in a follow-up change.
- Add real reviewer and human identity authorization in a later security scope.

## Next step

Review and merge this focused API boundary fix after the required checks and
approval pass.

## Verification

- [x] `.venv\\Scripts\\python.exe -m pytest -W error -rA` — 538 passed, 2 skipped.
- [x] `.venv\\Scripts\\python.exe -m ruff check src tests` — passed.
- [x] `.venv\\Scripts\\autoresearch.exe doctor` — passed.
- [x] `node .ai-team/check.mjs --base origin/main` — valid before PR ledger addition.
- [x] Manual API test — `promoted=true` returned `409 Conflict`; experience search returned `200 []`.
- [ ] CI `Task contract` and `repo-task-sync` after this ledger is pushed.

## Handoff note

The implementation commit is `036265f`. The PR must include this ledger with
the four production/test/documentation files so the repository task-contract
checks can verify the change's scope and evidence.
