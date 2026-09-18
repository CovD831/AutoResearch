"""R006-P0-BASELINE experience-injection pipeline and agent variants.

P0 verifies a single premise: does *injecting historical experience* make paper
production better?  This module is the **only** code P0 adds on the drafting
side.  It deliberately stays below the runtime (`benchmark.py`) and the
experience store (`evolution_service.py` / `contracts.py`): it synthesises
``ExperienceRecord`` objects and exposes two ``BenchmarkAgent`` implementations
that differ *only* in whether experience text is appended to the draft prompt.

Hard constraints honoured here (DESIGN.md §2.3 / §2.4):

* **No hand-written experience prose.**  Every ``ExperienceRecord`` is produced
  through the *same* mapping path ``experience_sink.py`` uses to turn audit
  events into failure causes -- ``problem`` is extracted from the event payload,
  ``technique`` / ``outcome`` are built from fixed templates plus event fields.
* **Three variants from one synthesizer.**  ``clean`` / ``noisy`` / ``wrong``
  differ only in the *input* the synthesizer transforms, never in the code that
  writes the record.  Noise and error injection are reproducible, seeded
  transformations, not ad-hoc text.
* **Two agents, one path.**  ``NoExperienceAgent`` and ``ExperienceInjectingAgent``
  share every line except whether the guidance block is empty.
* **Simplest retrieval only.**  ``SimpleExperienceRetriever`` is keyword/top-k,
  no vectors, no RRF (DESIGN.md §5).
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from autoresearch.benchmark import AgentDraft, BenchmarkAgent, BenchmarkTask
from autoresearch.contracts import EvidenceGrade, ExperienceRecord

# Reuse the *exact* event->cause mapping from the production sink so the
# synthesised records follow the same contract the real pipeline would produce.
from autoresearch.experience_sink import (
    FAILURE_TAG,
    MAPPING_RULES,
    TECHNIQUE_AUDIT_EVIDENCE_REMEDIATION,
    TECHNIQUE_AUDIT_UNKNOWN_RESOLUTION,
    TECHNIQUE_EVIDENCE_BLOCKED,
    _experience_id,
    _recurrence_key,
)

# ---------------------------------------------------------------------------
# 1. Experience synthesis -- same path as experience_sink.py
# ---------------------------------------------------------------------------

#: Fixed template strings.  Experience *text* is always field concatenation,
#: never a hand-written sentence (DESIGN.md §2.3 hard constraint).
VAGUE_OUTCOME_TEMPLATE = (
    "outcome was not clearly recorded; the situation may or may not have improved "
    "(blurred from: {original})"
)
CONFLICT_OUTCOME_TEMPLATE = (
    "an alternative approach reported the opposite result for the same problem"
)
STALE_TECHNIQUE_PREFIX = "(deprecated) "
WRONG_OUTCOME_TEMPLATE = (
    "this technique reliably resolves the problem (claimed, never verified)"
)

STALE_TAG = "stale"
VAGUE_TAG = "noisy_vague"
CONFLICT_TAG = "noisy_conflict"
WRONG_TAG = "wrong"

#: Reproducible opposite/erroneous technique map (fixed strings, seed-selected).
OPPOSITE_TECHNIQUE = {
    TECHNIQUE_EVIDENCE_BLOCKED: "evidence_admission_force_accepted",
    TECHNIQUE_AUDIT_EVIDENCE_REMEDIATION: "audit_evidence_skip_remediation",
    TECHNIQUE_AUDIT_UNKNOWN_RESOLUTION: "audit_unknown_ignore",
}
WRONG_TECHNIQUE = {
    TECHNIQUE_EVIDENCE_BLOCKED: "evidence_admission_always_bypass",
    TECHNIQUE_AUDIT_EVIDENCE_REMEDIATION: "audit_evidence_accept_verbatim",
    TECHNIQUE_AUDIT_UNKNOWN_RESOLUTION: "audit_unknown_treat_as_pass",
}


def _match_to_record(
    project_id: str, technique: str, problem: str, outcome: str, evidence_ids: tuple[str, ...]
) -> ExperienceRecord:
    """Replicate the *first-occurrence* record construction in ``_merge_records``.

    This is the same ``ExperienceRecord`` the sink writes when no prior record
    exists for a cause: same ``experience_id`` derivation, same ``grade=E0``,
    same ``failure`` tag.  The sink's merge branch (existing record) is not
    needed for synthesis because synthetic causes are always fresh (no store).
    """

    recurrence_key = _recurrence_key(technique, problem)
    experience_id = _experience_id(project_id, recurrence_key)
    return ExperienceRecord(
        experience_id=experience_id,
        project_id=project_id,
        problem=problem,
        technique=technique,
        outcome=outcome,
        grade=EvidenceGrade.E0,
        recurrence_count=1,
        evidence_ids=list(evidence_ids),
        tags=[FAILURE_TAG],
        promoted=False,
    )


@dataclass(frozen=True)
class SynthesisResult:
    """What one synthesize call produced, fully reconstructable from its inputs."""

    records: tuple[ExperienceRecord, ...]
    source_events: tuple[dict[str, Any], ...]
    mode: str
    seed: int
    project_id: str
    transforms: tuple[str, ...] = ()

    def reproducible_input(self) -> dict[str, Any]:
        """The exact call that regenerates this result."""

        return {
            "events": [dict(event) for event in self.source_events],
            "mode": self.mode,
            "seed": self.seed,
            "project_id": self.project_id,
        }


def synthesize_experiences(
    events: Sequence[dict[str, Any]],
    *,
    mode: str = "clean",
    project_id: str = "synthetic",
    seed: int = 0,
) -> SynthesisResult:
    """Synthesize ``ExperienceRecord`` objects from constructed audit events.

    ``events`` are in the *same shape* ``ExperienceSink._events`` returns:
    ``{"event_id": str, "event_type": str, "payload": dict}``.  Each mapped
    event is run through the very same ``MAPPING_RULES`` the production sink
    uses, so the produced ``problem`` / ``technique`` / ``outcome`` follow the
    identical template-based construction (never hand-written).

    ``mode`` selects which reproducible input transform is applied:

    * ``clean`` -- no noise.
    * ``noisy`` -- inject vague phrasing, a conflicting experience (same problem,
      opposite technique), and a stale experience, via a seeded RNG.
    * ``wrong`` -- deliberately wrong technique on a seeded-selected record.

    The construction parameters (events, mode, seed, project_id) are returned in
    ``SynthesisResult`` so the run is reproducible.
    """

    if mode not in {"clean", "noisy", "wrong"}:
        raise ValueError(f"unknown synthesis mode: {mode!r}")

    matches: list[tuple[str, str, str, tuple[str, ...]]] = []
    for event in events:
        parser = MAPPING_RULES.get(str(event.get("event_type")))
        if parser is None:
            continue
        payload = event.get("payload")
        match = parser(payload) if payload is not None else None
        if match is None:
            continue
        matches.append((match.technique, match.problem, match.outcome, match.evidence_ids))

    records = [
        _match_to_record(project_id, technique, problem, outcome, evidence_ids)
        for technique, problem, outcome, evidence_ids in matches
    ]

    transforms: list[str] = []
    if mode == "noisy":
        records, transforms = _inject_noise(records, project_id=project_id, seed=seed)
    elif mode == "wrong":
        records, transforms = _inject_wrong(records, project_id=project_id, seed=seed)

    return SynthesisResult(
        records=tuple(records),
        source_events=tuple(dict(event) for event in events),
        mode=mode,
        seed=seed,
        project_id=project_id,
        transforms=tuple(transforms),
    )


def _inject_noise(
    records: list[ExperienceRecord], *, project_id: str, seed: int
) -> tuple[list[ExperienceRecord], list[str]]:
    """Reproducible noise: vague phrasing + conflicting experience + stale record.

    Indices are drawn from ``random.Random(seed)``; every mutation uses a fixed
    template plus the source record's own fields.  No prose is hand-written.
    """

    if not records:
        return list(records), []

    rng = random.Random(seed)
    out: list[ExperienceRecord] = []
    transforms: list[str] = []

    # (a) vague phrasing -- blur the outcome of one deterministic record.
    vague_idx = rng.randrange(len(records))
    for i, record in enumerate(records):
        if i == vague_idx:
            blurred = record.model_copy(
                update={
                    "outcome": VAGUE_OUTCOME_TEMPLATE.format(original=record.outcome),
                    "tags": sorted(set(record.tags) | {VAGUE_TAG}),
                }
            )
            out.append(blurred)
            transforms.append(f"vague:record[{vague_idx}]")
        else:
            out.append(record)

    # (b) conflicting experience -- same problem, opposite technique.
    src = records[rng.randrange(len(records))]
    opposite = OPPOSITE_TECHNIQUE.get(src.technique, f"{src.technique}_alternative")
    conflict = _match_to_record(
        project_id,
        opposite,
        src.problem,
        CONFLICT_OUTCOME_TEMPLATE,
        tuple(src.evidence_ids),
    ).model_copy(update={"tags": sorted({FAILURE_TAG, CONFLICT_TAG})})
    out.append(conflict)
    transforms.append(f"conflict:problem={src.problem!r}:technique={opposite!r}")

    # (c) stale experience -- a record marked deprecated.
    stale_src = records[rng.randrange(len(records))]
    stale = stale_src.model_copy(
        update={
            "technique": STALE_TECHNIQUE_PREFIX + stale_src.technique,
            "tags": sorted(set(stale_src.tags) | {STALE_TAG}),
        }
    )
    out.append(stale)
    transforms.append(f"stale:problem={stale_src.problem!r}")

    return out, transforms


def _inject_wrong(
    records: list[ExperienceRecord], *, project_id: str, seed: int
) -> tuple[list[ExperienceRecord], list[str]]:
    """Reproducible error: a seeded-selected record gets a deliberately wrong technique."""

    if not records:
        return list(records), []

    rng = random.Random(seed)
    target_idx = rng.randrange(len(records))
    out: list[ExperienceRecord] = []
    transforms: list[str] = []
    for i, record in enumerate(records):
        if i == target_idx:
            wrong_technique = WRONG_TECHNIQUE.get(
                record.technique, f"{record.technique}_unsupported"
            )
            wrong = _match_to_record(
                project_id,
                wrong_technique,
                record.problem,
                WRONG_OUTCOME_TEMPLATE,
                tuple(record.evidence_ids),
            ).model_copy(update={"tags": sorted({FAILURE_TAG, WRONG_TAG})})
            out.append(wrong)
            transforms.append(
                f"wrong:record[{target_idx}]:{record.technique!r}->{wrong_technique!r}"
            )
        else:
            out.append(record)
    return out, transforms


# ---------------------------------------------------------------------------
# 2. Simplest retrieval (no vectors / RRF, DESIGN.md §5)
# ---------------------------------------------------------------------------


class SimpleExperienceRetriever:
    """Keyword-overlap top-k over an in-memory experience corpus.

    P0 validates the *mechanism*, not retrieval quality.  If the whole corpus is
    searched the ranking still falls back to returning up to ``top_k`` records so
    the injection agent always has something deterministic to append.
    """

    def __init__(self, experiences: Sequence[ExperienceRecord], *, top_k: int = 5) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        self._experiences = tuple(experiences)
        self._top_k = top_k

    @staticmethod
    def _score(record: ExperienceRecord, query: str) -> int:
        text = (record.problem + " " + record.technique + " " + record.outcome).lower()
        return sum(1 for token in query.lower().split() if token and token in text)

    def retrieve(self, task: BenchmarkTask) -> tuple[ExperienceRecord, ...]:
        if not self._experiences:
            return ()
        query = f"{task.question} {task.title} {task.body}"
        ranked = sorted(self._experiences, key=lambda r: self._score(r, query), reverse=True)
        hits = [r for r in ranked if self._score(r, query) > 0][: self._top_k]
        if not hits:
            hits = list(ranked[: self._top_k])
        return tuple(hits)


# ---------------------------------------------------------------------------
# 3. Two agents -- identical path, only the guidance differs
# ---------------------------------------------------------------------------

GUIDANCE_HEADER = "# Past experience (guidance -- treat as suggestion, not fact):\n"
RECORD_TEMPLATE = "- PROBLEM: {problem}\n  TECHNIQUE: {technique}\n  OUTCOME: {outcome}\n"
PROMPT_TEMPLATE = "{question}\n\n{guidance}{body}"


class _BaseExperienceDraftAgent:
    """Shared drafting path.  ``draft`` subclasses differ *only* in the guidance.

    ``last_prompt`` is captured on every call so a test can prove the only
    difference between the variants is the guidance block (no other code path
    diverges -- same template, same material handling, same single "LLM" call).
    """

    name: str = "base-agent"

    def __init__(self, *, retriever: SimpleExperienceRetriever | None = None) -> None:
        self._retriever = retriever
        self.last_prompt: str = ""

    def _format_guidance(self, records: Sequence[ExperienceRecord]) -> str:
        if not records:
            return ""
        lines = [GUIDANCE_HEADER]
        for record in records:
            lines.append(
                RECORD_TEMPLATE.format(
                    problem=record.problem,
                    technique=record.technique,
                    outcome=record.outcome,
                )
            )
        return "".join(lines) + "\n"

    def _render(self, task: BenchmarkTask, guidance: str) -> str:
        return PROMPT_TEMPLATE.format(question=task.question, guidance=guidance, body=task.body)

    def _produce_draft(self, task: BenchmarkTask, guidance: str) -> AgentDraft:
        # The single, shared "LLM call": identical prompt assembly and identical
        # deterministic replay of the frozen corpus draft for both agents.
        self.last_prompt = self._render(task, guidance)
        return AgentDraft(
            body=task.body,
            title=task.title,
            claims=task.claims,
            claim_evidence_map=task.claim_evidence_map,
        )


class NoExperienceAgent(_BaseExperienceDraftAgent, BenchmarkAgent):
    """Baseline: drafts with no experience lookup at all."""

    name = "no-experience-agent"

    def draft(self, task: BenchmarkTask) -> AgentDraft:
        return self._produce_draft(task, self._format_guidance(()))


class ExperienceInjectingAgent(_BaseExperienceDraftAgent, BenchmarkAgent):
    """Injects retrieved experience into the prompt's guidance segment."""

    name = "experience-injecting-agent"

    def __init__(self, experiences: Sequence[ExperienceRecord], *, top_k: int = 5) -> None:
        super().__init__(retriever=SimpleExperienceRetriever(experiences, top_k=top_k))

    def draft(self, task: BenchmarkTask) -> AgentDraft:
        records = self._retriever.retrieve(task) if self._retriever else ()  # type: ignore[union-attr]
        return self._produce_draft(task, self._format_guidance(records))


