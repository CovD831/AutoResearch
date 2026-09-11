"""Typed provider-lane identity, catalog, cost, credentials and drift guard.

O12 ProviderLane — lane 不可变身份 + pi-ai 语义移植（MIT, badlogic/pi-mono
packages/ai）+ openpilot lane 约束（预算档/凭据白名单/漂移 fail-closed）。

依据（全部已签认，见 docs/coord/adr-01-external-integrations.md 签字块 1）:
- 模型目录: pi-ai ``Model<TApi>`` / ``ModelCost``（四档 $/1M tokens + tiers 阶梯），
  数据 vendored 自 models.dev（MIT）——见 ``data/models_catalog.json`` 与
  ``scripts/refresh_model_catalog.py``。
- 计价: pi-ai ``calculateCost``——四档 rate/1e6 × tokens；reasoning tokens 是
  output 的子集，不重复计价；Anthropic 1h cacheWrite 规则未采用（models.dev
  快照不含该字段，backlog）。
- lane 身份/白名单/漂移: 本地 openpilot ``Code/src/core/provider_lane.py``
  （frozen identity + credential whitelist + fail-closed drift check）移植。
- 准入 fail-closed 模式（错误对象含 suggested_recovery）取自 openpilot
  ``provider_tool_admission.py``；工具执行/文件范围校验不在 O12 范围。

段 1 范围（speculative）: 身份/目录/计价/凭据/漂移/预算 + anthropic 档位映射
（两代规格，transport 二期实现）。transport（httpx）、handoff 消息转换、
constrained sampling 在段 2 落地。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "ProviderLaneError",
    "LaneCatalogError",
    "LaneNotConfiguredError",
    "LaneDriftError",
    "LaneBudgetExceededError",
    "LaneStrictError",
    "LaneResponseError",
    "ReasoningLevel",
    "THINKING_LEVELS_ORDERED",
    "ModelCost",
    "CostTier",
    "LaneBudgetProfile",
    "DEFAULT_MAX_CALLS_PER_RUN",
    "default_budget_profile",
    "LaneIdentity",
    "Usage",
    "UsageCost",
    "ModelCatalog",
    "calculate_cost",
    "anthropic_thinking_params",
    "credential_from_env",
    "require_credential",
    "validate_lane_settings",
    "lane_drift_event",
    "check_call_budget",
    "PRESET_LANE_IDS",
    "build_preset_lane",
    "load_default_catalog",
    "selftest_catalog",
    "LaneRequest",
    "LaneResult",
    "LaneRunLedger",
    "LaneTransport",
    "LaneTransportError",
    "LaneResponseError",
    "RetryPolicy",
    "build_openai_completions_payload",
    "normalize_usage_openai",
    "make_strict_json_schema",
    "resolve_response_format",
    "retry_with_backoff",
    "is_retryable_status",
    "normalize_tool_call_id",
    "degrade_images_for_non_vision",
    "synthesize_orphan_tool_results",
    "convert_thinking_for_cross_model",
    "receipt_usage_fields",
]


# --------------------------------------------------------------------------
# exceptions（openpilot 准入 fail-closed 模式：错误带 recovery 提示）
# --------------------------------------------------------------------------


class ProviderLaneError(ValueError):
    """Base error for provider lane violations (fail-closed)."""

    def __init__(self, message: str, *, suggested_recovery: str | None = None) -> None:
        self.suggested_recovery = suggested_recovery
        if suggested_recovery:
            message = f"{message} (recovery: {suggested_recovery})"
        super().__init__(message)


class LaneCatalogError(ProviderLaneError):
    """Catalog snapshot missing/malformed or requested entry absent."""


class LaneNotConfiguredError(ProviderLaneError):
    """Credential whitelist produced no usable key for a non-local lane."""


class LaneDriftError(ProviderLaneError):
    """Observed settings drifted from the immutable lane identity."""


class LaneBudgetExceededError(ProviderLaneError):
    """Estimated/spent cost or tokens exceed the lane budget profile."""


class LaneStrictError(ProviderLaneError):
    """Constrained sampling requested with strict=require but unsupported."""


# --------------------------------------------------------------------------
# reasoning levels（pi-ai ThinkingLevel 枚举）
# --------------------------------------------------------------------------

ReasoningLevel = str  # one of THINKING_LEVELS_ORDERED or "off"

THINKING_LEVELS_ORDERED: tuple[str, ...] = (
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

# Anthropic 档位→thinking 预算（本项目的文档化约定；pi-ai 的 antMapping 公式
# 未经源码确认，按官方约束 [min 1024, < max_tokens] 自定义并锁定测试）。
ANTHROPIC_BUDGET_BY_LEVEL: dict[str, int] = {
    "minimal": 1024,
    "low": 4096,
    "medium": 8192,
    "high": 16384,
    "xhigh": 24576,
    "max": 32768,
}

# Anthropic 4.6+ adaptive 模式：output_config.effort 档位原生（low/medium/high）。
ANTHROPIC_ADAPTIVE_EFFORT: dict[str, str] = {
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}


def _valid_level(level: str) -> bool:
    return level == "off" or level in THINKING_LEVELS_ORDERED


# --------------------------------------------------------------------------
# cost models（pi-ai ModelCost / tiers，$ / 1M tokens）
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CostTier:
    """Pricing tier: applies once billed input tokens reach ``input_tokens_above``."""

    input_tokens_above: int
    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0

    def __post_init__(self) -> None:
        if self.input_tokens_above < 0:
            raise ProviderLaneError("cost tier threshold must be >= 0")
        if min(self.input, self.output, self.cache_read, self.cache_write) < 0:
            raise ProviderLaneError("cost tier rates must be >= 0")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CostTier:
        return cls(
            input_tokens_above=int(data["inputTokensAbove"]),
            input=float(data["input"]),
            output=float(data["output"]),
            cache_read=float(data.get("cacheRead", 0.0)),
            cache_write=float(data.get("cacheWrite", 0.0)),
        )


@dataclass(frozen=True)
class ModelCost:
    """Four canonical tiers, USD per 1M tokens (pi-ai ``ModelCost``)."""

    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0
    tiers: tuple[CostTier, ...] = ()

    def __post_init__(self) -> None:
        if min(self.input, self.output, self.cache_read, self.cache_write) < 0:
            raise ProviderLaneError("model cost rates must be >= 0")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelCost:
        tiers = tuple(
            sorted(
                (CostTier.from_dict(t) for t in data.get("tiers", []) or []),
                key=lambda t: t.input_tokens_above,
            )
        )
        return cls(
            input=float(data["input"]),
            output=float(data["output"]),
            cache_read=float(data.get("cache_read", 0.0)),
            cache_write=float(data.get("cache_write", 0.0)),
            tiers=tiers,
        )

    def rates_for(self, billed_input_tokens: int) -> ModelCost:
        """pi-ai tier semantics: the highest threshold reached wins (>=)."""
        active = self
        for tier in self.tiers:
            if billed_input_tokens >= tier.input_tokens_above:
                active = ModelCost(
                    input=tier.input,
                    output=tier.output,
                    cache_read=tier.cache_read,
                    cache_write=tier.cache_write,
                )
        return active


@dataclass(frozen=True)
class Usage:
    """Normalized token usage (pi-ai ``Usage``). ``reasoning_tokens`` is an
    informational subset of ``output_tokens`` and is never priced twice."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0

    def __post_init__(self) -> None:
        for name in (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
        ):
            if getattr(self, name) < 0:
                raise ProviderLaneError(f"usage.{name} must be >= 0")


