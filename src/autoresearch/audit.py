from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from enum import StrEnum
from math import ceil
from typing import Any

from pydantic import BaseModel, Field, model_validator

from autoresearch.contracts import EvidenceGrade, EvidenceType, Manuscript
from autoresearch.evidence import EvidenceService
from autoresearch.pipeline_contracts import (
    EvidenceAdmissionResult,
    EvidenceCandidate,
)
from autoresearch.storage import RecordStore


class AuditStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class AuditMethod(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"


class AuditCategory(StrEnum):
    CITATION_EXISTENCE = "citation_existence"
    LOCATOR_CONSISTENCY = "locator_consistency"
    PUBLICATION_STATUS = "publication_status"
    EVIDENCE_RECONCILIATION = "evidence_reconciliation"
    UNBOUND_CLAIM = "unbound_claim"


class AuditMode(StrEnum):
    IN_RUNTIME = "in-runtime"
    STANDALONE = "standalone"


class EvidenceReconciliationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING = "missing"
    UNKNOWN = "unknown"


class LocatorMethod(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"


class CitationRef(BaseModel):
    citation_id: str = Field(min_length=1, max_length=200)
    source_id: str | None = None
    source_uri: str | None = None
    title: str | None = Field(default=None, max_length=300)
    locator: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def has_source_reference(self) -> CitationRef:
        if not (self.source_id or self.source_uri or self.title):
            raise ValueError("citation must have source_id, source_uri, or title")
        return self


class AuditClaim(BaseModel):
    claim_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2000)
    citation_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    locator_method: LocatorMethod = LocatorMethod.DETERMINISTIC


class ResolverRecord(BaseModel):
    source_id: str = Field(min_length=1, max_length=300)
    source_uri: str | None = None
    title: str | None = Field(default=None, max_length=300)
    status: str = "current"
    related_source_ids: list[str] = Field(default_factory=list)


class ResolverSnapshot(BaseModel):
    version: str = Field(min_length=1, max_length=100)
    available: bool = True
    records: list[ResolverRecord] = Field(default_factory=list)
    provider: str = "local-snapshot"


class LocalDocument(BaseModel):
    source_id: str = Field(min_length=1, max_length=300)
    source_uri: str | None = None
    full_text_available: bool = True
    locators: dict[str, str] = Field(default_factory=dict)


class CorpusSnapshot(BaseModel):
    version: str = Field(min_length=1, max_length=100)
    documents: list[LocalDocument] = Field(default_factory=list)


class LocatorAssessment(BaseModel):
    status: AuditStatus
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=1000)


class AuditVerdict(BaseModel):
    verdict_id: str
    claim_id: str
    category: AuditCategory
    status: AuditStatus
    method: AuditMethod
    confidence: float | None = Field(default=None, ge=0, le=1)
    citation_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    related_source_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class EvidenceReconciliation(BaseModel):
    claim_id: str
    evidence_id: str
    status: EvidenceReconciliationStatus
    traceable: bool = True
    reason: str


class AuditReport(BaseModel):
    report_id: str
    audit_key: str
    project_id: str
    mode: AuditMode
    input_hash: str
    corpus_version: str
    resolver_snapshot_version: str
    status: AuditStatus
    deterministic_verdicts: list[AuditVerdict] = Field(default_factory=list)
    model_assisted_verdicts: list[AuditVerdict] = Field(default_factory=list)
    evidence_reconciliation: list[EvidenceReconciliation] = Field(default_factory=list)
    unverified_claims: list[str] = Field(default_factory=list)
    evidence_candidates: list[EvidenceCandidate] = Field(default_factory=list)
    admission_results: list[EvidenceAdmissionResult] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)

    @property
    def verdicts(self) -> list[AuditVerdict]:
        """Return all verdicts while retaining method-separated storage."""

        return [*self.deterministic_verdicts, *self.model_assisted_verdicts]


