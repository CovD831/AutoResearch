"""O12 <-> B4 seam tests: lane completion -> B4 payload -> B4 port result.

Offline only: a fake transport supplies the lane response, so no network and no
credential are required. The point of these tests is the contract boundary, not
the model: the seam must reuse B4's payload models and port classes verbatim
(diff = 0) and must fail closed on a malformed completion.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

import autoresearch.lane_llm_adapter as seam
import autoresearch.reader_writer_ports as b4
from autoresearch.contracts import EvidenceGrade, EvidenceType, PaperRecord
from autoresearch.pipeline_contracts import SectionPlan
from autoresearch.provider_lane import (
    LaneRequest,
    LaneResult,
    ModelCost,
    Usage,
    build_preset_lane,
    calculate_cost,
)

LANE = build_preset_lane("deepseek:chat:v1")

READING_JSON = {
    "research_question": "Does treatment X raise outcome Y?",
    "method": "randomised controlled trial",
    "data_or_setting": "n=100, single site",
    "findings": ["X raises Y by 10% over baseline"],
    "limitations": ["small sample"],
    "locators": ["abstract"],
    "confidence": 0.8,
    "independent_source": "example.invalid/paper-1",
}

DRAFT_JSON = {
    "title": "Evaluation",
    "body": "We evaluate the reported effect against the bound evidence.",
    "claims": ["X raises Y by 10%"],
    "claim_evidence_map": {"X raises Y by 10%": ["ev-1"]},
    "unresolved_gaps": [],
    "limitations": ["fixture data"],
}


class FakeTransport:
    """Minimal LaneTransport stand-in: returns a canned completion."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[LaneRequest] = []

    def complete(self, request: LaneRequest) -> LaneResult:
        self.requests.append(request)
        usage = Usage(input_tokens=1000, output_tokens=100)
        return LaneResult(
            text=self.text,
            lane_id=LANE.lane_id,
            model=LANE.model,
            usage=usage,
            usage_cost=calculate_cost(usage, ModelCost(input=0.28, output=0.42)),
            raw={},
        )


def _reader_request() -> b4.ReaderRequest:
    return b4.ReaderRequest(
        request_id="req-r1",
        project_id="proj-1",
        paper=PaperRecord(
            paper_id="paper-1",
            project_id="proj-1",
            title="A fixture paper",
            source="example.invalid",
        ),
    )


def _writer_request() -> b4.WriterRequest:
    plan = SectionPlan(project_id="proj-1", objective="Evaluate the bound evidence")
    return b4.WriterRequest(
        request_id="req-w1",
        project_id="proj-1",
        plan=plan,
        profile_id="wprof-1",
        benchmark_plan_id="bplan-1",
    )


# ---------------------------------------------------------------------------
# Contract diff = 0
# ---------------------------------------------------------------------------


def test_seam_reuses_b4_models_and_ports_verbatim() -> None:
    """The seam must not mirror B4 types: identity, not equality."""

    assert seam.StructuredReadingPayload is b4.StructuredReadingPayload
    assert seam.StructuredDraftPayload is b4.StructuredDraftPayload
    assert seam.StructuredReaderAdapter is b4.StructuredReaderAdapter
    assert seam.StructuredWriterAdapter is b4.StructuredWriterAdapter


def test_seam_delegates_to_b4_port_instances() -> None:
    adapter = seam.LaneLLMAdapter(LANE, transport=FakeTransport("{}"))
    assert isinstance(adapter._reader, b4.StructuredReaderAdapter)
    assert isinstance(adapter._writer, b4.StructuredWriterAdapter)


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


def test_read_maps_lane_json_to_b4_reader_result() -> None:
    transport = FakeTransport(json.dumps(READING_JSON))
    adapter = seam.LaneLLMAdapter(LANE, transport=transport)

    result = adapter.read(_reader_request(), system="be careful", user="read this")

    assert isinstance(result, b4.ReaderResult)
    assert result.adapter is b4.AdapterKind.LLM
    assert result.card.research_question == READING_JSON["research_question"]
    assert result.card.findings == READING_JSON["findings"]
    assert result.candidate.claim == READING_JSON["findings"][0]
    assert result.candidate.evidence_type is EvidenceType.PAPER
    assert result.candidate.grade is EvidenceGrade.E1
    assert adapter.last_result is not None


def test_write_maps_lane_json_to_b4_writer_result() -> None:
    adapter = seam.LaneLLMAdapter(LANE, transport=FakeTransport(json.dumps(DRAFT_JSON)))

    result = adapter.write(_writer_request(), system="be careful", user="write this")

    assert isinstance(result, b4.WriterResult)
    assert result.adapter is b4.AdapterKind.LLM
    assert result.draft.title == "Evaluation"
    assert result.draft.claim_evidence_map == DRAFT_JSON["claim_evidence_map"]


def test_seam_constrains_call_with_json_schema_and_prefer() -> None:
    """S2.4 sampling matrix: schema attached, strict=prefer never raises."""

    transport = FakeTransport(json.dumps(READING_JSON))
    adapter = seam.LaneLLMAdapter(LANE, transport=transport)

    adapter.read(_reader_request(), system="s", user="u")

    lane_request = transport.requests[0]
    assert lane_request.json_schema is not None
    assert lane_request.strict == "prefer"
    assert lane_request.json_schema["properties"]["research_question"]["type"] == "string"


def test_malformed_completion_fails_closed_before_the_port() -> None:
    transport = FakeTransport(json.dumps({"research_question": "only one field"}))
    adapter = seam.LaneLLMAdapter(LANE, transport=transport)

    with pytest.raises(ValidationError):
        adapter.read(_reader_request(), system="s", user="u")


def test_last_result_exposes_lane_cost_for_receipt() -> None:
    """S2.5 hook: the seam keeps the lane result so callers can price the receipt."""

    adapter = seam.LaneLLMAdapter(LANE, transport=FakeTransport(json.dumps(READING_JSON)))

    adapter.read(_reader_request(), system="s", user="u")

    assert adapter.last_result is not None
    assert adapter.last_result.usage.input_tokens == 1000
    assert adapter.last_result.usage_cost.total > 0
