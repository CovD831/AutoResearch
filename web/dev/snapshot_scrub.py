#!/usr/bin/env python
"""Shared helper for the M13 snapshot tooling: scrub host paths out of evidence.

Why this exists
---------------
The runtime legitimately returns absolute paths -- ``GET /projects/{id}`` echoes
the project's ``path`` -- and that is a product behaviour the M13 package does
not change. But a **committed** snapshot must not carry the author's home
directory:

* it leaks the local machine layout (username, checkout directory), and
* it makes the evidence non-reproducible, because a reader on another machine
  sees a path that cannot exist for them.

Both ``seed_demo.py`` (which writes the raw API captures) and
``build_snapshots.py`` (which writes the derived projections and the screenshot
index) need this, so it lives in one place. Duplicating it in each script would
mean the two copies can drift -- the exact failure mode this package has been
repeatedly bitten by elsewhere.

Policy
------
* A path under the repository root becomes ``<repo>/<relative-path>``.
* Any other absolute path is reduced to ``<abs>/<basename>`` so no host
  structure survives.
* Non-paths (including ordinary strings that merely start with ``/`` inside a
  URL) are left alone unless they look like a filesystem path -- see
  ``_looks_like_path``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["scrub_absolute_paths"]

# Prefixes that are part of an ordinary URL / route rather than a host path.
_URL_PREFIXES = ("//", "/api", "/projects", "/runs", "/evidence", "/papers",
                 "/manuscripts", "/knowledge", "/profiles", "/experiences",
                 "/evolution", "/health", "/work-packages")


def _looks_like_path(value: str) -> bool:
    """True when ``value`` is a filesystem path rather than a URL or route."""
    if not value.startswith("/"):
        return False
    return not value.startswith(_URL_PREFIXES)


def scrub_absolute_paths(value: Any, root: Path) -> Any:
    """Recursively rewrite absolute host paths into non-identifying forms.

    ``root`` is the repository root; anything under it becomes a ``<repo>/...``
    relative path. Any other host path keeps only its basename.
    """
    root_str = str(root)
    if isinstance(value, str):
        if value.startswith(root_str):
            rel = value[len(root_str):].lstrip("/")
            return f"<repo>/{rel}" if rel else "<repo>"
        if _looks_like_path(value):
            tail = value.rstrip("/").rsplit("/", 1)[-1]
            return f"<abs>/{tail}" if tail else "<abs>"
        return value
    if isinstance(value, dict):
        return {k: scrub_absolute_paths(v, root) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_absolute_paths(v, root) for v in value]
    return value
