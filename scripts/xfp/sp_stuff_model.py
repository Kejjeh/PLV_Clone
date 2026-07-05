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

ROOT = Path(__file__).resolve().parents[2]
FG = ROOT / "data" / "research" / "fg_asof"
FEATS = ["pre_fp", "k_pct", "bb_pct", "swstr_pct", "siera", "stuff_plus"]
MIN_GS = 5
MY_TEAM = "New York Ligers"


def _norm(name: str) -> str:
    # item 10 (2026-07-04): NOT routed to name_match.join_key — the output feeds
    # _last_init_key(nm), a (last, first-initial) fallback that needs SPACE-
    # separated, order-preserving tokens. join_key sorts + strips spaces, which
    # would break that fallback (same reason build_xfp_boards._li_key stays local).
    import re, unicodedata
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z ]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


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
    d = pd.read_csv(FG / "fg_pit_2026_current.csv")
    d["gs"] = pd.to_numeric(d["gs"], errors="coerce")
    d["g"] = pd.to_numeric(d["g"], errors="coerce")
    for c in ["k_pct", "bb_pct", "swstr_pct", "siera", "stuff_plus",
              "location_plus", "pitching_plus", "pb_stuff", "pb_command"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[(d["gs"] >= MIN_GS) & (d["gs"] / d["g"] >= 0.7)].copy()
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

    print("=== TOP 20 BY PROJECTED RoS FP/START (league-wide) ===")
    print(hdr); print("-" * len(hdr))
    for _, r in d.nlargest(20, "proj_ros_fp").iterrows():
        print(fmt(r))

    print("\n=== TOP 20 BREAKOUT CANDIDATES (elite Stuff+, lagging results) ===")
    print(hdr); print("-" * len(hdr))
    for _, r in d[d["stuff_pctl"] >= 60].nlargest(20, "breakout_gap").iterrows():
        print(fmt(r))

    if has_own:
        mine = d[d["own"] == "MINE"].sort_values("proj_ros_fp", ascending=False)
        fa = d[d["own"] == "FA"].sort_values("proj_ros_fp", ascending=False)
        print(f"\n=== YOUR SP STAFF ({len(mine)}) - ranked by projected RoS FP ===")
        print(hdr); print("-" * len(hdr))
        for _, r in mine.iterrows():
            print(fmt(r))
        worst_mine = mine["proj_ros_fp"].min() if len(mine) else 0
        print(f"\n=== TOP 15 FA SPs (projFP) - upgrades over your weakest "
              f"projected starter ({worst_mine:.1f}) flagged * ===")
        print(hdr); print("-" * len(hdr))
        for _, r in fa.nlargest(15, "proj_ros_fp").iterrows():
            star = " *" if r.proj_ros_fp > worst_mine else ""
            print(fmt(r) + star)
        print(f"\n=== TOP 12 FA BREAKOUT TARGETS (b/o gap, Stuff+ pctl>=60) ===")
        print(hdr); print("-" * len(hdr))
        for _, r in fa[fa["stuff_pctl"] >= 60].nlargest(12, "breakout_gap").iterrows():
            print(fmt(r))


if __name__ == "__main__":
    main()
