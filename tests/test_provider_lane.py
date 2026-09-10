"""O12 ProviderLane — S1 结构/校验/计价/凭据/漂移/预算/anthropic 档位测试."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from autoresearch.provider_lane import (
    PRESET_LANE_IDS,
    CostTier,
    LaneBudgetExceededError,
    LaneBudgetProfile,
    LaneCatalogError,
    LaneDriftError,
    LaneIdentity,
    LaneNotConfiguredError,
    ModelCatalog,
    ModelCost,
    ProviderLaneError,
    Usage,
    anthropic_thinking_params,
    build_preset_lane,
    calculate_cost,
    check_call_budget,
    credential_from_env,
    lane_drift_event,
    load_default_catalog,
    require_credential,
    selftest_catalog,
    validate_lane_settings,
)


@pytest.fixture(scope="module")
def catalog() -> ModelCatalog:
    return load_default_catalog()


def _observed(lane: LaneIdentity) -> dict:
    """Full observed-settings projection (drift test baseline)."""
    return {
        "provider": lane.provider,
        "endpoint": lane.endpoint,
        "model": lane.model,
        "api_family": lane.api_family,
        "max_rounds": lane.max_rounds,
        "credential_env_names": list(lane.credential_env_names),
        "reasoning_supported": lane.reasoning_supported,
        "max_cost_per_call_usd": lane.budget_profile.max_cost_per_call_usd,
        "max_calls_per_run": lane.budget_profile.max_calls_per_run,
        "max_tokens_per_run": lane.budget_profile.max_tokens_per_run,
    }


# --------------------------------------------------------------------------
# S1.1 catalog + preset lanes
# --------------------------------------------------------------------------


def test_catalog_provenance_records_mit_and_source(catalog: ModelCatalog) -> None:
    assert catalog._meta["license"] == "MIT"
    assert "models.dev" in catalog._meta["source"]
    assert catalog._meta["fetched_at"]


def test_selftest_catalog_instantiates_six_lanes() -> None:
    lines = selftest_catalog()
    assert len(lines) == len(PRESET_LANE_IDS) == 6
    assert all(line.startswith("OK ") for line in lines)


@pytest.mark.parametrize("lane_id", PRESET_LANE_IDS)
def test_preset_lanes_instantiate_offline(lane_id: str, catalog: ModelCatalog) -> None:
    lane = build_preset_lane(lane_id, catalog=catalog)
    assert lane.lane_id == lane_id
    assert lane.endpoint.startswith("http")
    assert lane.cost.input >= 0 and lane.cost.output >= 0


def test_unknown_preset_lane_raises_catalog_error() -> None:
    with pytest.raises(LaneCatalogError):
        build_preset_lane("nope:never:v1")


# --------------------------------------------------------------------------
# S1.2 identity structure & validation
# --------------------------------------------------------------------------


def test_lane_identity_is_frozen() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    with pytest.raises(FrozenInstanceError):
        lane.model = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda ln: replace(ln, lane_id="  "),
        lambda ln: replace(ln, endpoint=""),
        lambda ln: replace(ln, model=" "),
        lambda ln: replace(ln, provider=""),
        lambda ln: replace(ln, api_family="grpc"),
        lambda ln: replace(ln, max_rounds=0),
        lambda ln: replace(ln, context_window=-1),
    ],
)
def test_lane_identity_validation_failures(mutate) -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    with pytest.raises(ProviderLaneError):
        mutate(lane)


def test_lane_identity_credential_scope_required_for_non_local() -> None:
    with pytest.raises(ProviderLaneError):
        LaneIdentity(
            lane_id="x:chat:v1",
            provider="deepseek",
            endpoint="https://api.deepseek.com",
            model="deepseek-v4-flash",
            api_family="openai-completions",
            cost=ModelCost(input=0.14, output=0.28),
            context_window=1000,
            max_output_tokens=1000,
            reasoning_supported=True,
            credential_env_names=(),
        )


def test_local_endpoint_lane_may_have_empty_scope() -> None:
    lane = build_preset_lane("vllm:local:v1")
    assert lane.budget_profile.local_endpoint is True
    assert lane.credential_env_names == ()


# --------------------------------------------------------------------------
# S1.3 cost calculator（pi-ai calculateCost 语义）
# --------------------------------------------------------------------------


def test_cost_flat_pricing_matches_hand_computation() -> None:
    # deepseek-v4-flash: input=$0.14/1M, output=$0.28/1M (models.dev snapshot)
    lane = build_preset_lane("deepseek:chat:v1")
    cost = calculate_cost(Usage(input_tokens=1_000_000, output_tokens=500_000), lane.cost)
    assert cost.input == pytest.approx(0.14)
    assert cost.output == pytest.approx(0.14)
    assert cost.total == pytest.approx(0.28)


def test_cost_reasoning_tokens_not_double_counted() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    base = Usage(input_tokens=0, output_tokens=100)
    with_reasoning = Usage(input_tokens=0, output_tokens=100, reasoning_tokens=40)
    assert calculate_cost(base, lane.cost) == calculate_cost(with_reasoning, lane.cost)


def test_cost_cache_tiers_priced_separately() -> None:
    # anthropic claude-sonnet-4-5: input=3? cache_read/cache_write from snapshot
    lane = build_preset_lane("anthropic:messages:v1")
    cost = calculate_cost(
        Usage(
            input_tokens=1_000_000,
            output_tokens=0,
            cache_read_tokens=1_000_000,
            cache_write_tokens=1_000_000,
        ),
        lane.cost,
    )
    assert cost.input == pytest.approx(lane.cost.input)
    assert cost.cache_read == pytest.approx(lane.cost.cache_read)
    assert cost.cache_write == pytest.approx(lane.cost.cache_write)
    expected_total = lane.cost.input + lane.cost.cache_read + lane.cost.cache_write
    assert cost.total == pytest.approx(expected_total)


def test_cost_tier_selection_highest_threshold_reached_wins() -> None:
    cost = ModelCost(
        input=1.0,
        output=2.0,
        tiers=(CostTier(input_tokens_above=1_000_000, input=0.4, output=1.0),),
    )
    below = calculate_cost(Usage(input_tokens=100_000, output_tokens=0), cost)
    at_threshold = calculate_cost(Usage(input_tokens=1_000_000, output_tokens=0), cost)
    assert below.input == pytest.approx(0.1)  # base rate $1.0/1M
    assert at_threshold.input == pytest.approx(0.4)  # tier rate $0.4/1M


def test_cost_zero_for_local_vllm_lane() -> None:
    lane = build_preset_lane("vllm:local:v1")
    cost = calculate_cost(Usage(input_tokens=10_000, output_tokens=2_000), lane.cost)
    assert cost.total == 0.0


def test_negative_usage_rejected() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    with pytest.raises(ProviderLaneError):
        calculate_cost(Usage(input_tokens=-1, output_tokens=0), lane.cost)


# --------------------------------------------------------------------------
# S1.4 credential whitelist
# --------------------------------------------------------------------------


def test_credential_whitelist_respects_order() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    env = {"DEEPSEEK_API_KEY": "second", "AUTORESEARCH_DEEPSEEK_API_KEY": "first"}
    assert credential_from_env(lane, env) == "first"


def test_credential_ignores_names_outside_scope() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    assert credential_from_env(lane, {"OPENAI_API_KEY": "stray"}) is None


def test_require_credential_missing_fails_closed() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    with pytest.raises(LaneNotConfiguredError) as excinfo:
        require_credential(lane, {})
    assert "AUTORESEARCH_DEEPSEEK_API_KEY" in str(excinfo.value)


def test_require_credential_local_endpoint_exempt() -> None:
    lane = build_preset_lane("vllm:local:v1")
    assert require_credential(lane, {}) == ""


# --------------------------------------------------------------------------
# S1.4 drift guard（7 项篡改全部被拒）
# --------------------------------------------------------------------------


def test_drift_accepts_matching_settings() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    validate_lane_settings(lane, _observed(lane))


@pytest.mark.parametrize(
    "field",
    [
        "provider",
        "endpoint",
        "model",
        "api_family",
        "max_rounds",
        "max_cost_per_call_usd",
        "credential_env_names",
    ],
)
def test_drift_rejects_each_tampered_field(field: str) -> None:
    lane = build_preset_lane(
        "deepseek:chat:v1",
        budget_profile=LaneBudgetProfile(max_cost_per_call_usd=0.5),
    )
    observed = _observed(lane)
    if field == "endpoint":
        observed[field] = "https://evil.example.com/v1"
    elif field == "credential_env_names":
        observed[field] = ["EVIL_API_KEY"]
    elif field.startswith("max_"):
        observed[field] = 999999.0 if field.endswith("usd") else 999999
    else:
        observed[field] = "tampered" if isinstance(observed[field], str) else 999
    with pytest.raises(LaneDriftError) as excinfo:
        validate_lane_settings(lane, observed)
    assert field in str(excinfo.value)


def test_drift_endpoint_trailing_slash_tolerated() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    observed = _observed(lane)
    observed["endpoint"] = lane.endpoint.rstrip("/") + "///"
    validate_lane_settings(lane, observed)


def test_lane_drift_event_only_on_drift() -> None:
    """PLAN §5 requires a ``provider.lane_drift`` audit event on drift."""

    lane = build_preset_lane("deepseek:chat:v1")
    assert lane_drift_event(lane, _observed(lane)) is None

    observed = _observed(lane)
    observed["endpoint"] = "https://evil.example.com/v1"
    event = lane_drift_event(lane, observed)

    assert event is not None
    assert event["event"] == "provider.lane_drift"
    assert event["lane_id"] == lane.lane_id
    assert event["model"] == lane.model
    assert "endpoint" in event["detail"]


# --------------------------------------------------------------------------
# S1.4 budget guard
# --------------------------------------------------------------------------


def test_budget_per_call_cap_enforced() -> None:
    lane = build_preset_lane(
        "deepseek:chat:v1", budget_profile=LaneBudgetProfile(max_cost_per_call_usd=0.01)
    )
    with pytest.raises(LaneBudgetExceededError):
        check_call_budget(lane, estimated_cost_usd=0.02)
    check_call_budget(lane, estimated_cost_usd=0.005)


def test_budget_run_caps_enforced() -> None:
    lane = build_preset_lane(
        "deepseek:chat:v1",
        budget_profile=LaneBudgetProfile(max_calls_per_run=2, max_tokens_per_run=1000),
    )
    with pytest.raises(LaneBudgetExceededError):
        check_call_budget(lane, calls_used=2)
    with pytest.raises(LaneBudgetExceededError):
        check_call_budget(lane, estimated_tokens=1500)
    check_call_budget(lane, calls_used=1, estimated_tokens=999)


# --------------------------------------------------------------------------
# §4.4 anthropic thinking（两代规格）
# --------------------------------------------------------------------------


def test_anthropic_off_returns_none() -> None:
    assert anthropic_thinking_params("off", adaptive=True) is None
    assert anthropic_thinking_params("off", adaptive=False, max_output_tokens=8192) is None


def test_anthropic_manual_budget_clamped_under_max_output() -> None:
    params = anthropic_thinking_params("high", adaptive=False, max_output_tokens=8192)
    assert params == {"thinking": {"type": "enabled", "budget_tokens": 8191}}


def test_anthropic_manual_budget_floor_1024() -> None:
    params = anthropic_thinking_params("minimal", adaptive=False, max_output_tokens=1100)
    assert params == {"thinking": {"type": "enabled", "budget_tokens": 1024}}


def test_anthropic_manual_budget_below_floor_raises() -> None:
    with pytest.raises(ProviderLaneError):
        anthropic_thinking_params("minimal", adaptive=False, max_output_tokens=1024)


def test_anthropic_adaptive_effort_clamps_xhigh_and_max() -> None:
    xhigh = anthropic_thinking_params("xhigh", adaptive=True)
    top = anthropic_thinking_params("max", adaptive=True)
    medium = anthropic_thinking_params("medium", adaptive=True)
    assert xhigh == {"output_config": {"effort": "high"}}
    assert top == {"output_config": {"effort": "high"}}
    assert medium == {"output_config": {"effort": "medium"}}


def test_anthropic_unknown_level_rejected() -> None:
    with pytest.raises(ProviderLaneError):
        anthropic_thinking_params("ultra", adaptive=True)  # type: ignore[arg-type]
