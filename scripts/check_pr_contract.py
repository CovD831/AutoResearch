#!/usr/bin/env python3
"""Deterministic PR contract checks for AutoResearch."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


FORBIDDEN_GENERATED_PREFIXES = ("var/",)


def run(*args: str) -> str:
    result = subprocess.run(args, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "command failed")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    args = parser.parse_args()

    try:
        changed = [line for line in run("git", "diff", "--name-only", f"{args.base}...HEAD").splitlines() if line]
    except RuntimeError as error:
        print(f"PR contract check failed: {error}", file=sys.stderr)
        return 1

    if any(path.startswith(FORBIDDEN_GENERATED_PREFIXES) for path in changed):
        print("PR contract check failed: generated runtime state under var/ is not allowed")
        return 1

    task_ledgers = [path for path in changed if path.startswith(".ai-team/tasks/") and path.endswith(".md")]
    product_changes = [
        path
        for path in changed
        if not path.startswith((".ai-team/", ".github/", "docs/", "scripts/"))
    ]
    if product_changes and not task_ledgers and ".ai-team/TASK.md" not in changed:
        print("PR contract check failed: product changes need a task-local ledger or .ai-team/TASK.md")
        return 1

    for task_path in task_ledgers:
        result = subprocess.run(
            ["node", ".ai-team/check.mjs", "--task", task_path, "--base", args.base],
            check=False,
            text=True,
        )
        if result.returncode != 0:
            return result.returncode

    print(f"PR contract check passed: {len(changed)} changed paths; {len(task_ledgers)} task ledger(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
