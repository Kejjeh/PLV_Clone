"""Ligers hitter xwOBA/EV signal evaluation with Bayesian shrinkage."""
import sys, duckdb, pandas as pd
sys.path.insert(0, r"c:\Users\Joshua\plv_clone")

PARQ26 = r"c:\Users\Joshua\plv_clone\data\research\xfp_cache\statcast_2026.parquet"
PARQ25 = r"c:\Users\Joshua\plv_clone\data\research\xfp_cache\statcast_2025.parquet"
rh3 = pd.read_csv(r"c:\Users\Joshua\plv_clone\data\outputs\xfp_rh3_projections.csv")
rprs2 = pd.read_csv(r"c:\Users\Joshua\plv_clone\data\outputs\xfp_rprs2_projections.csv")

hitters = {
    "Aaron Judge":           (592450, "NYY", "RF"),
    "Vladimir Guerrero Jr.": (665489, "TOR", "1B"),
    "Corbin Carroll":        (682998, "ARI", "RF"),
    "Elly De La Cruz":       (682829, "CIN", "SS"),
    "Trea Turner":           (607208, "PHI", "SS"),
    "Pete Alonso":           (624413, "NYM", "1B"),
    "Luis Arraez":           (650333, "SDP", "2B"),
    "Salvador Perez":        (521692, "KCR", "C"),
    "Bo Bichette":           (666182, "TOR", "SS"),
    "Michael Harris II":     (671739, "ATL", "CF"),
    "Jordan Walker":         (691023, "STL", "RF"),
    "Max Muncy":             (571970, "LAD", "3B"),
    "Wyatt Langford":        (694671, "TEX", "LF"),
}
il_players = {"Wyatt Langford"}
ids_str = ",".join(str(v[0]) for v in hitters.values())

con = duckdb.connect()

df26 = con.execute(f"""
SELECT batter,
  COUNT(CASE WHEN events IS NOT NULL AND events!='' THEN 1 END) AS pa,
  AVG(CASE WHEN events IS NOT NULL AND events!='' AND estimated_woba_using_speedangle IS NOT NULL
           THEN estimated_woba_using_speedangle END) AS xwoba_szn,
  AVG(CASE WHEN game_date::DATE >= '2026-05-04' AND events IS NOT NULL AND events!=''
           AND estimated_woba_using_speedangle IS NOT NULL
           THEN estimated_woba_using_speedangle END) AS xwoba_l21d,
  COUNT(CASE WHEN game_date::DATE >= '2026-05-04' AND events IS NOT NULL AND events!='' THEN 1 END) AS pa_l21d,
  PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY launch_speed)
    FILTER (WHERE launch_speed IS NOT NULL AND events IS NOT NULL AND events!='') AS ev90,
  AVG(CASE WHEN bat_speed IS NOT NULL AND description IN (
    'swinging_strike','swinging_strike_bounded','foul_tip','foul','hit_into_play','foul_bunt','missed_bunt'
  ) THEN bat_speed END) AS avg_batspeed,
  COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_bounded','foul_tip') THEN 1 END)*100.0/
    NULLIF(COUNT(CASE WHEN description IN (
      'swinging_strike','swinging_strike_bounded','foul_tip','foul','hit_into_play','foul_bunt','missed_bunt'
    ) THEN 1 END), 0) AS whiff_pct,
  AVG(CASE WHEN events IS NOT NULL AND events!='' AND launch_speed IS NOT NULL
           AND estimated_woba_using_speedangle IS NOT NULL
           THEN estimated_woba_using_speedangle END) AS xwoba_con
FROM read_parquet('{PARQ26}')
WHERE batter IN ({ids_str}) AND game_date >= '2026-03-26'
GROUP BY batter
""").df()

df25 = con.execute(f"""
SELECT batter,
  AVG(CASE WHEN events IS NOT NULL AND events!='' AND estimated_woba_using_speedangle IS NOT NULL
           THEN estimated_woba_using_speedangle END) AS xwoba_25,
  AVG(CASE WHEN events IS NOT NULL AND events!='' AND launch_speed IS NOT NULL
           AND estimated_woba_using_speedangle IS NOT NULL
           THEN estimated_woba_using_speedangle END) AS xwoba_con_25,
  COUNT(CASE WHEN events IS NOT NULL AND events!='' THEN 1 END) AS pa_25
FROM read_parquet('{PARQ25}')
WHERE batter IN ({ids_str})
GROUP BY batter
""").df()

con.close()

