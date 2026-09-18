"""Candidate recall pipeline for the M11 knowledge lane (M11-05 / TASK-SPECS.md:411).

Stages, in the order they must run:

- ``L0``  boundary filter -- ``project_id`` / ``partition`` / availability, applied
  **before any scoring** (``TASK-SPECS.md:429``, ``task-package.json:36``);
- ``L1``  lexical recall -- field-weighted BM25 over title / tags / body, replacing
  the previous naive substring count (``TASK-SPECS.md:420``);
- ``L2``  vector recall -- cosine similarity against an injected ``EmbeddingProvider``;
  when no provider is available **or the provider raises**, the arm reports a
  degradation reason instead of inventing a vector result, and a partially computed
  vector pass is discarded rather than mixed into the ranking
  (``TASK-SPECS.md:438``);
- ``L2``  graph expansion -- same-partition neighbours of the surviving candidates,
  preserving the M11-MVP-01 semantics (``TASK-SPECS.md:432``).

Everything here is a pure function over plain payload dicts plus a deterministic
offline embedder, so the whole pipeline is reproducible without a database, a
network connection or a model file.

Availability is not defined anywhere in the repository (the word only appears at
``TASK-SPECS.md:429`` / ``task-package.json:62``). This module anchors it on the one
schema signal that can express it: a page whose ``review_status`` is
``ReviewStatus.SUPERSEDED`` (``contracts.py:105``) is treated as not available.
See ledger decision ``D-M11-02-02``.
"""

from __future__ import annotations

import math
import re
import time
import zlib
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from autoresearch.contracts import RetrievalChannel, ReviewStatus

# Stage labels carried on every hit (RetrievalHit.matched_stage) and on the audit
# record's stage_timings_ms.
STAGE_L0 = "L0"
STAGE_LEXICAL = "L1"
STAGE_VECTOR = "L2-vector"
STAGE_GRAPH = "L2-graph"

#: Field weights for the lexical arm. Title matches matter most, tags next.
_FIELD_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("title", 3.0),
    ("tags", 2.0),
    ("body", 1.0),
)

#: Standard BM25 parameters; documented so the fixture's expected ranking is explainable.
BM25_K1 = 1.5
BM25_B = 0.75

#: Graph neighbours inherit a decayed score, never below a floor (M11-MVP-01 semantics).
GRAPH_NEIGHBOUR_DECAY = 0.35
GRAPH_NEIGHBOUR_FLOOR = 0.1

#: Rounded to 12 decimals so scores are stable when they round-trip through JSON.
_SCORE_DIGITS = 12

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_UNAVAILABLE_REVIEW_STATUSES = frozenset({ReviewStatus.SUPERSEDED.value})


def tokenize(text: str) -> list[str]:
    """Lower-case alphanumeric tokenisation shared by every arm."""

    return _TOKEN_RE.findall(text.lower())


def is_available(page: Mapping[str, Any]) -> bool:
    """``L0`` availability predicate. See the module docstring for the anchoring rationale."""

    status = page.get("review_status", ReviewStatus.DRAFT.value)
    if hasattr(status, "value"):
        status = status.value
    return status not in _UNAVAILABLE_REVIEW_STATUSES


def _partition_name(page: Mapping[str, Any]) -> str | None:
    value = page.get("partition")
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def _page_project(page: Mapping[str, Any]) -> str | None:
    value = page.get("project_id")
    return None if value is None else str(value)


def in_scope(
    page: Mapping[str, Any],
    *,
    project_id: str | None,
    partitions: frozenset[str],
    require_evidence: bool,
) -> bool:
    """Single L0 gate shared by the seed pool and the graph-expanded neighbours.

    Both arms must obey the same boundary (``TASK-SPECS.md:430``), and
    ``require_evidence`` must filter both arms (``TASK-SPECS.md:431``), so the gate
    lives in exactly one place.
    """

    partition = _partition_name(page)
    if partition is None or partition not in partitions:
        return False
    if project_id is not None and _page_project(page) != project_id:
        return False
    if not is_available(page):
        return False
    return not (require_evidence and not page.get("evidence_ids"))