# ---------------------------------------------------------------------------
# Sample construction (deterministic, reproducible) + minimal self-test
# ---------------------------------------------------------------------------


def sample_audit_events() -> list[dict[str, Any]]:
    """Deterministic audit events the synthesizer consumes.

    Mirrors the frozen contract ``ExperienceSink`` reads: each event carries the
    payload the production parsers expect.  The reasons/status feed ``problem``;
    the templates build ``technique``/``outcome``.
    """

    return [
        {
            "event_id": "evt-block-1",
            "event_type": "evidence.candidate_blocked",
            "payload": {
                "candidate_id": "cand-001",
                "reasons": [
                    "claim contradicts the cited source's stated method",
                    "locator does not resolve to a verifiable section",
                ],
            },
        },
        {
            "event_id": "evt-audit-1",
            "event_type": "audit_evidence.report_created",
            "payload": {
                "report_id": "rep-001",
                "status": "fail",
                "unverified_claims": ["the baseline metric improved by 30% without a control"],
                "admission_results": [{"evidence_id": "ev-abc"}],
                "deterministic_verdicts": [
                    {"reasons": ["no independent source"], "evidence_ids": ["ev-abc"]}
                ],
            },
        },
        {
            "event_id": "evt-audit-2",
            "event_type": "audit.report_created",
            "payload": {
                "report_id": "rep-002",
                "verdict_count": 4,
                "unknown_count": 2,
            },
        },
    ]


