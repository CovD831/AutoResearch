"""Refresh the vendored model catalog snapshot from models.dev.

Explicit-network script (ADR-01 §1.1: 内置默认栈 0 付费；本脚本仅由维护者手工运行).
Source data: https://models.dev/api.json — MIT licensed
(https://github.com/anomalyco/models.dev, maintained by the SST team).
The vendored snapshot is a *filtered* subset: only the provider families that
map to AutoResearch preset lanes, only models with known pricing and a
non-zero context window.

Usage:
    PYTHONPATH=src python scripts/refresh_model_catalog.py

Output: src/autoresearch/data/models_catalog.json
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://models.dev/api.json"
REPO_URL = "https://github.com/anomalyco/models.dev"

# provider id on models.dev -> our api family (transport族)
TARGET_PROVIDERS: dict[str, str] = {
    "deepseek": "openai-completions",
    "openai": "openai-completions",
    "moonshotai": "openai-completions",  # Kimi
    "alibaba": "openai-completions",  # Qwen / DashScope compatible-mode
    "anthropic": "anthropic-messages",  # transport 二期（catalog 先行）
}


def fetch_raw() -> dict:
    req = urllib.request.Request(
        API_URL, headers={"User-Agent": "autoresearch-catalog-sync/1.0"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (fixed https URL)
        return json.load(resp)


def filter_provider(provider_id: str, entry: dict) -> dict | None:
    models_out: dict[str, dict] = {}
    for model_id, model in sorted((entry.get("models") or {}).items()):
        cost = model.get("cost")
        limit = model.get("limit") or {}
        context = int(limit.get("context") or 0)
        if not isinstance(cost, dict) or context <= 0:
            continue
        # models.dev may expose cost.reasoning; pi-ai semantics treat reasoning
        # tokens as a subset of output (billed at the output rate) — keep the
        # four canonical tiers only.
        models_out[model_id] = {
            "id": model.get("id", model_id),
            "name": model.get("name", model_id),
            "reasoning": bool(model.get("reasoning", False)),
            "tool_call": bool(model.get("tool_call", False)),
            "cost": {
                "input": float(cost.get("input") or 0.0),
                "output": float(cost.get("output") or 0.0),
                "cache_read": float(cost.get("cache_read") or 0.0),
                "cache_write": float(cost.get("cache_write") or 0.0),
            },
            "limit": {"context": context, "output": int(limit.get("output") or 0)},
            "api_family": TARGET_PROVIDERS[provider_id],
        }
    if not models_out:
        return None
    return {
        "id": provider_id,
        "name": entry.get("name", provider_id),
        "api_family": TARGET_PROVIDERS[provider_id],
        "env_keys_hint": list(entry.get("envKeys") or []),
        "models": models_out,
    }


def main() -> int:
    raw = fetch_raw()
    providers_out: dict[str, dict] = {}
    for provider_id in sorted(TARGET_PROVIDERS):
        entry = raw.get(provider_id)
        if entry is None:
            print(f"warn: provider {provider_id} missing upstream", file=sys.stderr)
            continue
        filtered = filter_provider(provider_id, entry)
        if filtered is not None:
            providers_out[provider_id] = filtered

    # Hand-maintained local lane (vLLM / self-hosted OpenAI-compatible).
    # Pricing is zero by definition (self-hosted); model list is a template
    # that operators extend in their own deployment.
    providers_out["vllm-local"] = {
        "id": "vllm-local",
        "name": "Local vLLM (self-hosted, user-configured)",
        "api_family": "openai-completions",
        "env_keys_hint": [],
        "user_configurable": True,
        "models": {
            "local-model": {
                "id": "local-model",
                "name": "User-deployed model (template entry, zero cost)",
                "reasoning": False,
                "tool_call": True,
                "cost": {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0},
                "limit": {"context": 0, "output": 0},  # 0 = query at runtime
                "api_family": "openai-completions",
            }
        },
    }

    snapshot = {
        "_meta": {
            "source": API_URL,
            "repo": REPO_URL,
            "license": "MIT",
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "upstream_providers": len(raw),
            "filter": (
                "providers="
                + ",".join(sorted(TARGET_PROVIDERS))
                + "+vllm-local(hand-maintained); models with non-null cost and "
                "context>0; four canonical cost tiers (reasoning billed as output)"
            ),
            "generated_by": "scripts/refresh_model_catalog.py",
        },
        "providers": providers_out,
    }

    out_path = Path(__file__).resolve().parent.parent / "src" / "autoresearch" / "data" / "models_catalog.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    total_models = sum(len(p["models"]) for p in providers_out.values())
    print(f"written {out_path}")
    print(f"providers={len(providers_out)} models={total_models} size={out_path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
