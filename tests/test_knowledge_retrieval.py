"""M11-MVP-02 candidate recall pipeline: L0 boundary -> L1 BM25 -> L2 vector / graph.

Fixture: ``fixtures/knowledge_retrieval/recall_pipeline.json``. Its ``expected`` block
is hand-authored from the boundary rules (``TASK-SPECS.md:429-432``), never regenerated
from the implementation.

The last test in the file reproduces the pre-MVP-02 ranking
(``f197b7a:src/autoresearch/knowledge.py:199-268``) and asserts the fixture discriminates
it, so the assertions above cannot pass vacuously.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from autoresearch.contracts import (
    GraphEdge,
    KnowledgePartition,
    RetrievalChannel,
    WikiPage,
)
from autoresearch.knowledge import KnowledgeService
from autoresearch.knowledge_retrieval import (
    GRAPH_NEIGHBOUR_DECAY,
    GRAPH_NEIGHBOUR_FLOOR,
    HashingEmbedder,
    apply_l0_boundary,
    bm25_scores,
    cosine_similarity,
    expand_graph,
    is_available,
    page_text,
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


def _load_fixture() -> dict:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["schema"] == "m11-knowledge-retrieval/v1"
    return payload


def _build_service(tmp_path: Path, payload: dict, *, with_embedder: bool):
    store = RecordStore(tmp_path / "retrieval.sqlite3")
    service = KnowledgeService(store)
    # D-M11-02-01: the L0 project scope is read as an optional instance attribute.
    # This line is the testable wiring point; production wiring belongs to the owner.
    service.project_id = payload["project_id"]
    for raw_page in payload["pages"]:
        service.add_page(WikiPage.model_validate(raw_page))
    for raw_edge in payload["edges"]:
        service.add_edge(GraphEdge.model_validate(raw_edge))
    if with_embedder:
        service.embedding_provider = FixtureEmbeddingProvider(payload)
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
    draft = {"review_status": "draft"}
    superseded = {"review_status": "superseded"}
    assert is_available(draft) is True
    assert is_available(superseded) is False
    # A missing status defaults to draft, i.e. available.
    assert is_available({}) is True


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


def test_the_project_filter_is_driven_by_the_optional_scope_attribute(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=False)

    del service.project_id
    assert "b-intruder" in _ids(_retrieve(service, payload))

    service.project_id = "project-a"
    assert "b-intruder" not in _ids(_retrieve(service, payload))


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


def test_level_one_never_runs_the_graph_arm(tmp_path: Path):
    payload = _load_fixture()
    service, _ = _build_service(tmp_path, payload, with_embedder=True)

    hits = _retrieve(service, payload, level=1)
    assert _ids(hits) == {"a-lexical", "a-vector-only"}
    assert all("graph" not in hit.retrieval_level for hit in hits)


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
