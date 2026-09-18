"""K12 ``SensitivityClass`` -- data sensitivity labels + traceable egress (M14-04).

Contract: ``docs/rearchitecture/R007-parallel-modules/04-l2-contracts.md`` K12.

Two invariants:

* **① ``SENSITIVE`` 禁止进入 embedding / 外部模型.**

  🔴 **This is an EMPTY CONSTRAINT in this repository -- the annotation is
  ``【向量落地后生效】``.**  Measured: ``grep -rniE
  "embedding|vector|faiss|chromadb|sentence_transformers" src`` returns 11 lines
  and every one is a false positive -- ``contracts.py:159``
  (``VECTOR = "vector"  # 【P4 后生效】当前仓库无向量实现``, an unreachable enum
  member), its explanatory comment, and 9 lines of *pricing-catalog data* for
  ``text-embedding-3-*`` models in ``src/autoresearch/data/models_catalog.json``.
  There is **no** vector store, **no** embedding call site and **no** similarity
  search anywhere in the tree, so the ban cannot be violated today.

  Per R-007 §5 (**and R-006 §11.8's lesson**) this module therefore
  **does NOT assert that the ban holds** -- a ``passes`` assertion here would be
  a permanently-green test.  The deferred stage is *registered* instead, in the
  machine-readable :data:`DEFERRED_INVARIANTS` table below, and the only test
  that touches it guards that the registration is still present (a documentation
  guard that can genuinely go red, not evidence the invariant holds).

* **② 导出/删除可追溯.** -- :class:`SensitivityLedger` records every export and
  delete of a classified resource, and fails closed on an unclassified resource
  or a missing reason.

The scanner is dependency-free (regex) and **never stores the matched text**:
:class:`PiiSpan` carries offsets and a kind, not the secret.  Storing the match
would recreate the very leak this module exists to prevent (and would collide
with K13-3's "never record the full text").
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel, Field, model_validator

from autoresearch.contracts import new_id, utc_now

# ---------------------------------------------------------------------------
# Sensitivity vocabulary
# ---------------------------------------------------------------------------


class SensitivityClass(StrEnum):
    """How far a resource may travel (K12).

    ``SENSITIVE`` additionally forbids embedding / external-model egress.
    **That half is not enforceable yet** -- see :data:`DEFERRED_INVARIANTS`.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"  # 【向量落地后生效】禁 embedding / 外部模型 —— 当前不可被违反


#: Machine-readable registry of invariants that **cannot be violated in this
#: repository yet**.  They must NOT be covered by a "passes" assertion
#: (R-007 §5: 「凡标【…后生效】的，禁止为其写『通过』断言」).  Registering the
#: deferral -- instead of testing the invariant -- is the whole point.
DEFERRED_INVARIANTS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "K12.SENSITIVE_FORBIDS_EMBEDDING": (
            "【向量落地后生效】SENSITIVE 资源禁止进入 embedding / 外部模型。"
            "实测本仓库无任何向量/embedding 实现（contracts.py:159 的 VECTOR 枚举值"
            "自带【P4 后生效】标注且不可达），故该约束当前不可被违反；"
            "按 R-007 §5 不为其写『通过』断言。向量能力落地（P4）后必须补："
            "一条 SENSITIVE 资源被送入 embedding/外部模型的路径必须被拒的负例。"
        ),
    }
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SensitivityError(ValueError):
    """Base class for K12 failures."""


class UntraceableExport(SensitivityError):
    """An export/delete arrived with no reason -- it must not be recorded silently."""


class UnclassifiedExport(SensitivityError):
    """An export/delete targeted a resource that carries no sensitivity label.

    Fail-closed (D-L09-06): an unlabelled resource is not assumed ``PUBLIC``.
    """


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


class PiiSpan(BaseModel):
    """One sensitive span, stored as a *location* + kind.

    Deliberately **not** a substring: keeping the matched text would turn the
    detector into a second copy of the secret.
    """

    kind: str = Field(min_length=1, max_length=40)
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_order(self) -> PiiSpan:
        if self.end < self.start:
            raise ValueError("span end must not precede start")
        return self


class PiiScanResult(BaseModel):
    """The outcome of one PII scan.

    ``value`` is the number of sensitive spans found, or **``None`` when the
    scan did not happen** (no scanner available / scan skipped).  ``None`` and
    ``0`` are different facts -- "we did not look" vs "we looked and found
    nothing" -- and collapsing them is the defect family K13-1 names for
    telemetry (O12 ``_recurrence_count``; PR #20's ``except: return 0``).  The
    same discipline is applied here on the PII side.
    """

    resource_id: str = Field(min_length=1, max_length=400)
    scanner: str | None = Field(default=None, max_length=200)
    value: int | None = Field(default=None, ge=0)
    spans: list[PiiSpan] = Field(default_factory=list)

    @property
    def measured(self) -> bool:
        return self.value is not None

    @model_validator(mode="after")
    def _value_matches_scanner(self) -> PiiScanResult:
        if self.scanner is None and self.value is not None:
            raise ValueError("a scan with no scanner cannot carry a value")
        if self.scanner is not None and self.value is None:
            raise ValueError("a scan that ran must carry a value (use 0 for 'found none')")
        if self.value is not None and self.value != len(self.spans):
            raise ValueError("value must equal the number of recorded spans")
        return self


