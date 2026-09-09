from __future__ import annotations

from autoresearch.audit import (
    AuditCategory,
    AuditClaim,
    AuditMethod,
    AuditMode,
    AuditService,
    AuditStatus,
    CitationRef,
    CorpusSnapshot,
    LocalDocument,
    LocatorAssessment,
    LocatorMethod,
    ResolverRecord,
    ResolverSnapshot,
)
from autoresearch.contracts import EvidenceGrade, EvidenceType
from autoresearch.pipeline_contracts import (
    EvidenceAdmissionResult,
    EvidenceAdmissionStatus,
    EvidenceCandidate,
)


def _citation(locator: str | None = "p.1") -> CitationRef:
    return CitationRef(
        citation_id="cite-current",
        source_id="paper-current",
        source_uri="https://example.invalid/paper-current",
        title="Current synthetic paper",
        locator=locator,
    )


def _claim(
    *,
    evidence_ids: list[str] | None = None,
    text: str = "The source supports a bounded evaluation claim.",
    locator_method: LocatorMethod = LocatorMethod.DETERMINISTIC,
) -> AuditClaim:
    return AuditClaim(
        claim_id="claim-1",
        text=text,
        citation_ids=["cite-current"],
        evidence_ids=list(evidence_ids or []),
        locator_method=locator_method,
    )


def _resolver(
    *,
    version: str = "resolver-v1",
    available: bool = True,
    status: str = "current",
    related_source_ids: list[str] | None = None,
) -> ResolverSnapshot:
    return ResolverSnapshot(
        version=version,
        available=available,
        records=(
            [
                ResolverRecord(
                    source_id="paper-current",
                    source_uri="https://example.invalid/paper-current",
                    title="Current synthetic paper",
                    status=status,
                    related_source_ids=list(related_source_ids or []),
                )
            ]
            if available
            else []
        ),
    )


def _corpus(
    *,
    version: str = "corpus-v1",
    available: bool = True,
    locator: str = "p.1",
    text: str = "The source supports a bounded evaluation claim.",
) -> CorpusSnapshot:
    return CorpusSnapshot(
        version=version,
        documents=(
            [
                LocalDocument(
                    source_id="paper-current",
                    source_uri="https://example.invalid/paper-current",
                    full_text_available=available,
                    locators={locator: text} if available else {},
                )
            ]
            if available
            else []
        ),
    )


def test_existing_citation_is_deterministic_pass(runtime, project):
    report = AuditService(runtime.store, runtime.evidence).audit(
        "demo",
        claims=[_claim()],
        citations=[_citation()],
        resolver_snapshot=_resolver(),
        corpus_snapshot=_corpus(),
    )

    assert report.status == AuditStatus.UNKNOWN  # the claim is intentionally unbound
    verdict = next(
        item
        for item in report.verdicts
        if item.category == AuditCategory.CITATION_EXISTENCE
    )
    assert verdict.status == AuditStatus.PASS
    assert verdict.method == AuditMethod.DETERMINISTIC


def test_missing_citation_is_deterministic_fail(runtime, project):
    report = AuditService(runtime.store, runtime.evidence).audit(
        "demo",
        claims=[_claim()],
        citations=[],
        resolver_snapshot=_resolver(),
        corpus_snapshot=_corpus(),
    )

    verdict = next(
        item
        for item in report.verdicts
        if item.category == AuditCategory.CITATION_EXISTENCE
    )
    assert report.status == AuditStatus.FAIL
    assert verdict.status == AuditStatus.FAIL
    assert "missing" in verdict.reasons[0]


def test_citation_can_be_resolved_by_title(runtime, project):
    citation = CitationRef(
        citation_id="cite-by-title",
        title="Current synthetic paper",
        locator="p.1",
    )
    claim = _claim().model_copy(update={"citation_ids": [citation.citation_id]})
    report = AuditService(runtime.store, runtime.evidence).audit(
        "demo",
        claims=[claim],
        citations=[citation],
        resolver_snapshot=_resolver(),
        corpus_snapshot=_corpus(),
    )

    verdict = next(
        item
        for item in report.verdicts
        if item.category == AuditCategory.CITATION_EXISTENCE
    )
    assert verdict.status == AuditStatus.PASS