merged = df26.merge(df25, on="batter", how="left")
id_to_name = {v[0]: k for k, v in hitters.items()}


def rh3_rank(name):
    last = name.split()[-1].lower()
    m = rh3[rh3["player_name"].str.lower().str.contains(last, na=False)]
    if len(m):
        return int(m["rank"].iloc[0])
    return 999


print()
print("=" * 90)
print("LIGERS HITTERS — xwOBA signal evaluation (2026-05-25)")
print("Breakout: shrunk Δ >= +0.030 | Decline: Δ vs 25 <= -0.060 | Slump: Δ <= -0.030")
print("=" * 90)
print(f"  {'Name':<26} {'PA':<5} {'xw25':<7} {'xwSzn':<7} {'xwL21':<7} {'ΔL21-25':<8} {'shrunk':<8} {'EV90':<6} {'BatSpd':<7} {'#rh3':<5} Signal")
print(f"  {'-'*100}")

for _, row in merged.sort_values("batter").iterrows():
    bid = int(row["batter"])
    name = id_to_name.get(bid, str(bid))
    inj_tag = " [IL10]" if name in il_players else ""

    pa    = int(row["pa"]) if row["pa"] is not None else 0
    xw25  = float(row["xwoba_25"]) if row["xwoba_25"] is not None else None
    xw26  = float(row["xwoba_szn"]) if row["xwoba_szn"] is not None else None
    xwl   = float(row["xwoba_l21d"]) if row["xwoba_l21d"] is not None else None
    xwcon = float(row["xwoba_con"]) if row["xwoba_con"] is not None else None
    xwcon25 = float(row["xwoba_con_25"]) if row["xwoba_con_25"] is not None else None
    pal   = int(row["pa_l21d"]) if row["pa_l21d"] is not None else 0
    ev90  = float(row["ev90"]) if row["ev90"] is not None else None
    bs    = float(row["avg_batspeed"]) if row["avg_batspeed"] is not None else None

    delta = (xwl - xw25) if xwl is not None and xw25 is not None else None

    # Bayesian shrinkage (k=150)
    shrunk_gap = None
    if xwl is not None and xw25 is not None and pal >= 10:
        k = 150
        shrunk = (pal * xwl + k * xw25) / (pal + k)
        shrunk_gap = shrunk - xw25

    sigs = []
    if pal < 15:
        sigs.append(f"tiny-L21({pal}PA)")
    elif shrunk_gap is not None:
        if shrunk_gap >= 0.030:
            sigs.append("BREAKOUT-watch")
        elif delta is not None and delta <= -0.060:
            sigs.append("DECLINE-risk")
        elif delta is not None and delta <= -0.030:
            sigs.append("slump-check")

    rank = rh3_rank(name)

    x25s  = f"{xw25:.3f}" if xw25 else "---"
    x26s  = f"{xw26:.3f}" if xw26 else "---"
    xls   = f"{xwl:.3f}" if xwl else "---"
    ds    = f"{delta:+.3f}" if delta is not None else "---"
    sgs   = f"{shrunk_gap:+.3f}" if shrunk_gap is not None else "---"
    ev90s = f"{ev90:.1f}" if ev90 else "---"
    bss   = f"{bs:.1f}" if bs else "---"

    nd = (name + inj_tag)[:28]
    print(f"  {nd:<28} {pa:<5} {x25s:<7} {x26s:<7} {xls:<7} {ds:<8} {sgs:<8} {ev90s:<6} {bss:<7} #{rank:<4} {' '.join(sigs)}")

print()
print("=" * 90)
print("xwOBACON comparison (contact quality, 2025 vs 2026 season)")
print("=" * 90)
print(f"  {'Name':<26} {'xwCON25':<9} {'xwCON26':<9} {'Δ-CON'}")
print(f"  {'-'*55}")
for _, row in merged.sort_values("batter").iterrows():
    bid = int(row["batter"])
    name = id_to_name.get(bid, str(bid))
    xc25 = float(row["xwoba_con_25"]) if row["xwoba_con_25"] is not None else None
    xc26 = float(row["xwoba_con"]) if row["xwoba_con"] is not None else None
    delta_c = (xc26 - xc25) if xc26 is not None and xc25 is not None else None
    ds = f"{delta_c:+.3f}" if delta_c is not None else "---"
    print(f"  {name:<26} {(str(round(xc25,3)) if xc25 else '---'):<9} {(str(round(xc26,3)) if xc26 else '---'):<9} {ds}")