def _self_test() -> None:
    """Prove: (a) identical non-experience path, (b) three variants differ."""

    task = BenchmarkTask(
        case_id="case-x",
        question="Does experience injection reduce unsupported claims in drafts?",
        title="Experience injection study",
        body="A frozen draft body used for the control comparison.",
    )
    events = sample_audit_events()

    # (a) identical non-experience path -----------------------------------
    no_exp = NoExperienceAgent()
    empty_inj = ExperienceInjectingAgent([])
    d_no = no_exp.draft(task)
    d_empty = empty_inj.draft(task)
    assert d_no == d_empty, "agents must produce identical drafts when no experience is injected"
    assert no_exp.last_prompt == empty_inj.last_prompt, (
        "prompt path must be identical without guidance"
    )

    clean = synthesize_experiences(events, mode="clean").records
    inj = ExperienceInjectingAgent(clean)
    d_inj = inj.draft(task)
    # Reconstruct the guidance from exactly what the retriever returned; the only
    # difference from no_exp must be that block, inserted at a fixed position in
    # the shared template.
    retrieved = inj._retriever.retrieve(task)  # type: ignore[union-attr]
    assert retrieved, "retriever must surface at least one synthesized experience"
    guidance = inj._format_guidance(retrieved)
    guidance_start = len(task.question) + 2  # "\n\n" separator in PROMPT_TEMPLATE
    rebuilt = no_exp.last_prompt[:guidance_start] + guidance + no_exp.last_prompt[guidance_start:]
    assert d_inj == d_no, "injected draft body must equal baseline body (only prompt differs)"
    assert rebuilt == inj.last_prompt, "the only prompt difference must be the guidance block"
    assert guidance in inj.last_prompt, "experience text must be present in the injected prompt"

    # (b) three variants differ ------------------------------------------
    noisy = synthesize_experiences(events, mode="noisy", seed=7).records
    wrong = synthesize_experiences(events, mode="wrong", seed=7).records

    # Reproducibility: same inputs -> same outputs.
    again = synthesize_experiences(events, mode="noisy", seed=7).records
    assert tuple(noisy) == tuple(again), "synthesis must be reproducible for a fixed seed"

    clean_g = {r.technique + "|" + r.problem for r in clean}
    noisy_g = {r.technique + "|" + r.problem for r in noisy}
    wrong_g = {r.technique + "|" + r.problem for r in wrong}
    assert clean_g != noisy_g, "noisy variant must differ from clean"
    assert clean_g != wrong_g, "wrong variant must differ from clean"

    # Distinct noise markers present.
    all_tags = {tag for r in noisy for tag in r.tags}
    assert {VAGUE_TAG, CONFLICT_TAG, STALE_TAG} <= all_tags, (
        "noisy must carry vague/conflict/stale markers"
    )
    wrong_tags = {tag for r in wrong for tag in r.tags}
    assert WRONG_TAG in wrong_tags, "wrong variant must carry the wrong marker"

    # problem text originates from the payload, not hand-written prose.
    assert any(
        "contradicts the cited source" in r.problem for r in clean
    ), "problem must be extracted from the event payload"

    print(
        "self-test OK: agents share one path; clean/noisy/wrong variants differ and are "
        "reproducible"
    )


