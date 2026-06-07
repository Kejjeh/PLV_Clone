"""
sp_floor_model.py — per-START bust-probability (floor) model for SPs.

Stuff+ predicts the MEAN; the bust/floor model (sp_location_investigation +
bust_model showed K-BB% drives the floor, not stuff) predicts the DOWNSIDE.
This goes per-start: P(this start busts, fp<5) from PRE-START info only.

Features (all known before first pitch — no leakage):
  prior_k_pct, prior_bb_pct  : pitcher's cumulative season-to-date rates BEFORE
                               this start (expanding mean, shifted)
  lineup_xfp                 : opponent lineup expected output (pre-start)
  days_rest                  : gap since previous start (clipped 3-7)
  n_prior_starts             : sample-stability / role proxy

Train 2018-2022 -> test 2023-2025. Reports AUC, calibration, base-rate lift.
Library fn `score_floor(prior_k, prior_bb, lineup_xfp, days_rest, n_prior)`.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT/"data/research/_boom_stack_per_start_panel_cache.parquet"
FEATS = ["prior_k_pct","prior_bb_pct","lineup_xfp","days_rest","n_prior_starts"]
BUST = 5.0
TRAIN = [2018,2019,2021,2022]; TEST = [2023,2024,2025]

def build_panel():
    p = pd.read_parquet(PANEL).sort_values(["pitcher","year","game_date"]).copy()
    p["game_date"] = pd.to_datetime(p["game_date"])
    g = p.groupby(["pitcher","year"], group_keys=False)
    # cumulative PRIOR (shifted) season-to-date rates
    p["cum_K"]  = g["actual_K"].cumsum()  - p["actual_K"]
    p["cum_BB"] = g["actual_BB"].cumsum() - p["actual_BB"]
    p["cum_PA"] = g["actual_PA"].cumsum() - p["actual_PA"]
    p["prior_k_pct"]  = p["cum_K"]/p["cum_PA"]
    p["prior_bb_pct"] = p["cum_BB"]/p["cum_PA"]
    p["days_rest"] = g["game_date"].diff().dt.days.clip(3,7)
    p["bust"] = (p["fp"] < BUST).astype(int)
    p = p[(p["n_prior_starts"]>=4) & (p["cum_PA"]>=40)].dropna(subset=FEATS+["bust"])
    return p

def main():
    p = build_panel()
    tr, te = p[p.year.isin(TRAIN)], p[p.year.isin(TEST)]
    print(f"per-start rows: train {len(tr)} ({TRAIN}), test {len(te)} ({TEST})")
    print(f"bust base rate: train {tr.bust.mean()*100:.1f}%  test {te.bust.mean()*100:.1f}%\n")

    sc = StandardScaler().fit(tr[FEATS])
    m = LogisticRegression(max_iter=1000).fit(sc.transform(tr[FEATS]), tr.bust)
    te = te.copy(); te["p"] = m.predict_proba(sc.transform(te[FEATS]))[:,1]

    auc = roc_auc_score(te.bust, te.p)
    print(f"TEST AUC = {auc:.3f}  (0.5=coinflip; >0.65 useful for a noisy per-start target)")
    print("\nStandardized coefs (log-odds of bust per +1 SD):")
    for f,c in sorted(zip(FEATS,m.coef_[0]),key=lambda t:-abs(t[1])):
        print(f"  {f:<16} {c:+.3f}")

    # calibration + lift by predicted-prob quintile (test)
    te["q"] = pd.qcut(te.p, 5, labels=["Q1 safest","Q2","Q3","Q4","Q5 riskiest"])
    print(f"\nCalibration / lift by predicted-bust quintile (test, base {te.bust.mean()*100:.0f}%):")
    print(f"  {'quintile':<12}{'pred%':>7}{'actual%':>9}{'n':>6}")
    for q,s in te.groupby("q",observed=True):
        print(f"  {str(q):<12}{s.p.mean()*100:>7.0f}{s.bust.mean()*100:>9.0f}{len(s):>6}")
    q5 = te[te.q=="Q5 riskiest"].bust.mean(); q1 = te[te.q=="Q1 safest"].bust.mean()
    print(f"\n  Riskiest quintile busts {q5*100:.0f}% vs safest {q1*100:.0f}% "
          f"-> {q5/q1:.1f}x separation. Mean pred(bust) {te[te.bust==1].p.mean()*100:.0f}% vs pred(no-bust) {te[te.bust==0].p.mean()*100:.0f}%.")

    # ablation: does opponent + rest add over command alone?
    for label,fs in [("command only (prior_k,prior_bb)",["prior_k_pct","prior_bb_pct"]),
                     ("+ opponent (lineup_xfp)",["prior_k_pct","prior_bb_pct","lineup_xfp"]),
                     ("+ rest + n_prior (full)",FEATS)]:
        s2=StandardScaler().fit(tr[fs]); mm=LogisticRegression(max_iter=1000).fit(s2.transform(tr[fs]),tr.bust)
        a=roc_auc_score(te.bust, mm.predict_proba(s2.transform(te[fs]))[:,1])
        print(f"  ablation AUC {label:<34} {a:.3f}")

def _production_fit():
    """Fit on ALL panel years for live scoring; return (scaler, model, means)."""
    p = build_panel()
    sc = StandardScaler().fit(p[FEATS])
    m = LogisticRegression(max_iter=1000).fit(sc.transform(p[FEATS]), p.bust)
    return sc, m, p[FEATS].mean()

def floor_tier(prob):
    if prob < 0.20: return "SAFE"
    if prob < 0.30: return "MODERATE"
    return "RISKY"

def staff_board():
    """Rank the user's SP staff by command-based bust probability (opponent-neutral).
    prior_k/bb come from each SP's 2026 season-to-date; opponent/rest set neutral."""
    import sys as _s
    _s.path.insert(0, str(Path(__file__).resolve().parent))
    from sp_stuff_model import build
    sc, m, means = _production_fit()
    d,_ = build(); mine = d[d.own=="MINE"][["mlb_id","player_name_fg","stuff_plus"]].copy()
    cur = pd.read_csv(ROOT/"data/research/fg_asof/fg_pit_2026_current.csv")
    for c in ["k_pct","bb_pct"]: cur[c]=pd.to_numeric(cur[c],errors="coerce")
    mp = mine.merge(cur[["mlb_id","k_pct","bb_pct"]],on="mlb_id").dropna(subset=["k_pct","bb_pct"])
    X = pd.DataFrame({"prior_k_pct":mp.k_pct,"prior_bb_pct":mp.bb_pct,
        "lineup_xfp":means["lineup_xfp"],"days_rest":5,"n_prior_starts":12})[FEATS]
    mp["bust_prob"] = m.predict_proba(sc.transform(X))[:,1]
    mp["tier"] = mp["bust_prob"].apply(floor_tier)
    mp = mp.sort_values("bust_prob",ascending=False)
    print("\n=== STAFF FLOOR BOARD (command-based bust prob, opponent-neutral) ===")
    print(f"  {'SP':<18}{'Stuff+':>7}{'K%':>6}{'BB%':>6}{'bustProb':>9}  tier")
    for _,r in mp.iterrows():
        print(f"  {r.player_name_fg:<18}{r.stuff_plus:>7.0f}{r.k_pct*100:>6.1f}{r.bb_pct*100:>6.1f}"
              f"{r.bust_prob*100:>8.0f}%  {r.tier}")
    print("  (RISKY = bench-first vs strong offenses; SAFE = highest floor. Opponent shifts ~+/-5pp.)")

if __name__=="__main__":
    import sys
    main()
    if "--staff" in sys.argv or True:
        staff_board()
