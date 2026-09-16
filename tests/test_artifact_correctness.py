"""O16 Artifact Correctness: discriminating tests for the three defects.

Each test targets a defect that existed before this package and asserts the
post-fix observable behaviour. These are criterion (assertion) failures on
pre-fix code, not symbol errors: they read the relevant values (findings,
sections, disk files) rather than a new field.
"""

from __future__ import annotations

from pathlib import Path

from autoresearch.contracts import PaperRecord, ReadingCard
from autoresearch.reader_service import PaperReaderService


def _paper(project_id: str, *, title: str, abstract: str, doi: str | None = None) -> PaperRecord:
    return PaperRecord(
        project_id=project_id,
        title=title,
        abstract=abstract,
        authors=["A. Author"],
        year=2026,
        doi=doi,
        source="offline",
        source_record_id=doi or title,
    )


def _card(
    project_id: str,
    *,
    paper_id: str,
    findings: list[str],
    evidence_id: str = "ev-1",
) -> ReadingCard:
    return ReadingCard(
        project_id=project_id,
        paper_id=paper_id,
        research_question="q",
        method="m",
        data_or_setting="d",
        findings=findings,
        limitations=["limitation"],
        locators=["abstract"],
        evidence_ids=[evidence_id],
        confidence=0.5,
    )


# ---------------------------------------------------------------------------
# 缺陷 A：抽取失败不得伪装成发现
# ---------------------------------------------------------------------------


def test_extraction_failure_yields_empty_findings_not_sentinel(runtime, project):
    """A short abstract (below the sentence threshold) must not produce the
    sentinel "No extractable finding..." as a finding."""
    from autoresearch.contracts import KnowledgePartition, WikiPage

    reader: PaperReaderService = runtime.reader
    paper = _paper("demo", title="Terse record", abstract="Short.")
    # reader.read() writes a graph edge summarised_by -> requires the paper node
    # to already exist as a wiki page (the real search pipeline persists it first).
    runtime.store.put(
        "paper", paper.paper_id, paper, project_id="demo", partition="papers"
    )
    runtime.knowledge.add_page(
        WikiPage(
            page_id=paper.paper_id,
            project_id="demo",
            partition=KnowledgePartition.PAPERS,
            title=paper.title,
            body=paper.abstract,
            level=1,
            author="test",
        )
    )
    card, _evidence = reader.read(paper)
    assert card.findings == []
    assert "No extractable finding" not in card.findings


def test_extraction_failure_is_surfaced_as_gap_not_related_work(runtime, project):
    """A card with no findings must not appear in Related Work and must add a gap."""
    card = _card("demo", paper_id="p1", findings=[])
    result = runtime.writing.draft(
        "demo",
        "idea",
        [_paper("demo", title="Terse record", abstract="Short.")],
        [card],
        [],
        [],
    )
    body = result.sections["Related Work"]
    assert "No extractable finding" not in body
    assert not any("p1" in line for line in body.splitlines())
    assert any("未能抽取出可用的发现" in gap for gap in result.unresolved_gaps)


# ---------------------------------------------------------------------------
# 缺陷 B：三处去重口径一致
# ---------------------------------------------------------------------------


def test_related_work_deduplicates_identical_findings(runtime, project):
    card_a = _card("demo", paper_id="p1", findings=["Identical finding text."])
    card_b = _card("demo", paper_id="p2", findings=["Identical finding text."])
    result = runtime.writing.draft(
        "demo",
        "idea",
        [
            _paper("demo", title="A", abstract="x."),
            _paper("demo", title="B", abstract="x."),
        ],
        [card_a, card_b],
        [],
        [],
    )
    body = result.sections["Related Work"]
    assert body.count("Identical finding text.") == 1


def test_references_deduplicates_same_title_different_doi(runtime, project):
    papers = [
        _paper("demo", title="CRP-RAG Framework", abstract="x.", doi="10.1/preprint"),
        _paper("demo", title="CRP-RAG Framework", abstract="y.", doi="10.2/published"),
    ]
    result = runtime.writing.draft("demo", "idea", papers, [], [], [])
    refs = result.sections["References"]
    assert refs.count("CRP-RAG Framework") == 1


# ---------------------------------------------------------------------------
# 缺陷 C：交付文件与注册表不再分叉
# ---------------------------------------------------------------------------


def test_draft_writes_both_archive_and_current_pointer(runtime, project):
    card = _card("demo", paper_id="p1", findings=["A finding."])
    runtime.writing.draft(
        "demo", "idea", [_paper("demo", title="T", abstract="x.")], [card], [], []
    )
    writing_dir = Path(runtime.settings.projects_dir) / "demo" / "05_writing"
    v1 = writing_dir / "MANUSCRIPT_DRAFT_v1.md"
    cur = writing_dir / "MANUSCRIPT_DRAFT.md"
    assert v1.exists()
    assert cur.exists()
    assert v1.read_text(encoding="utf-8") == cur.read_text(encoding="utf-8")


def test_revise_overwrites_current_pointer_and_stops_revision_files(runtime, project):
    card = _card("demo", paper_id="p1", findings=["A finding."])
    manuscript = runtime.writing.draft(
        "demo", "idea", [_paper("demo", title="T", abstract="x.")], [card], [], []
    )
    first_id = manuscript.manuscript_id
    runtime.writing.revise(first_id, "improve", mode="revise")
    writing_dir = Path(runtime.settings.projects_dir) / "demo" / "05_writing"
    cur = writing_dir / "MANUSCRIPT_DRAFT.md"
    v1 = writing_dir / "MANUSCRIPT_DRAFT_v1.md"
    # No new MANUSCRIPT_REVISION_* file is produced.
    revision_files = list(writing_dir.glob("MANUSCRIPT_REVISION_*.md"))
    assert revision_files == []
    # Current pointer carries the latest revision, archive is untouched.
    assert cur.exists()
    assert v1.exists()
    assert v1.read_text(encoding="utf-8") != cur.read_text(encoding="utf-8")
    # Current pointer reflects the newest manuscript (has Revision Notes section).
    assert "Revision Notes" in cur.read_text(encoding="utf-8")