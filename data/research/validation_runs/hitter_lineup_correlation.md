# Hitter Lineup Correlation — Do teammates booming predict you booming?

Generated 2026-06-03. Built from hitter_boom_bust_panel.parquet (245,712 batter-game rows, 33,839 team-day rows, years [2018, 2019, 2021, 2022, 2023, 2024, 2025]).

## Framing

- `boom_stack` is the validated per-hitter pre-game signal (skill_spike + recform_hot + opp_soft), built leakage-safe in `analyze_hitter_boom_bust.py`.
- `lineup_stack2_count` = # starters on a team-day with `boom_stack >= 2` going IN to the game. Computed at PRE-game time (boom_stack uses only data strictly prior to the game).
- `teammates_stack2` = `lineup_stack2_count` minus self (the right measure for individual amplification).
- `team_boom`: team's total fp_proxy across all its starters that day >= 15.0 (empirical 80th pct of team-days).
- `team_opp_soft`: the team is facing an SP whose prior-only xwoba_to is in the top tertile within (year, month). Identical for every hitter on the team by construction.

## 1. Heatmap — individual hitter boom rate by (own_stack x teammates_stack2)

Rate (%) of boom_game by own boom_stack (rows) and # OTHER teammates with stack >= 2 (cols):

| own_stack | 0 | 1 | 2 | 3+ |
|---|---|---|---|---|
| 0 | 23.9% (n=153,037) | 24.1% (n=8,402) | 27.2% (n=313) | - |
| 1 | 25.0% (n=43,444) | 26.2% (n=22,483) | 26.8% (n=7,425) | 28.2% (n=1,882) |
| 2 | 27.0% (n=4,440) | 27.4% (n=2,398) | 28.9% (n=865) | 32.5% (n=268) |
| 3 | 28.2% (n=323) | 31.4% (n=274) | 31.6% (n=95) | - |

**Read:** moving DOWN a column shows the own_stack edge holding teammate-count fixed. Moving RIGHT across a row shows the teammate amplification holding own_stack fixed.

**Headline amplification reads:**
- own_stack=1: boom rate 25.0% (n=43,444) at 0 teammates_stack2 -> 28.2% (n=1,882) at 3+ teammates. Delta +3.1 pp.
- own_stack=2: boom rate 27.0% (n=4,440) at 0 teammates_stack2 -> 32.5% (n=268) at 3+ teammates. Delta +5.5 pp.

## 2. Team-level boom rate by lineup_stack2_count

| lineup_stack2_count | n_team_days | mean team fp_proxy | team_boom rate |
|---|---|---|---|
| 0 | 27,344 | 8.23 | 19.7% |
| 1 | 4,763 | 9.53 | 25.0% |
| 2 | 1,336 | 10.64 | 28.2% |
| 3+ | 396 | 11.84 | 33.8% |

**Team boom edge (lineup_stack2 = 3+ vs = 0): +14.2 pp**

## 3. Year-by-year stability — team boom rate edge

| year | n(=0) | n(=3+) | rate(=0) | rate(=3+) | edge |
|---|---|---|---|---|---|
| 2018 | 3,999 | 58 | 21.3% | 34.5% | +13.2 pp |
| 2019 | 3,927 | 59 | 23.6% | 45.8% | +22.2 pp |
| 2021 | 3,792 | 61 | 18.7% | 24.6% | +5.9 pp |
| 2022 | 3,878 | 57 | 17.3% | 36.8% | +19.6 pp |
| 2023 | 3,879 | 83 | 20.2% | 34.9% | +14.8 pp |
| 2024 | 3,897 | 40 | 17.9% | 27.5% | +9.6 pp |
| 2025 | 3,972 | 38 | 18.8% | 28.9% | +10.1 pp |

## 4. Independence vs opp_soft — does lineup_stack add lift on top of opp_soft?

opp_soft is already team-level (every hitter on the team faces the same SP). If lineup_stack2 is mostly a proxy for opp_soft, stratifying by opp_soft should flatten the edge.

| opp_soft | stack2_bucket | n | team_boom rate | mean team fp_proxy |
|---|---|---|---|---|
| 0 | 0 | 23,018 | 19.2% | 8.10 |
| 0 | 1 | 1,449 | 21.6% | 8.67 |
| 0 | 2 | 62 | 25.8% | 10.10 |
| 0 | 3+ | 3 | 0.0% | 3.00 |
| 1 | 0 | 4,326 | 22.2% | 8.95 |
| 1 | 1 | 3,314 | 26.6% | 9.90 |
| 1 | 2 | 1,274 | 28.3% | 10.67 |
| 1 | 3+ | 393 | 34.1% | 11.90 |

**Within-stratum edge (high vs =0), using min-n=30 on high cell:**
- normal opp: lineup_stack2 = 2 (3+ too thin) (n=62) vs = 0 = +6.6 pp
- soft opp: lineup_stack2 = 3+ (n=393) vs = 0 = +11.9 pp

