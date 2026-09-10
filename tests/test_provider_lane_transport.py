"""O12 ProviderLane — S2.2–S2.4 transport/payload/usage/retry/handoff/sampling 测试."""

from __future__ import annotations

import httpx
import pytest

from autoresearch.provider_lane import (
    LaneBudgetExceededError,
    LaneBudgetProfile,
    LaneRequest,
    LaneStrictError,
    LaneTransport,
    LaneTransportError,
    ProviderLaneError,
    RetryPolicy,
    build_openai_completions_payload,
    build_preset_lane,
    convert_thinking_for_cross_model,
    degrade_images_for_non_vision,
    make_strict_json_schema,
    normalize_tool_call_id,
    normalize_usage_openai,
    receipt_usage_fields,
    resolve_response_format,
    synthesize_orphan_tool_results,
)


class FakeResponse:
    def __init__(self, status_code: int, data: dict) -> None:
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self) -> dict:
        return self._data


class FakeClient:
    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, headers=None, json=None):  # noqa: A002
        self.calls.append({"url": url, "headers": headers, "json": json})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _completion_payload(text: str = "ok", usage: dict | None = None) -> dict:
    return {
        "id": "chatcmpl-fixture",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
        "usage": usage or {"prompt_tokens": 1000, "completion_tokens": 100},
    }


# --------------------------------------------------------------------------
# S2.3 payload builders + reasoning 档位映射
# --------------------------------------------------------------------------


def test_openai_lane_maps_effort_and_clamps_xhigh() -> None:
    # gpt-4o-mini 非推理模型；推理档位用 gpt-5（快照 reasoning=True）
    lane = build_preset_lane("openai:chat:v1", model_override="gpt-5")
    payload = build_openai_completions_payload(
        lane, LaneRequest(system="s", user="u", reasoning_level="xhigh")
    )
    assert payload["reasoning_effort"] == "high"
    assert payload["model"] == "gpt-5"


def test_deepseek_lane_uses_thinking_block() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    payload = build_openai_completions_payload(
        lane, LaneRequest(system="s", user="u", reasoning_level="medium")
    )
    assert payload["thinking"] == {"type": "enabled", "effort": "medium"}


def test_reasoning_off_omits_thinking_keys() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    payload = build_openai_completions_payload(
        lane, LaneRequest(system="s", user="u", reasoning_level="off")
    )
    assert "thinking" not in payload
    assert "reasoning_effort" not in payload


def test_lane_without_reasoning_mapping_fails_fast() -> None:
    lane = build_preset_lane("qwen:chat:v1")  # thinking_format=None（首版）
    with pytest.raises(ProviderLaneError):
        build_openai_completions_payload(
            lane, LaneRequest(system="s", user="u", reasoning_level="high")
        )


def test_model_without_reasoning_support_fails_fast() -> None:
    lane = build_preset_lane("vllm:local:v1")  # reasoning_supported=False
    with pytest.raises(ProviderLaneError):
        build_openai_completions_payload(
            lane, LaneRequest(system="s", user="u", reasoning_level="low")
        )


# --------------------------------------------------------------------------
# S2.4 strict json schema 三规则 + 降级矩阵
# --------------------------------------------------------------------------


def test_strict_schema_injects_additional_properties_false_and_required() -> None:
    strict = make_strict_json_schema(
        {"type": "object", "properties": {"b": {"type": "string"}, "a": {"type": "integer"}}}
    )
    assert strict["additionalProperties"] is False
    assert strict["required"] == ["a", "b"]


def test_strict_schema_nullable_becomes_any_of() -> None:
    strict = make_strict_json_schema(
        {"type": "object", "properties": {"note": {"type": ["string", "null"]}}}
    )
    assert strict["properties"]["note"]["anyOf"] == [{"type": "string"}, {"type": "null"}]


