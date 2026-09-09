from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from autoresearch.application import AutoResearchApplication
from autoresearch.audit import AuditRuntime, BoundedEvidenceView, read_bounded_evidence_view
from autoresearch.audit_contracts import AuditInvocationRequest, AuditMode
from autoresearch.config import get_settings
from autoresearch.contracts import (
    EvidenceGrade,
    EvidenceItem,
    EvidenceType,
    EvolutionProposal,
    KnowledgePartition,
    ManuscriptRevisionRequest,
    PaperRecord,
    ProjectCreate,
    ResumeRequest,
    RunRequest,
)
from autoresearch.resolver import (
    ResolverRecord,
    ResolverSnapshot,
    ResolverSnapshotRepository,
    SnapshotResolverAdapter,
)
from autoresearch.storage import RecordStore

app = typer.Typer(
    name="autoresearch",
    help="Evidence-governed five-agent research workflow.",
    no_args_is_help=True,
)


def _echo(value) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


@app.command()
def doctor() -> None:
    """Check local runtime, agent registry, and safe configuration summary."""
    runtime = AutoResearchApplication()
    try:
        _echo(runtime.doctor())
    finally:
        runtime.close()


@app.command("init-project")
def init_project(
    project_id: Annotated[str, typer.Argument(help="Stable lowercase project ID")],
    title: Annotated[str, typer.Argument(help="Human-readable project title")],
    idea: Annotated[str, typer.Option("--idea", help="Initial research idea")] = "",
    owner: Annotated[str, typer.Option("--owner", help="Project owner label")] = "user",
) -> None:
    """Instantiate a governed paper-project folder from the canonical template."""
    runtime = AutoResearchApplication()
    try:
        _echo(
            runtime.create_project(
                ProjectCreate(project_id=project_id, title=title, idea=idea),
                owner=owner,
            )
        )
    finally:
        runtime.close()


@app.command()
def run(
    project_id: Annotated[str, typer.Argument(help="Existing paper project ID")],
    idea: Annotated[str, typer.Option("--idea", help="Research idea for this run")],
    seed_file: Annotated[
        Path | None,
        typer.Option(
            "--seed-file",
            exists=True,
            dir_okay=False,
            help="JSON array of user-authorized paper records",
        ),
    ] = None,
    request_release: Annotated[
        bool,
        typer.Option("--request-release", help="Pause at the L4 human release gate"),
    ] = False,
) -> None:
    """Execute from idea until completion, an evidence block, or a human interrupt."""
    seeds: list[PaperRecord] = []
    if seed_file:
        raw_items = json.loads(seed_file.read_text(encoding="utf-8"))
        seeds = [PaperRecord.model_validate({**raw, "project_id": project_id}) for raw in raw_items]
    runtime = AutoResearchApplication()
    try:
        _echo(
            runtime.run(
                RunRequest(
                    project_id=project_id,
                    idea=idea,
                    seed_papers=seeds,
                    request_release=request_release,
                )
            )
        )
    finally:
        runtime.close()


@app.command()
def resume(
    run_id: Annotated[str, typer.Argument(help="Interrupted LangGraph run ID")],
    approve: Annotated[bool, typer.Option("--approve/--reject")],
    reviewer: Annotated[str, typer.Option("--reviewer", help="Named human reviewer")],
    note: Annotated[str, typer.Option("--note")] = "",
) -> None:
    """Resume an L4 human interrupt using the same durable thread ID."""
    runtime = AutoResearchApplication()
    try:
        _echo(
            runtime.resume(
                run_id,
                ResumeRequest(approval=approve, reviewer=reviewer, note=note),
            )
        )
    finally:
        runtime.close()


@app.command()
def status(
    run_id: Annotated[str, typer.Argument(help="Run ID")],
    checkpoint: Annotated[bool, typer.Option("--checkpoint")] = False,
) -> None:
    """Read an application run record and optionally its LangGraph checkpoint."""
    runtime = AutoResearchApplication()
    try:
        record = runtime.get_run(run_id)
        if record is None:
            raise typer.BadParameter(f"unknown run: {run_id}")
        if checkpoint:
            record = {**record, "checkpoint": runtime.graph_state(run_id)}
        _echo(record)
    finally:
        runtime.close()