if __name__ == "__main__":
    _self_test()


# ---------------------------------------------------------------------------
# Live-model drafters (R006-P0, owner decision 2026-09-15: "接真实 LLM")
# ---------------------------------------------------------------------------
#
# The recorded drafter above replays the corpus case, which is what the existing
# mechanism benchmark wants and is precisely what P0 must not use: a drafter that
# ignores its prompt cannot show whether experience moves the output.  These
# classes put a real model behind the same ``BenchmarkAgent`` protocol.
#
# Both variants share one code path; the *only* difference is the guidance block
# handed to ``_render``.  Any other divergence (a different system prompt, a
# different retry policy, a different model) would put the treatment and the
# control on different code and destroy the comparison.

#: Content-free filler occupying a comparable amount of prompt as a real
#: guidance block, so the placeholder control isolates *content* from *length*.
PLACEHOLDER_LINE = "- (placeholder filler of matched length; carries no experience)\n"

DRAFT_SYSTEM = (
    "You draft one section of a research paper. "
    "Answer with the section body only, no preamble, no meta-commentary."
)


class LiveDraftError(RuntimeError):
    """The model could not be reached, or returned nothing usable.

    Raised rather than swallowed: a drafting step that silently produced an empty
    body would be scored as a hallucination-free draft and read as a *good*
    result, which is the "degrade a failure into a normal value" family this
    project keeps hitting.
    """


