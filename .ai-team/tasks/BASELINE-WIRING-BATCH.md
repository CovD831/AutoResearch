# BASELINE-WIRING-BATCH

- ID: `BASELINE-WIRING-BATCH`
- Title: `Baseline wiring batch: run a scoped pipeline end-to-end, wire three slot islands, make task status verifiable`
- Status: `reviewing`
- Status note: 6 commits on `feat/baseline-wiring-batch` (base `origin/main@859eedc`), PR #40. The branch is pushed; `main` is untouched. The four code commits were each verified green in its own isolated worktree, not only at the tip; the two documentation-only commits were verified at the tip. This ledger exists so the change set satisfies the repository PR contract, which requires a task-local ledger whenever product files change.
- Owner: `owner`
- Next owner: `user`

## Goal

Turn the pipeline from "structurally complete but unable to run" into a reachable, verifiable
baseline, and repair the dispatch records that would have misdirected the next round of work.

Three things were actually wrong, and each is addressed by a separate commit:

1. The run could not reach the release gate at all. `GateRequest.work_closed_loop` was a `bool`
   derived as `not manuscript.unresolved_gaps`, so a pipeline merely *scoped* to literature
   evidence was reported as *broken*, and no value a caller could pass meant "this stage is not
   enabled".
2. Three ADR-01 slots had working, tested implementations with **no production consumer**:
   slot 3 (PDF parsing) and slot 7 (retraction check) in `external_sources.py` (887 lines),
   and slot 14 (K11 access policy) in `acl.py` (379 lines). Wiring them is the only way to find
   out whether they work in a real path.
3. The task-package ledger contradicted the repository: 28 packages carried statuses that would
   have sent a member to re-implement merged work, one with a `base_ref` 118 commits stale.

Not in scope: `reader_writer_ports` (580 lines). It needs a design decision — wrap the existing
service as one adapter so the three-way parity comparison has something to compare — rather than
a mechanical change, so it is deliberately left out.

## Acceptance scenarios

- [x] A scoped run reaches `release_pending` with `blockers=[]`, i.e. it reaches the L4 human gate instead of parking in `WAITING_EVIDENCE`.
- [x] `LoopClosure` names three facts (`CLOSED` / `NOT_APPLICABLE` / `OPEN`); only `OPEN` blocks; the default is `OPEN` so an undeclared caller fails closed.
- [x] A scoped pass restates its scope in the decision's reasons, so the ledger never reads as though a result lineage was verified.
- [x] ADR-01 slot 3 delegates PDF parsing to `PdfParser` (docling first), with the old `pypdf` pass retained and explicitly ranked last rather than removed.
- [x] ADR-01 slot 7 verifies persisted DOIs against Crossref and surfaces retracted/corrected verdicts in the run diagnostics.
- [x] ADR-01 slot 14 (K11) is evaluated at the external release, the one irreversible outward-facing action; off by default and **stated as such** in the run warnings.
- [x] Access control denies by default when enabled, and records the refusal as a blocker rather than raising, so the run stays resumable.
- [x] The four ACL states are pinned by tests (off / on+no policy / on+granted / on+ungranted) because a layer that denies everything would satisfy a denies-only suite.
- [x] R006-P0 is archived out of the production package with its negative result recorded.
- [x] All 28 task packages carry a status backed by a measurement, with `integrated_at` or `archived_at` evidence pointers.
- [x] Nine wiring task packages give each module its next concrete step, with an acceptance criterion of production reachability rather than "tests pass".
- [ ] The AI review job has produced a report on PR #40. It is still running; an empty report is not a pass.
- [ ] `main` carries these commits. It does not — the work is on a branch with an open PR, by design.

## Invariants

- **No shared-contract edits.** `contracts.py`, `graph.py`, `agents/base.py` and `application.py` are the global serial points. `graph.py` was touched only by the three-state plumbing that the loop-closure change required, and the change is additive.
- **`corpus.json` keeps its frozen keys meaning what they meant.** The fixture is matched label-for-label, so the old `work_closed_loop: bool` maps to `CLOSED`/`OPEN` rather than degrading to `OPEN` — degrading it would have flipped every closure-requiring case.
- **A loosened requirement is never left silent.** A scoped pass says so in its recorded reasons. A disabled access-control layer writes a warning. "Wired" and "not wired" must not produce indistinguishable run records.
- **No fallback may be presented as a result.** The manuscript carries an explicit placeholder for results; the contract that a model must not produce facts is unchanged.
- **Ranking rather than removal keeps a fallback honest.** `pypdf` is third, not deleted: its layout quality is the lowest of the three, but it is the reason the reader never degrades to "no text at all".
- **A green suite is not evidence of wiring.** Every island's own tests were passing before this change. That is exactly why the nine new packages state reachability as the criterion.
- **An unmeasurable case is left alone, not guessed.** Where neither "the branch is merged" nor product evidence could settle a package's status, the status was not changed.