class AuditService:
    """Offline, snapshot-based manuscript and claim auditor.

    The service owns AuditReport persistence. Formal evidence remains owned by
    EvidenceService: audit conclusions can only leave this module as candidates.
    """

    _MODEL_ASSISTED_MIN_CONFIDENCE = 0.8
    _STOP_WORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "by",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "our",
        "the",
        "this",
        "to",
        "we",
        "with",
    }

    def __init__(self, store: RecordStore, evidence: EvidenceService | None = None):
        self.store = store
        self.evidence = evidence

    @staticmethod
    def _normalize(value: str | None) -> str:
        return re.sub(r"\s+", " ", value or "").strip().casefold()

    @classmethod
    def _canonical(cls, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return cls._canonical(value.model_dump(mode="json"))
        if isinstance(value, Mapping):
            return {
                str(key): cls._canonical(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, (list, tuple)):
            return [cls._canonical(item) for item in value]
        return value

    @classmethod
    def _hash_input(
        cls,
        project_id: str,
        manuscript: Manuscript | None,
        claims: list[AuditClaim],
        citations: list[CitationRef],
        resolver: ResolverSnapshot,
        corpus: CorpusSnapshot,
        mode: AuditMode,
    ) -> str:
        payload = {
            "project_id": project_id,
            "manuscript": manuscript,
            "claims": claims,
            "citations": citations,
            "resolver": resolver,
            "corpus": corpus,
            "mode": mode,
        }
        encoded = json.dumps(cls._canonical(payload), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def _audit_key(cls, input_hash: str) -> str:
        return f"audit_{input_hash}"

    @classmethod
    def _verdict_id(
        cls,
        input_hash: str,
        claim_id: str,
        category: AuditCategory,
        citation_id: str | None = None,
    ) -> str:
        value = ":".join((input_hash, claim_id, category.value, citation_id or ""))
        return "av_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _coerce_model(model_type: type[BaseModel], value: Any) -> BaseModel:
        if isinstance(value, model_type):
            return value
        return model_type.model_validate(value)

    @classmethod
    def _citations(
        cls,
        values: Iterable[CitationRef | dict[str, Any]] | Mapping[str, CitationRef | dict[str, Any]],
    ) -> list[CitationRef]:
        if isinstance(values, Mapping):
            result = []
            for citation_id, value in values.items():
                if isinstance(value, CitationRef):
                    result.append(value)
                else:
                    result.append(CitationRef.model_validate({"citation_id": citation_id, **value}))
            return result
        return [
            cls._coerce_model(CitationRef, value)  # type: ignore[list-item]
            for value in values
        ]

    @classmethod
    def _claims(cls, values: Iterable[AuditClaim | dict[str, Any]]) -> list[AuditClaim]:
        return [cls._coerce_model(AuditClaim, value) for value in values]  # type: ignore[list-item]

    @staticmethod
    def _resolver_index(snapshot: ResolverSnapshot) -> dict[str, ResolverRecord]:
        index: dict[str, ResolverRecord] = {}
        for record in snapshot.records:
            for key in (record.source_id, record.source_uri, record.title):
                if key:
                    index[AuditService._normalize(key)] = record
        return index

    @staticmethod
    def _corpus_index(snapshot: CorpusSnapshot) -> dict[str, LocalDocument]:
        index: dict[str, LocalDocument] = {}
        for document in snapshot.documents:
            for key in (document.source_id, document.source_uri):
                if key:
                    index[AuditService._normalize(key)] = document
        return index

    @classmethod
    def _find_record(
        cls,
        citation: CitationRef,
        index: dict[str, ResolverRecord],
    ) -> ResolverRecord | None:
        for key in (citation.source_id, citation.source_uri, citation.title):
            if key and (record := index.get(cls._normalize(key))) is not None:
                return record
        return None

    @classmethod
    def _find_document(
        cls,
        citation: CitationRef,
        index: dict[str, LocalDocument],
    ) -> LocalDocument | None:
        for key in (citation.source_id, citation.source_uri):
            if key and (document := index.get(cls._normalize(key))) is not None:
                return document
        return None

    @staticmethod
    def _locator_key(value: str) -> str:
        normalized = re.sub(r"\s+", "", value.casefold())
        normalized = normalized.replace("page", "p")
        return normalized.rstrip(".")

    @classmethod
    def _locator_text(cls, document: LocalDocument, locator: str) -> str | None:
        requested = cls._locator_key(locator)
        for available, text in document.locators.items():
            if cls._locator_key(available) == requested:
                return text
        return None

    @classmethod
    def _claim_matches_text(cls, claim: str, text: str) -> bool:
        claim_normalized = cls._normalize(claim)
        text_normalized = cls._normalize(text)
        if claim_normalized in text_normalized:
            return True
        terms = [
            term
            for term in re.findall(r"[\w\u4e00-\u9fff]+", claim_normalized)
            if len(term) >= 4 and term not in cls._STOP_WORDS
        ]
        if not terms:
            return True
        overlap = sum(term in text_normalized for term in terms)
        return overlap >= max(1, ceil(len(terms) / 2))

    @classmethod
    def _status_verdict(
        cls,
        input_hash: str,
        claim: AuditClaim,
        citation: CitationRef,
        record: ResolverRecord | None,
        resolver_available: bool,
    ) -> AuditVerdict:
        verdict_id = cls._verdict_id(
            input_hash, claim.claim_id, AuditCategory.PUBLICATION_STATUS, citation.citation_id
        )
        if not resolver_available:
            return AuditVerdict(
                verdict_id=verdict_id,
                claim_id=claim.claim_id,
                category=AuditCategory.PUBLICATION_STATUS,
                status=AuditStatus.UNKNOWN,
                method=AuditMethod.DETERMINISTIC,
                citation_id=citation.citation_id,
                reasons=["resolver snapshot is unavailable; publication status is unknown"],
            )
        if record is None:
            return AuditVerdict(
                verdict_id=verdict_id,
                claim_id=claim.claim_id,
                category=AuditCategory.PUBLICATION_STATUS,
                status=AuditStatus.UNKNOWN,
                method=AuditMethod.DETERMINISTIC,
                citation_id=citation.citation_id,
                reasons=["publication status is unavailable for the citation"],
            )

        status = cls._normalize(record.status)
        if status in {"retracted", "withdrawn"}:
            return AuditVerdict(
                verdict_id=verdict_id,
                claim_id=claim.claim_id,
                category=AuditCategory.PUBLICATION_STATUS,
                status=AuditStatus.FAIL,
                method=AuditMethod.DETERMINISTIC,
                citation_id=citation.citation_id,
                related_source_ids=record.related_source_ids,
                reasons=["citation is retracted or withdrawn"],
            )
        if status in {"corrected", "superseded", "versioned"}:
            relation = ", ".join(record.related_source_ids)
            if record.related_source_ids:
                return AuditVerdict(
                    verdict_id=verdict_id,
                    claim_id=claim.claim_id,
                    category=AuditCategory.PUBLICATION_STATUS,
                    status=AuditStatus.PASS,
                    method=AuditMethod.DETERMINISTIC,
                    confidence=1.0,
                    citation_id=citation.citation_id,
                    related_source_ids=record.related_source_ids,
                    reasons=[f"{status} relation is traceable: {relation}"],
                )
            return AuditVerdict(
                verdict_id=verdict_id,
                claim_id=claim.claim_id,
                category=AuditCategory.PUBLICATION_STATUS,
                status=AuditStatus.UNKNOWN,
                method=AuditMethod.DETERMINISTIC,
                citation_id=citation.citation_id,
                reasons=[f"{status} status has no traceable related source"],
            )
        if status in {"current", "active", "valid", "available"}:
            return AuditVerdict(
                verdict_id=verdict_id,
                claim_id=claim.claim_id,
                category=AuditCategory.PUBLICATION_STATUS,
                status=AuditStatus.PASS,
                method=AuditMethod.DETERMINISTIC,
                confidence=1.0,
                citation_id=citation.citation_id,
                reasons=["citation has a current resolver status"],
            )
        return AuditVerdict(
            verdict_id=verdict_id,
            claim_id=claim.claim_id,
            category=AuditCategory.PUBLICATION_STATUS,
            status=AuditStatus.UNKNOWN,
            method=AuditMethod.DETERMINISTIC,
            citation_id=citation.citation_id,
            reasons=[f"resolver status is not recognized: {record.status}"],
        )

    @classmethod
    def _locator_verdict(
        cls,
        input_hash: str,
        claim: AuditClaim,
        citation: CitationRef,
        document: LocalDocument | None,
        assessment: LocatorAssessment | None,
    ) -> AuditVerdict:
        method = (
            AuditMethod.MODEL_ASSISTED
            if claim.locator_method == LocatorMethod.MODEL_ASSISTED
            else AuditMethod.DETERMINISTIC
        )
        verdict_id = cls._verdict_id(
            input_hash, claim.claim_id, AuditCategory.LOCATOR_CONSISTENCY, citation.citation_id
        )
        if method == AuditMethod.MODEL_ASSISTED:
            if assessment is None:
                return AuditVerdict(
                    verdict_id=verdict_id,
                    claim_id=claim.claim_id,
                    category=AuditCategory.LOCATOR_CONSISTENCY,
                    status=AuditStatus.UNKNOWN,
                    method=method,
                    citation_id=citation.citation_id,
                    reasons=["model-assisted locator assessment is missing"],
                )
            if assessment.confidence < cls._MODEL_ASSISTED_MIN_CONFIDENCE:
                return AuditVerdict(
                    verdict_id=verdict_id,
                    claim_id=claim.claim_id,
                    category=AuditCategory.LOCATOR_CONSISTENCY,
                    status=AuditStatus.UNKNOWN,
                    method=method,
                    confidence=assessment.confidence,
                    citation_id=citation.citation_id,
                    reasons=[
                        "model-assisted locator confidence is below the frozen 0.8 threshold",
                        assessment.reason,
                    ],
                )
            return AuditVerdict(
                verdict_id=verdict_id,
                claim_id=claim.claim_id,
                category=AuditCategory.LOCATOR_CONSISTENCY,
                status=assessment.status,
                method=method,
                confidence=assessment.confidence,
                citation_id=citation.citation_id,
                reasons=[assessment.reason],
            )

        if not citation.locator:
            status = AuditStatus.UNKNOWN
            reason = "citation locator is absent"
        elif document is None or not document.full_text_available:
            status = AuditStatus.UNKNOWN
            reason = "local full text is unavailable; locator comparison is unknown"
        else:
            locator_text = cls._locator_text(document, citation.locator)
            if locator_text is None:
                status = AuditStatus.FAIL
                reason = "citation locator does not exist in the local full-text snapshot"
            elif not cls._claim_matches_text(claim.text, locator_text):
                status = AuditStatus.FAIL
                reason = "claim text does not match the cited local locator"
            else:
                status = AuditStatus.PASS
                reason = "claim matches the cited local locator"
        return AuditVerdict(
            verdict_id=verdict_id,
            claim_id=claim.claim_id,
            category=AuditCategory.LOCATOR_CONSISTENCY,
            status=status,
            method=AuditMethod.DETERMINISTIC,
            confidence=1.0 if status != AuditStatus.UNKNOWN else None,
            citation_id=citation.citation_id,
            reasons=[reason],
        )

    @classmethod
    def _existence_verdict(
        cls,
        input_hash: str,
        claim: AuditClaim,
        citation_id: str,
        citation: CitationRef | None,
        record: ResolverRecord | None,
        resolver_available: bool,
    ) -> AuditVerdict:
        verdict_id = cls._verdict_id(
            input_hash, claim.claim_id, AuditCategory.CITATION_EXISTENCE, citation_id
        )
        if citation is None:
            return AuditVerdict(
                verdict_id=verdict_id,
                claim_id=claim.claim_id,
                category=AuditCategory.CITATION_EXISTENCE,
                status=AuditStatus.FAIL,
                method=AuditMethod.DETERMINISTIC,
                citation_id=citation_id,
                reasons=["citation is missing from the citation registry"],
            )
        if not resolver_available:
            return AuditVerdict(
                verdict_id=verdict_id,
                claim_id=claim.claim_id,
                category=AuditCategory.CITATION_EXISTENCE,
                status=AuditStatus.UNKNOWN,
                method=AuditMethod.DETERMINISTIC,
                citation_id=citation_id,
                reasons=["resolver snapshot is unavailable; citation existence is unknown"],
            )
        if record is None:
            return AuditVerdict(
                verdict_id=verdict_id,
                claim_id=claim.claim_id,
                category=AuditCategory.CITATION_EXISTENCE,
                status=AuditStatus.FAIL,
                method=AuditMethod.DETERMINISTIC,
                citation_id=citation_id,
                reasons=["citation was not found in the local resolver snapshot"],
            )
        return AuditVerdict(
            verdict_id=verdict_id,
            claim_id=claim.claim_id,
            category=AuditCategory.CITATION_EXISTENCE,
            status=AuditStatus.PASS,
            method=AuditMethod.DETERMINISTIC,
            confidence=1.0,
            citation_id=citation_id,
            reasons=["citation exists in the local resolver snapshot"],
        )

    def _reconcile_evidence(
        self,
        input_hash: str,
        claim: AuditClaim,
    ) -> tuple[list[AuditVerdict], list[EvidenceReconciliation], bool]:
        verdicts: list[AuditVerdict] = []
        reconciliations: list[EvidenceReconciliation] = []
        valid_support = False
        for evidence_id in dict.fromkeys(claim.evidence_ids):
            if self.evidence is None:
                reconciliation = EvidenceReconciliation(
                    claim_id=claim.claim_id,
                    evidence_id=evidence_id,
                    status=EvidenceReconciliationStatus.UNKNOWN,
                    reason="bounded evidence view is unavailable",
                )
                status = AuditStatus.UNKNOWN
            else:
                item = self.evidence.get(evidence_id)
                if item is None:
                    reconciliation = EvidenceReconciliation(
                        claim_id=claim.claim_id,
                        evidence_id=evidence_id,
                        status=EvidenceReconciliationStatus.UNKNOWN,
                        traceable=False,
                        reason="evidence id is absent from the bounded Evidence Module view",
                    )
                    status = AuditStatus.UNKNOWN
                else:
                    reason = self.evidence.validity_reason(evidence_id)
                    if reason is not None or not item.valid:
                        reconciliation = EvidenceReconciliation(
                            claim_id=claim.claim_id,
                            evidence_id=evidence_id,
                            status=EvidenceReconciliationStatus.INVALID,
                            reason=reason or "evidence is invalid",
                        )
                        status = AuditStatus.FAIL
                    else:
                        reconciliation = EvidenceReconciliation(
                            claim_id=claim.claim_id,
                            evidence_id=evidence_id,
                            status=EvidenceReconciliationStatus.VALID,
                            reason="evidence is valid and traceable",
                        )
                        status = AuditStatus.PASS
                        valid_support = True
            reconciliations.append(reconciliation)
            verdicts.append(
                AuditVerdict(
                    verdict_id=self._verdict_id(
                        input_hash,
                        claim.claim_id,
                        AuditCategory.EVIDENCE_RECONCILIATION,
                        evidence_id,
                    ),
                    claim_id=claim.claim_id,
                    category=AuditCategory.EVIDENCE_RECONCILIATION,
                    status=status,
                    method=AuditMethod.DETERMINISTIC,
                    confidence=1.0 if status != AuditStatus.UNKNOWN else None,
                    evidence_ids=[evidence_id],
                    reasons=[reconciliation.reason],
                )
            )
        return verdicts, reconciliations, valid_support

    @staticmethod
    def _overall_status(verdicts: list[AuditVerdict], diagnostics: list[str]) -> AuditStatus:
        statuses = {verdict.status for verdict in verdicts}
        if AuditStatus.FAIL in statuses:
            return AuditStatus.FAIL
        if AuditStatus.UNKNOWN in statuses or not verdicts or diagnostics:
            return AuditStatus.UNKNOWN
        return AuditStatus.PASS

    @staticmethod
    def _candidate(
        project_id: str,
        audit_key: str,
        claim: AuditClaim,
        citation: CitationRef,
        record: ResolverRecord,
        resolver_version: str,
    ) -> EvidenceCandidate | None:
        if not citation.locator:
            return None
        source_id = citation.source_id or record.source_id
        source_uri = citation.source_uri or record.source_uri
        independent_source = source_id or source_uri
        if not independent_source:
            return None
        candidate_id = "evcand_" + hashlib.sha256(
            f"{audit_key}:{claim.claim_id}:{citation.citation_id}".encode()
        ).hexdigest()[:16]
        return EvidenceCandidate(
            candidate_id=candidate_id,
            project_id=project_id,
            evidence_type=EvidenceType.PAPER,
            grade=EvidenceGrade.E1,
            title=citation.title or record.title or "Audited citation",
            claim=claim.text,
            source_uri=source_uri,
            source_id=source_id,
            locator=citation.locator,
            independent_source=independent_source,
            metadata={
                "audit_key": audit_key,
                "resolver_snapshot_version": resolver_version,
                "audit_conclusion": "citation_exists_and_status_traceable",
            },
        )

    def audit(
        self,
        project_id: str,
        *,
        claims: Iterable[AuditClaim | dict[str, Any]] = (),
        citations: Iterable[CitationRef | dict[str, Any]]
        | Mapping[str, CitationRef | dict[str, Any]] = (),
        manuscript: Manuscript | dict[str, Any] | None = None,
        resolver_snapshot: ResolverSnapshot | dict[str, Any] | None = None,
        corpus_snapshot: CorpusSnapshot | dict[str, Any] | None = None,
        mode: AuditMode | str = AuditMode.STANDALONE,
        model_assisted_locators: Mapping[str, LocatorAssessment | dict[str, Any]] | None = None,
        actor: str = "audit",
    ) -> AuditReport:
        selected_mode = AuditMode(mode)
        if selected_mode == AuditMode.IN_RUNTIME and self.evidence is None:
            raise ValueError("in-runtime audit requires EvidenceService")
        parsed_claims = self._claims(claims)
        parsed_citations = self._citations(citations)
        parsed_manuscript = (
            manuscript
            if isinstance(manuscript, Manuscript)
            else Manuscript.model_validate(manuscript)
            if manuscript is not None
            else None
        )
        if parsed_manuscript is not None and parsed_manuscript.project_id != project_id:
            raise ValueError("manuscript project_id does not match audit project_id")
        resolver = (
            resolver_snapshot
            if isinstance(resolver_snapshot, ResolverSnapshot)
            else ResolverSnapshot.model_validate(resolver_snapshot)
            if resolver_snapshot is not None
            else ResolverSnapshot(version="unavailable", available=False)
        )
        corpus = (
            corpus_snapshot
            if isinstance(corpus_snapshot, CorpusSnapshot)
            else CorpusSnapshot.model_validate(corpus_snapshot)
            if corpus_snapshot is not None
            else CorpusSnapshot(version="unavailable")
        )
        assessments = {
            key: (
                value
                if isinstance(value, LocatorAssessment)
                else LocatorAssessment.model_validate(value)
            )
            for key, value in (model_assisted_locators or {}).items()
        }
        input_hash = self._hash_input(
            project_id,
            parsed_manuscript,
            parsed_claims,
            parsed_citations,
            resolver,
            corpus,
            selected_mode,
        )
        audit_key = self._audit_key(input_hash)
        cached = self.store.get("audit_report", audit_key)
        if cached is not None:
            return AuditReport.model_validate(cached)

        citation_index = {citation.citation_id: citation for citation in parsed_citations}
        resolver_index = self._resolver_index(resolver)
        corpus_index = self._corpus_index(corpus)
        deterministic: list[AuditVerdict] = []
        model_assisted: list[AuditVerdict] = []
        reconciliations: list[EvidenceReconciliation] = []
        unverified_claims: list[str] = []
        candidates: list[EvidenceCandidate] = []
        diagnostics: list[str] = []

        for claim in parsed_claims:
            claim_verdicts: list[AuditVerdict] = []
            valid_support = False
            evidence_verdicts, claim_reconciliations, valid_support = self._reconcile_evidence(
                input_hash, claim
            )
            deterministic.extend(evidence_verdicts)
            reconciliations.extend(claim_reconciliations)
            for citation_id in dict.fromkeys(claim.citation_ids):
                citation = citation_index.get(citation_id)
                record = self._find_record(citation, resolver_index) if citation else None
                existence = self._existence_verdict(
                    input_hash,
                    claim,
                    citation_id,
                    citation,
                    record,
                    resolver.available,
                )
                deterministic.append(existence)
                claim_verdicts.append(existence)
                if citation is None:
                    continue
                status = self._status_verdict(
                    input_hash, claim, citation, record, resolver.available
                )
                deterministic.append(status)
                claim_verdicts.append(status)
                document = self._find_document(citation, corpus_index)
                assessment = assessments.get(f"{claim.claim_id}:{citation_id}") or assessments.get(
                    claim.claim_id
                )
                locator = self._locator_verdict(
                    input_hash, claim, citation, document, assessment
                )
                target_verdicts = (
                    model_assisted
                    if locator.method == AuditMethod.MODEL_ASSISTED
                    else deterministic
                )
                target_verdicts.append(locator)
                claim_verdicts.append(locator)
                if (
                    selected_mode == AuditMode.IN_RUNTIME
                    and existence.status == AuditStatus.PASS
                    and status.status == AuditStatus.PASS
                    and locator.status == AuditStatus.PASS
                    and record is not None
                ):
                    candidate = self._candidate(
                        project_id, audit_key, claim, citation, record, resolver.version
                    )
                    if candidate is not None:
                        candidates.append(candidate)
            if not claim.evidence_ids or not valid_support:
                unverified_claims.append(f"[未验证] {claim.text}")
                deterministic.append(
                    AuditVerdict(
                        verdict_id=self._verdict_id(
                            input_hash, claim.claim_id, AuditCategory.UNBOUND_CLAIM
                        ),
                        claim_id=claim.claim_id,
                        category=AuditCategory.UNBOUND_CLAIM,
                        status=AuditStatus.UNKNOWN,
                        method=AuditMethod.DETERMINISTIC,
                        evidence_ids=list(dict.fromkeys(claim.evidence_ids)),
                        reasons=["claim has no valid evidence binding"],
                    )
                )

        if not parsed_claims:
            diagnostics.append("no claims were supplied for audit")
        unique_candidates = list(
            {candidate.candidate_id: candidate for candidate in candidates}.values()
        )
        admissions: list[EvidenceAdmissionResult] = []
        if selected_mode == AuditMode.IN_RUNTIME:
            for candidate in unique_candidates:
                admissions.append(self.evidence.admit_candidate(candidate, actor=actor))

        report = AuditReport(
            report_id="ar_" + input_hash[:20],
            audit_key=audit_key,
            project_id=project_id,
            mode=selected_mode,
            input_hash=input_hash,
            corpus_version=corpus.version,
            resolver_snapshot_version=resolver.version,
            status=self._overall_status([*deterministic, *model_assisted], diagnostics),
            deterministic_verdicts=deterministic,
            model_assisted_verdicts=model_assisted,
            evidence_reconciliation=reconciliations,
            unverified_claims=unverified_claims,
            evidence_candidates=unique_candidates if selected_mode == AuditMode.IN_RUNTIME else [],
            admission_results=admissions,
            diagnostics=diagnostics,
        )
        self.store.put(
            "audit_report",
            audit_key,
            report,
            project_id=project_id,
            partition="audit",
        )
        self.store.append_event(
            "audit.report_created",
            report,
            project_id=project_id,
            actor=actor,
        )
        return report

    run = audit
