"""A9 handoff-by-reference acceptance.

Context: the handoff envelope used to be sized for the handful of papers an
offline fixture produced (20 refs / 100 evidence ids) while ``paper_reader``
attached one ref per reading card and one evidence id per mined claim. A real run
that retrieved 44 papers produced 41 refs and 164 evidence ids and pydantic
rejected the envelope outright -- the run crashed rather than degrading.

The fix is semantic, not numeric: the envelope is a *reference list*, so producers
name ids and never embed content, and the bounds are sized for a real retrieval
run. These tests pin both halves:

* the envelope survives a real-volume run (this is the regression that crashed);
* producers do not embed readable content (widening the numbers alone would let
  the payload grow again);
* the truncation that does remain is observable rather than silent.
"""

from __future__ import annotations

import pytest

from autoresearch.agents.paper_search import HANDOFF_REF_LIMIT
from autoresearch.contracts import (
    AgentId,
    ArtifactRef,
    HandoffEnvelope,
)

BASE = {
    "project_id": "demo",
    "run_id": "run-1",
    "from_agent": AgentId.PAPER_READER,
    "to_agent": AgentId.REVIEWER,
    "objective": "audit provenance",
    "expected_output": "review report",
}


# --------------------------------------------------------------------------- #
# 1. The envelope survives a real-volume run
# --------------------------------------------------------------------------- #


def test_envelope_accepts_a_real_retrieval_volume():
    """44 papers -> 41 reading cards + 164 evidence ids must construct.

    These are the measured numbers from the run that crashed the pipeline.
    """

    envelope = HandoffEnvelope(
        **BASE,
        artifact_refs=[
            ArtifactRef(artifact_id=f"card-{index}", kind="reading_card") for index in range(41)
        ],
        evidence_ids=[f"ev-{index}" for index in range(164)],
    )

    assert len(envelope.artifact_refs) == 41
    assert len(envelope.evidence_ids) == 164


def test_bounds_are_sized_above_a_real_retrieval_run():
    """The measured failing numbers must sit inside the bound, with headroom.

    A test cannot resurrect the old bound (it is gone), so instead this pins the
    requirement the new bound has to satisfy: the 41 refs / 164 evidence ids that
    crashed the run must clear it, and the bound must not be unbounded either
    (asserted separately below).
    """

    envelope = HandoffEnvelope(**BASE)
    fields = HandoffEnvelope.model_fields

    refs_bound = fields["artifact_refs"].metadata[0].max_length
    evidence_bound = fields["evidence_ids"].metadata[0].max_length

    assert refs_bound >= 41, "the run that crashed produced 41 refs"
    assert evidence_bound >= 164, "the run that crashed produced 164 evidence ids"
    assert envelope.artifact_refs == []
    assert envelope.evidence_ids == []


def test_bounds_stay_finite_so_a_runaway_producer_is_still_caught():
    """Widening must not mean unbounded: an envelope is not a bulk channel."""

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        HandoffEnvelope(
            **BASE,
            artifact_refs=[
                ArtifactRef(artifact_id=f"c{i}", kind="reading_card")
                for i in range(501)
            ],
        )


# --------------------------------------------------------------------------- #
# 2. Producers reference, they do not embed
# --------------------------------------------------------------------------- #


def test_reading_card_refs_are_resolvable_and_carry_no_content(runtime, project):
    """The reviewer resolves cards from the store; findings must not travel inline.

    Asserting on the persisted card + the ref shape keeps the invariant ("a ref is
    an address, not a payload") without re-running the whole reader pipeline,
    whose own side effects are covered elsewhere.
    """

    from autoresearch.contracts import ReadingCard
    from autoresearch.storage import RecordStore

    store: RecordStore = runtime.store
    card = ReadingCard(
        project_id="demo",
        paper_id="paper-1",
        research_question="q",
        method="m",
        data_or_setting="d",
        findings=["finding text that must not be embedded in the envelope"],
        limitations=["l"],
        locators=["abstract"],
        evidence_ids=["ev-1"],
        confidence=0.5,
    )
    store.put("reading_card", card.card_id, card, project_id="demo")

    ref = ArtifactRef(artifact_id=card.card_id, kind="reading_card")

    assert ref.summary == "", "no readable content may be embedded in a reference"
    stored = store.get("reading_card", ref.artifact_id)
    assert stored is not None, "the referenced card must be resolvable from the store"
    assert stored["findings"] == ["finding text that must not be embedded in the envelope"]


def test_reader_agent_handoff_drops_inline_summaries(monkeypatch, tmp_path):
    """End-to-end: the reader's envelope carries ids only, even with many cards."""

    from autoresearch.agents.paper_reader import PaperReaderAgent

    captured: list[HandoffEnvelope] = []

    class _CapturingHandoffs:
        def accept(self, *_args, **_kwargs):
            return None

        def issue(self, envelope):
            captured.append(envelope)

            class _Issued:
                handoff_id = envelope.handoff_id

                def model_dump(self, **_kwargs):
                    return envelope.model_dump(mode="json")

            return _Issued()

    agent = PaperReaderAgent(
        store=_StubStore(),
        reader=_StubReader(cards=41, innovations=8),
        handoffs=_CapturingHandoffs(),
        state_machine=_PermissiveStateMachine(),
    )

    state = {
        "project_id": "demo",
        "run_id": "run-1",
        "idea": "test idea",
        "paper_ids": [f"paper-{index}" for index in range(41)],
        "evidence_ids": [],
        "diagnostics": [],
        "lifecycle_state": "literature_searched",
        "seed_papers": [],
        "search_queries": [],
        "handoff": None,
        "last_agent": None,
    }

    agent.run(state)

    assert captured, "the reader must issue a handoff"
    envelope = captured[0]
    assert len(envelope.artifact_refs) == 49, "41 cards + 8 candidates, all by reference"
    assert all(ref.summary == "" for ref in envelope.artifact_refs)


