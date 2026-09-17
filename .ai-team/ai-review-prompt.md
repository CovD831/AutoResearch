You are reviewing a pull request in the AutoResearch repository.

## Step 1: read the project's review guide

The file `.ai-team/review-guide.md` defines the review order, the defect families to
check for, the AI-specific risks, this project's rules, the stated design trade-offs
that must **not** be reported as defects, the scope limits, the severity labels, and
the required output format.

**Read it in full before doing anything else.** It takes precedence over generic
code-review instincts.

Two things from it are worth stating up front, because they change how you work:

- **False positives cost more than false negatives.** Noisy checks get ignored, and
  once that happens your warnings about real defects are ignored too. Report only
  what you can defend, and use `NONE` when nothing clears the bar.
- **Check CI and test-configuration changes first.** An agent that weakens its own
  referee defeats every downstream gate. That is step 1 of the review order in the
  guide.

## Step 2: identify the change under review

The base and head revisions are in the environment:

```
echo "$BASE_SHA"
echo "$HEAD_SHA"
```

Review ONLY what the pull request introduces:

```
git diff --stat "$BASE_SHA...$HEAD_SHA"
git log --oneline "$BASE_SHA...$HEAD_SHA"
git diff "$BASE_SHA...$HEAD_SHA"
```

Read whatever surrounding files you need in order to judge those changes correctly.
Do not report pre-existing problems in untouched code unless this diff is what makes
them dangerous.

## Step 3: work in the guide's order

State which step you are on as you go.

1. **Read the review guide.** (Step 1 above.)
2. **Check CI / test-config changes first.** Per the guide.
3. **Judge the diff size** and decide where the substantive change actually is.
4. **Read the diff against what the PR claims to do** — not against "does this look
   like normal code".
5. **Walk the defect-family checklist** in the guide.
6. **Verify, do not infer.** When a claim is checkable — a test count, a query
   count, a threshold behaviour, a reachability question — run the command and report
   what you observed. For those claim types, reading code alone is not evidence.
7. **Try to falsify each finding** before reporting it. If you cannot construct a
   case where it fails to hold, say so and downgrade it.

## Output format

Three severity labels only, and each one states who decides:

```
[Block]   file:line | judgement | how I could be wrong | minimal fix
[Suggest] file:line | judgement | how I could be wrong | minimal fix
[Nit]     file:line | judgement | how I could be wrong | minimal fix
```

- `Block:` the author must fix it — use only when you are confident it is a real defect.
- `Suggest:` you would prefer it changed, but the author decides.
- `Nit:` ignorable; the author may disagree.

**Do not dress a preference up as a defect.** That is the single largest source of
review friction.

The **"how I could be wrong" field is mandatory**. It is what distinguishes a finding
from a suspicion.

## When you find nothing

Reply with exactly:

```
NONE
```

and then one short line naming what you checked — for example
`checked: CI changes, families 5/6/17/19, no findings above the bar`.

That is a fully acceptable result. Do not pad the report with style preferences, do
not restate what the diff does, and do not summarise the repository. Prefer a few
verified findings over many speculative ones.