def test_strict_schema_walks_nested_objects() -> None:
    strict = make_strict_json_schema(
        {
            "type": "object",
            "properties": {
                "inner": {"type": "object", "properties": {"x": {"type": "number"}}}
            },
        }
    )
    inner = strict["properties"]["inner"]
    assert inner["additionalProperties"] is False
    assert inner["required"] == ["x"]


def test_sampling_matrix_strict_supported_uses_json_schema() -> None:
    lane = build_preset_lane("openai:chat:v1")  # supports_strict=True
    request = LaneRequest(system="s", user="u", json_schema={"type": "object"})
    rf = resolve_response_format(lane, request)
    assert rf is not None and rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True


def test_sampling_matrix_prefer_degrades_to_json_object() -> None:
    lane = build_preset_lane("deepseek:chat:v1")  # supports_strict=False
    rf = resolve_response_format(
        lane, LaneRequest(system="s", user="u", json_schema={"type": "object"}, strict="prefer")
    )
    assert rf == {"type": "json_object"}


def test_sampling_matrix_require_without_support_raises() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    with pytest.raises(LaneStrictError):
        resolve_response_format(
            lane,
            LaneRequest(system="s", user="u", json_schema={"type": "object"}, strict="require"),
        )


# --------------------------------------------------------------------------
# S2.2 usage 归一化
# --------------------------------------------------------------------------


def test_normalize_openai_cached_tokens_subtracted_from_input() -> None:
    usage = normalize_usage_openai(
        {
            "prompt_tokens": 1200,
            "completion_tokens": 350,
            "prompt_tokens_details": {"cached_tokens": 800},
        }
    )
    assert usage.input_tokens == 400
    assert usage.cache_read_tokens == 800
    assert usage.output_tokens == 350


def test_normalize_deepseek_native_cache_field() -> None:
    usage = normalize_usage_openai(
        {"prompt_tokens": 1200, "completion_tokens": 350, "prompt_cache_hit_tokens": 800}
    )
    assert usage.cache_read_tokens == 800
    assert usage.input_tokens == 400


def test_normalize_reasoning_tokens_tracked_not_priced_separately() -> None:
    usage = normalize_usage_openai(
        {
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "completion_tokens_details": {"reasoning_tokens": 150},
        }
    )
    assert usage.reasoning_tokens == 150
    assert usage.output_tokens == 200


# --------------------------------------------------------------------------
# S2.2 retry（分类 + 退避序列 + fail fast）
# --------------------------------------------------------------------------


def test_retry_retries_then_succeeds_with_backoff_sequence() -> None:
    sleeps: list[float] = []
    client = FakeClient(
        [
            FakeResponse(429, {"error": "overloaded"}),
            FakeResponse(500, {"error": "boom"}),
            FakeResponse(200, _completion_payload("recovered")),
        ]
    )
    transport = LaneTransport(
        build_preset_lane("deepseek:chat:v1"),
        environ={"DEEPSEEK_API_KEY": "k"},
        client=client,
        sleep=sleeps.append,
    )
    result = transport.complete(LaneRequest(system="s", user="u"))
    assert result.text == "recovered"
    assert sleeps == [0.5, 1.0]  # base×2^0, base×2^1（RetryPolicy 默认）


def test_retry_fail_fast_on_auth_error() -> None:
    sleeps: list[float] = []
    client = FakeClient([FakeResponse(401, {"error": "bad key"})])
    transport = LaneTransport(
        build_preset_lane("deepseek:chat:v1"),
        environ={"DEEPSEEK_API_KEY": "k"},
        client=client,
        sleep=sleeps.append,
    )
    with pytest.raises(LaneTransportError) as excinfo:
        transport.complete(LaneRequest(system="s", user="u"))
    assert excinfo.value.status_code == 401
    assert excinfo.value.retryable is False
    assert sleeps == []


