"""P0 smoke run: three conditions on one case, to prove the live path works.

Runs *before* the full comparison so a broken wiring shows up in one case rather
than after hundreds of model calls.  Asserts the live drafter actually reaches the
model and returns distinct bodies for distinct prompts -- the same property the
discriminating-power self-check verifies with a stub, now verified end to end
against the real endpoint.
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, "src")

from autoresearch.config import Settings  # noqa: E402
from autoresearch.experience_injection import (  # noqa: E402
    LiveExperienceAgent,
    LiveNoExperienceAgent,
    LivePlaceholderAgent,
    sample_audit_events,
    synthesize_experiences,
)
from autoresearch.llm import LLMService  # noqa: E402
from test_benchmark_runtime import load_corpus  # noqa: E402


def main() -> int:
    settings = Settings(_env_file=".env")
    service = LLMService(settings)
    if not service.available:
        print("FAIL: the LLM boundary is not configured (.env)")
        return 1

    corpus = load_corpus("tests/fixtures/benchmark/corpus.json")
    task = corpus.case("case-001")
    print(f"case: {task.case_id}")
    print(f"question: {task.question[:90]}")
    print()

    result = synthesize_experiences(
        sample_audit_events(), mode="clean", seed=0, project_id="benchmark"
    )
    records = result.records if hasattr(result, "records") else result.experiences
    print(f"experience records: {len(records)}")

    reference = LiveExperienceAgent(records, llm=service)
    guidance_len = len(reference._format_guidance(records))
    print(f"real guidance block: {guidance_len} chars")

    agents = [
        ("off", LiveNoExperienceAgent(llm=service)),
        ("clean", reference),
        ("placeholder", LivePlaceholderAgent(llm=service, target_chars=guidance_len)),
    ]

    drafts = {}
    for name, agent in agents:
        start = time.time()
        try:
            draft = agent.draft(task)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
            return 1
        elapsed = time.time() - start
        drafts[name] = draft
        print(
            f"[ok] {name:11} {elapsed:5.2f}s  prompt={len(agent.last_prompt):5}  "
            f"body={len(draft.body):5}  head={draft.body[:60]!r}"
        )

    print()
    failures = []

    # The treatment must differ from both controls, otherwise the variable did not
    # reach the model's output.
    if drafts["clean"].body == drafts["off"].body:
        failures.append("clean produced the same body as off")
    if drafts["clean"].body == drafts["placeholder"].body:
        failures.append("clean produced the same body as placeholder")

    # Prompt sizes must be in the same ballpark, or the comparison measures length.
    len_off = len(agents[0][1].last_prompt)
    len_clean = len(agents[1][1].last_prompt)
    len_ph = len(agents[2][1].last_prompt)
    if len_clean == len_off:
        failures.append("clean prompt is identical in size to off (no injection happened)")
    ratio = len_ph / len_clean if len_clean else 0.0
    if not (0.7 <= ratio <= 1.4):
        failures.append(f"placeholder/clean prompt length ratio {ratio:.2f} is out of range")
    print(f"prompt lengths: off={len_off} clean={len_clean} placeholder={len_ph} (ratio {ratio:.2f})")

    print()
    if failures:
        print("smoke FAILED:")
        for item in failures:
            print("  -", item)
        return 1
    print("smoke OK: the live path reaches the model, and the three conditions "
          "produce distinct drafts at comparable prompt sizes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
