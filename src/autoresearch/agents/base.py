from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph


class WorkflowState(TypedDict, total=False):
    schema_version: int
    project_id: str
    run_id: str
    idea: str
    lifecycle_state: str
    run_status: str
    request_release: bool
    search_queries: list[str]
    seed_papers: list[dict[str, Any]]
    paper_ids: list[str]
    reading_card_ids: list[str]
    innovation_ids: list[str]
    work_package_ids: list[str]
    manuscript_id: str | None
    review_ids: list[str]
    evidence_ids: list[str]
    gate_decision_ids: list[str]
    handoff: dict[str, Any] | None
    diagnostics: list[str]
    #: Carry the experiment lane's declared closure state (see ``LoopClosure``).
    #: This key MUST be declared here: langgraph keeps only the keys the state
    #: schema declares and silently drops the rest, so a node that writes
    #: ``loop_closure`` without a declaration here would have it vanish before
    #: the closure-requiring gate ever reads it.
    loop_closure: str
    #: Non-blocking warnings carried through the graph. This key MUST be declared
    #: here: langgraph keeps only the keys the state schema declares and silently
    #: drops the rest, so a warning written by a node without a declaration here
    #: never survives the graph at all.
    warnings: list[str]
    blockers: list[str]
    last_agent: str
    updated_at: str


def single_node_subgraph(name: str, function: Callable[[WorkflowState], dict]) -> Any:
    builder = StateGraph(WorkflowState)
    builder.add_node(name, function)
    builder.add_edge(START, name)
    builder.add_edge(name, END)
    return builder.compile(checkpointer=False)
