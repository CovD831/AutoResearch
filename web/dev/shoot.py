#!/usr/bin/env python
"""Screenshot the M13 panel snapshots with a headless browser.

``ui-skeleton-first`` treats the screenshot as a deliverable: without looking at
a real page fed with real data, "the skeleton is done" is an unverified claim.

Uses the already-installed Google Chrome through Playwright's ``channel="chrome"``
so no browser download is needed. Pages are loaded over ``file://`` from the
snapshots produced by ``build_snapshots.py``.

Usage
-----
    python web/dev/shoot.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from snapshot_scrub import scrub_absolute_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SHOTS = REPO_ROOT / "docs" / "tasks" / "M13-ui" / "tasks" / "screenshots"

#: (project, panel, note) -- curated so each image shows something a reader must check.
CURATED: tuple[tuple[str, str, str], ...] = (
    ("litalpha", "project", "rich run: 5 sections verified, blockers BLOCKED"),
    ("litalpha", "evidence", "mixed: 4 verified, 3 unverified (read gaps G-3/G-4/G-5)"),
    ("litalpha", "approval", "M13-07 actions; no pending interrupt -> buttons disabled"),
    ("litalpha", "files", "M13-06 BLOCKED on K11 AccessPolicy (L-09)"),
    ("bare", "project", "N-1: created, never run -> every section UNVERIFIED with a reason"),
    ("nolit", "project", "N-2: run without seeds -> BLOCKED, distinguishable from UNVERIFIED"),
)

#: Synthetic pages. Kept separate and named with a leading underscore so no
#: synthetic image can be mistaken for a real project snapshot.
FIXTURES: tuple[tuple[str, str], ...] = (
    (
        "snapshot-_tabdot-fixture.html",
        "SYNTHETIC: all three tab-dot states are reachable; verified is unreachable "
        "from real data, so this is the only place the third dot can be shown",
    ),
)


def tab_dots(page) -> dict[str, str | None]:
    """The rendered class of every tab status dot, per panel."""
    return page.evaluate(
        """() => {
          const out = {};
          document.querySelectorAll('.tab').forEach((tab) => {
            const dot = tab.querySelector('.tab__dot');
            out[tab.dataset.panel] = dot
              ? (dot.className.match(/tab__dot--(\\w+)/) || [null, null])[1]
              : null;
          });
          return out;
        }"""
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=SHOTS)
    parser.add_argument("--width", type=int, default=1360)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        page.on("console", lambda msg: rows.append({"console": f"{msg.type}: {msg.text}"}))
        page.on("pageerror", lambda err: rows.append({"pageerror": str(err)}))

        for project_id, panel_id, note in CURATED:
            html = out / f"snapshot-{project_id}-{panel_id}.html"
            if not html.is_file():
                raise SystemExit(f"missing snapshot {html}; run build_snapshots.py")
            page.goto(html.as_uri())
            page.wait_for_selector(".section", timeout=10_000)
            png = out / f"{project_id}-{panel_id}.png"
            page.screenshot(path=str(png), full_page=True)
            # count only per-section chips; the legend and the panel header also
            # render chips, and mixing them in would overstate coverage.
            chips = page.eval_on_selector_all(
                ".section > .section__head > .chip",
                "els => els.map(e => e.classList.contains('chip--verified') ? 'verified'"
                " : e.classList.contains('chip--blocked') ? 'blocked' : 'unverified')",
            )
            counts = {
                state: sum(1 for c in chips if c == state)
                for state in ("verified", "unverified", "blocked")
            }
            headline = page.eval_on_selector_all(
                ".panel__head > .chip",
                "els => els.map(e => e.className).join(' ')",
            )
            print(f"[shot] {png.name:34s} sections={len(chips):2d} {counts} "
                  f"panel={headline} tabdots={tab_dots(page)}  # {note}")
            rows.append({
                "png": str(png), "project_id": project_id, "panel_id": panel_id,
                "note": note, "states": counts, "synthetic": False,
                "section_count": len(chips), "panel_chip": headline,
                "tab_dots": tab_dots(page),
            })

        for name, note in FIXTURES:
            html = out / name
            if not html.is_file():
                raise SystemExit(f"missing fixture {html}; run build_snapshots.py")
            page.goto(html.as_uri())
            page.wait_for_selector(".section", timeout=10_000)
            png = out / name.replace("snapshot-", "").replace(".html", ".png")
            page.screenshot(path=str(png), full_page=True)
            dots = tab_dots(page)
            print(f"[shot] {png.name:34s} SYNTHETIC tabdots={dots}  # {note}")
            rows.append({
                "png": str(png), "project_id": None, "panel_id": None,
                "note": note, "synthetic": True, "tab_dots": dots,
            })
        browser.close()

    errors = [r for r in rows if "pageerror" in r or r.get("console", "").startswith("error")]
    print(f"[shot] {len(rows)} record(s); page errors: {len(errors)}")
    for err in errors:
        print("   ", err)
    (out / "_screenshots.json").write_text(
        json.dumps(
            scrub_absolute_paths(rows, REPO_ROOT), indent=1, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
