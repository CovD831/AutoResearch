"""S2.6: LLMService keeps its public surface while dispatching through a lane.

Offline: the lane transport is replaced by a canned fake, so no key and no
network are needed. These tests pin what S2.6 promised -- the signature is
unchanged, the internals really are the O12 lane, and lane resolution is robust
to endpoint spelling instead of silently zeroing the price.
"""

from __future__ import annotations

import json

import pytest
from pydantic import SecretStr

from autoresearch.config import Settings
from autoresearch.llm import LLMService, lane_from_settings
from autoresearch.provider_lane import (
    LaneNotConfiguredError,
    LaneRequest,
    LaneResult,
    ModelCost,
    Usage,
    calculate_cost,
)

DEEPSEEK_SETTINGS = Settings(
    llm_provider="deepseek",
    llm_api_key=SecretStr("sk-test"),
    llm_base_url="https://api.deepseek.com",
    llm_model="deepseek-v4-flash",
)

CUSTOM_SETTINGS = Settings(
    llm_provider="workbuddy",
    llm_api_key=SecretStr("sk-test"),
    llm_base_url="https://custom.example.invalid/v1",
    llm_model="custom-model",
)


def _settings(base_url: str | None, model: str, provider: str = "deepseek") -> Settings:
    return Settings(
        llm_provider=provider,
        llm_api_key=SecretStr("sk-test"),
        llm_base_url=base_url,
        llm_model=model,
    )


class FakeTransport:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[LaneRequest] = []

    def complete(self, request: LaneRequest) -> LaneResult:
        self.requests.append(request)
        usage = Usage(input_tokens=2000, output_tokens=200)
        return LaneResult(
            text=self.text,
            lane_id="deepseek:chat:v1",
            model="deepseek-v4-flash",
            usage=usage,
            usage_cost=calculate_cost(usage, ModelCost(input=0.28, output=0.42)),
            raw={"id": "chatcmpl-test", "usage": {"prompt_tokens": 2000}},
        )


# ---------------------------------------------------------------------------
# Lane resolution
# ---------------------------------------------------------------------------


def test_lane_from_settings_reuses_preset_catalog_pricing() -> None:
    lane = lane_from_settings(DEEPSEEK_SETTINGS)

    assert lane.lane_id == "deepseek:chat:v1"
    assert lane.model == "deepseek-v4-flash"
    # catalog pricing, not the zero-cost fallback
    assert lane.cost.input > 0
    assert lane.cost.output > 0


def test_lane_from_settings_tolerates_endpoint_spelling() -> None:
    """Adversarial finding F1: /v1 suffix, trailing slash and host case are
    spelling, not identity. Getting this wrong silently zeroes the price."""

    for base_url in (
        "https://api.deepseek.com",
        "https://api.deepseek.com/",
        "https://api.deepseek.com/v1",
        "https://API.DeepSeek.com",
    ):
        lane = lane_from_settings(_settings(base_url, "deepseek-v4-flash"))
        assert lane.lane_id == "deepseek:chat:v1", base_url
        assert lane.cost.input > 0, base_url


def test_pricing_survives_a_custom_endpoint_for_a_known_model() -> None:
    """A third-party endpoint serving a catalog model is still priced, not zeroed."""

    lane = lane_from_settings(CUSTOM_SETTINGS.model_copy(update={"llm_model": "deepseek-v4-pro"}))

    assert lane.lane_id == "workbuddy:settings:v1"
    assert lane.cost.input > 0  # resolved from the model id, not the endpoint
    assert lane.endpoint == "https://custom.example.invalid/v1"


def test_lane_from_settings_falls_back_to_unpriced_lane() -> None:
    lane = lane_from_settings(CUSTOM_SETTINGS)

    assert lane.lane_id == "workbuddy:settings:v1"
    assert lane.endpoint == "https://custom.example.invalid/v1"
    assert lane.cost.input == 0.0 and lane.cost.output == 0.0
    assert lane.api_family == "openai-completions"


def test_unknown_model_stays_unpriced() -> None:
    """Honest negative: an unknown model is never assigned an invented rate."""

    lane = lane_from_settings(_settings("https://api.deepseek.com", "no-such-model"))

    assert lane.cost.input == 0.0
    assert lane.cost.output == 0.0


def test_incomplete_settings_raise_a_recovery_hint() -> None:
    """Adversarial finding F2: fail closed with a hint, not a bare ValueError."""

    with pytest.raises(LaneNotConfiguredError) as excinfo:
        lane_from_settings(_settings(None, "deepseek-v4-flash"))

    assert excinfo.value.suggested_recovery


# ---------------------------------------------------------------------------
# Public surface unchanged
# ---------------------------------------------------------------------------


def test_offline_service_stays_unavailable_and_returns_none() -> None:
    service = LLMService(Settings())

    assert service.available is False
    assert service.complete(system="s", user="u") is None
    assert service.complete_json(system="s", user="u") is None


def test_empty_key_fails_closed_instead_of_sending_a_blank_bearer() -> None:
    """Adversarial finding F3: an all-whitespace key is 'not configured', so the
    request must fail fast locally rather than ship an empty Authorization header."""

    service = LLMService(_settings("https://api.deepseek.com", "deepseek-v4-flash"))
    service.settings = service.settings.model_copy(update={"llm_api_key": SecretStr("   ")})

    with pytest.raises(LaneNotConfiguredError):
        service._ensure_transport()


def test_complete_dispatches_through_the_lane_transport() -> None:
    service = LLMService(DEEPSEEK_SETTINGS)
    transport = FakeTransport("hello")
    service._transport = transport  # type: ignore[assignment]

    result = service.complete(system="sys", user="usr", temperature=0.1, json_mode=True)

    assert result is not None
    assert result.text == "hello"
    assert result.model == "deepseek-v4-flash"
    assert result.provider == "deepseek"
    # the request really went through LaneTransport, and json_mode is carried
    assert transport.requests[0].json_mode is True
    assert transport.requests[0].temperature == 0.1
    # priced usage travels with the result for receipt filling (S2.5)
    assert result.raw["cost"]["total"] > 0
    assert result.raw["tokens"]["input"] == 2000
    assert service.last_result is not None


def test_complete_json_parses_the_lane_text() -> None:
    service = LLMService(DEEPSEEK_SETTINGS)
    service._transport = FakeTransport(json.dumps({"search_queries": ["a", "b"]}))  # type: ignore[assignment]

    parsed = service.complete_json(system="s", user="u")

    assert parsed == {"search_queries": ["a", "b"]}
