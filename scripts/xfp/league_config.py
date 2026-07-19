"""league_config.py — re-export shim.

This was a byte-identical DUPLICATE of plv_clone.league_config (the installed
canonical copy) until 2026-07-19 — the two had already started to drift (the
HD-weight fix landed in one but not the other). Collapsed to a shim so there
is exactly one league-configuration source. Consumers here import it bare
(`import league_config`) via the scripts/xfp sys.path entry.
"""
from plv_clone.league_config import *  # noqa: F401,F403
