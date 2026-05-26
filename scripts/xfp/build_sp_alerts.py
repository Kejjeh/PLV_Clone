"""
build_sp_alerts.py — daily SP and hitter upgrade alert generator.

SP: Signal H (roster upgrade) + Signal A HIGH (early-GS breakout)
Hitter: Signal I (roster upgrade — xwOBA + xwOBACON floor comparison)

Writes data/outputs/sp_alerts.json consumed by live_monitor.py dashboard.
Run as part of refresh_dashboards.py step 2.5.
"""
import sys, duckdb, json, unicodedata, re, pandas as pd
from pathlib import Path
from datetime import date

REPO = Path(r"c:\Users\Joshua\plv_clone")
sys.path.insert(0, str(REPO))
from app.espn_connector import get_my_roster_with_injuries, _get_league
from plv_clone.utils.name_match import lookup_batter_id_cached

PARQ26 = (REPO / "data/research/xfp_cache/statcast_2026.parquet").as_posix()
PARQ25 = (REPO / "data/research/xfp_cache/statcast_2025.parquet").as_posix()
rp3 = pd.read_csv(REPO / "data/outputs/xfp_rp3_projections.csv")
rh3 = pd.read_csv(REPO / "data/outputs/xfp_rh3_projections.csv")
OUT = REPO / "data/outputs/sp_alerts.json"


