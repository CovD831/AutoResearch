"""M11-MVP-02 candidate recall pipeline: L0 boundary -> L1 BM25 -> L2 vector / graph.

Fixture: ``fixtures/knowledge_retrieval/recall_pipeline.json``. Its ``expected`` block
is hand-authored from the boundary rules (``TASK-SPECS.md:429-432``), never regenerated
from the implementation.

The last test in the file reproduces the pre-MVP-02 ranking
(``f197b7a:src/autoresearch/knowledge.py:199-268``) and asserts the fixture discriminates
it, so the assertions above cannot pass vacuously.

Three behaviours are exercised through the real entry point rather than through the
service directly, because they are wiring properties and would otherwise be untestable
(ledger ``D-M11-02-01`` / ``D-M11-02-09``):

- a query without a project scope is refused, never widened to every project;
- the same shared store answers per project, and a cross-project graph edge cannot
  smuggle a page across;
- the vector provider only runs when it was handed to ``knowledge_scope`` explicitly.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from autoresearch.application import AutoResearchApplication
from autoresearch.contracts import (
    GraphEdge,
    KnowledgePartition,
    RetrievalChannel,
    ReviewStatus,
    WikiPage,
)
from autoresearch.knowledge import KnowledgeScopeRequiredError, KnowledgeService
from autoresearch.knowledge_retrieval import (
    GRAPH_NEIGHBOUR_DECAY,
    GRAPH_NEIGHBOUR_FLOOR,
    HashingEmbedder,
    apply_l0_boundary,
    bm25_scores,
    cosine_similarity,
    expand_graph,
    in_scope,
    is_available,
    page_text,
    vector_arm,
)
from autoresearch.recall_audit import RECALL_AUDIT_KIND, RecallAuditRecord
from autoresearch.storage import RecordStore

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "knowledge_retrieval" / "recall_pipeline.json"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = KnowledgePartition.KNOWLEDGE


class FixtureEmbeddingProvider:
    """Hand-authored vectors from the fixture, resolved by page title.

    Titles are unique in the fixture and none is a substring of another, so the
    lookup is unambiguous. An unknown text raises instead of returning a zero
    vector: a silent miss would make every vector assertion below vacuous.
    """

    def __init__(self, payload: dict) -> None:
        embeddings = payload["embeddings"]
        self.name = embeddings["provider"]
        self.dimensions = embeddings["dimensions"]
        self._query_vectors = {
            text: tuple(vector) for text, vector in embeddings["query_vectors"].items()
        }
        self._titles = {page["page_id"]: page["title"] for page in payload["pages"]}
        self._page_vectors = {
            page_id: tuple(vector) for page_id, vector in embeddings["vectors"].items()
        }

    def embed(self, text: str) -> tuple[float, ...]:
        if text in self._query_vectors:
            return self._query_vectors[text]
        for page_id, title in self._titles.items():
            if title in text:
                return self._page_vectors[page_id]
        raise AssertionError(f"fixture has no vector for text {text!r}")


class BrokenEmbedder:
    """A provider that is simply broken, from its very first call.

    Models a missing model file: the capability is unavailable, not wrong. The
    query must still be answered by the arms that do work.
    """

    name = "broken/v1"
    dimensions = 3

    def __init__(self, error: type[Exception] = RuntimeError) -> None:
        self._error = error

    def embed(self, text: str) -> tuple[float, ...]:
        raise self._error(f"cannot embed {text!r}: model file is missing")


class DimensionDriftEmbedder:
    """Query and page vectors live in different spaces.

    ``cosine_similarity`` raises ``ValueError`` on the first page, so a provider
    that returns well-formed but inconsistent vectors is a capability failure too.
    """

    name = "drift/v1"
    dimensions = 3

    def embed(self, text: str) -> tuple[float, ...]:
        return (1.0, 0.0, 0.0) if text in self._query_texts else (1.0, 0.0)

    _query_texts = frozenset({"grid cells"})


class MidPassEmbedder:
    """Answers the query and the first page, then dies.

    Half a vector pass is enough to be dangerous: the answered page gets a perfect
    query match, so a pipeline that merged whatever it had would rewrite that
    page's ``score_breakdown`` and channel. ``answered_calls`` lets the test prove
    the failure really happened partway, i.e. that there was a partial result to
    discard.
    """

    name = "mid-pass/v1"
    dimensions = 3

    def __init__(self, *, answers: int = 2) -> None:
        self.answers = answers
        self.calls = 0

    def embed(self, text: str) -> tuple[float, ...]:
        self.calls += 1
        if self.calls > self.answers:
            raise RuntimeError("vector provider died mid-pass")
        return (1.0, 0.0, 0.0)


class ConstantEmbedder:
    """One vector for every text, so the arm matches any in-scope page.

    Makes the vector arm observable without depending on tokens: a page with no
    lexical overlap is still found, and only through ``RetrievalChannel.VECTOR``.
    """

    name = "constant/v1"
    dimensions = 2

    def embed(self, text: str) -> tuple[float, ...]:
        return (1.0, 0.0)


def _load_fixture() -> dict:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["schema"] == "m11-knowledge-retrieval/v1"
    return payload


def _build_service(
    tmp_path: Path,
    payload: dict,
    *,
    with_embedder: bool,
    embedder=None,
    store_name: str = "retrieval.sqlite3",
):
    """Build the service the way production builds it: scope and provider at construction.

    D-M11-02-01: the project scope and the optional vector capability are
    creation-time inputs, not ambient attributes set afterwards. ``embedder``
    overrides the fixture provider so a broken provider can be injected without
    patching the service after the fact. ``store_name`` lets one test build two
    services over the same fixture without sharing a store (a second ``add_page``
    for the same page_id would otherwise be a revision conflict).
    """

    store = RecordStore(tmp_path / store_name)
    if embedder is None and with_embedder:
        embedder = FixtureEmbeddingProvider(payload)
    service = KnowledgeService(
        store, project_id=payload["project_id"], embedding_provider=embedder
    )
    for raw_page in payload["pages"]:
        service.add_page(WikiPage.model_validate(raw_page))
    for raw_edge in payload["edges"]:
        service.add_edge(GraphEdge.model_validate(raw_edge))
    return service, store


def _retrieve(service, payload, *, require_evidence=None, level=None):
    query = payload["query"]
    return service.retrieve(
        query["text"],
        partitions=[KnowledgePartition(value) for value in query["partitions"]],
        level=query["level"] if level is None else level,
        limit=query["limit"],
        require_evidence=(
            query["require_evidence"] if require_evidence is None else require_evidence
        ),
    )


def _ids(hits) -> set[str]:
    return {hit.record_id for hit in hits}


# ---------------------------------------------------------------------------
# L0 boundary -- runs before any scoring
# ---------------------------------------------------------------------------


def test_l0_boundary_removes_every_out_of_scope_page_before_scoring():
    payload = _load_fixture()
    kept = apply_l0_boundary(
        payload["pages"],
        project_id=payload["project_id"],
        partitions=payload["query"]["partitions"],
        require_evidence=True,
    )
    assert {page["page_id"] for page in kept} == {"a-lexical", "a-neighbour", "a-vector-only"}


def test_l0_boundary_keeps_the_three_exclusions_independent():
    payload = _load_fixture()
    pages = payload["pages"]

    # require_evidence is the only switch that brings a-no-evidence back.
    loose = apply_l0_boundary(
        pages, project_id="project-a", partitions=["knowledge"], require_evidence=False
    )
    assert {page["page_id"] for page in loose} == {
        "a-lexical",
        "a-neighbour",
        "a-no-evidence",
        "a-vector-only",
    }

    # Dropping the project scope is what lets the project-b page in: it proves
    # the project filter (not the partition filter) is what removes b-intruder.
    unscoped = apply_l0_boundary(
        pages, project_id=None, partitions=["knowledge"], require_evidence=True
    )
    assert "b-intruder" in {page["page_id"] for page in unscoped}
    assert "a-superseded" not in {page["page_id"] for page in unscoped}


def test_availability_is_anchored_on_the_superseded_review_status():
    """Availability is not defined in the repository; this is the frozen reading.

    ``superseded`` is the one schema value that says "a later revision replaced
    this one", so it is the only status treated as unavailable. Ledger
    ``D-M11-02-02``.
    """

    for status in (ReviewStatus.DRAFT, ReviewStatus.PUBLISHED):
        assert is_available({"review_status": status.value}) is True
    assert is_available({"review_status": ReviewStatus.SUPERSEDED.value}) is False
    # A missing status defaults to draft, i.e. available.
    assert is_available({}) is True


@pytest.mark.parametrize(
    ("status", "available"),
    [
        ("draft", True),
        ("published", True),
        (None, True),
        ("superseded", False),
    ],
)
def test_the_availability_matrix_gates_the_shared_l0_boundary(status, available):
    page = {
        "page_id": "p-1",
        "project_id": "project-a",
        "partition": "knowledge",
        "title": "Grid",
        "body": "grid cells",
        "evidence_ids": ["ev-1"],
    }
    if status is not None:
        page["review_status"] = status

    assert is_available(page) is available
    # Availability is applied by the one gate both arms share, not by a caller.
    assert (
        in_scope(
            page,
            project_id="project-a",
            partitions=frozenset({"knowledge"}),
            require_evidence=True,
        )
        is available
    )


def test_a_published_revision_is_retrievable_and_a_superseded_one_is_not(
    tmp_path: Path,
):
    store = RecordStore(tmp_path / "availability.sqlite3")
    service = KnowledgeService(store, project_id="project-a")
    published = WikiPage(
        page_id="a-published",
        project_id="project-a",
        partition=KNOWLEDGE,
        title="Grid fidelity in simulation",
        body="grid cells drive fidelity",
        evidence_ids=["ev-1"],
        review_status=ReviewStatus.PUBLISHED,
        effective_at=datetime(2026, 9, 17, tzinfo=UTC),
        author="test_knowledge_retrieval",
    )
    retired = published.model_copy(
        update={
            "page_id": "a-retired",
            "review_status": ReviewStatus.SUPERSEDED,
            "effective_at": None,
        }
    )
    service.add_page(published)
    service.add_page(retired)

    assert _ids(service.retrieve("grid cells", partitions=[KNOWLEDGE])) == {
        "a-published"
    }


# ---------------------------------------------------------------------------
# End-to-end pipeline over the frozen fixture
# ---------------------------------------------------------------------------


def test_full_pipeline_ranks_the_three_in_scope_pages(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=True)

    hits = _retrieve(service, payload)
    expected = payload["expected"]

    assert _ids(hits) == set(expected["hit_id_set"])
    # Order is deterministic: a-lexical (BM25 ~2.80) > a-vector-only (cosine
    # ~0.9945) > a-neighbour (graph, decayed to ~0.9815).
    assert [hit.record_id for hit in hits] == ["a-lexical", "a-vector-only", "a-neighbour"]
    assert {hit.record_id: hit.channel.value for hit in hits} == expected["channels"]
    assert all(hit.partition is KNOWLEDGE for hit in hits)


def test_graph_expansion_is_what_surfaces_the_neighbour(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=True)

    hits = {hit.record_id: hit for hit in _retrieve(service, payload)}
    neighbour = hits[payload["expected"]["graph_only_hit"]]
    assert neighbour.channel is RetrievalChannel.GRAPH
    assert neighbour.matched_stage == "L2-graph"
    assert set(neighbour.score_breakdown) == {"graph"}
    assert neighbour.score == pytest.approx(hits["a-lexical"].score * GRAPH_NEIGHBOUR_DECAY)


def test_pre_existing_retrieval_hit_fields_keep_their_meaning(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=True)

    top = {hit.record_id: hit for hit in _retrieve(service, payload)}["a-lexical"]
    assert top.partition is KNOWLEDGE
    assert top.title == "Grid fidelity in simulation"
    assert top.snippet == "grid cells drive fidelity"
    assert top.evidence_ids == ["ev-1"]
    assert top.retrieval_level.startswith("lexical")
    # The new C7 fields are populated, and the best arm is the one reported.
    assert top.channel is RetrievalChannel.LEXICAL
    assert top.matched_stage == "L1"
    assert top.score_breakdown == {"lexical": top.score}


def test_vector_arm_wins_for_a_page_with_no_lexical_overlap(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=True)

    vector_hit = {hit.record_id: hit for hit in _retrieve(service, payload)}["a-vector-only"]
    assert vector_hit.channel is RetrievalChannel.VECTOR
    assert vector_hit.matched_stage == "L2-vector"
    assert set(vector_hit.score_breakdown) == {"vector"}


def test_require_evidence_filters_the_seed_arm(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=True)

    loose = _retrieve(service, payload, require_evidence=False)
    assert _ids(loose) == set(payload["expected"]["without_evidence_filter"]["hit_id_set"])
    assert "a-no-evidence" in _ids(loose)

    strict = _retrieve(service, payload, require_evidence=True)
    assert "a-no-evidence" not in _ids(strict)


def test_graph_arm_obeys_the_same_boundary_gate():
    payload = _load_fixture()
    pages = {page["page_id"]: page for page in payload["pages"]}
    neighbour = dict(pages["a-neighbour"])
    neighbour["evidence_ids"] = []

    def resolve(page_id: str):
        return neighbour if page_id == "a-neighbour" else pages.get(page_id)

    common = {
        "edges": payload["edges"],
        "ordered_ids": ("a-lexical",),
        "candidate_scores": {"a-lexical": 1.0},
        "project_id": "project-a",
        "partitions": frozenset({"knowledge"}),
        "resolve_page": resolve,
    }
    # a-neighbour survives only when the shared gate allows an evidence-free page,
    # and b-intruder (project-b, reachable through edge-cross-project) never does.
    assert expand_graph(require_evidence=True, **common) == {}
    added = expand_graph(require_evidence=False, **common)
    assert set(added) == {"a-neighbour"}
    assert added["a-neighbour"] == pytest.approx(
        max(1.0 * GRAPH_NEIGHBOUR_DECAY, GRAPH_NEIGHBOUR_FLOOR)
    )


def test_cross_project_and_cross_partition_pages_never_surface(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=True)

    for require_evidence in (True, False):
        ids = _ids(_retrieve(service, payload, require_evidence=require_evidence))
        assert {"a-other-partition", "b-intruder", "a-superseded"} & ids == set()


# ---------------------------------------------------------------------------
# L0 project scope -- fail closed, never widen
# ---------------------------------------------------------------------------


def test_the_scope_decides_which_project_is_read(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=False)

    in_scope_a = _retrieve(service, payload)
    assert "b-intruder" not in _ids(in_scope_a)

    # Same store, same query text, different scope: project-b's page is the only
    # page readable from project-b, which proves the filter reads the scope the
    # service was created with rather than the query.
    service.project_id = "project-b"
    assert _ids(_retrieve(service, payload)) == {"b-intruder"}


def test_an_unscoped_service_refuses_to_retrieve(tmp_path: Path):
    payload = _load_fixture()
    store = RecordStore(tmp_path / "unscoped.sqlite3")
    service = KnowledgeService(store)  # no project_id
    for raw_page in payload["pages"]:
        service.add_page(WikiPage.model_validate(raw_page))

    # Fail-closed: "we do not know the scope" must never read as "every scope".
    # If it did, project-b's page -- which the lexical arm ranks happily -- would
    # be returned to a caller that forgot to pass a project.
    with pytest.raises(KnowledgeScopeRequiredError):
        _retrieve(service, payload)


def test_an_empty_scope_is_refused_like_a_missing_one(tmp_path: Path):
    payload = _load_fixture()
    store = RecordStore(tmp_path / "empty-scope.sqlite3")
    service = KnowledgeService(store, project_id="")

    with pytest.raises(KnowledgeScopeRequiredError):
        _retrieve(service, payload)


def test_the_scope_error_stays_catchable_as_a_value_error():
    # The pre-MVP-02 signature already raised ``ValueError`` for a bad partition,
    # so callers may guard with ``except ValueError``; the new error keeps that
    # contract while being specifically identifiable.
    assert issubclass(KnowledgeScopeRequiredError, ValueError)


def test_the_scope_cannot_be_dropped_after_construction(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=False)

    service.project_id = None
    with pytest.raises(KnowledgeScopeRequiredError):
        _retrieve(service, payload)


# ---------------------------------------------------------------------------
# The wired entry point (AutoResearchApplication) -- never the raw service
# ---------------------------------------------------------------------------


def _runtime_page(
    runtime: AutoResearchApplication,
    *,
    project_id: str,
    title: str,
    body: str,
    evidence_ids: tuple[str, ...] = ("ev-1",),
) -> WikiPage:
    """Write one page through the application's unscoped write/index handle."""

    return runtime.knowledge.add_page(
        WikiPage(
            project_id=project_id,
            partition=KNOWLEDGE,
            title=title,
            body=body,
            evidence_ids=list(evidence_ids),
            author="test_knowledge_retrieval",
        )
    )