def test_retracted_citation_fails_and_corrected_relation_is_traceable(runtime, project):
    service = AuditService(runtime.store, runtime.evidence)
    retracted = service.audit(
        "demo",
        claims=[_claim()],
        citations=[_citation()],
        resolver_snapshot=_resolver(status="retracted"),
        corpus_snapshot=_corpus(),
    )
    status_verdict = next(
        item
        for item in retracted.verdicts
        if item.category == AuditCategory.PUBLICATION_STATUS
    )
    assert retracted.status == AuditStatus.FAIL
    assert status_verdict.status == AuditStatus.FAIL

    corrected = service.audit(
        "demo",
        claims=[_claim()],
        citations=[_citation()],
        resolver_snapshot=_resolver(
            version="resolver-v2", status="corrected", related_source_ids=["paper-v2"]
        ),
        corpus_snapshot=_corpus(),
    )
    corrected_status = next(
        item
        for item in corrected.verdicts
        if item.category == AuditCategory.PUBLICATION_STATUS
    )
    assert corrected_status.status == AuditStatus.PASS
    assert corrected_status.related_source_ids == ["paper-v2"]
    assert "traceable" in corrected_status.reasons[0]


def test_resolver_unavailable_is_unknown_and_never_fail_open(runtime, project):
    report = AuditService(runtime.store, runtime.evidence).audit(
        "demo",
        claims=[_claim()],
        citations=[_citation()],
        resolver_snapshot=_resolver(available=False),
        corpus_snapshot=_corpus(),
    )

    citation_verdicts = [
        item
        for item in report.verdicts
        if item.category in {
            AuditCategory.CITATION_EXISTENCE,
            AuditCategory.PUBLICATION_STATUS,
        }
    ]
    assert report.status == AuditStatus.UNKNOWN
    assert citation_verdicts
    assert all(item.status == AuditStatus.UNKNOWN for item in citation_verdicts)


def test_locator_missing_text_is_unknown_but_locator_mismatch_fails(runtime, project):
    service = AuditService(runtime.store, runtime.evidence)
    no_text = service.audit(
        "demo",
        claims=[_claim()],
        citations=[_citation()],
        resolver_snapshot=_resolver(),
        corpus_snapshot=_corpus(available=False),
    )
    no_text_locator = next(
        item
        for item in no_text.verdicts
        if item.category == AuditCategory.LOCATOR_CONSISTENCY
    )
    assert no_text_locator.status == AuditStatus.UNKNOWN

    mismatch = service.audit(
        "demo",
        claims=[_claim()],
        citations=[_citation()],
        resolver_snapshot=_resolver(),
        corpus_snapshot=_corpus(text="An unrelated paragraph discusses a different topic."),
    )
    mismatch_locator = next(
        item
        for item in mismatch.verdicts
        if item.category == AuditCategory.LOCATOR_CONSISTENCY
    )
    assert mismatch_locator.status == AuditStatus.FAIL
    assert mismatch.status == AuditStatus.FAIL


def test_unbound_claim_is_unknown_and_explicitly_reported(runtime, project):
    report = AuditService(runtime.store, runtime.evidence).audit(
        "demo",
        claims=[_claim()],
        citations=[_citation()],
        resolver_snapshot=_resolver(),
        corpus_snapshot=_corpus(),
    )

    unbound = next(
        item for item in report.verdicts if item.category == AuditCategory.UNBOUND_CLAIM
    )
    assert unbound.status == AuditStatus.UNKNOWN
    assert report.unverified_claims == ["[未验证] The source supports a bounded evaluation claim."]


