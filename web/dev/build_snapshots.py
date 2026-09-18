#!/usr/bin/env python
"""Rebuild the M13 panels as static, self-contained HTML from captured API payloads.

Step 1 of ``ui-skeleton-first``: look at a real page fed with real data before
writing any interaction. This script does **not** invent data -- it loads the
payloads captured by ``seed_demo.py`` and runs them through the very same
``PanelProjection`` builders the live BFF uses (``src/autoresearch/web_api.py``),
then inlines the same ``web/styles.css`` / ``web/app.js``.

The result is a page that is
  * identical in markup and CSS to the live UI,
  * driven by real endpoint responses, and
  * openable over ``file://`` with no server (so screenshots are reproducible).

``render_page`` is the single source of truth for the page markup: both the real
snapshots and the tests that assert on rendered DOM go through it, so a test can
never be exercising markup that differs from what ships.

Usage
-----
    python web/dev/build_snapshots.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from snapshot_scrub import scrub_absolute_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = REPO_ROOT / "web"
DEFAULT_RAW = REPO_ROOT / "docs" / "tasks" / "M13-ui" / "tasks" / "screenshots" / "raw-api"

CONTRACT_BANNER = """<div class="banner banner--contract" role="note">
  <strong>面板不得把未完成写成完成</strong>（M13-04 / L1 §4.2 A5）。
  每个 section 都带一个 <code>verification_state</code>；非 verified 的 section
  <strong>必须内联显示原因</strong>，不使用「灰色 / 暂无」这类无法区分
  <code>unverified</code> 与 <code>blocked</code> 的写法。
</div>"""

PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<header class="topbar">
  <div class="topbar__id">
    <h1>AutoResearch · M13 面板</h1>
    <p class="topbar__sub">{subtitle}</p>
  </div>
  <div class="topbar__controls">
    <label class="field">
      <span class="field__label">project_id</span>
      <input id="project-input" class="field__input" type="text" value="{project_input}" disabled>
    </label>
    <button id="load-btn" class="btn btn--primary" type="button" disabled>载入</button>
  </div>
</header>

<div id="snapshot-note" class="banner banner--snapshot" role="note">
{banner}
</div>

{contract}

<nav id="tabs" class="tabs" aria-label="面板"></nav>
<div id="legend" class="legend"></div>
<main id="panels" class="panels"><p class="placeholder">正在载入…</p></main>

<footer class="foot">
{footer}
</footer>

<script id="panel-payload">
window.__PANEL_SNAPSHOT__ = {payload};
</script>
<script id="panel-app">
{js}
</script>
</body>
</html>
"""

REAL_FOOTER = """<p>来源：<code>GET /projects/{id}</code> · <code>GET /runs/{id}</code> ·
     <code>GET /projects/{id}/evidence?valid_only=false</code> ·
     <code>GET /projects/{id}/work-packages</code> ·
     <code>GET /projects/{id}/audit-events</code></p>
  <p>写入（仅 M13-07）：<code>POST /runs/{run_id}/resume</code> ·
     <code>POST /evidence/{evidence_id}/invalidate</code></p>"""

FIXTURE_FOOTER = (
    "<p>夹具由 <code>web/dev/build_snapshots.py</code> 生成；"
    "投影内容为合成，仅用于像素级核对渲染器行为。</p>"
)

FIXTURE_BANNER = """<strong>这是渲染夹具，不是真实项目快照。</strong>
  用途：<strong>证明四个 tab 状态点按真实投影状态着色，且 <code>verified</code> 与
  <code>INVALID-STATE</code> 两条路径可达</strong>。为什么需要它：在当前离线环境下，
  三个真实项目的 12 个面板<strong>没有任何一个</strong>整体达到 <code>verified</code>
  （实测 7 unverified + 5 blocked + 0 verified），因此 tab 点的第三态
  <strong>无法用真实数据截图</strong>。下面 4 个面板的状态依次是
  <code>verified</code> / <code>unverified</code> / <code>blocked</code> /
  故意畸形的 <code>weird-state</code>（用于验证渲染器不会把它伪装成三态之一）。"""


def render_page(
    *,
    title: str,
    subtitle: str,
    project_input: str,
    banner: str,
    footer: str,
    css: str,
    js: str,
    payload: dict[str, Any],
    contract_banner: bool = True,
) -> str:
    """Render one panel page. The only place the page markup is defined."""
    return PAGE.format(
        title=title,
        subtitle=subtitle,
        project_input=project_input,
        banner=banner,
        contract=CONTRACT_BANNER if contract_banner else "",
        footer=footer,
        css=css,
        js=js,
        payload=json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"),
    )


def read_assets(web_root: Path = WEB_ROOT) -> tuple[str, str]:
    return (
        (web_root / "styles.css").read_text(encoding="utf-8"),
        (web_root / "app.js").read_text(encoding="utf-8"),
    )


def load(project_dir: Path, name: str) -> Any:
    path = project_dir / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def load_sources(project_dir: Path, project_id: str) -> Any:
    from autoresearch.web_api import PanelSources

    return PanelSources(
        project_id=project_id,
        project=load(project_dir, "project"),
        run=load(project_dir, "run"),
        work_packages=load(project_dir, "project_work_packages"),
        # valid_only=false is required: the endpoint default hides retracted
        # evidence, which the retraction section must show.
        evidence=load(project_dir, "project_evidence_all"),
        audit_events=load(project_dir, "audit_events"),
    )


def project_ids(raw: Path) -> list[str]:
    return sorted(
        entry.name
        for entry in raw.iterdir()
        if entry.is_dir() and (entry / "project.json").is_file()
    )


