"""
enrich_outputs — post-processing enrichment for fantasy + master-hitter exports.

Adds three columns to pitcher_fantasy_YYYY.csv and master_hitter_YYYY.csv:
  signal       — categorical tier (Top Target / Strong Add / Watchlist / Pass / Too Small)
  profile_flag — pitcher archetype tags (comma-separated)
  risk_flag    — hitter weakness/strength tags (comma-separated)
  sample_tier  — human-readable sample-size label
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path

from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)

_SIGNAL_LABELS = ["Top Target", "Strong Add", "Watchlist", "Pass"]
_SIGNAL_CUTOFFS = [85, 65, 45]  # pctile thresholds (upper-inclusive for each tier)


def _signal_from_pctile(pctile: float | None) -> str:
    if pctile is None or pd.isna(pctile):
        return "—"
    for label, cutoff in zip(_SIGNAL_LABELS, _SIGNAL_CUTOFFS):
        if pctile >= cutoff:
            return label
    return "Pass"


# ── Pitcher enrichment ────────────────────────────────────────────────────────

def _enrich_pitchers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    fp_median = df["fp_per_ip"].median() if "fp_per_ip" in df.columns else 0.0

    def _signal(row) -> str:
        if row.get("pitches", 0) < 150:
            return "Too Small"
        return _signal_from_pctile(row.get("plv_pctile"))

    def _profile(row) -> str:
        flags: list[str] = []
        plv_b = row.get("plv_blended", row.get("plv", 0.0)) or 0.0
        if plv_b >= 5.2:
            flags.append("Bat-Miss Elite")
        elif plv_b >= 5.0:
            flags.append("Bat-Miss Solid")
        elif row.get("fp_per_ip", 0.0) > fp_median:
            flags.append("Command/Location")
        is_closer = (row.get("pitcher_role") == "RP" and row.get("est_sv_per_162", 0) == 28)
        if is_closer:
            flags.append("Closer Value")
            if plv_b < 4.8:
                flags.append("Saves Risk")
        return ", ".join(flags)

    def _sample_tier(pitches) -> str:
        p = pitches or 0
        if p >= 400:
            return "Strong"
        if p >= 200:
            return "Okay"
        if p >= 100:
            return "Small"
        return "Too Small"

    df["signal"]       = df.apply(_signal, axis=1)
    df["profile_flag"] = df.apply(_profile, axis=1)
    df["sample_tier"]  = df["pitches"].apply(_sample_tier) if "pitches" in df.columns else "—"
    return df


# ── Hitter enrichment ─────────────────────────────────────────────────────────

def _enrich_hitters(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "proc_plus_positional" in df.columns:
        df["_ppp_pctile"] = df["proc_plus_positional"].rank(pct=True, na_option="keep") * 100
    else:
        df["_ppp_pctile"] = 50.0

    def _signal(row) -> str:
        bw = row.get("blend_weight", 1.0)
        pa = row.get("pa", 0)
        if (bw is None or pd.isna(bw) or bw < 0.15) or pa < 50:
            return "Too Small"
        return _signal_from_pctile(row.get("_ppp_pctile"))

    def _risk(row) -> str:
        flags: list[str] = []
        kav = row.get("k_avoidance_plus") or 100.0
        pwr = row.get("power_plus") or 100.0
        if pd.isna(kav):
            kav = 100.0
        if pd.isna(pwr):
            pwr = 100.0
        if kav < 85:
            flags.append("Chase Risk")
        elif kav < 90:
            flags.append("K Risk")
        if pwr > 115:
            flags.append("Power Flag")
        return ", ".join(flags)

    def _sample_tier(bw) -> str:
        if bw is None or pd.isna(bw):
            return "Too Small"
        if bw >= 0.60:
            return "Strong"
        if bw >= 0.35:
            return "Okay"
        if bw >= 0.15:
            return "Small"
        return "Too Small"

    df["signal"]      = df.apply(_signal, axis=1)
    df["risk_flag"]   = df.apply(_risk, axis=1)
    df["sample_tier"] = df["blend_weight"].apply(_sample_tier) if "blend_weight" in df.columns else "—"
    df.drop(columns=["_ppp_pctile"], inplace=True)
    return df


# ── Public entry point ────────────────────────────────────────────────────────

def enrich_outputs(year: int, outputs_dir: Path) -> None:
    """Read pitcher_fantasy and master_hitter CSVs, add enrichment columns, write back."""
    outputs_dir = Path(outputs_dir)

    pf_path = outputs_dir / f"pitcher_fantasy_{year}.csv"
    if pf_path.exists():
        pf = pd.read_csv(pf_path)
        pf = _enrich_pitchers(pf)
        pf.to_csv(pf_path, index=False)
        logger.info("Enriched pitcher_fantasy_%d.csv (%d rows)", year, len(pf))
    else:
        logger.warning("pitcher_fantasy_%d.csv not found — skipping.", year)

    mh_path = outputs_dir / f"master_hitter_{year}.csv"
    if mh_path.exists():
        mh = pd.read_csv(mh_path)
        mh = _enrich_hitters(mh)
        mh.to_csv(mh_path, index=False)
        logger.info("Enriched master_hitter_%d.csv (%d rows)", year, len(mh))
    else:
        logger.warning("master_hitter_%d.csv not found — skipping.", year)
