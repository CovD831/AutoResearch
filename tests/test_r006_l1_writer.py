"""R-006 L1 writer: append-only versioned writes + head index (§11.9).

Every invariant below carries a *discriminating* assertion: a well-formed
input that violates the invariant is explicitly rejected, so the test proves
the guard fires rather than merely that legal input is accepted.
"""

from __future__ import annotations

import multiprocessing
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import autoresearch.storage as storage_module
from autoresearch.contracts import KnowledgePartition, WikiPage
from autoresearch.knowledge import WIKI_PAGE_HEAD_KIND, KnowledgeService
from autoresearch.storage import RecordStore


@pytest.fixture
def svc(tmp_path: Path) -> KnowledgeService:
    return KnowledgeService(RecordStore(tmp_path / "wiki.sqlite3"))


def _page(
    page_id: str,
    revision: int,
    *,
    author: str = "writer_test",
    body: str = "body",
) -> WikiPage:
    return WikiPage(
        page_id=page_id,
        project_id="demo",
        partition=KnowledgePartition.KNOWLEDGE,
        title=f"Page {page_id}",
        body=body,
        author=author,
        revision=revision,
    )


def _page_events(store: RecordStore) -> list[dict]:
    return [
        event
        for event in store.events("demo")
        if event["event_type"] == "knowledge.page_added"
    ]


def _page_event_revisions(store: RecordStore) -> list[int]:
    return [event["payload"]["revision"] for event in _page_events(store)]


def _process_write_revision(database: str, body: str, barrier, result_queue) -> None:
    service = KnowledgeService(RecordStore(database))
    barrier.wait(timeout=20)
    try:
        service.add_page(_page("process-shared", 2, body=body))
    except Exception as exc:
        result_queue.put(
            {
                "status": "rejected",
                "writer": body,
                "exception": type(exc).__name__,
                "message": str(exc),
            }
        )
        return
    result_queue.put({"status": "succeeded", "writer": body})


def _process_hold_uncommitted_revision(database: str, inserted_event) -> None:
    store = RecordStore(database)
    pending_page = _page("process-crash", 2, body="uncommitted-r2")
    with store.transaction() as connection:
        head = store._read_record(connection, WIKI_PAGE_HEAD_KIND, pending_page.page_id)
        if head is None or head["revision"] != 1:
            raise RuntimeError("unexpected crash-test head")
        store._insert_record(
            connection,
            "wiki_page",
            pending_page.revision_id,
            pending_page,
            project_id=pending_page.project_id,
            partition=pending_page.partition.value,
        )
        inserted_event.set()
        time.sleep(60)


class _SynchronizedPragmaConnection:
    def __init__(self, connection, barrier, remaining, remaining_lock):
        object.__setattr__(self, "_connection", connection)
        object.__setattr__(self, "_barrier", barrier)
        object.__setattr__(self, "_remaining", remaining)
        object.__setattr__(self, "_remaining_lock", remaining_lock)

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __setattr__(self, name, value):
        setattr(self._connection, name, value)

    def execute(self, sql, *args, **kwargs):
        synchronize = False
        if sql.strip().upper() == "PRAGMA JOURNAL_MODE=WAL":
            with self._remaining_lock:
                if self._remaining["count"] > 0:
                    self._remaining["count"] -= 1
                    synchronize = True
        if synchronize:
            self._barrier.wait(timeout=10)
        return self._connection.execute(sql, *args, **kwargs)


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
# Invariant I2.2: revision is contiguous -- every write is exactly max + 1.
# ---------------------------------------------------------------------------


def test_revision_must_equal_current_max_plus_one(svc):
    svc.add_page(_page("p2", 1))
    svc.add_page(_page("p2", 2))

    for invalid_revision in (1, 2, 4):
        with pytest.raises(ValueError, match="expected revision 3"):
            svc.add_page(_page("p2", invalid_revision))

    assert svc.get_page("p2").revision == 2
    assert svc.store.get("wiki_page", "p2:r4") is None
    assert {row["revision"] for row in svc.store.list("wiki_page")} == {1, 2}


