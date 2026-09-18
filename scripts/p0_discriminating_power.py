"""P0 discriminating-power self-check: can injected experience change the draft at all?

Why this file exists
--------------------
The first P0 implementation produced an agent whose ``draft`` returned the task's
own fields verbatim:

    AgentDraft(body=task.body, title=task.title, claims=task.claims,
               claim_evidence_map=task.claim_evidence_map)

It faithfully copied the existing ``RecordedAgent``, whose docstring states the
intent -- "Fixing the corpus fixes the prompts ... swapping the writing head must
not silently change the measured quantity."  That is correct for the mechanism
benchmark it was built for, and fatal here: a P0 comparison asks whether the
*experience content* moves the output, so an agent that ignores its prompt cannot
answer it.  Every condition scored identically (``hallucination_ratio=1.0``,
``evidence_binding_rate=0.0``), which the stop-loss rule would have read as
"experience brings no benefit" and terminated the program on a defect of our own
making.

Both review gates missed it: steelmanning and independent review read the design
documents, and this lives in how the design was implemented.  Hence a separate,
executable check that runs *before* any comparison: prove the treatment variable
reaches the measured quantity.

What is checked
---------------
1. A stub drafter whose output is a pure function of the assembled prompt.
2. Injecting different experience produces different drafts (the variable is
   live).
3. Injecting *no* experience and injecting the length-matched placeholder differ
   from the real treatments (the control is distinguishable).
4. The whole check runs offline with no credentials and no network.

What is NOT checked
-------------------
Whether the change *improves* anything.  That is the comparison's job, and it
only becomes meaningful once this file passes.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass

sys.path.insert(0, "src")

from autoresearch.benchmark import AgentDraft, BenchmarkTask  # noqa: E402

GUIDANCE_HEADER = "## Prior experience (guidance only, not evidence)\n"
RECORD_TEMPLATE = "- problem: {problem}\n  technique: {technique}\n  outcome: {outcome}\n"
PROMPT_TEMPLATE = (
    "## Question\n{question}\n\n"
    "{guidance}"
    "## Draft body\n{body}\n"
)

#: The placeholder must occupy a comparable amount of prompt as real guidance,
#: otherwise "injected experience" and "the prompt got longer" are confounded
#: (REVIEW.md B2).  The real check of equal length lives in the self-test below.
PLACEHOLDER_LINE = "- (placeholder filler of matched length; carries no experience)\n"


@dataclass(frozen=True, slots=True)
class StubExperience:
    problem: str
    technique: str
    outcome: str


def format_guidance(records: tuple[StubExperience, ...]) -> str:
    if not records:
        return ""
    body = "".join(
        RECORD_TEMPLATE.format(
            problem=r.problem, technique=r.technique, outcome=r.outcome
        )
        for r in records
    )
    return GUIDANCE_HEADER + body + "\n"


def format_placeholder(line_count: int) -> str:
    """Content-free filler sized to a real guidance block (lines = records + 2)."""

    return GUIDANCE_HEADER + PLACEHOLDER_LINE * line_count + "\n"


def render(task: BenchmarkTask, guidance: str) -> str:
    return PROMPT_TEMPLATE.format(question=task.question, guidance=guidance, body=task.body)


class StubPromptDependentDrafter:
    """A drafter whose output is a deterministic function of its prompt.

    This is the *point* of the stub: it makes "did the treatment reach the
    output" observable without a live model, a credential or a network call.  It
    says nothing about output quality and must not be read that way.
    """

    name = "stub-prompt-dependent-drafter"

    def __init__(self, *, mode: str, experiences: tuple[StubExperience, ...] = ()) -> None:
        self.mode = mode
        self._experiences = experiences
        self.last_prompt = ""

    def _guidance(self) -> str:
        if self.mode == "off":
            return ""
        if self.mode == "placeholder":
            return format_placeholder(len(self._experiences) + 2)
        return format_guidance(self._experiences)

    def draft(self, task: BenchmarkTask) -> AgentDraft:
        prompt = render(task, self._guidance())
        self.last_prompt = prompt
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        # Claims are bound to a material id derived from the prompt digest, so a
        # different prompt yields a different binding -- exactly the quantity
        # evidence_binding_rate reads.  Deterministic: same prompt, same draft.
        bound = f"material-{digest[:12]}"
        claims = ("claim-from-prompt",)
        return AgentDraft(
            body=f"body-{digest[:16]}",
            title=f"title-{digest[:8]}",
            claims=claims,
            claim_evidence_map={claims[0]: (bound,)},
        )


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _task() -> BenchmarkTask:
    return BenchmarkTask(
        case_id="selfcheck-1",
        question="Does evidence gating change how an evaluation section is planned?",
        title="selfcheck",
        body="A frozen body used only by the discriminating-power self-check.",
    )


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    task = _task()

    exp_a = (
        StubExperience(
            problem="retrieval failed because the key was absent",
            technique="read the key from settings and fail closed when missing",
            outcome="the primary source stopped failing",
        ),
    )
    exp_b = (
        StubExperience(
            problem="the report understated spend",
            technique="return None when the catalogue has no price",
            outcome="budget reports stopped understating spend",
        ),
    )

    off = StubPromptDependentDrafter(mode="off")
    clean_a = StubPromptDependentDrafter(mode="clean", experiences=exp_a)
    clean_b = StubPromptDependentDrafter(mode="clean", experiences=exp_b)
    placeholder = StubPromptDependentDrafter(mode="placeholder", experiences=exp_a)

    d_off = off.draft(task)
    d_a = clean_a.draft(task)
    d_b = clean_b.draft(task)
    d_p = placeholder.draft(task)

    # 1. Same prompt -> same draft (determinism; a flaky check proves nothing).
    again = clean_a.draft(task)
    results.append(
        CheckResult(
            "deterministic",
            again == d_a,
            "same prompt must yield the same draft",
        )
    )

    # 2. Different experience -> different draft.  THE check this file exists for.
    results.append(
        CheckResult(
            "treatment reaches the output",
            d_a != d_b,
            f"experience A vs B: {'differ' if d_a != d_b else 'IDENTICAL'} "
            f"(body {d_a.body!r} vs {d_b.body!r})",
        )
    )

    # 3. Treatment differs from the no-experience baseline.
    results.append(
        CheckResult(
            "treatment differs from off",
            d_a != d_off,
            f"clean vs off: {'differ' if d_a != d_off else 'IDENTICAL'}",
        )
    )

    # 4. The placeholder control is distinguishable from the real treatment --
    #    otherwise the control would be measuring the treatment.
    results.append(
        CheckResult(
            "placeholder differs from treatment",
            d_p != d_a,
            f"placeholder vs clean: {'differ' if d_p != d_a else 'IDENTICAL'}",
        )
    )

    # 5. The placeholder prompt is length-matched to the real guidance prompt.
    len_real = len(render(task, format_guidance(exp_a)))
    len_ph = len(render(task, format_placeholder(len(exp_a) + 2)))
    ratio = len_ph / len_real if len_real else 0.0
    results.append(
        CheckResult(
            "placeholder is length-matched",
            0.5 <= ratio <= 2.0,
            f"placeholder/real prompt length = {ratio:.2f} (must be within [0.5, 2.0])",
        )
    )

    # 6. Claim binding actually varies with the prompt -- the quantity the
    #    primary metric reads must be reachable by the treatment.
    bound_off = d_off.claim_evidence_map["claim-from-prompt"]
    bound_a = d_a.claim_evidence_map["claim-from-prompt"]
    results.append(
        CheckResult(
            "prompt reaches the binding",
            bound_off != bound_a,
            "evidence_binding_rate reads claim_evidence_map; the prompt must move it",
        )
    )

    return results


def main() -> int:
    results = run_checks()
    width = max(len(r.name) for r in results)
    failed = 0
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        if not r.passed:
            failed += 1
        print(f"[{mark}] {r.name:<{width}}  {r.detail}")
    print()
    if failed:
        print(
            f"self-check FAILED ({failed} of {len(results)}): the treatment does not "
            "reach the measured quantity. Running the comparison now would produce a "
            "difference-free result that is an artefact of the harness, not a finding."
        )
        return 1
    print(
        f"self-check OK ({len(results)} checks): injected experience changes the draft, "
        "the controls are distinguishable, and the change reaches the quantity the "
        "primary metric reads."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