def test_retry_exhaustion_raises_after_max_retries() -> None:
    sleeps: list[float] = []
    client = FakeClient([FakeResponse(500, {"error": "boom"}) for _ in range(10)])
    transport = LaneTransport(
        build_preset_lane("deepseek:chat:v1"),
        environ={"DEEPSEEK_API_KEY": "k"},
        client=client,
        sleep=sleeps.append,
        retry_policy=RetryPolicy(max_retries=2),
    )
    with pytest.raises(LaneTransportError):
        transport.complete(LaneRequest(system="s", user="u"))
    assert len(sleeps) == 2  # attempt0/1 重试，attempt2 放弃


# --------------------------------------------------------------------------
# S2.2 transport happy path（真实链路：payload → response → usage → cost）
# --------------------------------------------------------------------------


def test_transport_complete_computes_cost_from_snapshot_prices() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    client = FakeClient(
        [
            FakeResponse(
                200,
                _completion_payload(
                    text="outline",
                    usage={
                        "prompt_tokens": 1_000_000,
                        "completion_tokens": 500_000,
                        "prompt_cache_hit_tokens": 0,
                    },
                ),
            )
        ]
    )
    transport = LaneTransport(lane, environ={"DEEPSEEK_API_KEY": "k"}, client=client)
    result = transport.complete(LaneRequest(system="s", user="u"))
    assert result.text == "outline"
    assert result.lane_id == "deepseek:chat:v1"
    assert result.usage_cost.input == pytest.approx(lane.cost.input)
    assert result.usage_cost.output == pytest.approx(lane.cost.output / 2)
    assert client.calls[0]["headers"]["Authorization"] == "Bearer k"
    assert client.calls[0]["url"].endswith("/chat/completions")


def test_transport_local_lane_sends_no_auth_header() -> None:
    lane = build_preset_lane("vllm:local:v1")
    client = FakeClient([FakeResponse(200, _completion_payload())])
    transport = LaneTransport(lane, client=client)
    transport.complete(LaneRequest(system="s", user="u"))
    assert "Authorization" not in client.calls[0]["headers"]


def test_transport_missing_credential_fails_at_construction() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    with pytest.raises(ProviderLaneError):
        LaneTransport(lane, environ={})


def test_transport_network_error_is_retryable() -> None:
    sleeps: list[float] = []
    client = FakeClient(
        [httpx.ConnectError("conn refused"), FakeResponse(200, _completion_payload())]
    )
    transport = LaneTransport(
        build_preset_lane("deepseek:chat:v1"),
        environ={"DEEPSEEK_API_KEY": "k"},
        client=client,
        sleep=sleeps.append,
    )
    result = transport.complete(LaneRequest(system="s", user="u"))
    assert result.text == "ok"
    assert sleeps == [0.5]


# --------------------------------------------------------------------------
# 预算档接线（A5 评估纪律：预算必须被执行，不只是被声明）
# --------------------------------------------------------------------------


def test_transport_enforces_call_cap_before_dispatch() -> None:
    """The call cap must fail closed *before* the next request leaves the process."""

    lane = build_preset_lane(
        "deepseek:chat:v1", budget_profile=LaneBudgetProfile(max_calls_per_run=1)
    )
    client = FakeClient([FakeResponse(200, _completion_payload())])
    transport = LaneTransport(lane, environ={"DEEPSEEK_API_KEY": "k"}, client=client)

    transport.complete(LaneRequest(system="s", user="u"))

    with pytest.raises(LaneBudgetExceededError):
        transport.complete(LaneRequest(system="s", user="u"))
    assert len(client.calls) == 1  # the second call never reached the network
    assert transport.calls_made == 1


def test_transport_enforces_per_call_cost_cap() -> None:
    lane = build_preset_lane(
        "deepseek:chat:v1", budget_profile=LaneBudgetProfile(max_cost_per_call_usd=0.0)
    )
    client = FakeClient([FakeResponse(200, _completion_payload())])
    transport = LaneTransport(lane, environ={"DEEPSEEK_API_KEY": "k"}, client=client)

    with pytest.raises(LaneBudgetExceededError):
        transport.complete(LaneRequest(system="s", user="u"))