PiiScanner = Callable[[str], list[PiiSpan]]

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Precision-over-recall on bare digit runs, deliberately: a phone number is
# recognised only when it is *formatted* -- E.164 (``+`` and 7-15 digits) or
# grouped with spaces/dashes (``138 0000 1111``).  An unseparated 10-15 digit run
# is far more often an identifier (a run id, a hash prefix, an epoch stamp) than a
# phone number, and flagging those would make every consumer's ids look like PII.
# The cost is a genuine false negative on unformatted numbers; that trade-off is
# recorded as a known limit.
_PHONE_RE = re.compile(r"\+\d{7,15}|(?<!\d)\d{2,4}[\s-]\d{2,4}(?:[\s-]?\d{2,4})?(?!\d)")


def default_scanner(text: str) -> list[PiiSpan]:
    """Dependency-free email/phone detector.  Returns spans, never substrings."""
    spans: list[PiiSpan] = []
    for kind, pattern in (("email", _EMAIL_RE), ("phone", _PHONE_RE)):
        for match in pattern.finditer(text):
            spans.append(PiiSpan(kind=kind, start=match.start(), end=match.end()))
    spans.sort(key=lambda s: (s.start, s.end))
    return spans


def scan_for_pii(
    text: str,
    *,
    resource_id: str,
    scanner: PiiScanner | None = None,
    scanner_name: str | None = None,
) -> PiiScanResult:
    """Scan *text*, or record that the scan did not happen.

    ``scanner=None`` returns ``value=None`` -- **not** ``0``.  Callers must
    branch on ``result.value is None``; treating it as "clean" would be the
    exact "missing recorded as a normal value" defect.
    """
    if scanner is None:
        return PiiScanResult(resource_id=resource_id, scanner=None, value=None)
    spans = scanner(text)
    name = scanner_name or getattr(scanner, "__name__", "scanner")
    return PiiScanResult(resource_id=resource_id, scanner=name, value=len(spans), spans=spans)


# ---------------------------------------------------------------------------
# Labels + egress trace (K12 ②)
# ---------------------------------------------------------------------------


class SensitivityLabel(BaseModel):
    """A resource -> sensitivity binding."""

    label_id: str = Field(default_factory=lambda: new_id("sens"))
    resource_kind: str = Field(min_length=1, max_length=40)
    resource_id: str = Field(min_length=1, max_length=400)
    sensitivity: SensitivityClass
    assigned_by: str = Field(min_length=1, max_length=200)
    created_at: datetime = Field(default_factory=utc_now)


class TraceAction(StrEnum):
    EXPORT = "export"
    DELETE = "delete"


class SensitivityTrace(BaseModel):
    """One traceable export/delete of a classified resource (K12 ②)."""

    trace_id: str = Field(default_factory=lambda: new_id("pii_trace"))
    action: TraceAction
    resource_id: str
    sensitivity: SensitivityClass
    subject: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=400)
    created_at: datetime = Field(default_factory=utc_now)


class SensitivityLedger:
    """Labels resources and records every export/delete of a labelled one.

    This answers "did we leave a trace?", not "are you allowed?" -- the latter is
    :mod:`autoresearch.acl` (K11).  The two are deliberately independent so each
    can be tested without the other.
    """

    def __init__(self) -> None:
        self._labels: dict[tuple[str, str], SensitivityLabel] = {}
        self._traces: list[SensitivityTrace] = []

    # -- labels ------------------------------------------------------------

    def label(self, label: SensitivityLabel) -> SensitivityLabel:
        self._labels[(label.resource_kind, label.resource_id)] = label
        return label

    def sensitivity_of(self, resource_kind: str, resource_id: str) -> SensitivityClass | None:
        found = self._labels.get((resource_kind, resource_id))
        return found.sensitivity if found else None

    @property
    def traces(self) -> tuple[SensitivityTrace, ...]:
        return tuple(self._traces)

    # -- egress ------------------------------------------------------------

    def record(
        self,
        *,
        action: TraceAction,
        resource_kind: str,
        resource_id: str,
        subject: str,
        reason: str,
    ) -> SensitivityTrace:
        """Record one export/delete.  Fails closed on the two silent paths.

        * unlabelled resource -> :class:`UnclassifiedExport` (we do not assume
          ``PUBLIC``, D-L09-06);
        * empty reason -> :class:`UntraceableExport` (an unattributed egress is
          not a trace).
        """
        if not reason.strip():
            raise UntraceableExport(
                f"{action.value} of {resource_id!r} needs a non-empty reason to be traceable"
            )
        sensitivity = self.sensitivity_of(resource_kind, resource_id)
        if sensitivity is None:
            raise UnclassifiedExport(
                f"{action.value} of {resource_kind}:{resource_id!r} refused: "
                "resource carries no sensitivity label"
            )
        trace = SensitivityTrace(
            action=action,
            resource_id=resource_id,
            sensitivity=sensitivity,
            subject=subject,
            reason=reason.strip(),
        )
        self._traces.append(trace)
        return trace
