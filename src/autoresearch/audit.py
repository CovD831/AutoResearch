from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Protocol

from pydantic import BaseModel, Field

from autoresearch.audit_contracts import (
    AuditCategory,
    AuditCitation,
    AuditInvocationReceipt,
    AuditInvocationRequest,
    AuditReceiptStatus,
    AuditReport,
    AuditVerdict,
    AuditVerdictStatus,
    audit_request_fingerprint,
)
from autoresearch.contracts import ArtifactRef, EvidenceCandidate, new_id, utc_now
from autoresearch.resolver import (
    ResolverAdapter,
    ResolverResponse,
    ResolverStatus,
)
from autoresearch.storage import RecordStore


class AuditPersistencePort(Protocol):
    """Persistence operations owned by the Audit boundary."""

    def get_invocation(self, scope: str, key: str) -> dict | None: ...

    def reserve_invocation(self, scope: str, key: str, request: dict) -> bool: ...

    def reclaim_invocation(
        self, scope: str, key: str, *, project_id: str | None, reason: str
    ) -> None:
        """Drop a pending invocation record left behind by a crashed run (F-9).

        Audit performs no external side effects before finalization, so the
        caller may reclaim a pending record and recompute deterministically.
        """
        ...

    def save_report(self, report: AuditReport, project_id: str | None) -> None: ...

    def append_event(
        self,
        event_type: str,
        payload: dict,
        *,
        project_id: str | None,
        actor: str,
    ) -> None: ...

    def finalize_invocation(self, scope: str, key: str, result: dict) -> None: ...


class RecordStoreAuditPersistence:
    """Canonical SQLite implementation of the Audit persistence port."""

    def __init__(self, store: RecordStore):
        self.store = store

    def get_invocation(self, scope: str, key: str) -> dict | None:
        return self.store.get_idempotent(scope, key)

    def reserve_invocation(self, scope: str, key: str, request: dict) -> bool:
        return self.store.reserve_idempotent(scope, key, request)

    def save_report(self, report: AuditReport, project_id: str | None) -> None:
        self.store.put(
            "audit_report",
            report.artifact.artifact_id,
            report,
            project_id=project_id,
            partition="audit",
        )

    def append_event(
        self,
        event_type: str,
        payload: dict,
        *,
        project_id: str | None,
        actor: str,
    ) -> None:
        self.store.append_event(event_type, payload, project_id=project_id, actor=actor)

    def finalize_invocation(self, scope: str, key: str, result: dict) -> None:
        self.store.finalize_idempotent(scope, key, result)

    def reclaim_invocation(
        self, scope: str, key: str, *, project_id: str | None, reason: str
    ) -> None:
        if self.store.delete_idempotent(scope, key):
            self.store.append_event(
                "audit.invocation_reclaimed",
                {"scope": scope, "request_fingerprint": key, "reason": reason},
                project_id=project_id,
                actor="audit_runtime",
            )


class BoundedEvidenceItem(BaseModel):
    """The small, read-only evidence projection exposed to Audit."""

    evidence_id: str
    source_id: str | None = None
    source_uri: str | None = None
    locator: str | None = None
    valid: bool = True
    full_text_available: bool = False


class BoundedEvidenceView(BaseModel):
    items: list[BoundedEvidenceItem] = Field(default_factory=list, max_length=200)

    def for_citation(self, citation: AuditCitation) -> list[BoundedEvidenceItem]:
        evidence_ids = set(citation.evidence_ids)
        return [
            item
            for item in self.items
            if item.valid
            and (
                item.evidence_id in evidence_ids
                or (citation.source_id is not None and item.source_id == citation.source_id)
            )
        ]

    def valid_ids(self) -> set[str]:
        return {item.evidence_id for item in self.items if item.valid}


def read_bounded_evidence_view(
    store: RecordStore,
    project_id: str | None,
    evidence_ids: Iterable[str],
    *,
    max_items: int = 200,
) -> BoundedEvidenceView:
    """Read only bounded evidence metadata; no Audit code writes evidence facts."""

    if project_id is None:
        return BoundedEvidenceView()
    selected: list[BoundedEvidenceItem] = []
    seen: set[str] = set()
    for evidence_id in evidence_ids:
        if evidence_id in seen or len(selected) >= max_items:
            continue
        seen.add(evidence_id)
        raw = store.get("evidence", evidence_id)
        if raw is None or raw.get("project_id") != project_id:
            continue
        status = store.get("evidence_status", evidence_id) or {}
        source_id = raw.get("source_id")
        full_text_available = False
        if source_id:
            paper = store.get("paper", source_id)
            full_text_available = bool(paper and paper.get("full_text_path"))
        selected.append(
            BoundedEvidenceItem(
                evidence_id=evidence_id,
                source_id=source_id,
                source_uri=raw.get("source_uri"),
                locator=raw.get("locator"),
                valid=bool(status.get("valid", raw.get("valid", True))),
                full_text_available=full_text_available,
            )
        )
    return BoundedEvidenceView(items=selected)


