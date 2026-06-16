"""FA position analysis — C, 1B/3B, 2B/SS, OF, UTIL, SP, RP."""
import pandas as pd
import unicodedata
import sys
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.espn_connector import get_my_roster_with_injuries, get_free_agents


def _norm(s):
    return unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def to_rp3(name):
    parts = name.strip().split()
    return _norm(parts[-1] + ", " + " ".join(parts[:-1])) if len(parts) >= 2 else _norm(name)


rh3   = pd.read_csv(ROOT / "data/outputs/xfp_rh3_projections.csv")
rp3   = pd.read_csv(ROOT / "data/outputs/xfp_rp3_projections.csv")
rprs2 = pd.read_csv(ROOT / "data/outputs/xfp_rprs2_projections.csv")

# rh3: key on (norm_name, team) to prevent same-name collisions (Max Muncy LAD vs ATH)
rh3_by_name_team: dict = {}
for _, r in rh3.iterrows():
    key = (_norm(r["player_name"]), str(r["team"]).upper())
    rh3_by_name_team[key] = r
# also build a name-only index for unique-name fallback
_rh3_name_only: dict = {}
_rh3_name_dups: set = set()
for (nm, tm), r in rh3_by_name_team.items():
    if nm in _rh3_name_only:
        _rh3_name_dups.add(nm)
    _rh3_name_only[nm] = r

rp3_n   = {_norm(r["player_name"]): r for _, r in rp3.iterrows()}
rprs2_n = {_norm(r["name_api"]): r for _, r in rprs2.iterrows()}

cutoff = (date.today() - timedelta(days=14)).isoformat()
bs_pitch: dict = {}
bs_hit: dict = {}
for path, store in [
    (ROOT / "data/research/xfp_cache/boxscore_pitchers.parquet", bs_pitch),
    (ROOT / "data/research/xfp_cache/boxscore_hitters.parquet",  bs_hit),
]:
    if path.exists():
        df = pd.read_parquet(path)
        df = df[df["game_date"] >= cutoff].sort_values("game_date", ascending=False)
        for _, row in df.iterrows():
            store.setdefault(_norm(row["player_name"]), []).append(row)


def bsp(name, n=2):
    rows = bs_pitch.get(_norm(name), [])[:n]
    if not rows:
        return ""
    parts = []
    for r in rows:
        ip = float(r["ip"]); fp = float(r["fp_sp"]); so = int(r["so"])
        flag = "E" if fp >= 20 else ("F" if fp >= 15 else "")
        parts.append(f"{str(r['game_date'])[5:]} {ip:.1f}IP {so}K {fp:.1f}FP{flag}")
    return " | ".join(parts)


def bsh(name, n=2):
    rows = bs_hit.get(_norm(name), [])[:n]
    if not rows:
        return ""
    parts = []
    for r in rows:
        fp = float(r["fp_h"]); tb = int(r["tb"]); ru = int(r["r"])
        flag = "*" if fp >= 12 else ("+" if fp >= 8 else "")
        parts.append(f"{str(r['game_date'])[5:]} {ru}R {tb}TB {fp:.1f}FP{flag}")
    return " | ".join(parts)


def h_proj(nm, team=""):
    """Team-keyed rh3 lookup. Falls back to name-only iff the name is unique."""
    key = (_norm(nm), str(team).upper())
    r = rh3_by_name_team.get(key)
    if r is None and _norm(nm) not in _rh3_name_dups:
        r = _rh3_name_only.get(_norm(nm))
    if r is None:
        return None, None
    return float(r["xfp_rh3_per_game"]), int(r["rank"])


def sp_proj(nm):
    r = rp3_n.get(to_rp3(nm))
    if r is None:
        return None, None
    return float(r["xfp_rp3_per_start"]), int(r["rank"])


def rp_proj(nm):
    r = rprs2_n.get(_norm(nm))
    if r is None:
        return None, None
    return float(r["xfp_ros"]), int(r["rank"])


roster = get_my_roster_with_injuries()
my_h = roster[~roster["position"].isin(["SP", "RP", "P"])].copy()
my_p = roster[roster["position"].isin(["SP", "RP", "P"])].copy()

print("Fetching FA pool...", flush=True)
fas = get_free_agents(size=2000)
fa_h = fas[~fas["position"].isin(["SP", "RP", "P"])].copy()
fa_p = fas[fas["position"].isin(["SP", "RP", "P"])].copy()


IL_SLOTS   = frozenset({"IL", "IL10", "IL15", "IL60", "IR"})
IL_STATES  = frozenset({"TEN_DAY_DL", "FIFTEEN_DAY_DL", "SIXTY_DAY_DL",
                         "INJURY_RESERVE", "OUT", "IL10", "IL15", "IL60"})

def avail_tag(row):
    """Return availability marker based only on IL slot + injury status.
    BE/BENCH/BN = active (Josh manages lineup daily). Empty string = fully active."""
    slot   = row.get("lineup_slot", "")
    status = row.get("injury_status", "")
    if slot in IL_SLOTS or status in IL_STATES:
        return f" [IL: {status}]"
    if status == "DAY_TO_DAY":
        return " [DTD]"
    return ""


def hdr(title):
    print()
    print("=" * 82)
    print(title)
    print("=" * 82)


def my_hline(row):
    nm   = row["player_name"]
    team = str(row.get("pro_team", "")).upper()
    tag  = avail_tag(row)
    xfp, rnk = h_proj(nm, team)
    proj = f"{xfp:.3f}" if xfp else "  ---"
    rank = f"#{rnk}" if rnk else "  ?"
    return f"  MINE  {nm+tag:<36} rh3={proj} {rank:<6}  {bsh(nm)}"


