#!/usr/bin/env python
"""Discriminating-power probe for M08-01 (K1 ``RunManifest``).

Method (``docs/process/DISCRIMINATING-POWER.md``)
------------------------------------------------
Build a probe tree from the base commit **without** this package's changes, copy
in only the new test file, and run it under several probe variants:

``P0-nomodule``   the true pre-implementation baseline: no ``run_manifest`` at all
``P1-shim``       symbol-only shim: the K1 symbol exists, with no validators and
                  no helpers ("只补符号、不改行为")
``M1..M4``        mutation probes: the real module with exactly one guard removed
                  or inverted, to attribute each negative case to the guard it targets

Failures are classified as
**判据型** (``DID NOT RAISE`` / ``AssertionError`` -- the rule really did not hold)
or **符号型** (``AttributeError`` / ``KeyError`` / ``ImportError`` / ``TypeError``
-- only proves the symbol exists), and the classification is printed per case.

Usage
-----
    python tests/fixtures/run_manifest/probe_discriminating_power.py [--base 8dd8780]

The probe tree is created under a temporary directory and is never committed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TEST_REL = "tests/test_run_manifest.py"
MODULE_REL = "src/autoresearch/run_manifest.py"
SHIM_REL = "tests/_l05_probe_shim.py"

# --- P1 shim: symbols only, no validators, no helpers ------------------------

SHIM_SOURCE = '''\
"""Probe-only shim: the K1 symbol exists, with no validators and no helpers."""

from __future__ import annotations

import sys
import types
from datetime import datetime
from typing import Any

from pydantic import BaseModel

import autoresearch

_module = types.ModuleType("autoresearch.run_manifest")


class RunManifest(BaseModel):
    run_id: str = ""
    project_id: str = ""
    work_package_id: str = ""
    code_revision: str = ""
    data_refs: list[str] = []
    environment: dict[str, str] = {}
    parameters: dict[str, Any] = {}
    seeds: list[int] = []
    command: list[str] = []
    exit_code: int | None = None
    output_hashes: dict[str, str] = {}
    rerun_of: str | None = None
    created_at: datetime | None = None


_module.RunManifest = RunManifest
autoresearch.run_manifest = _module
sys.modules["autoresearch.run_manifest"] = _module
'''

# --- Mutation probes: one guard removed or inverted each ---------------------

MUTATIONS: dict[str, list[tuple[str, str]]] = {
    # M1 -- K1-1 not enforced: the field accepts a shell string and the guard is off.
    "M1-command-shell-string-accepted": [
        (r"\n    command: list\[str\]\n", "\n    command: str | list[str]\n"),
        (
            r'        if isinstance\(value, str\):\n'
            r'            raise ValueError\(\n'
            r'                "command must be an argv list \(K1-1\); "',
            '        if False:\n'
            r'            raise ValueError('
            "\n"
            r'                "command must be an argv list (K1-1); "',
        ),
    ],
    # M2 -- K1-2 not enforced: an empty seed list is legal.
    "M2-empty-seeds-accepted": [
        (r"    seeds: list\[int\] = Field\(min_length=1\)\n", "    seeds: list[int]\n"),
    ],
    # M3 -- K1-3 collapse: "not executed" is rewritten into a successful exit code.
    "M3-none-coerced-to-zero": [
        (
            r"        if value is None:\n            return None\n",
            r"        if value is None:\n            return 0\n",
        ),
    ],
    # M4 -- K1-3 inverse collapse: a failed run is rewritten into "never ran".
    "M4-nonzero-coerced-to-none": [
        (
            r"        return value\n\n    @property\n    def executed",
            "        return None if value not in (0, None) else value\n\n    @property\n"
            "    def executed",
        ),
    ],
}

JUDGEMENTAL = ("DID NOT RAISE", "AssertionError", "assert ")
SYMBOLIC = ("AttributeError", "ImportError", "ModuleNotFoundError", "KeyError", "TypeError")


def classify(line: str) -> str:
    if any(marker in line for marker in SYMBOLIC):
        return "symbol-missing"
    if any(marker in line for marker in JUDGEMENTAL):
        return "criterion"
    return "unknown"


def parse_failing_sections(output: str) -> dict[str, str]:
    """Map each failing test (or collection error) to the ``E `` lines pytest printed."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    header = re.compile(r"^_+ (.+?) _+$")
    for line in output.splitlines():
        matched = header.match(line.strip())
        if matched:
            # Node ids may contain spaces, so never tokenise the header name.
            raw = matched.group(1).strip()
            current = "<collection>" if raw.startswith("ERROR collecting") else raw
            sections.setdefault(current, [])
            continue
        if current is not None and line.startswith("E "):
            sections[current].append(line[2:].strip())
    return {name: " | ".join(lines) for name, lines in sections.items() if lines}