def apply_l0_boundary(
    pages: Iterable[Mapping[str, Any]],
    *,
    project_id: str | None,
    partitions: Iterable[str],
    require_evidence: bool,
) -> list[dict[str, Any]]:
    """Filter the raw page pool before any scoring happens."""

    allowed = frozenset(str(part.value if hasattr(part, "value") else part) for part in partitions)
    return [
        dict(page)
        for page in pages
        if in_scope(
            page,
            project_id=project_id,
            partitions=allowed,
            require_evidence=require_evidence,
        )
    ]


def _document_terms(page: Mapping[str, Any]) -> dict[str, float]:
    """Field-weighted term frequencies for one page."""

    counts: dict[str, float] = {}
    for field_name, weight in _FIELD_WEIGHTS:
        raw = page.get(field_name, "")
        if isinstance(raw, (list, tuple, set)):
            raw = " ".join(str(item) for item in raw)
        for token in tokenize(str(raw)):
            counts[token] = counts.get(token, 0.0) + weight
    return counts


def bm25_scores(pages: Sequence[Mapping[str, Any]], terms: Sequence[str]) -> dict[str, float]:
    """Okapi BM25 over the field-weighted documents.

    Pure Python on purpose: ``storage.py`` is a forbidden path for this package, so
    no FTS5 index table can be created, and BM25 only needs term frequencies plus
    document lengths to be reproducible (ledger ``D-M11-02-03``).
    """

    documents: dict[str, dict[str, float]] = {}
    for page in pages:
        page_id = str(page["page_id"])
        documents[page_id] = _document_terms(page)
    total = len(documents)
    if total == 0:
        return {}

    lengths = {page_id: sum(counts.values()) for page_id, counts in documents.items()}
    average_length = sum(lengths.values()) / total
    scores: dict[str, float] = dict.fromkeys(documents, 0.0)

    for term in sorted(set(terms)):
        document_frequency = sum(1 for counts in documents.values() if counts.get(term))
        if document_frequency == 0:
            continue
        idf = math.log(1.0 + (total - document_frequency + 0.5) / (document_frequency + 0.5))
        for page_id, counts in documents.items():
            frequency = counts.get(term, 0.0)
            if frequency == 0.0:
                continue
            length_ratio = lengths[page_id] / average_length if average_length else 0.0
            denominator = frequency + BM25_K1 * (1.0 - BM25_B + BM25_B * length_ratio)
            scores[page_id] += idf * (frequency * (BM25_K1 + 1.0)) / denominator

    return {
        page_id: round(score, _SCORE_DIGITS)
        for page_id, score in scores.items()
        if score > 0.0
    }


class EmbeddingProvider(Protocol):
    """Minimal embedding contract; the vector arm degrades when none is supplied."""

    @property
    def name(self) -> str: ...

    def embed(self, text: str) -> Sequence[float]: ...


