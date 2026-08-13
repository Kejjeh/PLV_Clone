"""
xfp_bx panel builder — box-score-era player-season panels.

Source: MLB Stats API season stats (https://statsapi.mlb.com/api/v1/stats),
which serves full-history season lines (verified live 2026-07-10: 1972
pitching and 1975 hitting return complete splits with age, HBP, TB, SB).
Lahman via pybaseball is broken (stale zip URL -> BadZipFile), and the
baseballdatabank raw CSV path 404s, so the Stats API is BOTH the deep
history and the recent-season source — one consistent feed, natively
mlbam-keyed.

ID crosswalk: pybaseball.chadwick_register() -> key_bbref (identical to
the Lahman playerID for effectively all players) + key_retro. Cached at
raw/chadwick_register.csv.

Outputs:
  data/research/boxscore_era/hitter_season_panel.csv   (1960-2026)
  data/research/boxscore_era/pitcher_season_panel.csv  (1970-2026)
  raw/hitting_{yr}.json, raw/pitching_{yr}.json        (API cache)

History constraints (documented, enforced downstream):
  - HBP: recorded for the full window (verified 1972+).
  - SV: official 1969+ (panel starts pitching at 1970 -> always valid).
  - HLD: only ~2000+ (verified: 1972 has no 'holds' key; 2004 has 258
    pitchers with holds>0). RP FP is therefore fully computable only
    2000+; the RP leg of the panel is restricted to 2000+.
  - TB from H/2B/3B/HR: 'totalBases' served directly by the API.

Scoring (BrownU):
  HITTER FP = R + TB + RBI + BB + HBP + SB - K
  PITCH  FP = K + IP*3.3 - H - 2*ER - BB - HBP   (+5*SV + 2*HLD for RP)
"""
from __future__ import annotations
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
RAW.mkdir(exist_ok=True)

HIT_YEARS = range(1960, 2027)
PIT_YEARS = range(1970, 2027)
BASE = "https://statsapi.mlb.com/api/v1/stats"


def _fetch_season(year: int, group: str) -> list[dict]:
    """Fetch (with disk cache) all season splits for one year/group."""
    cache = RAW / f"{group}_{year}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    splits: list[dict] = []
    offset = 0
    while True:
        params = {
            "stats": "season", "group": group, "season": year,
            "sportId": 1, "playerPool": "all", "limit": 5000,
            "offset": offset,
        }
        r = requests.get(BASE, params=params, timeout=60)
        r.raise_for_status()
        stats = r.json().get("stats", [])
        if not stats:
            break
        chunk = stats[0].get("splits", [])
        splits.extend(chunk)
        total = stats[0].get("totalSplits", len(splits))
        if len(splits) >= total or not chunk:
            break
        offset = len(splits)
        time.sleep(0.3)
    cache.write_text(json.dumps(splits), encoding="utf-8")
    time.sleep(0.4)  # be polite
    return splits


def _ip_to_float(ip) -> float:
    """'123.1' baseball notation -> 123 + 1/3."""
    if ip is None:
        return np.nan
    s = str(ip)
    if "." in s:
        whole, frac = s.split(".")
        return int(whole) + int(frac) / 3.0
    return float(s)


def _num(stat: dict, key: str, default=0.0) -> float:
    v = stat.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def build_hitters() -> pd.DataFrame:
    rows = []
    for yr in HIT_YEARS:
        for s in _fetch_season(yr, "hitting"):
            st = s["stat"]
            pa = _num(st, "plateAppearances")
            if pa <= 0:
                continue
            ab = _num(st, "atBats")
            h = _num(st, "hits")
            hr = _num(st, "homeRuns")
            k = _num(st, "strikeOuts")
            bb = _num(st, "baseOnBalls")
            hbp = _num(st, "hitByPitch")
            sb = _num(st, "stolenBases")
            r = _num(st, "runs")
            rbi = _num(st, "rbi")
            tb = _num(st, "totalBases")
            sf = _num(st, "sacFlies")
            fp = r + tb + rbi + bb + hbp + sb - k
            babip_den = ab - k - hr + sf
            rows.append({
                "mlbam": s["player"]["id"],
                "player_name": s["player"].get("fullName"),
                "year": yr,
                "age": st.get("age"),
                "pa": pa, "ab": ab, "g": _num(st, "gamesPlayed"),
                "k_pct": k / pa,
                "bb_pct": bb / pa,
                "hbp_per_pa": hbp / pa,
                "iso": (tb - h) / ab if ab > 0 else np.nan,
                "hr_per_pa": hr / pa,
                "sb_per_pa": sb / pa,
                "babip": (h - hr) / babip_den if babip_den > 0 else np.nan,
                "r_per_pa": r / pa,
                "rbi_per_pa": rbi / pa,
                "fp_total": fp,
                "fp_per_pa": fp / pa,
            })
        print(f"  hitting {yr}: done ({len(rows)} cumulative rows)")
    return pd.DataFrame(rows)