def test_unknown_evidence_id_is_unknown_and_cannot_support_claim(runtime, project):
    report = AuditService(runtime.store, runtime.evidence).audit(
        "demo",
        claims=[_claim(evidence_ids=["ev-missing"])],
        citations=[_citation()],
        resolver_snapshot=_resolver(),
        corpus_snapshot=_corpus(),
    )

    reconciliation = report.evidence_reconciliation[0]
    evidence_verdict = next(
        item
        for item in report.verdicts
        if item.category == AuditCategory.EVIDENCE_RECONCILIATION
    )
    assert reconciliation.status.value == "unknown"
    assert reconciliation.traceable is False
    assert evidence_verdict.status == AuditStatus.UNKNOWN
    assert report.unverified_claims == ["[未验证] The source supports a bounded evaluation claim."]


def test_in_runtime_audit_returns_candidates_through_evidence_service(runtime, project):
    report = AuditService(runtime.store, runtime.evidence).audit(
        "demo",
        claims=[_claim()],
        citations=[_citation()],
        resolver_snapshot=_resolver(),
        corpus_snapshot=_corpus(),
        mode=AuditMode.IN_RUNTIME,
    )

    assert len(report.evidence_candidates) == 1
    assert report.admission_results[0].status == EvidenceAdmissionStatus.ACCEPTED
    assert runtime.evidence.get(report.admission_results[0].evidence_id) is not None
    assert len(runtime.evidence.list("demo")) == 1


def test_duplicate_and_conflict_candidates_are_reconciled(runtime, project):
    service = AuditService(runtime.store, runtime.evidence)
    first = service.audit(
        "demo",
        claims=[_claim()],
        citations=[_citation()],
        resolver_snapshot=_resolver(),
        corpus_snapshot=_corpus(),
        mode=AuditMode.IN_RUNTIME,
    )
    assert first.admission_results[0].status == EvidenceAdmissionStatus.ACCEPTED

    duplicate = service.audit(
        "demo",
        claims=[_claim(evidence_ids=[first.admission_results[0].evidence_id])],
        citations=[_citation()],
        resolver_snapshot=_resolver(version="resolver-v2"),
        corpus_snapshot=_corpus(),
        mode=AuditMode.IN_RUNTIME,
    )
    assert duplicate.admission_results[0].status == EvidenceAdmissionStatus.DUPLICATE

    conflict = service.audit(
        "demo",
        claims=[_claim(text="A different claim is attached to the same source locator.")],
        citations=[_citation()],
        resolver_snapshot=_resolver(version="resolver-v3"),
        corpus_snapshot=_corpus(
            text="A different claim is attached to the same source locator."
        ),
        mode=AuditMode.IN_RUNTIME,
    )
    assert conflict.admission_results[0].status == EvidenceAdmissionStatus.CONFLICT
    assert len(runtime.evidence.list("demo")) == 1


def test_standalone_mode_never_admits_candidates(runtime, project):
    report = AuditService(runtime.store).audit(
        "demo",
        claims=[_claim()],
        citations=[_citation()],
        resolver_snapshot=_resolver(),
        corpus_snapshot=_corpus(),
        mode=AuditMode.STANDALONE,
    )

    assert report.evidence_candidates == []
    assert report.admission_results == []
    assert runtime.store.list("evidence", project_id="demo") == []


def test_audit_is_idempotent_and_snapshot_version_is_part_of_identity(runtime, project):
    service = AuditService(runtime.store, runtime.evidence)
    kwargs = {
        "claims": [_claim()],
        "citations": [_citation()],
        "resolver_snapshot": _resolver(),
        "corpus_snapshot": _corpus(),
    }
    first = service.audit("demo", **kwargs)
    second = service.audit("demo", **kwargs)
    assert second.model_dump(mode="json") == first.model_dump(mode="json")
    audit_events = [
        event
        for event in runtime.store.events("demo")
        if event["event_type"] == "audit.report_created"
    ]
    assert len(audit_events) == 1

    changed = service.audit(
        "demo",
        **{**kwargs, "resolver_snapshot": _resolver(version="resolver-v2")},
    )
    assert changed.report_id != first.report_id
    assert changed.resolver_snapshot_version == "resolver-v2"