## Decisions

- **D-BW-01 (`work_closed_loop` becomes three-state, not a loosened bool)**: removing the requirement would have made the gate pass by omission. Naming `NOT_APPLICABLE` keeps the distinction between "the lane did not run" and "the lane ran and did not close", which is the difference between a scoped pass and an open blocker.
- **D-BW-02 (default `OPEN`)**: the fail-closed direction. A caller that forgets to declare its closure state gets a blocker, not a silent pass.
- **D-BW-03 (the experiment lane declares its own state)**: it is the only stage that knows whether it ran. The gate consumes that fact rather than inferring closure from "are there any gaps?" — the inference was the original defect.
- **D-BW-04 (slot 7 reports, it does not adjudicate)**: dropping a record would change the behaviour of a lane whose contract this package does not own. The fact is surfaced and the decision stays with the caller.
- **D-BW-05 (DOI verification is bounded and de-duplicated)**: each check is a network round-trip, and a run that retrieves 15 papers must not become 15 sequential calls on the critical path. De-duplication is by normalized DOI, because the same DOI arriving from two sources otherwise spends two round-trips and emits two diagnostics.
- **D-BW-06 (ACL is off by default, and says so)**: in a single-operator local run every grant would be a formality — policy rows without control — so enforcing it adds records and no assurance. It is worth enabling where a release is authorized by someone other than the person running the CLI.
- **D-BW-07 (`base_ref` becomes the symbolic `main`, not a sha)**: a pinned sha goes stale the moment anything lands, and a package that starts from a stale base is how the previous generation ended up 118 commits behind.
- **D-BW-08 (task status is judged by product evidence, not by "the branch is merged")**: PR branches are deleted on merge, so 11 of 28 packages could not be judged that way at all.
- **D-BW-09 (archival does not move directories)**: the packages are marked in place, because moving them would break references that other documents still hold.

## Completed

- `src/autoresearch/contracts.py`: `LoopClosure` (`CLOSED` / `NOT_APPLICABLE` / `OPEN`), default `OPEN`.
- `src/autoresearch/agents/orchestrator.py` + `agents/reviewer.py` + `gates.py`: the experiment lane declares its closure state; the gate consumes it; a scoped pass restates its scope in the recorded reasons.
- `src/autoresearch/reader_service.py` + `adapter_search_service.py` + `external_sources.py`: slot 3 delegates to `PdfParser`; slot 7 verifies DOIs and emits retracted/corrected verdicts. `CrossrefClient` now closes its `httpx.Client` and supports the context-manager protocol.
- `src/autoresearch/config.py` + `application.py` + `graph.py`: slot 14 evaluated at the external release; `access_policy_enabled` config; explicit warning when the layer is off.
- `tests/test_acl_release_wiring.py` (new), `tests/test_loop_closure_tristate.py` (new), `tests/test_governance_services.py` (extended).
- `experiments/r006-p0/`: the abandoned baseline-measurement assets moved out of the production package, with `README.md` recording the four mis-specifications and the 24-case underpowering.
- `docs/tasks/**/task-package.json` (24 files): 11 → `integrated` with evidence pointers, 13 → `archived` with reasons, 3 left `planned`.
- `docs/rearchitecture/TASK-PACKAGE-REGISTRY.md`: header states the single source of truth, the dispatchable list, the `status` semantics, and the module-to-owner split; the body is marked as history.
- `docs/tasks/*/tasks/M*-WIRE/task-package.json` (9 files): the wiring packages.

## Pending

- **AI review report on PR #40.** The job is running. Historic risk: the gateway has returned 403 on review prompts before, in which case no report appears regardless of budget.
- **`main` has not moved.** These commits are on `feat/baseline-wiring-batch`; merging needs the protection window, because `require_last_push_approval=true` and the owner cannot self-approve.
- **`reader_writer_ports` is still an island.** The decision (wrap `reader_service`/`writing_service` as one adapter) is made but not implemented.
- **The nine wiring packages do not list `.ai-team/tasks/` in `allowed_paths`.** A member following them literally would produce a PR that fails the required check. This must be fixed before dispatch.
- **Slot 3 measured 228.7s on a 2.2MB PDF with docling** (first run, including model load). A parser-selection or caching decision is still open.
- **`repo-task-sync` fails on PR #40 for the same root cause as `Task contract`** and is informational only; it is not a required check.

