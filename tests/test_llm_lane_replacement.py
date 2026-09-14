"""S2.6: LLMService keeps its public surface while dispatching through a lane.

Offline: the lane transport is replaced by a canned fake, so no key and no
network are needed. These tests pin what S2.6 promised -- the signature is
unchanged, the internals really are the O12 lane, and lane resolution is robust
to endpoint spelling instead of silently zeroing the price.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from pydantic import SecretStr

from autoresearch.config import Settings
from autoresearch.llm import LLMService, lane_from_settings
from autoresearch.provider_lane import (
    LaneNotConfiguredError,
    LaneRequest,
    LaneResult,
    ModelCost,
    ProviderLaneError,
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
    # Unpriced is ``None``, not a zero-rate table: a $0.00 model would price real
    # calls as free (D-O12-14). ``cost`` and ``price_source`` move together.
    assert lane.cost is None
    assert lane.price_source is None
    assert lane.api_family == "openai-completions"


def test_unpriced_lane_still_carries_a_volume_budget() -> None:
    """Regression for P1-1: the custom-provider path must not ship an empty budget.

    The six preset lanes having caps is not the same as every reachable lane
    having one. A ``base_url`` matching no preset lands on the settings-derived
    lane, which used to build ``LaneBudgetProfile()`` -- three ``None`` caps, i.e.
    no budget at all, so a caller could make unbounded calls.
    """

    lane = lane_from_settings(CUSTOM_SETTINGS)

    assert lane.budget_profile.max_calls_per_run is not None
    assert lane.budget_profile.max_tokens_per_run is not None
    assert lane.budget_profile.max_calls_per_run == 240  # same rule as the presets


def test_unpriced_lane_leaves_only_the_dollar_cap_unset() -> None:
    """An unpriced model cannot be bounded in dollars -- say so, do not fake a 0.

    Deriving a cost cap from a price that does not exist would either reject real
    work (deriving 0) or protect nothing. The documented trade-off is: volume is
    bounded, dollars are not, and the caller can see that from ``None``.
    """

    lane = lane_from_settings(CUSTOM_SETTINGS)

    assert lane.cost is None
    assert lane.budget_profile.max_cost_per_call_usd is None
    # ...while the two derivable dimensions stay enforced.
    assert lane.budget_profile.max_calls_per_run == 240
    assert lane.budget_profile.max_tokens_per_run > 0


def test_unknown_model_stays_unpriced() -> None:
    """Honest negative: an unknown model is never assigned an invented rate."""

    lane = lane_from_settings(_settings("https://api.deepseek.com", "no-such-model"))

    assert lane.cost is None
    assert lane.price_source is None


def test_lane_identity_rejects_half_priced_state() -> None:
    """``cost``/``price_source`` are two views of one fact and cannot disagree."""

    lane = lane_from_settings(CUSTOM_SETTINGS)
    with pytest.raises(ProviderLaneError):
        replace(lane, cost=ModelCost(input=1.0, output=1.0))  # price_source stays None
    with pytest.raises(ProviderLaneError):
        replace(lane, price_source="dangling")  # cost stays None


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


def test_empty_key_fails_closed_instead_of_sending_a_blank_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adversarial finding F3: an all-whitespace key is 'not configured', so the
    request must fail fast locally rather than ship an empty Authorization header.

    The credential whitelist falls back to the process environment, so the env
    vars must be cleared for this test to be self-contained — otherwise a shell
    that exports DEEPSEEK_API_KEY makes this locally green (or red) for a reason
    that has nothing to do with the behaviour under test.
    """

    monkeypatch.delenv("AUTORESEARCH_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    service = LLMService(_settings("https://api.deepseek.com", "deepseek-v4-flash"))
    service.settings = service.settings.model_copy(update={"llm_api_key": SecretStr("   ")})

    with pytest.raises(LaneNotConfiguredError):
        service._ensure_transport()


def test_blank_key_falls_back_to_the_credential_whitelist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of F3: a blank settings key must not be shipped as an empty
    Bearer, but the whitelisted environment variable still wins if it holds a real
    key. That fallback is the designed behaviour, not a leak."""

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    monkeypatch.delenv("AUTORESEARCH_DEEPSEEK_API_KEY", raising=False)

    service = LLMService(_settings("https://api.deepseek.com", "deepseek-v4-flash"))
    service.settings = service.settings.model_copy(update={"llm_api_key": SecretStr("   ")})

    transport = service._ensure_transport()

    assert transport.credential == "sk-from-env"


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
