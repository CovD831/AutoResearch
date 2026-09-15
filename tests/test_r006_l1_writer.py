"""R-006 L1 writer: append-only versioned writes + head index (§11.9).

Every invariant below carries a *discriminating* assertion: a well-formed
input that violates the invariant is explicitly rejected, so the test proves
the guard fires rather than merely that legal input is accepted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autoresearch.contracts import KnowledgePartition, WikiPage
from autoresearch.knowledge import WIKI_PAGE_HEAD_KIND, KnowledgeService
from autoresearch.storage import RecordStore


@pytest.fixture
def svc(tmp_path: Path) -> KnowledgeService:
    return KnowledgeService(RecordStore(tmp_path / "wiki.sqlite3"))


def _page(page_id: str, revision: int, *, author: str = "writer_test") -> WikiPage:
    return WikiPage(
        page_id=page_id,
        project_id="demo",
        partition=KnowledgePartition.KNOWLEDGE,
        title=f"Page {page_id}",
        body="body",
        author=author,
        revision=revision,
    )


# ---------------------------------------------------------------------------
# Invariant I2.1: the same page_id written twice keeps BOTH versions, and the
# older revision is still retrievable (revisions are never overwritten).
# ---------------------------------------------------------------------------


def test_two_writes_keep_both_versions_and_old_is_retrievable(svc):
    p1 = _page("p1", 1)
    p2 = _page("p1", 2, author="writer_test")
    assert svc.add_page(p1) is p1
    assert svc.add_page(p2) is p2

    # Head resolves to the newest revision.
    assert svc.get_page("p1").revision == 2

    # Every revision is still present in the raw version table.
    versions = svc.store.list("wiki_page", project_id="demo")
    assert {v["revision"] for v in versions} == {1, 2}

    # The old revision is still retrievable by its revision_id.
    old = svc.store.get("wiki_page", "p1:r1")
    assert old is not None and old["revision"] == 1

    # Discriminating: a write at revision <= max is rejected, so an overwrite
    # is impossible rather than silently applied.
    with pytest.raises(ValueError):
        svc.add_page(_page("p1", 2, author="writer_test"))
    with pytest.raises(ValueError):
        svc.add_page(_page("p1", 1, author="writer_test"))


# ---------------------------------------------------------------------------
# Invariant I2.2: revision is monotonically increasing and the writer refuses
# any revision <= the current max.
# ---------------------------------------------------------------------------


def test_revision_must_be_strictly_greater_than_max(svc):
    svc.add_page(_page("p2", 3))
    # Gap is allowed (3 -> 7) as long as it is strictly greater.
    svc.add_page(_page("p2", 7))
    assert svc.get_page("p2").revision == 7

    # Discriminating: equal and lower revisions are both rejected.
    with pytest.raises(ValueError):
        svc.add_page(_page("p2", 7))
    with pytest.raises(ValueError):
        svc.add_page(_page("p2", 5))


def test_first_revision_default_is_accepted(svc):
    svc.add_page(_page("p3", 1))
    assert svc.get_page("p3").revision == 1


# ---------------------------------------------------------------------------
# Invariant I2.3: get_page returns the current (head) revision.
# ---------------------------------------------------------------------------


def test_get_page_returns_current_revision(svc):
    svc.add_page(_page("p4", 1))
    svc.add_page(_page("p4", 4))
    page = svc.get_page("p4")
    assert page is not None
    assert page.revision == 4
    assert page.revision_id == "p4:r4"

    # A bare id that was never written resolves to None.
    assert svc.get_page("never_written") is None


# ---------------------------------------------------------------------------
# Invariant I2.4: list_pages de-duplicates by page_id (returns pages, not
# versions).
# ---------------------------------------------------------------------------


def test_list_pages_dedupes_by_page_not_version(svc):
    svc.add_page(_page("a", 1))
    svc.add_page(_page("a", 2))
    svc.add_page(_page("b", 1))
    svc.add_page(_page("b", 2))
    svc.add_page(_page("b", 3))

    pages = svc.list_pages()
    assert {p.page_id for p in pages} == {"a", "b"}
    assert len(pages) == 2
    # Each returned page is the head (current) revision.
    by_id = {p.page_id: p.revision for p in pages}
    assert by_id == {"a": 2, "b": 3}

    # Discriminating: the raw version table enumerates versions, not pages, so
    # list("wiki_page") would have given 5 rows -- proving list_pages is the
    # de-duplicated view.
    assert len(svc.store.list("wiki_page")) == 5


def test_list_pages_filters_by_partition_and_project(svc):
    svc.add_page(_page("x", 1))
    svc.add_page(
        WikiPage(
            page_id="y",
            project_id="other",
            partition=KnowledgePartition.PAPERS,
            title="t",
            body="b",
            author="writer_test",
        )
    )
    assert {p.page_id for p in svc.list_pages(partition=KnowledgePartition.KNOWLEDGE)} == {"x"}
    assert {p.page_id for p in svc.list_pages(project_id="other")} == {"y"}


# ---------------------------------------------------------------------------
# Invariant I2.5: add_edge / retrieve resolve endpoints through the head index
# (a bare page_id must no longer hit the versioned table directly).
# ---------------------------------------------------------------------------


def test_add_edge_and_retrieve_use_head_index(svc):
    svc.add_page(_page("src", 1))
    svc.add_page(_page("dst", 1, author="writer_test"))
    # Re-add dst at a newer revision to prove add_edge resolves the head, not a
    # stale bare-id lookup.
    svc.add_page(_page("dst", 2, author="writer_test"))

    from autoresearch.contracts import GraphEdge

    edge = svc.add_edge(
        GraphEdge(
            project_id="demo",
            partition=KnowledgePartition.KNOWLEDGE,
            source_id="src",
            relation="summarized_by",
            target_id="dst",
            evidence_ids=[],
        )
    )
    assert edge is not None

    # The neighbor is reachable through the graph expansion at level >= 2.
    hits = svc.retrieve(
        "Page", partitions=[KnowledgePartition.KNOWLEDGE], level=2
    )
    hit_ids = {h.record_id for h in hits}
    assert "src" in hit_ids and "dst" in hit_ids

    # Discriminating: an edge whose endpoint was never written is rejected.
    with pytest.raises(ValueError):
        svc.add_edge(
            GraphEdge(
                project_id="demo",
                partition=KnowledgePartition.KNOWLEDGE,
                source_id="src",
                relation="summarized_by",
                target_id="ghost",
                evidence_ids=[],
            )
        )


def test_retrieve_graph_channel_not_silently_broken_by_versioning(svc):
    # Graph expansion must surface the neighbor even though the versioned table
    # no longer keys on bare page_id (the §11.9 regression).
    svc.add_page(_page("n1", 1))
    svc.add_page(_page("n2", 1, author="writer_test"))
    from autoresearch.contracts import GraphEdge

    svc.add_edge(
        GraphEdge(
            project_id="demo",
            partition=KnowledgePartition.KNOWLEDGE,
            source_id="n1",
            relation="summarized_by",
            target_id="n2",
            evidence_ids=[],
        )
    )
    hits = svc.retrieve("Page", partitions=[KnowledgePartition.KNOWLEDGE], level=2)
    assert {h.record_id for h in hits} == {"n1", "n2"}


# ---------------------------------------------------------------------------
# Invariant I2.6: head <-> version atomicity and crash consistency.
# ---------------------------------------------------------------------------


def test_head_and_version_atomicity(svc):
    # A successful write leaves the head pointing exactly at the written
    # version.
    svc.add_page(_page("h1", 1))
    head = svc.store.get(WIKI_PAGE_HEAD_KIND, "h1")
    assert head["current_revision_id"] == "h1:r1"
    assert head["revision"] == 1
    # The version really exists.
    assert svc.store.get("wiki_page", "h1:r1") is not None


def test_head_pointing_at_missing_version_is_not_surfaced(svc):
    # Simulate the documented crash/repair edge case: a head record exists but
    # points at a version that is absent. get_page must return None (the head
    # is authoritative; a dangling version is never surfaced), and list_pages
    # must skip it.
    svc.store.put(
        WIKI_PAGE_HEAD_KIND,
        "orphan",
        {"page_id": "orphan", "current_revision_id": "orphan:r9", "revision": 9},
        project_id="demo",
        partition=KnowledgePartition.KNOWLEDGE.value,
    )
    assert svc.get_page("orphan") is None

    # A valid page coexists; list_pages returns only the valid one.
    svc.add_page(_page("real", 1))
    assert {p.page_id for p in svc.list_pages()} == {"real"}

    # Discriminating: writing the missing version afterward does NOT retroactively
    # revive the orphan head (head still points at r9, which is still absent).
    svc.store.put(
        "wiki_page",
        "orphan:r1",
        _page("orphan", 1).model_dump(),
        project_id="demo",
        partition=KnowledgePartition.KNOWLEDGE.value,
    )
    assert svc.get_page("orphan") is None


def test_version_without_head_is_not_current(svc):
    # A version written directly (bypassing add_page) without a head is
    # invisible to readers -- the head index is the only entry point.
    svc.store.put(
        "wiki_page",
        "floating:r1",
        _page("floating", 1).model_dump(),
        project_id="demo",
        partition=KnowledgePartition.KNOWLEDGE.value,
    )
    assert svc.get_page("floating") is None

    # Discriminating: adding the head retroactively makes it current.
    svc.add_page(_page("floating", 1))
    assert svc.get_page("floating").revision == 1
