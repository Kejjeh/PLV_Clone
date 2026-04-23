# Process+ vs BatScore — Integration Analysis

*Unofficial public-data clone. Calibrated on 2021–2024 Statcast data, v1.0.0.*

---

## Why the Direct Merge Is More Complex Than It Looks

The natural assumption is: "strong Process+ but weak BatScore = buy; weak Process+ but strong BatScore = sell." The 2024 data reveals a critical complication:

**Power+ (a Process+ component) and xwOBA are nearly collinear (r = 0.985).**

Because Power+ measures xwOBA above pitch expectation on in-play balls, and BatScore measures batted-ball damage (exit velocity, barrel rate, hard-hit%), the two systems largely agree on who hits the ball hard. That's by design — Process+ is *not* independent of batted-ball quality.

**2024 Correlation Summary (413 qualified hitters, Pearson r):**

| Metric | vs xwOBA |
|---|---|
| Power+ | **0.985** — nearly identical ranking |
| Process+ | **0.887** — strong, mostly driven by Power+ |
| Decision+ | **0.157** — largely independent |
| Contact+ | **-0.398** — negatively correlated (discipline suppresses contact%) |

**Implication:** If you use absolute dual thresholds (Process+ strong AND xwOBA weak), you'll find almost no one — the two metrics largely rank hitters the same way. The useful signal is **rank divergence**, not absolute threshold crossings.

---

## The Correct Comparison: Rank Divergence

The `fantasy_hitter_merged_YYYY.csv` file provides:

| Column | Meaning |
|---|---|
| `pp_rank` | Process+ percentile (0–1) |
| `xwoba_rank` | xwOBA percentile (0–1) |
| `rank_gap` | `pp_rank - xwoba_rank` |
| `batscore_rank` | BatScore percentile (0–1) — NaN until BatScore data loaded |
| `pp_vs_bs_gap` | `pp_rank - batscore_rank` — populated after merge |
| `pp_bs_agreement` | `process_ahead` / `batscore_ahead` / `agree` |

**rank_gap distribution (2024):** std = 0.157, p25 = -0.074, p75 = +0.081.

Hitters with `rank_gap > 0.15` are outliers where Process+ materially outranks their surface results — these are buy candidates. Hitters with `rank_gap < -0.15` are the reverse.

---

## Component-Level Disagreement: Where the Real Novel Signal Lives

BatScore and Process+ differ most on Decision+ (r = 0.157 vs xwOBA). This is the independent signal.

**Decision+ tells you things BatScore cannot:**

1. **Is the hitter making correct swing/take decisions?** A hitter who chases 35% of pitches outside the zone but still runs a 0.400 xwOBA is a regression risk — their batted-ball quality is masking poor decisions. Decision+ flags this.

2. **Early-season stability.** Decision+ is reliable at 50 PA (split-half r = 0.741). BatScore-style exit velocity metrics require more contact events to stabilize. In April/May, Decision+ separates hitters before BatScore can.

3. **Walk rate and K% sustainability.** Decision+ correlates strongly with BB% and inversely with K% in ways that don't show up in exit velocity profiles.

---

## 2024 Disagreement Examples

### Process+ ahead of xwOBA (buy candidates — rank_gap > 0.35)

| Hitter | PA | Process+ | xwOBA | rank_gap | Signal |
|---|---|---|---|---|---|
| Luis Arráez | 712 | 107.2 | 0.329 | +0.471 | Elite decision-making, low power output; results understated |
| Ernie Clement | 463 | 102.3 | 0.301 | +0.470 | Strong process for a low-profile hitter |
| Jung Hoo Lee | 165 | 105.3 | 0.327 | +0.437 | Small sample; process ahead; monitor |

**Interpretation:** Arráez and Kwan are known discipline-first hitters — their Contact+ and Decision+ are strong but they don't generate the exit velocity that BatScore rewards. Their Process+ is "correct" about their hitter quality in a way that raw xwOBA undersells.

### xwOBA ahead of Process+ (regression risks — rank_gap < -0.35)

| Hitter | PA | Process+ | xwOBA | rank_gap | Signal |
|---|---|---|---|---|---|
| Davis Schneider | 465 | 93.2 | 0.377 | -0.460 | Chasing; strong batted-ball outcomes masking poor decisions |
| Will Benson | 389 | 96.4 | 0.399 | -0.450 | High raw power, low discipline |
| Michael Taylor | 311 | 95.2 | 0.381 | -0.438 | Below-average process across all components |

**Interpretation:** These hitters are generating surface value through raw power/barrel rate, but their Decision+ is weak. They are chase-prone. When pitchers locate better or adjust, the results will decline faster than their BatScore suggests.

---

## When Process+ and BatScore Would Disagree Most After Merge

Once BatScore data is loaded into `fantasy_hitter_merged_YYYY.csv`, filter on `pp_vs_bs_gap` to find actionable disagreements:

```python
import pandas as pd
merged = pd.read_csv("data/outputs/fantasy_hitter_merged_2024.csv")

# Process+ likes them; BatScore doesn't → stealth buy candidates
process_ahead = merged[merged["pp_bs_agreement"] == "process_ahead"].sort_values("pp_vs_bs_gap", ascending=False)

# BatScore likes them; Process+ doesn't → regression risks
batscore_ahead = merged[merged["pp_bs_agreement"] == "batscore_ahead"].sort_values("pp_vs_bs_gap")
```

Expected result: `dec_rank_vs_bs` will show the widest spreads — Decision+ is the least correlated with BatScore-style metrics. `pow_rank_vs_bs` should show tight agreement (near zero mean spread).

---

## How to Load Your BatScore CSV

```python
from plv_clone.pipelines.batscore_merge import run
from plv_clone.config import get_config

cfg = get_config()
merged = run(
    year=2024,
    batscore_path="path/to/your_batscore_2024.csv",  # provide your CSV
    config=cfg,
)
```

**Column detection is automatic.** The pipeline looks for these names in order:

- Player name: `Name`, `player_name`, `PlayerName`, `name`, `Player`
- Player ID (preferred): `MLBAMID`, `mlbam_id`, `player_id`, `batter`, `mlb_id`
- Score: `BatScore`, `batscore`, `Score`, `score`, `bat_score`

All other BatScore columns are retained with a `bs_` prefix. Merge diagnostics (match rate, unmatched players) are logged at INFO level.

**Match rate target:** If your BatScore file covers all qualified hitters, expect 85–95% name-match rate. MLBAM ID join is preferred and should reach 98%+.

---

## Caveats

1. **Power+ and BatScore overlap heavily.** Agreement between the systems on power hitters is expected and not a validation — it reflects shared data inputs (Statcast exit velocity underpins both).

2. **Process+ has no park adjustment.** A hitter who plays in Coors Field will have inflated xwOBA relative to their Process+ score. When comparing Process+ to park-adjusted BatScore, expect Coors hitters to appear in the "batscore_ahead" bucket for reasons unrelated to regression risk.

3. **Contact+ is negatively correlated with xwOBA (r = -0.398).** This is not a bug. Hitters with high Contact+ make contact on difficult pitches (low whiff rate) but those difficult pitches are less likely to result in hard contact. The metric captures execution quality, not damage.

4. **No BatScore data is included in this repository.** The merge template (`fantasy_hitter_merged_2024.csv`) ships with empty `batscore` and `batscore_rank` columns. Populate it using the pipeline above.

---

*Framework calibrated on 2024 data. Re-validate correlation structure each season using `scripts/validate_outputs.py`.*
