"""milb_translation — AAA->MLB FP translation for hitters with no MLB track record.

WHY THESE FACTORS. No fitted model exists for zero-MLB-PA rookies (rh3 requires
real MLB PA to run), so this applies published MLE-lineage translation ranges
(Davenport/Tango) rather than an in-repo backtest. TB/BB/HBP/SB/R/RBI shrink
toward MLB-quality pitching; K is the one component that INFLATES against
better stuff. Treat outputs as a wide-uncertainty placeholder, not a rh3-grade
number — see blend_with_mlb_actual for folding in real MLB sample as it accrues.
"""
from __future__ import annotations

DEFAULT_FACTORS = {
    "tb": 0.80,
    "bb": 0.90,
    "hbp": 0.90,
    "k": 1.15,
    "sb": 0.85,
    "r": 0.82,
    "rbi": 0.82,
}


def translate_milb_to_mlb(stats, factors=DEFAULT_FACTORS, pa_per_game=4.2):
    pa = stats["pa"]
    if pa <= 0:
        raise ValueError(f"pa must be positive, got {pa}")

    rates = {}
    for component, factor in factors.items():
        rates[component] = (stats[component] / pa) * factor

    fp_per_pa = (
        rates["r"] + rates["tb"] + rates["rbi"]
        + rates["bb"] + rates["hbp"] + rates["sb"] - rates["k"]
    )

    out = dict(rates)
    out["fp_per_pa"] = fp_per_pa
    out["fp_per_game"] = fp_per_pa * pa_per_game
    out["fp_per_600"] = fp_per_pa * 600
    return out


def target_aaa_year(debut_date):
    debut_year = int(debut_date[:4])
    debut_month = int(debut_date[5:7])
    return debut_year - 1 if debut_month <= 4 else debut_year


def pick_mlb_actual(stats_by_year, debut_year, min_pa=100, lookahead_years=3):
    for offset in range(lookahead_years):
        stat = stats_by_year.get(debut_year + offset)
        if stat and stat.get("plateAppearances", 0) >= min_pa:
            return stat
    return None


def _api_stat_to_translate_stats(s):
    return {"pa": s["plateAppearances"], "r": s["runs"], "tb": s["totalBases"], "rbi": s["rbi"],
            "bb": s["baseOnBalls"], "hbp": s["hitByPitch"], "sb": s["stolenBases"], "k": s["strikeOuts"]}


def build_backtest_row(name, aaa_api_stat, mlb_api_stat, min_aaa_pa=150):
    if aaa_api_stat.get("plateAppearances", 0) < min_aaa_pa:
        return None
    aaa = _api_stat_to_translate_stats(aaa_api_stat)
    mlb = _api_stat_to_translate_stats(mlb_api_stat)
    pred = translate_milb_to_mlb(aaa)["fp_per_pa"]
    actual = (mlb["r"] + mlb["tb"] + mlb["rbi"] + mlb["bb"] + mlb["hbp"] + mlb["sb"] - mlb["k"]) / mlb["pa"]
    return {"name": name, "pred": pred, "actual": actual, "aaa_pa": aaa["pa"], "mlb_pa": mlb["pa"]}


def blend_with_mlb_actual(translated_rate, mlb_rate, mlb_n, credibility_n):
    if mlb_n < 0:
        raise ValueError(f"mlb_n must be non-negative, got {mlb_n}")
    if credibility_n <= 0:
        raise ValueError(f"credibility_n must be positive, got {credibility_n}")

    weight_mlb = mlb_n / (mlb_n + credibility_n)
    return weight_mlb * mlb_rate + (1 - weight_mlb) * translated_rate


def summarize_backtest(rows):
    n = len(rows)
    if n < 2:
        raise ValueError(f"summarize_backtest needs at least 2 rows, got {n}")
    errors = [r["pred"] - r["actual"] for r in rows]
    preds = [r["pred"] for r in rows]
    actuals = [r["actual"] for r in rows]

    mean_pred = sum(preds) / n
    mean_actual = sum(actuals) / n
    cov = sum((p - mean_pred) * (a - mean_actual) for p, a in zip(preds, actuals)) / n
    var_pred = sum((p - mean_pred) ** 2 for p in preds) / n
    var_actual = sum((a - mean_actual) ** 2 for a in actuals) / n
    pearson_r = cov / (var_pred * var_actual) ** 0.5
    slope = cov / var_pred
    intercept = mean_actual - slope * mean_pred

    return {
        "n": n,
        "mean_error": sum(errors) / n,
        "mean_abs_error": sum(abs(e) for e in errors) / n,
        "rmse": (sum(e ** 2 for e in errors) / n) ** 0.5,
        "pearson_r": pearson_r,
        "r_squared": pearson_r ** 2,
        "regression_slope": slope,
        "regression_intercept": intercept,
    }
