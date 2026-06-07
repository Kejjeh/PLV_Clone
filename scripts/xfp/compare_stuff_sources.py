"""
compare_stuff_sources.py  (research / one-off — DO NOT commit per task)

Determine whether our archetype STUFF (20-80, from build_sp_archetypes.py,
season-to-date Statcast) can REPLACE the brittle FanGraphs Stuff+ scrape as
the engine of /sp-stuff-board.

Four analyses:
  1. Clean predictive head-to-head (partial r over baseline + cross-year Ridge)
       - FG stuff_plus (as-of June6)
       - archetype STUFF (PRIOR year, clean)
       - archetype STUFF (full-season, flagged leaky)
  2. As-of availability: is there an in-season 2026 archetype STUFF, season-to-date?
  3. Ranking-equivalence on live 2026 pool (FG vs archetype breakout ranking)
  4. Coverage gap (FG-only vs archetype-only 2026 SPs)

Writes report to data/research/validation_runs/archetype_stuff_replacement_2026-06-06.md
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, "scripts/xfp")
from validate_fg_pitch_modeling_inseason import load as load_fg  # noqa: E402

ROOT = Path(".").resolve()
ARCH = ROOT / "data" / "research" / "sp_ratings_master.csv"
FG26 = ROOT / "data" / "research" / "fg_asof" / "fg_pit_2026_current.csv"
REPORT = ROOT / "data" / "research" / "validation_runs" / "archetype_stuff_replacement_2026-06-06.md"

YEARS = [2021, 2022, 2023, 2024, 2025]
TRAIN = [2021, 2022, 2023]
HOLD = [2024, 2025]
RATE = ["k_pct", "bb_pct", "swstr_pct", "siera"]
BASE = ["pre_fp"] + RATE

OUT = []  # report lines


def log(s=""):
    print(s)
    OUT.append(s)


def partial_r(df, x, y, controls):
    sub = df[[x, y] + controls].dropna()
    if len(sub) < 20:
        return np.nan, np.nan, len(sub)
    Z = sub[controls].values
    rx = sub[x].values - LinearRegression().fit(Z, sub[x]).predict(Z)
    ry = sub[y].values - LinearRegression().fit(Z, sub[y]).predict(Z)
    r, p = pearsonr(rx, ry)
    return r, p, len(sub)


def cross_year_r(train_df, test_df, feats):
    sub_tr = train_df[feats + ["ros_fp"]].dropna()
    sub_te = test_df[feats + ["ros_fp"]].dropna()
    if len(sub_tr) < 30 or len(sub_te) < 20:
        return np.nan, len(sub_te)
    sc = StandardScaler().fit(sub_tr[feats])
    Xtr, Xte = sc.transform(sub_tr[feats]), sc.transform(sub_te[feats])
    mdl = Ridge(alpha=1.0).fit(Xtr, sub_tr["ros_fp"])
    pred = mdl.predict(Xte)
    return pearsonr(pred, sub_te["ros_fp"])[0], len(sub_te)


# ---------------------------------------------------------------- load + merge
def build_frame():
    fg = load_fg()  # 506 SP-seasons 2021-25, mlb_id, stuff_plus(as-of), pre_fp, ros_fp, rates, year
    arch = pd.read_csv(ARCH)[["pitcher", "year", "STUFF"]].rename(
        columns={"pitcher": "mlb_id", "STUFF": "arch_stuff_full"}
    )
    arch["mlb_id"] = pd.to_numeric(arch["mlb_id"], errors="coerce").astype("Int64")
    fg["mlb_id"] = pd.to_numeric(fg["mlb_id"], errors="coerce").astype("Int64")

    # full-season archetype STUFF (same year) -- LEAKY
    df = fg.merge(arch, on=["mlb_id", "year"], how="left")
    # prior-year archetype STUFF (year-1) -- CLEAN
    arch_prior = arch.rename(columns={"arch_stuff_full": "arch_stuff_prior"}).copy()
    arch_prior["year"] = arch_prior["year"] + 1
    df = df.merge(arch_prior, on=["mlb_id", "year"], how="left")
    return df


def analysis_1(df):
    log("## 1. Clean predictive head-to-head (predicting ros_fp)\n")
    log(f"Frame: n={len(df)} FG SP-seasons 2021-25.")
    cov_fg = df["stuff_plus"].notna().sum()
    cov_full = df["arch_stuff_full"].notna().sum()
    cov_prior = df["arch_stuff_prior"].notna().sum()
    log(f"Coverage in frame: FG stuff_plus={cov_fg}, "
        f"archetype STUFF full-season={cov_full}, archetype STUFF prior-year={cov_prior}.\n")

    log("### Pooled partial r over baseline [pre_fp + k_pct + bb_pct + swstr_pct + siera]\n")
    log("| signal | raw r | partial r | p | n |")
    log("|---|---|---|---|---|")
    sigs = [
        ("FG stuff_plus (as-of)", "stuff_plus"),
        ("archetype STUFF (PRIOR yr, CLEAN)", "arch_stuff_prior"),
        ("archetype STUFF (full-season, LEAKY)", "arch_stuff_full"),
    ]
    pooled = {}
    for label, col in sigs:
        sub = df[[col, "ros_fp"]].dropna()
        raw = pearsonr(sub[col], sub["ros_fp"])[0] if len(sub) > 5 else np.nan
        pr, p, n = partial_r(df, col, "ros_fp", BASE)
        pooled[col] = (pr, p, n)
        log(f"| {label} | {raw:+.3f} | {pr:+.3f} | {p:.4f} | {n} |")
    log("")

    log("### Per-year partial r over baseline\n")
    log("| signal | " + " | ".join(str(y) for y in YEARS) + " | signs |")
    log("|---|" + "---|" * (len(YEARS) + 1))
    for label, col in sigs:
        base_sign = np.sign(pooled[col][0])
        cells, signs = [], 0
        for y in YEARS:
            r, _, n = partial_r(df[df.year == y], col, "ros_fp", BASE)
            cells.append(f"{r:+.3f}" if not np.isnan(r) else "n/a")
            if not np.isnan(r) and np.sign(r) == base_sign:
                signs += 1
        log(f"| {label} | " + " | ".join(cells) + f" | {signs}/5 |")
    log("")

    log("### Cross-year Ridge lift (train 2021-23 -> test 2024-25)\n")
    tr, te = df[df.year.isin(TRAIN)], df[df.year.isin(HOLD)]
    base_r, nte = cross_year_r(tr, te, BASE)
    log(f"Baseline [pre_fp + rate stats]: r = {base_r:.4f} (n_test={nte})\n")
    log("| + signal | r | gain |")
    log("|---|---|---|")
    for label, col in sigs:
        r, n = cross_year_r(tr, te, BASE + [col])
        gain = r - base_r if not np.isnan(r) else np.nan
        log(f"| {label} | {r:.4f} | {gain:+.4f} |")
    log("")
    return pooled


def analysis_2():
    log("## 2. As-of availability — is there a LIVE 2026 archetype STUFF?\n")
    arch = pd.read_csv(ARCH)
    y26 = arch[arch.year == 2026]
    log(f"- 2026 rows in sp_ratings_master.csv: **{len(y26)}**, "
        f"STUFF non-null: **{y26.STUFF.notna().sum()}**.")
    log(f"- 2026 gs range in archetype master: {int(y26.gs.min())}-{int(y26.gs.max())} "
        f"(GS_FLOOR_RATED=6 applied) -> season-to-date, NOT end-of-year.")
    multiyr = pd.read_csv(ROOT / "data/research/xfp_cache/sp_multiyr_2015_2025.csv")
    m26 = multiyr[multiyr.year == 2026]
    log(f"- Underlying Statcast source (sp_multiyr) 2026: {len(m26)} SPs, "
        f"gs {int(m26.gs.min())}-{int(m26.gs.max())} (mean {m26.gs.mean():.1f}).")
    log("- build_sp_archetypes.build_ratings_panel() rates STUFF from season-to-date "
        "k_pct / swstr_pct / c_plus_swstr aggregated per (pitcher, year); 2026 = games "
        "played to date. It is step 2.6 of refresh_dashboards.py, so it updates DAILY.")
    log("\n**Verdict 2b: YES — archetype STUFF is a live, season-to-date grade that refreshes daily.**\n")


def analysis_3_4(pooled):
    log("## 3. Ranking-equivalence on the live 2026 pool\n")
    fg = pd.read_csv(FG26)
    fg["mlb_id"] = pd.to_numeric(fg["mlb_id"], errors="coerce").astype("Int64")
    fg["gs"] = pd.to_numeric(fg["gs"], errors="coerce")
    fg = fg[fg["gs"] >= 5].copy()

    arch = pd.read_csv(ARCH)
    a26 = arch[arch.year == 2026][["pitcher", "player_name", "STUFF", "fp_per_start", "gs"]].copy()
    a26 = a26.rename(columns={"pitcher": "mlb_id"})
    a26["mlb_id"] = pd.to_numeric(a26["mlb_id"], errors="coerce").astype("Int64")

    j = fg.merge(a26, on="mlb_id", how="inner", suffixes=("_fg", "_arch"))
    log(f"Joined 2026 SPs (FG gs>=5 INNER archetype): n={len(j)}.\n")

    # correlation of the two stuff sources on live pool
    rp = pearsonr(j["stuff_plus"], j["STUFF"])[0]
    rs = spearmanr(j["stuff_plus"], j["STUFF"]).correlation
    log(f"- FG stuff_plus <-> archetype STUFF on 2026 pool: Pearson r = {rp:.3f}, "
        f"Spearman rho = {rs:.3f}.\n")

    # Build a simple breakout ranking BOTH ways.
    # Breakout = elite stuff, lagging current results (buy-low). We rank by a
    # z(stuff) - z(current fp_per_start) score so high-stuff/low-results float up,
    # using each stuff source. Use FG's fp (pre-cutoff proxy) consistently.
    j["fp"] = pd.to_numeric(j["fp_per_start"], errors="coerce")
    fp_fallback = j["fp"].fillna(j["fp"].median())

    def z(s):
        s = pd.to_numeric(s, errors="coerce")
        return (s - s.mean()) / s.std(ddof=0)

    z_fp = z(fp_fallback)
    j["score_fg"] = z(j["stuff_plus"]) - z_fp
    j["score_arch"] = z(j["STUFF"]) - z_fp
    j["rank_fg"] = j["score_fg"].rank(ascending=False, method="min")
    j["rank_arch"] = j["score_arch"].rank(ascending=False, method="min")

    rank_corr = spearmanr(j["rank_fg"], j["rank_arch"]).correlation
    log(f"- Breakout-ranking Spearman (FG-stuff ranking vs archetype-STUFF ranking): "
        f"rho = {rank_corr:.3f}.\n")

    top_fg = set(j.nsmallest(15, "rank_fg")["mlb_id"])
    top_arch = set(j.nsmallest(15, "rank_arch")["mlb_id"])
    overlap = top_fg & top_arch
    log(f"- Top-15 breakout name overlap: **{len(overlap)}/15** "
        f"({100*len(overlap)/15:.0f}%).\n")

    # Eury Perez check
    eury = j[j["player_name"].str.contains("Eury", case=False, na=False) |
            j["player_name_fg"].str.contains("Eury", case=False, na=False)]
    if len(eury):
        e = eury.iloc[0]
        log(f"- **Eury Perez check**: FG stuff_plus={e['stuff_plus']:.1f} "
            f"(rank {int(e['rank_fg'])}/{len(j)}), archetype STUFF={int(e['STUFF'])} "
            f"(rank {int(e['rank_arch'])}/{len(j)}). "
            f"Both rank him elite-stuff: {'YES' if e['rank_fg']<=15 and e['rank_arch']<=15 else 'see ranks'}.")
        # also raw stuff percentile
        p_fg = (j["stuff_plus"] < e["stuff_plus"]).mean() * 100
        p_arch = (j["STUFF"] < e["STUFF"]).mean() * 100
        log(f"  Raw stuff percentile in pool: FG {p_fg:.0f}th, archetype {p_arch:.0f}th.\n")
    else:
        log("- Eury Perez not found in joined 2026 pool (check coverage below).\n")

    # Side-by-side top ~15 by FG ranking
    log("### Side-by-side: top 15 breakout picks by FG ranking\n")
    log("| name | FG stuff+ | arch STUFF | rank_FG | rank_arch | d_rank |")
    log("|---|---|---|---|---|---|")
    show = j.nsmallest(15, "rank_fg").copy()
    nm = show["player_name"].fillna(show["player_name_fg"])
    for (_, r), name in zip(show.iterrows(), nm):
        d = int(r["rank_arch"] - r["rank_fg"])
        log(f"| {name} | {r['stuff_plus']:.0f} | {int(r['STUFF'])} | "
            f"{int(r['rank_fg'])} | {int(r['rank_arch'])} | {d:+d} |")
    log("")

    # ---- analysis 4: coverage gap
    log("## 4. Coverage gap (2026 live pool)\n")
    fg_ids = set(fg["mlb_id"].dropna())
    arch_ids = set(a26["mlb_id"].dropna())
    fg_only = fg_ids - arch_ids
    arch_only = arch_ids - fg_ids
    log(f"- FG 2026 SPs (gs>=5): {len(fg_ids)}")
    log(f"- Archetype 2026 SPs (gs>=6 floor): {len(arch_ids)}")
    log(f"- In both: {len(fg_ids & arch_ids)}")
    log(f"- **FG-only (have FG stuff, NO archetype STUFF): {len(fg_only)}** "
        f"— these LOSE a stuff grade if we drop FG.")
    log(f"- Archetype-only (archetype but not in FG gs>=5 pool): {len(arch_only)}.\n")

    # name the FG-only (likely rookies / small sample). Pull their FG gs.
    fg_only_df = fg[fg["mlb_id"].isin(fg_only)][["player_name_fg", "gs", "stuff_plus"]]
    fg_only_df = fg_only_df.sort_values("stuff_plus", ascending=False)
    log("### FG-only SPs (top 15 by FG stuff+) — the coverage we'd lose\n")
    log("| name | FG gs | FG stuff+ |")
    log("|---|---|---|")
    for _, r in fg_only_df.head(15).iterrows():
        log(f"| {r['player_name_fg']} | {r['gs']:.0f} | {r['stuff_plus']:.0f} |")
    log(f"\nMedian FG gs among FG-only: {fg_only_df['gs'].median():.0f} "
        f"(low gs => small-sample / callups, below archetype's gs>=6 floor).\n")
    return rank_corr, len(overlap), rp


def main():
    df = build_frame()
    log("# Archetype STUFF vs FanGraphs Stuff+ — replacement analysis")
    log("_2026-06-06 — research one-off (compare_stuff_sources.py). Not committed._\n")
    pooled = analysis_1(df)
    analysis_2()
    rank_corr, overlap, live_corr = analysis_3_4(pooled)

    # ---- recommendation
    log("## Recommendation\n")
    fg_pr = pooled["stuff_plus"][0]
    pri_pr = pooled["arch_stuff_prior"][0]
    log(f"- Predictive (clean): FG stuff_plus partial r = {fg_pr:+.3f}; "
        f"archetype STUFF (prior, clean) partial r = {pri_pr:+.3f}. "
        f"d = {pri_pr-fg_pr:+.3f}.")
    log(f"- Live stuff-source correlation (2026): r = {live_corr:.3f}.")
    log(f"- Breakout ranking agreement: Spearman {rank_corr:.3f}, "
        f"top-15 overlap {overlap}/15.")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(OUT), encoding="utf-8")
    print(f"\n[written] {REPORT}")


if __name__ == "__main__":
    main()
