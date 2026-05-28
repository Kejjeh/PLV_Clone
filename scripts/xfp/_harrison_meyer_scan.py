"""
Scan for next Kyle Harrison / Max Meyer:
  - Kyle Harrison archetype: high whiff%, high BABIP masking elite soft contact.
    fp_proxy never fired (too many H). stuff_contact_composite fires 35 days earlier.
  - Max Meyer archetype: young SP, first 3-8 starts, raw stuff elite, fp_proxy
    may not have enough sample yet but xwOBA-on-contact already screams.

For every SP with 4-12 GS in 2026, compute per-start:
  whiff%, CSW%, xwOBA-on-contact, avg EV, BABIP-proxy, fp_proxy
Then apply stuff_contact_composite signal and flag candidates.
"""
import sys, duckdb, pandas as pd, unicodedata, re
from pathlib import Path

REPO = Path(r"c:\Users\Joshua\plv_clone")
sys.path.insert(0, str(REPO))

PARQ = (REPO / "data/research/xfp_cache/statcast_2026.parquet").as_posix()
rp3  = pd.read_csv(REPO / "data/outputs/xfp_rp3_projections.csv")

from app.espn_connector import _get_league


def _norm(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", s).strip()


print("Loading ESPN roster data...", flush=True)
league = _get_league()
rostered = set()
for team in league.teams:
    for p in team.roster:
        rostered.add(_norm(p.name))
        rostered.add(p.name.split()[-1].lower())  # last-name fallback


def roster_tag(sc_name):
    """'Last, First' → display → check rostered set → return team or FA"""
    if "," in sc_name:
        parts = sc_name.split(",", 1)
        display = parts[1].strip() + " " + parts[0].strip()
    else:
        display = sc_name
    n = _norm(display)
    last = display.split()[-1].lower()
    for team in league.teams:
        for p in team.roster:
            if _norm(p.name) == n or p.name.split()[-1].lower() == last:
                return team.team_name
    return "FA"


con = duckdb.connect()

# ── Season-level fp_proxy (BF >= 10 per game, grouped by pitcher/season) ─────
print("Computing season fp_proxy per pitcher...", flush=True)
season_fpp = con.execute(f"""
    WITH starts AS (
      SELECT pitcher, player_name,
        game_date::DATE AS gd,
        COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) AS bf,
        SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
        SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
        SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
        SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr
      FROM read_parquet('{PARQ}')
      WHERE game_date >= '2026-03-26'
      GROUP BY pitcher, player_name, game_date::DATE
      HAVING COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) >= 10
    )
    SELECT pitcher, player_name,
      COUNT(*) AS gs,
      SUM(bf) AS tot_bf,
      SUM(k) AS tot_k, SUM(bb) AS tot_bb, SUM(h) AS tot_h, SUM(hr) AS tot_hr,
      ROUND((SUM(k)-SUM(bb)-SUM(h)-SUM(hr))*1.0/NULLIF(SUM(bf),0), 4) AS fpp_season,
      -- Good-start count (per-start threshold = -0.0476)
      SUM(CASE WHEN (k-bb-h-hr)*1.0/NULLIF(bf,0) >= -0.0476 THEN 1 ELSE 0 END) AS good_starts
    FROM starts
    GROUP BY pitcher, player_name
    HAVING COUNT(*) BETWEEN 4 AND 15
    ORDER BY fpp_season ASC   -- sort worst first: fp_proxy blind spots at top
""").df()

print(f"  {len(season_fpp)} pitchers with 4-15 GS in 2026", flush=True)

# ── Per-start stuff_contact metrics ──────────────────────────────────────────
print("Computing stuff+contact metrics...", flush=True)

# We need per-pitcher season aggregates for:
#   whiff% = swinging_strike / swings
#   CSW%   = (swinging_strike + called_strike) / total pitches
#   xwOBA-on-contact = avg estimated_woba_using_speedangle on batted balls
#   avg EV on contact
#   BABIP proxy = H / (BF - K - BB - HR)  [already have components]

stuff = con.execute(f"""
    SELECT pitcher,
      -- Whiff%
      COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_bounded','foul_tip') THEN 1 END)
        * 100.0 /
        NULLIF(COUNT(CASE WHEN description IN (
          'swinging_strike','swinging_strike_bounded','foul_tip',
          'foul','hit_into_play','foul_bunt','missed_bunt'
        ) THEN 1 END), 0) AS whiff_pct,
      -- CSW%
      COUNT(CASE WHEN description IN (
        'swinging_strike','swinging_strike_bounded','foul_tip','called_strike'
      ) THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) AS csw_pct,
      -- xwOBA on contact (batted balls only)
      AVG(CASE WHEN launch_speed IS NOT NULL AND estimated_woba_using_speedangle IS NOT NULL
               THEN estimated_woba_using_speedangle END) AS xwoba_contact,
      -- Avg EV on contact
      AVG(CASE WHEN launch_speed IS NOT NULL THEN launch_speed END) AS avg_ev,
      -- Count of batted balls (for sample size)
      COUNT(CASE WHEN launch_speed IS NOT NULL THEN 1 END) AS n_contact
    FROM read_parquet('{PARQ}')
    WHERE game_date >= '2026-03-26'
    GROUP BY pitcher
""").df()

# ── Per-start BABIP (need hits and BIP) ──────────────────────────────────────
# BABIP = (H - HR) / (BF - K - BB - HR) using season totals
# Already in season_fpp: h, hr, k, bb, bf

df = season_fpp.merge(stuff, on="pitcher", how="left")
df["babip"] = (df["tot_h"] - df["tot_hr"]) / (
    df["tot_bf"] - df["tot_k"] - df["tot_bb"] - df["tot_hr"]
).clip(lower=1)
df["fp_proxy_fired"] = df["fpp_season"] >= -0.0476
df["rolling_L4"] = (df["good_starts"] / df["gs"].clip(lower=1)).round(2)

# ── stuff_contact_composite signal ───────────────────────────────────────────
# Fires when:
#   (whiff_pct >= 26 AND xwoba_contact <= 0.320)
#   OR (csw_pct >= 30 AND xwoba_contact <= 0.310)
# Trigger condition A (BABIP case): BABIP > 0.350 AND (avg_ev < 87 OR xwoba_contact < 0.310)
# Trigger condition B (fp_proxy blind spot): gs >= 6 AND no fp_proxy fire AND whiff >= 26 sustained

df["composite_fires"] = (
    ((df["whiff_pct"] >= 26) & (df["xwoba_contact"] <= 0.320)) |
    ((df["csw_pct"] >= 30) & (df["xwoba_contact"] <= 0.310))
)
df["babip_case"] = (df["babip"] > 0.350) & (
    (df["avg_ev"] < 87) | (df["xwoba_contact"] < 0.310)
)
df["blind_spot_case"] = (
    (df["gs"] >= 6) & (~df["fp_proxy_fired"]) & (df["whiff_pct"] >= 26)
)
df["harrison_candidate"] = df["composite_fires"] & (df["babip_case"] | df["blind_spot_case"])

# ── Meyer archetype: early GS (4-8), fp_proxy fired immediately ─────────────
df["meyer_candidate"] = (
    (df["gs"] <= 8) & df["fp_proxy_fired"] &
    (df["fpp_season"] >= 0.04) &
    (df["whiff_pct"] >= 24)
)

# ── Roster tag + rp3 rank ────────────────────────────────────────────────────
print("Tagging roster status and model ranks...", flush=True)

def get_rp3_rank(sc_name):
    last = sc_name.split(",")[0].strip().split()[-1].lower() if sc_name else ""
    m = rp3[rp3["player_name"].str.lower().str.contains(last, na=False)]
    return int(m["rank"].iloc[0]) if len(m) else 999

tags, ranks = [], []
for _, row in df.iterrows():
    tags.append(roster_tag(row["player_name"]))
    ranks.append(get_rp3_rank(row["player_name"]))

df["team_2026"] = tags
df["rp3_rank"] = ranks

def display_name(sc):
    if "," in sc:
        p = sc.split(",", 1)
        return p[1].strip() + " " + p[0].strip()
    return sc

df["display"] = df["player_name"].apply(display_name)

# ── Print ─────────────────────────────────────────────────────────────────────
cols = ["display","team_2026","gs","fpp_season","good_starts",
        "whiff_pct","csw_pct","xwoba_contact","avg_ev","babip","rp3_rank"]

print("\n" + "="*75)
print("KYLE HARRISON ARCHETYPE — composite fires, fp_proxy blind/slow")
print("high whiff + elite contact suppression + BABIP or walk drag hiding it")
print("="*75)
harrison = df[df["harrison_candidate"]].sort_values("xwoba_contact")
if len(harrison) == 0:
    print("  (no candidates meeting threshold)")
else:
    print(f"  {'Player':<26} {'Team':<25} GS  fpp/bf  GS+ whiff  CSW xwCON  AvEV  BABIP rp3")
    print(f"  {'-'*100}")
    for _, r in harrison.iterrows():
        fa_tag = "** FA **" if r["team_2026"] == "FA" else r["team_2026"][:18]
        print(f"  {r['display']:<26} {fa_tag:<25} {int(r['gs']):>2}"
              f"  {r['fpp_season']:>+6.3f}  {int(r['good_starts']):>2}"
              f"  {r['whiff_pct']:>5.1f}  {r['csw_pct']:>4.1f}"
              f"  {r['xwoba_contact']:>5.3f}  {r['avg_ev']:>4.1f}  {r['babip']:>5.3f}"
              f"  #{r['rp3_rank']}")

print("\n" + "="*75)
print("MAX MEYER ARCHETYPE — early GS (<=8), fp_proxy already fired, high whiff")
print("strong first-start signal, model may not have caught up yet")
print("="*75)
meyer = df[df["meyer_candidate"]].sort_values("fpp_season", ascending=False)
if len(meyer) == 0:
    print("  (no candidates meeting threshold)")
else:
    print(f"  {'Player':<26} {'Team':<25} GS  fpp/bf  GS+ whiff  CSW xwCON  AvEV  BABIP rp3")
    print(f"  {'-'*100}")
    for _, r in meyer.iterrows():
        fa_tag = "** FA **" if r["team_2026"] == "FA" else r["team_2026"][:18]
        print(f"  {r['display']:<26} {fa_tag:<25} {int(r['gs']):>2}"
              f"  {r['fpp_season']:>+6.3f}  {int(r['good_starts']):>2}"
              f"  {r['whiff_pct']:>5.1f}  {r['csw_pct']:>4.1f}"
              f"  {r['xwoba_contact']:>5.3f}  {r['avg_ev']:>4.1f}  {r['babip']:>5.3f}"
              f"  #{r['rp3_rank']}")

print("\n" + "="*75)
print("ALL SPs 4-15 GS — sorted by xwOBA-on-contact ASC (best contact suppression)")
print("(reference table — full field)")
print("="*75)
all_sorted = df[df["n_contact"] >= 20].sort_values("xwoba_contact")
print(f"  {'Player':<26} {'Team':<22} GS  fpp/bf  GS+ whiff  CSW xwCON  AvEV  BABIP rp3  flags")
print(f"  {'-'*110}")
for _, r in all_sorted.head(40).iterrows():
    fa_tag = "FA" if r["team_2026"] == "FA" else r["team_2026"][:15]
    flags = ""
    if r["harrison_candidate"]: flags += " HARRISON"
    if r["meyer_candidate"]:    flags += " MEYER"
    if r["composite_fires"] and not r["harrison_candidate"] and not r["meyer_candidate"]:
        flags += " composite"
    print(f"  {r['display']:<26} {fa_tag:<22} {int(r['gs']):>2}"
          f"  {r['fpp_season']:>+6.3f}  {int(r['good_starts']):>2}"
          f"  {r['whiff_pct']:>5.1f}  {r['csw_pct']:>4.1f}"
          f"  {r['xwoba_contact']:>5.3f}  {r['avg_ev']:>4.1f}  {r['babip']:>5.3f}"
          f"  #{r['rp3_rank']}{flags}")

con.close()