class _BaseLiveDraftAgent(_BaseExperienceDraftAgent):
    """Shared live path.  ``draft`` subclasses differ only in the guidance text.

    Subclasses the recorded-agent base rather than re-implementing it: that base
    already owns ``_render`` and ``_format_guidance``, and a second copy would be
    the "reimplemented instead of reused" pattern this project has been bitten by
    before -- two prompt templates that drift apart silently.
    """

    name: str = "base-live-agent"

    def __init__(self, *, llm: Any, retriever: SimpleExperienceRetriever | None = None) -> None:
        super().__init__(retriever=retriever)
        self._llm = llm
        self.calls: int = 0

    def _guidance(self, task: BenchmarkTask) -> str:
        if self._retriever is None:
            return ""
        return self._format_guidance(self._retriever.retrieve(task))

    def draft(self, task: BenchmarkTask) -> AgentDraft:
        prompt = self._render(task, self._guidance(task))
        self.last_prompt = prompt
        result = self._llm.complete(system=DRAFT_SYSTEM, user=prompt, temperature=0.0)
        if result is None:
            raise LiveDraftError(
                "the LLM boundary is unavailable (no endpoint/model/credential); "
                "refusing to draft rather than score an empty body"
            )
        self.calls += 1
        body = (result.text or "").strip()
        if not body:
            raise LiveDraftError("the model returned an empty draft body")
        # The corpus case owns the claims and their bindings; the model writes
        # prose.  Keeping the binding fixed means hallucination_ratio measures
        # what the *prompt* did to the draft, not whether the model happened to
        # invent a citation.
        return AgentDraft(
            body=body,
            title=task.title,
            claims=task.claims,
            claim_evidence_map=task.claim_evidence_map,
        )