@dataclass(frozen=True)
class UsageCost:
    input: float
    output: float
    cache_read: float
    cache_write: float
    total: float


def calculate_cost(usage: Usage, cost: ModelCost) -> UsageCost:
    """pi-ai ``calculateCost``: rate/1e6 × tokens over the four canonical tiers.

    Tier selection compares *billed input tokens* (input + cache_read +
    cache_write) against ``CostTier.input_tokens_above`` using ``>=``.
    """
    billed_input = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    rates = cost.rates_for(billed_input)
    part_input = rates.input / 1_000_000 * usage.input_tokens
    part_output = rates.output / 1_000_000 * usage.output_tokens
    part_cache_read = rates.cache_read / 1_000_000 * usage.cache_read_tokens
    part_cache_write = rates.cache_write / 1_000_000 * usage.cache_write_tokens
    return UsageCost(
        input=part_input,
        output=part_output,
        cache_read=part_cache_read,
        cache_write=part_cache_write,
        total=part_input + part_output + part_cache_read + part_cache_write,
    )


# --------------------------------------------------------------------------
# lane identity（openpilot frozen ProviderLane，扩展 cost/catalog 字段）
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LaneBudgetProfile:
    """Fail-closed budget caps (A5 评估纪律: 固定调用预算入 receipt).

    ``None`` means "no cap configured" for that dimension; caps that ARE
    configured are enforced by :func:`check_call_budget` (and by the transport
    before dispatch).

    ``None`` is a *test/probe* shape, not a shipped one: every preset lane is
    built through :func:`default_budget_profile`, so no preset lane can run
    unbounded. Shipping all three dimensions as ``None`` while the transport
    docstring claimed the caps were enforced was the original defect (D-O12-11).
    """

    max_cost_per_call_usd: float | None = None
    max_calls_per_run: int | None = None
    max_tokens_per_run: int | None = None
    local_endpoint: bool = False


# A preset lane's default budget (D-O12-11). Deriving the caps from the lane's own
# catalog entry is what keeps them from ever rejecting legitimate work: the token
# cap is "every call in the run used a full context window", and the per-call cost
# cap is that same worst case priced at this lane's own worst rate tier.
DEFAULT_MAX_CALLS_PER_RUN = 240  # == A5 ResourceBudget.max_calls, so both ends agree
_FALLBACK_CONTEXT_TOKENS = 128_000  # used when the catalog reports context 0 (unknown)
_FALLBACK_OUTPUT_TOKENS = 8_192
_COST_CAP_HEADROOM = 1.5  # a provider may overshoot its own declared output limit


def default_budget_profile(
    *,
    context_window: int,
    max_output_tokens: int,
    cost: ModelCost,
    local_endpoint: bool = False,
) -> LaneBudgetProfile:
    """Build the complete, fail-closed budget a preset lane ships with.

    Every dimension is filled, because a default that caps nothing is not a
    default -- it is the absence of one. The values are the *worst case this lane
    could ever legitimately produce*, so they stop a runaway without ever
    rejecting real work:

    * ``max_calls_per_run``: 240, the same fixed call budget A5 records in its run
      receipt, so the two ends of the pricing chain agree on one number.
    * ``max_tokens_per_run``: 240 calls x (context window + max output).
    * ``max_cost_per_call_usd``: one full-window call at this lane's worst rate
      tier, times a small headroom factor.
    """

    context = context_window if context_window > 0 else _FALLBACK_CONTEXT_TOKENS
    output = max_output_tokens if max_output_tokens > 0 else _FALLBACK_OUTPUT_TOKENS
    rate_input = max([cost.input, *(tier.input for tier in cost.tiers)])
    rate_output = max([cost.output, *(tier.output for tier in cost.tiers)])
    worst_call_usd = (
        rate_input * context / 1_000_000 + rate_output * output / 1_000_000
    ) * _COST_CAP_HEADROOM
    return LaneBudgetProfile(
        max_cost_per_call_usd=worst_call_usd,
        max_calls_per_run=DEFAULT_MAX_CALLS_PER_RUN,
        max_tokens_per_run=DEFAULT_MAX_CALLS_PER_RUN * (context + output),
        local_endpoint=local_endpoint,
    )


API_FAMILIES = ("openai-completions", "anthropic-messages")


@dataclass(frozen=True)
class LaneIdentity:
    """Immutable expected identity for one provider lane (openpilot 同款)."""

    lane_id: str
    provider: str
    endpoint: str
    model: str
    api_family: str
    cost: ModelCost
    context_window: int  # 0 = unknown (local template entry), resolved at runtime
    max_output_tokens: int  # 0 = unknown
    reasoning_supported: bool
    credential_env_names: tuple[str, ...]
    budget_profile: LaneBudgetProfile = field(default_factory=LaneBudgetProfile)
    # openai-completions family only: which thinkingFormat the provider speaks
    # ("openai" -> reasoning_effort, "deepseek" -> thinking{type}+effort).
    # None => reasoning requests are rejected (fail fast) for this lane.
    thinking_format: str | None = None
    # provider supports strict json_schema response_format? False => prefer
    # degrades to json_object, require raises LaneStrictError (§4.5 矩阵).
    supports_strict_json_schema: bool = False
    max_rounds: int = 8
    # Where the cost figures came from (None = unpriced lane, no catalog entry).
    # Carried so a receipt can name the price table it was priced against.
    price_source: str | None = None

    def __post_init__(self) -> None:
        if not self.lane_id.strip() or not self.endpoint.strip() or not self.model.strip():
            raise ProviderLaneError("provider lane identity fields must be non-empty")
        if not self.provider.strip():
            raise ProviderLaneError("provider lane provider must be non-empty")
        if self.api_family not in API_FAMILIES:
            raise ProviderLaneError(
                f"unknown api_family {self.api_family!r}",
                suggested_recovery=f"use one of {API_FAMILIES}",
            )
        if not self.credential_env_names and not self.budget_profile.local_endpoint:
            raise ProviderLaneError(
                f"provider lane {self.lane_id} has no credential scope "
                "(non-local lanes must own at least one env name)"
            )
        if any(not name.strip() for name in self.credential_env_names):
            raise ProviderLaneError("credential env names must be non-empty")
        if self.max_rounds < 1:
            raise ProviderLaneError("provider lane max_rounds must be positive")
        if self.context_window < 0 or self.max_output_tokens < 0:
            raise ProviderLaneError("lane token limits must be >= 0")


