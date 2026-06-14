# AAA Statcast → MLB Rookie Performance — Feasibility + Validation Study

**Date:** 2026-06-13
**Author:** research agent (Opus 4.8)
**Question:** Do AAA velo / K% / whiff translate to MLB *rookie* BrownU FP/start?
If a call-up's AAA Statcast shows plus velo+whiff, can we project them **before**
they have any MLB data? (Extends our talent-prior + `/shadow-scout` tooling, which
today returns `NO_MLB_DATA` for true rookies.)
**Script:** `scripts/_oneoff/aaa_statcast_study.py`
**Caches written:** `data/research/aaa_statcast_cache/aaa_statcast_pitchers_{2023,2024}.csv`,
`aaa_statcast_mlb_joined.csv`

---

## 1. Data collectability (the feasibility half)

| Source | Has velo? | Has whiff? | Has K%/BB%? | Coverage | Cost |
|---|---|---|---|---|---|
| **Savant `statcast_search/csv?...&minors=true`** | **YES** (`release_speed`) | **YES** (`description=swinging_strike`) | derivable | pitch-level, all MiLB levels mixed | free, ~15 MB/day |
| MLB Stats API `sportId=11` | no | no | YES | season agg | free |
| Existing repo `milb_pitcher_stats_ext_{yr}_AAA.json` | no | no | **YES** (K/BB/BF) | full-season, 2015+ | already cached |
| `pybaseball` | — | — | — | **no `statcast_minor_league` fn** (v2.2.7) | n/a |

**Key feasibility findings:**

1. **AAA *Statcast* IS freely collectable** via Baseball Savant's hidden
   `minors=true` flag on `statcast_search/csv`. Returns pitch-by-pitch
   `release_speed` (velo), `pitch_type`, and `description` (→ whiff%, CSW%) for
   **all minor-league levels in one CSV**. There is **no level/league column**, so
   AAA is isolated by **team abbreviation** (the 30 `sportId=11` teams from the
   Stats API: ABQ, BUF, CLT, DUR, ELP, … WOR). Verified: 2023+2024 weekly pulls
   returned ~18–20k AAA pitches/week with real velo (mean 88 mph) and whiff tags.
2. **`pybaseball` has NO minor-league Statcast function** (2.2.7) — the Savant
   URL is the only path. Reusable in-repo now (cache builder in the script).
3. **The existing repo caches already give AAA K%/BB%** (from `battersFaced`,
   `strikeOuts`, `baseOnBalls`) with **full-season coverage back to 2015** — no
   new pull needed, and *broader* coverage than the sampled Statcast.
4. MLB outcome (`fp_per_start_to` from `rolling_pitchers_2018_2026.csv`) joins to
   AAA by **MLBAM `pitcher` id** — clean, no name matching.

**Collection caveats:** the Savant minors export is heavy (~15 MB/day), so the
script **samples 8 weekly windows/season** rather than the full year → median
**120 pitches/pitcher** (thin; FB-velo and whiff estimates are noisy at that n).
A production layer should either pull the full season (heavier) or lean on the
full-season K%/BB% from the STATS json.

---

## 2. Validation result (the predictive half)

**Design (leakage-safe):** AAA metrics from season **Y**; MLB outcome (season-
cumulative FP/start) from **Y** *or* **Y+1**, reported separately. The **Y+1 join
is fully leakage-safe** (entire AAA season predates the next MLB season) and is the
**headline**; same-year (Y) is shown only as a co-temporal sanity check. Filters:
≥3 AAA GS, ≥3 MLB GS; "rookie-ish" = ≤20 MLB GS. Pooled 2023+2024.

### Correlations with MLB FP/start (Pearson r)

**AAA STATS (K%/BB%) — broad coverage, no Statcast needed:**

| Predictor | Y+1 ALL (n=180) | Y+1 rookie≤20GS (n=122) | sameY ALL (n=204) |
|---|---|---|---|
| **AAA K%** | **+0.257** | +0.172 | **+0.312** |
| AAA BB% | −0.073 | −0.054 | −0.020 |
| **AAA K-BB%** | **+0.259** | +0.184 | +0.290 |

