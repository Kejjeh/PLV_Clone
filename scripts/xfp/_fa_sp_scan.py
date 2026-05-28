"""FA SP availability scan with Signal A and rolling window."""
import sys, duckdb, pandas as pd, unicodedata, re
sys.path.insert(0, r"c:\Users\Joshua\plv_clone")
from app.espn_connector import _get_league

PARQ26 = r"c:\Users\Joshua\plv_clone\data\research\xfp_cache\statcast_2026.parquet"
rp3 = pd.read_csv(r"c:\Users\Joshua\plv_clone\data\outputs\xfp_rp3_projections.csv")

def _norm(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", s).strip()

def display_name(sc):
    if "," in sc:
        p = sc.split(",", 1)
        return p[1].strip() + " " + p[0].strip()
    return sc

print("Loading FA pool...", flush=True)
league = _get_league()
fas = league.free_agents(size=2000)
fa_sps = {}
for p in fas:
    if getattr(p, "position", "") in ("SP", "P"):
        fa_sps[_norm(p.name)] = p

print(f"  {len(fa_sps)} FA SPs found", flush=True)

con = duckdb.connect()

sp_stats = con.execute(f"""
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
    CASE WHEN (k-bb-h-hr)*1.0/NULLIF(bf,0)>=-0.0476 THEN 1 ELSE 0 END AS good
  FROM starts
)
SELECT pitcher, player_name,
  COUNT(*) AS gs,
  ROUND((SUM(k)-SUM(bb)-SUM(h)-SUM(hr))*1.0/NULLIF(SUM(bf),0), 4) AS fpp,
  SUM(good) AS gsp,
  SUM(CASE WHEN rn<=4 THEN good ELSE 0 END) AS l4g
FROM ranked
GROUP BY pitcher, player_name
HAVING COUNT(*) >= 4
ORDER BY fpp DESC
""").df()

stuff = con.execute(f"""
SELECT pitcher,
  COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_bounded','foul_tip') THEN 1 END)*100.0/
    NULLIF(COUNT(CASE WHEN description IN (
      'swinging_strike','swinging_strike_bounded','foul_tip','foul','hit_into_play','foul_bunt','missed_bunt'
    ) THEN 1 END), 0) AS whiff_pct,
  AVG(CASE WHEN launch_speed IS NOT NULL AND estimated_woba_using_speedangle IS NOT NULL
           THEN estimated_woba_using_speedangle END) AS xwoba_con
FROM read_parquet('{PARQ26}')
WHERE game_date >= '2026-03-26'
GROUP BY pitcher
""").df()

con.close()

merged = sp_stats.merge(stuff, on="pitcher", how="left")

def rp3_rank(sc_name):
    n = _norm(display_name(sc_name))
    last = n.split()[-1]
    m = rp3[rp3["player_name"].str.lower().str.contains(last, na=False)]
    if len(m):
        return int(m["rank"].iloc[0])
    return 999

# filter to FAs only — two-pass name match
def is_fa(sc_name):
    n = _norm(display_name(sc_name))
    if n in fa_sps:
        return True
    last = n.split()[-1]
    first_init = n.split()[0][0] if n.split() else ""
    for k in fa_sps:
        kparts = k.split()
        if kparts and kparts[-1] == last and kparts[0][0] == first_init:
            return True
    return False

fa_rows = merged[merged["player_name"].apply(is_fa)].copy()
fa_rows["rank"] = fa_rows["player_name"].apply(rp3_rank)
fa_rows["display"] = fa_rows["player_name"].apply(display_name)

print()
print("=" * 80)
print("FA SPs with 4+ starts in 2026 — sorted by fpp (best first)")
print("Signal A threshold (MC-refined): fpp >= +0.02 AND whiff >= 26%")
print("=" * 80)
print(f"  {'Player':<26} {'GS':<4} {'fpp':<8} {'GS+':<5} {'L4':<5} {'whiff':<7} {'xCON':<7} {'rp3':<5} Signal")
print(f"  {'-'*85}")

shown = 0
for _, r in fa_rows.sort_values("fpp", ascending=False).iterrows():
    gs   = int(r["gs"])
    fpp  = float(r["fpp"])
    gsp  = int(r["gsp"])
    l4g  = int(r["l4g"]) if r["l4g"] is not None else 0
    l4n  = min(gs, 4)
    whiff = float(r["whiff_pct"]) if r["whiff_pct"] is not None else 0.0
    xcon  = float(r["xwoba_con"]) if r["xwoba_con"] is not None else None
    rank  = int(r["rank"])
    disp  = r["display"][:26]
    xcs   = f"{xcon:.3f}" if xcon else "---"

    siga = ""
    if 4 <= gs <= 8:
        if fpp >= 0.02 and whiff >= 26:
            siga = "SigA-HIGH"
        elif fpp >= 0.00:
            siga = "SigA-watch"

    roll = f"{l4g}/{l4n}"

    print(f"  {disp:<26} {gs:<4} {fpp:>+7.4f}  {gsp}/{gs:<3} {roll:<5} {whiff:>5.1f}%  {xcs:<7} #{rank:<4} {siga}")
    shown += 1
    if shown >= 30:
        break

# Also show Signal A candidates specifically
print()
print("── Signal A HIGH fires (FA only) ──────────────────────────────────────────")
siga_rows = fa_rows[
    (fa_rows["gs"].between(4, 8)) &
    (fa_rows["fpp"] >= 0.02) &
    (fa_rows["whiff_pct"] >= 26)
].sort_values("fpp", ascending=False)
if len(siga_rows) == 0:
    print("  (none meeting both fpp>=+0.02 AND whiff>=26 in 4-8 GS window)")
else:
    for _, r in siga_rows.iterrows():
        print(f"  {r['display'][:26]:<26} GS={int(r['gs'])} fpp={float(r['fpp']):+.4f} whiff={float(r['whiff_pct']):.1f}% rp3#{int(r['rank'])}")