def test_the_wired_entry_point_cannot_read_across_projects(
    runtime: AutoResearchApplication,
):
    alpha = _runtime_page(
        runtime,
        project_id="alpha",
        title="Grid fidelity in simulation",
        body="grid cells drive fidelity",
    )
    neighbour = _runtime_page(
        runtime,
        project_id="alpha",
        title="Mesh refinement notes",
        body="unrelated narrative",
        evidence_ids=("ev-4",),
    )
    beta = _runtime_page(
        runtime,
        project_id="beta",
        title="Grid cells of beta",
        body="grid cells",
        evidence_ids=("ev-9",),
    )
    # Both edges are created in project alpha, and the second one points at a
    # project-beta page: an edge created in one project may name another's page.
    runtime.knowledge.add_edge(
        GraphEdge(
            project_id="alpha",
            partition=KNOWLEDGE,
            source_id=alpha.page_id,
            relation="summarized_by",
            target_id=neighbour.page_id,
        )
    )
    runtime.knowledge.add_edge(
        GraphEdge(
            project_id="alpha",
            partition=KNOWLEDGE,
            source_id=alpha.page_id,
            relation="summarized_by",
            target_id=beta.page_id,
        )
    )

    in_alpha = runtime.knowledge_scope("alpha").retrieve(
        "grid cells", partitions=[KNOWLEDGE], level=2
    )
    assert [hit.record_id for hit in in_alpha] == [alpha.page_id, neighbour.page_id]

    # The same store, queried in the other scope, exposes only beta's page: the
    # cross-project edge cannot drag it into alpha's result set.
    in_beta = runtime.knowledge_scope("beta").retrieve(
        "grid cells", partitions=[KNOWLEDGE], level=2
    )
    assert [hit.record_id for hit in in_beta] == [beta.page_id]

    # The shared app-level handle is a write/index handle: it has no scope, so a
    # query through it is refused rather than answered across every project.
    with pytest.raises(KnowledgeScopeRequiredError):
        runtime.knowledge.retrieve("grid cells", partitions=[KNOWLEDGE], level=2)


