"""S3-B Reader / Writer Domain Ports (B4).

Typed, side-effect-free contracts for the ``reader`` and ``writer`` domain
roles. Three transport-neutral adapters — ``native`` (deterministic oracle and
fallback), ``llm`` (structured), and ``external`` (structured) — normalise the
same input into the same typed outputs so the pipeline downstream sees one
contract shape. No adapter writes evidence or store records: formal evidence
still enters only through :class:`autoresearch.evidence.EvidenceService`
(the sole writer), and every non-native output is a candidate until admitted.

This module does not modify ``reader_service.py``, ``writing_service.py``,
shared ``contracts.py``, or any A-lane path.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from autoresearch.contracts import (
    EvidenceGrade,
    EvidenceType,
    PaperRecord,
    ReadingCard,
)
from autoresearch.evidence import EvidenceService
from autoresearch.pipeline_contracts import (
    EvidenceCandidate,
    SectionDraft,
    SectionPlan,
)

# ---------------------------------------------------------------------------
# Identities and statuses
# ---------------------------------------------------------------------------


class AdapterKind(StrEnum):
    NATIVE = "native"
    LLM = "llm"
    EXTERNAL = "external"


class BindingStatus(StrEnum):
    BOUND = "bound"
    UNBOUND = "unbound"
    PARTIAL = "partial"


class ParityStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


# ---------------------------------------------------------------------------
# Reader port
# ---------------------------------------------------------------------------


class ReaderRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=200)
    project_id: str = Field(min_length=1, max_length=200)
    paper: PaperRecord
    question: str | None = Field(default=None, max_length=2000)


class StructuredReadingPayload(BaseModel):
    """Normalised output of an off-port LLM or external reader capability.

    Carries only extracted, locatable material. A port adapter wraps this into
    :class:`ReadingCard` plus an :class:`EvidenceCandidate`; nothing here is
    evidence until the certificate admits it.
    """

    research_question: str = Field(min_length=1, max_length=2000)
    method: str = Field(min_length=1, max_length=2000)
    data_or_setting: str = Field(min_length=1, max_length=2000)
    findings: list[str] = Field(min_length=1, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    locators: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0, le=1)
    source_uri: str | None = Field(default=None, max_length=2000)
    locator: str | None = Field(default=None, max_length=300)
    independent_source: str = Field(min_length=1, max_length=300)


class ReaderResult(BaseModel):
    request_id: str
    adapter: AdapterKind
    card: ReadingCard
    candidate: EvidenceCandidate
    diagnostics: list[str] = Field(default_factory=list)


@runtime_checkable
class ReaderPort(Protocol):
    adapter_kind: AdapterKind

    def read(self, request: ReaderRequest) -> ReaderResult: ...


# ---------------------------------------------------------------------------
# Writer port
# ---------------------------------------------------------------------------


class WriterRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=200)
    project_id: str = Field(min_length=1, max_length=200)
    plan: SectionPlan
    cards: list[ReadingCard] = Field(default_factory=list)
    profile_id: str = Field(min_length=1, max_length=200)
    benchmark_plan_id: str = Field(min_length=1, max_length=200)


class StructuredDraftPayload(BaseModel):
    """Normalised output of an off-port LLM or external writer capability.

    ``observed_result_summary`` must be ``None`` for plan-only content; a real
    measured outcome smuggled in here is rejected by the gate-compliance check.
    """

    title: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=100_000)
    claims: list[str] = Field(default_factory=list, max_length=500)
    claim_evidence_map: dict[str, list[str]] = Field(default_factory=dict)
    unresolved_gaps: list[str] = Field(default_factory=list, max_length=500)
    limitations: list[str] = Field(default_factory=list, max_length=500)
    observed_result_summary: str | None = Field(default=None, max_length=2000)


class WriterResult(BaseModel):
    request_id: str
    adapter: AdapterKind
    draft: SectionDraft
    diagnostics: list[str] = Field(default_factory=list)


@runtime_checkable
class WriterPort(Protocol):
    adapter_kind: AdapterKind

    def write(self, request: WriterRequest) -> WriterResult: ...


# ---------------------------------------------------------------------------
# Native adapters (deterministic oracle + fallback)
# ---------------------------------------------------------------------------


class NativeReaderAdapter:
    """Deterministic, offline reading extraction.

    Mirrors the native extraction semantics from ``reader_service.py`` without
    touching the store: it produces a structured ``ReadingCard`` plus a
    candidate. Because the candidate carries classification (PAPER/E1), the
    caller may admit it directly through ``EvidenceService.admit_candidate``.
    """

    adapter_kind = AdapterKind.NATIVE

    @staticmethod
    def _sentences(text: str) -> list[str]:
        compact = re.sub(r"\s+", " ", text or "").strip()
        return [
            part.strip()
            for part in re.split(r"(?<=[.!?。！？])\s+", compact)
            if len(part.strip()) >= 25
        ]

    def read(self, request: ReaderRequest) -> ReaderResult:
        paper = request.paper
        source_text = paper.abstract.strip() or paper.title
        sentences = self._sentences(source_text)
        findings = sentences[:3] or [f"Title-supplied material only: {paper.title}"]

        method = next(
            (
                sentence[:800]
                for sentence in sentences
                if any(
                    keyword in sentence.lower()
                    for keyword in ("method", "approach", "propose", "experiment", "方法")
                )
            ),
            "Method not identifiable from the supplied material.",
        )
        setting = next(
            (
                sentence[:800]
                for sentence in sentences
                if any(
                    keyword in sentence.lower()
                    for keyword in ("dataset", "benchmark", "sample", "数据", "样本")
                )
            ),
            "Data or setting not identifiable from the supplied material.",
        )
        limitations = [
            sentence[:800]
            for sentence in sentences
            if any(
                keyword in sentence.lower()
                for keyword in ("limit", "future", "however", "局限", "未来")
            )
        ][:3] or ["No explicit limitation was extractable; this is an evidence gap."]

        independent_source = paper.doi or paper.url or f"{paper.source}:{paper.source_record_id}"
        locator = "abstract" if paper.abstract.strip() else "title"
        candidate = EvidenceCandidate(
            project_id=request.project_id,
            evidence_type=EvidenceType.PAPER,
            grade=EvidenceGrade.E1,
            title=f"Reading extraction: {paper.title}",
            claim=findings[0],
            source_uri=paper.url or None,
            source_id=paper.paper_id,
            locator=locator,
            checksum=None,
            independent_source=independent_source,
            adapter="paper_reader.native",
            adapter_version="0.1",
            metadata={"full_text_used": False, "extraction": "deterministic"},
        )
        card = ReadingCard(
            project_id=request.project_id,
            paper_id=paper.paper_id,
            research_question=request.question
            or (sentences[0][:800] if sentences else paper.title),
            method=method,
            data_or_setting=setting,
            findings=findings,
            limitations=limitations,
            locators=[locator],
            evidence_ids=[],
            confidence=0.45,
        )
        return ReaderResult(
            request_id=request.request_id,
            adapter=self.adapter_kind,
            card=card,
            candidate=candidate,
        )


class NativeWriterAdapter:
    """Deterministic, plan-only writer fallback.

    Builds the :class:`SectionDraft` directly from the supplied
    :class:`SectionPlan` and preserves claim/evidence bindings verbatim. It
    never fabricates an observed result.
    """

    adapter_kind = AdapterKind.NATIVE

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))

    def write(self, request: WriterRequest) -> WriterResult:
        plan = request.plan
        claim_lines = []
        for claim in plan.claims:
            evidence_ids = ", ".join(plan.claim_evidence_map.get(claim, [])) or "none"
            claim_lines.append(f"- {claim}\n  - evidence: {evidence_ids}")
        body = "\n".join(
            [
                f"# {plan.section_name}",
                "",
                "## Objective",
                plan.objective,
                "",
                "## Claims",
                "\n".join(claim_lines) if claim_lines else "- none",
                "",
                "## Evidence",
                "\n".join(f"- {eid}" for eid in plan.evidence_ids) or "- none",
                "",
                "## Notes",
                "Deterministic plan-only draft; no observed result is reported.",
            ]
        )
        draft = SectionDraft(
            project_id=request.project_id,
            section_id=plan.plan_id,
            profile_id=request.profile_id,
            plan_id=plan.plan_id,
            benchmark_plan_id=request.benchmark_plan_id,
            section_name=plan.section_name,
            title=plan.section_name,
            body=body,
            claims=self._unique(plan.claims),
            claim_evidence_map=plan.claim_evidence_map,
            evidence_ids=self._unique(plan.evidence_ids),
            unresolved_gaps=self._unique(plan.gaps),
            limitations=self._unique(plan.gaps),
            observed_result_summary=None,
            review_ready=True,
        )
        return WriterResult(
            request_id=request.request_id,
            adapter=self.adapter_kind,
            draft=draft,
        )


# ---------------------------------------------------------------------------
# Structured adapters (LLM / external, transport-neutral)
# ---------------------------------------------------------------------------


class StructuredReaderAdapter:
    """Wraps an off-port structured reading payload into the port contract.

    The payload is the *normalised* result of a real LLM or external reader;
    the adapter itself performs no network call and writes nothing. The
    produced candidate carries ``PAPER/E1`` only because the payload was
    supplied as extracted material — admission remains the certificate's job.
    """

    def __init__(self, adapter_kind: AdapterKind, *, adapter_name: str, adapter_version: str):
        if adapter_kind is AdapterKind.NATIVE:
            raise ValueError("structured adapter requires llm or external kind")
        self.adapter_kind = adapter_kind
        self.adapter_name = adapter_name
        self.adapter_version = adapter_version

    def read(
        self,
        request: ReaderRequest,
        payload: StructuredReadingPayload,
    ) -> ReaderResult:
        candidate = EvidenceCandidate(
            project_id=request.project_id,
            evidence_type=EvidenceType.PAPER,
            grade=EvidenceGrade.E1,
            title=f"Reading extraction: {request.paper.title}",
            claim=payload.findings[0],
            source_uri=payload.source_uri or request.paper.url or None,
            source_id=request.paper.paper_id,
            locator=payload.locator,
            checksum=None,
            independent_source=payload.independent_source,
            adapter=self.adapter_name,
            adapter_version=self.adapter_version,
            metadata={"kind": self.adapter_kind.value},
        )
        card = ReadingCard(
            project_id=request.project_id,
            paper_id=request.paper.paper_id,
            research_question=payload.research_question,
            method=payload.method,
            data_or_setting=payload.data_or_setting,
            findings=payload.findings,
            limitations=payload.limitations,
            locators=payload.locators or [payload.locator or "abstract"],
            evidence_ids=[],
            confidence=payload.confidence,
        )
        return ReaderResult(
            request_id=request.request_id,
            adapter=self.adapter_kind,
            card=card,
            candidate=candidate,
        )


class StructuredWriterAdapter:
    """Wraps an off-port structured draft payload into the port contract."""

    def __init__(self, adapter_kind: AdapterKind, *, adapter_name: str, adapter_version: str):
        if adapter_kind is AdapterKind.NATIVE:
            raise ValueError("structured adapter requires llm or external kind")
        self.adapter_kind = adapter_kind
        self.adapter_name = adapter_name
        self.adapter_version = adapter_version

    def write(
        self,
        request: WriterRequest,
        payload: StructuredDraftPayload,
    ) -> WriterResult:
        plan = request.plan
        draft = SectionDraft(
            project_id=request.project_id,
            section_id=plan.plan_id,
            profile_id=request.profile_id,
            plan_id=plan.plan_id,
            benchmark_plan_id=request.benchmark_plan_id,
            section_name=plan.section_name,
            title=payload.title,
            body=payload.body,
            claims=payload.claims,
            claim_evidence_map=payload.claim_evidence_map,
            evidence_ids=_unique_ids(
                [eid for eids in payload.claim_evidence_map.values() for eid in eids]
                + plan.evidence_ids
            ),
            unresolved_gaps=payload.unresolved_gaps,
            limitations=payload.limitations,
            observed_result_summary=payload.observed_result_summary,
            review_ready=True,
            notes=[f"adapter={self.adapter_name}; version={self.adapter_version}"],
        )
        return WriterResult(
            request_id=request.request_id,
            adapter=self.adapter_kind,
            draft=draft,
        )


def _unique_ids(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


# ---------------------------------------------------------------------------
# Claim binding
# ---------------------------------------------------------------------------


class ClaimBinding(BaseModel):
    claim: str
    evidence_ids: list[str] = Field(default_factory=list)
    status: BindingStatus
    missing_or_invalid: list[str] = Field(default_factory=list)


def bind_claims(
    draft: SectionDraft,
    evidence: EvidenceService,
) -> list[ClaimBinding]:
    """Evaluate binding for every claim in a draft against formal evidence.

    A claim is ``bound`` only when every listed evidence id resolves to a valid
    item (100% binding). Any missing or invalid id pushes the claim to
    ``partial``; an empty mapping is ``unbound``. This is the fail-closed rule
    that keeps unverifiable claims from being treated as supported.
    """
    bindings: list[ClaimBinding] = []
    for claim in draft.claims:
        evidence_ids = _unique_ids(draft.claim_evidence_map.get(claim, []))
        if not evidence_ids:
            bindings.append(
                ClaimBinding(claim=claim, evidence_ids=[], status=BindingStatus.UNBOUND)
            )
            continue
        missing_or_invalid: list[str] = []
        for evidence_id in evidence_ids:
            item = evidence.get(evidence_id)
            if item is None or not item.valid:
                missing_or_invalid.append(evidence_id)
        if missing_or_invalid:
            bindings.append(
                ClaimBinding(
                    claim=claim,
                    evidence_ids=evidence_ids,
                    status=BindingStatus.PARTIAL,
                    missing_or_invalid=missing_or_invalid,
                )
            )
        else:
            bindings.append(
                ClaimBinding(
                    claim=claim,
                    evidence_ids=evidence_ids,
                    status=BindingStatus.BOUND,
                )
            )
    return bindings


def gate_compliance(
    draft: SectionDraft,
    bindings: list[ClaimBinding],
) -> tuple[bool, list[str]]:
    """Fail closed on evidence/governance invariants.

    Returns compliance plus issues discovered. Violations: a planned-only draft
    reporting an observed result; an unbound/partial claim that is not listed in
    ``unresolved_gaps`` (a claim silently treated as supported); a claim bound
    to evidence ids that are not in ``draft.evidence_ids`` (invisible lineage);
    an orphan ``claim_evidence_map`` key not listed in ``draft.claims`` (a
    binding silently dropped because its claim never entered the draft).
    """
    issues: list[str] = []
    if draft.observed_result_summary is not None:
        issues.append("planned-only draft reports an observed result")
    unresolved = set(draft.unresolved_gaps)
    bound_ids = set(draft.evidence_ids)
    known_claims = set(draft.claims)
    for orphan_key in draft.claim_evidence_map:
        if orphan_key not in known_claims:
            issues.append(
                f"claim_evidence_map contains an orphan key not listed in claims: "
                f"{orphan_key[:80]}"
            )
    for binding in bindings:
        if binding.status is not BindingStatus.BOUND and binding.claim not in unresolved:
            issues.append(
                f"claim without full evidence binding is not marked unresolved: "
                f"{binding.claim[:80]}"
            )
        for evidence_id in binding.evidence_ids:
            if evidence_id not in bound_ids:
                issues.append(f"claim binds evidence absent from draft.evidence_ids: {evidence_id}")
    return (not issues), issues


# ---------------------------------------------------------------------------
# Parity report (contract-level, never text equivalence)
# ---------------------------------------------------------------------------


class AdapterParity(BaseModel):
    adapter: AdapterKind
    schema_valid: bool
    claim_count: int
    bound_count: int
    binding_rate: float | None = None
    gate_compliant: bool
    issues: list[str] = Field(default_factory=list)


class ParityReport(BaseModel):
    report_id: str = Field(default_factory=lambda: "parity-" + _new_suffix())
    adapters: list[AdapterParity] = Field(default_factory=list)
    overall: ParityStatus = ParityStatus.PASS
    issues: list[str] = Field(default_factory=list)


def _new_suffix() -> str:
    import uuid

    return uuid.uuid4().hex[:16]


def compare_writer_parity(
    results: list[WriterResult],
    *,
    evidence: EvidenceService,
) -> ParityReport:
    """Contract-level parity across writer adapters.

    Structural rules only: schema validity, claim-binding completeness
    (bound claims must be 100% valid evidence), gate compliance, and
    planned-only enforcement. Text is never compared because distinct
    implementations legitimately differ in wording.
    """
    rows: list[AdapterParity] = []
    for result in results:
        draft = result.draft
        bindings = bind_claims(draft, evidence)
        compliant, issues = gate_compliance(draft, bindings)
        bound = sum(1 for binding in bindings if binding.status is BindingStatus.BOUND)
        rate = (bound / len(bindings)) if bindings else None
        schema_valid = isinstance(draft, SectionDraft) and bool(draft.title) and bool(draft.body)
        rows.append(
            AdapterParity(
                adapter=result.adapter,
                schema_valid=schema_valid,
                claim_count=len(bindings),
                bound_count=bound,
                binding_rate=rate,
                gate_compliant=compliant,
                issues=issues,
            )
        )
    problems = [
        f"{row.adapter.value}: {'; '.join(row.issues)}"
        for row in rows
        if not row.schema_valid or not row.gate_compliant
    ]
    return ParityReport(
        adapters=rows,
        overall=ParityStatus.FAIL if problems else ParityStatus.PASS,
        issues=problems,
    )