def test_first_revision_default_is_accepted(svc):
    with pytest.raises(ValueError, match="expected revision 1"):
        svc.add_page(_page("p3", 2))

    assert svc.get_page("p3") is None
    svc.add_page(_page("p3", 1))
    assert svc.get_page("p3").revision == 1


# ---------------------------------------------------------------------------
# Invariant I2.3: get_page returns the current (head) revision.
# ---------------------------------------------------------------------------


def test_get_page_returns_current_revision(svc):
    svc.add_page(_page("p4", 1))
    svc.add_page(_page("p4", 2))
    page = svc.get_page("p4")
    assert page is not None
    assert page.revision == 2
    assert page.revision_id == "p4:r2"

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

    # The append-only writer must not overwrite or adopt a version that was
    # written outside the version+head transaction.
    with pytest.raises(ValueError, match="already exists"):
        svc.add_page(_page("floating", 1, body="replacement"))
    assert svc.get_page("floating") is None
    assert svc.store.get("wiki_page", "floating:r1")["body"] == "body"


class _BarrierHeadReadStore(RecordStore):
    """Force two old-style writers to observe the same head snapshot."""

    def __init__(self, path: Path, barrier: threading.Barrier):
        self._head_barrier = barrier
        super().__init__(path)

    def get(self, kind: str, record_id: str):
        value = super().get(kind, record_id)
        if kind == WIKI_PAGE_HEAD_KIND and record_id == "shared" and value is not None:
            self._head_barrier.wait(timeout=10)
        return value


def test_concurrent_writers_cannot_both_commit_the_same_revision(tmp_path: Path):
    database = tmp_path / "concurrent.sqlite3"
    KnowledgeService(RecordStore(database)).add_page(_page("shared", 1, body="r1"))
    barrier = threading.Barrier(2)
    services = [
        KnowledgeService(_BarrierHeadReadStore(database, barrier)),
        KnowledgeService(_BarrierHeadReadStore(database, barrier)),
    ]

    def write(index: int) -> tuple[str, str]:
        try:
            services[index].add_page(_page("shared", 2, body=f"writer-{index}"))
        except ValueError as exc:
            return "rejected", str(exc)
        return "succeeded", ""

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, (0, 1)))

    statuses = [status for status, _ in outcomes]
    store = RecordStore(database)
    assert statuses.count("succeeded") == 1
    assert statuses.count("rejected") == 1
    rejected_message = next(
        message for status, message in outcomes if status == "rejected"
    )
    assert "expected revision 3" in rejected_message
    assert {row["revision"] for row in store.list("wiki_page")} == {1, 2}
    assert store.get(WIKI_PAGE_HEAD_KIND, "shared")["revision"] == 2
    assert store.get("wiki_page", "shared:r2")["body"] in {"writer-0", "writer-1"}
    page_events = [
        event for event in store.events("demo") if event["event_type"] == "knowledge.page_added"
    ]
    assert [event["payload"]["revision"] for event in page_events] == [1, 2]


class _ObservedHeadReadStore(RecordStore):
    def __init__(
        self,
        path: Path,
        *,
        writer_name: str,
        observations: dict[str, int],
        head_read: threading.Event,
        release_after_read: threading.Event | None = None,
    ):
        self._writer_name = writer_name
        self._observations = observations
        self._head_read = head_read
        self._release_after_read = release_after_read
        super().__init__(path)

    def _read_record(self, connection, kind, record_id):
        value = super()._read_record(connection, kind, record_id)
        if kind == WIKI_PAGE_HEAD_KIND and record_id == "observed":
            self._observations[self._writer_name] = value["revision"]
            self._head_read.set()
            if self._release_after_read is not None:
                assert self._release_after_read.wait(timeout=10)
        return value