def test_the_wired_scope_only_runs_the_vector_arm_when_it_was_injected(
    runtime: AutoResearchApplication,
):
    page = _runtime_page(
        runtime,
        project_id="alpha",
        title="Numerical mesh convergence",
        body="mesh resolution studies",
    )

    # No lexical overlap with the query, and no provider: no result at all.
    assert runtime.knowledge_scope("alpha").retrieve(
        "grid cells", partitions=[KNOWLEDGE], level=1
    ) == []

    provider = ConstantEmbedder()
    scoped = runtime.knowledge_scope("alpha", embedding_provider=provider)
    hits = scoped.retrieve("grid cells", partitions=[KNOWLEDGE], level=1)

    assert scoped.embedding_provider is provider
    assert [hit.record_id for hit in hits] == [page.page_id]
    assert hits[0].channel is RetrievalChannel.VECTOR
    assert hits[0].retrieval_level == "lexical+vector"


# ---------------------------------------------------------------------------
# Degradation and level gating
# ---------------------------------------------------------------------------


def test_missing_embedder_degrades_to_lexical_and_reports_it(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=False)

    hits = _retrieve(service, payload)
    degraded = payload["expected"]["vector_unavailable"]
    assert _ids(hits) == set(degraded["hit_id_set"])
    assert all(degraded["retrieval_level_contains"] in hit.retrieval_level for hit in hits)
    assert all(hit.channel is not RetrievalChannel.VECTOR for hit in hits)


