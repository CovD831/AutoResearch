# CI-AI-REVIEW - Codex AI review job

- ID: `CI-AI-REVIEW`
- Title: `AI code review job (Codex + GLM-5.3)`
- Status: `reviewing`
- Owner: `owner`
- Next owner: `user`
- Base: `origin/main@780e051`

## Goal

Add a review job that reads code semantics, which the existing three jobs cannot do.

Today the repository checks documents and test outcomes only: `ruff`, `compileall`,
`pytest -W error`, `check_pr_contract.py`, `check.mjs`. None of them reads what the
code means. Two defects that reached `main` recently demonstrate the gap:

- a guard reading `row.get("evidence_id")` when the wiki-page schema field is
  `evidence_ids` -- an assertion that could never fail, and that passed every check
- `with sqlite3.Connection as connection:` in a test, which commits but never closes;
  `-W error` only catches this on Python 3.13 while CI pins 3.12

Both passed all existing gates. One was found by hand, the other only after a
four-lane deep review.

This package adds a review job that can read semantics, and ships the judgment
criteria it reviews against.

## Acceptance scenarios

- [x] The workflow posts a review comment on a pull request.
- [x] The reviewer is pointed at the WorkBuddy gateway rather than OpenAI.
- [x] The job runs on every pull request event, including each push.
- [x] A fork pull request is skipped with the reason recorded, not failed.
- [x] The job is advisory only and is not a required status check.
- [x] The review guide states the false-positive budget and the review order.
- [x] A live run completes end to end on a real pull request.

## Invariants

- **The reviewer must not be able to modify the branch under review.** The job uses
  `permission-profile: :read-only`; `permissions: contents: read` on the workflow.
- **The API key is never written into the repository.** It lives only in the
  repository secret `WB2API_KEY`.
- **A fork pull request must never be reported as a failure.** Secrets are
  unavailable there, so the skip is a first-class outcome with a written reason.
- **The job must not be a required status check.** It stays advisory until its
  false-positive rate has been measured on real pull requests.
- **`medium` is not used as a reasoning level.** It is not an official GLM-5.3
  level and was measured as accepted-but-inert (zero reasoning tokens).

## Decisions

- **D-CI-1**: Use `openai/codex-action@v1`. Of the three first-party review actions,
  it is the only one that accepts a custom endpoint (`responses-api-endpoint`);
  `anthropics/claude-code-action` and `google-github-actions/run-gemini-cli` are
  bound to their vendors' own clouds and cannot use our gateway.
- **D-CI-2**: Model `glm-5.3` with `effort: max`. Chosen by measurement, not by
  reputation: on the same probe it found two `high` and one `medium` finding,
  including the real concurrency defect in PR #36, where `kimi-k3-1` found one and
  `minimax-m3` returned `NONE`. `max` is also what the vendor recommends for
  reasoning and coding work.
- **D-CI-3**: The review guide is the substance of this change, not the workflow.
  A generic "review this code" prompt returns style advice; the guide points the
  reviewer at the defect families that have actually recurred here.
- **D-CI-4**: Severity labels are `Block` / `Suggest` / `Nit`, each naming who
  decides. The earlier `blocking/high/medium/low/note` scale did not, which invites
  a preference to be presented as a defect.
- **D-CI-5**: CI and test-configuration changes are the reviewer's **first** step.
  An agent that weakens its own referee defeats every downstream gate; this is the
  upstream-documented adversarial move.
- **D-CI-6**: A false positive costs more than a false negative. Google's Tricorder
  holds itself to a 10% ceiling on user-perceived false positives because noisy
  checks get bypassed, and once a reviewer is ignored its warnings about real
  defects are ignored too. `NONE` is therefore an accepted result.
- **D-CI-7**: `codex-version` is deliberately unpinned, because the `:read-only`
  permission profile requires CLI `>= 0.138.0`.
- **D-CI-8**: Keep `effort: max` and accept a long runtime. Depth is worth the
  latency; the goal is that a long review terminates with a landing, not that
  reviews are short. `timeout-minutes: 45` bounds a runaway, it does not pace the
  review.
