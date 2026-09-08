from __future__ import annotations

from autoresearch.contracts import InnovationCandidate, ReadingCard
from autoresearch.pipeline_contracts import BenchmarkPlan, SectionPlan


class BenchmarkAdvisor:
    def propose(
        self,
        plan: SectionPlan,
        cards: list[ReadingCard],
        *,
        innovations: list[InnovationCandidate] | None = None,
    ) -> BenchmarkPlan:
        baseline = list(
            dict.fromkeys(card.method.strip() for card in cards if card.method.strip())
        )[:2]

        metrics = ["evidence traceability", "benchmark comparability", "failure visibility"]
        if any("latency" in claim.lower() for claim in plan.claims):
            metrics.append("latency")
        if any("quality" in claim.lower() for claim in plan.claims):
            metrics.append("quality")

        required_materials = list(
            dict.fromkeys(
                [
                    "locators for cited reading cards",
                    "baseline definitions",
                    "metric definitions",
                    "planned-only result guard",
                ]
            )
        )
        if innovations:
            required_materials.extend(
                f"falsification check for {item.statement[:120]}" for item in innovations
            )

        risks = list(dict.fromkeys(plan.gaps or []))
        if not risks:
            risks = [
                "The benchmark must remain a plan until real execution evidence is registered."
            ]

        return BenchmarkPlan(
            project_id=plan.project_id,
            section_id=plan.plan_id,
            benchmark_name=f"{plan.section_name} benchmark plan",
            baseline=baseline,
            metrics=metrics,
            required_materials=required_materials,
            risks=risks[:5],
            planned_only=True,
        )