# --------------------------------------------------------------------------- #
# 3. Remaining truncation is observable, never silent
# --------------------------------------------------------------------------- #


def test_paper_search_reports_when_it_truncates_the_reference_list():
    """A silent truncation reads downstream as 'you got everything' -- fail-open."""

    from autoresearch.agents.paper_search import PaperSearchAgent

    agent = PaperSearchAgent(
        search=_StubSearch(count=HANDOFF_REF_LIMIT + 7),
        evidence=_StubEvidence(),
        handoffs=_CapturingHandoffs(),
        state_machine=_PermissiveStateMachine(),
    )

    result = agent.run(
        {
            "project_id": "demo",
            "run_id": "run-1",
            "idea": "test",
            "evidence_ids": [],
            "diagnostics": [],
            "lifecycle_state": "intake",
            "seed_papers": [],
            "search_queries": ["q"],
            "handoff": None,
            "last_agent": None,
        }
    )

    assert any("first 50 of 57" in item for item in result["diagnostics"]), (
        "the truncation must be visible in diagnostics"
    )
    assert "refs_attached=50" in _captured_envelope(agent).bounded_context


def test_paper_search_does_not_warn_when_nothing_is_truncated():
    from autoresearch.agents.paper_search import PaperSearchAgent

    agent = PaperSearchAgent(
        search=_StubSearch(count=HANDOFF_REF_LIMIT),
        evidence=_StubEvidence(),
        handoffs=_CapturingHandoffs(),
        state_machine=_PermissiveStateMachine(),
    )

    result = agent.run(
        {
            "project_id": "demo",
            "run_id": "run-1",
            "idea": "test",
            "evidence_ids": [],
            "diagnostics": [],
            "lifecycle_state": "intake",
            "seed_papers": [],
            "search_queries": ["q"],
            "handoff": None,
            "last_agent": None,
        }
    )

    assert result["diagnostics"] == []


# --------------------------------------------------------------------------- #
# stubs
# --------------------------------------------------------------------------- #


class _StubStore:
    def get(self, kind, record_id):
        from autoresearch.contracts import PaperRecord

        if kind == "paper":
            return PaperRecord(project_id="demo", title=f"Paper {record_id}", source="stub")
        return None


class _StubReader:
    def __init__(self, *, cards: int, innovations: int):
        self._cards = cards
        self._innovations = innovations

    def read(self, paper):
        from autoresearch.contracts import EvidenceGrade, EvidenceItem, EvidenceType, ReadingCard

        card = ReadingCard(
            project_id="demo",
            paper_id=paper.paper_id,
            research_question="q",
            method="m",
            data_or_setting="d",
            findings=["finding text that must not be embedded"],
            limitations=["l"],
            locators=["abstract"],
            evidence_ids=["ev-1"],
            confidence=0.5,
        )
        evidence = EvidenceItem(
            project_id="demo",
            evidence_type=EvidenceType.PAPER,
            grade=EvidenceGrade.E1,
            title="t",
            claim="c",
            source_id=paper.paper_id,
            locator="abstract",
            independent_source="doi:10.1/x",
        )
        return card, evidence

    def mine_innovations(self, project_id, idea, cards):
        from autoresearch.contracts import InnovationCandidate

        return [
            InnovationCandidate(
                project_id=project_id,
                statement=f"candidate {index}",
                rationale="r",
                differentiators=[],
                evidence_ids=["ev-1"],
                falsification_test="f",
            )
            for index in range(self._innovations)
        ]


class _StubSearch:
    def __init__(self, *, count: int):
        self._count = count

    def search(self, project_id, queries, *, seed_papers=None, per_connector_limit=5):
        from autoresearch.contracts import PaperRecord
        from autoresearch.search_service import SearchOutcome

        return SearchOutcome(
            papers=[
                PaperRecord(project_id=project_id, title=f"Paper {i}", source="stub")
                for i in range(self._count)
            ]
        )


class _StubEvidence:
    def list(self, _project_id, *, valid_only=True):
        return []


class _CapturingHandoffs:
    """Module-level variant so a test can inspect what the agent issued."""

    issued: list = []

    def accept(self, *_args, **_kwargs):
        return None

    def issue(self, envelope):
        _CapturingHandoffs.issued.append(envelope)

        class _Issued:
            handoff_id = envelope.handoff_id

            def model_dump(self, **_kwargs):
                return envelope.model_dump(mode="json")

        return _Issued()


class _PermissiveStateMachine:
    def transition(self, _current, target):
        return target


def _captured_envelope(_agent):
    return _CapturingHandoffs.issued[-1]
