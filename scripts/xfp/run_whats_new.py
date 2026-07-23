"""run_whats_new.py — the /whats-new delta briefing engine.

Everything notable since the user's last look, as a PURE JOINER over stores
the nightly refresh already accumulates. Zero model math; awareness only
(Rule 13 — nothing here moves a projection; route decisions to /daily-edge,
deep dives to /triangulate).

Sections (each fail-soft — a broken/missing store prints one WARN line and
the briefing continues):
  1. LEAGUE TRANSACTIONS  data/research/transactions_history.parquet
  2. MY GAME LINES        xfp_cache/boxscore_{hitters,pitchers}.parquet
                          joined to the LIVE roster (my_roster()) by mlbam id
  3. RANK MOVERS          data/research/player_projection_history.parquet
                          (two latest snapshots, rh3 + rp3)
  4. INJURY CHANGES       xfp_cache/injury_status.json diffed vs the IL map
                          snapshotted in the state file (first run: my IL list)
  5. PL RANK CHANGES      data/research/pl_cache/pl_*_<date>.json
                          (two latest editions per list)
  6. FA STANDOUTS         data/outputs/volume_watch.csv risers + FB-velo
                          risers (lib/trend_signal), ownership-filtered to FA

State: data/research/whats_new_last_seen.json —
  {"last_seen": iso-ts, "markers": {...seen edition dates...}, "il": {...}}
Updated at END of a successful default run. `--since <iso>` overrides
last_seen (and ignores seen-markers); `--dry-run` never writes state.

Repo rules honored: players are labeled MINE only via a live my_roster()
pull; every join is by mlbam id where the store carries one; name fallback
is normalized FULL-name only (never last-name contains).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "scripts" / "xfp")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

RESEARCH = ROOT / "data" / "research"
OUTPUTS = ROOT / "data" / "outputs"
XFP_CACHE = RESEARCH / "xfp_cache"
PL_CACHE = RESEARCH / "pl_cache"
STATE_PATH = RESEARCH / "whats_new_last_seen.json"
FA_PICKLE = RESEARCH / "espn_snapshot" / "free_agents_2000.pkl"

CAP = 10  # rows per section before "+N more"

_PITCHER_POS = {"SP", "RP", "P"}


# ---------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------

def _utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _warn(section: str, msg: str) -> None:
    print(f"  ! WARN [{section}] {msg}")


def _emit(lines: list[str], cap: int = CAP) -> None:
    if not lines:
        print("  (nothing)")
        return
    for ln in lines[:cap]:
        print(f"  {ln}")
    if len(lines) > cap:
        print(f"  ... +{len(lines) - cap} more")


def _header(title: str) -> None:
    print(f"\n== {title} " + "=" * max(1, 60 - len(title)))


def _load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    tmp.replace(STATE_PATH)


def _normalize(name: str) -> str:
    try:
        from plv_clone.utils.name_match import _normalize as nm
        return nm(str(name))
    except Exception:
        return str(name).strip().lower()


# ---------------------------------------------------------------------------
# live roster (the ONLY source allowed to label a player MINE)
# ---------------------------------------------------------------------------

def _live_roster():
    """(roster_df, mlbam_map {mlbam: (name, position)}) or (None, {})."""
    try:
        from plv_clone.league_state import default_state
        roster = default_state().my_roster()
    except Exception as e:
        _warn("roster", f"live my_roster() failed ({type(e).__name__}: {e}) — "
                        "MY-lines section skipped, MINE flags omitted")
        return None, {}
    mlbam_map: dict[int, tuple[str, str]] = {}
    try:
        from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id
        for _, r in roster.iterrows():
            name = str(r.get("player_name") or "")
            pos = str(r.get("position") or "").upper()
            team = str(r.get("pro_team") or "") or None
            if not name:
                continue
            try:
                if pos in _PITCHER_POS:
                    mid = resolve_pitcher_id(name, team=team,
                                             role=pos if pos in ("SP", "RP") else None)
                else:
                    mid = resolve_batter_id(name, team=team, position=pos or None)
            except Exception:
                mid = None
            if mid is not None:
                mlbam_map[int(mid)] = (name, pos)
    except Exception as e:
        _warn("roster", f"mlbam resolution unavailable ({type(e).__name__}: {e})")
    return roster, mlbam_map


# ---------------------------------------------------------------------------
# FA ownership chain (pickle -> live available_fa -> volume_watch own column)
# ---------------------------------------------------------------------------

def _own_map_from_volume_watch() -> tuple[dict[int, str], dict[int, str]]:
    """{mlbam: own}, {mlbam: player_name} from volume_watch.csv (offline)."""
    vw = pd.read_csv(OUTPUTS / "volume_watch.csv")
    own = dict(zip(vw["mlbam_id"].astype(int), vw["own"].astype(str)))
    names = dict(zip(vw["mlbam_id"].astype(int), vw["player_name"].astype(str)))
    return own, names


def _fa_checker(own_map: dict[int, str]):
    """Return (fa_check(mlbam, name) -> bool|None, source_note).

    Chain: espn snapshot pickle (if <48h fresh) -> live available_fa ->
    volume_watch own column -> None (no filter, caller notes it).
    """
    # 1. snapshot pickle
    try:
        if FA_PICKLE.exists():
            age_h = (datetime.now().timestamp() - FA_PICKLE.stat().st_mtime) / 3600
            if age_h <= 48:
                import pickle
                with open(FA_PICKLE, "rb") as fh:
                    pool = pickle.load(fh)
                names = set()
                for p in pool:
                    nm = getattr(p, "name", None) or (p.get("name") if isinstance(p, dict) else None)
                    if nm:
                        names.add(_normalize(nm))
                if names:
                    return (lambda m, n: _normalize(n) in names if n else None,
                            f"espn snapshot pickle ({len(names)} FAs, {age_h:.0f}h old)")
    except Exception as e:
        _warn("fa-pool", f"snapshot pickle unreadable ({type(e).__name__}: {e})")
    # 2. live available_fa
    try:
        from plv_clone.league_state import default_state
        fa = default_state().available_fa()
        names = {_normalize(n) for n in fa["player_name"].astype(str)}
        if names:
            return (lambda m, n: _normalize(n) in names if n else None,
                    f"live available_fa ({len(names)} FAs)")
    except Exception as e:
        _warn("fa-pool", f"live available_fa failed ({type(e).__name__}: {e})")
    # 3. volume_watch own column (as-of last volume-watch run)
    if own_map:
        return (lambda m, n: (own_map.get(int(m)) == "FA") if m is not None and int(m) in own_map else None,
                "volume_watch.csv own column (as-of last volume-watch run)")
    return (lambda m, n: None), "NONE — ownership filter skipped"


# ---------------------------------------------------------------------------
# 1. league transactions
# ---------------------------------------------------------------------------

def sec_transactions(last_seen: datetime) -> None:
    path = RESEARCH / "transactions_history.parquet"
    if not path.exists():
        _warn("transactions", f"{path.name} missing — skipped")
        return
    df = pd.read_parquet(path)
    cutoff_ms = int(last_seen.timestamp() * 1000)
    new = df[df["ts_ms"] > cutoff_ms].sort_values("ts_ms")
    if new.empty:
        print("  (no transactions since last seen)")
        return
    lines = []
    for team, grp in new.groupby("team_name", sort=True):
        for _, r in grp.iterrows():
            pos = f" {r['position']}" if r.get("position") else ""
            pro = f", {r['pro_team']}" if r.get("pro_team") else ""
            lines.append(f"{r['date']}  {team}: {r['action_str']} "
                         f"{r['player_name']}{pos}{pro}")
    _emit(lines)


# ---------------------------------------------------------------------------
# 2. my players' game lines
# ---------------------------------------------------------------------------

def sec_my_lines(last_seen: datetime, mlbam_map: dict[int, tuple[str, str]]) -> None:
    if not mlbam_map:
        _warn("my-lines", "no live roster mlbam ids — skipped")
        return
    try:
        from lib.boom_bust import SP_BOOM, SP_BUST, RP_BOOM, RP_BUST, H_BOOM, H_BUST
    except Exception:
        SP_BOOM = SP_BUST = RP_BOOM = RP_BUST = H_BOOM = H_BUST = None
    cutoff = last_seen.date().isoformat()
    ids = set(mlbam_map)
    lines: list[tuple[str, str]] = []  # (sort_key, text)

    def flag(fp, boom, bust):
        if boom is None:
            return ""
        if fp >= boom:
            return "  BOOM"
        if fp < bust:
            return "  BUST"
        return ""

    hp = XFP_CACHE / "boxscore_hitters.parquet"
    if hp.exists():
        h = pd.read_parquet(hp)
        h = h[h["mlbam_id"].isin(ids) & (h["game_date"] >= cutoff)]
        for _, r in h.iterrows():
            fp = float(r["fp_h"])
            lines.append((f"{r['game_date']}h{-fp:09.1f}",
                          f"{r['game_date']}  {r['player_name']:<22} H   "
                          f"{fp:+6.1f} FP{flag(fp, H_BOOM, H_BUST)}"))
    else:
        _warn("my-lines", "boxscore_hitters.parquet missing")

    pp = XFP_CACHE / "boxscore_pitchers.parquet"
    if pp.exists():
        p = pd.read_parquet(pp)
        p = p[p["mlbam_id"].isin(ids) & (p["game_date"] >= cutoff)]
        for _, r in p.iterrows():
            is_start = int(r.get("gs", 0)) == 1
            fp = float(r["fp_sp"] if is_start else r["fp_rp"])
            role = "SP " if is_start else "RP "
            bb = flag(fp, SP_BOOM, SP_BUST) if is_start else flag(fp, RP_BOOM, RP_BUST)
            lines.append((f"{r['game_date']}p{-fp:09.1f}",
                          f"{r['game_date']}  {r['player_name']:<22} {role} "
                          f"{fp:+6.1f} FP  ({r['ip']:.1f}IP {int(r['so'])}K "
                          f"{int(r['er'])}ER){bb}"))
    else:
        _warn("my-lines", "boxscore_pitchers.parquet missing")

    lines.sort(key=lambda t: t[0], reverse=True)  # newest date first, best FP first
    _emit([t[1] for t in lines], cap=CAP + 5)


# ---------------------------------------------------------------------------
# 3. rank movers (rh3 / rp3, two latest snapshots)
# ---------------------------------------------------------------------------

def sec_rank_movers(markers: dict, my_ids: set[int],
                    own_map: dict[int, str], new_markers: dict) -> None:
    path = RESEARCH / "player_projection_history.parquet"
    if not path.exists():
        _warn("rank-movers", f"{path.name} missing — skipped")
        return
    panel = pd.read_parquet(path, columns=["snapshot_date", "player_type",
                                           "mlbam_id", "player_name", "rank"])
    for ptype, label in (("H", "rh3"), ("SP", "rp3")):
        sub = panel[panel["player_type"] == ptype]
        dates = sorted(sub["snapshot_date"].astype(str).unique())
        if len(dates) < 2:
            _warn("rank-movers", f"{label}: <2 snapshots — skipped")
            continue
        prev_d, cur_d = dates[-2], dates[-1]
        new_markers[f"proj_{ptype}"] = cur_d
        if markers.get(f"proj_{ptype}") == cur_d:
            print(f"  {label}: latest snapshot {cur_d} already seen")
            continue
        cur = (sub[sub["snapshot_date"].astype(str) == cur_d]
               .drop_duplicates("mlbam_id").set_index("mlbam_id"))
        prev = (sub[sub["snapshot_date"].astype(str) == prev_d]
                .drop_duplicates("mlbam_id").set_index("mlbam_id"))
        j = cur[["player_name", "rank"]].join(prev[["rank"]], rsuffix="_prev", how="inner")
        j = j[(j[["rank", "rank_prev"]].min(axis=1) <= 200)]
        j["delta"] = j["rank_prev"] - j["rank"]  # positive = climbed
        movers = pd.concat([j.nlargest(10, "delta"), j.nsmallest(10, "delta")])
        movers = movers[movers["delta"].abs() >= 5].sort_values("delta", ascending=False)
        print(f"  {label} ({prev_d} -> {cur_d}), top movers (|d|>=5, rank<=200):")
        lines = []
        for mid, r in movers.iterrows():
            tags = []
            if int(mid) in my_ids:
                tags.append("MINE")
            elif own_map.get(int(mid)) == "FA":
                tags.append("FA")
            tag = f"  [{'/'.join(tags)}]" if tags else ""
            lines.append(f"{r['player_name']:<24} {int(r['rank_prev']):>3} -> "
                         f"{int(r['rank']):>3}  ({int(r['delta']):+d}){tag}")
        _emit(lines)


# ---------------------------------------------------------------------------
# 4. injury changes
# ---------------------------------------------------------------------------

def sec_injuries(prev_il: dict, roster, new_state: dict) -> None:
    try:
        from lib.injury_status import INJURY_CACHE, load_injury_details
        with open(INJURY_CACHE, encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception as e:
        _warn("injuries", f"injury cache unreadable ({type(e).__name__}: {e})")
        return
    cur_il: dict[str, str] = raw.get("il", {}) or {}
    fetched = raw.get("fetched")
    new_state["il"] = cur_il
    details, _ = load_injury_details()

    def ret(name: str) -> str:
        rec = details.get(_normalize(name)) or {}
        rd = rec.get("return_date")
        it = rec.get("injury_type")
        bits = [b for b in (it, f"ret {rd}" if rd else None) if b]
        return f"  ({', '.join(bits)})" if bits else ""

    my_names = set()
    if roster is not None:
        my_names = {_normalize(n) for n in roster["player_name"].astype(str)}

    def mine(name: str) -> str:
        return "  [MINE]" if _normalize(name) in my_names else ""

    if prev_il:
        lines = []
        for name, st in sorted(cur_il.items()):
            old = prev_il.get(name)
            if old is None:
                lines.append(f"NEW IL   {name}: {st}{ret(name)}{mine(name)}")
            elif old != st:
                lines.append(f"CHANGED  {name}: {old} -> {st}{ret(name)}{mine(name)}")
        for name, st in sorted(prev_il.items()):
            if name not in cur_il:
                lines.append(f"OFF IL   {name} (was {st}){mine(name)}")
        print(f"  vs last-seen IL snapshot (cache asof {fetched}):")
        _emit(lines)
    else:
        print(f"  no prior IL snapshot — current MY-roster IL (cache asof {fetched}):")
        if roster is None:
            _warn("injuries", "no live roster — cannot scope IL list to MINE")
            return
        lines = [f"{name}: {st}{ret(name)}"
                 for name, st in sorted(cur_il.items()) if _normalize(name) in my_names]
        _emit(lines)


# ---------------------------------------------------------------------------
# 5. PL rank changes (two latest dated editions per list)
# ---------------------------------------------------------------------------

_PL_LISTS = [
    ("pl_sps_top100", "SP Top 100"),
    ("pl_hitters_top150", "Hitters Top 150"),
    ("pl_closers", "Closers"),
]


def sec_pl(markers: dict, new_markers: dict) -> None:
    import glob as _glob
    for stem, label in _PL_LISTS:
        files = sorted(_glob.glob(str(PL_CACHE / f"{stem}_2???-??-??.json")))
        if len(files) < 2:
            _warn("pl-ranks", f"{label}: <2 dated editions — skipped")
            continue
        prev_f, cur_f = files[-2], files[-1]
        cur_date = Path(cur_f).stem.rsplit("_", 1)[-1]
        prev_date = Path(prev_f).stem.rsplit("_", 1)[-1]
        new_markers[f"pl_{stem}"] = cur_date
        if markers.get(f"pl_{stem}") == cur_date:
            print(f"  {label}: edition {cur_date} already seen")
            continue
        try:
            cur = json.loads(Path(cur_f).read_text(encoding="utf-8")).get("ranks", {})
            prev = json.loads(Path(prev_f).read_text(encoding="utf-8")).get("ranks", {})
        except Exception as e:
            _warn("pl-ranks", f"{label}: unreadable ({type(e).__name__}: {e})")
            continue
        moves = [(n, prev[n] - cur[n], prev[n], cur[n])
                 for n in cur if n in prev and prev[n] != cur[n]]
        moves.sort(key=lambda t: -abs(t[1]))
        entered = [n for n in cur if n not in prev]
        dropped = [n for n in prev if n not in cur]
        print(f"  {label} ({prev_date} -> {cur_date}):")
        lines = [f"{n:<24} {p:>3} -> {c:>3}  ({d:+d})" for n, d, p, c in moves[:6]]
        if entered:
            lines.append("NEW: " + ", ".join(f"{n} (#{cur[n]})" for n in
                                             sorted(entered, key=lambda x: cur[x])[:5])
                         + (f" +{len(entered)-5} more" if len(entered) > 5 else ""))
        if dropped:
            lines.append("OUT: " + ", ".join(sorted(dropped)[:5])
                         + (f" +{len(dropped)-5} more" if len(dropped) > 5 else ""))
        _emit(lines)


# ---------------------------------------------------------------------------
# 6. FA standouts (volume risers + FB-velo risers), Rule 13 awareness only
# ---------------------------------------------------------------------------

def sec_fa_standouts(last_seen: datetime, own_map: dict[int, str],
                     vw_names: dict[int, str], new_markers: dict,
                     markers: dict) -> None:
    vw_path = OUTPUTS / "volume_watch.csv"
    if not vw_path.exists():
        _warn("fa-standouts", "volume_watch.csv missing — skipped")
        return
    vw_mtime = datetime.fromtimestamp(vw_path.stat().st_mtime)
    new_markers["volume_watch_mtime"] = vw_mtime.isoformat(timespec="seconds")
    if markers.get("volume_watch_mtime") == new_markers["volume_watch_mtime"]:
        print("  volume_watch.csv unchanged since last seen — skipped")
        return

    fa_check, fa_src = _fa_checker(own_map)
    print(f"  (FA filter source: {fa_src})")

    # trend tables (bulk, fail-soft — statcast parquet reads)
    pit_tbl = hit_tbl = None
    try:
        from lib.trend_signal import pitcher_trend_table, hitter_trend_table
        pit_tbl = pitcher_trend_table()
        hit_tbl = hitter_trend_table()
    except Exception as e:
        _warn("fa-standouts", f"trend tables unavailable ({type(e).__name__}: {e}) "
                              "— velo/bat-speed overlay skipped")

    vw = pd.read_csv(vw_path)
    risers = vw[vw["direction"] == "RISER"].copy()

    def is_fa(row) -> bool:
        chk = fa_check(row["mlbam_id"], row["player_name"])
        if chk is None:  # fall back to the CSV's own column, else keep
            return str(row.get("own")) == "FA"
        return bool(chk)

    fa_risers = risers[risers.apply(is_fa, axis=1)].sort_values("impact", ascending=False)
    lines = []
    for _, r in fa_risers.head(CAP).iterrows():
        mid = int(r["mlbam_id"])
        trend = ""
        try:
            if r["player_type"] == "SP" and pit_tbl is not None and mid in pit_tbl.index:
                z = float(pit_tbl.loc[mid, "z"])
                if z >= 1.0:
                    trend = f"  +velo {pit_tbl.loc[mid, 'd_velo']:+.1f}mph ({z:+.1f}s) DUAL-LIST"
            elif r["player_type"] == "H" and hit_tbl is not None and mid in hit_tbl.index:
                zc = float(hit_tbl.loc[mid, "z_comp"])
                if zc >= 1.0:
                    trend = f"  +phys {zc:+.1f}s DUAL-LIST"
        except Exception:
            pass
        fl = f"  [{r['flags']}]" if isinstance(r.get("flags"), str) and r["flags"] else ""
        lines.append(f"{r['player_type']}  {r['player_name']:<24} vol gap "
                     f"{r['gap']:+.2f} {r['unit']}, impact {r['impact']:+.2f}{fl}{trend}")
    print("  FA volume RISERS (impact-ranked):")
    _emit(lines)

    # standalone FB-velo risers among FAs (not necessarily on the volume board)
    if pit_tbl is not None:
        vlines = []
        vr = pit_tbl[pit_tbl["z"] >= 1.5].sort_values("z", ascending=False)
        for mid, row in vr.iterrows():
            name = vw_names.get(int(mid))
            chk = fa_check(mid, name)
            if chk is False or (chk is None and own_map.get(int(mid)) != "FA"):
                continue
            if name is None:
                continue  # no safe name for this mlbam in the offline maps
            vlines.append(f"{name:<24} FB velo {row['d_velo']:+.1f} mph "
                          f"({row['z']:+.1f}s vs '25)")
        print("  FA FB-velo risers (z >= 1.5):")
        _emit(vlines, cap=8)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

INBOX_MD = Path(r"C:\Users\Joshua\Obsidian\Brain\inbox.md")


def sec_inbox(last_seen) -> None:
    """Josh's Obsidian capture note (vault trial 2026-07-20). Fail-soft view:
    prints the inbox body when the file changed since last_seen (else a quiet
    'unchanged' line). The CALLER (Claude, in /whats-new or /daily-rhythm)
    triages items — vetoes -> decision-gates, lessons -> rules, questions ->
    answers — and marks/clears them; this section only surfaces the text."""
    if not INBOX_MD.exists():
        print("  (no Obsidian inbox at "
              f"{INBOX_MD} — vault trial not set up on this machine)")
        return
    from datetime import datetime as _dt
    mtime = _dt.fromtimestamp(INBOX_MD.stat().st_mtime)
    body = [ln.rstrip() for ln in
            INBOX_MD.read_text(encoding="utf-8").splitlines()]
    # strip the header/instructions block (everything through the first ---)
    if "---" in body:
        body = body[body.index("---") + 1:]
    items = [ln for ln in body if ln.strip()]
    try:
        changed = mtime > last_seen.replace(tzinfo=None)
    except Exception:
        changed = True
    if not items:
        print("  (inbox empty)")
        return
    if not changed:
        print(f"  inbox unchanged since last look ({len(items)} item(s) "
              f"pending triage — edited {mtime:%m-%d %H:%M})")
        return
    print(f"  inbox edited {mtime:%m-%d %H:%M} — items:")
    for ln in items:
        print(f"    {ln}")
    print("  -> triage: vetoes -> /decision-gates add, lessons -> rules, "
          "questions get answered; mark items ✔ or clear after")


def main() -> int:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description="/whats-new delta briefing")
    ap.add_argument("--since", help="ISO date/timestamp override for last_seen")
    ap.add_argument("--dry-run", action="store_true",
                    help="render the briefing but do not update last_seen state")
    args = ap.parse_args()

    state = _load_state()
    markers = dict(state.get("markers") or {})
    prev_il = dict(state.get("il") or {})
    if args.since:
        last_seen = datetime.fromisoformat(args.since)
        markers = {}      # show every current edition/diff
        prev_il = dict(state.get("il") or {})  # IL diff still vs stored snapshot
    elif state.get("last_seen"):
        last_seen = datetime.fromisoformat(state["last_seen"])
    else:
        last_seen = datetime.now() - timedelta(days=7)

    try:
        from plv_clone.league_config import MY_TEAM_NAME
    except Exception:
        MY_TEAM_NAME = "New York Ligers"

    now = datetime.now()
    print("=" * 66)
    print(f"WHAT'S NEW — {MY_TEAM_NAME} — since {last_seen:%Y-%m-%d %H:%M} "
          f"(now {now:%Y-%m-%d %H:%M})")
    print("=" * 66)
    print("Awareness layer only (Rule 13) — decisions via /daily-edge, "
          "deep dives via /triangulate.")

    roster, mlbam_map = _live_roster()
    my_ids = set(mlbam_map)
    try:
        own_map, vw_names = _own_map_from_volume_watch()
    except Exception as e:
        _warn("volume-watch", f"own map unavailable ({type(e).__name__}: {e})")
        own_map, vw_names = {}, {}

    new_markers: dict = {}
    new_state: dict = {}
    sections = [
        ("1. LEAGUE TRANSACTIONS", lambda: sec_transactions(last_seen)),
        ("2. MY PLAYERS' GAME LINES", lambda: sec_my_lines(last_seen, mlbam_map)),
        ("3. RANK MOVERS (rh3/rp3)", lambda: sec_rank_movers(markers, my_ids, own_map, new_markers)),
        ("4. INJURY CHANGES", lambda: sec_injuries(prev_il, roster, new_state)),
        ("5. PL RANK CHANGES", lambda: sec_pl(markers, new_markers)),
        ("6. FA STANDOUTS", lambda: sec_fa_standouts(last_seen, own_map, vw_names, new_markers, markers)),
        ("7. JOSH'S INBOX (Obsidian)", lambda: sec_inbox(last_seen)),
    ]
    for title, fn in sections:
        _header(title)
        try:
            fn()
        except Exception as e:
            _warn(title, f"section crashed ({type(e).__name__}: {e}) — skipped")

    print()
    if args.dry_run:
        print("[dry-run] last_seen NOT updated")
    else:
        out = {
            "last_seen": now.isoformat(timespec="seconds"),
            "markers": {**markers, **new_markers},
            "il": new_state.get("il", prev_il),
        }
        _save_state(out)
        print(f"last_seen updated -> {out['last_seen']}  ({STATE_PATH.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