def build_payloads(project_dir: Path, project_id: str, panels: tuple[str, ...]) -> dict:
    from autoresearch.web_api import build_panel

    sources = load_sources(project_dir, project_id)
    built = {
        panel_id: build_panel(panel_id, sources).model_dump(mode="json")
        for panel_id in panels
    }
    for projection in built.values():
        projection["project_id"] = project_id
    return built


def build_all(
    raw: Path,
    out: Path,
    only: list[str] | None,
    panels: tuple[str, ...],
) -> list[dict[str, str]]:
    css, js = read_assets()
    projections_dir = out / "projections"
    projections_dir.mkdir(parents=True, exist_ok=True)

    written: list[dict[str, str]] = []
    for project_id in project_ids(raw):
        if only and project_id not in only:
            continue
        built = build_payloads(raw / project_id, project_id, panels)
        for panel_id, projection in built.items():
            (projections_dir / f"{project_id}-{panel_id}.json").write_text(
                json.dumps(
                    scrub_absolute_paths(projection, REPO_ROOT),
                    indent=1,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        for panel_id in panels:
            html = render_page(
                title=f"AutoResearch M13 · {project_id} · {panel_id} (snapshot)",
                subtitle=(
                    f"静态快照 · project_id=<code>{project_id}</code> · 数据来自实跑 "
                    "<code>autoresearch serve</code> 的 GET 响应"
                ),
                project_input=project_id,
                banner=(
                    "这是<strong>静态快照</strong>：数据来自实跑 "
                    "<code>autoresearch serve</code> 的 GET 响应，已内联进页面。"
                    "<code>file://</code> 打开时写操作被禁用，点击按钮不会发出请求。"
                ),
                footer=REAL_FOOTER,
                css=css,
                js=js,
                payload={"initial": panel_id, "panels": built},
            )
            target = out / f"snapshot-{project_id}-{panel_id}.html"
            target.write_text(html, encoding="utf-8")
            written.append({
                "project_id": project_id,
                "panel_id": panel_id,
                "html": str(target),
                "state": built[panel_id]["verification_state"],
            })
    return written


def fixture_payloads() -> dict[str, Any]:
    """Synthetic projections, labelled as such on the page itself.

    Every real panel in this environment is `unverified` or `blocked`, so the
    `verified` dot would otherwise be unreachable from real data. The fixture is
    built from the real builders for the three legitimate states, plus one
    deliberately malformed projection to prove the renderer refuses to launder an
    unknown state into a real one.
    """
    from autoresearch.web_api import (
        PanelProjection,
        blocked_section,
        unverified_section,
        verified_section,
    )

    label = "_rendering-fixture (SYNTHETIC -- not project data)"

    def panel(panel_id: str, state: str, sections: list) -> dict:
        payload = PanelProjection(
            panel_id=panel_id, sections=sections, verification_state=state
        ).model_dump(mode="json")
        payload["project_id"] = label
        return payload

    return {
        "initial": "project",
        "fixture": True,
        "panels": {
            "project": panel("project", "verified", [
                verified_section("夹具段 A / fixture section (verified)",
                                 ["fix_ref_a"], {"fixture": "true"}),
            ]),
            "evidence": panel("evidence", "unverified", [
                unverified_section("夹具段 B / fixture section (unverified)",
                                   "fixture: synthetic reason for an unverified section",
                                   ["fix_ref_b"]),
            ]),
            "files": panel("files", "blocked", [
                blocked_section("夹具段 C / fixture section (blocked)",
                                "fixture: synthetic reason for a blocked section",
                                ["fix_ref_c"]),
            ]),
            "approval": {
                "panel_id": "approval",
                "project_id": label,
                "verification_state": "weird-state",
                "sections": [{
                    "title": "夹具段 D / malformed section (verification_state=weird-state)",
                    "refs": [],
                    "verified": False,
                    "unknown_reason": (
                        "fixture: deliberately malformed state to test the renderer guard"
                    ),
                    "verification_state": "weird-state",
                    "facts": {"fixture": "true"},
                }],
            },
        },
    }


def build_tabdot_fixture(out: Path, css: str, js: str) -> Path:
    html = render_page(
        title="AutoResearch M13 · tab-dot rendering fixture (synthetic)",
        subtitle=(
            "<strong>渲染夹具（合成数据，不是项目数据）</strong> · "
            "project_id=<code>_rendering-fixture</code>"
        ),
        project_input="_rendering-fixture",
        banner=FIXTURE_BANNER,
        footer=FIXTURE_FOOTER,
        css=css,
        js=js,
        payload=fixture_payloads(),
    )
    target = out / "snapshot-_tabdot-fixture.html"
    target.write_text(html, encoding="utf-8")
    return target


def main() -> int:
    from autoresearch.web_api import PANEL_IDS

    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--only", default=None,
                        help="comma-separated project ids to build")
    args = parser.parse_args()

    raw = args.raw.resolve()
    out = (args.out or raw.parent).resolve()
    if not raw.is_dir():
        raise SystemExit(f"no captured payloads at {raw}; run seed_demo.py first")

    only = [p.strip() for p in args.only.split(",")] if args.only else None
    written = build_all(raw, out, only, PANEL_IDS)
    for row in written:
        print(f"[snapshot] {row['project_id']:10s} {row['panel_id']:9s} "
              f"-> {row['state']:10s} {Path(row['html']).name}")
    css, js = read_assets()
    fixture = build_tabdot_fixture(out, css, js)
    print(f"[snapshot] tab-dot rendering fixture -> {fixture.name} (synthetic)")
    print(f"[snapshot] {len(written)} real page(s) + 1 fixture -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
