from __future__ import annotations

from typing import Any, Protocol

from autoresearch.contracts import PaperRecord
from autoresearch.invocation_contracts import (
    CapabilityManifest,
    EvidenceCandidate,
    InvocationPhase,
    InvocationReceipt,
    InvocationStatus,
    PaperSearchInvocation,
    PaperSearchRequest,
    request_fingerprint,
)
from autoresearch.storage import RecordStore


class PaperSearchServicePort(Protocol):
    def search(
        self,
        project_id: str,
        queries: list[str],
        *,
        seed_papers: list[PaperRecord] | None = None,
        per_connector_limit: int = 5,
    ) -> Any: ...


class InvocationConflictError(ValueError):
    """The same invocation identity was reused with a different request."""


class PendingInvocationError(RuntimeError):
    """A previous process reserved the invocation but did not finalize it."""


class UnknownProviderError(RuntimeError):
    """The provider outcome cannot be proven from the connector response."""


class PaperSearchCapabilityAdapter:
    """Reliable S1 boundary around the legacy PaperSearchService."""

    def __init__(
        self,
        service: PaperSearchServicePort,
        store: RecordStore,
        manifest: CapabilityManifest | None = None,
    ):
        self.service = service
        self.store = store
        self.manifest = manifest or CapabilityManifest(name="paper_search", version="1")

    @property
    def scope(self) -> str:
        return self.manifest.name

    @staticmethod
    def _key(request: PaperSearchRequest) -> str:
        return f"{request.run_id}:{request.invocation_id}"

    @staticmethod
    def _outcome_parts(outcome: Any) -> tuple[list[PaperRecord], list[str]]:
        papers = [
            paper if isinstance(paper, PaperRecord) else PaperRecord.model_validate(paper)
            for paper in outcome.papers
        ]
        diagnostics = [str(item) for item in getattr(outcome, "diagnostics", [])]
        return papers, diagnostics

    @staticmethod
    def _status(papers: list[PaperRecord], diagnostics: list[str]) -> InvocationStatus:
        if papers:
            return InvocationStatus.COMPLETED
        lowered = " ".join(diagnostics).lower()
        uncertain_markers = (
            "disabled",
            "failed",
            "unavailable",
            "timeout",
            "unknown",
            "error",
        )
        if any(marker in lowered for marker in uncertain_markers):
            return InvocationStatus.UNKNOWN_OUTCOME
        return InvocationStatus.COMPLETED_EMPTY

    def _candidates(
        self,
        request: PaperSearchRequest,
        papers: list[PaperRecord],
    ) -> list[EvidenceCandidate]:
        candidates: list[EvidenceCandidate] = []
        for paper in papers:
            independent_source = (
                paper.doi
                or paper.url
                or f"{paper.source}:{paper.source_record_id or paper.paper_id}"
            )
            candidates.append(
                EvidenceCandidate(
                    project_id=request.project_id,
                    run_id=request.run_id,
                    invocation_id=request.invocation_id,
                    claim=f"Bibliographic record exists for: {paper.title}",
                    source_id=paper.paper_id,
                    source_uri=paper.url,
                    independent_source=independent_source,
                    adapter=self.manifest.name,
                    adapter_version=self.manifest.version,
                )
            )
        return candidates

    def _record_request(self, request: PaperSearchRequest, fingerprint: str) -> dict[str, Any]:
        return {
            **request.model_dump(mode="json"),
            "request_fingerprint": fingerprint,
        }

    def _build_result(
        self,
        request: PaperSearchRequest,
        fingerprint: str,
        status: InvocationStatus,
        papers: list[PaperRecord],
        diagnostics: list[str],
    ) -> PaperSearchInvocation:
        receipt = InvocationReceipt(
            invocation_id=request.invocation_id,
            status=status,
            outcome_status=status,
            adapter=self.manifest.name,
            adapter_version=self.manifest.version,
            request_fingerprint=fingerprint,
            paper_ids=[paper.paper_id for paper in papers],
            diagnostics=diagnostics,
        )
        return PaperSearchInvocation(
            request=request,
            receipt=receipt,
            papers=papers,
            diagnostics=diagnostics,
            evidence_candidates=self._candidates(request, papers),
        )

    @staticmethod
    def _exception_status(exc: Exception) -> InvocationStatus:
        """Classify only explicitly uncertain transport/provider failures as unknown."""

        if isinstance(exc, (TimeoutError, ConnectionError, OSError, UnknownProviderError)):
            return InvocationStatus.UNKNOWN_OUTCOME
        return InvocationStatus.FAILED

    @staticmethod
    def _exception_diagnostic(exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "provider timeout; outcome is unknown"
        if isinstance(exc, (ConnectionError, OSError, UnknownProviderError)):
            detail = f": {exc}" if str(exc) else ""
            return f"provider outcome is unknown after {type(exc).__name__}{detail}"
        return f"provider failure: {type(exc).__name__}: {exc}" if str(exc) else (
            f"provider failure: {type(exc).__name__}"
        )

    def _replay(self, record: dict[str, Any]) -> PaperSearchInvocation:
        result = record.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("finalized invocation has no replayable result")
        invocation = PaperSearchInvocation.model_validate(result)
        outcome_status = invocation.receipt.outcome_status or invocation.receipt.status
        receipt = invocation.receipt.model_copy(
            update={"status": InvocationStatus.REPLAYED, "outcome_status": outcome_status}
        )
        return invocation.model_copy(update={"receipt": receipt})

    def invoke(self, request: PaperSearchRequest) -> PaperSearchInvocation:
        fingerprint = request_fingerprint(request)
        key = self._key(request)
        existing = self.store.get_idempotent(self.scope, key)
        if existing is not None:
            existing_fingerprint = existing.get("request_fingerprint")
            if existing_fingerprint != fingerprint:
                raise InvocationConflictError(
                    "invocation identity is already bound to another request"
                )
            if existing.get("state") == "pending":
                raise PendingInvocationError("invocation outcome is unknown; recover explicitly")
            return self._replay(existing)

        reserved = self.store.reserve_idempotent(
            self.scope,
            key,
            self._record_request(request, fingerprint),
        )
        if not reserved:
            existing = self.store.get_idempotent(self.scope, key)
            if existing is None:
                raise RuntimeError("idempotency reservation disappeared")
            if existing.get("request_fingerprint") != fingerprint:
                raise InvocationConflictError(
                    "invocation identity is already bound to another request"
                )
            if existing.get("state") == "pending":
                raise PendingInvocationError("invocation outcome is unknown; recover explicitly")
            return self._replay(existing)

        self.store.append_event(
            "capability.invocation_reserved",
            {"invocation_id": request.invocation_id, "request_fingerprint": fingerprint},
            project_id=request.project_id,
            actor="capability_adapter",
        )
        self.store.mark_idempotent_phase(
            self.scope,
            key,
            InvocationPhase.SERVICE_STARTED.value,
        )
        self.store.append_event(
            "capability.service_started",
            {"invocation_id": request.invocation_id},
            project_id=request.project_id,
            actor="capability_adapter",
        )
        try:
            outcome = self.service.search(
                request.project_id,
                [request.query],
                seed_papers=request.seed_papers,
                per_connector_limit=request.limit,
            )
            papers, diagnostics = self._outcome_parts(outcome)
            status = self._status(papers, diagnostics)
        except Exception as exc:
            papers = []
            diagnostics = [self._exception_diagnostic(exc)]
            status = self._exception_status(exc)

        invocation = self._build_result(request, fingerprint, status, papers, diagnostics)
        self.store.mark_idempotent_phase(
            self.scope,
            key,
            InvocationPhase.SERVICE_RETURNED.value,
            staged_result=invocation.model_dump(mode="json"),
        )
        self.store.append_event(
            "capability.service_returned",
            {
                "invocation_id": request.invocation_id,
                "status": status.value,
                "paper_ids": [paper.paper_id for paper in papers],
                "diagnostics": diagnostics,
            },
            project_id=request.project_id,
            actor="capability_adapter",
        )
        self.store.finalize_idempotent(
            self.scope,
            key,
            invocation.model_dump(mode="json"),
        )
        self.store.append_event(
            "capability.invocation_finalized",
            {
                "invocation_id": request.invocation_id,
                "status": status.value,
                "paper_ids": [paper.paper_id for paper in papers],
                "diagnostics": diagnostics,
            },
            project_id=request.project_id,
            actor="capability_adapter",
        )
        return invocation

    def recover_pending(
        self,
        run_id: str,
        invocation_id: str,
        *,
        reason: str,
        outcome_status: InvocationStatus | None = None,
    ) -> PaperSearchInvocation:
        if outcome_status is not None and outcome_status not in (
            InvocationStatus.FAILED,
            InvocationStatus.UNKNOWN_OUTCOME,
        ):
            raise ValueError("pending recovery must close as failed or unknown_outcome")
        key = f"{run_id}:{invocation_id}"
        existing = self.store.get_idempotent(self.scope, key)
        if existing is None:
            raise KeyError(f"unknown idempotency record: {self.scope}:{key}")
        if existing.get("state") != "pending":
            raise RuntimeError("idempotency record is already finalized")
        phase = existing.get("phase", InvocationPhase.RESERVED.value)
        staged_result = existing.get("staged_result")
        if phase == InvocationPhase.SERVICE_RETURNED.value and isinstance(staged_result, dict):
            invocation = PaperSearchInvocation.model_validate(staged_result)
            self.store.finalize_idempotent(
                self.scope,
                key,
                invocation.model_dump(mode="json"),
            )
            self.store.append_event(
                "capability.invocation_recovered",
                {
                    "invocation_id": invocation_id,
                    "status": invocation.receipt.outcome_status.value,
                    "reason": "finalized staged service result",
                    "phase": phase,
                    "recovery_action": "finalize_staged_result",
                },
                project_id=invocation.request.project_id,
                actor="capability_adapter",
            )
            return invocation
        request = PaperSearchRequest.model_validate(existing.get("request", {}))
        fingerprint = existing.get("request_fingerprint") or request_fingerprint(request)
        if phase == InvocationPhase.RESERVED.value:
            status = InvocationStatus.FAILED
            recovery_reason = f"{reason}; recovery found reserved without service start"
        elif phase == InvocationPhase.SERVICE_STARTED.value:
            status = InvocationStatus.UNKNOWN_OUTCOME
            recovery_reason = f"{reason}; recovery found service_started without staged result"
        elif phase == InvocationPhase.SERVICE_RETURNED.value:
            status = InvocationStatus.UNKNOWN_OUTCOME
            recovery_reason = f"{reason}; service_returned is missing staged result"
        else:
            raise RuntimeError(f"cannot recover pending invocation at phase {phase!r}")
        invocation = self._build_result(request, fingerprint, status, [], [recovery_reason])
        self.store.finalize_idempotent(
            self.scope,
            key,
            invocation.model_dump(mode="json"),
        )
        self.store.append_event(
            "capability.invocation_recovered",
            {
                "invocation_id": invocation_id,
                "status": status.value,
                "reason": recovery_reason,
                "phase": phase,
                "recovery_action": "close_pending",
            },
            project_id=request.project_id,
            actor="capability_adapter",
        )
        return invocation

    def fail_pending(
        self, run_id: str, invocation_id: str, *, reason: str
    ) -> PaperSearchInvocation:
        return self.recover_pending(
            run_id,
            invocation_id,
            reason=reason,
            outcome_status=InvocationStatus.FAILED,
        )
