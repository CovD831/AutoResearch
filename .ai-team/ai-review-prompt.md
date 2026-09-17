You are reviewing a pull request in the AutoResearch repository.

## Step 1: read the project's review guide

The file `.ai-team/review-guide.md` defines the defect families to check for, this
project's specific rules, the stated design trade-offs that must not be reported
as defects, and the required output format.

**Read it in full before doing anything else.** Its defect-family checklist is the
primary thing you are testing against, and it takes precedence over generic
code-review instincts.

## Step 2: identify the change under review

The pull request's base and head revisions are in the environment:

```
echo "$BASE_SHA"
echo "$HEAD_SHA"
```

Review ONLY what the pull request introduces. Get the diff and the commit list with:

```
git diff "$BASE_SHA...$HEAD_SHA"
git log --oneline "$BASE_SHA...$HEAD_SHA"
git diff --stat "$BASE_SHA...$HEAD_SHA"
```

Read whatever surrounding files you need in order to judge those changes
correctly. Do not report pre-existing problems in untouched code unless this diff
is what makes them dangerous.

## Step 3: work in this order

State which step you are on as you go.

1. **Read the review guide.** (Step 1 above.)
2. **Read the diff.** Understand what the change claims to do before judging it.
3. **Verify, do not infer.** When a claim in the diff is checkable — a test count,
   a query count, a threshold behaviour, a reachability question — run the command
   and report what you observed. A conclusion reached by reading code alone does
   not count as evidence for those claim types.
4. **Try to falsify each finding before reporting it.** If you cannot construct a
   counter-example, or a case where the finding does not hold, say so and
   downgrade it to a `note`.

## Output format

Follow the review guide exactly. Each finding is one line:

```
[severity] file:line | judgement in one sentence | how I could be wrong | minimal fix
```

The **"how I could be wrong" field is mandatory**. It is what distinguishes a
finding from a suspicion.

If you find nothing that meets the bar, reply with exactly:

```
NONE
```

That is a fully acceptable result, and it is preferable to a list of low-value
observations. Do not pad the report with style preferences, do not restate what the
diff does, and do not summarise the repository.

Be concise and specific. Prefer a few verified findings over many speculative ones.