def test_transport_accumulates_run_budget_counters() -> None:
    lane = build_preset_lane("deepseek:chat:v1")
    client = FakeClient([FakeResponse(200, _completion_payload())])
    transport = LaneTransport(lane, environ={"DEEPSEEK_API_KEY": "k"}, client=client)

    transport.complete(LaneRequest(system="s", user="u"))

    assert transport.spent_tokens == 1100  # 1000 prompt + 100 completion
    assert transport.spent_usd > 0
    assert transport.calls_made == 1


# --------------------------------------------------------------------------
# 重试计费口径（自审 4.4：重试次数必须可解释，否则成本被系统性低估）
# --------------------------------------------------------------------------


def test_transport_first_try_records_one_attempt() -> None:
    client = FakeClient([FakeResponse(200, _completion_payload())])
    transport = LaneTransport(
        build_preset_lane("deepseek:chat:v1"), environ={"DEEPSEEK_API_KEY": "k"}, client=client
    )

    assert transport.complete(LaneRequest(system="s", user="u")).attempts == 1


def test_transport_retry_attempts_reach_the_receipt_cost_block() -> None:
    client = FakeClient(
        [FakeResponse(500, {"error": "boom"}), FakeResponse(200, _completion_payload())]
    )
    transport = LaneTransport(
        build_preset_lane("deepseek:chat:v1"),
        environ={"DEEPSEEK_API_KEY": "k"},
        client=client,
        sleep=lambda _seconds: None,
    )

    result = transport.complete(LaneRequest(system="s", user="u"))

    assert result.attempts == 2
    cost = receipt_usage_fields(result)["cost"]
    assert cost["attempts"] == 2
    # total x attempts is the honest upper bound for what this call may have cost
    assert cost["total"] * cost["attempts"] > cost["total"]


# --------------------------------------------------------------------------
# S2.3 handoff 四规则
# --------------------------------------------------------------------------


def test_tool_call_id_sanitized_and_capped() -> None:
    assert normalize_tool_call_id("call_abc-123") == "call_abc-123"
    dirty = "call/" + "!@#" * 30
    normalized = normalize_tool_call_id(dirty)
    assert all(ch.isalnum() or ch in "_-" for ch in normalized)
    assert len(normalized) <= 64


def test_orphan_tool_calls_get_synthetic_results() -> None:
    messages = [
        {"role": "user", "content": "run"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "call_a"}, {"id": "call_b"}],
        },
        {"role": "tool", "tool_call_id": "call_a", "content": "ok"},
    ]
    merged = synthesize_orphan_tool_results(messages)
    tool_results = [m for m in merged if m.get("role") == "tool"]
    assert {m["tool_call_id"] for m in tool_results} == {"call_a", "call_b"}
    synthetic = [m for m in tool_results if m.get("content") == "(no tool result recorded)"]
    assert [m["tool_call_id"] for m in synthetic] == ["call_b"]


def test_degrade_images_replaces_image_blocks() -> None:
    message = {
        "role": "user",
        "content": [
            {"type": "text", "text": "look"},
            {"type": "image", "source": {"kind": "base64"}},
        ],
    }
    degraded = degrade_images_for_non_vision(message)
    assert degraded["content"][1] == {
        "type": "text",
        "text": "(image omitted: model does not support images)",
    }
    assert message["content"][1]["type"] == "image"  # 原消息不被原地修改


def test_convert_thinking_drops_redacted_and_downgrades_to_text() -> None:
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "step one", "signature": "sig"},
                {"type": "thinking", "redacted": True},
                {"type": "text", "text": "answer"},
            ],
        }
    ]
    converted = convert_thinking_for_cross_model(messages)
    blocks = converted[0]["content"]
    assert blocks == [
        {"type": "text", "text": "step one"},
        {"type": "text", "text": "answer"},
    ]
