#!/usr/bin/env python3
"""Reproduce the L-01 (M01-CONTEXT) discriminating-power evidence.

Two levels, both recorded by the L3 §5:

  A. symbol-only shim -> measure that the new tests fail on a
     "symbols + field declarations only, no validators, no method bodies"
     baseline (the kickoff convention's prescribed way to obtain judgment-type
     failures for a brand new module).
  B. behaviour rollback mutations -> revert one guard at a time from the REAL
     implementation and show the matching test fails with a judgment-type error.

Usage (from the repository root, or anywhere -- paths are resolved relative to
this file):

    python docs/tasks/M01-context/evidence/discriminating_power.py

The script never commits anything. Every file it touches is restored before the
process exits, including on failure.
"""

from __future__ import annotations

import re
import subprocess
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SRC = REPO / "src" / "autoresearch"
CONTEXT = SRC / "context_assembler.py"
MIGRATION = SRC / "migration.py"
TARGETS = [CONTEXT, MIGRATION]
TEST_FILES = [
    "tests/test_m01_context_assembler.py",
    "tests/test_m01_migration.py",
]


def run_pytest(*args: str) -> str:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *args,
            "-q",
            "-o",
            "addopts=",
            "-W",
            "error",
            "--tb=line",
        ],
        cwd=REPO,
        # Override the env instead of replacing it: ``env={"PATH": ...}``
        # alone would drop PYTHONIOENCODING, which Python on Windows
        # inherits from the spawn shell and uses to decode stdout.
        # Forcing utf-8 here plus the ``encoding`` kwarg below is the
        # belt-and-braces that lets the script read and write Chinese
        # source on either platform.
        env={**os.environ, "PYTHONPATH": "src", "PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.stdout + proc.stderr


_PASSED = re.compile(r"\b(\d+) passed\b")
#: ``--tb=line`` prints one ``<file>:<line>: <reason>`` line per failure.
_LOCATION = re.compile(r"^\S+\.py:\d+: (?P<reason>.+)$")


def classify(output: str) -> dict[str, int]:
    """Count distinct failing tests per reason (one location line each)."""

    counts: dict[str, int] = {}
    for line in output.splitlines():
        match = _LOCATION.match(line.strip())
        if match is None:
            continue
        reason = match.group("reason")
        if reason.startswith("Failed: DID NOT RAISE"):
            key = "Failed: DID NOT RAISE (strong: names the missing guarantee)"
        elif reason.startswith("NotImplementedError"):
            key = "NotImplementedError (weak: API reached, body absent)"
        elif "ValidationError" in reason:
            key = (
                "ValidationError from the shim's own field declarations "
                "(binds to the extension being optional)"
            )
        else:
            key = reason.split(":", 1)[0]
        counts[key] = counts.get(key, 0) + 1
    return counts


def outcome(output: str) -> str:
    match = _PASSED.search(output)
    if match and " failed" not in output and " error" not in output:
        return f"PASS ({match.group(1)} passed)"
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("E ") and ("Error" in stripped or "Failed" in stripped):
            return stripped[2:].strip()
    first = next((line for line in output.splitlines() if "Error" in line), "FAIL (no reason)")
    return first.strip()[:120]


class Guard:
    """Restores the two source files on exit, whatever happens."""

    def __init__(self) -> None:
        self._originals = {path: path.read_text(encoding="utf-8") for path in TARGETS}

    def restore(self) -> None:
        for path, text in self._originals.items():
            path.write_text(text, encoding="utf-8")

    def __enter__(self) -> Guard:
        return self

    def __exit__(self, *exc: object) -> None:
        self.restore()


def shim_probe() -> None:
    print("== A. symbol-only shim ==")
    summary = run_pytest(*TEST_FILES)
    real = outcome(summary)
    print(f"  real implementation : {real}")
    for name in ("context_assembler.shim.py", "migration.shim.py"):
        (SRC / name.replace(".shim.py", ".py")).write_text((HERE / name).read_text(encoding="utf-8"), encoding="utf-8")
    shim = run_pytest(*TEST_FILES)
    for line in shim.splitlines():
        if "passed" in line or "failed" in line:
            print(f"  shim run            : {line.strip()}")
    breakdown = classify(shim)
    for reason, count in sorted(breakdown.items(), key=lambda item: -item[1]):
        print(f"      {count:>3}  {reason}")
    print(f"  distinct failures classified: {sum(breakdown.values())}")
    print(f"  ImportError/AttributeError count: {shim.count('ImportError') + shim.count('AttributeError')}")


def mutations() -> None:
    print("\n== B. behaviour rollback mutations ==")
    cases = [
        (
            "M1 remove the K5-2 validator",
            CONTEXT,
            "if self.truncated and not self.dropped_refs:",
            "if False:",
            "tests/test_m01_context_assembler.py::test_truncated_slice_must_record_dropped_refs",
        ),
        (
            "M2 drop the RefId type/length guard",
            CONTEXT,
            "RefId = Annotated[\n    str,\n    StringConstraints(strict=True, min_length=1, max_length=MAX_REF_ID_LENGTH),\n]",
            "RefId = str",
            "tests/test_m01_context_assembler.py::test_refs_reject_non_string_and_over_long_ids",
        ),
        (
            "M3 treat unmeasured token cost as 0",
            CONTEXT,
            """            for item in candidates:
                if item.tokens is None:
                    dropped.append(item.ref_id)
                    continue
                if item_ceiling is not None and len(included) >= item_ceiling:
                    dropped.append(item.ref_id)
                    continue
                if used + item.tokens > ceiling:
                    dropped.append(item.ref_id)
                    continue
                included.append(item)
                used += item.tokens""",
            """            for item in candidates:
                cost = item.tokens if item.tokens is not None else 0
                if item_ceiling is not None and len(included) >= item_ceiling:
                    dropped.append(item.ref_id)
                    continue
                if used + cost > ceiling:
                    dropped.append(item.ref_id)
                    continue
                included.append(item)
                used += cost""",
            "tests/test_m01_context_assembler.py::test_unmeasured_token_cost_is_not_treated_as_free",
        ),
        (
            "M4 stop recording dropped refs (K5-1/N-1)",
            CONTEXT,
            "                    truncated=bool(dropped),\n                    dropped_refs=dropped,",
            "                    truncated=bool(dropped),\n                    dropped_refs=[],",
            "tests/test_m01_context_assembler.py::test_over_budget_falls_back_to_splitting_and_records_dropped_refs",
        ),
        (
            "M5 ignore the per-kind token tier",
            CONTEXT,
            "            ceiling = min(budget.kind_token_ceiling(kind), remaining)",
            "            ceiling = remaining",
            "tests/test_m01_context_assembler.py::test_per_kind_token_tier_is_honoured",
        ),
        (
            "M6 give unknown_field_policy a silent default",
            MIGRATION,
            '    unknown_field_policy: Literal["reject", "preserve"]\n',
            '    unknown_field_policy: Literal["reject", "preserve"] = "preserve"\n',
            "tests/test_m01_migration.py::test_unknown_field_policy_must_be_stated",
        ),
        (
            "M7 remove the to_version strict-increase check (K6-3)",
            MIGRATION,
            "        if version_key(self.to_version) <= version_key(self.from_version):",
            "        if False:",
            "tests/test_m01_migration.py::test_to_version_must_strictly_increase",
        ),
        (
            "M8 make reject policy fail open",
            MIGRATION,
            "        if unknown and self.unknown_field_policy == UnknownFieldPolicy.REJECT:",
            "        if False:",
            "tests/test_m01_migration.py::test_reject_policy_raises_on_an_unknown_field",
        ),
        (
            "M9 drop the state_version bridge guard",
            MIGRATION,
            "    if isinstance(version, bool) or not isinstance(version, int):",
            "    if False:",
            "tests/test_m01_migration.py::test_bridge_rejects_objects_without_an_integer_version",
        ),
        (
            "M10 ignore the output reserve (reserved_ratio)",
            CONTEXT,
            "        return max(0, int(self.max_tokens * (1.0 - self.reserved_ratio)))",
            "        return self.max_tokens",
            "tests/test_m01_context_assembler.py::test_output_reserve_excludes_an_item_by_naming_it",
        ),
        (
            "M11 make the per-kind fallback 0 instead of the global budget",
            CONTEXT,
            "        return (self.max_tokens_per_kind or {}).get(kind, self.usable_tokens)",
            "        return (self.max_tokens_per_kind or {}).get(kind, 0)",
            "tests/test_m01_context_assembler.py::test_max_tokens_per_kind_is_optional_and_none_is_k5_equivalent",
        ),
    ]
    hits = 0
    for name, target, old, new, test in cases:
        original = target.read_text(encoding="utf-8")
        if old not in original:
            print(f"  {name}: SKIPPED (anchor not found)")
            continue
        target.write_text(original.replace(old, new, 1), encoding="utf-8")
        result = outcome(run_pytest(test))
        target.write_text(original, encoding="utf-8")
        judgment = "ImportError" not in result and "AttributeError" not in result
        hits += 1 if (judgment and result != "PASS") else 0
        print(f"  {name}\n      {test.rsplit('::', 1)[1]}: {result}")
    print(f"  judgment-type failures: {hits}/{len(cases)}")


def main() -> int:
    with Guard() as guard:
        shim_probe()
        guard.restore()
        mutations()
    restored = outcome(run_pytest(*TEST_FILES))
    print(f"\nrestored, focused suite: {restored}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
