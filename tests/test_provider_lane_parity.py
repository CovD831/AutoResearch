"""O12 ProviderLane — S1.5/S3.1 三路 parity（mock / replay / real）.

- mock:   内存假 usage → 快照价目复算（计价链贯通）
- replay: 回放 fixture（含 S3.1 真实录制）→ 与 mock 同一断言
- real:   真实 provider 调用（WorkBuddy 自定义端口）；设
  ``AUTORESEARCH_LANE_REAL=1`` 才运行（成本入 receipt，ADR-01 §1.1 第 2 条）。
  凭据从 ``~/.workbuddy/models.json`` 读取，永不入库。

诚实负结果：端点模型若不在 vendored catalog 中则 unpriced（cost=0），
不编造价目；real 用例对此显式断言。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from autoresearch.provider_lane import (
    LaneIdentity,
    LaneRequest,
    LaneTransport,
    ModelCost,
    ProviderLaneError,
    Usage,
    build_preset_lane,
    calculate_cost,
    load_default_catalog,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "provider_lane"
WORKBUDDY_MODELS = Path.home() / ".workbuddy" / "models.json"
REAL_ENABLED = bool(os.environ.get("AUTORESEARCH_LANE_REAL"))
PROMPT = "Reply with exactly this token and nothing else: PONG"


@pytest.fixture(scope="module")
def deepseek_lane():
    return build_preset_lane("deepseek:chat:v1")


# 录制形状：OpenAI-compatible chat.completions 响应中的 usage 块
# （段 2 transport 负责把 provider 原生 usage 归一化为 provider_lane.Usage）。
@pytest.fixture(scope="module")
def replay_usage() -> Usage:
    payload = json.loads((FIXTURES / "replay_deepseek_chat.json").read_text(encoding="utf-8"))
    usage = payload["usage"]
    return Usage(
        input_tokens=int(usage["prompt_tokens"]),
        output_tokens=int(usage["completion_tokens"]),
        cache_read_tokens=int(usage.get("prompt_cache_hit_tokens", 0)),
    )


def _hand_cost(lane: LaneIdentity, usage: Usage) -> float:
    cost = lane.cost
    return (
        cost.input / 1_000_000 * usage.input_tokens
        + cost.output / 1_000_000 * usage.output_tokens
        + cost.cache_read / 1_000_000 * usage.cache_read_tokens
        + cost.cache_write / 1_000_000 * usage.cache_write_tokens
    )


# ---------------------------------------------------------------------------
# mock / replay（离线）
# ---------------------------------------------------------------------------


def test_mock_parity_cost_pipeline(deepseek_lane, replay_usage: Usage) -> None:
    """mock 路：任何 usage 进计价器 → 与手算一致，且 total = 四项和。"""
    cost = calculate_cost(replay_usage, deepseek_lane.cost)
    assert cost.total == pytest.approx(_hand_cost(deepseek_lane, replay_usage))
    parts = cost.input + cost.output + cost.cache_read + cost.cache_write
    assert cost.total == pytest.approx(parts)


def test_replay_parity_matches_fixture_snapshot(deepseek_lane, replay_usage: Usage) -> None:
    """replay 路：同一 fixture 重复跑两次结果逐位一致（确定性，D-F8-01 同源要求）。"""
    first = calculate_cost(replay_usage, deepseek_lane.cost)
    second = calculate_cost(replay_usage, deepseek_lane.cost)
    assert first == second


def test_replay_fixture_provenance_recorded() -> None:
    payload = json.loads((FIXTURES / "replay_deepseek_chat.json").read_text(encoding="utf-8"))
    assert payload["_provenance"]["recorded_at"]
    assert payload["_provenance"]["lane_id"] == "deepseek:chat:v1"
    assert payload["model"] == "deepseek-v4-flash"


def test_replay_workbuddy_fixture_is_priced_from_the_catalog() -> None:
    """S3.1 录制：真实 usage 套 catalog 价目（deepseek-v4-pro），与手算逐位一致。"""
    payload = json.loads(
        (FIXTURES / "replay_workbuddy_deepseek-v4-pro.json").read_text(encoding="utf-8")
    )
    lane = build_preset_lane("deepseek:chat:v1", model_override="deepseek-v4-pro")
    usage = Usage(
        input_tokens=int(payload["usage"]["prompt_tokens"]),
        output_tokens=int(payload["usage"]["completion_tokens"]),
    )
    cost = calculate_cost(usage, lane.cost)

    assert cost.total == pytest.approx(_hand_cost(lane, usage))
    assert payload["_provenance"]["lane_id"] == "workbuddy:deepseek-v4-pro:v1"
    assert payload["_provenance"]["endpoint_host"] == "workbuddy2api.henryai.top"


# ---------------------------------------------------------------------------
# real（显式开启）
# ---------------------------------------------------------------------------


def _workbuddy_lane(model_id: str) -> tuple[LaneIdentity, str]:
    """Build a lane for a WorkBuddy model, priced from the catalog when possible."""

    if not WORKBUDDY_MODELS.exists():
        pytest.skip(f"{WORKBUDDY_MODELS} not available")
    entries = json.loads(WORKBUDDY_MODELS.read_text(encoding="utf-8"))
    entry = next((e for e in entries if str(e.get("id")) == model_id), None)
    if entry is None:
        pytest.skip(f"model {model_id} not configured in {WORKBUDDY_MODELS}")

    cost = None
    catalog = load_default_catalog()
    for provider in ("deepseek", "openai", "anthropic", "alibaba", "moonshotai"):
        try:
            cost = ModelCost.from_dict(catalog.get_model(provider, model_id)["cost"])
            break
        except ProviderLaneError:
            continue

    lane = LaneIdentity(
        lane_id=f"workbuddy:{model_id}:v1",
        provider="workbuddy",
        endpoint=str(entry["url"]),
        model=model_id,
        api_family="openai-completions",
        cost=cost or ModelCost(input=0.0, output=0.0),
        context_window=0,
        max_output_tokens=0,
        reasoning_supported=bool(entry.get("supportsReasoning")),
        credential_env_names=("AUTORESEARCH_LLM_API_KEY", "LLM_API_KEY"),
        thinking_format="openai" if entry.get("supportsReasoning") else None,
    )
    return lane, str(entry["apiKey"])


@pytest.mark.skipif(
    not REAL_ENABLED,
    reason="real API parity runs only with AUTORESEARCH_LANE_REAL=1 (段 3, S3.1)",
)
def test_real_parity_workbuddy_priced_lane() -> None:
    """真实调用：catalog 有价目的模型，计价链与手算一致（误差 0）。"""
    lane, credential = _workbuddy_lane("deepseek-v4-pro")
    assert lane.cost.input > 0

    result = LaneTransport(lane, credential=credential, timeout_seconds=90.0).complete(
        LaneRequest(system="You are a terse assistant.", user=PROMPT, temperature=0.0)
    )

    assert result.text.strip()
    assert result.usage.input_tokens > 0
    assert result.usage_cost.total == pytest.approx(_hand_cost(lane, result.usage))


@pytest.mark.skipif(
    not REAL_ENABLED,
    reason="real API parity runs only with AUTORESEARCH_LANE_REAL=1 (段 3, S3.1)",
)
def test_real_parity_workbuddy_unpriced_lane_stays_zero() -> None:
    """诚实负结果：端点模型无 catalog 条目 → 不计价，也不编造价目。"""
    lane, credential = _workbuddy_lane("glm-5.3")
    assert lane.cost.input == 0.0 and lane.cost.output == 0.0

    result = LaneTransport(lane, credential=credential, timeout_seconds=90.0).complete(
        LaneRequest(system="You are a terse assistant.", user=PROMPT, temperature=0.0)
    )

    assert result.usage.input_tokens > 0
    assert result.usage_cost.total == 0.0
