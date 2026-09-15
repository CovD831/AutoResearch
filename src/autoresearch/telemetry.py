"""K13 ``TelemetryPoint`` + M15-02 log redaction + M15-04 metric interruption.

Contract: ``docs/rearchitecture/R007-parallel-modules/04-l2-contracts.md`` K13.

The single discipline this module exists to enforce, in four places:

* **K13-1 ``value=None`` means NOT MEASURED -- never ``0``.**
  :attr:`TelemetryPoint.value` is ``float | None`` and a ``None`` is never
  coerced to a zero.  ``0`` means "we measured, and it was zero"; ``None`` means
  "we did not measure".  Collapsing the two is this repository's most-repeated
  defect family (O12 ``_recurrence_count``; PR #20's ``except: return 0`` which
  made the promotion threshold *silently never* pass).

  The same discipline is pushed one step further: :attr:`TelemetryPoint.breaches_threshold`
  is ``bool | None``, so "there is a threshold but we never measured a value" is
  ``None`` -- **not** ``False``.  A caller that writes ``if point.breaches_threshold:``
  silently reads ``None`` as "fine"; :meth:`TelemetrySink.record` therefore does
  not use truthiness either, and files such points under
  :attr:`TelemetrySink.unmeasured` where they are visible instead of silent.

* **K13-2 ``cost_usd`` is ``None`` when no price table matched** (TASK-SPECS:63).
  :func:`cost_usd_point` takes the O12 caliber verbatim: ``price_source is None``
  is the *same condition* as "cannot be priced"
  (``provider_lane.py:388-424``), and ``attempts`` folds in as the honest upper
  bound exactly as ``provider_lane.receipt_usage_fields`` does (``:1630``).

* **K13-3 no prompt / full text / token / secret is ever recorded.**  Enforced by
  a **field whitelist** (only ``project``/``run``/``node``/``agent``/``gate`` may
  appear in ``dimensions``) plus a content scan over the values, and by refusing
  ``redacted=False`` outright: this module only emits redacted points.  There is
  deliberately no free-text field to leak into -- a schema with nowhere to put a
  prompt cannot record one.

* **K13-4 over-threshold raises an interrupt.**  A breach raises
  :class:`TelemetryInterrupt` and is kept in :attr:`TelemetrySink.breaches`.

.. note::
   **K13-4 is realised as an exception, not as a langgraph interrupt.**  Wiring
   this to the graph's interrupt mechanism belongs to the caller (M15-04's
   integration), which is outside this module's exclusive file surface.  See
   ``L3.md`` §4 D-L09-08 -- this is a registered deviation, not a claim that the
   graph interrupt fires.

**K1 interop (no import).**  ``dimensions["run"]`` must reference
``RunManifest.run_id`` (``07-lane-kickoff-convention.md`` §3.3) -- it must not be
a self-invented identifier.  This module accepts either the ``run_id`` string or
any object exposing ``.run_id`` (K1's ``RunManifest`` satisfies that), following
the one-way-dependency pattern already used by
``provider_lane.receipt_usage_fields``.  Importing ``autoresearch.run_manifest``
here would make this module un-importable wherever K1 is not on the path, so the
dependency is kept structural instead of syntactic.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from autoresearch.contracts import new_id, utc_now
from autoresearch.pii import default_scanner

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


class Metric(StrEnum):
    """The five metrics K13 names."""

    BLOCKED = "blocked"
    DENIED = "denied"
    RETRY = "retry"
    LATENCY_MS = "latency_ms"
    COST_USD = "cost_usd"


#: K13-3 field whitelist.  ``dimensions`` may carry **only** these keys, which is
#: what makes "no prompt / full text / token / secrets" a schema property rather
#: than a promise: there is no key to smuggle content through.
DIMENSION_KEYS: frozenset[str] = frozenset({"project", "run", "node", "agent", "gate"})

#: Dimension values are identifiers, never prose.  A prompt or a document body
#: contains newlines and runs long, so both are rejected before they can be
#: recorded (K13-3, "不得记录 prompt / 全文").
MAX_DIMENSION_VALUE = 200

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),  # OpenAI-style API key
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),  # GitHub token
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack token
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{8,}=*"),  # Authorization header value
    re.compile(r"(?i)\b(api[_-]?key|apikey|secret|password|passwd|token|bearer)\b\s*[:=]"),
)


@runtime_checkable
class _RunLike(Protocol):
    """Structural stand-in for K1 ``RunManifest`` (never imported -- see module docstring)."""

    run_id: str


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TelemetryError(ValueError):
    """Base class for K13 failures."""


class SensitiveDimension(TelemetryError):
    """A dimension value carried content that must never be recorded (K13-3)."""


class TelemetryInterrupt(TelemetryError):
    """K13-4: a metric crossed its threshold; the caller must interrupt."""


# ---------------------------------------------------------------------------
# The point
# ---------------------------------------------------------------------------


class TelemetryPoint(BaseModel):
    """One metric sample (K13).

    ``value is None`` is a first-class, honest state: the metric was not measured.
    No validator, factory or helper in this module will substitute ``0`` for it.
    """

    point_id: str = Field(default_factory=lambda: new_id("tp"))
    metric: Metric
    dimensions: dict[str, str] = Field(default_factory=dict)
    #: K13-1: ``None`` = 未测.  Never a stand-in zero.
    value: float | None = None
    threshold: float | None = None
    #: K13-3: this module only ever emits redacted points; ``False`` is refused.
    redacted: bool = True
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _whitelist_and_scan_dimensions(self) -> TelemetryPoint:
        unknown = sorted(set(self.dimensions) - DIMENSION_KEYS)
        if unknown:
            # K13-3: the whitelist is the mechanism, so it fails closed on anything
            # outside it rather than dropping the offenders silently.
            raise ValueError(
                f"dimensions may only use {sorted(DIMENSION_KEYS)}; got {unknown} "
                "(K13-3: a non-whitelisted key is how a prompt or a secret would travel)"
            )
        for key, raw in self.dimensions.items():
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError(f"dimension {key!r} must be a non-empty string")
            if len(raw) > MAX_DIMENSION_VALUE:
                raise ValueError(
                    f"dimension {key!r} is {len(raw)} chars (>{MAX_DIMENSION_VALUE}); "
                    "dimension values are identifiers, never full text (K13-3)"
                )
            if "\n" in raw or "\r" in raw:
                raise ValueError(
                    f"dimension {key!r} contains a newline; that is document/prompt "
                    "content, not an identifier (K13-3)"
                )
            for pattern in _SECRET_PATTERNS:
                if pattern.search(raw):
                    raise ValueError(
                        f"dimension {key!r} matches a secret/token pattern; "
                        "secrets must never be recorded (K13-3)"
                    )
            if default_scanner(raw):
                raise ValueError(
                    f"dimension {key!r} matches a personal-data pattern; "
                    "identifiers must not carry PII (K13-3)"
                )
        if self.redacted is not True:
            raise ValueError(
                "this module only emits redacted points; redacted=False is refused (K13-3)"
            )
        return self

    @property
    def measured(self) -> bool:
        """``False`` when ``value is None`` -- i.e. the metric was never measured."""
        return self.value is not None

    @property
    def breaches_threshold(self) -> bool | None:
        """``True`` / ``False`` / **``None`` when it cannot be decided**.

        * ``threshold is None`` -> ``False``: no limit was configured;
        * ``value is None`` -> **``None``**: a limit exists but nothing was
          measured, so "did it exceed?" is *unknown*.  This is deliberately not
          ``False`` -- ``False`` would read as "it was fine".
        """
        if self.threshold is None:
            return False
        if self.value is None:
            return None
        return self.value > self.threshold


# ---------------------------------------------------------------------------
# Run identity (K1 linkage, structural)
# ---------------------------------------------------------------------------


def run_id_of(run: str | _RunLike | None) -> str | None:
    """Resolve ``dimensions["run"]`` from a K1 ``RunManifest`` or a plain ``run_id``.

    Accepts a string or any object with ``.run_id`` -- so ``RunManifest`` works
    without this module importing it.  A blank id is rejected: an empty run
    dimension would look like "no run" while actually meaning "we lost the id".
    """
    if run is None:
        return None
    resolved = run if isinstance(run, str) else getattr(run, "run_id", None)
    if not isinstance(resolved, str):
        raise TelemetryError(
            f"run must be a run_id string or expose .run_id (K1 RunManifest); got {type(run)!r}"
        )
    if not resolved.strip():
        raise TelemetryError("run_id must be non-empty (K1 linkage, §3.3)")
    return resolved


def dimensions_for(
    *,
    project: str | None = None,
    run: str | _RunLike | None = None,
    node: str | None = None,
    agent: str | None = None,
    gate: str | None = None,
) -> dict[str, str]:
    """Build a whitelisted ``dimensions`` mapping, dropping the unset keys."""
    resolved = {
        "project": project,
        "run": run_id_of(run),
        "node": node,
        "agent": agent,
        "gate": gate,
    }
    return {key: value for key, value in resolved.items() if value is not None}


# ---------------------------------------------------------------------------
# Factories (the K13-2 cost caliber lives here)
# ---------------------------------------------------------------------------


def cost_usd_point(
    *,
    total: float | None,
    price_source: str | None,
    attempts: int = 1,
    threshold: float | None = None,
    project: str | None = None,
    run: str | _RunLike | None = None,
    node: str | None = None,
    agent: str | None = None,
    gate: str | None = None,
) -> TelemetryPoint:
    """A ``cost_usd`` point using the O12 caliber (K13-2).

    ``price_source is None`` means **no price table matched the model**, which is
    the same condition as "this call cannot be priced"
    (``provider_lane.py:388-424``).  In that case ``value`` is ``None`` --
    **never ``0.0``**: a zero rate and an unknown rate are indistinguishable in a
    receipt, and only one of them is true (D-O12-14).

    ``attempts`` folds in as the upper bound (``total x attempts``), matching
    ``provider_lane.receipt_usage_fields``.  It is **not** a dimension: K13-3's
    whitelist is fixed at the five contract keys, so the multiplier is carried in
    the value and in this function's contract, not in ``dimensions``.
    """
    if attempts < 1:
        raise TelemetryError("attempts must be >= 1 (1 = first try)")
    value: float | None = None if price_source is None or total is None else total * attempts
    return TelemetryPoint(
        metric=Metric.COST_USD,
        dimensions=dimensions_for(
            project=project, run=run, node=node, agent=agent, gate=gate
        ),
        value=value,
        threshold=threshold,
    )


# .. note:: **Deliberately no ACL adapter here.**
#    K11-2 requires a denial to be observable and K13 offers the ``denied``
#    metric, so an adapter looks like the obvious join -- but it cannot be
#    written honestly: K13's dimension whitelist is exactly
#    ``project``/``run``/``node``/``agent``/``gate``, and a denial's
#    ``resource_kind`` / ``resource_id`` / ``reason`` have no key to live in.
#    Stuffing them into ``gate`` would record a *wrong* dimension, which is worse
#    than recording none.  The join is therefore left to the caller, and the
#    whitelist gap is reported as a contract observation (see ``L3.md`` §4
#    D-L09-09) rather than worked around silently.


# ---------------------------------------------------------------------------
# M15-02: log redaction (pure functions, wiring-ready)
# ---------------------------------------------------------------------------

#: Keys whose values are replaced wholesale in a health report.
_REDACT_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "secret",
        "password",
        "passwd",
        "credential",
        "authorization",
        "prompt",
        "content",
        "full_text",
        "text",
    }
)

REDACTED = "***redacted***"


def redact_value(key: str, value: object) -> object:
    """Redact one (key, value) pair for logging.

    Two independent rules, because either alone leaks:

    * **key rule** -- a sensitive *name* is redacted whatever it holds;
    * **content rule** -- a value that *looks* like a secret (or carries PII,
      reusing :func:`autoresearch.pii.default_scanner`) is redacted whatever it
      is called.

    Long values are truncated: a prompt or a document body is not a loggable
    field, and truncation at least bounds the leak even when no pattern matches.
    """
    if key.strip().lower() in _REDACT_KEYS:
        return REDACTED
    text = str(value)
    if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        return REDACTED
    if default_scanner(text):
        return REDACTED
    if len(text) > MAX_DIMENSION_VALUE:
        return text[:MAX_DIMENSION_VALUE] + f"...<truncated {len(text)} chars>"
    return value


def redact_health_report(report: dict[str, object]) -> dict[str, object]:
    """Redact a ``doctor()``-shaped mapping (M15-02).

    ``AutoResearchApplication.doctor()`` (``application.py:432``, signature
    ``def doctor(self) -> dict[str, Any]``) already returns a
    ``settings.safe_summary()``; this function is the reusable redaction step the
    wiring can call on top of it.  It is a pure function on purpose: the wiring
    lives in ``application.py``, which is outside this lane's exclusive file
    surface (L3 §4 D-L09-07).
    """
    return {key: redact_value(key, value) for key, value in report.items()}


def doctor_diagnostics(report: dict[str, object]) -> list[str]:
    """Human-readable diagnostics for a health report, with redaction applied.

    Emits one line per *non-healthy* signal so the log carries the reason rather
    than a bare boolean.  Never includes a value that
    :func:`redact_value` would redact.
    """
    redacted = redact_health_report(report)
    diagnostics: list[str] = []
    if redacted.get("ok") is not True:
        diagnostics.append(f"doctor: ok={redacted.get('ok')!r} (not healthy)")
    for key in ("database_ready", "projects_dir_exists", "template_dir_exists"):
        if key in redacted and redacted[key] is not True:
            diagnostics.append(f"doctor: {key}={redacted[key]!r}")
    return diagnostics


# ---------------------------------------------------------------------------
# M15-04: the sink
# ---------------------------------------------------------------------------


class ThresholdBreach(BaseModel):
    """One recorded threshold crossing (K13-4)."""

    breach_id: str = Field(default_factory=lambda: new_id("breach"))
    point_id: str
    metric: Metric
    value: float
    threshold: float
    dimensions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class TelemetrySink:
    """Collects points, surfaces breaches, and never hides an unmeasured alert.

    Counterpart of :class:`autoresearch.acl.AccessPolicyStore`'s denial log: the
    point of both is that a refusal or a gap is *observable*, not silent.
    """

    def __init__(self, *, interrupt_on_breach: bool = True) -> None:
        self._points: list[TelemetryPoint] = []
        self._breaches: list[ThresholdBreach] = []
        self._unmeasured: list[TelemetryPoint] = []
        self._interrupt_on_breach = interrupt_on_breach

    @property
    def points(self) -> tuple[TelemetryPoint, ...]:
        return tuple(self._points)

    @property
    def breaches(self) -> tuple[ThresholdBreach, ...]:
        return tuple(self._breaches)

    @property
    def unmeasured(self) -> tuple[TelemetryPoint, ...]:
        """Points that carry a threshold but no measured value.

        These are **not** passes and **not** breaches -- they are gaps.  Keeping
        them in their own list is what stops ``None`` from being read as "fine"
        by a downstream aggregation.
        """
        return tuple(self._unmeasured)

    def record(self, point: TelemetryPoint) -> TelemetryPoint:
        """Record a point; raise :class:`TelemetryInterrupt` on a real breach.

        Branching is explicit (``is True`` / ``is None``) rather than truthy --
        a truthiness check would silently treat the unmeasured ``None`` as "ok",
        which is the defect K13-1 exists to block.
        """
        self._points.append(point)
        breach = point.breaches_threshold
        if breach is None:
            self._unmeasured.append(point)
        elif breach is True:
            record = ThresholdBreach(
                point_id=point.point_id,
                metric=point.metric,
                value=float(point.value),  # type: ignore[arg-type]
                threshold=float(point.threshold),  # type: ignore[arg-type]
                dimensions=dict(point.dimensions),
            )
            self._breaches.append(record)
            if self._interrupt_on_breach:
                raise TelemetryInterrupt(
                    f"{point.metric.value} breached threshold: "
                    f"value={point.value} > threshold={point.threshold} "
                    f"(point {point.point_id})"
                )
        return point

    def record_all(self, points: list[TelemetryPoint]) -> list[TelemetryPoint]:
        """Record every point, collecting breaches instead of raising on the first.

        Use when one breach must not hide the points behind it.
        """
        previous, self._interrupt_on_breach = self._interrupt_on_breach, False
        try:
            for point in points:
                self.record(point)
        finally:
            self._interrupt_on_breach = previous
        return list(points)