def run_pytest(tree: Path, plugin: str | None = None) -> dict[str, object]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(tree / "src"), str(tree / "tests")])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        TEST_REL,
        "-q",
        "-o",
        "addopts=",
        "-W",
        "error",
        "--tb=short",
        "-rf",
        "-p",
        "no:cacheprovider",
    ]
    if plugin:
        cmd += ["-p", plugin]
    proc = subprocess.run(cmd, cwd=tree, env=env, capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    summary = next(
        (ln for ln in reversed(out.splitlines()) if re.search(r"\d+ (passed|failed|error)", ln)),
        "(no summary line)",
    )
    sections = parse_failing_sections(out)
    failures: dict[str, str] = {}
    for ln in out.splitlines():
        # Parametrised node ids may contain spaces, so do not use \S+ here.
        match = re.match(r"FAILED (.+?)(?: - (.*))?$", ln)
        if match:
            test = match.group(1).split("::")[-1]
            failures[test] = sections.get(test) or (match.group(2) or "").strip()
    collection_error = bool(re.search(r"^ERROR tests/", out, re.M)) or "<collection>" in sections
    if collection_error:
        failures = {
            "<collection>": sections.get("<collection>") or "(collection error, no detail line)"
        }
    return {
        "summary": summary.strip(),
        "exit_code": proc.returncode,
        "failures": failures,
        "collection_error": collection_error,
    }


def build_tree(base: str, workdir: Path) -> Path:
    tree = workdir / "tree"
    tree.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "archive", base], cwd=REPO, capture_output=True, check=True
    )
    subprocess.run(["tar", "-x", "-C", str(tree)], input=archive.stdout, check=True)
    shutil.copy2(REPO / TEST_REL, tree / TEST_REL)
    return tree


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="8dd8780", help="base commit to probe against")
    parser.add_argument("--workdir", default=None, help="probe working directory")
    args = parser.parse_args()

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="l05-probe-"))
    print(f"probe workdir : {workdir}")
    print(f"base commit   : {args.base}")
    print(f"python        : {sys.executable}")

    reference = build_tree(args.base, workdir)

    variants: list[tuple[str, Path, str | None, str]] = []

    # P0: true baseline -- no module at all.
    p0 = workdir / "P0-nomodule"
    shutil.copytree(reference, p0)
    variants.append(("P0-nomodule", p0, None, "pre-implementation baseline (no module)"))

    # P1: symbol-only shim (no validators, no helpers).
    p1 = workdir / "P1-shim"
    shutil.copytree(reference, p1)
    (p1 / SHIM_REL).write_text(SHIM_SOURCE, encoding="utf-8")
    variants.append(("P1-shim", p1, "_l05_probe_shim", "symbols only; no validators, no helpers"))

    # M1..M4: the real module with exactly one guard removed/inverted.
    real_module = (REPO / MODULE_REL).read_text(encoding="utf-8")
    for name, mutations in MUTATIONS.items():
        mutated = real_module
        for pattern, repl in mutations:
            mutated, count = re.subn(pattern, repl, mutated)
            if count != 1:
                raise SystemExit(f"mutation {name}: pattern matched {count} times: {pattern!r}")
        assert mutated != real_module, name
        tree = workdir / name
        shutil.copytree(reference, tree)
        (tree / MODULE_REL).write_text(mutated, encoding="utf-8")
        variants.append((name, tree, None, "real module with one guard removed/inverted"))

    report = {}
    for name, tree, plugin, description in variants:
        result = run_pytest(tree, plugin)
        classified = {case: classify(detail) for case, detail in result["failures"].items()}
        report[name] = {
            "description": description,
            "summary": result["summary"],
            "exit_code": result["exit_code"],
            "collection_error": result["collection_error"],
            "failures": result["failures"],
            "classification": classified,
        }
        print(f"\n=== {name}: {description}")
        print(f"    {result['summary']}  (exit {result['exit_code']})")
        for case, detail in sorted(result["failures"].items()):
            print(f"    [{classified[case]:>14}] {case}: {detail[:110]}")

    print("\n=== matrix (rows = probes, cells = the four negative cases)")
    header = f"{'probe':<34}{'N-1':<14}{'N-2':<14}{'N-3':<14}{'N-4':<14}"
    print(header)
    targets = {
        "N-1": "test_k1_1_shell_string_command_is_rejected",
        "N-2": "test_k1_2_empty_seeds_is_rejected",
        "N-3": "test_k1_3_unexecuted_none_is_never_coerced_to_zero",
        "N-4": "test_k1_3_non_zero_exit_code_is_accepted_as_an_executed_run",
    }
    for name, _tree, _plugin, _desc in variants:
        if report[name]["collection_error"]:
            print(f"{name:<34}" + "".join(f"{'not-run(symbol)':<14}" for _ in targets))
            continue
        cells = []
        for test_name in targets.values():
            hit = [
                (n, kind)
                for n, kind in report[name]["classification"].items()
                if n.startswith(test_name)
            ]
            cells.append(hit[0][1] if hit else "pass")
        print(f"{name:<34}" + "".join(f"{cell:<14}" for cell in cells))

    out = workdir / "probe-report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nreport: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
