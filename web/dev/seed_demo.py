#!/usr/bin/env python
"""Seed the M13 panels with **real** data and capture the real API responses.

Why a live server instead of calling Python directly: the panels must be driven by
what the 24 HTTP endpoints actually return. This script starts the real
``autoresearch serve`` process (offline provider -- zero cost, no network),
drives it over HTTP, and writes every response it captures to disk so the
screenshots can be rebuilt offline and inspected byte for byte.

Usage
-----
    python web/dev/seed_demo.py [--out docs/tasks/M13-ui/tasks/screenshots/raw-api]

Writes
------
    <out>/<project_id>/<name>.json     one file per captured GET response
    <out>/_writes.json                 the M13-07 write attempts and their results
    <out>/_summary.json                project ids, run ids, endpoint inventory
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from snapshot_scrub import scrub_absolute_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "docs" / "tasks" / "M13-ui" / "tasks" / "screenshots" / "raw-api"

EVIDENCE_BY_GRADE = [
    ("human", "H3", "Human expert assessment of the candidate method",
     "A named human expert judged the candidate method reproducible.",
     "human-expert:review-board", "review board minutes, item 4"),
    ("experiment", "E3", "Closed-loop rerun receipt for the candidate method",
     "The candidate method reproduced its reported metric on a rerun.",
     "experiment:local-rerun", "run receipt 2026-09-15/rerun"),
    ("paper", "E2", "Peer-reviewed baseline comparison",
     "The cited baseline reports the metric the candidate claims to improve.",
     "paper:baseline-2022", "baseline paper, table 2"),
    ("knowledge", "E1", "Internal knowledge page on evidence grading",
     "Internal knowledge records the E0-H3 grading scale used by the gate.",
     "knowledge:grading-scale", "knowledge page, section 3"),
]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Client:
    def __init__(self, base: str) -> None:
        self.base = base
        self.log: list[dict[str, Any]] = []

    def request(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, method=method
        )
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as response:  # noqa: S310 - localhost only
                status = int(response.status)
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        self.log.append({"method": method, "path": path, "status": status})
        return status, payload

    def get(self, path: str) -> Any:
        status, payload = self.request("GET", path)
        assert status == 200, (path, status, payload)
        return payload

    def post(self, path: str, body: Any, expect: int) -> Any:
        status, payload = self.request("POST", path, body)
        assert status == expect, (path, status, payload)
        return payload


def wait_for_health(client: Client, deadline: float = 40.0) -> dict[str, Any]:
    started = time.time()
    while time.time() - started < deadline:
        try:
            status, payload = client.request("GET", "/health")
            if status == 200:
                return payload
        except OSError:
            pass
        time.sleep(0.35)
    raise SystemExit("server did not become healthy in time")


def build_scenario(client: Client) -> dict[str, Any]:
    """Drive the real endpoints. Every call below is one of the 24 routes."""
    summary: dict[str, Any] = {"projects": {}, "writes": []}

    # --- project A: literature present, reaches a gate decision --------------
    client.post("/projects", {
        "project_id": "litalpha",
        "title": "Evidence-graded literature screening",
        "idea": "Grade the evidence behind an automated literature review claim.",
    }, 201)
    seeds = [
        {
            "project_id": "litalpha",
            "title": "Retrieval Augmented Research Agents",
            "abstract": "We study RAG for literature review automation.",
            "authors": ["A. Researcher"],
            "year": 2024,
            "doi": "10.1000/lit-a",
            "url": "https://example.org/lit-a",
            "source": "user_seed",
        },
        {
            "project_id": "litalpha",
            "title": "Evidence-Graded Claim Verification",
            "abstract": "Grading evidence for claim support in automated review.",
            "authors": ["B. Author"],
            "year": 2023,
            "doi": "10.1000/lit-b",
            "url": "https://example.org/lit-b",
            "source": "user_seed",
        },
    ]
    status, run = client.request("POST", "/runs", {
        "project_id": "litalpha",
        "idea": "Grade the evidence behind an automated literature review claim.",
        "seed_papers": seeds,
        "request_release": True,
    })
    assert status == 201, (status, run)
    summary["projects"]["litalpha"] = {"run_id": run["run_id"]}

    # a human-graded item, so the approval panel has a real H3 to show
    added = []
    for evidence_type, grade, title, claim, source, locator in EVIDENCE_BY_GRADE:
        status, item = client.request("POST", "/evidence", {
            "project_id": "litalpha",
            "evidence_type": evidence_type,
            "grade": grade,
            "title": title,
            "claim": claim,
            "independent_source": source,
            "locator": locator,
            "source_uri": f"https://example.org/{grade.lower()}",
        })
        assert status == 201, (status, item)
        added.append(item["evidence_id"])
    summary["projects"]["litalpha"]["added_evidence"] = added

    packages = client.get("/projects/litalpha/work-packages")
    if packages:
        # one package blocked -> a real blocker in the project panel (N-2)
        status, blocked = client.request(
            "PATCH", f"/work-packages/{packages[0]['work_package_id']}",
            {"status": "blocked", "evidence_ids": [], "note": "waiting on hardware access"},
        )
        summary["writes"].append({
            "call": f"PATCH /work-packages/{packages[0]['work_package_id']}",
            "status": status, "response": blocked,
        })
        if len(packages) > 1:
            status, done = client.request(
                "PATCH", f"/work-packages/{packages[1]['work_package_id']}",
                {"status": "completed", "evidence_ids": [added[0]], "note": "evidence attached"},
            )
            summary["writes"].append({
                "call": f"PATCH /work-packages/{packages[1]['work_package_id']}",
                "status": status, "response": done,
            })

    # --- project B: created, never run -> every section must declare a reason --
    client.post("/projects", {
        "project_id": "bare",
        "title": "Created but never run",
        "idea": "Shows what the panels look like when there is no run at all.",
    }, 201)
    summary["projects"]["bare"] = {"run_id": None}

    # --- project C: run without seeds -> blocked with no evidence coverage -----
    client.post("/projects", {
        "project_id": "nolit",
        "title": "Run with no seed papers",
        "idea": "The pipeline must block instead of inventing paper records.",
    }, 201)
    run_c = client.post("/runs", {
        "project_id": "nolit",
        "idea": "Run with no seed papers, so the pipeline blocks instead of inventing.",
        "seed_papers": [],
        "request_release": False,
    }, 201)
    summary["projects"]["nolit"] = {"run_id": run_c["run_id"]}

    return summary


def capture_reads(client: Client, summary: dict[str, Any], out: Path) -> None:
    for project_id in summary["projects"]:
        target = out / project_id
        target.mkdir(parents=True, exist_ok=True)
        audit = client.get(f"/projects/{project_id}/audit-events")
        reads: dict[str, Any] = {
            "project": client.get(f"/projects/{project_id}"),
            "project_evidence_all": client.get(
                f"/projects/{project_id}/evidence?valid_only=false"
            ),
            "project_evidence_valid_only": client.get(
                f"/projects/{project_id}/evidence"
            ),
            "project_work_packages": client.get(f"/projects/{project_id}/work-packages"),
            "audit_events": audit,
        }
        run_id = summary["projects"][project_id].get("run_id")
        if run_id is None:
            run_id = next(
                (
                    event["payload"]["run_id"]
                    for event in audit
                    if event["event_type"] == "run.started"
                ),
                None,
            )
        if run_id:
            reads["run"] = client.get(f"/runs/{run_id}")
        for name, payload in reads.items():
            (target / f"{name}.json").write_text(
                json.dumps(
                    scrub_absolute_paths(payload, REPO_ROOT),
                    indent=1,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )


def capture_writes(client: Client, summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Exercise the M13-07 write endpoints and record exactly what came back."""
    writes: list[dict[str, Any]] = []
    project = summary["projects"]["litalpha"]
    run_id = project["run_id"]

    # 1. approve/reject a pending human interrupt. If the run never reached a
    #    release gate there is no interrupt, and the guard must say so -- that
    #    failure is itself evidence, so it is recorded rather than hidden.
    for approval in (True, False):
        status, payload = client.request(
            "POST", f"/runs/{run_id}/resume",
            {"approval": approval, "reviewer": "l08-demo", "note": "panel M13-07"},
        )
        writes.append({
            "purpose": "M13-07 approve/reject",
            "call": f"POST /runs/{run_id}/resume",
            "body": {"approval": approval, "reviewer": "l08-demo", "note": "panel M13-07"},
            "status": status,
            "response": payload,
        })
        if status != 200:
            break

    # 2. retract (打回) an evidence item -- the reachable path in this package.
    target = project["added_evidence"][-1]
    status, payload = client.request(
        "POST", f"/evidence/{target}/invalidate",
        {"reason": "panel M13-07 retraction: source could not be re-verified",
         "actor": "l08-demo"},
    )
    writes.append({
        "purpose": "M13-07 retract evidence",
        "call": f"POST /evidence/{target}/invalidate",
        "body": {"reason": "panel M13-07 retraction: source could not be re-verified",
                 "actor": "l08-demo"},
        "status": status,
        "response": payload,
    })

    # 3. prove the retraction actually landed in the audit chain.
    audit = client.get("/projects/litalpha/audit-events")
    writes.append({
        "purpose": "audit confirmation after retraction",
        "call": "GET /projects/litalpha/audit-events",
        "retraction_events": [
            event for event in audit if event["event_type"] == "evidence.invalidated"
        ],
        "event_type_histogram": _histogram(audit),
    })
    return writes


