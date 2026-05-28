"""
Ligers roster signal evaluation — refined thresholds from MC bootstrap.
Signal A: fpp >= +0.02 AND whiff% >= 26 (4-8 GS window)
Rolling window: 3/4 good starts = ACTIONABLE, 4/4 = LOCK
Harrison: fpp blind (<-0.0476) but stuff_contact fires
"""
import sys, duckdb, pandas as pd, unicodedata, re
from pathlib import Path

REPO = Path(r"c:\Users\Joshua\plv_clone")
sys.path.insert(0, str(REPO))
from app.espn_connector import get_my_roster_with_injuries

PARQ26 = (REPO / "data/research/xfp_cache/statcast_2026.parquet").as_posix()
PARQ25 = (REPO / "data/research/xfp_cache/statcast_2025.parquet").as_posix()
rp3   = pd.read_csv(REPO / "data/outputs/xfp_rp3_projections.csv")
rh3   = pd.read_csv(REPO / "data/outputs/xfp_rh3_projections.csv")
rprs2 = pd.read_csv(REPO / "data/outputs/xfp_rprs2_projections.csv")


def _norm(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", s).strip()


def model_rank(name, tbl, name_col="player_name", rank_col="rank"):
    if name_col not in tbl.columns:
        # rprs2 uses name_api
        name_col = "name_api" if "name_api" in tbl.columns else tbl.columns[1]
    last = _norm(name).split()[-1]
    m = tbl[tbl[name_col].str.lower().str.contains(last, na=False)]
    if len(m):
        return int(m[rank_col].iloc[0])
    return 999


print("Pulling live Ligers roster...", flush=True)
roster = get_my_roster_with_injuries()
sp_rows = roster[roster["position"] == "SP"]
rp_rows = roster[roster["position"] == "RP"]
hit_rows = roster[~roster["position"].isin(["SP", "RP"])]
sp_names = sp_rows["player_name"].tolist()
rp_names = rp_rows["player_name"].tolist()
hit_names = hit_rows["player_name"].tolist()

con = duckdb.connect()

# ── SP season aggregates ─────────────────────────────────────────────────────
sp_season = con.execute(f"""
WITH starts AS (
  SELECT pitcher, player_name, game_date::DATE AS gd,
    COUNT(CASE WHEN events IS NOT NULL AND events!='' THEN 1 END) AS bf,
    SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
    SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
    SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
    SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr
  FROM read_parquet('{PARQ26}')
  WHERE game_date >= '2026-03-26'
  GROUP BY pitcher, player_name, game_date::DATE
  HAVING COUNT(CASE WHEN events IS NOT NULL AND events!='' THEN 1 END) >= 10
)
SELECT pitcher, player_name,
  COUNT(*) AS gs,
  SUM(bf) AS tot_bf,
  SUM(k) AS k, SUM(bb) AS bb, SUM(h) AS h, SUM(hr) AS hr,
  ROUND((SUM(k)-SUM(bb)-SUM(h)-SUM(hr))*1.0/NULLIF(SUM(bf),0), 4) AS fpp,
  SUM(CASE WHEN (k-bb-h-hr)*1.0/NULLIF(bf,0)>=-0.0476 THEN 1 ELSE 0 END) AS good_starts
FROM starts GROUP BY pitcher, player_name
""").df()

# ── SP rolling window (last 5 starts) ────────────────────────────────────────
sp_roll = con.execute(f"""
WITH starts AS (
  SELECT pitcher, player_name, game_date::DATE AS gd,
    COUNT(CASE WHEN events IS NOT NULL AND events!='' THEN 1 END) AS bf,
    SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
    SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
    SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
    SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr
  FROM read_parquet('{PARQ26}')
  WHERE game_date >= '2026-03-26'
  GROUP BY pitcher, player_name, game_date::DATE
  HAVING COUNT(CASE WHEN events IS NOT NULL AND events!='' THEN 1 END) >= 10
),
ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY pitcher ORDER BY gd DESC) AS rn,
    CASE WHEN (k-bb-h-hr)*1.0/NULLIF(bf,0) >= -0.0476 THEN 1 ELSE 0 END AS good
  FROM starts
)
SELECT pitcher, player_name,
  COUNT(*) AS total_gs,
  SUM(CASE WHEN rn<=4 THEN good ELSE 0 END) AS l4_good,
  MIN(CASE WHEN rn<=4 THEN 1 ELSE NULL END) AS l4_has,
  SUM(CASE WHEN rn<=5 THEN good ELSE 0 END) AS l5_good,
  SUM(CASE WHEN rn<=5 THEN 1 ELSE NULL END) AS l5_n,
  STRING_AGG(CAST(good AS VARCHAR), '' ORDER BY rn DESC) AS pattern
FROM ranked GROUP BY pitcher, player_name
""").df()

# ── stuff+contact (whiff, CSW, xwOBA-contact) ────────────────────────────────
stuff = con.execute(f"""
SELECT pitcher,
  COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_bounded','foul_tip') THEN 1 END)*100.0/
    NULLIF(COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_bounded','foul_tip','foul','hit_into_play','foul_bunt','missed_bunt') THEN 1 END),0) AS whiff_pct,
  COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_bounded','foul_tip','called_strike') THEN 1 END)*100.0/NULLIF(COUNT(*),0) AS csw_pct,
  AVG(CASE WHEN launch_speed IS NOT NULL AND estimated_woba_using_speedangle IS NOT NULL
           THEN estimated_woba_using_speedangle END) AS xwoba_contact,
  AVG(CASE WHEN launch_speed IS NOT NULL THEN launch_speed END) AS avg_ev
FROM read_parquet('{PARQ26}')
WHERE game_date >= '2026-03-26'
GROUP BY pitcher
""").df()

# ── Hitter xwOBA: season + L21d vs 2025 baseline ────────────────────────────
hit_sql_26 = f"""
SELECT batter, player_name,
  COUNT(CASE WHEN events IS NOT NULL AND events!='' THEN 1 END) AS pa,
  AVG(CASE WHEN events IS NOT NULL AND events!='' AND estimated_woba_using_speedangle IS NOT NULL
           THEN estimated_woba_using_speedangle END) AS xwoba_szn,
  AVG(CASE WHEN game_date::DATE >= '2026-05-04' AND events IS NOT NULL AND events!=''
           AND estimated_woba_using_speedangle IS NOT NULL
           THEN estimated_woba_using_speedangle END) AS xwoba_l21d,
  COUNT(CASE WHEN game_date::DATE >= '2026-05-04' AND events IS NOT NULL AND events!='' THEN 1 END) AS pa_l21d,
  AVG(CASE WHEN launch_speed IS NOT NULL THEN launch_speed END) AS avg_ev,
  PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY launch_speed) FILTER (WHERE launch_speed IS NOT NULL) AS ev90,
  COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_bounded','foul_tip') THEN 1 END)*100.0/
    NULLIF(COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_bounded','foul_tip','foul','hit_into_play') THEN 1 END), 0) AS whiff_pct
FROM read_parquet('{PARQ26}')
WHERE game_date >= '2026-03-26'
GROUP BY batter, player_name
"""
hit_26 = con.execute(hit_sql_26).df()

hit_sql_25 = f"""
SELECT batter,
  AVG(CASE WHEN events IS NOT NULL AND events!='' AND estimated_woba_using_speedangle IS NOT NULL
           THEN estimated_woba_using_speedangle END) AS xwoba_25,
  COUNT(CASE WHEN events IS NOT NULL AND events!='' THEN 1 END) AS pa_25
FROM read_parquet('{PARQ25}')
GROUP BY batter
"""
hit_25 = con.execute(hit_sql_25).df()

hit_merged = hit_26.merge(hit_25, on="batter", how="left")

# ── RP fpp/bf season ─────────────────────────────────────────────────────────
rp_sql = f"""
WITH apps AS (
  SELECT pitcher, player_name,
    COUNT(DISTINCT game_date::DATE) AS apps,
    COUNT(CASE WHEN events IS NOT NULL AND events!='' THEN 1 END) AS bf,
    SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
    SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
    SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
    SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr
  FROM read_parquet('{PARQ26}')
  WHERE game_date >= '2026-03-26' AND inning > 1
  GROUP BY pitcher, player_name
)
SELECT *, ROUND((k-bb-h-hr)*1.0/NULLIF(bf,0), 4) AS fpp
FROM apps WHERE apps >= 5
"""
rp_data = con.execute(rp_sql).df()

con.close()


def find_sp(name):
    n = _norm(name)
    last = n.split()[-1]
    for _, r in sp_season.iterrows():
        if last in _norm(r["player_name"]):
            return r
    return None


def find_roll(name):
    last = _norm(name).split()[-1]
    for _, r in sp_roll.iterrows():
        if last in _norm(r["player_name"]):
            return r
    return None


def find_stuff(pitcher_id):
    m = stuff[stuff["pitcher"] == pitcher_id]
    if len(m):
        return m.iloc[0]
    return None


def find_hitter(name):
    last = _norm(name).split()[-1]
    for _, r in hit_merged.iterrows():
        if last in _norm(r["player_name"]):
            return r
    return None


def find_rp(name):
    last = _norm(name).split()[-1]
    for _, r in rp_data.iterrows():
        if last in _norm(r["player_name"]):
            return r
    return None


def get_injury(name):
    row = roster[roster["player_name"] == name]
    if len(row) and row.iloc[0]["injured"]:
        return row.iloc[0]["injury_status"]
    return None


def roll_tier(l4g, l4n):
    if l4n < 3:
        return f"early({l4g}/{l4n})"
    r = l4g / l4n
    if r >= 1.0:
        return f"LOCK {l4g}/{l4n}"
    if r >= 0.75:
        return f"LOCK {l4g}/{l4n}"
    if r >= 0.5:
        return f"STRONG {l4g}/{l4n}"
    return f"WATCH {l4g}/{l4n}"


# ────────────────────────────────────────────────────────────────────────────
print()
print("=" * 75)
print("LIGERS ROSTER SIGNAL EVALUATION  (2026-05-25)")
print("MC-refined thresholds: Signal A => fpp>=+0.02 AND whiff>=26 (4-8 GS)")
print("=" * 75)

print()
print("─" * 75)
print("STARTING PITCHERS")
print("─" * 75)
print(f"  {'Name':<26} {'GS':<4} {'fpp':<7} {'GS+':<6} {'Roll-L4':<12} {'whiff':<7} {'xCON':<7} {'rp3':<5} Signals")
print(f"  {'-'*100}")

for sp in sp_names:
    inj = get_injury(sp)
    inj_tag = f" [{inj[:8]}]" if inj else ""
    sr = find_sp(sp)
    rr = find_roll(sp)
    rank = model_rank(sp, rp3)

    if sr is None:
        print(f"  {sp+inj_tag:<32} {'--':<4} {'no 2026 starts':>7}{'':>27} #{rank}")
        continue

    gs = int(sr["gs"])
    fpp = float(sr["fpp"])
    gsp = int(sr["good_starts"])
    pid = int(sr["pitcher"])
    st = find_stuff(pid)

    # Rolling window
    rtier = "---"
    if rr is not None:
        l4g = int(rr["l4_good"]) if rr["l4_good"] is not None else 0
        l4n = min(gs, 4)
        rtier = roll_tier(l4g, l4n)

    # whiff/xwOBA contact
    w_str = f"{float(st['whiff_pct']):.1f}%" if st is not None else "---"
    xc_val = float(st["xwoba_contact"]) if st is not None and st["xwoba_contact"] is not None else None
    xc_str = f"{xc_val:.3f}" if xc_val else "---"
    csw = float(st["csw_pct"]) if st is not None else 0
    whiff = float(st["whiff_pct"]) if st is not None else 0

    # Signals
    sigs = []
    # Signal A (MC-refined: fpp >= 0.02 AND whiff >= 26, 4-8 GS)
    if 4 <= gs <= 8:
        if fpp >= 0.02 and whiff >= 26:
            sigs.append("SigA-HIGH")
        elif fpp >= 0.00:
            sigs.append("SigA-WATCH")

    # Harrison: fp_proxy blind but stuff fires
    if fpp < -0.0476 and xc_val is not None:
        if (whiff >= 26 and xc_val <= 0.320) or (csw >= 30 and xc_val <= 0.310):
            sigs.append("HARRISON")

    # Velo concern: if we had it (placeholder)
    if fpp < -0.10 and gsp < gs // 2:
        sigs.append("CONCERN")

    sig_str = " ".join(sigs) if sigs else ""
    name_disp = (sp + inj_tag)[:30]
    print(f"  {name_disp:<30} {gs:<4} {fpp:>+6.3f}  {gsp}/{gs:<4} {rtier:<12} {w_str:<7} {xc_str:<7} #{rank:<4} {sig_str}")

print()
print("─" * 75)
print("RELIEF PITCHERS")
print("─" * 75)
# rprs2 col
rprs2_rank_col = "rank"
rprs2_name_col = "player_name" if "player_name" in rprs2.columns else rprs2.columns[0]

print(f"  {'Name':<24} {'Apps':<6} {'fpp/bf':<8} {'rprs2':<6} {'Role/Signal'}")
print(f"  {'-'*70}")

for rp in rp_names:
    inj = get_injury(rp)
    inj_tag = f" [{inj[:8]}]" if inj else ""
    rr = find_rp(rp)
    rank = model_rank(rp, rprs2)

    if rr is None:
        print(f"  {rp+inj_tag:<28} no RP data | rprs2 #{rank}")
        continue

    apps = int(rr["apps"])
    fpp = float(rr["fpp"])
    sigs = []
    if fpp >= 0.04 and apps >= 20:
        sigs.append("Signal-G(holds-elite)")
    elif fpp >= 0.02:
        sigs.append("solid")
    elif fpp < -0.05:
        sigs.append("struggling")

    name_disp = (rp + inj_tag)[:26]
    print(f"  {name_disp:<26} {apps:<6} {fpp:>+7.4f}  #{rank:<5} {' '.join(sigs)}")

print()
print("─" * 75)
print("HITTERS  (xwOBA: 2025 baseline → 2026 season → L21d | gap = L21d minus 2025)")
print("─" * 75)
print(f"  {'Name':<26} {'PA':<5} {'xwOBA25':<9} {'xwOBA26':<9} {'xwOBA-L21':<11} {'Δ vs 25':<9} {'EV90':<6} {'rh3':<5} Signal")
print(f"  {'-'*100}")

for hit in hit_names:
    inj = get_injury(hit)
    inj_tag = f" [{inj[:8]}]" if inj else ""
    hr = find_hitter(hit)
    rank = model_rank(hit, rh3)

    if hr is None:
        print(f"  {hit+inj_tag:<30} no Statcast data | rh3 #{rank}")
        continue

    pa = int(hr["pa"]) if hr["pa"] else 0
    xw25 = float(hr["xwoba_25"]) if hr["xwoba_25"] is not None else None
    xw26 = float(hr["xwoba_szn"]) if hr["xwoba_szn"] is not None else None
    xwl = float(hr["xwoba_l21d"]) if hr["xwoba_l21d"] is not None else None
    pal = int(hr["pa_l21d"]) if hr["pa_l21d"] is not None else 0
    ev90 = float(hr["ev90"]) if hr["ev90"] is not None else None

    delta = None
    if xwl is not None and xw25 is not None:
        delta = xwl - xw25

    sigs = []
    if delta is not None:
        if delta >= 0.050:
            sigs.append("BREAKOUT-watch")
        elif delta <= -0.060:
            sigs.append("DECLINE-risk")
        elif delta <= -0.030:
            sigs.append("slump-check")

    x25s = f"{xw25:.3f}" if xw25 else "---"
    x26s = f"{xw26:.3f}" if xw26 else "---"
    xls = f"{xwl:.3f}({pal}PA)" if xwl else "---"
    ds = f"{delta:+.3f}" if delta else "---"
    ev90s = f"{ev90:.1f}" if ev90 else "---"

    name_disp = (hit + inj_tag)[:28]
    print(f"  {name_disp:<28} {pa:<5} {x25s:<9} {x26s:<9} {xls:<13} {ds:<9} {ev90s:<6} #{rank:<4} {' '.join(sigs)}")

print()
print("=" * 75)
print("SUMMARY FLAGS")
print("=" * 75)
