"""B4 S3-B Reader / Writer Ports tests.

Contract-level assertions only. The three adapter outputs must agree on
schema, claim binding, gate compliance, and planned-only enforcement — never on
surface text. Formal evidence is only admitted through
``EvidenceService.admit_candidate``; no port adapter writes it directly.
"""

from __future__ import annotations

from autoresearch.contracts import (
    EvidenceGrade,
    EvidenceType,
    PaperRecord,
    ReadingCard,
)
from autoresearch.pipeline_contracts import (
    EvidenceCandidate,
    ReadinessStatus,
    SectionDraft,
)
from autoresearch.reader_writer_ports import (
    AdapterKind,
    BindingStatus,
    NativeReaderAdapter,
    NativeWriterAdapter,
    ParityStatus,
    StructuredDraftPayload,
    StructuredReaderAdapter,
    StructuredReadingPayload,
    StructuredWriterAdapter,
    bind_claims,
    compare_writer_parity,
    gate_compliance,
)


def _paper(project_id: str) -> PaperRecord:
    return PaperRecord(
        project_id=project_id,
        title="Synthetic evidence-first evaluation study",
        abstract=(
            "We propose an evidence-first evaluation method. The experiment "
            "measures material readiness. We note a limitation: one comparator "
            "is still missing for a fully closed comparison."
        ),
        authors=["Synthetic Author"],
        year=2026,
        doi="10.0000/example.invalid",
        url=None,
        source="offline",
        source_record_id="example.invalid",
    )


def _admit_candidate(runtime, project_id: str) -> EvidenceCandidate:
    candidate = EvidenceCandidate(
        project_id=project_id,
        evidence_type=EvidenceType.PAPER,
        grade=EvidenceGrade.E1,
        title="Evidence-aware writing input",
        claim="The source exists and can support the section plan.",
        source_uri="https://example.invalid/source-a",
        source_id="source-a",
        locator="section 1",
        checksum="sha256:source-a",
        independent_source="source-a",
    )
    return runtime.evidence.admit_candidate(candidate, actor="tester")


