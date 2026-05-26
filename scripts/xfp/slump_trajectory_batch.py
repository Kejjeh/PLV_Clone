"""
slump_trajectory_batch.py
=========================
Batch slump trajectory analysis for a list of batter IDs.

Computes per-batter:
  1. Rolling 30-PA xwOBA trajectory (2026) — ~10 evenly-spaced sample points
  2. K% decomposition across 2025 / 2026-szn / 2026-L21d windows
  3. Pitch-mix attack (FB / BRK / OFF) for 2026-szn vs L21d, with shift flag

Usage:
    from scripts.xfp.slump_trajectory_batch import batch_slump_trajectory
    results = batch_slump_trajectory([545361, 592518, 596019])
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("c:/Users/Joshua/plv_clone")
sys.path.insert(0, str(ROOT))

import duckdb

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PARQUET_2025 = str(ROOT / "data/research/xfp_cache/statcast_2025.parquet")
PARQUET_2026 = str(ROOT / "data/research/xfp_cache/statcast_2026.parquet")

SLUMP_THRESHOLD = 0.320   # rolling-30 first dips below → slump start
TRAJ_SAMPLE_POINTS = 10   # target number of trajectory points to return

# PA-terminating events (plate appearance = one of these)
PA_EVENTS = {
    "strikeout", "strikeout_double_play",
    "walk", "intent_walk",
    "single", "double", "triple", "home_run",
    "field_out", "force_out", "grounded_into_double_play",
    "fielders_choice", "fielders_choice_out", "double_play",
    "sac_fly", "sac_fly_double_play", "sac_bunt",
    "hit_by_pitch", "catcher_interf", "field_error",
}

# For K-decomp classification
STRIKEOUT_EVENTS   = {"strikeout", "strikeout_double_play"}
WALK_EVENTS        = {"walk", "intent_walk"}
HIT_EVENTS         = {"single", "double", "triple", "home_run"}
OUT_CONTACT_EVENTS = {
    "field_out", "force_out", "grounded_into_double_play",
    "fielders_choice", "fielders_choice_out", "double_play",
    "sac_fly", "sac_fly_double_play",
}

# Pitch-type families
FB_TYPES  = ("FF", "FT", "SI", "FC")
BRK_TYPES = ("SL", "CU", "KC", "SV", "ST")
OFF_TYPES = ("CH", "FS", "SP", "EP", "KN")


# ---------------------------------------------------------------------------
# DuckDB helpers
# ---------------------------------------------------------------------------

def _make_in_clause(ids: list[int]) -> str:
    return "(" + ", ".join(str(i) for i in ids) + ")"


def _fetch_2026_pa_events(con: duckdb.DuckDBPyConnection, batter_ids: list[int]):
    """Return all 2026 PA-terminating events for the given batters, ordered."""
    ids = _make_in_clause(batter_ids)
    sql = f"""
        SELECT
            batter,
            game_date,
            events,
            estimated_woba_using_speedangle AS xwoba
        FROM read_parquet('{PARQUET_2026}')
        WHERE batter IN {ids}
          AND events IS NOT NULL
          AND events NOT IN ('truncated_pa')
        ORDER BY batter, game_date, at_bat_number
    """
    return con.execute(sql).fetchall()


def _fetch_2025_pa_events(con: duckdb.DuckDBPyConnection, batter_ids: list[int]):
    """Return all 2025 PA-terminating events for K-decomp baseline."""
    ids = _make_in_clause(batter_ids)
    sql = f"""
        SELECT
            batter,
            events
        FROM read_parquet('{PARQUET_2025}')
        WHERE batter IN {ids}
          AND events IS NOT NULL
          AND events NOT IN ('truncated_pa')
        ORDER BY batter, game_date, at_bat_number
    """
    return con.execute(sql).fetchall()


def _fetch_2026_pitches(con: duckdb.DuckDBPyConnection, batter_ids: list[int]):
    """Return all 2026 pitches (with pitch_type) for pitch-mix analysis."""
    ids = _make_in_clause(batter_ids)
    sql = f"""
        SELECT
            batter,
            game_date,
            pitch_type,
            -- row rank within batter to identify L21d by PA count
            ROW_NUMBER() OVER (
                PARTITION BY batter
                ORDER BY game_date, at_bat_number, pitch_number
            ) AS row_n
        FROM read_parquet('{PARQUET_2026}')
        WHERE batter IN {ids}
          AND pitch_type IS NOT NULL
        ORDER BY batter, game_date, at_bat_number, pitch_number
    """
    return con.execute(sql).fetchall()


# ---------------------------------------------------------------------------
# Per-batter processing helpers
# ---------------------------------------------------------------------------

def _compute_k_decomp_rates(rows: list[tuple]) -> dict:
    """Given a list of (events,) tuples, compute k/bb/hit/out rates."""
    n = len(rows)
    if n == 0:
        return {"k_rate": None, "bb_rate": None, "hit_rate": None, "out_rate": None, "pa": 0}
    k = sum(1 for r in rows if r[0] in STRIKEOUT_EVENTS)
    bb = sum(1 for r in rows if r[0] in WALK_EVENTS)
    hit = sum(1 for r in rows if r[0] in HIT_EVENTS)
    out = sum(1 for r in rows if r[0] in OUT_CONTACT_EVENTS)
    return {
        "k_rate":   round(k  / n, 4),
        "bb_rate":  round(bb / n, 4),
        "hit_rate": round(hit / n, 4),
        "out_rate": round(out / n, 4),
        "pa":       n,
    }


def _classify_slump_source(
    base: dict, szn: dict, l21: dict
) -> tuple[str, str]:
    """
    Classify the slump source comparing szn/l21d to 2025 baseline.
    Returns (label, note).
    """
    if base["k_rate"] is None or szn["k_rate"] is None or l21["k_rate"] is None:
        return "UNKNOWN", "Insufficient data"

    # Use L21d as the 'current' window vs 2025 baseline
    k_delta   = l21["k_rate"]   - base["k_rate"]
    bb_delta  = l21["bb_rate"]  - base["bb_rate"]
    hit_delta = l21["hit_rate"] - base["hit_rate"]
    out_delta = l21["out_rate"] - base["out_rate"]

    THRESHOLD = 0.02  # 2 percentage points

    k_up   = k_delta  >  THRESHOLD
    k_dn   = k_delta  < -THRESHOLD
    bb_dn  = bb_delta < -THRESHOLD
    out_up = out_delta > THRESHOLD
    hit_dn = hit_delta < -THRESHOLD

    factors = []
    if k_up:
        factors.append("K")
    if bb_dn:
        factors.append("BB")
    if out_up and hit_dn:
        factors.append("BABIP")

    notes = []
    notes.append(
        f"K% {base['k_rate']*100:.1f}%->{l21['k_rate']*100:.1f}% "
        f"({'UP' if k_up else 'DOWN' if k_dn else 'stable'}"
        f"{', discipline fine' if not k_up and not bb_dn else ''})"
    )
    if bb_dn:
        notes.append(f"BB% {base['bb_rate']*100:.1f}%->{l21['bb_rate']*100:.1f}% (DOWN)")
    notes.append(
        f"out_rate {base['out_rate']*100:.1f}%->{l21['out_rate']*100:.1f}% "
        f"({'UP, balls finding gloves' if out_up else 'stable/down'})"
    )

    if not factors:
        label = "HOLDING"
    elif "K" in factors and "BB" in factors:
        label = "DISCIPLINE_COLLAPSE"
    elif "K" in factors and "BABIP" in factors:
        label = "MIXED"
    elif "K" in factors:
        label = "K_DRIVEN"
    elif "BABIP" in factors:
        label = "BABIP_DRIVEN"
    else:
        label = "MIXED"

    return label, "; ".join(notes)


def _compute_pitch_mix(
    pitches: list[tuple],  # (game_date, pitch_type, row_n)
    l21d_event_count: int,
) -> dict:
    """
    Compute FB/BRK/OFF breakdown for 2026 season and L21d.
    l21d_event_count is the # of PA events in L21d (used to approximate
    the corresponding pitch rows — we take the last N pitches by row_n).
    """
    # pitches sorted by row_n ascending
    total = len(pitches)

    def _pct_breakdown(rows):
        n = len(rows)
        if n == 0:
            return {"fb_pct": None, "brk_pct": None, "off_pct": None, "n": 0}
        fb  = sum(1 for r in rows if r[1] in FB_TYPES)
        brk = sum(1 for r in rows if r[1] in BRK_TYPES)
        off = sum(1 for r in rows if r[1] in OFF_TYPES)
        return {
            "fb_pct":  round(fb  / n, 4),
            "brk_pct": round(brk / n, 4),
            "off_pct": round(off / n, 4),
            "n":       n,
        }

    szn_data = _pct_breakdown(pitches)

    # L21d: approximate as last (l21d_event_count * avg pitches/PA) rows
    # Use last 100 pitches as a reasonable proxy for ~21 PAs
    # (typical ~4-5 pitches/PA → 21 PAs ≈ 85-105 pitches)
    l21d_rows = pitches[-min(100, total):]
    l21d_data = _pct_breakdown(l21d_rows)

    # Detect shift > 5pt in any family
    shift_flag = False
    shift_notes = []
    if szn_data["fb_pct"] is not None and l21d_data["fb_pct"] is not None:
        for family, s_key in [("Fastball", "fb_pct"), ("Breaking", "brk_pct"), ("Offspeed", "off_pct")]:
            delta = l21d_data[s_key] - szn_data[s_key]
            if abs(delta) > 0.05:
                shift_flag = True
                direction = "+" if delta > 0 else ""
                shift_notes.append(
                    f"{family} {direction}{delta*100:.0f}pt in L21d"
                )

    shift_note = (
        "; ".join(shift_notes) + " (pitchers adjusting)" if shift_notes
        else "No significant mix shift"
    )

    return {
        "2026_szn": szn_data,
        "l21d":     l21d_data,
        "shift_flag": shift_flag,
        "shift_note": shift_note,
    }


def _compute_trajectory(
    pa_rows: list[tuple],  # (game_date, events, xwoba)
) -> tuple[list[dict], int | None, str | None]:
    """
    Compute rolling-30 xwOBA trajectory for xwOBA-eligible PA events.
    Returns (trajectory_points, slump_start_event, slump_start_date).
    """
    # Filter to rows with non-null xwOBA (xwOBA eligible events)
    xwoba_rows = [
        (r[0], r[2])  # (game_date, xwoba)
        for r in pa_rows
        if r[2] is not None
    ]

    n = len(xwoba_rows)
    if n < 5:
        return [], None, None

    # Compute rolling-30 at each event position
    rolling = []
    for i in range(n):
        window = xwoba_rows[max(0, i - 29): i + 1]
        mean_xwoba = sum(r[1] for r in window) / len(window)
        rolling.append({
            "event_n":      i + 1,
            "date":         str(xwoba_rows[i][0])[:10],
            "roll30_xwoba": round(mean_xwoba, 4),
        })

    # Sample ~10 evenly-spaced points
    if n <= TRAJ_SAMPLE_POINTS:
        trajectory = rolling
    else:
        step = max(1, n // TRAJ_SAMPLE_POINTS)
        indices = list(range(0, n, step))
        # Always include last point
        if (n - 1) not in indices:
            indices.append(n - 1)
        trajectory = [rolling[i] for i in sorted(set(indices))]

    # Find slump start (first time rolling-30 drops below threshold)
    slump_start_event = None
    slump_start_date  = None
    for pt in rolling:
        if pt["roll30_xwoba"] < SLUMP_THRESHOLD:
            slump_start_event = pt["event_n"]
            slump_start_date  = pt["date"]
            break

    return trajectory, slump_start_event, slump_start_date


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def batch_slump_trajectory(batter_ids: list[int]) -> dict[int, dict]:
    """
    Compute slump trajectory data for a list of batter IDs.

    Returns a dict keyed by batter_id with keys:
        trajectory, slump_start_event, slump_start_date,
        k_decomp, pitch_mix
    """
    if not batter_ids:
        return {}

    con = duckdb.connect()

    # --- Fetch raw data ---
    raw_2026 = _fetch_2026_pa_events(con, batter_ids)
    raw_2025 = _fetch_2025_pa_events(con, batter_ids)
    raw_pitches = _fetch_2026_pitches(con, batter_ids)

    con.close()

    # --- Group by batter ---
    from collections import defaultdict
    pa_2026:    dict[int, list] = defaultdict(list)
    pa_2025:    dict[int, list] = defaultdict(list)
    pitches_26: dict[int, list] = defaultdict(list)

    for batter, game_date, events, xwoba in raw_2026:
        pa_2026[batter].append((game_date, events, xwoba))

    for batter, events in raw_2025:
        pa_2025[batter].append((events,))

    for batter, game_date, pitch_type, row_n in raw_pitches:
        pitches_26[batter].append((game_date, pitch_type, row_n))

    # --- Per-batter processing ---
    results: dict[int, dict] = {}

    for bid in batter_ids:
        rows_26 = pa_2026.get(bid, [])
        rows_25 = pa_2025.get(bid, [])
        pitches = pitches_26.get(bid, [])

        # 1. Trajectory (all PA rows — xwoba filter inside)
        trajectory, slump_start_event, slump_start_date = _compute_trajectory(rows_26)

        # 2. K-decomp windows
        # 2026 all-season
        szn_rows  = [(r[1],) for r in rows_26]
        # L21d: last 21 PA events by row order
        l21d_rows = [(r[1],) for r in rows_26[-21:]]
        # 2025 baseline
        base_rows = rows_25

        base_stats = _compute_k_decomp_rates(base_rows)
        szn_stats  = _compute_k_decomp_rates(szn_rows)
        l21d_stats = _compute_k_decomp_rates(l21d_rows)

        slump_source, slump_note = _classify_slump_source(base_stats, szn_stats, l21d_stats)

        k_decomp = {
            "2025":        {k: v for k, v in base_stats.items() if k != "pa"},
            "2026_szn":    {k: v for k, v in szn_stats.items()  if k != "pa"},
            "l21d":        {k: v for k, v in l21d_stats.items() if k != "pa"},
            "slump_source":      slump_source,
            "slump_source_note": slump_note,
        }

        # 3. Pitch mix
        pitch_mix = _compute_pitch_mix(pitches, len(l21d_rows))

        results[bid] = {
            "trajectory":         trajectory,
            "slump_start_event":  slump_start_event,
            "slump_start_date":   slump_start_date,
            "k_decomp":           k_decomp,
            "pitch_mix":          pitch_mix,
        }

    return results


# ---------------------------------------------------------------------------
# CLI test block
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    TEST_IDS = [
        545361,  # Vladimir Guerrero Jr.
        592518,  # Manny Machado
        596019,  # Corey Seager
    ]
    NAMES = {
        545361: "Vladimir Guerrero Jr.",
        592518: "Manny Machado",
        596019: "Corey Seager",
    }

    print("Running batch_slump_trajectory on test batters...\n")
    results = batch_slump_trajectory(TEST_IDS)

    for bid in TEST_IDS:
        name = NAMES[bid]
        data = results.get(bid, {})
        traj = data.get("trajectory", [])
        kd   = data.get("k_decomp", {})
        pm   = data.get("pitch_mix", {})

        print(f"{'='*60}")
        print(f"  {name} (ID: {bid})")
        print(f"{'='*60}")

        # Trajectory
        print(f"  Trajectory ({len(traj)} points, slump threshold: {SLUMP_THRESHOLD}):")
        if traj:
            for pt in traj:
                marker = " <-- SLUMP START" if pt["event_n"] == data.get("slump_start_event") else ""
                print(f"    event {pt['event_n']:3d}  {pt['date']}  roll30_xwoba={pt['roll30_xwoba']:.4f}{marker}")
            print(f"  Slump start: event {data.get('slump_start_event')}  date {data.get('slump_start_date')}")
        else:
            print("    (no trajectory data)")

        # K-decomp
        print(f"\n  K-Decomp:")
        for window in ("2025", "2026_szn", "l21d"):
            w = kd.get(window, {})
            print(f"    {window:10s}  K%={w.get('k_rate','?'):.3f}  BB%={w.get('bb_rate','?'):.3f}  "
                  f"H%={w.get('hit_rate','?'):.3f}  out%={w.get('out_rate','?'):.3f}")
        print(f"  Slump source: {kd.get('slump_source','?')}")
        print(f"  Note: {kd.get('slump_source_note','')}")

        # Pitch mix
        print(f"\n  Pitch Mix:")
        for window in ("2026_szn", "l21d"):
            w = pm.get(window, {})
            print(f"    {window:10s}  FB%={w.get('fb_pct','?')}  BRK%={w.get('brk_pct','?')}  "
                  f"OFF%={w.get('off_pct','?')}  n={w.get('n','?')}")
        print(f"  Shift flag: {pm.get('shift_flag')}  |  {pm.get('shift_note','')}")
        print()