class LiveNoExperienceAgent(_BaseLiveDraftAgent, BenchmarkAgent):
    """Control: a real model, no experience block."""

    name = "live-no-experience-agent"


class LiveExperienceAgent(_BaseLiveDraftAgent, BenchmarkAgent):
    """Treatment: a real model, experience block appended."""

    name = "live-experience-agent"

    def __init__(self, experiences: Sequence[ExperienceRecord], *, llm: Any, top_k: int = 5):
        super().__init__(llm=llm, retriever=SimpleExperienceRetriever(experiences, top_k=top_k))


class LivePlaceholderAgent(_BaseLiveDraftAgent, BenchmarkAgent):
    """Control: a real model, a guidance block of *matched size* but no content.

    Without this, ``live-experience`` vs ``live-no-experience`` confounds "the
    experience text" with "the prompt got longer" (REVIEW.md B2).

    Matching by *character count*, not by record count: the first version filled
    one short line per record, which produced a 388-character block against the
    real 660-character one -- a 0.59 ratio that leaves most of the length
    difference in place and therefore most of the confound.
    """

    name = "live-placeholder-agent"

    def __init__(self, *, llm: Any, target_chars: int) -> None:
        super().__init__(llm=llm, retriever=None)
        self._target_chars = target_chars

    def _guidance(self, task: BenchmarkTask) -> str:
        return GUIDANCE_HEADER + _filler_of(self._target_chars) + "\n"


def _filler_of(target_chars: int) -> str:
    """Filler text whose *rendered length* matches ``target_chars``.

    Sized by construction rather than by a line count, because the point of the
    control is that the prompt grows by the same amount with and without real
    experience.
    """

    if target_chars <= 0:
        return ""
    unit = "- filler line of matched length.\n"
    line = unit * (target_chars // len(unit))
    remainder = target_chars - len(line)
    if remainder:
        line += "-" * (remainder - 1) + "\n"
    return line