def test_write_lock_is_held_from_head_read_through_commit(tmp_path: Path):
    database = tmp_path / "lock-scope.sqlite3"
    KnowledgeService(RecordStore(database)).add_page(_page("observed", 1))
    observations: dict[str, int] = {}
    a_head_read = threading.Event()
    release_a = threading.Event()
    b_started = threading.Event()
    b_head_read = threading.Event()
    service_a = KnowledgeService(
        _ObservedHeadReadStore(
            database,
            writer_name="A",
            observations=observations,
            head_read=a_head_read,
            release_after_read=release_a,
        )
    )
    service_b = KnowledgeService(
        _ObservedHeadReadStore(
            database,
            writer_name="B",
            observations=observations,
            head_read=b_head_read,
        )
    )

    def write_a() -> str:
        service_a.add_page(_page("observed", 2, body="writer-A"))
        return "succeeded"

    def write_b() -> tuple[str, str]:
        b_started.set()
        try:
            service_b.add_page(_page("observed", 2, body="writer-B"))
        except ValueError as exc:
            return "rejected", str(exc)
        return "succeeded", ""

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(write_a)
        assert a_head_read.wait(timeout=10)
        future_b = pool.submit(write_b)
        assert b_started.wait(timeout=10)
        assert not b_head_read.wait(timeout=0.25)
        release_a.set()
        assert future_a.result(timeout=10) == "succeeded"
        b_status, b_message = future_b.result(timeout=10)

    assert observations == {"A": 1, "B": 2}
    assert b_status == "rejected"
    assert "expected revision 3" in b_message


def test_two_processes_cannot_both_commit_the_same_revision(tmp_path: Path):
    database = tmp_path / "multiprocess.sqlite3"
    KnowledgeService(RecordStore(database)).add_page(
        _page("process-shared", 1, body="r1")
    )
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(3)
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_process_write_revision,
            args=(str(database), f"process-{index}", barrier, result_queue),
        )
        for index in range(2)
    ]

    for process in processes:
        process.start()
    barrier.wait(timeout=20)
    for process in processes:
        process.join(timeout=20)
        assert not process.is_alive()
        assert process.exitcode == 0

    outcomes = [result_queue.get(timeout=5) for _ in processes]
    result_queue.close()
    result_queue.join_thread()
    statuses = [outcome["status"] for outcome in outcomes]
    succeeded = next(outcome for outcome in outcomes if outcome["status"] == "succeeded")
    rejected = next(outcome for outcome in outcomes if outcome["status"] == "rejected")
    store = RecordStore(database)

    assert statuses.count("succeeded") == 1
    assert statuses.count("rejected") == 1
    assert rejected["exception"] == "ValueError"
    assert "expected revision 3" in rejected["message"]
    assert {row["revision"] for row in store.list("wiki_page")} == {1, 2}
    assert store.get(WIKI_PAGE_HEAD_KIND, "process-shared")["revision"] == 2
    assert store.get("wiki_page", "process-shared:r2")["body"] == succeeded["writer"]
    assert _page_event_revisions(store) == [1, 2]


def test_eight_writers_contending_for_one_revision_have_one_winner(tmp_path: Path):
    database = tmp_path / "eight-contenders.sqlite3"
    KnowledgeService(RecordStore(database)).add_page(_page("contended", 1, body="r1"))
    barrier = threading.Barrier(8)

    def write(index: int) -> tuple[str, int, str]:
        service = KnowledgeService(RecordStore(database))
        barrier.wait(timeout=20)
        try:
            service.add_page(_page("contended", 2, body=f"writer-{index}"))
        except ValueError as exc:
            return "rejected", index, str(exc)
        return "succeeded", index, ""

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(write, range(8)))

    statuses = [status for status, _, _ in outcomes]
    winner = next(index for status, index, _ in outcomes if status == "succeeded")
    store = RecordStore(database)
    assert statuses.count("succeeded") == 1
    assert statuses.count("rejected") == 7
    assert all(
        "expected revision 3" in message
        for status, _, message in outcomes
        if status == "rejected"
    )
    assert {row["revision"] for row in store.list("wiki_page")} == {1, 2}
    assert store.get(WIKI_PAGE_HEAD_KIND, "contended")["revision"] == 2
    assert store.get("wiki_page", "contended:r2")["body"] == f"writer-{winner}"
    assert _page_event_revisions(store) == [1, 2]