# --------------------------------------------------------------------------
# model catalog（vendored models.dev snapshot，MIT）
# --------------------------------------------------------------------------

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "models_catalog.json"
DEFAULT_OVERRIDES_PATH = Path(__file__).resolve().parent / "data" / "price_overrides.json"


class ModelCatalog:
    """Read-only view over the vendored snapshot plus manual price overrides.

    The snapshot is a point-in-time copy of models.dev and *will* lag provider
    price pages; ``price_overrides.json`` pins the prices of the models this
    project actually calls. See ``PRICE-POLICY.md``.
    """

    def __init__(
        self,
        data: Mapping[str, Any],
        *,
        source_path: str | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> None:
        meta = data.get("_meta")
        if not isinstance(meta, dict) or "source" not in meta or "license" not in meta:
            raise LaneCatalogError(
                "catalog snapshot is missing the _meta provenance block",
                suggested_recovery="regenerate via scripts/refresh_model_catalog.py",
            )
        if not isinstance(data.get("providers"), dict):
            raise LaneCatalogError("catalog snapshot has no providers table")
        self._meta = dict(meta)
        self._overrides: dict[str, Any] = dict(overrides or {})
        # Copy two levels down: applying an override must never mutate the data
        # structure the caller handed us.
        self._providers: dict[str, dict] = {
            provider_id: {
                **provider,
                "models": {mid: dict(model) for mid, model in provider.get("models", {}).items()},
            }
            for provider_id, provider in data["providers"].items()
        }
        self.source_path = source_path
        self._apply_price_overrides()

    @classmethod
    def load(
        cls, path: str | Path | None = None, *, overrides_path: str | Path | None = None
    ) -> ModelCatalog:
        resolved = Path(path) if path is not None else DEFAULT_CATALOG_PATH
        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise LaneCatalogError(
                f"catalog snapshot not found at {resolved}",
                suggested_recovery="run scripts/refresh_model_catalog.py",
            ) from exc
        except json.JSONDecodeError as exc:
            raise LaneCatalogError(f"catalog snapshot is not valid JSON: {exc}") from exc

        overrides: dict[str, Any] | None = None
        resolved_overrides = (
            Path(overrides_path) if overrides_path is not None else DEFAULT_OVERRIDES_PATH
        )
        if resolved_overrides.exists():
            try:
                overrides = json.loads(resolved_overrides.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise LaneCatalogError(
                    f"price overrides at {resolved_overrides} are not valid JSON: {exc}",
                    suggested_recovery="fix or remove src/autoresearch/data/price_overrides.json",
                ) from exc
        return cls(data, source_path=str(resolved), overrides=overrides)

    @property
    def price_source(self) -> str:
        """Human-readable provenance of the prices in this snapshot.

        These prices are an *estimate* derived from this snapshot, not the
        provider's invoice. Vendored data can lag the provider's published price
        table — verified 2026-09-11 against DeepSeek's official rates, where the
        snapshot differed by up to ~4.5x and did not model peak/off-peak pricing
        (see ``SELF-REVIEW.md``). Recording the source on each priced receipt is
        what keeps a cost traceable to the table that produced it.
        """

        fetched = str(self._meta.get("fetched_at", ""))[:10]
        return f"models.dev snapshot {fetched}".strip()

    @staticmethod
    def _coerce_override_rate(key: str, field: str, value: Any) -> float:
        """Parse one override rate; malformed data is a catalog error, not a guess.

        A negative, non-numeric or NaN rate would otherwise be stored silently and
        surface only later (if ever) when the model is built into a lane — or never,
        for a model nothing builds. The catalog is the audit basis for pricing, so
        bad data fails loudly at load time instead of becoming a quiet wrong number.
        """

        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise LaneCatalogError(
                f"price override {key!r}: {field!r} must be a number",
                suggested_recovery="fix src/autoresearch/data/price_overrides.json",
            )
        try:
            rate = float(value)
        except (TypeError, ValueError) as exc:
            raise LaneCatalogError(
                f"price override {key!r}: {field!r} is not a number: {value!r}",
                suggested_recovery="fix src/autoresearch/data/price_overrides.json",
            ) from exc
        if rate != rate or rate in (float("inf"), float("-inf")) or rate < 0:
            raise LaneCatalogError(
                f"price override {key!r}: {field!r} must be a finite, "
                f"non-negative number, got {value!r}",
                suggested_recovery="fix src/autoresearch/data/price_overrides.json",
            )
        return rate

    def _apply_price_overrides(self) -> None:
        """Pin prices for the models actually in use (see ``PRICE-POLICY.md``).

        An override only replaces the four cost tiers of an *existing* catalog
        entry; it never invents a model, and an override pointing at an unknown
        entry is ignored rather than crashing the offline catalog. Malformed
        override data, by contrast, fails loudly: a catalog carrying a silently
        wrong rate is worse than one that refuses to load.

        A model is tagged with the source of its price only when an override
        actually patched a rate — an override that patches nothing must not make a
        receipt claim provenance it did not supply.
        """

        snapshot_source = self.price_source
        models_table = self._overrides.get("models") or {}
        if not isinstance(models_table, dict):
            raise LaneCatalogError(
                "price overrides 'models' must be an object keyed by 'provider/model'",
                suggested_recovery="fix src/autoresearch/data/price_overrides.json",
            )
        applied: set[tuple[str, str]] = set()
        for key, entry in models_table.items():
            if not isinstance(entry, dict):
                raise LaneCatalogError(
                    f"price override {key!r} must be an object",
                    suggested_recovery="fix src/autoresearch/data/price_overrides.json",
                )
            provider_id, _, model_id = str(key).partition("/")
            provider = self._providers.get(provider_id)
            if provider is None or model_id not in provider.get("models", {}):
                continue  # unknown target: ignored, never invents a model
            cost = dict(provider["models"][model_id].get("cost") or {})
            patched = False
            for rate_field in ("input", "output", "cache_read", "cache_write"):
                if rate_field not in entry:
                    continue
                cost[rate_field] = self._coerce_override_rate(
                    str(key), rate_field, entry[rate_field]
                )
                patched = True
            if not patched:
                continue  # nothing patched: keep the snapshot price and its source
            model = provider["models"][model_id]
            model["cost"] = cost
            parts = (
                "override",
                str(entry.get("checked_at") or ""),
                str(entry.get("source_host") or ""),
            )
            model["_price_source"] = " ".join(part for part in parts if part)
            applied.add((provider_id, model_id))

        for provider_id, provider in self._providers.items():
            for model_id, model in provider.get("models", {}).items():
                if (provider_id, model_id) not in applied:
                    model.setdefault("_price_source", snapshot_source)

    def model_price_source(self, provider_id: str, model_id: str) -> str:
        """Provenance of the price attached to one model entry."""

        model = self.get_model(provider_id, model_id)
        return str(model.get("_price_source") or self.price_source)

    def get_provider(self, provider_id: str) -> dict:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise LaneCatalogError(
                f"provider {provider_id!r} not in catalog",
                suggested_recovery=f"known providers: {', '.join(sorted(self._providers))}",
            )
        return provider

    def get_model(self, provider_id: str, model_id: str) -> dict:
        provider = self.get_provider(provider_id)
        model = provider["models"].get(model_id)
        if model is None:
            raise LaneCatalogError(
                f"model {model_id!r} not in provider {provider_id!r}",
                suggested_recovery=f"known models: {', '.join(sorted(provider['models'])[:10])}…",
            )
        return model


# --------------------------------------------------------------------------
# preset lanes（ADR-01 §1.1 用户 key 插槽；默认模型=2026-09 快照现价入选）
# --------------------------------------------------------------------------

LANE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "lane_id": "deepseek:chat:v1",
        "provider": "deepseek",
        "endpoint": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "credential_env_names": ("AUTORESEARCH_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY"),
        "thinking_format": "deepseek",
    },
    {
        "lane_id": "openai:chat:v1",
        "provider": "openai",
        "endpoint": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "credential_env_names": ("AUTORESEARCH_OPENAI_API_KEY", "OPENAI_API_KEY"),
        "thinking_format": "openai",
        "supports_strict_json_schema": True,
    },
    {
        # anthropic-messages transport 二期；目录/计价/档位映射先行（§4.4）
        "lane_id": "anthropic:messages:v1",
        "provider": "anthropic",
        "endpoint": "https://api.anthropic.com",
        "model": "claude-sonnet-4-5",
        "credential_env_names": ("AUTORESEARCH_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
        "thinking_format": None,
    },
    {
        "lane_id": "kimi:chat:v1",
        "provider": "moonshotai",
        "endpoint": "https://api.moonshot.cn/v1",
        "model": "kimi-k2.6",
        "credential_env_names": ("AUTORESEARCH_KIMI_API_KEY", "MOONSHOT_API_KEY"),
        "thinking_format": None,  # moonshot thinking format 未实现，首版 off
    },
    {
        "lane_id": "qwen:chat:v1",
        "provider": "alibaba",
        "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "credential_env_names": ("AUTORESEARCH_QWEN_API_KEY", "DASHSCOPE_API_KEY"),
        "thinking_format": None,  # qwen thinking format 未实现，首版 off
    },
    {
        "lane_id": "vllm:local:v1",
        "provider": "vllm-local",
        "endpoint": "http://localhost:8000/v1",
        "model": "local-model",
        "credential_env_names": (),
        "thinking_format": "openai",
        # No credential to check, but the budget is still derived and enforced:
        # an unbounded local lane is a spin loop, not a free run.
        "local_endpoint": True,
    },
)

PRESET_LANE_IDS: tuple[str, ...] = tuple(spec["lane_id"] for spec in LANE_SPECS)


def build_preset_lane(
    lane_id: str,
    *,
    catalog: ModelCatalog | None = None,
    budget_profile: LaneBudgetProfile | None = None,
    model_override: str | None = None,
) -> LaneIdentity:
    """Instantiate one preset lane from the vendored catalog (lazy, offline)."""
    spec = next((s for s in LANE_SPECS if s["lane_id"] == lane_id), None)
    if spec is None:
        raise LaneCatalogError(
            f"unknown preset lane {lane_id!r}",
            suggested_recovery=f"preset lanes: {', '.join(PRESET_LANE_IDS)}",
        )
    catalog = catalog if catalog is not None else load_default_catalog()
    model_id = model_override or spec["model"]
    model = catalog.get_model(spec["provider"], model_id)
    cost = ModelCost.from_dict(model["cost"])
    profile = (
        budget_profile
        or spec.get("budget_profile")
        or default_budget_profile(
            context_window=int(model["limit"]["context"]),
            max_output_tokens=int(model["limit"]["output"]),
            cost=cost,
            local_endpoint=bool(spec.get("local_endpoint", False)),
        )
    )
    return LaneIdentity(
        lane_id=lane_id,
        provider=spec["provider"],
        endpoint=spec["endpoint"],
        model=model_id,
        api_family=model["api_family"],
        cost=cost,
        context_window=int(model["limit"]["context"]),
        max_output_tokens=int(model["limit"]["output"]),
        reasoning_supported=bool(model["reasoning"]),
        credential_env_names=tuple(spec["credential_env_names"]),
        budget_profile=profile,
        thinking_format=spec.get("thinking_format"),
        supports_strict_json_schema=bool(spec.get("supports_strict_json_schema", False)),
        max_rounds=int(spec.get("max_rounds", 8)),
        price_source=catalog.model_price_source(spec["provider"], model_id),
    )


_DEFAULT_CATALOG: ModelCatalog | None = None


def load_default_catalog() -> ModelCatalog:
    global _DEFAULT_CATALOG
    if _DEFAULT_CATALOG is None:
        _DEFAULT_CATALOG = ModelCatalog.load()
    return _DEFAULT_CATALOG


# --------------------------------------------------------------------------
# credentials（openpilot 白名单模式：只读 lane 自己声明的 env 名）
# --------------------------------------------------------------------------


def credential_from_env(lane: LaneIdentity, environ: Mapping[str, str] | None = None) -> str | None:
    """Read only credential names explicitly owned by ``lane``, in order."""
    values = os.environ if environ is None else environ
    for name in lane.credential_env_names:
        value = values.get(name)
        if value and value.strip():
            return value
    return None


def require_credential(lane: LaneIdentity, environ: Mapping[str, str] | None = None) -> str:
    """Local lanes are exempt; everything else fails closed without a key."""
    if lane.budget_profile.local_endpoint:
        return ""
    credential = credential_from_env(lane, environ)
    if credential is None:
        raise LaneNotConfiguredError(
            f"provider lane {lane.lane_id} has no usable credential",
            suggested_recovery=(
                "set one of: " + ", ".join(lane.credential_env_names)
                if lane.credential_env_names
                else "configure a credential scope for this lane"
            ),
        )
    return credential


# --------------------------------------------------------------------------
# drift guard（openpilot validate_lane_settings → fail-closed + 字段清单）
# --------------------------------------------------------------------------

_DRIFT_FIELDS = (
    "provider",
    "endpoint",
    "model",
    "api_family",
    "max_rounds",
    "credential_env_names",
    "reasoning_supported",
    "max_cost_per_call_usd",
    "max_calls_per_run",
    "max_tokens_per_run",
)


def validate_lane_settings(lane: LaneIdentity, observed: Mapping[str, Any]) -> None:
    """Fail closed when observed settings drift from the lane identity.

    ``observed`` is built by the caller (transport 层在段 2 从 ``Settings``
    提取并触发 ``provider.lane_drift`` 审计事件；本函数只负责判定).
    Endpoint comparison tolerates trailing slashes.
    """
    mismatched: list[str] = []
    for name in _DRIFT_FIELDS:
        if name not in observed:
            continue
        observed_value = observed[name]
        if name == "endpoint":
            expected = lane.endpoint.rstrip("/")
            observed_value = str(observed_value).rstrip("/")
        elif name == "credential_env_names":
            expected = list(lane.credential_env_names)
        elif name in ("max_cost_per_call_usd", "max_calls_per_run", "max_tokens_per_run"):
            expected = getattr(lane.budget_profile, name)
        else:
            expected = getattr(lane, name)
        if observed_value != expected:
            mismatched.append(f"{name}={observed_value!r}!={expected!r}")
    if mismatched:
        raise LaneDriftError(
            f"settings do not match provider lane {lane.lane_id}: " + "; ".join(mismatched),
            suggested_recovery="align settings to the lane identity or select another lane",
        )


def lane_drift_event(lane: LaneIdentity, observed: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build the ``provider.lane_drift`` audit event for an observed drift.

    Returns ``None`` when the observed settings match the lane identity, so a
    caller can branch on the result. Deliberately a pure factory: this module
    owns no store and must not acquire one (R005 — no second Store, no bypass
    around Evidence/Policy), so the writer stays with the caller.

    Note (O12 self-review): no production caller wires this yet — a lane resolved
    from Settings is derived from the same source it would be checked against, so
    there is nothing to drift. It exists for the frozen-preset-lane consumers
    (A5/B6) that will hold a lane while Settings may move.
    """

    try:
        validate_lane_settings(lane, observed)
    except LaneDriftError as exc:
        return {
            "event": "provider.lane_drift",
            "lane_id": lane.lane_id,
            "provider": lane.provider,
            "model": lane.model,
            "detail": str(exc),
        }
    return None


# --------------------------------------------------------------------------
# budget guard（A5 评估纪律：固定预算 fail-closed）
# --------------------------------------------------------------------------


def check_call_budget(
    lane: LaneIdentity,
    *,
    estimated_cost_usd: float | None = None,
    estimated_tokens: int | None = None,
    calls_used: int = 0,
) -> None:
    """Raise when the dispatch would exceed the configured lane caps."""
    profile = lane.budget_profile
    cap = profile.max_cost_per_call_usd
    if cap is not None and estimated_cost_usd is not None and estimated_cost_usd > cap:
        raise LaneBudgetExceededError(
            f"lane {lane.lane_id} estimated cost ${estimated_cost_usd:.6f} exceeds "
            f"per-call cap ${cap:.6f}",
            suggested_recovery="reduce input size or raise the lane budget profile",
        )
    calls_cap = profile.max_calls_per_run
    if calls_cap is not None and calls_used + 1 > calls_cap:
        raise LaneBudgetExceededError(
            f"lane {lane.lane_id} call {calls_used + 1} exceeds run cap {calls_cap}",
            suggested_recovery="stop the run or raise max_calls_per_run",
        )
    tokens_cap = profile.max_tokens_per_run
    if tokens_cap is not None and estimated_tokens is not None and estimated_tokens > tokens_cap:
        raise LaneBudgetExceededError(
            f"lane {lane.lane_id} estimated tokens {estimated_tokens} exceed run cap {tokens_cap}",
            suggested_recovery="reduce input size or raise max_tokens_per_run",
        )


# --------------------------------------------------------------------------
# anthropic thinking params（两代规格，§4.4；messages transport 二期）
# --------------------------------------------------------------------------


def anthropic_thinking_params(
    level: ReasoningLevel,
    *,
    adaptive: bool,
    max_output_tokens: int | None = None,
) -> dict[str, Any] | None:
    """Map a reasoning level to Anthropic request params (None = off).

    - adaptive (Claude 4.6+): ``output_config.effort`` — native levels,
      xhigh/max clamp to high.
    - manual (Claude 4.5-): ``thinking.budget_tokens`` — min 1024, clamped
      below ``max_output_tokens`` when provided (thinking tokens are billed
      output tokens and count toward that limit).
    """
    if not _valid_level(level):
        raise ProviderLaneError(f"unknown reasoning level {level!r}")
    if level == "off":
        return None
    if adaptive:
        return {"output_config": {"effort": ANTHROPIC_ADAPTIVE_EFFORT[level]}}
    budget = ANTHROPIC_BUDGET_BY_LEVEL[level]
    if max_output_tokens is not None:
        budget = min(budget, max_output_tokens - 1)
    if budget < 1024:
        raise ProviderLaneError(
            f"anthropic thinking budget clamped below the 1024 minimum "
            f"(max_output_tokens={max_output_tokens})",
            suggested_recovery="raise max_output_tokens above 1024",
        )
    return {"thinking": {"type": "enabled", "budget_tokens": budget}}


# --------------------------------------------------------------------------
# S2.3 handoff（pi-ai transform-messages 语义：跨模型/跨 provider 四规则）
# --------------------------------------------------------------------------

_TOOL_ID_SANITIZE = re.compile(r"[^a-zA-Z0-9_-]")


def normalize_tool_call_id(call_id: str) -> str:
    """pi-ai normalizeToolCallId: 非法字符→``_``，截断 64（Anthropic 约束）。"""
    return _TOOL_ID_SANITIZE.sub("_", str(call_id))[:64]


def degrade_images_for_non_vision(message: dict) -> dict:
    """非视觉模型的图片块降级为占位文本（pi-ai 同语义，保内容可追溯）。"""
    out = json.loads(json.dumps(message))  # deep copy without aliasing
    content = out.get("content")
    if not isinstance(content, list):
        return out
    rebuilt = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "image":
            rebuilt.append(
                {"type": "text", "text": "(image omitted: model does not support images)"}
            )
        else:
            rebuilt.append(block)
    out["content"] = rebuilt
    return out


def synthesize_orphan_tool_results(messages: list[dict]) -> list[dict]:
    """assistant tool_calls 缺对应 tool 结果时补合成结果（防 provider 422）。"""
    answered: set[str] = set()
    for message in messages:
        if message.get("role") == "tool":
            call_id = message.get("tool_call_id")
            if call_id:
                answered.add(str(call_id))
    out = [dict(m) for m in messages]
    synthetic: list[dict] = []
    for index, message in enumerate(out):
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            call_id = str(call.get("id") or "")
            if call_id and call_id not in answered:
                synthetic.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": "(no tool result recorded)",
                        "_synthesized": True,
                        "_after_index": index,
                    }
                )
                answered.add(call_id)
    if not synthetic:
        return out
    merged: list[dict] = []
    for index, message in enumerate(out):
        merged.append(message)
        for item in synthetic:
            if item["_after_index"] == index:
                merged.append({k: v for k, v in item.items() if not k.startswith("_")})
    return merged


def convert_thinking_for_cross_model(messages: list[dict]) -> list[dict]:
    """跨模型 handoff：thinking 块降级为 text（有损、保留文本）；redacted 丢弃。

    同模型 replay 不走本函数（thinkingSignature 原样保留）。
    """
    out = []
    for message in messages:
        message = dict(message)
        content = message.get("content")
        if isinstance(content, list):
            rebuilt = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    if block.get("redacted"):
                        continue
                    text = block.get("thinking") or block.get("text") or ""
                    rebuilt.append({"type": "text", "text": text})
                else:
                    rebuilt.append(block)
            message["content"] = rebuilt
        out.append(message)
    return out


# --------------------------------------------------------------------------
# S2.4 constrained sampling（pi-ai constrained-sampling 降级矩阵）
# --------------------------------------------------------------------------


def make_strict_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """pi-ai makeStrictJsonSchema 三规则：补 additionalProperties:false、
    全量 required、nullable→anyOf[type, null]。返回净化后的深拷贝。"""
    out = json.loads(json.dumps(dict(schema)))

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        node = dict(node)
        if node.get("type") == "object" or "properties" in node:
            properties = node.get("properties") or {}
            node["properties"] = {key: walk(value) for key, value in properties.items()}
            node["additionalProperties"] = False
            node["required"] = sorted(node["properties"])
        elif node.get("type") == "array":
            if "items" in node:
                node["items"] = walk(node["items"])
        node_type = node.get("type")
        if isinstance(node_type, list) and "null" in node_type:
            # pi-ai makeStrictJsonSchema: type 数组 → anyOf（保留 null 分支）
            node = {"anyOf": [{"type": t} for t in node_type]}
        for key, value in list(node.items()):
            if key in ("type", "properties", "required", "additionalProperties", "items", "anyOf"):
                continue
            skip_walk = key in ("enum", "const", "default", "description")
            if isinstance(value, (dict, list)) and not skip_walk:
                node[key] = walk(value)
        return node

    return walk(out)


def resolve_response_format(lane: LaneIdentity, request: LaneRequest) -> dict[str, Any] | None:
    """§4.5 降级矩阵：strict=require + 不支持 → 显式抛错（fail fast）；
    prefer 永不抛，最多降级为 json_object。"""
    if request.json_schema is None:
        return None
    if lane.supports_strict_json_schema:
        strict = make_strict_json_schema(request.json_schema)
        return {
            "type": "json_schema",
            "json_schema": {"name": "response", "strict": True, "schema": strict},
        }
    if request.strict == "require":
        raise LaneStrictError(
            f"lane {lane.lane_id} does not support strict json_schema "
            f"but strict=require was requested",
            suggested_recovery=(
                'use strict="prefer" (degrades to json_object) '
                "or pick a lane that supports it"
            ),
        )
    return {"type": "json_object"}


# --------------------------------------------------------------------------
# S2.2 request/result/transport（pi-ai 语义，同步 httpx）
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LaneRequest:
    system: str
    user: str
    temperature: float = 0.2
    reasoning_level: ReasoningLevel = "off"
    json_mode: bool = False  # bare {"type": "json_object"} request, no schema
    json_schema: Mapping[str, Any] | None = None
    strict: str = "prefer"  # "prefer" | "require"
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        if not _valid_level(self.reasoning_level):
            raise ProviderLaneError(f"unknown reasoning level {self.reasoning_level!r}")
        if self.strict not in ("prefer", "require"):
            raise ProviderLaneError("strict must be 'prefer' or 'require'")


@dataclass(frozen=True)
class LaneResult:
    text: str
    lane_id: str
    model: str
    usage: Usage
    usage_cost: UsageCost
    raw: Mapping[str, Any]
    # How many HTTP attempts it took to obtain this result (1 = first try).
    # Recorded so a receipt can state the upper bound of what the call cost: a
    # failed retry is usually not billed, but a 5xx can arrive after the provider
    # already accepted the request.
    attempts: int = 1


class LaneTransportError(ProviderLaneError):
    """Transport-level failure; ``retryable`` drives the retry policy."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)


class LaneResponseError(LaneTransportError):
    """The provider answered, but the payload could not be read.

    A 2xx whose body is not JSON, whose ``usage`` block is missing or unusable,
    or whose ``choices`` have the wrong shape is a *deterministic* verdict, so
    this is never retryable -- retrying only pays for the same answer twice.

    It subclasses ``LaneTransportError`` so callers that already catch transport
    failures keep working, while a caller that wants to tell "the request failed"
    apart from "the answer was garbage" can catch this one.
    """

    def __init__(self, message: str, *, suggested_recovery: str | None = None) -> None:
        self.suggested_recovery = suggested_recovery
        if suggested_recovery:
            message = f"{message} (recovery: {suggested_recovery})"
        super().__init__(message, retryable=False)


_RETRYABLE_STATUS = frozenset({408, 429})


def is_retryable_status(status_code: int) -> bool:
    """pi-ai retry 分类：overloaded/429/5xx/network 可重试；其余 fail fast。"""
    return status_code in _RETRYABLE_STATUS or status_code >= 500


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay_ms: float = 500.0
    max_delay_ms: float = 60_000.0

    def delay_seconds(self, attempt: int) -> float:
        delay_ms = min(self.base_delay_ms * (2**attempt), self.max_delay_ms)
        return delay_ms / 1000.0


_OPENAI_EFFORT: dict[str, str] = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}


def build_openai_completions_payload(lane: LaneIdentity, request: LaneRequest) -> dict[str, Any]:
    """OpenAI-compatible chat.completions payload（含档位映射与 sampling 矩阵）。"""
    payload: dict[str, Any] = {
        "model": lane.model,
        "temperature": request.temperature,
        "messages": [
            {"role": "system", "content": request.system},
            {"role": "user", "content": request.user},
        ],
    }
    response_format = resolve_response_format(lane, request)
    if response_format is None and request.json_mode:
        # No schema supplied: ask for a bare json_object, matching the legacy
        # llm.py boundary that this lane replaces.
        response_format = {"type": "json_object"}
    if response_format is not None:
        payload["response_format"] = response_format
    level = request.reasoning_level
    if level != "off":
        if not lane.reasoning_supported:
            raise ProviderLaneError(
                f"lane {lane.lane_id} model does not support reasoning",
                suggested_recovery="request reasoning_level='off' or pick a reasoning lane",
            )
        if lane.thinking_format == "openai":
            payload["reasoning_effort"] = _OPENAI_EFFORT[level]
        elif lane.thinking_format == "deepseek":
            payload["thinking"] = {"type": "enabled", "effort": level}
        else:
            raise ProviderLaneError(
                f"lane {lane.lane_id} has no reasoning mapping (format={lane.thinking_format!r})",
                suggested_recovery="request reasoning_level='off' or extend the format table",
            )
    return payload


def normalize_usage_openai(raw: Mapping[str, Any]) -> Usage:
    """provider 原生 usage → 归一化 Usage。

    OpenAI/deepseek 的 ``prompt_tokens`` *包含* 命中缓存的 token：缓存命中的
    部分按 cache_read 计价、其余按 input 计价（pi-ai 同口径）。

    Every failure mode below is the *provider's* payload being unusable, so it is
    reported as ``LaneResponseError``. Left unguarded, ``int("n/a")`` raises a
    bare ``ValueError`` and a non-mapping ``usage`` / ``*_details`` a bare
    ``AttributeError`` -- neither of which a caller honouring this module's error
    contract would catch.
    """
    if not isinstance(raw, Mapping):
        raise LaneResponseError(
            f"usage block must be an object, got {type(raw).__name__}",
            suggested_recovery="record the model as unpriced (cost=None) rather than a cost of 0",
        )
    try:
        prompt = int(raw.get("prompt_tokens") or 0)
        completion = int(raw.get("completion_tokens") or 0)
        details = raw.get("prompt_tokens_details") or {}
        cached = int(details.get("cached_tokens") or 0)
        cached = int(raw.get("prompt_cache_hit_tokens") or cached)  # deepseek 原生字段
        cache_write = int(raw.get("cache_creation_input_tokens") or 0)  # anthropic 形状透传
        reasoning_details = raw.get("completion_tokens_details") or {}
        reasoning = int(reasoning_details.get("reasoning_tokens") or 0)
        return Usage(
            input_tokens=max(prompt - cached, 0),
            output_tokens=completion,
            cache_read_tokens=cached,
            cache_write_tokens=cache_write,
            reasoning_tokens=reasoning,
        )
    except ProviderLaneError:
        # ``Usage.__post_init__`` already fails closed on negative counts; keep its
        # more specific message rather than flattening it into a parse error.
        raise
    except (TypeError, ValueError, AttributeError, KeyError) as exc:
        raise LaneResponseError(
            f"provider usage block is unreadable: {exc!r}",
            suggested_recovery="record the model as unpriced (cost=None) rather than a cost of 0",
        ) from exc


@dataclass
class LaneRunLedger:
    """Per-*run* budget counters, shared by every transport serving that run.

    The counters used to live on the transport instance, and both consumers of a
    lane build their own transport (`lane_llm_adapter.py`, `llm.py`), so a single
    run's budget was silently multiplied by the number of transports that
    happened to exist. A caller that wants a genuine per-run budget passes one
    ledger to every transport it builds; a transport built without one gets its
    own, which is the right scope for one call or a unit test.

    ``requests_made`` counts *network requests*, not successful completions. The
    budget protects the provider's quota and the operator's bill, so a run stuck
    on retries has to consume it -- counting only successes would let a
    permanently-429 lane retry forever without ever reaching its cap.
    """

    requests_made: int = 0
    calls_completed: int = 0
    spent_usd: float = 0.0
    spent_tokens: int = 0


class LaneTransport:
    """Sync OpenAI-compatible transport for one lane (段 2，S2.2)。

    - 构造即验凭据（白名单 → fail-closed）。
    - retry：429/5xx/网络错误按 RetryPolicy 指数退避；401/403/422 等 fail fast。
    - 预算：**每次网络请求前**查 per-run 请求上限（重试同样计入），事后累计
      cost/tokens，超限 fail-closed；计数器挂在 :class:`LaneRunLedger` 上，
      同一 run 的多个 transport 共享一个 ledger 才构成真正的 per-run 预算。
    - post-call 计价：provider usage → 归一化 → 快照价 → LaneResult。
    - anthropic-messages 族 transport 二期（目录/计价/档位已就绪）。
    """

    def __init__(
        self,
        lane: LaneIdentity,
        *,
        environ: Mapping[str, str] | None = None,
        credential: str | None = None,
        client: Any = None,
        sleep: Any = time.sleep,
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float = 45.0,
        ledger: LaneRunLedger | None = None,
    ) -> None:
        if lane.api_family != "openai-completions":
            raise ProviderLaneError(
                f"api_family {lane.api_family!r} transport lands in 段 3 (messages 二期)"
            )
        self.lane = lane
        # An explicitly supplied credential wins over the env whitelist: the
        # settings-backed facade (llm.py) holds the key as a SecretStr rather
        # than publishing it as an env var, and must not be double-scoped.
        # A blank credential counts as "not supplied": it must fail closed (or be
        # exempted for a local endpoint) instead of shipping an empty Bearer.
        supplied = credential.strip() if credential is not None else ""
        self.credential = supplied if supplied else require_credential(lane, environ)
        self._client = client
        self._sleep = sleep
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout_seconds = timeout_seconds
        # Per-run budget counters (A5 evaluation discipline: a fixed call budget
        # must be *enforced*, not merely declared in the profile). Pass a shared
        # ledger to make the scope genuinely per-run; the default is one ledger
        # per transport, which is correct for a single call or a unit test.
        self.ledger = ledger if ledger is not None else LaneRunLedger()

    @property
    def calls_made(self) -> int:
        """Budgeted calls; equal to network requests (see ``LaneRunLedger``)."""

        return self.ledger.requests_made

    @property
    def spent_usd(self) -> float:
        return self.ledger.spent_usd

    @property
    def spent_tokens(self) -> int:
        return self.ledger.spent_tokens

    def _endpoint(self) -> str:
        return self.lane.endpoint.rstrip("/") + "/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.credential:
            headers["Authorization"] = f"Bearer {self.credential}"
        return headers

    def complete(self, request: LaneRequest) -> LaneResult:
        payload = build_openai_completions_payload(self.lane, request)
        ledger = self.ledger
        attempts = 0

        def _dispatch(_attempt: int) -> dict[str, Any]:
            nonlocal attempts
            # Fail closed *before* every network request, retries included: the
            # budget protects the provider's quota, so an attempt that would
            # exceed the cap must never leave the process.
            check_call_budget(self.lane, calls_used=ledger.requests_made)
            ledger.requests_made += 1
            attempts += 1
            return self._post(payload)

        raw = retry_with_backoff(_dispatch, policy=self.retry_policy, sleep=self._sleep)
        try:
            text = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LaneResponseError(
                "malformed chat completion response: missing choices[0].message.content",
                suggested_recovery="inspect the raw payload; it did not match the api_family shape",
            ) from exc
        usage = normalize_usage_openai(raw.get("usage") or {})
        usage_cost = calculate_cost(usage, self.lane.cost)

        # Accumulate the run budget. A per-call cost cap can only be judged after
        # the provider reports usage (there is no token estimator yet), so it — and
        # the per-run token cap — stop the run rather than pretend to pre-empt it.
        profile = self.lane.budget_profile
        ledger.calls_completed += 1
        ledger.spent_usd += usage_cost.total
        ledger.spent_tokens += (
            usage.input_tokens
            + usage.output_tokens
            + usage.cache_read_tokens
            + usage.cache_write_tokens
        )
        if profile.max_cost_per_call_usd is not None and (
            usage_cost.total > profile.max_cost_per_call_usd
        ):
            raise LaneBudgetExceededError(
                f"lane {self.lane.lane_id} call cost ${usage_cost.total:.6f} exceeds "
                f"per-call cap ${profile.max_cost_per_call_usd:.6f}",
                suggested_recovery="raise max_cost_per_call_usd or shrink the prompt",
            )
        if profile.max_tokens_per_run is not None and (
            ledger.spent_tokens > profile.max_tokens_per_run
        ):
            raise LaneBudgetExceededError(
                f"lane {self.lane.lane_id} run tokens {ledger.spent_tokens} exceed "
                f"cap {profile.max_tokens_per_run}",
                suggested_recovery="raise max_tokens_per_run or stop the run",
            )

        return LaneResult(
            text=text,
            lane_id=self.lane.lane_id,
            model=self.lane.model,
            usage=usage,
            usage_cost=usage_cost,
            raw={"id": raw.get("id"), "usage": raw.get("usage")},
            attempts=attempts,
        )

    def _post(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        import httpx

        try:
            if self._client is not None:
                response = self._client.post(
                    self._endpoint(), headers=self._headers(), json=payload
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(self._endpoint(), headers=self._headers(), json=payload)
        except httpx.TransportError as exc:
            raise LaneTransportError(f"network error: {exc}", retryable=True) from exc
        if response.status_code >= 400:
            raise LaneTransportError(
                f"provider returned HTTP {response.status_code}: {response.text[:200]}",
                status_code=response.status_code,
                retryable=is_retryable_status(response.status_code),
            )
        try:
            payload = response.json()
        except ValueError as exc:  # json.JSONDecodeError subclasses ValueError
            raise LaneResponseError(
                f"provider returned HTTP {response.status_code} with a non-JSON body: "
                f"{response.text[:200]}",
                suggested_recovery="inspect the raw body; a gateway or proxy may be answering",
            ) from exc
        if not isinstance(payload, dict):
            raise LaneResponseError(
                f"provider returned HTTP {response.status_code} with a "
                f"{type(payload).__name__} body where an object was expected",
                suggested_recovery="check that the endpoint points at the chat-completions API",
            )
        return payload


def retry_with_backoff(fn: Any, *, policy: RetryPolicy, sleep: Any) -> Any:
    """pi-ai retryAssistantCall 语义：指数退避 + 可重试分类 + abort 不重试。"""
    last_error: LaneTransportError | None = None
    for attempt in range(policy.max_retries + 1):
        try:
            return fn(attempt)
        except LaneTransportError as exc:
            last_error = exc
            if not exc.retryable or attempt == policy.max_retries:
                raise
            sleep(policy.delay_seconds(attempt))
    raise last_error if last_error else ProviderLaneError("retry loop exited without result")


# --------------------------------------------------------------------------
# S2.5 receipt 计价字段（O12 → A 线 invocation receipt，PLAN §4.2 字段名）
# --------------------------------------------------------------------------


def receipt_usage_fields(
    result: LaneResult, *, price_source: str | None = None
) -> dict[str, Any]:
    """Build the ``tokens`` / ``cost`` receipt blocks for a lane result.

    Returns ``{"tokens": {...}, "cost": {...}}`` using the shared
    ``TokenUsage`` / ``InvocationCost`` field names, so a receipt can be filled
    without O12 importing the receipt module (one-way dependency). ``reasoning``
    is a subset of ``output`` and is recorded for transparency only — it is
    never priced separately (pi-ai semantics).
    """

    usage, cost = result.usage, result.usage_cost
    return {
        "tokens": {
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "cache_read": usage.cache_read_tokens,
            "cache_write": usage.cache_write_tokens,
            "reasoning": usage.reasoning_tokens,
        },
        "cost": {
            "input": cost.input,
            "output": cost.output,
            "cache_read": cost.cache_read,
            "cache_write": cost.cache_write,
            "total": cost.total,
            "currency": "USD",
            "model": result.model,
            "lane_id": result.lane_id,
            "attempts": result.attempts,
            "price_source": price_source,
        },
    }


# --------------------------------------------------------------------------
# selftest（S1.1 验收入口：catalog schema + 六条 preset lane 实例化）
# --------------------------------------------------------------------------


def selftest_catalog(*, catalog_path: str | Path | None = None) -> list[str]:
    catalog = ModelCatalog.load(catalog_path)
    if catalog._meta.get("license") != "MIT":
        raise LaneCatalogError("catalog snapshot provenance must record the MIT license")
    if "models.dev" not in str(catalog._meta.get("source", "")):
        raise LaneCatalogError("catalog snapshot provenance must point at models.dev")
    lines: list[str] = []
    for lane_id in PRESET_LANE_IDS:
        lane = build_preset_lane(lane_id, catalog=catalog)
        lines.append(
            f"OK {lane.lane_id} provider={lane.provider} model={lane.model} "
            f"endpoint={lane.endpoint} api={lane.api_family} "
            f"context={lane.context_window} max_out={lane.max_output_tokens} "
            f"reasoning={lane.reasoning_supported} "
            f"cost_in=${lane.cost.input}/1M cost_out=${lane.cost.output}/1M "
            f"env={','.join(lane.credential_env_names) or '-'}"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--catalog" not in argv:
        print("usage: python -m autoresearch.provider_lane --catalog", file=sys.stderr)
        return 2
    try:
        for line in selftest_catalog():
            print(line)
    except ProviderLaneError as exc:
        print(f"SELFTEST FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"selftest passed: {len(PRESET_LANE_IDS)} preset lanes instantiated offline")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(main())