def fa_hline(row):
    nm   = row["player_name"]
    team = str(row.get("pro_team", "")).upper()
    pos  = row["position"]
    pct  = row["percent_owned"]
    xfp, rnk = h_proj(nm, team)
    if xfp is None:
        return None
    return f"  FA    {nm:<28} {pos:<6} rh3={xfp:.3f} #{rnk:<5} own={pct:.1f}%  {bsh(nm)}"


def top_fa_h(df, positions, n=6):
    sub = df[df["position"].isin(positions)]
    rows = []
    for _, r in sub.iterrows():
        xfp, rnk = h_proj(r["player_name"], str(r.get("pro_team", "")).upper())
        if xfp:
            rows.append((rnk, r))
    rows.sort(key=lambda x: x[0])
    printed = 0
    for _, r in rows:
        line = fa_hline(r)
        if line:
            print(line); printed += 1
            if printed >= n:
                break


# ====== CATCHER ======
hdr("C  --  CATCHER")
for _, p in my_h[my_h["position"] == "C"].iterrows():
    print(my_hline(p))
print("  -- Top FA Catchers --")
top_fa_h(fa_h, ["C"], n=6)

# ====== 1B / 3B ======
hdr("1B / 3B")
for _, p in my_h[my_h["position"].isin(["1B", "3B"])].iterrows():
    print(my_hline(p))
print("  -- Top FA 1B/3B --")
top_fa_h(fa_h, ["1B", "3B", "1B/3B"], n=7)

# ====== 2B / SS ======
hdr("2B / SS")
for _, p in my_h[my_h["position"].isin(["2B", "SS"])].iterrows():
    print(my_hline(p))
print("  -- Top FA 2B/SS --")
top_fa_h(fa_h, ["2B", "SS", "2B/SS"], n=6)

# ====== OF ======
hdr("OF")
for _, p in my_h[my_h["position"].isin(["LF", "CF", "RF", "OF"])].iterrows():
    print(my_hline(p))
print("  -- Top FA OF --")
top_fa_h(fa_h, ["LF", "CF", "RF", "OF"], n=8)

# ====== UTIL ======
hdr("UTIL  --  Top FA hitters (any position)")
all_fa_h = []
for _, r in fa_h.iterrows():
    xfp, rnk = h_proj(r["player_name"], str(r.get("pro_team", "")).upper())
    if xfp:
        all_fa_h.append((rnk, r))
all_fa_h.sort(key=lambda x: x[0])
printed = 0
for _, r in all_fa_h:
    line = fa_hline(r)
    if line:
        print(line); printed += 1
        if printed >= 10:
            break

# ====== SP ======
hdr("SP  --  STARTING PITCHERS")
sp_mine = my_p[my_p["position"].isin(["SP", "P"])].copy()
for _, p in sp_mine.iterrows():
    nm  = p["player_name"]
    tag = avail_tag(p)
    xfp, rnk = sp_proj(nm)
    if xfp:
        print(f"  MINE  {nm+tag:<36} {xfp:.2f}/s  rp3 #{rnk:<5}  {bsp(nm)}")
    else:
        xfp2, rnk2 = rp_proj(nm)
        br = bsp(nm)
        if xfp2:
            print(f"  MINE  {nm+tag:<36} {xfp2:.1f}ros rprs2 #{rnk2:<5} (SP/RP dual)  {br}")
        else:
            print(f"  MINE  {nm+tag:<36}  ---  no model match  {br}")
print("  -- Top FA SPs --")
fa_sps = fa_p[fa_p["position"] == "SP"]
sp_rows = []
for _, r in fa_sps.iterrows():
    xfp, rnk = sp_proj(r["player_name"])
    if xfp:
        sp_rows.append((rnk, r, xfp))
sp_rows.sort(key=lambda x: x[0])
for rnk, r, xfp in sp_rows[:12]:
    print(f"  FA    {r['player_name']:<28} SP   {xfp:.2f}/s rp3 #{rnk:<5} own={r['percent_owned']:.1f}%  {bsp(r['player_name'])}")

# ====== RP ======
hdr("RP  --  RELIEF PITCHERS")
rp_mine = my_p[my_p["position"].isin(["RP", "P"])].copy()
for _, p in rp_mine.iterrows():
    nm  = p["player_name"]
    tag = avail_tag(p)
    br  = bsp(nm)
    xfp, rnk = rp_proj(nm)
    if xfp:
        print(f"  MINE  {nm+tag:<36} {xfp:.1f}ros rprs2 #{rnk:<5}  {br}")
    else:
        xfp2, rnk2 = sp_proj(nm)
        if xfp2:
            print(f"  MINE  {nm+tag:<36} {xfp2:.2f}/s rp3 #{rnk2:<5} (SP-eligible)  {br}")
        else:
            print(f"  MINE  {nm+tag:<36}  ---  no model match  {br}")
print("  -- Top FA RPs --")
fa_rps = fa_p[fa_p["position"] == "RP"]
rp_rows = []
for _, r in fa_rps.iterrows():
    xfp, rnk = rp_proj(r["player_name"])
    if xfp:
        rp_rows.append((rnk, r, xfp))
rp_rows.sort(key=lambda x: x[0])
for rnk, r, xfp in rp_rows[:10]:
    print(f"  FA    {r['player_name']:<28} RP   {xfp:.1f}ros rprs2 #{rnk:<4} own={r['percent_owned']:.1f}%  {bsp(r['player_name'])}")