- **D-CI-9**: Separate three things the first version conflated -- **depth** (keep),
  **noise** (tighten, per the false-positive budget) and **wandering** (stop; the
  only actual runaway). The run that produced nothing for 35 minutes was wandering,
  not depth.

## Completed

- Verified the gateway supports what Codex requires: `POST /v1/responses` returns a
  well-formed response object; with `tools` it returns a `function_call` output item;
  with `stream: true` it returns SSE. Measured by direct request, not inferred.
- Configured the repository secret `WB2API_KEY`.
- Wrote the workflow, the prompt file, and the review guide.
- **Ran it end to end on PR #37.** The log shows the Codex CLI being installed on the
  runner, the Responses proxy starting, the model reached, and the reviewer running
  `rg` searches inside the repository. Duration 116 s; 238,737 tokens.
- Second revision of the guide aligns it with Google / Microsoft / GitHub / OWASP
  practice and closes six gaps the first version had.

## Completed (continued)

- **Observed a runaway and bounded it.** The third run of this job spent 35 minutes
  and produced nothing, against 116 seconds for a simple diff in the same job. The
  cause was not depth: nothing told the reviewer when to stop looking. Constraints
  were added for exploration (no opening a file without a concrete suspicion, no
  re-verifying, skip generated artefacts and caches), for landing (stop and report
  when a run goes long), for report size (originally 8 findings, remainder as a
  count -- later tightened to 5, see below), and a requirement that behavioural
  claims cite a `file:line`.
- **Measured the timeout behaviour rather than assuming it.** A `timeout-minutes: 30`
  job was cancelled at exactly 35 minutes, so GitHub's cancellation is cooperative
  and a step blocked on an external HTTP call notices late. The limit was raised to
  45 minutes and the measurement recorded in the workflow comment.

### The runaway was not the task: it was the action wrapper

- **Three reviews hung at 55 minutes, and the cause was not the review.** After the
  exploration constraints landed, a run still spent 55 minutes with `Run the review`
  never leaving `in_progress`. The task surface was not the reason.

  `@v1` and `v1.12` are the same commit, and v1.12 has a wrapper lifecycle bug:
  `openai/codex-action#169` reports 33 of 39 reviews stuck until the job timeout
  with this job's exact configuration, the shape being "Codex prints its final JSON
  and token count, then the action never exits or emits its end marker". The wrapper
  spawns with inherited stdout/stderr and waits on the child's `close` event, so a
  descendant holding those descriptors keeps it alive after the direct child is
  done. `#151` fixes it with private pipes and is unreleased.

  Pinned to `v1.11`, which supports both `permission-profile` and `codex-home`.
  Result across two runs: 55 minutes hanging became 6.3 minutes either completing or
  failing cleanly, and `Post Run the review` now executes, which is the end marker
  the wrapper was failing to emit.

- **A step-level timeout is not a hard stop.** `timeout-minutes: 25` was set on the
  review step and a run still reached 55 minutes. Cooperative cancellation needs the
  wrapper's cooperation, and a wrapper blocked in `await child.on('close')` does not
  provide it. The step bound is kept as a second layer under the job bound, not as
  the mechanism that ends a hung review.

- **`approval_policy = "never"` is load-bearing on this runner, not tidiness.**
  `permission-profile: ":read-only"` constrains the filesystem and the network but
  sets no approval policy, and Codex defaults to `on-request` -- in CI, asking a
  human who is not there. The logs show
  `warning: Codex could not find bubblewrap on PATH`, so there is no sandbox backend,
  and a read-only policy without one falls back to *requiring* approval. `never`
  turns that into reject-and-continue. It has to go through `codex-home` because
  codex-action lists `approval_policy` in `RESTRICTED_CONFIG_ROOTS`.

- **The token budget fired on a real review, and was then raised.** An uncalibrated
  `limit_tokens = 600000` stopped a review at 602,575 tokens -- correct behaviour,
  0.4% past the limit, and proof the mechanism works. But it stopped the run before a
  report landed. Raised to 1,500,000; the bound exists to stop a runaway, not to cut
  off a review that is working.

