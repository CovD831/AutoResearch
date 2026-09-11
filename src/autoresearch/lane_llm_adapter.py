"""O12 <-> B4 seam: turn a live ProviderLane completion into a validated B4 payload.

``reader_writer_ports`` (B4) normalises *supplied* payloads and explicitly leaves
live provider wiring to O12 (B4 L3, "Known limits": "That integration belongs to
O12 ProviderLane"). This module is exactly that missing piece and nothing more:
it reuses B4's ``StructuredReadingPayload`` / ``StructuredDraftPayload`` models and
``Structured{Reader,Writer}Adapter`` classes verbatim, so the contract diff
against B4 is zero by construction -- no mirrored type and no new port method is
introduced here.

It does not modify ``reader_writer_ports.py`` and performs no evidence write: the
B4 port still owns candidate construction, and admission stays downstream.
"""

from __future__ import annotations

from typing import Any

from autoresearch.provider_lane import (
    LaneIdentity,
    LaneRequest,
    LaneResult,
    LaneRunLedger,
    LaneTransport,
)
from autoresearch.reader_writer_ports import (
    AdapterKind,
    ReaderRequest,
    ReaderResult,
    StructuredDraftPayload,
    StructuredReaderAdapter,
    StructuredReadingPayload,
    StructuredWriterAdapter,
    WriterRequest,
    WriterResult,
)

__all__ = ["LaneLLMAdapter"]


class LaneLLMAdapter:
    """Thin seam: one lane completion -> validated B4 payload -> B4 port result."""

    def __init__(
        self,
        lane: LaneIdentity,
        *,
        transport: LaneTransport | None = None,
        ledger: LaneRunLedger | None = None,
        adapter_name: str = "lane.llm",
        adapter_version: str = "v1",
    ) -> None:
        self.lane = lane
        # ``ledger`` puts this adapter on the same per-run budget as any other
        # consumer of the lane (e.g. LLMService); pass either a ledger or a
        # ready-made transport, not both.
        self.transport = (
            transport if transport is not None else LaneTransport(lane, ledger=ledger)
        )
        self.last_result: LaneResult | None = None
        self._reader = StructuredReaderAdapter(
            AdapterKind.LLM, adapter_name=adapter_name, adapter_version=adapter_version
        )
        self._writer = StructuredWriterAdapter(
            AdapterKind.LLM, adapter_name=adapter_name, adapter_version=adapter_version
        )

    def read(self, request: ReaderRequest, *, system: str, user: str) -> ReaderResult:
        payload = self._complete_as(StructuredReadingPayload, system, user)
        return self._reader.read(request, payload)

    def write(self, request: WriterRequest, *, system: str, user: str) -> WriterResult:
        payload = self._complete_as(StructuredDraftPayload, system, user)
        return self._writer.write(request, payload)

    def _complete_as(self, model: Any, system: str, user: str) -> Any:
        """Run one lane call constrained to ``model``'s JSON schema, then validate.

        ``strict="prefer"`` never raises the sampling matrix (S2.4): a lane that
        supports strict json_schema gets it, otherwise the response format
        degrades to ``json_object``. The payload is validated against the exact
        B4 model before it reaches the port, so a malformed completion fails
        closed here instead of fabricating a reading/draft.
        """

        self.last_result = self.transport.complete(
            LaneRequest(
                system=system,
                user=user,
                json_schema=model.model_json_schema(),
                strict="prefer",
            )
        )
        return model.model_validate_json(self.last_result.text)
