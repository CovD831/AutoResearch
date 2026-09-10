"""O12 ProviderLane — S1.5 三路 parity 骨架（mock / replay / real）.

- mock:  内存假 payload → 用快照价格复算 cost（计价链贯通性）
- replay: 回放 fixture（录制过的真实响应形状）→ 与 mock 同一断言
- real:  真实 provider 调用 —— 段 3（S3.1）实现；默认 skip，
  设 ``AUTORESEARCH_LANE_REAL=1`` 才运行（成本入 receipt，ADR-01 §1.1 第 2 条）。

段 2 的 LaneTransport 落地后，mock/replay 两路改经 transport 断言完整链路
（payload → usage 归一化 → cost → LaneResult）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autoresearch.provider_lane import (
    Usage,
    build_preset_lane,
    calculate_cost,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "provider_lane"


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


def test_mock_parity_cost_pipeline(deepseek_lane, replay_usage: Usage) -> None:
    """mock 路：任何 usage 进计价器 → 与手算一致，且 total = 四项和。"""
    cost = calculate_cost(replay_usage, deepseek_lane.cost)
    expected = (
        deepseek_lane.cost.input / 1_000_000 * replay_usage.input_tokens
        + deepseek_lane.cost.output / 1_000_000 * replay_usage.output_tokens
        + deepseek_lane.cost.cache_read / 1_000_000 * replay_usage.cache_read_tokens
    )
    assert cost.total == pytest.approx(expected)
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


@pytest.mark.skipif(
    not __import__("os").environ.get("AUTORESEARCH_LANE_REAL"),
    reason="real API parity runs only with AUTORESEARCH_LANE_REAL=1 (段 3, S3.1)",
)
def test_real_parity_deepseek_vs_openai(deepseek_lane) -> None:
    """段 3 占位：真实双 provider parity（同 prompt 双 lane，cost 对照官方价目表）。"""
    raise NotImplementedError("S3.1 实现双 provider 真实 parity")
