#!/usr/bin/env python3
"""O12 S3.1 — real provider parity (explicit network run, never a unit test).

Runs one live ``chat.completions`` call per target model through the real
``LaneTransport`` and reports the collected usage and price, so the cost chain
can be checked against a hand computation (rate/1e6 x tokens).

Credentials come from the WorkBuddy custom-model endpoint configured in
``~/.workbuddy/models.json``; nothing here is read from, or written to, the
repository. Use ``--record`` to refresh the replay fixture used by the offline
parity test.

Usage:
    python scripts/parity_real_lane.py                 # call + report
    python scripts/parity_real_lane.py --record        # call + write fixture
    python scripts/parity_real_lane.py --model glm-5.3 # narrow the target
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoresearch.provider_lane import (  # noqa: E402
    LaneIdentity,
    LaneRequest,
    LaneResult,
    LaneTransport,
    ModelCatalog,
    ModelCost,
    ProviderLaneError,
    load_default_catalog,
    receipt_usage_fields,
)

MODELS_JSON = Path.home() / ".workbuddy" / "models.json"
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "provider_lane"
DEFAULT_TARGETS = ("deepseek-v4-pro", "glm-5.3")
PROMPT = "Reply with exactly this token and nothing else: PONG"


def _int(value: object) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _catalog_cost(catalog: ModelCatalog, model_id: str) -> ModelCost | None:
    """Reuse the vendored price when the served model id has a catalog entry."""

    for provider in ("deepseek", "openai", "anthropic", "alibaba", "moonshotai"):
        try:
            model = catalog.get_model(provider, model_id)
        except ProviderLaneError:
            continue
        return ModelCost.from_dict(model["cost"])
    return None


def build_lane(entry: dict, catalog: ModelCatalog) -> LaneIdentity:
    model_id = str(entry["id"])
    cost = _catalog_cost(catalog, model_id)
    return LaneIdentity(
        lane_id=f"workbuddy:{model_id}:v1",
        provider="workbuddy",
        endpoint=str(entry["url"]),
        model=model_id,
        api_family="openai-completions",
        # Priced from the vendored catalog when available; otherwise unpriced
        # (cost stays 0 and is reported as such, never invented).
        cost=cost or ModelCost(input=0.0, output=0.0),
        context_window=_int(entry.get("maxInputTokens")),
        max_output_tokens=_int(entry.get("maxOutputTokens")),
        reasoning_supported=bool(entry.get("supportsReasoning")),
        credential_env_names=("AUTORESEARCH_LLM_API_KEY", "LLM_API_KEY"),
        thinking_format="openai" if entry.get("supportsReasoning") else None,
    )


def run_one(entry: dict, catalog: ModelCatalog) -> dict:
    lane = build_lane(entry, catalog)
    transport = LaneTransport(lane, credential=str(entry["apiKey"]), timeout_seconds=90.0)
    result: LaneResult = transport.complete(
        LaneRequest(system="You are a terse assistant.", user=PROMPT, temperature=0.0)
    )
    fields = receipt_usage_fields(result)
    usage, cost = result.usage, result.usage_cost
    hand = (
        lane.cost.input / 1_000_000 * usage.input_tokens
        + lane.cost.output / 1_000_000 * usage.output_tokens
        + lane.cost.cache_read / 1_000_000 * usage.cache_read_tokens
        + lane.cost.cache_write / 1_000_000 * usage.cache_write_tokens
    )
    return {
        "lane_id": lane.lane_id,
        "model": result.model,
        "priced": lane.cost.input > 0 or lane.cost.output > 0,
        "text": result.text.strip(),
        "usage": fields["tokens"],
        "cost": fields["cost"],
        "cost_hand_check": hand,
        "cost_delta": abs(hand - cost.total),
    }


def write_fixture(entry: dict, report: dict) -> Path:
    """Record the live response shape as an offline replay fixture (key-free)."""

    path = FIXTURE_DIR / f"replay_workbuddy_{entry['id'].replace('.', '_')}.json"
    fixture = {
        "_provenance": {
            "lane_id": report["lane_id"],
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "endpoint_host": str(entry["url"]).split("//")[-1].split("/")[0],
            "note": (
                "Live WorkBuddy custom-model response captured by "
                "scripts/parity_real_lane.py. Credentials are never stored."
            ),
        },
        "model": report["model"],
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": report["text"]},
             "finish_reason": "stop"}
        ],
        "usage": {
            "prompt_tokens": report["usage"]["input"] + report["usage"]["cache_read"],
            "completion_tokens": report["usage"]["output"],
            "total_tokens": (
                report["usage"]["input"] + report["usage"]["cache_read"] + report["usage"]["output"]
            ),
        },
    }
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", default=None, help="target model id")
    parser.add_argument("--record", action="store_true", help="write replay fixtures")
    args = parser.parse_args()

    if not MODELS_JSON.exists():
        print(f"missing {MODELS_JSON}", file=sys.stderr)
        return 2

    entries = json.loads(MODELS_JSON.read_text(encoding="utf-8"))
    by_id = {str(e.get("id")): e for e in entries}
    targets = args.model or list(DEFAULT_TARGETS)
    catalog = load_default_catalog()

    reports = []
    for model_id in targets:
        entry = by_id.get(model_id)
        if entry is None:
            print(f"skip {model_id}: not configured in {MODELS_JSON}", file=sys.stderr)
            continue
        report = run_one(entry, catalog)
        reports.append(report)
        marker = "priced" if report["priced"] else "UNPRICED (no catalog entry)"
        print(f"[{model_id}] {marker} usage={report['usage']} cost_total={report['cost']['total']:.8f}")
        if args.record:
            print("  fixture:", write_fixture(entry, report))
        if report["priced"] and report["cost_delta"] > 1e-12:
            print("  WARNING: cost chain disagrees with hand computation", file=sys.stderr)

    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
