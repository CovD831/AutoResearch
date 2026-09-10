"""O12 receipt pricing fields (S2.5): lane usage -> shared receipt schema.

Offline: costs are computed from the vendored catalog entry, no network call.
The frozen field names below are the schema A5 implements against tomorrow.
"""

from __future__ import annotations

import pytest

from autoresearch.capability_registry import CapabilityInvocationReceipt
from autoresearch.invocation_contracts import (
    InvocationCost,
    InvocationReceipt,
    InvocationStatus,
    TokenUsage,
)
from autoresearch.provider_lane import (
    LaneResult,
    ModelCost,
    Usage,
    build_preset_lane,
    calculate_cost,
    receipt_usage_fields,
)

LANE = build_preset_lane("deepseek:chat:v1")


def _lane_result() -> LaneResult:
    usage = Usage(
        input_tokens=1_000_000,
        output_tokens=500_000,
        reasoning_tokens=120_000,
    )
    return LaneResult(
        text="{}",
        lane_id=LANE.lane_id,
        model=LANE.model,
        usage=usage,
        usage_cost=calculate_cost(usage, LANE.cost),
        raw={},
    )


# ---------------------------------------------------------------------------
# O12 -> receipt conversion
# ---------------------------------------------------------------------------


def test_receipt_fields_shape_and_price_match_calculator() -> None:
    result = _lane_result()
    fields = receipt_usage_fields(result)

    assert set(fields) == {"tokens", "cost"}
    assert fields["tokens"] == {
        "input": 1_000_000,
        "output": 500_000,
        "cache_read": 0,
        "cache_write": 0,
        "reasoning": 120_000,
    }
    assert fields["cost"]["total"] == pytest.approx(result.usage_cost.total)
    assert fields["cost"]["lane_id"] == LANE.lane_id
    assert fields["cost"]["model"] == LANE.model
    assert fields["cost"]["currency"] == "USD"


def test_reasoning_tokens_are_not_billed_twice() -> None:
    usage = Usage(input_tokens=0, output_tokens=1000, reasoning_tokens=1000)
    result = LaneResult(
        text="",
        lane_id="lane:test",
        model="m",
        usage=usage,
        usage_cost=calculate_cost(usage, ModelCost(input=1.0, output=3.0)),
        raw={},
    )
    cost = receipt_usage_fields(result)["cost"]

    assert cost["output"] == pytest.approx(3.0 / 1_000_000 * 1000)
    assert cost["total"] == pytest.approx(
        cost["input"] + cost["output"] + cost["cache_read"] + cost["cache_write"]
    )


# ---------------------------------------------------------------------------
# Shared receipt contracts (A1 + S3-A) accept the blocks
# ---------------------------------------------------------------------------


def test_invocation_receipt_accepts_usage_and_cost_blocks() -> None:
    fields = receipt_usage_fields(_lane_result())
    receipt = InvocationReceipt(
        invocation_id="inv-1",
        status=InvocationStatus.COMPLETED,
        adapter="lane.llm",
        adapter_version="v1",
        request_fingerprint="0" * 64,
        tokens=fields["tokens"],
        cost=fields["cost"],
    )

    assert receipt.tokens is not None and receipt.tokens.input == 1_000_000
    assert receipt.cost is not None and receipt.cost.lane_id == LANE.lane_id


def test_invocation_receipt_pricing_fields_default_to_none() -> None:
    receipt = InvocationReceipt(
        invocation_id="inv-2",
        status=InvocationStatus.COMPLETED_EMPTY,
        adapter="paper_search.native",
        adapter_version="0.1",
        request_fingerprint="1" * 64,
    )

    assert receipt.tokens is None
    assert receipt.cost is None


def test_capability_receipt_shares_the_same_pricing_schema() -> None:
    fields = receipt_usage_fields(_lane_result())
    receipt = CapabilityInvocationReceipt(
        invocation_id="inv-3",
        capability="semantic_scholar.search",
        adapter_kind="native",
        adapter_version="0.1",
        trust_tier="candidate_only",
        status="completed",
        outcome_status="completed",
        request_fingerprint="2" * 64,
        tokens=fields["tokens"],
        cost=fields["cost"],
    )

    assert receipt.tokens is not None
    assert receipt.cost is not None
    assert set(receipt.cost.model_dump()) >= {
        "input",
        "output",
        "cache_read",
        "cache_write",
        "total",
        "currency",
        "model",
        "lane_id",
    }
    # pricing is informational: it never moves the admissibility boundary
    assert receipt.candidates_admissible is True


def test_a5_reserved_schema_field_names_are_stable() -> None:
    """Frozen contract: A5 implements against exactly these names."""

    assert set(TokenUsage().model_dump()) == {
        "input",
        "output",
        "cache_read",
        "cache_write",
        "reasoning",
    }
    assert set(InvocationCost().model_dump()) == {
        "input",
        "output",
        "cache_read",
        "cache_write",
        "total",
        "currency",
        "model",
        "lane_id",
    }