def _histogram(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        key = event.get("event_type", "?")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--data-dir", type=Path, default=None)
    args = parser.parse_args()

    out: Path = args.out.resolve()
    data_dir: Path = (args.data_dir or (REPO_ROOT / "var" / "l08-demo" / "runtime")).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if data_dir.exists():
        import shutil

        shutil.rmtree(data_dir)
    (data_dir / "projects").mkdir(parents=True, exist_ok=True)

    port = free_port()
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "LLM_PROVIDER": "offline",
        "AUTORESEARCH_NETWORK_ENABLED": "false",
        "AUTORESEARCH_DATA_DIR": str(data_dir),
        "AUTORESEARCH_DB_PATH": str(data_dir / "autoresearch.sqlite3"),
        "AUTORESEARCH_CHECKPOINT_PATH": str(data_dir / "checkpoints.sqlite3"),
        "AUTORESEARCH_PROJECTS_DIR": str(data_dir / "projects"),
        "AUTORESEARCH_TEMPLATE_DIR": str(REPO_ROOT / "paper-projects" / "_template"),
    })

    print(f"[seed] starting autoresearch serve on 127.0.0.1:{port}", flush=True)
    server = subprocess.Popen(
        [sys.executable, "-m", "autoresearch", "serve", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(REPO_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    client = Client(f"http://127.0.0.1:{port}")
    try:
        doctor = wait_for_health(client)
        print(f"[seed] healthy: version={doctor.get('version')} "
              f"agents={doctor.get('agent_count')}", flush=True)

        summary = build_scenario(client)
        summary["doctor"] = doctor
        write_attempts = capture_writes(client, summary)
        capture_reads(client, summary, out)

        (out / "_writes.json").write_text(
            json.dumps(
                scrub_absolute_paths(write_attempts, REPO_ROOT),
                indent=1,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        summary["writes"] = write_attempts
        summary["http_log"] = client.log
        (out / "_summary.json").write_text(
            json.dumps(
                scrub_absolute_paths(summary, REPO_ROOT),
                indent=1,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        print(f"[seed] captured {len(client.log)} HTTP calls", flush=True)
        print("[seed] write attempts:", flush=True)
        for attempt in write_attempts:
            print(f"   {attempt.get('status', '-')}  {attempt['call']}"
                  f"   ({attempt['purpose']})", flush=True)
        print(f"[seed] raw responses -> {out}", flush=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