@app.command()
def audit(
    input_file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            help="JSON AuditInvocationRequest or {request, evidence_view} envelope",
        ),
    ],
    snapshot_file: Annotated[
        Path | None,
        typer.Option(
            "--snapshot",
            exists=True,
            dir_okay=False,
            help="Versioned local resolver snapshot JSON",
        ),
    ] = None,
    mode: Annotated[AuditMode, typer.Option("--mode")] = AuditMode.STANDALONE,
) -> None:
    """Run the local Audit runtime against bounded evidence and a resolver snapshot."""
    payload = json.loads(input_file.read_text(encoding="utf-8"))
    request_payload = payload.get("request", payload)
    request = AuditInvocationRequest.model_validate({**request_payload, "mode": mode})
    settings = get_settings()
    settings.ensure_runtime_dirs()
    store = RecordStore(settings.db_path)
    snapshots = ResolverSnapshotRepository(store)
    if snapshot_file:
        snapshot_payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
        if isinstance(snapshot_payload, dict) and "records" in snapshot_payload:
            raw_records = [
                ResolverRecord.model_validate(item) for item in snapshot_payload["records"]
            ]
            snapshot_version = snapshot_payload.get(
                "snapshot_version", request.resolver_snapshot_version
            )
            if "checksum" in snapshot_payload:
                snapshot = ResolverSnapshot.model_validate(snapshot_payload).verify()
            else:
                snapshot = ResolverSnapshot.from_records(
                    raw_records,
                    snapshot_version=snapshot_version,
                )
        else:
            raw_records = (
                snapshot_payload.get("records", snapshot_payload)
                if isinstance(snapshot_payload, dict)
                else snapshot_payload
            )
            snapshot = ResolverSnapshot.from_records(
                [ResolverRecord.model_validate(item) for item in raw_records],
                snapshot_version=request.resolver_snapshot_version,
            )
        if snapshot.snapshot_version != request.resolver_snapshot_version:
            raise typer.BadParameter(
                "snapshot version does not match AuditInvocationRequest.resolver_snapshot_version"
            )
        snapshots.save(snapshot)
    snapshot_present = snapshots.load(request.resolver_snapshot_version) is not None
    resolver = SnapshotResolverAdapter.from_store(
        store,
        snapshot_version=request.resolver_snapshot_version,
        available=snapshot_present,
    )
    evidence_view_payload = payload.get("evidence_view")
    if evidence_view_payload is not None:
        evidence_view = BoundedEvidenceView.model_validate(evidence_view_payload)
    else:
        evidence_ids = [
            evidence_id
            for claim in request.claims
            for evidence_id in claim.evidence_ids
        ] + [
            evidence_id
            for citation in request.citations
            for evidence_id in citation.evidence_ids
        ]
        evidence_view = read_bounded_evidence_view(store, request.project_id, evidence_ids)
    report = AuditRuntime(store, resolver).invoke(request, evidence_view=evidence_view)
    _echo(report)


@app.command("add-evidence")
def add_evidence(
    project_id: Annotated[str, typer.Argument()],
    title: Annotated[str, typer.Option("--title")],
    claim: Annotated[str, typer.Option("--claim")],
    source: Annotated[str, typer.Option("--source")],
    evidence_type: Annotated[EvidenceType, typer.Option("--type")] = EvidenceType.HUMAN,
    grade: Annotated[EvidenceGrade, typer.Option("--grade")] = EvidenceGrade.E1,
    source_uri: Annotated[str | None, typer.Option("--uri")] = None,
    locator: Annotated[str | None, typer.Option("--locator")] = None,
) -> None:
    """Register a locatable evidence item without exposing credentials."""
    runtime = AutoResearchApplication()
    try:
        item = EvidenceItem(
            project_id=project_id,
            evidence_type=evidence_type,
            grade=grade,
            title=title,
            claim=claim,
            source_uri=source_uri,
            locator=locator,
            independent_source=source,
        )
        _echo(runtime.add_evidence(item))
    finally:
        runtime.close()


@app.command("search-knowledge")
def search_knowledge(
    query: Annotated[str, typer.Argument()],
    partitions: Annotated[
        str,
        typer.Option("--partitions", help="Comma-separated partition names"),
    ] = "papers,knowledge,experiences",
    level: Annotated[int, typer.Option("--level", min=1, max=2)] = 1,
    require_evidence: Annotated[bool, typer.Option("--require-evidence")] = False,
) -> None:
    """Run partition-aware lexical or lexical+graph retrieval."""
    selected = [
        KnowledgePartition(value.strip()) for value in partitions.split(",") if value.strip()
    ]
    runtime = AutoResearchApplication()
    try:
        _echo(
            [
                hit.model_dump(mode="json")
                for hit in runtime.knowledge.retrieve(
                    query,
                    partitions=selected,
                    level=level,
                    require_evidence=require_evidence,
                )
            ]
        )
    finally:
        runtime.close()


@app.command("ask-paper")
def ask_paper(
    paper_id: Annotated[str, typer.Argument()],
    question: Annotated[str, typer.Option("--question")],
) -> None:
    """Ask the reader Agent using only supplied paper text and locators."""
    runtime = AutoResearchApplication()
    try:
        _echo(runtime.answer_paper(paper_id, question))
    finally:
        runtime.close()


@app.command("revise-manuscript")
def revise_manuscript(
    manuscript_id: Annotated[str, typer.Argument()],
    instructions: Annotated[str, typer.Option("--instructions")],
    mode: Annotated[str, typer.Option("--mode")] = "revise",
) -> None:
    """Create a non-release-ready revision while preserving evidence IDs."""
    runtime = AutoResearchApplication()
    try:
        _echo(
            runtime.revise_manuscript(
                manuscript_id,
                ManuscriptRevisionRequest(instructions=instructions, mode=mode),
            )
        )
    finally:
        runtime.close()


@app.command("propose-evolution")
def propose_evolution(
    project_id: Annotated[str, typer.Argument()],
    problem: Annotated[str, typer.Option("--problem")],
    change: Annotated[str, typer.Option("--change")],
    benefit: Annotated[str, typer.Option("--benefit")],
    risk: Annotated[list[str] | None, typer.Option("--risk")] = None,
    evidence_id: Annotated[list[str] | None, typer.Option("--evidence-id")] = None,
) -> None:
    """Create a proposal only; this command never changes policy or source code."""
    runtime = AutoResearchApplication()
    try:
        _echo(
            runtime.propose_evolution(
                EvolutionProposal(
                    project_id=project_id,
                    problem=problem,
                    proposed_change=change,
                    expected_benefit=benefit,
                    risks=risk or [],
                    evidence_ids=evidence_id or [],
                )
            )
        )
    finally:
        runtime.close()


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8010,
) -> None:
    """Serve the local FastAPI boundary. Remote exposure is not enabled by default."""
    from autoresearch.api import create_api

    runtime = AutoResearchApplication()
    uvicorn.run(create_api(runtime), host=host, port=port)


if __name__ == "__main__":
    app()