- **`effort: max` is configured but unverified.** Codex logs
  `Model metadata for glm-5.3 not found. Defaulting to fallback metadata`. The
  session reports `reasoning effort: max`, but with the model absent from Codex's
  table there is no guarantee the effort mapping is the one this setting selects.

- **Report cap tightened from 8 to 5**, with a ranking rule (severity, then
  defensible, then introduced-by-this-diff) and an exception: more than five
  `Block` findings are all reported, because the cap limits noise rather than
  defects. Rationale: Atlassian measured a 28.6-43.3% adoption rate on 4,000 internal
  LLM review comments -- over half ignored -- and Google's Tricorder budgets analyzers
  at a 10% perceived false-positive rate (Sadowski et al., CACM 2018).

- **Reviews are now routed by diff type.** Every changed file is assigned to a track
  -- DOC, CODE, CONFIG or DATA -- and the track decides what is read, which defect
  families apply, and whether anything may be executed. DATA is the catch-all so no
  diff falls through, and a mixed diff is split per file so no file is orphaned.
  Documentation is checked by reading against the repository, never by executing, and
  the full suite is off limits on every track. `.github/**` and test-config changes
  are still checked first on every track. Inspired by the reported Copilot finding
  that a reviewer should not start by exploring the entire repository.

## Pending

- A review of a pull request that contains real code changes. Every end-to-end run so
  far has been on a diff of Markdown plus one YAML file.
- Follow-up: the two gates disagree about whether `.github/` counts as a product
  change. `check_pr_contract.py` exempts the whole `.github/` prefix; `check.mjs`
  exempts only `repo-task-sync.yml`. This package added a ledger rather than change
  the gate; the inconsistency is recorded, not resolved.

## Next step

Trigger the review on a pull request that changes Python. PR #27 (`feat/r007-l01-context`)
is owner-authored and same-repo, so it is a usable replay target.

## Verification

- [x] `python -c "import yaml; yaml.safe_load(...)"` parses the workflow; jobs and
      `if:` conditions resolve as intended.
- [x] End-to-end run on PR #37: `AI review` completed `SUCCESS`, the comment was
      posted, and the log confirms the CLI install, the proxy, the model, and the
      in-repository `rg` searches.
- [x] The fork-skip path exercised: `AI review (skipped)` reported `SKIPPED`.
- [x] `pytest -W error` and `ruff` unaffected: this package changes no Python.
- [x] **The action-wrapper fix verified end to end.** Two runs after pinning to
      `v1.11`: one completed and posted a comment in 6.28 minutes, one terminated
      cleanly at 6.35 minutes on the budget. Against 55-minute hangs before the pin.
      `Post Run the review` executes in both, which is the end marker v1.12 failed to
      emit.
- [x] **The token budget verified.** Observed spend 602,575 against a 600,000 limit --
      the mechanism fires, and the number was too low rather than inert.
- [x] **Track routing verified from the logs.** The reviewer checked CI configuration
      explicitly (`rg` over `uses:` / `if:` / `timeout-minutes:` / `permissions:`),
      read the guide in slices rather than in full, and did not run the test suite.
- [x] **First real findings produced.** The run on `4f1dd01` reported two `Suggest`
      items, both against this ledger: the stale 8-finding cap, and the missing record
      of the 25-minute step bound and the `v1.11` pin. Both were correct and are fixed
      above.
- [ ] Review quality on a diff that contains code. Not yet exercised.
- [ ] `effort: max` is configured but unverified -- Codex has no metadata for
      `glm-5.3` and falls back to defaults. Untested until the gateway serves a model
      Codex knows.

## Handoff note

- From: `owner`
- To: `user`
- The job is live and advisory. It is not a gate, so it cannot block a merge; read
  its output on the next few code-bearing pull requests before deciding whether to
  promote it.
- The secret `WB2API_KEY` is a gateway key, not an OpenAI key. Rotating the gateway
  credential means updating that secret.
- Known gap: fork pull requests receive no review, because GitHub withholds secrets
  from them. Member PRs come from forks. Resolving this needs a different mechanism,
  not a workflow tweak.
