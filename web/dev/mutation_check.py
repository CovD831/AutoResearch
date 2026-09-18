#!/usr/bin/env python
"""Discriminating-power check: do the K14 tests actually catch a broken contract?

A brand-new module makes the usual "run the new tests on the pre-fix baseline"
trick useless: every test fails there for the trivial reason that the module does
not exist yet (a *symbol-missing* failure, which proves nothing). So instead each
mutation below breaks one K14 invariant **substantively** while leaving every
symbol in place, and the question becomes: which test catches it?

A mutation that no test catches is a hole in the suite. A mutation caught only by
a *construction* error (pydantic refusing to build the object) is weaker evidence
than one caught by an assertion about behaviour, and the report says which is
which.

The real module is backed up and restored in a ``finally`` block; nothing is left
mutated.

Usage
-----
    python web/dev/mutation_check.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "src" / "autoresearch" / "web_api.py"
WEB_JS = REPO_ROOT / "web" / "app.js"
TEST_FILE = "tests/test_web_panels.py"

#: (id, intent, target file, old, new)
MUTATIONS: tuple[tuple[str, str, Path, str, str], ...] = (
    (
        "M1",
        "K14-3: let a non-verified section pass without a reason",
        MODULE,
        'if not self.verified and not (self.unknown_reason or "").strip():',
        "if False:  # MUTATED",
    ),
    (
        "M2",
        "K14-1: stop rolling a blocked section up to a blocked panel",
        MODULE,
        '    if any(section.verification_state == "blocked" for section in sections):\n'
        '        return "blocked"',
        "    if False:  # MUTATED\n        return \"blocked\"",
    ),
    (
        "M3",
        "N-1: claim 'no blockers' for a project whose run state was never read",
        MODULE,
        "    if state is None:\n        # No ResearchState means the blocker list",
        "    if False:  # MUTATED\n        # No ResearchState means the blocker list",
    ),
    (
        "M4",
        "K14-2: leak evidence claim text into the panel",
        MODULE,
        '            "note": "K14-2: claim/title text is not copied into the panel",',
        '            "note": next((r["claim"] for r in rows if r.get("claim")), ""),',
    ),
    (
        "M5",
        "K14-4 regression: hardcode the tab status dot (the audited defect)",
        WEB_JS,
        '      // Only a state the projection actually carries gets a dot.\n'
        '      if (known[panelId]) syncTabState(panelId, known[panelId]);',
        '      tab.appendChild(el("span", "tab__dot tab__dot--unverified"));  // MUTATED',
    ),
    (
        "M6",
        "K14-4 regression: coerce an unknown verification_state to a real one",
        WEB_JS,
        "    return STATE_LABEL[value] && value !== INVALID_STATE ? value : INVALID_STATE;",
        '    return STATE_LABEL[value] ? value : "unverified";  // MUTATED',
    ),
    (
        # M5 alone is self-healing: renderPanel still calls syncTabState, so the
        # dot is corrected the moment a panel is selected. M7 removes that path
        # instead, reproducing the *observable* defect (selected panel's tab dot
        # disagrees with its own chip) -- which only the rendered-DOM test can see.
        "M7",
        "K14-4 regression: reproduce the audited defect's observable effect",
        WEB_JS,
        "    syncTabState(panelId, projection.verification_state);",
        '    syncTabState(panelId, "unverified");  // MUTATED',
    ),
    (
        # A semantically equivalent hardcoding: no literal `"tab__dot tab__dot--*"`
        # string, so the original fingerprint guard passed it (falsification R4).
        # The Node-based no-browser guard must catch it on behaviour.
        "M8",
        "K14-4 equivalent rewrite: make dotClassFor return a constant",
        WEB_JS,
        "    return TAB_DOT_CLASS[state] || null;",
        '    return "tab__dot--unverified";  // MUTATED',
    ),
    (
        "M9",
        "K14-4 equivalent rewrite: default an unknown state to unverified",
        WEB_JS,
        "    return TAB_DOT_CLASS[state] || null;",
        '    return TAB_DOT_CLASS[state] || "tab__dot--unverified";  // MUTATED',
    ),
)


def run_tests() -> tuple[int, str, list[str]]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    # PATH is preserved so the Node-based no-browser renderer guard can run; if
    # node were missing the guard would skip and the front-end mutations would
    # look "caught" only by the weaker guards.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TEST_FILE, "-q", "-o", "addopts=", "-W", "error"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    output = proc.stdout + proc.stderr
    failed = sorted(
        set(re.findall(r"^FAILED \S+::(\w+)", output, flags=re.MULTILINE))
    )
    return proc.returncode, output, failed


def summary_line(output: str) -> str:
    for line in reversed(output.strip().splitlines()):
        if "passed" in line or "failed" in line or "error" in line:
            return line.strip()
    return "(no summary)"


def main() -> int:
    targets = {MODULE, WEB_JS}
    originals = {path: path.read_text(encoding="utf-8") for path in targets}
    baseline_code, baseline_out, _ = run_tests()
    print(f"baseline            rc={baseline_code}  {summary_line(baseline_out)}")
    if baseline_code != 0:
        print("baseline is not green; refusing to report mutation results")
        print(baseline_out[-2000:])
        return 2

    rows = []
    backup_dir = Path(tempfile.mkdtemp())
    for path in targets:
        shutil.copy2(path, backup_dir / path.name)
    try:
        for mutation_id, intent, target, old, new in MUTATIONS:
            source = originals[target]
            if old not in source:
                print(f"{mutation_id}: anchor not found, skipping  # {intent}")
                rows.append((mutation_id, intent, "ANCHOR-MISSING", []))
                continue
            target.write_text(source.replace(old, new, 1), encoding="utf-8")
            code, out, failed = run_tests()
            caught = code != 0
            print(f"{mutation_id:4s} {'CAUGHT ' if caught else 'MISSED '}"
                  f"rc={code}  {summary_line(out)}  [{target.name}]")
            print(f"      intent: {intent}")
            for name in failed[:6]:
                print(f"      caught by: {name}")
            rows.append((mutation_id, intent, "CAUGHT" if caught else "MISSED", failed))
            target.write_text(source, encoding="utf-8")
    finally:
        for path in targets:
            path.write_text(originals[path], encoding="utf-8")
        shutil.rmtree(backup_dir, ignore_errors=True)

    # prove the restore was exact
    restored = all(path.read_text(encoding="utf-8") == originals[path] for path in targets)
    final_code, final_out, _ = run_tests()
    print(f"\nrestored exactly: {restored} | re-run rc={final_code} "
          f"{summary_line(final_out)}")
    missed = [r for r in rows if r[2] != "CAUGHT"]
    print(f"mutations caught: {len(rows) - len(missed)}/{len(rows)}")
    for row in missed:
        print(f"   MISSED {row[0]}: {row[1]}")
    return 0 if restored and final_code == 0 and not missed else 1


if __name__ == "__main__":
    raise SystemExit(main())