def _norm(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", s).strip()


def display_name(sc):
    if "," in sc:
        p = sc.split(",", 1)
        return p[1].strip() + " " + p[0].strip()
    return sc


def rp3_rank(name):
    last = _norm(name).split()[-1]
    m = rp3[rp3["player_name"].str.lower().str.contains(re.escape(last), na=False)]
    if len(m):
        return int(m["rank"].iloc[0])
    return 999


# ── Pull 2026 per-start stats for all pitchers ───────────────────────────────
print("Querying 2026 Statcast per-start stats...", flush=True)
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
    CASE WHEN (k-bb-h-hr)*1.0/NULLIF(bf,0) >= -0.0476 THEN 1 ELSE 0 END AS good
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

merged = sp_stats.merge(stuff, on="pitcher", how="left")
merged["display"] = merged["player_name"].apply(display_name)
merged["rank"] = merged["player_name"].apply(rp3_rank)
merged["whiff_pct"] = merged["whiff_pct"].fillna(0.0)
merged["xwoba_con"] = merged["xwoba_con"].fillna(0.400)

# ── Pull live roster ─────────────────────────────────────────────────────────
print("Pulling live roster...", flush=True)
roster = get_my_roster_with_injuries()
my_sps = roster[(roster["position"] == "SP") & (roster["lineup_slot"] != "IL")]
my_sp_names = set(my_sps["player_name"].tolist())

# compute fpp for each of my active SPs
def find_fpp(name):
    last = _norm(name).split()[-1]
    for _, r in merged.iterrows():
        if last in _norm(r["display"]):
            return float(r["fpp"])
    return -0.200  # default floor if no starts yet

my_sp_fpps = sorted([find_fpp(n) for n in my_sp_names])
# upgrade floor = 3rd-weakest (index 2) or weakest if fewer than 3
if len(my_sp_fpps) >= 3:
    upgrade_floor = my_sp_fpps[2]
else:
    upgrade_floor = my_sp_fpps[0] if my_sp_fpps else -0.100
print(f"  My active SP fpp values: {[round(f,4) for f in my_sp_fpps]}", flush=True)
print(f"  Upgrade floor (3rd-weakest): {upgrade_floor:+.4f}", flush=True)

# ── Pull FA SP pool ──────────────────────────────────────────────────────────
print("Pulling FA pool...", flush=True)
league = _get_league()
fas = league.free_agents(size=2000)
fa_sp_norm = {}
for p in fas:
    if getattr(p, "position", "") in ("SP", "P"):
        fa_sp_norm[_norm(p.name)] = p.name

def is_fa(sc_name):
    n = _norm(display_name(sc_name))
    if n in fa_sp_norm:
        return True
    parts = n.split()
    if len(parts) >= 2:
        last, fi = parts[-1], parts[0][0]
        for k in fa_sp_norm:
            kp = k.split()
            if len(kp) >= 2 and kp[-1] == last and kp[0][0] == fi:
                return True
    return False

fa_rows = merged[merged["player_name"].apply(is_fa)].copy()
print(f"  {len(fa_rows)} FA SPs with 4+ starts", flush=True)

# ── Apply signals ─────────────────────────────────────────────────────────────
alerts = []

for _, r in fa_rows.iterrows():
    gs    = int(r["gs"])
    fpp   = float(r["fpp"])
    gsp   = int(r["gsp"])
    l4g   = int(r["l4g"])
    l4n   = min(gs, 4)
    whiff = float(r["whiff_pct"])
    xcon  = float(r["xwoba_con"])
    rank  = int(r["rank"])
    disp  = r["display"]

    signal_a_high = (4 <= gs <= 8) and fpp >= 0.02 and whiff >= 26.0
    signal_a_watch = (4 <= gs <= 8) and fpp >= 0.00 and not signal_a_high

    fpp_gap = fpp - upgrade_floor
    signal_h_high   = fpp_gap >= 0.030 and rank <= 150 and gs >= 4
    signal_h_monitor = fpp_gap >= 0.015 and rank <= 200 and gs >= 4 and not signal_h_high

    if not (signal_a_high or signal_h_high or signal_h_monitor):
        continue

    tier = "HIGH" if (signal_a_high or signal_h_high) else "MONITOR"
    signals = []
    if signal_a_high:
        signals.append("SigA-HIGH")
    if signal_h_high:
        signals.append(f"SigH-HIGH(gap={fpp_gap:+.3f})")
    elif signal_h_monitor:
        signals.append(f"SigH-MONITOR(gap={fpp_gap:+.3f})")

    alerts.append({
        "name": disp,
        "tier": tier,
        "signals": signals,
        "gs": gs,
        "fpp": round(fpp, 4),
        "fpp_gap": round(fpp_gap, 4),
        "gsp": gsp,
        "l4": f"{l4g}/{l4n}",
        "whiff_pct": round(whiff, 1),
        "xwoba_con": round(xcon, 3),
        "rp3_rank": rank,
    })

alerts.sort(key=lambda x: (0 if x["tier"] == "HIGH" else 1, -x["fpp"]))

# ── Signal I: Hitter upgrade ──────────────────────────────────────────────────
print("\nComputing hitter upgrade alerts (Signal I)...", flush=True)

def rh3_rank(name):
    """Look up rh3 rank by batter ID first (accurate), fallback to last-name."""
    bid = None
    try:
        bid = lookup_batter_id_cached(name)
    except Exception:
        pass
    if bid and int(bid) in rh3_bid_to_rank:
        return int(rh3_bid_to_rank[int(bid)])
    # Fallback: exact player_name match
    m = rh3[rh3["player_name"] == name]
    if len(m):
        return int(m["rank"].iloc[0])
    return 999

my_hitters = roster[~roster["position"].isin(["SP", "RP"]) & (roster["lineup_slot"] != "IL")]
my_hit_names = my_hitters["player_name"].tolist()

# resolve batter IDs for my hitters
my_batter_ids = {}
for name in my_hit_names:
    team = roster[roster["player_name"] == name]["pro_team"].iloc[0] if len(roster[roster["player_name"] == name]) else None
    pos  = roster[roster["player_name"] == name]["position"].iloc[0] if len(roster[roster["player_name"] == name]) else None
    try:
        bid = lookup_batter_id_cached(name, team=team, position=pos)
        if bid:
            my_batter_ids[name] = int(bid)
    except Exception:
        pass

my_bids_str = ",".join(str(v) for v in my_batter_ids.values()) if my_batter_ids else "0"

my_hit_xwoba = con.execute(f"""
SELECT batter,
  AVG(CASE WHEN events IS NOT NULL AND events!='' AND estimated_woba_using_speedangle IS NOT NULL
           THEN estimated_woba_using_speedangle END) AS xwoba_szn,
  AVG(CASE WHEN events IS NOT NULL AND events!='' AND launch_speed IS NOT NULL
           AND estimated_woba_using_speedangle IS NOT NULL
           THEN estimated_woba_using_speedangle END) AS xwoba_con,
  COUNT(CASE WHEN events IS NOT NULL AND events!='' THEN 1 END) AS pa
FROM read_parquet('{PARQ26}')
WHERE batter IN ({my_bids_str}) AND game_date >= '2026-03-26'
GROUP BY batter
""").df() if my_batter_ids else pd.DataFrame(columns=["batter","xwoba_szn","xwoba_con","pa"])

bid_to_name = {v: k for k, v in my_batter_ids.items()}
my_xwobas = []
for _, r in my_hit_xwoba.iterrows():
    if r["pa"] and int(r["pa"]) >= 30 and r["xwoba_szn"] is not None:
        my_xwobas.append(float(r["xwoba_szn"]))
my_xwobas.sort()
hit_upgrade_floor = my_xwobas[2] if len(my_xwobas) >= 3 else (my_xwobas[0] if my_xwobas else 0.320)
print(f"  Hitter upgrade floor (3rd-weakest xwOBA): {hit_upgrade_floor:.3f}", flush=True)

# FA hitter pool — size 2000, position filter manually
fa_hitters = [p for p in fas if getattr(p, "position", "") not in ("SP", "RP", "P")]

# Pre-build rh3 batter-ID → rank lookup for accurate matching (avoids false
# last-name substring hits like "Alvarez" matching rank=1 for every player).
rh3_bid_to_rank = rh3.set_index("batter")["rank"].to_dict()

# get Statcast xwOBA for FA hitters by batter ID lookup (best-effort)
print(f"  Resolving batter IDs for {len(fa_hitters)} FA hitters (rh3 rank<=150 filter via batter ID)...", flush=True)

# Resolve FA hitter names → batter IDs; filter to rh3 rank<=150 via batter ID
fa_bid_map = {}  # bid → ESPN player name
n_ok = 0; n_fail = 0
for p in fa_hitters:
    try:
        bid = lookup_batter_id_cached(p.name)
        if bid and int(bid) in rh3_bid_to_rank and rh3_bid_to_rank[int(bid)] <= 150:
            fa_bid_map[int(bid)] = p.name
            n_ok += 1
        elif not bid:
            n_fail += 1
    except Exception:
        n_fail += 1
print(f"  Resolved {n_ok} FA hitters with rh3 rank<=150; {n_fail} failed ID resolution", flush=True)

hitter_alerts = []
if fa_bid_map:
    fa_bids_str = ",".join(str(b) for b in fa_bid_map)
    fa_hit_stats = con.execute(f"""
    SELECT batter,
      AVG(CASE WHEN events IS NOT NULL AND events!='' AND estimated_woba_using_speedangle IS NOT NULL
               THEN estimated_woba_using_speedangle END) AS xwoba_szn,
      AVG(CASE WHEN events IS NOT NULL AND events!='' AND launch_speed IS NOT NULL
               AND estimated_woba_using_speedangle IS NOT NULL
               THEN estimated_woba_using_speedangle END) AS xwoba_con,
      COUNT(CASE WHEN events IS NOT NULL AND events!='' THEN 1 END) AS pa
    FROM read_parquet('{PARQ26}')
    WHERE batter IN ({fa_bids_str}) AND game_date >= '2026-03-26'
    GROUP BY batter
    """).df()

    for _, r in fa_hit_stats.iterrows():
        bid = int(r["batter"])
        name = fa_bid_map.get(bid, str(bid))
        pa = int(r["pa"]) if r["pa"] is not None else 0
        if pa < 50:
            continue
        xwoba = float(r["xwoba_szn"]) if r["xwoba_szn"] is not None else None
        xcon  = float(r["xwoba_con"]) if r["xwoba_con"] is not None else None
        if xwoba is None or xcon is None or xcon < 0.350:
            continue
        gap = xwoba - hit_upgrade_floor
        rank = rh3_rank(name)
        if gap < 0.025 or rank > 150:
            continue
        tier = "HIGH" if gap >= 0.040 and rank <= 75 else "MONITOR"
        signals = [f"SigI-{tier}(gap={gap:+.3f})"]
        hitter_alerts.append({
            "name": name,
            "tier": tier,
            "signals": signals,
            "pa": pa,
            "xwoba_szn": round(xwoba, 3),
            "xwoba_gap": round(gap, 3),
            "xwoba_con": round(xcon, 3),
            "rh3_rank": rank,
        })

hitter_alerts.sort(key=lambda x: (0 if x["tier"] == "HIGH" else 1, -x["xwoba_szn"]))
con.close()

# ── Write output ──────────────────────────────────────────────────────────────
payload = {
    "generated": str(date.today()),
    "upgrade_floor_fpp": round(upgrade_floor, 4),
    "hit_upgrade_floor_xwoba": round(hit_upgrade_floor, 3),
    "alert_count": len(alerts),
    "hitter_alert_count": len(hitter_alerts),
    "alerts": alerts,
    "hitter_alerts": hitter_alerts,
    "my_active_sp_count": len(my_sp_fpps),
}

OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(f"\n  {len(alerts)} SP alerts + {len(hitter_alerts)} hitter alerts -> {OUT}", flush=True)

# ── Console summary ───────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print(f"SP UPGRADE ALERTS — {date.today()}  (floor: {upgrade_floor:+.4f})")
print(f"{'='*70}")
if not alerts:
    print("  No FA SP upgrades detected.")
else:
    print(f"  {'Player':<26} {'Tier':<8} {'GS':<4} {'fpp':<8} {'L4':<5} "
          f"{'whiff':<7} {'xCON':<7} {'rp3':<5} Signals")
    print(f"  {'-'*85}")
    for a in alerts:
        print(f"  {a['name']:<26} {a['tier']:<8} {a['gs']:<4} {a['fpp']:>+7.4f}  "
              f"{a['l4']:<5} {a['whiff_pct']:>5.1f}%  {a['xwoba_con']:<7.3f} "
              f"#{a['rp3_rank']:<4} {' '.join(a['signals'])}")

print(f"\n{'='*70}")
print(f"HITTER UPGRADE ALERTS — {date.today()}  (floor xwOBA: {hit_upgrade_floor:.3f})")
print(f"{'='*70}")
if not hitter_alerts:
    print("  No FA hitter upgrades detected.")
else:
    print(f"  {'Player':<26} {'Tier':<8} {'PA':<5} {'xwOBA':<7} {'gap':<7} {'xCON':<7} {'rh3':<5}")
    print(f"  {'-'*70}")
    for a in hitter_alerts:
        print(f"  {a['name']:<26} {a['tier']:<8} {a['pa']:<5} {a['xwoba_szn']:.3f}   "
              f"{a['xwoba_gap']:+.3f}   {a['xwoba_con']:.3f}   #{a['rh3_rank']}")
