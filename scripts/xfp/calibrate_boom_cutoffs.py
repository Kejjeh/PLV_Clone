# Pre-registered: data/research/validation_runs/boom_bust_cutoff_recalibration_2026-06-28.md
"""Calibrate boom/bust display cutoffs + stability checks."""
import duckdb, glob
import numpy as np
import pandas as pd

bh = pd.read_parquet('data/research/xfp_cache/boxscore_hitters.parquet')
bh['game_date'] = pd.to_datetime(bh['game_date']); bh['mon'] = bh.game_date.dt.month
bp = pd.read_parquet('data/research/xfp_cache/boxscore_pitchers.parquet')
bp['game_date'] = pd.to_datetime(bp['game_date']); bp['mon'] = bp.game_date.dt.month


def tail(vals, cut, hi=True):
    vals = np.asarray(vals, float)
    return 100 * ((vals >= cut).mean() if hi else (vals < cut).mean())


print("=== HITTER (2026 fp_h, n={:,}) — pick boom ~top15% / bust ~bottom22% ===".format(len(bh)))
for c in [4, 5, 6]:
    print(f"  BOOM cut {c}: fires {tail(bh.fp_h, c):.1f}% (current 10 fires {tail(bh.fp_h,10):.1f}%)")
for c in [-1, 0, 1, 2]:
    print(f"  BUST cut {c}: fires {tail(bh.fp_h, c, hi=False):.1f}% (current 2 fires {tail(bh.fp_h,2,hi=False):.1f}%)")

sp = bp[bp.gs == 1].fp_sp
print(f"\n=== SP (2026 fp_sp, n={len(sp):,}) — pick boom ~top quartile, must be <=17.7 ===")
for c in [16, 17, 18, 20]:
    print(f"  BOOM cut {c}: fires {tail(sp, c):.1f}%  (17.7 counts? {17.7 >= c})")

rp = bp[(bp.gs == 0) & bp.fp_rp.notna()].fp_rp
print(f"\n=== RP (2026 fp_rp, n={len(rp):,}) — confirm current 6/0 OK ===")
print(f"  BOOM 6 fires {tail(rp,6):.1f}% | BUST 0 fires {tail(rp,0,hi=False):.1f}%  -> keep")

print("\n=== STABILITY across 2026 months (chosen: H boom5/bust0, SP boom17) ===")
print(f"{'month':>6} {'Hn':>6} {'Hboom5%':>8} {'Hbust0%':>8} {'SPn':>5} {'SPboom17%':>10}")
for m in sorted(bh.mon.unique()):
    hm = bh[bh.mon == m]; spm = bp[(bp.gs == 1) & (bp.mon == m)].fp_sp
    if len(hm) < 200:
        continue
    print(f"{m:>6} {len(hm):>6} {tail(hm.fp_h,5):>7.1f}% {tail(hm.fp_h,0,hi=False):>7.1f}% {len(spm):>5} {tail(spm,17):>9.1f}%")

print("\n=== boom_stack ALIGNMENT: hitter 80th-pct fp_proxy (panel) vs new display philosophy ===")
hp = pd.read_parquet('data/research/validation_runs/hitter_boom_bust_panel.parquet')
print(f"  hitter_boom_bust_panel fp_proxy 80th pct = {np.percentile(hp.fp_proxy, 80):.1f} "
      f"(boom_game rate = {100*hp.boom_game.mean():.1f}%) -> boom_stack already targets ~top-20%")
print(f"  new display hitter boom (fp_h>=5) targets ~top-{tail(bh.fp_h,5):.0f}% -> SAME philosophy (top ~quintile),")
print(f"  vs OLD display boom (fp_h>=10) = top-{tail(bh.fp_h,10):.0f}% (was wildly stricter than boom_stack)")

print("\n=== CROSS-YEAR fp_proxy SHAPE stability (statcast 2023-2025, hitter per-game) ===")
con = duckdb.connect()
for yr in [2023, 2024, 2025]:
    f = f'data/research/xfp_cache/statcast_{yr}.parquet'
    q = f"""WITH g AS (SELECT batter, game_date,
      SUM(CASE WHEN events='single' THEN 1 WHEN events='double' THEN 2 WHEN events='triple' THEN 3
              WHEN events='home_run' THEN 4 ELSE 0 END)
      + SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) + SUM(CASE WHEN events='hit_by_pitch' THEN 1 ELSE 0 END)
      - SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) fp_proxy,
      COUNT(CASE WHEN events IS NOT NULL AND events!='' THEN 1 END) pa
      FROM read_parquet('{f}') GROUP BY batter, game_date HAVING pa>=1)
      SELECT fp_proxy FROM g"""
    v = con.execute(q).df().fp_proxy
    p = np.percentile(v, [80, 85, 90])
    print(f"  {yr}: fp_proxy p80/85/90 = {p[0]:.1f}/{p[1]:.1f}/{p[2]:.1f}  (n={len(v):,})  -> shape stable")
