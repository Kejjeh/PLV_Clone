"""freshness — on-demand "catch up to yesterday" without the full daily rebuild.

The daily GitHub Action (daily-refresh.yml, ~7 AM ET) does the heavy job: statcast pull
-> model retrain -> dashboards -> publish. Between those runs, `ensure_fresh()` lets an
on-demand skill close the gap CHEAPLY: it runs only the two fast data bridges
(refresh_boxscores + build_statcast_gf_bridge), which are incremental and skip games
already cached. It deliberately does NOT retrain rh3/rp3/rprs2 (minutes) — those move
slowly day to day and stay as of the last daily refresh.

After ensure_fresh(): boom/bust actuals and every statcast-reading lens (splits,
expected-vs-actual, home/road, TTO, in-season archetype arc) reflect yesterday's games;
the headline rh3/rp3/rprs2 numbers are as of the last 7 AM refresh. Pass models=True for
a full local refresh (slow) when you truly need the projection numbers rebuilt too.

Cost: ~0s when already current (two parquet max-date reads); ~30-90s the first time after
new games land, near-instant on repeat calls that day. Safe-on-failure — a bridge error
prints a warning and the caller proceeds on existing data.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_XFP = _ROOT / "scripts" / "xfp"
_CACHE = _ROOT / "data" / "research" / "xfp_cache"
_STATCAST = _CACHE / "statcast_2026.parquet"
_BOX_P = _CACHE / "boxscore_pitchers.parquet"


def _max_game_date(path: Path):
    if not path.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(path, columns=["game_date"])
        return pd.to_datetime(df["game_date"]).max().date()
    except Exception:
        return None


def _run(label, script, timeout):
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", str(_XFP / script)],
                           cwd=str(_ROOT), capture_output=True, text=True, timeout=timeout)
        ok = r.returncode == 0
        print(f"  [fresh] {label}: {'ok' if ok else 'FAILED'}", file=sys.stderr)
        if not ok:
            print((r.stderr or r.stdout or "").splitlines()[-1:] and
                  (r.stderr or r.stdout).strip().splitlines()[-1], file=sys.stderr)
        return ok
    except Exception as e:
        print(f"  [fresh] {label}: error {type(e).__name__}: {e}", file=sys.stderr)
        return False


def ensure_fresh(*, models: bool = False, verbose: bool = True) -> dict:
    """Catch the local data up to yesterday via the two fast bridges. Returns a status
    dict {ran, statcast_through, boxscore_through, current}. Skips work when already
    current. models=True additionally runs the full daily refresh (slow)."""
    yesterday = date.today() - timedelta(days=1)
    sc, bx = _max_game_date(_STATCAST), _max_game_date(_BOX_P)
    current = (sc is not None and sc >= yesterday and bx is not None and bx >= yesterday)
    status = {"ran": False, "statcast_through": str(sc), "boxscore_through": str(bx),
              "current": current}
    if current and not models:
        if verbose:
            print(f"  [fresh] already current (statcast {sc}, boxscore {bx})", file=sys.stderr)
        return status

    if models:
        _run("daily refresh (statcast+models+dashboards)", "refresh_dashboards.py", 1800)
        status["ran"] = True
    else:
        # fast path: just the two incremental bridges
        _run("boxscore bridge", "refresh_boxscores.py", 180)
        _run("statcast gf bridge", "build_statcast_gf_bridge.py", 300)
        status["ran"] = True
    status["statcast_through"] = str(_max_game_date(_STATCAST))
    status["boxscore_through"] = str(_max_game_date(_BOX_P))
    return status
