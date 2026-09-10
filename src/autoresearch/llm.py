"""Optional OpenAI-compatible boundary, now backed by the O12 provider lane.

The public surface is unchanged -- ``LLMService(settings)``, ``available``,
``complete(...)`` and ``complete_json(...)`` keep their signatures, so
``application.py``, ``orchestrator.py`` and ``writing_service.py`` need no edits.

Internally the raw httpx call is gone. Settings are resolved to a lane identity
(reusing a preset lane and its catalog pricing when the endpoint matches),
dispatch goes through :class:`LaneTransport` (credential scope, retry
classification, usage normalisation, four-tier pricing), and each result carries
its priced usage so a receipt can be filled without re-deriving it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from autoresearch.config import Settings
from autoresearch.provider_lane import (
    LANE_SPECS,
    LaneBudgetProfile,
    LaneIdentity,
    LaneRequest,
    LaneResult,
    LaneTransport,
    ModelCost,
    ProviderLaneError,
    build_preset_lane,
    receipt_usage_fields,
)


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    provider: str
    raw: dict[str, Any]


def lane_from_settings(settings: Settings) -> LaneIdentity:
    """Resolve Settings to a lane identity.

    A preset lane is reused whenever the configured endpoint matches one, which
    brings in the vendored catalog's four-tier pricing. Otherwise a settings lane
    is built with pricing left at zero (unpriced) so a call still works without a
    catalog entry; the credential is supplied explicitly by the facade.
    """

    base_url = (settings.llm_base_url or "").rstrip("/")
    model = settings.llm_model or ""
    for spec in LANE_SPECS:
        if spec["endpoint"].rstrip("/") != base_url:
            continue
        try:
            return build_preset_lane(spec["lane_id"], model_override=model)
        except ProviderLaneError:
            break
    return LaneIdentity(
        lane_id=f"{settings.llm_provider}:settings:v1",
        provider=settings.llm_provider,
        endpoint=base_url,
        model=model,
        api_family="openai-completions",
        cost=ModelCost(input=0.0, output=0.0),
        context_window=0,
        max_output_tokens=0,
        reasoning_supported=False,
        credential_env_names=("AUTORESEARCH_LLM_API_KEY", "LLM_API_KEY"),
        budget_profile=LaneBudgetProfile(),
    )


class LLMService:
    """Optional OpenAI-compatible boundary. Secrets remain inside Settings."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._lane: LaneIdentity | None = None
        self._transport: LaneTransport | None = None
        self.last_result: LaneResult | None = None

    @property
    def available(self) -> bool:
        return self.settings.llm_configured

    @property
    def lane(self) -> LaneIdentity:
        if self._lane is None:
            self._lane = lane_from_settings(self.settings)
        return self._lane

    def _ensure_transport(self) -> LaneTransport:
        if self._transport is None:
            key = self.settings.llm_api_key
            self._transport = LaneTransport(
                self.lane,
                credential=key.get_secret_value() if key else None,
                timeout_seconds=self.settings.llm_timeout_seconds,
            )
        return self._transport

    def complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> LLMResult | None:
        if not self.available:
            return None

        result = self._ensure_transport().complete(
            LaneRequest(system=system, user=user, temperature=temperature, json_mode=json_mode)
        )
        self.last_result = result
        raw: dict[str, Any] = {
            "id": result.raw.get("id"),
            "usage": result.raw.get("usage", {}),
            **receipt_usage_fields(result),
        }
        return LLMResult(
            text=result.text,
            model=result.model,
            provider=self.settings.llm_provider,
            raw=raw,
        )

    def complete_json(self, *, system: str, user: str) -> dict[str, Any] | None:
        result = self.complete(system=system, user=user, json_mode=True)
        if result is None:
            return None
        return json.loads(result.text)
