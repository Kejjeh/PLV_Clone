"""
Full-league retroactive signal audit.
For every player currently in the 2026 BrownU league (all 8 teams + top FA pool),
check whether they were undrafted in 2024 or 2025, and if so, what their
performance was and whether our signals would have caught them.
"""
import sys, duckdb, pandas as pd, unicodedata, re
from pathlib import Path

REPO = Path(r"c:\Users\Joshua\plv_clone")
sys.path.insert(0, str(REPO))
from app.espn_connector import _get_league

PARQ24 = (REPO / "data/research/xfp_cache/statcast_2024.parquet").as_posix()
PARQ25 = (REPO / "data/research/xfp_cache/statcast_2025.parquet").as_posix()

d24 = pd.read_csv(REPO / "data/reference/league_history/draft_2024.csv")
d25 = pd.read_csv(REPO / "data/reference/league_history/draft_2025.csv")
rp3   = pd.read_csv(REPO / "data/outputs/xfp_rp3_projections.csv")
rh3   = pd.read_csv(REPO / "data/outputs/xfp_rh3_projections.csv")
rprs2 = pd.read_csv(REPO / "data/outputs/xfp_rprs2_projections.csv")


def _norm(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", s).strip()


drafted_2024 = {_norm(n) for n in d24["player_name"]}
drafted_2025 = {_norm(n) for n in d25["player_name"]}


def was_drafted(name, dset):
    n = _norm(name)
    if n in dset:
        return True
    last = n.split()[-1]
    if len(last) >= 4:
        return any(last == _norm(d).split()[-1] for d in dset)
    return False


def model_rank(last):
    last = last.lower()
    nc_r = "name_api" if "name_api" in rprs2.columns else "player_name"
    m = rprs2[rprs2[nc_r].str.lower().str.contains(last, na=False)]
    if len(m):
        return ("rprs2", int(m["rank"].iloc[0]))
    m = rp3[rp3["player_name"].str.lower().str.contains(last, na=False)]
    if len(m):
        return ("rp3", int(m["rank"].iloc[0]))
    m = rh3[rh3["player_name"].str.lower().str.contains(last, na=False)]
    if len(m):
        return ("rh3", int(m["rank"].iloc[0]))
    return (None, 999)


print("Connecting to ESPN...", flush=True)
league = _get_league()

all_players = {}
for team in league.teams:
    for p in team.roster:
        all_players[p.name] = {"team": team.team_name, "pos": getattr(p, "position", "?")}

fas = league.free_agents(size=500)
for p in fas:
    if p.name not in all_players:
        all_players[p.name] = {"team": "FA", "pos": getattr(p, "position", "?")}

rostered_n = sum(1 for v in all_players.values() if v["team"] != "FA")
fa_n = sum(1 for v in all_players.values() if v["team"] == "FA")
print(f"Total players: {len(all_players)}  ({rostered_n} rostered, {fa_n} FA)", flush=True)

con = duckdb.connect()


def get_name_map(parq):
    return con.execute(f"""
        SELECT DISTINCT player_name,
          COALESCE(CAST(batter AS VARCHAR), CAST(pitcher AS VARCHAR)) AS pid
        FROM (
          SELECT player_name, batter, NULL::INT AS pitcher
          FROM read_parquet('{parq}') WHERE batter IS NOT NULL
          UNION ALL
          SELECT player_name, NULL::INT AS batter, pitcher
          FROM read_parquet('{parq}') WHERE pitcher IS NOT NULL
        )
    """).df()


print("Building name maps...", flush=True)
nmap24 = get_name_map(PARQ24)
nmap25 = get_name_map(PARQ25)


def sc_key(s):
    if "," in s:
        parts = s.split(",", 1)
        return _norm(parts[1].strip() + " " + parts[0].strip())
    return _norm(s)


sc24 = {sc_key(r["player_name"]): r["player_name"] for _, r in nmap24.iterrows()}
sc25 = {sc_key(r["player_name"]): r["player_name"] for _, r in nmap25.iterrows()}


def find_sc_name(display, sc_map):
    n = _norm(display)
    if n in sc_map:
        return sc_map[n]
    last = n.split()[-1]
    if len(last) >= 4:
        for k, v in sc_map.items():
            if k.split()[-1] == last:
                return v
    return None


def pitch_stats(sc_name, parq):
    safe = sc_name.replace("'", "''")
    df = con.execute(f"""
        WITH raw AS (
          SELECT pitcher,
            COUNT(DISTINCT game_date::DATE) AS apps,
            COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) AS bf,
            SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
            SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
            SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
            SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr,
            COUNT(DISTINCT CASE WHEN inning=1 THEN game_date::DATE END) AS gs_est
          FROM read_parquet('{parq}')
          WHERE player_name = '{safe}'
          GROUP BY pitcher
        )
        SELECT *, ROUND((k-bb-h-hr)*1.0/NULLIF(bf,0),4) AS fpp
        FROM raw
    """).df()
    if len(df) == 0:
        return None
    r = df.iloc[0]
    return {"apps": int(r["apps"]), "bf": int(r["bf"]), "fpp": float(r["fpp"]),
            "k": int(r["k"]), "gs_est": int(r["gs_est"])}


def hit_stats(sc_name, parq):
    safe = sc_name.replace("'", "''")
    df = con.execute(f"""
        SELECT
          COUNT(*) FILTER (WHERE events IS NOT NULL AND events != '') AS pa,
          AVG(estimated_woba_using_speedangle) FILTER (
            WHERE events IS NOT NULL AND events != ''
            AND estimated_woba_using_speedangle IS NOT NULL
          ) AS xwoba,
          SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr,
          SUM(CASE WHEN events='stolen_base' THEN 1 ELSE 0 END) AS sb
        FROM read_parquet('{parq}')
        WHERE player_name = '{safe}'
    """).df()
    if len(df) == 0:
        return None
    r = df.iloc[0]
    if r["pa"] is None or int(r["pa"]) < 20:
        return None
    return {"pa": int(r["pa"]),
            "xwoba": float(r["xwoba"]) if r["xwoba"] is not None else None,
            "hr": int(r["hr"]), "sb": int(r["sb"])}


print("Scanning all players...", flush=True)
rows = []
for name, meta in all_players.items():
    last = _norm(name).split()[-1]
    if len(last) < 3:
        continue
    model, mrank = model_rank(last)
    is_pitcher = meta["pos"] in ("SP", "RP", "P")

    for year, parq, sc_map, drafted in [
        (2024, PARQ24, sc24, drafted_2024),
        (2025, PARQ25, sc25, drafted_2025),
    ]:
        drafted_yn = was_drafted(name, drafted)
        sc_name = find_sc_name(name, sc_map)
        if sc_name is None:
            continue

        if is_pitcher:
            stats = pitch_stats(sc_name, parq)
            if stats is None or stats["bf"] < 40:
                continue
            rows.append({
                "name": name, "team_2026": meta["team"], "pos": meta["pos"],
                "year": year, "drafted": drafted_yn, "stat_type": "P",
                "apps": stats["apps"], "bf": stats["bf"], "fpp": stats["fpp"],
                "pa_xwoba": None, "xwoba": None, "model": model, "mrank": mrank,
            })
        else:
            stats = hit_stats(sc_name, parq)
            if stats is None or stats["pa"] < 60:
                continue
            rows.append({
                "name": name, "team_2026": meta["team"], "pos": meta["pos"],
                "year": year, "drafted": drafted_yn, "stat_type": "H",
                "apps": None, "bf": None, "fpp": None,
                "pa_xwoba": stats["pa"], "xwoba": stats["xwoba"],
                "model": model, "mrank": mrank,
            })

con.close()
df = pd.DataFrame(rows)
print(f"Rows with prior-year data: {len(df)} across {df['name'].nunique()} players", flush=True)


def signal_fires(row):
    if row["stat_type"] == "P":
        fpp = row["fpp"]
        if fpp is None:
            return False
        return fpp >= 0.04 or (fpp >= 0.0 and row["mrank"] <= 120)
    else:
        xw = row["xwoba"]
        if xw is None:
            return False
        return xw >= 0.360 and row["pa_xwoba"] >= 75


df["signal_fires"] = df.apply(signal_fires, axis=1)

# ── Full table: all players with prior-year data, drafted or not ─────────────
print("\n" + "=" * 75)
print("ALL CURRENT LEAGUE PLAYERS — prior-year performance vs draft status")
print("=" * 75)
print(f"{'Player':<26} {'2026 Team':<25} {'Yr'} {'Pos':<3} {'Drafted?':<9} {'Model':>10}  {'Key stat'}")
print("-" * 90)

display_df = df.drop_duplicates(subset=["name", "year"]).sort_values(["mrank", "name", "year"])
for _, r in display_df.iterrows():
    if r["stat_type"] == "P":
        stat = f"fpp={r['fpp']:+.4f} ({r['apps']}app)"
    else:
        xw = r["xwoba"]
        stat = f"xwOBA={xw:.3f} ({r['pa_xwoba']}PA)" if xw else f"PA={r['pa_xwoba']}"
    model_str = f"{r['model']} #{r['mrank']}" if r["model"] else "unranked"
    d_tag = "yes" if r["drafted"] else "NO ★"
    sig = " FIRE" if r["signal_fires"] and not r["drafted"] else ""
    print(f"  {r['name']:<24} {r['team_2026']:<25} {r['year']} {r['pos']:<3} {d_tag:<9} {model_str:>10}  {stat}{sig}")

# ── Summary: undrafted + signal fires ────────────────────────────────────────
undrafted_fires = df[(~df["drafted"]) & df["signal_fires"]].copy()
print(f"\n{'=' * 75}")
print(f"UNDRAFTED + SIGNAL FIRES: {undrafted_fires['name'].nunique()} unique players")
print(f"{'=' * 75}")
print(f"\n{'Player':<26} {'2026 Team':<25} {'Yr'} {'Pos':<3} {'Model':>10}  {'Key stat'}")
print("-" * 80)
for _, r in undrafted_fires.drop_duplicates(["name", "year"]).sort_values("mrank").iterrows():
    if r["stat_type"] == "P":
        stat = f"fpp={r['fpp']:+.4f} ({r['apps']}app)"
    else:
        xw = r["xwoba"]
        stat = f"xwOBA={xw:.3f} ({r['pa_xwoba']}PA)" if xw else ""
    model_str = f"{r['model']} #{r['mrank']}" if r["model"] else "unranked"
    print(f"  {r['name']:<24} {r['team_2026']:<25} {r['year']} {r['pos']:<3} {model_str:>10}  {stat}")

# ── By team ──────────────────────────────────────────────────────────────────
print(f"\n{'=' * 75}")
print("BY 2026 TEAM — count of players on roster who were undrafted + signal fired")
print(f"{'=' * 75}")
for team, grp in undrafted_fires.groupby("team_2026"):
    names = grp.drop_duplicates("name")["name"].tolist()
    print(f"  {team:<30} {len(names):>2}:  {', '.join(names[:6])}")

# ── Still on wire ─────────────────────────────────────────────────────────────
fa_fires = undrafted_fires[undrafted_fires["team_2026"] == "FA"]
print(f"\n{'=' * 75}")
print(f"STILL ON FA WIRE — undrafted signal fires sitting unclaimed: {fa_fires['name'].nunique()}")
print(f"{'=' * 75}")
for _, r in fa_fires.drop_duplicates("name").sort_values("mrank").iterrows():
    if r["stat_type"] == "P":
        stat = f"fpp={r['fpp']:+.4f} ({r['apps']}app)"
    else:
        xw = r["xwoba"]
        stat = f"xwOBA={xw:.3f} ({r['pa_xwoba']}PA)" if xw else ""
    model_str = f"{r['model']} #{r['mrank']}" if r["model"] else "unranked"
    print(f"  {r['name']:<24} {r['year']} {r['pos']:<3} {model_str:>10}  {stat}")