def test_audit_keeps_deterministic_and_model_assisted_verdicts_separate(runtime, project):
    report = AuditService(runtime.store, runtime.evidence).audit(
        "demo",
        claims=[_claim(locator_method=LocatorMethod.MODEL_ASSISTED)],
        citations=[_citation()],
        resolver_snapshot=_resolver(),
        corpus_snapshot=CorpusSnapshot(version="corpus-v1"),
        model_assisted_locators={
            "claim-1:cite-current": LocatorAssessment(
                status=AuditStatus.PASS,
                confidence=0.91,
                reason="synthetic model assessment",
            )
        },
    )

    assert report.deterministic_verdicts
    assert len(report.model_assisted_verdicts) == 1
    model_verdict = report.model_assisted_verdicts[0]
    assert model_verdict.method == AuditMethod.MODEL_ASSISTED
    assert model_verdict.confidence == 0.91
    assert model_verdict.status == AuditStatus.PASS


def test_low_confidence_model_assistance_is_unknown(runtime, project):
    report = AuditService(runtime.store, runtime.evidence).audit(
        "demo",
        claims=[_claim(locator_method=LocatorMethod.MODEL_ASSISTED)],
        citations=[_citation()],
        resolver_snapshot=_resolver(),
        corpus_snapshot=CorpusSnapshot(version="corpus-v1"),
        model_assisted_locators={
            "claim-1:cite-current": LocatorAssessment(
                status=AuditStatus.PASS,
                confidence=0.79,
                reason="below threshold synthetic assessment",
            )
        },
    )

    assert report.model_assisted_verdicts[0].status == AuditStatus.UNKNOWN
    assert report.model_assisted_verdicts[0].confidence == 0.79


class _AdmissionOnlyGateway:
    def __init__(self):
        self.calls: list[EvidenceCandidate] = []

    def admit_candidate(self, candidate: EvidenceCandidate, *, actor: str):
        self.calls.append(candidate)
        return EvidenceAdmissionResult(
            project_id=candidate.project_id,
            candidate_id=candidate.candidate_id,
            status=EvidenceAdmissionStatus.ACCEPTED,
        )


def test_audit_persists_reports_and_uses_only_candidate_admission(runtime, project):
    gateway = _AdmissionOnlyGateway()
    report = AuditService(runtime.store, gateway).audit(
        "demo",
        claims=[_claim()],
        citations=[_citation()],
        resolver_snapshot=_resolver(),
        corpus_snapshot=_corpus(),
        mode=AuditMode.IN_RUNTIME,
    )

    assert len(gateway.calls) == 1
    assert report.admission_results[0].status == EvidenceAdmissionStatus.ACCEPTED
    assert runtime.store.list("evidence", project_id="demo") == []
    assert runtime.store.get("audit_report", report.audit_key) is not None


def test_invalid_evidence_remains_traceable_but_cannot_support_claim(runtime, project):
    evidence = EvidenceCandidate(
        project_id="demo",
        evidence_type=EvidenceType.PAPER,
        grade=EvidenceGrade.E1,
        title="Invalidatable source",
        claim="The source supports a bounded evaluation claim.",
        source_id="paper-current",
        source_uri="https://example.invalid/paper-current",
        locator="p.1",
        independent_source="paper-current",
    )
    admission = runtime.evidence.admit_candidate(evidence, actor="test")
    runtime.evidence.invalidate(admission.evidence_id, "synthetic retraction", actor="test")
    report = AuditService(runtime.store, runtime.evidence).audit(
        "demo",
        claims=[_claim(evidence_ids=[admission.evidence_id])],
        citations=[_citation()],
        resolver_snapshot=_resolver(),
        corpus_snapshot=_corpus(),
    )

    reconciliation = report.evidence_reconciliation[0]
    evidence_verdict = next(
        item
        for item in report.verdicts
        if item.category == AuditCategory.EVIDENCE_RECONCILIATION
    )
    assert reconciliation.traceable is True
    assert reconciliation.status.value == "invalid"
    assert evidence_verdict.status == AuditStatus.FAIL