class AuditRuntime:
    """Audit boundary that produces reports and candidates, never EvidenceItems."""

    scope = "audit"

    def __init__(
        self,
        store: RecordStore | AuditPersistencePort,
        resolver: ResolverAdapter,
        *,
        persistence: AuditPersistencePort | None = None,
    ):
        # Keep the historical ``AuditRuntime(store, resolver)`` constructor while
        # routing all durable writes through the narrow Audit persistence port.
        self.store = store if isinstance(store, RecordStore) else None
        self.persistence = persistence or (
            RecordStoreAuditPersistence(store) if isinstance(store, RecordStore) else store
        )
        self.resolver = resolver

    def _resolver_response(
        self,
        citation: AuditCitation,
        request: AuditInvocationRequest,
    ) -> ResolverResponse:
        if request.resolver_snapshot_version != self.resolver.snapshot_version:
            return ResolverResponse(
                status=ResolverStatus.UNAVAILABLE,
                snapshot_version=self.resolver.snapshot_version,
                diagnostics=[
                    "resolver snapshot version does not match the requested audit snapshot"
                ],
            )
        try:
            return self.resolver.resolve(citation)
        except Exception as exc:  # Adapter errors are unknown, never a pass.
            return ResolverResponse(
                status=ResolverStatus.ERROR,
                snapshot_version=self.resolver.snapshot_version,
                diagnostics=[f"resolver adapter error: {type(exc).__name__}"],
            )

    @staticmethod
    def _verdict(
        *,
        category: AuditCategory,
        target_id: str,
        status: AuditVerdictStatus,
        reason_code: str,
        message: str,
        request: AuditInvocationRequest,
        citation: AuditCitation | None = None,
        claim_id: str | None = None,
        evidence_ids: list[str] | None = None,
        diagnostics: list[str] | None = None,
    ) -> AuditVerdict:
        return AuditVerdict(
            verdict_id=new_id("verdict"),
            category=category,
            status=status,
            target_id=target_id,
            claim_id=claim_id,
            citation_id=citation.citation_id if citation else None,
            reason_code=reason_code,
            message=message,
            resolver_snapshot_version=request.resolver_snapshot_version,
            evidence_ids=evidence_ids or [],
            diagnostics=diagnostics or [],
        )

    def _citation_verdicts(
        self,
        request: AuditInvocationRequest,
        citation: AuditCitation,
        view: BoundedEvidenceView,
    ) -> tuple[list[AuditVerdict], ResolverResponse]:
        response = self._resolver_response(citation, request)
        verdicts: list[AuditVerdict] = []
        if AuditCategory.EXISTENCE in request.categories:
            if response.status == ResolverStatus.FOUND:
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.EXISTENCE,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.PASS,
                        reason_code="resolver_match",
                        message="citation exists in the versioned resolver snapshot",
                        request=request,
                        citation=citation,
                        evidence_ids=citation.evidence_ids,
                    )
                )
            elif response.status == ResolverStatus.NOT_FOUND:
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.EXISTENCE,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.FAIL,
                        reason_code="resolver_not_found",
                        message="citation is absent from the resolver snapshot",
                        request=request,
                        citation=citation,
                        diagnostics=response.diagnostics,
                    )
                )
            else:
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.EXISTENCE,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.UNKNOWN,
                        reason_code="resolver_unavailable",
                        message="citation existence cannot be established",
                        request=request,
                        citation=citation,
                        diagnostics=response.diagnostics,
                    )
                )

        if AuditCategory.RETRACTION in request.categories:
            if response.status != ResolverStatus.FOUND or response.record is None:
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.RETRACTION,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.UNKNOWN,
                        reason_code="retraction_status_unknown",
                        message="retraction status is unavailable",
                        request=request,
                        citation=citation,
                        diagnostics=response.diagnostics,
                    )
                )
            elif response.record.retracted:
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.RETRACTION,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.FAIL,
                        reason_code="source_retracted",
                        message="resolver snapshot marks the source as retracted",
                        request=request,
                        citation=citation,
                    )
                )
            else:
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.RETRACTION,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.PASS,
                        reason_code="source_not_retracted",
                        message="resolver snapshot does not mark the source as retracted",
                        request=request,
                        citation=citation,
                    )
                )

        if AuditCategory.CORRECTION in request.categories:
            if response.status != ResolverStatus.FOUND or response.record is None:
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.CORRECTION,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.UNKNOWN,
                        reason_code="correction_status_unknown",
                        message="correction status is unavailable",
                        request=request,
                        citation=citation,
                        diagnostics=response.diagnostics,
                    )
                )
            elif response.record.corrected or response.record.version_state == "corrected":
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.CORRECTION,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.FAIL,
                        reason_code="source_corrected",
                        message=(
                            "resolver snapshot marks the source as corrected; review the version"
                        ),
                        request=request,
                        citation=citation,
                    )
                )
            else:
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.CORRECTION,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.PASS,
                        reason_code="source_not_corrected",
                        message="resolver snapshot has no correction flag",
                        request=request,
                        citation=citation,
                    )
                )

        if AuditCategory.LOCATOR in request.categories:
            matches = view.for_citation(citation)
            if not matches:
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.LOCATOR,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.UNKNOWN,
                        reason_code="evidence_not_in_bounded_view",
                        message="no valid evidence for this citation is visible to Audit",
                        request=request,
                        citation=citation,
                    )
                )
            elif not citation.locator:
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.LOCATOR,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.UNKNOWN,
                        reason_code="locator_missing",
                        message="citation has no locator to compare",
                        request=request,
                        citation=citation,
                    )
                )
            elif any(not item.full_text_available for item in matches):
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.LOCATOR,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.UNKNOWN,
                        reason_code="full_text_unavailable",
                        message="full text is unavailable; locator cannot be verified",
                        request=request,
                        citation=citation,
                    )
                )
            elif any(item.locator == citation.locator for item in matches):
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.LOCATOR,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.PASS,
                        reason_code="locator_match",
                        message="citation locator matches the bounded evidence view",
                        request=request,
                        citation=citation,
                        evidence_ids=citation.evidence_ids,
                    )
                )
            else:
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.LOCATOR,
                        target_id=citation.citation_id,
                        status=AuditVerdictStatus.FAIL,
                        reason_code="locator_mismatch",
                        message="citation locator does not match the bounded evidence view",
                        request=request,
                        citation=citation,
                        evidence_ids=citation.evidence_ids,
                    )
                )
        return verdicts, response

    def _candidates(
        self,
        request: AuditInvocationRequest,
        citations: list[AuditCitation],
        verdicts: list[AuditVerdict],
        responses: dict[str, ResolverResponse],
    ) -> list[EvidenceCandidate]:
        if request.mode.value != "in-runtime" or request.project_id is None:
            return []
        candidates: list[EvidenceCandidate] = []
        for citation in citations:
            existence = next(
                (
                    verdict
                    for verdict in verdicts
                    if verdict.citation_id == citation.citation_id
                    and verdict.category == AuditCategory.EXISTENCE
                ),
                None,
            )
            if existence is None or existence.status != AuditVerdictStatus.PASS:
                continue
            response = responses[citation.citation_id]
            source_uri = citation.source_uri or (
                response.record.source_uri if response.record else None
            )
            candidates.append(
                EvidenceCandidate(
                    project_id=request.project_id,
                    run_id=request.run_id,
                    invocation_id=request.invocation_id,
                    title=f"Audit verified citation: {citation.title}",
                    claim=f"Audit found a resolver match for: {citation.title}",
                    source_uri=source_uri,
                    source_id=citation.source_id or citation.doi or citation.arxiv_id,
                    locator=citation.locator,
                    independent_source=(
                        f"{self.resolver.name}:{request.resolver_snapshot_version}"
                    ),
                    adapter=self.resolver.name,
                    adapter_version=self.resolver.version,
                    metadata={
                        "audit_verdict_id": existence.verdict_id,
                        "resolver_snapshot_version": request.resolver_snapshot_version,
                    },
                )
            )
        return candidates

    def invoke(
        self,
        request: AuditInvocationRequest,
        *,
        evidence_view: BoundedEvidenceView | None = None,
    ) -> AuditReport:
        fingerprint = audit_request_fingerprint(request)
        existing = self.persistence.get_invocation(self.scope, fingerprint)
        if existing is not None and isinstance(existing.get("result"), dict):
            report = AuditReport.model_validate(existing["result"])
            receipt = report.receipt.model_copy(
                update={"status": AuditReceiptStatus.REPLAYED, "updated_at": utc_now()}
            )
            return report.model_copy(update={"receipt": receipt})
        reserved = self.persistence.reserve_invocation(
            self.scope,
            fingerprint,
            {
                "request": request.model_dump(mode="json"),
                "request_fingerprint": fingerprint,
            },
        )
        if not reserved:
            existing = self.persistence.get_invocation(self.scope, fingerprint)
            if existing is None:
                raise RuntimeError("audit idempotency reservation disappeared")
            if existing.get("state") == "pending":
                # A pending record can only come from a crashed invocation:
                # Audit performs no external side effects before finalization,
                # so reclaim and recompute (F-9); fail-closed is preserved.
                self.persistence.reclaim_invocation(
                    self.scope,
                    fingerprint,
                    project_id=request.project_id,
                    reason="crashed pending audit invocation reclaimed on retry",
                )
                reserved = self.persistence.reserve_invocation(
                    self.scope,
                    fingerprint,
                    {
                        "request": request.model_dump(mode="json"),
                        "request_fingerprint": fingerprint,
                    },
                )
                if not reserved:
                    raise RuntimeError(
                        "audit idempotency reservation raced after reclaim"
                    )
            else:
                if not isinstance(existing.get("result"), dict):
                    raise RuntimeError(
                        "finalized audit invocation has no replayable result"
                    )
                report = AuditReport.model_validate(existing["result"])
                receipt = report.receipt.model_copy(
                    update={"status": AuditReceiptStatus.REPLAYED, "updated_at": utc_now()}
                )
                return report.model_copy(update={"receipt": receipt})

        view = evidence_view or BoundedEvidenceView()
        verdicts: list[AuditVerdict] = []
        responses: dict[str, ResolverResponse] = {}
        for citation in request.citations:
            citation_verdicts, response = self._citation_verdicts(request, citation, view)
            verdicts.extend(citation_verdicts)
            responses[citation.citation_id] = response

        if AuditCategory.BINDING in request.categories:
            valid_evidence_ids = view.valid_ids()
            citation_ids = {citation.citation_id for citation in request.citations}
            for claim in request.claims:
                bound = bool(
                    (set(claim.evidence_ids) & valid_evidence_ids)
                    or (set(claim.citation_ids) & citation_ids)
                )
                verdicts.append(
                    self._verdict(
                        category=AuditCategory.BINDING,
                        target_id=claim.claim_id,
                        claim_id=claim.claim_id,
                        status=AuditVerdictStatus.PASS if bound else AuditVerdictStatus.FAIL,
                        reason_code="claim_bound" if bound else "unbound_claim",
                        message=(
                            "claim has a citation or valid evidence binding"
                            if bound
                            else "[未验证] claim has no citation or valid evidence binding"
                        ),
                        request=request,
                        evidence_ids=claim.evidence_ids,
                    )
                )

        candidates = self._candidates(request, request.citations, verdicts, responses)
        unknown_count = sum(verdict.status == AuditVerdictStatus.UNKNOWN for verdict in verdicts)
        diagnostics = [
            f"{unknown_count} verdict(s) remain unknown; Audit is fail-closed"
        ] if unknown_count else []
        report_id = new_id("audit")
        artifact_id = new_id("artifact")
        artifact = ArtifactRef(
            artifact_id=artifact_id,
            kind="audit_report",
            uri=f"store://audit_report/{artifact_id}",
            summary="Versioned AuditReport artifact",
        )
        receipt = AuditInvocationReceipt(
            invocation_id=request.invocation_id,
            status=AuditReceiptStatus.COMPLETED,
            request_fingerprint=fingerprint,
            artifact_id=artifact_id,
            verdict_count=len(verdicts),
            diagnostics=diagnostics,
        )
        report = AuditReport(
            report_id=report_id,
            request=request,
            request_fingerprint=fingerprint,
            receipt=receipt,
            artifact=artifact,
            verdicts=verdicts,
            candidates=candidates,
            diagnostics=diagnostics,
            bounded_evidence_count=len(view.items),
        )
        checksum_payload = report.model_dump(mode="json")
        checksum_payload["artifact"].pop("checksum", None)
        checksum = hashlib.sha256(
            json.dumps(checksum_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        report = report.model_copy(
            update={"artifact": artifact.model_copy(update={"checksum": checksum})}
        )
        self.persistence.save_report(report, request.project_id)
        self.persistence.append_event(
            "audit.report_created",
            {
                "report_id": report_id,
                "artifact_id": artifact_id,
                "request_fingerprint": fingerprint,
                "verdict_count": len(verdicts),
                "unknown_count": unknown_count,
            },
            project_id=request.project_id,
            actor="audit_runtime",
        )
        self.persistence.finalize_invocation(
            self.scope,
            fingerprint,
            report.model_dump(mode="json"),
        )
        return report


__all__ = [
    "AuditPersistencePort",
    "AuditRuntime",
    "BoundedEvidenceItem",
    "BoundedEvidenceView",
    "RecordStoreAuditPersistence",
    "read_bounded_evidence_view",
]