def test_a_provider_that_raises_degrades_instead_of_aborting(tmp_path: Path):
    payload = _load_fixture()
    service, store = _build_service(
        tmp_path, payload, with_embedder=False, embedder=BrokenEmbedder()
    )

    hits = _retrieve(service, payload)
    degraded = payload["expected"]["vector_unavailable"]

    # Same result set as having no provider at all: a broken capability costs the
    # vector arm and nothing else.
    assert _ids(hits) == set(degraded["hit_id_set"])
    assert all(hit.channel is not RetrievalChannel.VECTOR for hit in hits)
    for hit in hits:
        assert hit.retrieval_level.startswith("lexical+graph")
        assert "degraded" in hit.retrieval_level
        # The reason names the cause, so a log reader does not have to guess.
        assert "RuntimeError" in hit.retrieval_level
        assert "model file is missing" in hit.retrieval_level

    # A degraded query is still an audited query.
    assert len(store.list(RECALL_AUDIT_KIND)) == 1


def test_inconsistent_vector_dimensions_are_a_capability_failure_too(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(
        tmp_path, payload, with_embedder=False, embedder=DimensionDriftEmbedder()
    )

    hits = _retrieve(service, payload)
    degraded = payload["expected"]["vector_unavailable"]

    assert _ids(hits) == set(degraded["hit_id_set"])
    for hit in hits:
        assert "ValueError" in hit.retrieval_level
        assert "dimensions disagree" in hit.retrieval_level


def test_a_partially_computed_vector_pass_is_discarded_as_a_whole():
    payload = _load_fixture()
    pool = apply_l0_boundary(
        payload["pages"],
        project_id="project-a",
        partitions=["knowledge"],
        require_evidence=True,
    )
    provider = MidPassEmbedder(answers=2)  # the query, then the first page

    scores, reason = vector_arm(pool, query=payload["query"]["text"], embedder=provider)

    # Three calls were needed for three pages; two succeeded before the failure.
    assert provider.calls == 3
    assert scores == {}, "half a vector pass must not be merged into the ranking"
    assert reason is not None and "RuntimeError" in reason


def test_a_mid_pass_failure_leaves_no_vector_trace_in_the_ranking(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(
        tmp_path, payload, with_embedder=False, embedder=MidPassEmbedder(answers=2)
    )

    hits = {hit.record_id: hit for hit in _retrieve(service, payload)}

    assert set(hits) == set(payload["expected"]["vector_unavailable"]["hit_id_set"])
    # The first page was answered before the provider died; if that half pass had
    # survived, it would show up here as a vector entry in the breakdown.
    assert all("vector" not in hit.score_breakdown for hit in hits.values())
    # The graph neighbour is graph-only, so the lexical page is the one that would
    # have carried the leaked half pass.
    assert set(hits["a-lexical"].score_breakdown) == {"lexical"}
    assert hits["a-lexical"].channel is RetrievalChannel.LEXICAL


def test_level_one_never_runs_the_graph_arm(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=True)

    hits = _retrieve(service, payload, level=1)
    assert _ids(hits) == {"a-lexical", "a-vector-only"}
    assert all("graph" not in hit.retrieval_level for hit in hits)


def test_the_vector_arm_runs_only_because_the_provider_was_injected(tmp_path: Path):
    """The provider is a construction input, not something to remember later."""

    payload = _load_fixture()
    wired, _ = _build_service(
        tmp_path, payload, with_embedder=True, store_name="wired.sqlite3"
    )
    bare, _ = _build_service(
        tmp_path, payload, with_embedder=False, store_name="bare.sqlite3"
    )

    # Nothing was assigned on either service after construction (see
    # ``_build_service``): the difference in behaviour is the constructor argument.
    assert bare.embedding_provider is None
    assert wired.embedding_provider.name == payload["embeddings"]["provider"]

    assert all(
        hit.channel is not RetrievalChannel.VECTOR for hit in _retrieve(bare, payload)
    )
    assert any(
        hit.channel is RetrievalChannel.VECTOR for hit in _retrieve(wired, payload)
    )


def test_a_graph_parent_score_is_still_not_enough_to_keep_a_superseded_neighbour():
    payload = _load_fixture()
    pages = {page["page_id"]: page for page in payload["pages"]}
    retired = dict(pages["a-neighbour"])
    retired["review_status"] = ReviewStatus.SUPERSEDED.value

    def resolve(page_id: str):
        return retired if page_id == "a-neighbour" else pages.get(page_id)

    added = expand_graph(
        edges=payload["edges"],
        ordered_ids=("a-lexical",),
        candidate_scores={"a-lexical": 1.0},
        project_id="project-a",
        partitions=frozenset({"knowledge"}),
        require_evidence=False,
        resolve_page=resolve,
    )
    assert added == {}


# ---------------------------------------------------------------------------
# L8 recall audit (R-006 C8)
# ---------------------------------------------------------------------------


def test_every_retrieve_persists_one_valid_subset_chain(tmp_path: Path):
    payload = _load_fixture()
    service, store = _build_service(tmp_path, payload, with_embedder=True)

    hits = _retrieve(service, payload)
    _retrieve(service, payload)

    rows = store.list(RECALL_AUDIT_KIND)
    assert len(rows) == 2
    for row in rows:
        assert set(row["final_hits"]) == _ids(hits)
        assert (
            set(row["final_hits"])
            <= set(row["reranked"])
            <= set(row["deduped"])
            <= set(row["candidates"])
        )
        assert set(row["stage_timings_ms"]) == {"L0", "L1", "L2-vector", "L2-graph"}

    record = rows[0]
    assert record["project_id"] == payload["project_id"]
    assert record["query"] == payload["query"]["text"]
    assert set(record["candidates"]) == set(payload["expected"]["hit_id_set"])
    assert len(record["candidates"]) == payload["expected"]["chain_size"]
    assert record["filters"]["require_evidence"] is True


def test_recall_audit_can_be_switched_off(tmp_path: Path):
    payload = _load_fixture()
    service, store = _build_service(tmp_path, payload, with_embedder=True)

    service.recall_audit_enabled = False
    _retrieve(service, payload)
    assert store.list(RECALL_AUDIT_KIND) == []


def test_audit_model_refuses_a_leaked_final_hit():
    with pytest.raises(ValidationError):
        RecallAuditRecord(
            query="grid cells",
            candidates=("a",),
            deduped=("a",),
            reranked=("a",),
            final_hits=("b",),
        )


# ---------------------------------------------------------------------------
# Determinism and unit-level contracts
# ---------------------------------------------------------------------------


def test_two_runs_over_the_same_index_are_identical(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=True)

    def fingerprint(hits):
        return [(hit.record_id, hit.score, hit.channel.value, hit.matched_stage) for hit in hits]

    assert fingerprint(_retrieve(service, payload)) == fingerprint(_retrieve(service, payload))


def test_offline_embedder_is_reproducible_across_processes():
    # ``PYTHONHASHSEED=random`` is forced so a switch from zlib.crc32 to the builtin
    # ``hash`` would make the child's vector differ from this process's.
    code = (
        "from autoresearch.knowledge_retrieval import HashingEmbedder;"
        "print(list(HashingEmbedder().embed('grid cells')))"
    )
    child = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONHASHSEED": "random"},
    )
    assert child.returncode == 0, child.stderr
    assert child.stdout.strip() == str(list(HashingEmbedder().embed("grid cells")))


def test_hashing_embedder_is_l2_normalised_and_empty_safe():
    vector = HashingEmbedder(dimensions=8).embed("alpha beta")
    assert math.isclose(sum(value * value for value in vector), 1.0, rel_tol=1e-12)
    assert HashingEmbedder(dimensions=8).embed("") == (0.0,) * 8


def test_page_text_is_the_embedder_input_contract():
    assert page_text({"title": "T", "tags": ["a", "b"], "body": "B"}) == "T a b B"


def test_bm25_matches_a_hand_computed_value():
    pages = [
        {"page_id": "d1", "title": "alpha", "tags": [], "body": ""},
        {"page_id": "d2", "title": "beta", "tags": [], "body": ""},
    ]
    # N=2, df=1 -> idf = log(1 + (2-1+0.5)/(1+0.5)) = log(2).
    # d1: f = 3.0 (title weight), len = 3, avg = 3, ratio = 1
    #     -> denominator = 3.0 + 1.5 * (1 - 0.75 + 0.75 * 1) = 4.5
    expected = math.log(2.0) * 3.0 * (1.5 + 1.0) / (3.0 + 1.5 * (1.0 - 0.75 + 0.75 * 1.0))
    assert bm25_scores(pages, ["alpha"]) == {"d1": round(expected, 12)}


def test_cosine_similarity_refuses_a_dimension_mismatch():
    with pytest.raises(ValueError, match="dimensions disagree"):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# Adversarial meta-check: the fixture must discriminate the old behaviour
# ---------------------------------------------------------------------------


def _legacy_hit_ids(payload: dict) -> set[str]:
    """Reproduce the pre-MVP-02 ranking verbatim.

    Source: ``f197b7a:src/autoresearch/knowledge.py:199-268`` (the base revision of
    this package). Kept only to prove the fixture is not vacuous.
    """

    query = payload["query"]
    terms = [term for term in query["text"].lower().split() if term]
    partitions = set(query["partitions"])
    pages = {page["page_id"]: page for page in payload["pages"]}

    scored: dict[str, float] = {}
    for raw in payload["pages"]:
        if raw["partition"] not in partitions:
            continue
        title, body = raw["title"].lower(), raw["body"].lower()
        tags = " ".join(raw.get("tags", [])).lower()
        score = sum(
            (3.0 if term in title else 0.0)
            + (1.0 if term in body else 0.0)
            + (2.0 if term in tags else 0.0)
            for term in terms
        )
        if score > 0 and (not query["require_evidence"] or raw.get("evidence_ids")):
            scored[raw["page_id"]] = score

    if query["level"] >= 2 and scored:
        neighbours: dict[str, set[str]] = {}
        for edge in payload["edges"]:
            neighbours.setdefault(edge["source_id"], set()).add(edge["target_id"])
            neighbours.setdefault(edge["target_id"], set()).add(edge["source_id"])
        for page_id in list(scored):
            for neighbour_id in neighbours.get(page_id, ()):
                neighbour = pages.get(neighbour_id)
                if neighbour is None or neighbour["partition"] not in partitions:
                    continue
                if query["require_evidence"] and not neighbour.get("evidence_ids"):
                    continue
                scored.setdefault(neighbour_id, max(scored[page_id] * 0.35, 0.1))

    return set(scored)


def test_the_fixture_discriminates_the_pre_mvp02_implementation():
    payload = _load_fixture()
    expected = set(payload["expected"]["hit_id_set"])
    legacy = _legacy_hit_ids(payload)

    assert legacy != expected, "fixture is vacuous: the old ranking already matches"
    # Named differences, so a later fixture edit cannot quietly drop the discrimination.
    assert "b-intruder" in legacy and "b-intruder" not in expected  # no project filter
    assert "a-superseded" in legacy and "a-superseded" not in expected  # no availability
    assert "a-vector-only" not in legacy and "a-vector-only" in expected  # no vector arm
