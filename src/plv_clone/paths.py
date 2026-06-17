"""Repo paths — the single source for the project root + data locations.

Resolves the repo root from this file's location (src/plv_clone/paths.py ->
parents[2]) so it works on any machine and from any CWD with zero setup, and
honors a ``PLV_ROOT`` env override (CI points it at ``$GITHUB_WORKSPACE``;
unusual layouts can override). The ``XFP_DOCS`` GitHub-Pages target honors a
``PLV_XFP_DOCS`` override.

Replaces the pattern of ~170 scripts each hardcoding
``Path('c:/Users/Joshua/plv_clone')`` (and the two inconsistent env-based
variants that crept in). New code does ``from plv_clone.paths import ROOT, OUTPUTS``.
"""
from __future__ import annotations

import os
from pathlib import Path


def _resolve_root() -> Path:
    env = os.environ.get("PLV_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


ROOT = _resolve_root()
DATA = ROOT / "data"
OUTPUTS = DATA / "outputs"
RESEARCH = DATA / "research"
CACHE = RESEARCH / "xfp_cache"
MODELS = DATA / "models"
# xfp-model sibling docs (GitHub Pages). PLV_XFP_DOCS overrides for CI, where
# the sibling repo is checked out at a different path than ROOT/xfp-model.
XFP_DOCS = Path(os.environ.get("PLV_XFP_DOCS", str(ROOT / "xfp-model" / "docs")))