def test_concurrent_writers_for_different_pages_all_succeed(tmp_path: Path):
    database = tmp_path / "different-pages.sqlite3"
    barrier = threading.Barrier(8)

    def write(index: int) -> str:
        service = KnowledgeService(RecordStore(database))
        barrier.wait(timeout=20)
        service.add_page(_page(f"page-{index}", 1, body=f"writer-{index}"))
        return "succeeded"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(write, range(8)))

    store = RecordStore(database)
    assert outcomes == ["succeeded"] * 8
    assert {row["page_id"] for row in store.list("wiki_page")} == {
        f"page-{index}" for index in range(8)
    }
    assert {
        store.get(WIKI_PAGE_HEAD_KIND, f"page-{index}")["revision"]
        for index in range(8)
    } == {1}
    events = _page_events(store)
    assert len(events) == 8
    assert {event["payload"]["page_id"] for event in events} == {
        f"page-{index}" for index in range(8)
    }
    assert {event["payload"]["revision"] for event in events} == {1}


def test_process_termination_rolls_back_uncommitted_version(tmp_path: Path):
    database = tmp_path / "terminated-process.sqlite3"
    KnowledgeService(RecordStore(database)).add_page(_page("process-crash", 1, body="r1"))
    context = multiprocessing.get_context("spawn")
    inserted_event = context.Event()
    process = context.Process(
        target=_process_hold_uncommitted_revision,
        args=(str(database), inserted_event),
    )

    process.start()
    assert inserted_event.wait(timeout=20)
    process.terminate()
    process.join(timeout=20)
    assert not process.is_alive()
    assert process.exitcode != 0

    store = RecordStore(database)
    assert store.get("wiki_page", "process-crash:r2") is None
    assert store.get(WIKI_PAGE_HEAD_KIND, "process-crash")["revision"] == 1
    assert {row["revision"] for row in store.list("wiki_page")} == {1}
    assert _page_event_revisions(store) == [1]

    KnowledgeService(store).add_page(_page("process-crash", 2, body="retry-r2"))
    assert store.get("wiki_page", "process-crash:r2")["body"] == "retry-r2"
    assert store.get(WIKI_PAGE_HEAD_KIND, "process-crash")["revision"] == 2
    assert {row["revision"] for row in store.list("wiki_page")} == {1, 2}
    assert _page_event_revisions(store) == [1, 2]


def test_concurrent_cold_start_retries_wal_transition(
    tmp_path: Path,
    monkeypatch,
):
    database = tmp_path / "cold-start.sqlite3"
    barrier = threading.Barrier(2)
    remaining = {"count": 2}
    remaining_lock = threading.Lock()
    real_connect = storage_module.sqlite3.connect

    def synchronized_connect(*args, **kwargs):
        return _SynchronizedPragmaConnection(
            real_connect(*args, **kwargs),
            barrier,
            remaining,
            remaining_lock,
        )

    monkeypatch.setattr(storage_module.sqlite3, "connect", synchronized_connect)

    with ThreadPoolExecutor(max_workers=2) as pool:
        stores = list(pool.map(lambda _: RecordStore(database), range(2)))

    assert len(stores) == 2
    # ``with sqlite3.Connection`` commits but never closes, so the connection
    # would leak and surface as a ResourceWarning at GC time -- which the
    # project's ``pytest -W error`` gate turns into an error. Close it here.
    connection = real_connect(database)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        connection.close()


class _FailingHeadWriteStore(RecordStore):
    fail_head_write = False

    def _write_record(self, connection, kind, record_id, value, **kwargs):
        if self.fail_head_write and kind == WIKI_PAGE_HEAD_KIND:
            raise RuntimeError("injected head write failure")
        return super()._write_record(connection, kind, record_id, value, **kwargs)


def test_version_insert_rolls_back_when_head_update_fails(tmp_path: Path):
    database = tmp_path / "rollback.sqlite3"
    store = _FailingHeadWriteStore(database)
    service = KnowledgeService(store)
    service.add_page(_page("rollback", 1))
    store.fail_head_write = True

    with pytest.raises(RuntimeError, match="injected head write failure"):
        service.add_page(_page("rollback", 2))

    verifier = RecordStore(database)
    assert verifier.get("wiki_page", "rollback:r2") is None
    assert verifier.get(WIKI_PAGE_HEAD_KIND, "rollback")["revision"] == 1
    assert {row["revision"] for row in verifier.list("wiki_page")} == {1}
    page_events = [
        event
        for event in verifier.events("demo")
        if event["event_type"] == "knowledge.page_added"
    ]
    assert [event["payload"]["revision"] for event in page_events] == [1]