def build_pitchers() -> pd.DataFrame:
    rows = []
    for yr in PIT_YEARS:
        for s in _fetch_season(yr, "pitching"):
            st = s["stat"]
            ip = _ip_to_float(st.get("inningsPitched"))
            if not np.isfinite(ip) or ip <= 0:
                continue
            g = _num(st, "gamesPlayed")
            gs = _num(st, "gamesStarted")
            k = _num(st, "strikeOuts")
            bb = _num(st, "baseOnBalls")
            hbp = _num(st, "hitByPitch")
            h = _num(st, "hits")
            er = _num(st, "earnedRuns")
            hr = _num(st, "homeRuns")
            sv = _num(st, "saves")
            hld = _num(st, "holds") if "holds" in st else np.nan
            bf = _num(st, "battersFaced")
            if bf <= 0:  # approximate BF when absent
                bf = 3 * ip + h + bb + hbp
            fp_base = k + ip * 3.3 - h - 2 * er - bb - hbp
            rows.append({
                "mlbam": s["player"]["id"],
                "player_name": s["player"].get("fullName"),
                "year": yr,
                "age": st.get("age"),
                "g": g, "gs": gs, "ip": ip, "bf": bf,
                "ip_per_gs": ip / gs if gs > 0 else np.nan,
                "k_pct": k / bf,
                "bb_pct": bb / bf,
                "hr9": 9 * hr / ip,
                "era": 9 * er / ip,
                # FIP from box with fixed 3.10 constant (era-relative use
                # only; downstream models z-score within year anyway)
                "fip_box": (13 * hr + 3 * (bb + hbp) - 2 * k) / ip + 3.10,
                "sv": sv, "hld": hld,
                "fp_total_base": fp_base,
                "fp_per_start": fp_base / gs if gs > 0 else np.nan,
                # RP FP only valid where holds exist (~2000+)
                "fp_total_rp": (fp_base + 5 * sv + 3 * hld)
                               if np.isfinite(hld) else np.nan,
                "fp_per_g_rp": ((fp_base + 5 * sv + 3 * hld) / g)
                               if (np.isfinite(hld) and g > 0) else np.nan,
            })
        print(f"  pitching {yr}: done ({len(rows)} cumulative rows)")
    return pd.DataFrame(rows)


def attach_crosswalk(df: pd.DataFrame) -> pd.DataFrame:
    """Attach lahman-compatible (bbref) + retro ids via Chadwick register."""
    cw_path = RAW / "chadwick_register.csv"
    if cw_path.exists():
        reg = pd.read_csv(cw_path)
    else:
        from pybaseball import chadwick_register
        reg = chadwick_register()
        reg.to_csv(cw_path, index=False)
    reg = reg.dropna(subset=["key_mlbam"]).drop_duplicates("key_mlbam")
    reg["key_mlbam"] = reg["key_mlbam"].astype(int)
    xw = reg[["key_mlbam", "key_bbref", "key_retro"]].rename(
        columns={"key_mlbam": "mlbam", "key_bbref": "lahman_id",
                 "key_retro": "retro_id"})
    return df.merge(xw, on="mlbam", how="left")


def main():
    print("=== xfp_bx panel build ===")
    print("Hitters 1960-2026 ...")
    hit = build_hitters()
    hit = attach_crosswalk(hit)
    hit.to_csv(HERE / "hitter_season_panel.csv", index=False)
    print(f"wrote hitter_season_panel.csv: {len(hit)} rows")

    print("Pitchers 1970-2026 ...")
    pit = build_pitchers()
    pit = attach_crosswalk(pit)
    pit.to_csv(HERE / "pitcher_season_panel.csv", index=False)
    print(f"wrote pitcher_season_panel.csv: {len(pit)} rows")

    # Coverage by decade
    for name, df, vol in [("HITTERS", hit, "pa"), ("PITCHERS", pit, "ip")]:
        df = df.copy()
        df["decade"] = (df["year"] // 10) * 10
        cov = df.groupby("decade").agg(
            rows=("mlbam", "size"),
            players=("mlbam", "nunique"),
            xwalk_pct=("lahman_id", lambda s: 100 * s.notna().mean()),
            vol_sum=(vol, "sum"),
        )
        print(f"\n{name} coverage by decade:\n{cov.round(1).to_string()}")


if __name__ == "__main__":
    main()