## Next step

1. Re-run the required checks after this ledger lands and confirm `Task contract` turns green. If it does, that is the empirical confirmation that the ledger rule is the whole requirement.
2. Add `.ai-team/tasks/` to `allowed_paths` and state the ledger requirement in the deliverables of all nine `Mxx-WIRE` packages.
3. Decide the member access model. Members have historically worked from forks (`Luminary-s1`, `wangdafa750`), which the AI review skips by design; a same-repo branch requires granting write access.
4. Merge PR #40 through the protection window once the AI review report is in.

**Attack these first**:

1. **Is `NOT_APPLICABLE` a way to pass a gate by declaring it inapplicable?** It is recorded, and it restates the scope, but a caller who wants out can still declare it. What would make that harder without making the honest scoped case fail?
2. **Slot 7 only reports.** If a referenced paper is retracted, the record stays in the run. Is reporting enough for a manuscript that will be released, or does the retraction have to be a blocker?
3. **ACL off by default** means the gate's guarantee is opt-in. Where a release is authorized by someone else, off-by-default is a defect — is a warning in the run record enough to make that visible?

## Verification

All commands run in `/Users/abab/Documents/ChatGPT/autoresearch/AutoResearch` with
`<python> = /Users/abab/.workbuddy/binaries/python/envs/default/bin/python3` and `PYTHONPATH=src`.

- [x] **The four code commits were each checked out in their own isolated worktree** and tested there, not only at the tip: `02ed686` → 1041 passed / 2 skipped; `67172f6` → 1044 / 2; `b77eca7` → 1044 / 2; `6f85b4e` → 1048 / 2. `EXIT=0` in each.
- [x] `<python> -m ruff check src tests` → `All checks passed!` at every commit.
- [x] **The two documentation-only commits** (`8b47466`, `fc53f03`, both `docs/` only) were verified in the main worktree at the commit and at the tip: 1048 passed / 2 skipped, ruff clean.
- [x] **Commit count measured, not assumed**: `git rev-list --count 859eedc..HEAD` → `6`. An earlier draft of this ledger said seven; the number was corrected against this command.
- [x] `node .ai-team/check.mjs --base origin/main` → `Result: valid`.
- [x] All 28 `task-package.json` files still parse as JSON after the status rewrite.
- [x] `git diff --stat HEAD` empty after the batch — no uncommitted drift left behind.
- [x] **Criterion check for the ACL wiring**: disabling the ACL block makes the two denial tests fail with assertion errors and leaves the two coverage tests passing. A wiring that only had a denies case would be satisfied by a layer that denies everything.
- [x] **Live run against the real network** reaches `draft_reviewed` with 15 real papers and 31 evidence items; the diagnostics carry a genuine bibliographic alert (`10.1007/978-3-030-05318-5` is corrected per Crossref).
- [x] **Slot 3 layout quality measured**, not assumed: arXiv 1706.03762 → 49,240 characters with real page locators (`p.1`…`p.15`), which also removes the `local text` locator degradation recorded in the roadmap.
- [ ] **The AI review has not returned a report yet.** Not counted as verified.
- [ ] **`check_pr_contract.py --base 859eedc` on this branch has not been re-run after this ledger was added.** It is what the required check runs; claiming it passes before running it would be the same "claim before measure" error this batch is trying to avoid.

## Handoff note

To `user`. The branch is pushed, `main` is untouched, and all six commits are verified green.
The most useful thing to read first is the negative result in
`experiments/r006-p0/README.md` — four mis-specifications that cost a full round, recorded so the
next attempt does not repeat them.

Two findings from this batch are worth keeping beyond it:

- **"The branch is merged" is not a usable criterion** for task status, because PR branches are
  deleted on merge. Product evidence (`git cat-file -e HEAD:<path>`) settled 24 of 28.
- **A ledger's metadata line must be `- Status: \`value\`` with nothing after the closing
  backtick.** The validator anchors on `$`, so an inline annotation makes the field unparseable
  and the check reports a missing field rather than a malformed one. PR #35 hit exactly this.