**AAA STATCAST (velo / whiff / CSW) — sampled, n thinner:**

| Predictor | Y+1 ALL (n=95) | Y+1 rookie≤20GS (n=70) |
|---|---|---|
| AAA FB velo | +0.054 | +0.031 |
| AAA avg velo | −0.010 | −0.035 |
| **AAA whiff% (swstr/pitch)** | **+0.196** | +0.140 |
| AAA CSW% | +0.132 | +0.035 |
| AAA whiff/swing | +0.164 | +0.116 |
| AAA K% (statcast subset) | +0.169 | +0.139 |
| **AAA K-BB% (statcast subset)** | **+0.205** | +0.178 |

### What this says

- **AAA velo does NOT translate** to MLB rookie FP (r ≈ 0, slightly negative for
  avg velo). Plus velo alone is **not** a buy signal — it's table stakes in AAA.
  *Do not headline a rookie on AAA velo.*
- **AAA whiff% / CSW% DO carry modest signal** (Y+1 r ≈ +0.13–0.25). A high-whiff
  AAA arm is a real, if weak, positive.
- **AAA K% and K-BB% are the strongest and most robust predictors**
  (Y+1 r ≈ +0.26), and crucially they come **free, full-season, 2015+** from the
  STATS json — *better coverage and equal/stronger correlation than the sampled
  Statcast.* K-BB% is the single best AAA→MLB SP signal here.
- Effect size is **modest** (r ≈ 0.18–0.26 ⇒ R² ≈ 0.03–0.07) but **we have
  literally nothing today** for a no-MLB-data rookie — this is strictly additive
  to `/shadow-scout`'s `NO_MLB_DATA` verdict.

**Face validity (top-whiff AAA arms → next-year MLB FP/start):** Shane Baz (10.6),
Andrew Abbott (11.1), Jack Leiter (11.0), Gavin Williams (10.1), Brandon Pfaadt
(11.0), David Festa (10.3), Ronel Blanco (14.3) — the high-AAA-whiff group mostly
became league-average-or-better MLB starters, with a minority of busts (Faedo 2.6,
Burke 6.7), exactly the spread a modest prior should produce.

---

## 3. VERDICT

**Worth building a prospect/call-up SP prior layer? YES — modest but real, and we
have nothing else for no-MLB rookies. Build it on AAA K-BB% (+ whiff% as confirm),
NOT velo.**

**Recommended source path (cheapest → best):**

1. **PRIMARY — AAA K-BB% from the existing STATS json** (`milb_pitcher_stats_ext_*`).
   Zero new data, full-season, 2015+, strongest correlation (Y+1 r ≈ +0.26). This
   alone is enough to seed a talent prior for a call-up with no MLB data.
2. **SECONDARY — AAA whiff%/CSW% from Savant `minors=true`** as a *process confirm*
   (Y+1 r ≈ +0.13–0.20). Worth pulling for the handful of fresh call-ups each week,
   not the whole AAA population. Mirrors `/shadow-scout`'s percentile approach but
   sourced from AAA instead of MLB.
3. **DROP velo as a ranker** — near-zero predictive value; keep only as a
   descriptive grade, never a buy signal.

**Honest limits / next steps before promotion:**
- Modest effect (R² ≈ 0.03–0.07); position as a **prior / tie-breaker**, not a
  point forecast — consistent with the repo's "lenses are conviction, not additive
  lift" rule (gotcha #13).
- n is small (Statcast Y+1 rookie n=70) and only 2 seasons; widen to 2018–2024 and
  pull **full-season** Statcast (not 8-week samples) before any `/validate-feature`
  promotion. The STATS-K-BB path can be validated immediately at full coverage.
- Survivorship: only AAA pitchers who *reached* MLB with ≥3 GS are in the sample;
  the prior predicts FP **conditional on being called up**, which is the exact
  decision context (a call-up just happened), so this is acceptable.
- Translate AAA→MLB with a level/run-environment haircut (AAA is a hitter-friendly,
  high-offense league) before putting AAA K-BB% on an MLB scale.

**Not promoted to any ranker.** This is a feasibility + validation pre-registration
only; the data path and the K-BB%-over-velo finding are the deliverables.
