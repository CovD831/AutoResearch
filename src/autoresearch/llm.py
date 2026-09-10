"""Optional OpenAI-compatible boundary, now backed by the O12 provider lane.

The public surface is unchanged -- ``LLMService(settings)``, ``available``,
``complete(...)`` and ``complete_json(...)`` keep their signatures, so
``application.py``, ``orchestrator.py`` and ``writing_service.py`` need no edits.

Internally the raw httpx call is gone. Settings are resolved to a lane identity
(reusing a preset lane when the endpoint matches, with pricing resolved from the
model id via the vendored catalog), dispatch goes through
:class:`LaneTransport` (credential scope, retry classification, usage
normalisation, four-tier pricing), and each result carries its priced usage so a
receipt can be filled without re-deriving it.
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
    LaneNotConfiguredError,
    LaneRequest,
    LaneResult,
    LaneTransport,
    ModelCost,
    ProviderLaneError,
    build_preset_lane,
    load_default_catalog,
    receipt_usage_fields,
)


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    provider: str
    raw: dict[str, Any]


# Catalog lookup order for pricing a bare model id (pricing is a model property,
# not an endpoint property; the order only breaks ties across providers).
_PRICING_PROVIDER_ORDER = ("deepseek", "openai", "anthropic", "alibaba", "moonshotai")


def _normalize_endpoint(url: str) -> str:
    """Endpoint comparison tolerance: case, trailing slash and a ``/v1`` suffix
    are spelling differences, not identity differences."""

    normalized = (url or "").strip().rstrip("/").lower()
    for suffix in ("/v1", "/chat/completions"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
    return normalized.rstrip("/")


def _catalog_price_for_model(model_id: str) -> tuple[ModelCost, str] | None:
    """Price a model id from the catalog, regardless of endpoint.

    Returns the four-tier cost together with the provenance of the price table
    that produced it (snapshot vs manual override). Without this, a ``base_url``
    written as ``.../v1`` (or with different host casing) would fall through to an
    unpriced lane and report cost 0 for a call that really happened — an audit
    hole, not a conservative default.
    """

    if not model_id:
        return None
    catalog = load_default_catalog()
    for provider in _PRICING_PROVIDER_ORDER:
        try:
            model = catalog.get_model(provider, model_id)
        except ProviderLaneError:
            continue
        return ModelCost.from_dict(model["cost"]), catalog.model_price_source(provider, model_id)
    return None


def lane_from_settings(settings: Settings) -> LaneIdentity:
    """Resolve Settings to a lane identity.

    A preset lane is reused when the endpoint matches one (tolerantly), bringing
    in that lane's identity metadata. Pricing, however, is resolved from the model
    id via the vendored catalog, so it survives endpoint spelling differences; a
    model absent from the catalog stays unpriced (cost 0) rather than being given
    an invented rate. The credential is supplied explicitly by the facade.
    """

    base_url = (settings.llm_base_url or "").rstrip("/")
    model = settings.llm_model or ""
    if not base_url or not model:
        raise LaneNotConfiguredError(
            "settings do not define an LLM endpoint/model",
            suggested_recovery="set LLM_BASE_URL and LLM_MODEL, or keep LLM_PROVIDER=offline",
        )

    normalized = _normalize_endpoint(base_url)
    for spec in LANE_SPECS:
        if _normalize_endpoint(spec["endpoint"]) != normalized:
            continue
        try:
            return build_preset_lane(spec["lane_id"], model_override=model)
        except ProviderLaneError:
            break
    priced = _catalog_price_for_model(model)
    return LaneIdentity(
        lane_id=f"{settings.llm_provider}:settings:v1",
        provider=settings.llm_provider,
        endpoint=base_url,
        model=model,
        api_family="openai-completions",
        cost=priced[0] if priced else ModelCost(input=0.0, output=0.0),
        context_window=0,
        max_output_tokens=0,
        reasoning_supported=False,
        credential_env_names=("AUTORESEARCH_LLM_API_KEY", "LLM_API_KEY"),
        budget_profile=LaneBudgetProfile(),
        price_source=(priced[1] if priced else None),
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
            # An empty key means "not configured", not "send an empty Bearer and
            # wait for a 401": normalise it to None so the whitelist/fail-closed
            # path decides instead of the network round trip.
            credential = (key.get_secret_value().strip() or None) if key else None
            self._transport = LaneTransport(
                self.lane,
                credential=credential,
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
            **receipt_usage_fields(result, price_source=self.lane.price_source),
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