def _card(project_id: str, evidence_id: str) -> ReadingCard:
    return ReadingCard(
        project_id=project_id,
        paper_id="paper-a",
        research_question="How should the evaluation section stay evidence-first?",
        method="Evidence-first section planning",
        data_or_setting="Synthetic paper-project notes",
        findings=["A section draft should keep claims and evidence visible together."],
        limitations=["One comparator is still missing for a fully closed comparison."],
        locators=["p.1"],
        evidence_ids=[evidence_id],
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# Reader port
# ---------------------------------------------------------------------------


def test_native_reader_produces_typed_card_and_candidate(runtime, project):
    paper = _paper("demo")
    adapter = NativeReaderAdapter()
    result = adapter.read(_reader_request("r1", paper))
    assert result.adapter is AdapterKind.NATIVE
    assert result.card.paper_id == paper.paper_id
    assert result.card.findings
    assert result.card.evidence_ids == []
    # External/native output stays a candidate until admission.
    assert result.candidate.evidence_type is EvidenceType.PAPER
    admission = runtime.evidence.admit_candidate(result.candidate, actor="tester")
    assert admission.status.value == "accepted"
    assert runtime.evidence.list("demo")


def test_structured_reader_parity_with_native_shape(runtime, project):
    paper = _paper("demo")
    native = NativeReaderAdapter().read(_reader_request("n1", paper))
    payload = StructuredReadingPayload(
        research_question="Evidence-first evaluation?",
        method="Evidence-first planning",
        data_or_setting="Offline synthetic material",
        findings=["A structured reader can reproduce the typed card shape."],
        limitations=["Structured extraction remains synthetic."],
        locators=["p.1"],
        confidence=0.8,
        source_uri=None,
        locator="p.1",
        independent_source="example.invalid",
    )
    llm_adapter = StructuredReaderAdapter(
        AdapterKind.LLM, adapter_name="paper_reader.llm", adapter_version="0.1"
    )
    structured = llm_adapter.read(_reader_request("l1", paper), payload)

    assert structured.adapter is AdapterKind.LLM
    assert structured.card.paper_id == native.card.paper_id
    # Schema-level parity: both yield the same typed card fields.
    assert structured.card.findings == payload.findings
    # LLM output must still be a candidate, never pre-admitted evidence.
    assert structured.card.evidence_ids == []
    assert structured.candidate.evidence_type is EvidenceType.PAPER


# ---------------------------------------------------------------------------
# Writer port
# ---------------------------------------------------------------------------


def _plan(runtime, project_id: str, evidence_id: str | None):
    admission = None
    if evidence_id is None:
        admission = _admit_candidate(runtime, project_id)
        evidence_id = admission.evidence_id
    card = _card(project_id, evidence_id)
    profile = runtime.writing.build_writing_profile(project_id)
    return runtime.writing.plan_evaluation_section(
        project_id,
        "Evaluate the evidence-first section pipeline.",
        [card],
        evidence_ids=[evidence_id],
        profile=profile,
    ), profile


def test_native_writer_builds_plan_only_draft(runtime, project):
    plan, profile = _plan(runtime, "demo", None)
    adapter = NativeWriterAdapter()
    result = adapter.write(_writer_request(runtime, plan, profile.profile_id))
    assert result.adapter is AdapterKind.NATIVE
    assert result.draft.observed_result_summary is None
    assert result.draft.title == "Evaluation"
    assert "## Claims" in result.draft.body
    assert result.draft.claim_evidence_map == plan.claim_evidence_map


def test_three_way_writer_parity_passes_with_valid_bindings(runtime, project):
    plan, profile = _plan(runtime, "demo", None)
    evidence_id = plan.evidence_ids[0]

    native = NativeWriterAdapter().write(_writer_request(runtime, plan, profile.profile_id))
    structured_llm = StructuredWriterAdapter(
        AdapterKind.LLM, adapter_name="writer.llm", adapter_version="0.1"
    ).write(
        _writer_request(runtime, plan, profile.profile_id),
        StructuredDraftPayload(
            title="Evaluation (structured)",
            body="Plan-only structured body.",
            claims=plan.claims,
            claim_evidence_map=plan.claim_evidence_map,
            unresolved_gaps=plan.gaps,
            limitations=plan.gaps,
            observed_result_summary=None,
        ),
    )
    structured_external = StructuredWriterAdapter(
        AdapterKind.EXTERNAL, adapter_name="writer.external", adapter_version="0.1"
    ).write(
        _writer_request(runtime, plan, profile.profile_id),
        StructuredDraftPayload(
            title="Evaluation (external)",
            body="Plan-only external body.",
            claims=plan.claims,
            claim_evidence_map=plan.claim_evidence_map,
            unresolved_gaps=plan.gaps,
            limitations=plan.gaps,
            observed_result_summary=None,
        ),
    )

    report = compare_writer_parity(
        [native, structured_llm, structured_external],
        evidence=runtime.evidence,
    )
    assert report.overall is ParityStatus.PASS
    assert [row.adapter for row in report.adapters] == [
        AdapterKind.NATIVE,
        AdapterKind.LLM,
        AdapterKind.EXTERNAL,
    ]
    assert evidence_id
    for row in report.adapters:
        assert row.schema_valid is True
        assert row.gate_compliant is True
        # Every structured claim is bound to the single valid evidence id.
        assert row.claim_count == len(plan.claims)
        assert row.bound_count == row.claim_count


def test_parity_fails_when_non_native_draft_reports_observed_result(runtime, project):
    plan, profile = _plan(runtime, "demo", None)
    structured = StructuredWriterAdapter(
        AdapterKind.LLM, adapter_name="writer.llm", adapter_version="0.1"
    ).write(
        _writer_request(runtime, plan, profile.profile_id),
        StructuredDraftPayload(
            title="Evaluation",
            body="Observed result included.",
            claims=plan.claims,
            claim_evidence_map=plan.claim_evidence_map,
            unresolved_gaps=plan.gaps,
            limitations=plan.gaps,
            observed_result_summary="+12.3%",
        ),
    )
    report = compare_writer_parity([structured], evidence=runtime.evidence)
    assert report.overall is ParityStatus.FAIL
    assert any("observed result" in issue for issue in report.issues)


# ---------------------------------------------------------------------------
# Claim binding adversarial rules
# ---------------------------------------------------------------------------


def test_bind_claims_flags_unbound_and_missing_evidence(runtime, project):
    plan, profile = _plan(runtime, "demo", None)
    draft = NativeWriterAdapter().write(_writer_request(runtime, plan, profile.profile_id)).draft
    # A claim bound to a non-existent evidence id must not be treated as bound.
    draft = draft.model_copy(
        update={
            "claims": ["A fabricated claim"],
            "claim_evidence_map": {"A fabricated claim": ["ev_missing"]},
            "evidence_ids": ["ev_missing"],
            "unresolved_gaps": [],
        }
    )
    bindings = bind_claims(draft, runtime.evidence)
    assert len(bindings) == 1
    assert bindings[0].status is BindingStatus.PARTIAL
    assert "ev_missing" in bindings[0].missing_or_invalid


def test_gate_compliance_requires_unbound_claim_to_be_unresolved(runtime, project):
    plan, profile = _plan(runtime, "demo", None)
    draft = NativeWriterAdapter().write(_writer_request(runtime, plan, profile.profile_id)).draft
    # No evidence for the claim and not marked unresolved -> fail-closed.
    draft = draft.model_copy(
        update={
            "claims": ["Unsupported claim"],
            "claim_evidence_map": {},
            "unresolved_gaps": [],
        }
    )
    bindings = bind_claims(draft, runtime.evidence)
    compliant, issues = gate_compliance(draft, bindings)
    assert compliant is False
    assert any("not marked unresolved" in issue for issue in issues)


def test_gate_compliance_flags_orphan_claim_evidence_map_key(runtime, project):
    """Owner integration fix (PR #13 review): a claim_evidence_map key absent
    from claims was previously invisible -- never bound, never reported. It
    must fail closed as a binding the draft silently dropped."""
    plan, profile = _plan(runtime, "demo", None)
    draft = NativeWriterAdapter().write(_writer_request(runtime, plan, profile.profile_id)).draft
    evidence_id = plan.evidence_ids[0]
    draft = draft.model_copy(
        update={
            "claim_evidence_map": {
                **plan.claim_evidence_map,
                "Orphan claim absent from claims": [evidence_id],
            },
        }
    )
    bindings = bind_claims(draft, runtime.evidence)
    compliant, issues = gate_compliance(draft, bindings)
    assert compliant is False
    assert any("orphan key" in issue for issue in issues)
    # The orphan key must also fail the three-way parity verdict.
    structured = StructuredWriterAdapter(
        AdapterKind.LLM, adapter_name="writer.llm", adapter_version="0.1"
    ).write(
        _writer_request(runtime, plan, profile.profile_id),
        StructuredDraftPayload(
            title="Evaluation",
            body="Plan-only body with an orphan mapping entry.",
            claims=plan.claims,
            claim_evidence_map={
                **plan.claim_evidence_map,
                "Orphan claim absent from claims": [evidence_id],
            },
            unresolved_gaps=plan.gaps,
            limitations=plan.gaps,
            observed_result_summary=None,
        ),
    )
    report = compare_writer_parity([structured], evidence=runtime.evidence)
    assert report.overall is ParityStatus.FAIL


def test_compose_evaluation_section_yields_typed_draft(runtime, project):
    """Cross-check that the port's typed SectionDraft matches mainline compose."""
    plan, profile = _plan(runtime, "demo", None)
    result = runtime.writing.compose_evaluation_section(
        "demo",
        "Evaluate the evidence-first section pipeline.",
        [_card("demo", plan.evidence_ids[0])],
        evidence_ids=plan.evidence_ids,
        profile=profile,
    )
    assert result.readiness.status is ReadinessStatus.NEEDS_MATERIAL
    assert result.draft is not None
    assert isinstance(result.draft, SectionDraft)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reader_request(request_id: str, paper: PaperRecord):
    from autoresearch.reader_writer_ports import ReaderRequest

    return ReaderRequest(request_id=request_id, project_id="demo", paper=paper)


def _writer_request(runtime, plan, profile_id: str):
    from autoresearch.reader_writer_ports import WriterRequest

    return WriterRequest(
        request_id="w1",
        project_id="demo",
        plan=plan,
        cards=[],
        profile_id=profile_id,
        benchmark_plan_id="bplan-test",
    )
