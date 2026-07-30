"""
sp_stuff_model.py - standalone SP breakout / FA-filter board driven by the
VALIDATED FanGraphs Stuff+ in-season signal (see
data/research/validation_runs/fg_pitch_modeling_inseason_2026-06-06.md).

Pipeline:
  1. Fit the validated projection on 2021-2025 as-of-June-6 -> RoS:
       ros_fp ~ pre_fp + k_pct + bb_pct + swstr_pct + siera + stuff_plus   (Ridge)
  2. Apply to 2026 season-to-date SPs (>= MIN_GS starts) to project RoS FP/start.
  3. Breakout gap = stuff_plus percentile − current-FP percentile (within the
     2026 SP pool). High gap = elite stuff, lagging results = buy-low the model
     is built to catch.
  4. (optional) tag MINE / opp / FA via ESPN - added in a later step.

Headline rank = projected RoS FP/start. Breakout flag = the gap.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_fg_pitch_modeling_inseason import load as load_hist, real_ip  # noqa: E402
from plv_clone.league_config import MY_TEAM_NAME

ROOT = Path(__file__).resolve().parents[2]
FG = ROOT / "data" / "research" / "fg_asof"
BOX = ROOT / "data" / "research" / "xfp_cache" / "boxscore_pitchers.parquet"
FEATS = ["pre_fp", "k_pct", "bb_pct", "swstr_pct", "siera", "stuff_plus"]
MIN_GS = 5
FG_STALE_DAYS = 5          # FG rate stats stabilize but drift; warn past this
RECENT_APPS = 6            # window for recency-aware role classification
RECENT_START_RATIO = 0.6   # >= this share of recent apps as starts => SP
MY_TEAM = MY_TEAM_NAME


def _warn_if_fg_stale(path):
    """Loud guard so a frozen FG scrape is never silently trusted again.
    The June-6 staleness that mislabeled Griffin Jax (7 GS frozen vs 13 live)
    would have printed here. Returns age in days."""
    import time
    try:
        age = (time.time() - Path(path).stat().st_mtime) / 86400.0
    except OSError:
        print(f"WARN sp_stuff_model: FG file missing ({path})", file=sys.stderr)
        return None
    if age > FG_STALE_DAYS:
        print(f"\n*** STALE FG DATA: {Path(path).name} is {age:.0f} days old "
              f"(> {FG_STALE_DAYS}d). Stuff+/K%/BB% are frozen at that date. "
              f"Refresh via: python scripts/_oneoff/fg_2026_current.py ***\n",
              file=sys.stderr)
    return age


def _live_gs_from_boxscore():
    """Authoritative GS from the DAILY-refreshed boxscore — immune to FG
    staleness. Returns per-pitcher live_gs / live_apps / recent_start_ratio so
    role classification uses live usage, not a frozen season snapshot. The
    recent-window ratio catches mid-season RP->SP converters (Jax 2026) whose
    cumulative gs/g is dragged down by early relief appearances."""
    if not BOX.exists():
        return None
    b = pd.read_parquet(BOX, columns=["mlbam_id", "game_date", "gs"])
    b["game_date"] = pd.to_datetime(b["game_date"])
    out = []
    for pid, g in b.groupby("mlbam_id"):
        g = g.sort_values("game_date")
        rec = g.tail(RECENT_APPS)
        out.append((pid, int(g["gs"].sum()), len(g),
                    float(rec["gs"].mean()) if len(rec) else 0.0))
    return pd.DataFrame(out, columns=["mlb_id", "live_gs", "live_apps", "recent_start_ratio"])


# Name join key — OWNER: plv_clone.utils.name_match.safe_name_key. Order-
# PRESERVING, space-separated ("kyle schwarber"), collapses curly-vs-straight
# apostrophes, C.J./CJ and hyphens. NEVER re-derive locally: a local copy
# mis-keyed Ryan O'Hearn's U+2019 apostrophe and printed an opponent's player
# as a FREE AGENT (2026-07-28). NOT join_key — that one sorts tokens and drops
# separators, which is a different (order-independent) key.
from plv_clone.utils.name_match import safe_name_key as _norm  # noqa: E402


def _last_init_key(norm_name: str):
    """(last_name, first_initial) tuple for the two-pass fallback, or None."""
    parts = norm_name.split()
    if len(parts) >= 2 and parts[0]:
        return (parts[-1], parts[0][0])
    return None


def ownership_map():
    """Return {'full': {norm_name: tag}, 'li': {(last, first_init): {pro_team: tag}}}.

    Two-pass index so first-name spelling drift (ESPN 'Cam Schlittler' vs
    FanGraphs 'Cameron Schlittler') resolves to the rostering team instead of
    leaking through as a false FA. Mirrors the /roster-verify rule: full name
    first, then (last, first-initial) — never last-name alone (keeps Logan vs
    Gunnar Henderson distinct via the differing initial). Degrades to {}
    offline so tags are simply omitted.
    """
    try:
        sys.path.insert(0, str(ROOT))
        from app.espn_connector import get_all_teams
        teams = get_all_teams()
    except Exception as e:  # offline / no creds
        print(f"  [ownership] ESPN unavailable ({type(e).__name__}); tags omitted.\n")
        return {}
    full, li = {}, {}
    for _, r in teams.iterrows():
        tag = "MINE" if str(r["team_name"]).strip() == MY_TEAM else str(r["team_name"]).strip()
        nm = _norm(r["player_name"])
        full[nm] = tag
        key = _last_init_key(nm)
        if key:
            pro = str(r.get("pro_team", "")).strip().upper()
            li.setdefault(key, {})[pro] = tag
    return {"full": full, "li": li}


def own_tag(own, fg_name, fg_team=None):
    """Resolve a FanGraphs name to its roster tag via the two-pass index.

    Returns 'MINE' / opp-team-name / 'FA'. An ambiguous (last, first-initial)
    bucket with 2+ teams and no team match returns 'FA' rather than guessing.
    """
    if not own:
        return ""
    n = _norm(fg_name)
    full = own.get("full", {})
    if n in full:
        return full[n]
    key = _last_init_key(n)
    bucket = own.get("li", {}).get(key) if key else None
    if bucket:
        if fg_team:
            t = str(fg_team).strip().upper()
            if t in bucket:
                return bucket[t]
        if len(bucket) == 1:  # unambiguous last+initial -> safe to resolve
            return next(iter(bucket.values()))
    return "FA"


def brownu_fp_per_start(d):
    rip = real_ip(d["ip"])
    for c in ["so", "h", "er", "bb", "hbp", "gs"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return (d["so"] + rip * 3.3 - d["h"] - 2 * d["er"] - d["bb"] - d["hbp"].fillna(0)) / d["gs"]


def fit_model():
    h = load_hist()
    sub = h[FEATS + ["ros_fp"]].dropna()
    sc = StandardScaler().fit(sub[FEATS])
    mdl = Ridge(alpha=1.0).fit(sc.transform(sub[FEATS]), sub["ros_fp"])
    return mdl, sc, len(sub)


def load_2026():
    fpath = FG / "fg_pit_2026_current.csv"
    age = _warn_if_fg_stale(fpath)
    d = pd.read_csv(fpath)
    d["gs"] = pd.to_numeric(d["gs"], errors="coerce")
    d["g"] = pd.to_numeric(d["g"], errors="coerce")
    for c in ["k_pct", "bb_pct", "swstr_pct", "siera", "stuff_plus",
              "location_plus", "pitching_plus", "pb_stuff", "pb_command"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    # ── In-house stuff fallback (2026-07-20) ────────────────────────────
    # When the FG scrape is stale (Cloudflare-gated, silently freezes — see
    # model-health `fg_scrape_silent_fail`), override stuff_plus with the
    # SAME-DAY in-house score (archetype STUFF quantile-mapped to the FG
    # scale, PLV filling rookies) from build_inhouse_stuff.py. This
    # implements the REGISTERED verdict of the 2026-06-06 head-to-head
    # (archetype_stuff_replacement: predictively equal, FALLBACK-ONLY).
    # FG stays the untouched primary whenever it is fresh. Every row carries
    # `stuff_source` provenance: fg | arch | plv | fg_frozen.
    d["stuff_source"] = "fg"
    if age is not None and age > FG_STALE_DAYS:
        inh_path = FG / "stuff_inhouse_2026.csv"
        try:
            inh = pd.read_csv(inh_path)[
                ["mlb_id", "stuff_plus_inhouse", "stuff_source"]
            ].rename(columns={"stuff_source": "_inh_src"})
            d = d.merge(inh, on="mlb_id", how="left")
            hit = d["stuff_plus_inhouse"].notna()
            d.loc[hit, "stuff_plus"] = d.loc[hit, "stuff_plus_inhouse"]
            d.loc[hit, "stuff_source"] = d.loc[hit, "_inh_src"]
            d.loc[~hit & d["stuff_plus"].notna(), "stuff_source"] = "fg_frozen"
            import time as _t
            inh_age_h = (_t.time() - inh_path.stat().st_mtime) / 3600.0
            n_arch = int((d.loc[hit, "_inh_src"] == "arch").sum())
            n_plv = int((d.loc[hit, "_inh_src"] == "plv").sum())
            print(f"*** IN-HOUSE STUFF fallback ACTIVE (FG {age:.0f}d stale): "
                  f"stuff_plus overridden for {int(hit.sum())} pitchers "
                  f"(arch={n_arch}, plv={n_plv}; in-house file "
                  f"{inh_age_h:.0f}h old); un-covered rows tagged fg_frozen ***",
                  file=sys.stderr)
            if inh_age_h > 48:
                print("WARN: in-house stuff file itself >48h old — run "
                      "scripts/xfp/build_inhouse_stuff.py", file=sys.stderr)
            d = d.drop(columns=["stuff_plus_inhouse", "_inh_src"])
        except OSError:
            print("WARN: FG stale AND stuff_inhouse_2026.csv missing — "
                  "stuff_plus stays frozen. Run "
                  "scripts/xfp/build_inhouse_stuff.py", file=sys.stderr)
    # Reconcile GS/apps from the daily boxscore so the SP gate is NEVER driven
    # by a stale FG snapshot. Season gs/g>=0.7 keeps clean starters; the OR on
    # recent_start_ratio admits mid-season converters (Jax: cum 13/24=0.54 fails
    # 0.7, but last 6 apps all starts => recent_ratio 1.0 => correctly SP).
    live = _live_gs_from_boxscore()
    if live is not None:
        d = d.merge(live, on="mlb_id", how="left")
        d["gs"] = d["live_gs"].fillna(d["gs"])
        d["g"] = d["live_apps"].fillna(d["g"])
        is_sp = ((d["gs"] >= MIN_GS)
                 & (((d["gs"] / d["g"]) >= 0.7)
                    | (d["recent_start_ratio"].fillna(0) >= RECENT_START_RATIO)))
    else:
        is_sp = (d["gs"] >= MIN_GS) & (d["gs"] / d["g"] >= 0.7)
    d = d[is_sp].copy()
    d["pre_fp"] = brownu_fp_per_start(d)
    return d


def build():
    mdl, sc, n_train = fit_model()
    d = load_2026().dropna(subset=FEATS).copy()
    d["proj_ros_fp"] = mdl.predict(sc.transform(d[FEATS]))
    # percentiles within 2026 SP pool
    d["stuff_pctl"] = d["stuff_plus"].rank(pct=True) * 100
    d["curfp_pctl"] = d["pre_fp"].rank(pct=True) * 100
    d["breakout_gap"] = d["stuff_pctl"] - d["curfp_pctl"]
    d["proj_vs_current"] = d["proj_ros_fp"] - d["pre_fp"]
    own = ownership_map()
    team_col = next((c for c in ("team", "Team", "tm", "Tm", "team_fg") if c in d.columns), None)
    d["own"] = (
        d.apply(lambda r: own_tag(own, r["player_name_fg"],
                                  r[team_col] if team_col else None), axis=1)
        if own else ""
    )
    return d, n_train


def main():
    d, n_train = build()
    print(f"Model: Ridge on {n_train} SP-seasons (2021-25, as-of-June-6 -> RoS). "
          f"2026 SP pool: {len(d)} (>= {MIN_GS} GS).\n")

    has_own = (d["own"] != "").any()
    fmt = lambda r: (f"{r.player_name_fg:<21}{(r.own if has_own else str(r.team))[:15]:<16}"
                     f"{int(r.gs):>3}{r.stuff_plus:>8.1f}{r.pre_fp:>8.1f}"
                     f"{r.proj_ros_fp:>9.1f}{r.breakout_gap:>+9.0f}{r.proj_vs_current:>+8.1f}")
    hdr = (f"{'pitcher':<21}{('owner' if has_own else 'tm'):<16}{'GS':>3}{'Stuff+':>8}"
           f"{'curFP':>8}{'projFP':>9}{'b/o gap':>9}{'d_proj':>8}")

    def emit(r, suffix=""):
        # per-player crash guard (audit 2026-07-19 item 22, collect_cards
        # pattern): one bad row (NaN int cast, missing field) must not kill
        # the board — warn one line and continue.
        try:
            print(fmt(r) + suffix)
        except Exception as e:
            print(f"WARN sp_stuff row {getattr(r, 'player_name_fg', '?')}: "
                  f"{type(e).__name__}: {e} — skipped")

    print("=== TOP 20 BY PROJECTED RoS FP/START (league-wide) ===")
    print(hdr); print("-" * len(hdr))
    for _, r in d.nlargest(20, "proj_ros_fp").iterrows():
        emit(r)

    print("\n=== TOP 20 BREAKOUT CANDIDATES (elite Stuff+, lagging results) ===")
    print(hdr); print("-" * len(hdr))
    for _, r in d[d["stuff_pctl"] >= 60].nlargest(20, "breakout_gap").iterrows():
        emit(r)

    if has_own:
        mine = d[d["own"] == "MINE"].sort_values("proj_ros_fp", ascending=False)
        fa = d[d["own"] == "FA"].sort_values("proj_ros_fp", ascending=False)
        print(f"\n=== YOUR SP STAFF ({len(mine)}) - ranked by projected RoS FP ===")
        print(hdr); print("-" * len(hdr))
        for _, r in mine.iterrows():
            emit(r)
        worst_mine = mine["proj_ros_fp"].min() if len(mine) else 0
        print(f"\n=== TOP 15 FA SPs (projFP) - upgrades over your weakest "
              f"projected starter ({worst_mine:.1f}) flagged * ===")
        print(hdr); print("-" * len(hdr))
        for _, r in fa.nlargest(15, "proj_ros_fp").iterrows():
            emit(r, " *" if r.proj_ros_fp > worst_mine else "")
        print(f"\n=== TOP 12 FA BREAKOUT TARGETS (b/o gap, Stuff+ pctl>=60) ===")
        print(hdr); print("-" * len(hdr))
        for _, r in fa[fa["stuff_pctl"] >= 60].nlargest(12, "breakout_gap").iterrows():
            emit(r)


if __name__ == "__main__":
    main()