@dataclass(frozen=True)
class HashingEmbedder:
    """Dependency-free, deterministic offline embedder (feature hashing + L2 norm).

    Uses :func:`zlib.crc32` rather than the builtin ``hash``: Python randomises string
    hashing per process, which would break the cross-store repeatability requirement.
    """

    dimensions: int = 64
    name: str = "hashing-64"

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            vector[zlib.crc32(token.encode("utf-8")) % self.dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return tuple(vector)
        return tuple(value / norm for value in vector)


def page_text(page: Mapping[str, Any]) -> str:
    """The exact text handed to an ``EmbeddingProvider`` for one page.

    Public because it is the embedder's input contract: a provider must embed
    ``page_text(page)`` so the stored and query vectors live in the same space.
    """

    chunks: list[str] = []
    for field_name, _ in _FIELD_WEIGHTS:
        raw = page.get(field_name, "")
        if isinstance(raw, (list, tuple, set)):
            raw = " ".join(str(item) for item in raw)
        chunks.append(str(raw))
    return " ".join(chunks)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions disagree")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    return dot / (left_norm * right_norm)


def vector_scores(
    pages: Sequence[Mapping[str, Any]], query: str, embedder: EmbeddingProvider
) -> dict[str, float]:
    """Cosine similarity of every L0-surviving page against the query embedding."""

    query_vector = embedder.embed(query)
    scores: dict[str, float] = {}
    for page in pages:
        similarity = cosine_similarity(query_vector, embedder.embed(page_text(page)))
        if similarity > 0.0:
            scores[str(page["page_id"])] = round(similarity, _SCORE_DIGITS)
    return scores


def vector_arm(
    pages: Sequence[Mapping[str, Any]],
    *,
    query: str,
    embedder: EmbeddingProvider | None,
) -> tuple[dict[str, float], str | None]:
    """Run the vector arm behind a degradation boundary (``TASK-SPECS.md:438``).

    Returns ``(scores, degradation_reason)``. When the arm produced scores the
    reason is ``None``; when the arm could not run the scores are ``{}`` -- never a
    partial vector result, because mixing half a vector pass into the ranking would
    silently produce an incomplete result set.

    An ``EmbeddingProvider`` is an external capability boundary: the model file may
    be missing, the model may fail to load, the dimensions may disagree, or the
    provider may simply have a bug. None of those may abort a query that the
    lexical arm can still answer, so ``embed`` is allowed to raise here and the
    reason keeps both the exception type and its message.

    ``BaseException`` is deliberately **not** caught: ``KeyboardInterrupt`` and
    ``SystemExit`` are process-level signals, not capability failures. See ledger
    ``D-M11-02-08``.
    """

    if embedder is None:
        return {}, "no embedding provider"
    if not query.strip():
        return {}, None
    try:
        scores = vector_scores(pages, query, embedder)
    except Exception as exc:
        return {}, f"vector provider failed: {type(exc).__name__}: {exc}"
    return scores, None


def expand_graph(
    *,
    edges: Iterable[Mapping[str, Any]],
    ordered_ids: Sequence[str],
    candidate_scores: Mapping[str, float],
    project_id: str | None,
    partitions: frozenset[str],
    require_evidence: bool,
    resolve_page: Callable[[str], Mapping[str, Any] | None],
) -> dict[str, float]:
    """Add same-partition neighbours of the scored candidates.

    Preserves the M11-MVP-01 semantics (decayed score, floor, "first parent wins"),
    and additionally checks ``project_id`` on **both** sides: the edge's own project
    (an edge records the project that created it) and the resolved neighbour page's
    project. Filtering the edge alone is insufficient -- an edge created in project A
    may point at a page in project B.
    """

    neighbours: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if project_id is not None and str(edge.get("project_id") or "") != project_id:
            continue
        source_id = edge.get("source_id")
        target_id = edge.get("target_id")
        if source_id is None or target_id is None:
            continue
        neighbours[str(source_id)].add(str(target_id))
        neighbours[str(target_id)].add(str(source_id))

    added: dict[str, float] = {}
    for page_id in ordered_ids:
        parent_score = candidate_scores[page_id]
        # Sorted so the "first parent wins" tie-break cannot depend on set ordering.
        for neighbour_id in sorted(neighbours.get(page_id, ())):
            if neighbour_id in candidate_scores or neighbour_id in added:
                continue
            page = resolve_page(neighbour_id)
            if page is None:
                continue
            if not in_scope(
                page,
                project_id=project_id,
                partitions=partitions,
                require_evidence=require_evidence,
            ):
                continue
            added[neighbour_id] = max(
                parent_score * GRAPH_NEIGHBOUR_DECAY, GRAPH_NEIGHBOUR_FLOOR
            )
    return added


@dataclass(frozen=True)
class RecallCandidate:
    """One scored hit together with the channel and stage that produced it."""

    page_id: str
    partition: str
    title: str
    snippet: str
    score: float
    evidence_ids: tuple[str, ...]
    channel: RetrievalChannel
    matched_stage: str
    score_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RecallResult:
    """Stage-by-stage output. The four id tuples form the audit subset chain."""

    candidates: tuple[str, ...]
    deduped: tuple[str, ...]
    reranked: tuple[str, ...]
    hits: tuple[RecallCandidate, ...]
    stage_timings_ms: dict[str, float]
    degradation: str | None
    vector_used: bool


def describe_retrieval_level(*, level: int, vector_used: bool, degradation: str | None) -> str:
    """Human-readable trace of the arms that actually ran (``TASK-SPECS.md:438``).

    Reuses the historical vocabulary: ``lexical`` and ``lexical+graph`` are unchanged
    for the pre-existing level=1 / level=2 lexical-only paths.
    """

    arms = ["lexical"]
    if vector_used:
        arms.append("vector")
    if level >= 2:
        arms.append("graph")
    label = "+".join(arms)
    if degradation is not None:
        return f"{label} (degraded: {degradation})"
    return label


def recall(
    *,
    pages: Sequence[Mapping[str, Any]],
    query: str,
    level: int,
    limit: int,
    project_id: str | None,
    partitions: Iterable[str],
    require_evidence: bool = False,
    embedder: EmbeddingProvider | None = None,
    edges: Iterable[Mapping[str, Any]] = (),
    resolve_page: Callable[[str], Mapping[str, Any] | None] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> RecallResult:
    """Run L0 -> L1 -> L2(vector) -> L2(graph) and return the ranked candidates.

    ``project_id`` is an explicit parameter here so the pipeline itself never has to
    guess a scope; how the service obtains it is a wiring concern (ledger
    ``D-M11-02-01``).
    """

    partitions_set = frozenset(
        str(part.value if hasattr(part, "value") else part) for part in partitions
    )
    timings: dict[str, float] = {}

    started = clock()
    pool = apply_l0_boundary(
        pages,
        project_id=project_id,
        partitions=partitions_set,
        require_evidence=require_evidence,
    )
    timings[STAGE_L0] = round((clock() - started) * 1000.0, 6)

    candidates: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for page in pool:
        page_id = str(page["page_id"])
        candidates.append(page_id)
        by_id.setdefault(page_id, page)
    deduped = tuple(dict.fromkeys(candidates))

    terms = tokenize(query)
    started = clock()
    lexical = bm25_scores(pool, terms) if terms else {}
    timings[STAGE_LEXICAL] = round((clock() - started) * 1000.0, 6)

    started = clock()
    vector, degradation = vector_arm(pool, query=query, embedder=embedder)
    timings[STAGE_VECTOR] = round((clock() - started) * 1000.0, 6)

    scores: dict[str, float] = {}
    channels: dict[str, RetrievalChannel] = {}
    stages: dict[str, str] = {}
    breakdown: dict[str, dict[str, float]] = {}
    for page_id in deduped:
        parts = {
            "lexical": lexical.get(page_id, 0.0),
            "vector": vector.get(page_id, 0.0),
        }
        best = max(parts.values())
        if best <= 0.0:
            continue
        scores[page_id] = best
        breakdown[page_id] = {name: value for name, value in parts.items() if value > 0.0}
        if parts["vector"] > parts["lexical"]:
            channels[page_id] = RetrievalChannel.VECTOR
            stages[page_id] = STAGE_VECTOR
        else:
            channels[page_id] = RetrievalChannel.LEXICAL
            stages[page_id] = STAGE_LEXICAL

    graph: dict[str, float] = {}
    started = clock()
    if level >= 2 and scores and resolve_page is not None:
        graph = expand_graph(
            edges=edges,
            ordered_ids=tuple(scores),
            candidate_scores=scores,
            project_id=project_id,
            partitions=partitions_set,
            require_evidence=require_evidence,
            resolve_page=resolve_page,
        )
    timings[STAGE_GRAPH] = round((clock() - started) * 1000.0, 6)

    for page_id, score in graph.items():
        page = resolve_page(page_id) if resolve_page is not None else None
        if page is None:
            continue
        by_id[page_id] = dict(page)
        scores[page_id] = score
        channels[page_id] = RetrievalChannel.GRAPH
        stages[page_id] = STAGE_GRAPH
        breakdown[page_id] = {"graph": score}

    reranked_ids = sorted(
        scores,
        key=lambda page_id: (-scores[page_id], str(by_id[page_id].get("title", "")), page_id),
    )
    final_ids = reranked_ids[:limit]

    hits = tuple(
        RecallCandidate(
            page_id=page_id,
            partition=_partition_name(by_id[page_id]) or "",
            title=str(by_id[page_id].get("title", "")),
            snippet=str(by_id[page_id].get("body", ""))[:500],
            score=scores[page_id],
            evidence_ids=tuple(by_id[page_id].get("evidence_ids", []) or ()),
            channel=channels[page_id],
            matched_stage=stages[page_id],
            score_breakdown=dict(breakdown[page_id]),
        )
        for page_id in final_ids
    )

    return RecallResult(
        candidates=tuple(candidates),
        deduped=deduped,
        reranked=tuple(reranked_ids),
        hits=hits,
        stage_timings_ms=timings,
        degradation=degradation,
        vector_used=bool(vector) and degradation is None,
    )