Note: in the normal-opp stratum the (lineup_stack2=3+) cell is mechanically sparse because opp_soft is one of the three flags that drives a hitter's individual boom_stack to 2+. We therefore fall back to the 2-bucket on the normal-opp side, which still has a reasonable sample.

## 5. lineup_stack_amplification flag

Flag fires when: own boom_stack >= 1 AND >= 2 other teammates also have boom_stack >= 1 going in.

| lineup_amp | n | boom rate | bust rate | mean fp_proxy |
|---|---|---|---|---|
| 0 | 174,665 | 23.9% | 43.5% | 1.12 |
| 1 | 71,047 | 26.2% | 40.0% | 1.31 |

**lineup_stack_amplification raw edge: +2.3 pp boom rate**

### 5a. Amp flag year-by-year

| year | n(on) | rate(on) | rate(off) | edge |
|---|---|---|---|---|
| 2018 | 10,211 | 26.2% | 24.8% | +1.4 pp |
| 2019 | 10,085 | 28.2% | 26.5% | +1.7 pp |
| 2021 | 9,905 | 26.9% | 24.1% | +2.8 pp |
| 2022 | 10,215 | 25.2% | 22.2% | +3.0 pp |
| 2023 | 10,451 | 26.7% | 24.0% | +2.7 pp |
| 2024 | 10,097 | 25.0% | 22.6% | +2.4 pp |
| 2025 | 10,083 | 25.2% | 23.2% | +1.9 pp |

### 5b. Amp flag INDEPENDENCE — does it add lift on top of own boom_stack?

Stratify by own boom_stack. If amp is just a proxy for own stack, the within-stratum edge should be ~0.

| own_stack | lineup_amp | n | boom rate | bust rate |
|---|---|---|---|---|
| 0 | 0 | 161,766 | 23.9% | 43.4% |
| 1 | 0 | 11,595 | 23.7% | 44.0% |
| 1 | 1 | 63,639 | 26.0% | 40.1% |
| 2 | 0 | 1,303 | 25.8% | 43.4% |
| 2 | 1 | 6,668 | 27.8% | 39.6% |
| 3 | 0 | 1 | 0.0% | 100.0% |
| 3 | 1 | 740 | 30.7% | 37.4% |

**Within-stratum amp edge (on vs off):**
- own_stack=1: 23.7% (n=11,595) -> 26.0% (n=63,639) = +2.2 pp
- own_stack=2: 25.8% (n=1,303) -> 27.8% (n=6,668) = +2.0 pp
- own_stack=3: 0.0% (n=1) -> 30.7% (n=740) = +30.7 pp

## 6. Verdict

- Team-level boom edge (lineup_stack2 = 3+ vs = 0): **+14.2 pp**
- Year-by-year team-edge stability: **+5.9 to +22.2 pp** across 7 years
- lineup_stack_amplification raw edge (hitter level): **+2.3 pp**
- amp edge AFTER stratifying by own boom_stack (avg across own=1,2): **+2.1 pp**
- team-stack edge AFTER stratifying by opp_soft (avg across both opp_soft strata, min-n=30 high cell): **+9.3 pp**

### VERDICT: **SHIP_AS_4TH_HITTER_COMPONENT**

lineup_stack_amplification adds +2.1 pp boom rate on top of own boom_stack (year-stable: +1.4 to +3.0 pp across 7 years, never negative). The team-level edge of +14.2 pp (year-stable +5.9 to +22.2 pp) confirms the underlying lineup-correlation phenomenon is real. The within-soft-opp stratum edge (+11.9 pp on opp_soft=1) confirms it is not purely opp_soft re-expressed. The component magnitude (+2.1 pp) is in the same range as the already-shipped skill_spike (+1.1 pp), recform_hot (+3.7 pp), and opp_soft (+2.2 pp) components. SHIP-CAUTIOUS as a 4th component on the existing DISPLAY-TAG-ONLY footing.

### Engine integration spec (if SHIP_AS_4TH_HITTER_COMPONENT)

- Component name: `lineup_amp_hitter` (or similar).
- Compute in `scripts/xfp/lib/hitter_boom_stack.py`:
  - For the target hitter, compute their boom_stack (already done).
  - Pull the day's confirmed lineup for the hitter's team via MLB Stats API.
  - For each lineup-mate, compute their boom_stack live the same way.
  - Flag = 1 if own boom_stack >= 1 AND >= 2 other starters have boom_stack >= 1.
- New boom_stack range becomes 0-4.
- Update `BOOM_RATE_BY_STACK` / `BUST_RATE_BY_STACK` tables in lib.
- DISPLAY TAG ONLY — same caveats as current boom_stack.

### Engine integration spec (if SHIP_AS_TEAM_BADGE_ONLY)

- Add a `team_lineup_heat` field to triangulate cards: count of starters on the hitter's team-day with `boom_stack >= 2`.
- Surface as "team stack: N/9 hitters hot" badge.
- Do NOT modify per-hitter boom_stack scoring or rh3.