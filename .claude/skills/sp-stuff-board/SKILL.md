---
name: sp-stuff-board
description: SP breakout / FA-filter board driven by the VALIDATED FanGraphs Stuff+ in-season signal. Projects every 2026 SP's rest-of-season BrownU FP/start from a Stuff+-anchored model, tags MINE/opp/FA from a live ESPN call, and flags breakout candidates (elite Stuff+, lagging results = buy-low). Use when the user asks "stuff board", "stuff+ breakout candidates", "which FA SPs have the best stuff", "who's a buy-low SP", "rank SPs by stuff", or wants to compare their staff vs FAs on pitch quality.
---

# sp-stuff-board

You are running the Stuff+ breakout / FA-filter board. The headline number is a
**rest-of-season FP/start projection** from a model anchored on FanGraphs Stuff+,
the ONE pitch-modeling metric validated to predict SP fantasy points.

Engine: `python scripts/xfp/sp_stuff_model.py`

---

## Why Stuff+ (the validated foundation)

Full `/validate-feature` run 2026-06-06
(`data/research/validation_runs/fg_pitch_modeling_inseason_2026-06-06.md`,
PASS). In-season-leading design (metric as-of cutoff → RoS FP/start), n=506
SP-seasons 2021-25:

- **stuff_plus** — THE signal. Partial r 0.298 (p<1e-9) over a prior-FP + rate-stat
  baseline; 5/5 year-consistent; holdout +0.22/+0.42; cross-year Ridge lift +0.057.
- **Pitching+ / pb_stuff** — redundant (Pitching+ only correlates by embedding Stuff+).
- **Location+ / pb_command — REJECTED.** Command does NOT predict fantasy points:
  BrownU SP scoring (`K + IP*3.3 − H − 2*ER − BB − HBP`) rewards K/IP, not walk
  avoidance. Tested standalone, conditionally, as a stuff modulator, and over 45+9
  combinations — all fail. **Do not re-add location to this board.** See the REJECTED
  entry in `reference_validated_signals_registry.md`.

The canonical case: **Eury Pérez** — Stuff+ 117.6 (98th pct), Location+ 92.7 (7th
pct). Looks broken on ratios; the board correctly rates him a top BUY because his
elite stuff prints Ks and the walks barely cost points. His comps (Greene, Burnes,
Crochet, C.Sánchez) all improved RoS despite bad location.

---

## What the board outputs

1. **proj RoS FP/start** — validated Ridge: `pre_fp + k_pct + bb_pct + swstr_pct +
   siera + stuff_plus`, fit on 2021-25, applied to 2026 season-to-date SPs (GS≥5).
2. **breakout gap** = Stuff+ percentile − current-FP percentile (within the 2026 SP
   pool). High gap = elite stuff, lagging results = the buy-low the model catches.
3. **d_proj** = projected − current FP (positive = model expects improvement).
4. **ownership** = MINE / opp team name / FA, from a live `get_all_teams()` call.

Sections: top-20 league-wide by projFP; top-20 breakout candidates; YOUR staff
ranked; top-15 FA SPs (upgrades over your weakest starter flagged *); top-12 FA
breakout targets.

---

## Data dependency + refresh

Needs `data/research/fg_asof/fg_pit_2026_current.csv` (2026 season-to-date FG
snapshot WITH counting stats). Pull it via `python scripts/_oneoff/fg_2026_current.py`
(undetected-chromedriver — **run FOREGROUND**; backgrounding caused a Chrome runaway).
Cloudflare 403s the clean API path; the visible-browser scrape is the working route.
Re-pull weekly. Historical training snapshots live in `data/research/fg_asof/`.

---

## ⚠ MANDATORY DECLINE CROSS-CHECK (before headlining any "buy-low")

**Stuff+ measures stuff LEVEL, not TRAJECTORY.** A high-Stuff+ arm whose
results lag can be a genuine buy-low OR a veteran in real decline whose stuff
hasn't fully cratered yet but whose K-conversion has. The board CANNOT tell
these apart on its own — so any candidate flagged **high Stuff+ + lagging
results = "buy-low"** MUST be cross-checked against the three decline lenses
below BEFORE you headline a BUY:

1. **Archetype STUFF-rating YoY slope** — `data/research/sp_archetype_career_panel.parquet`
   (or `/sp-archetype profile <name>`). A STUFF rating dropping year-over-year
   (e.g. 56→46) is real erosion the in-season Stuff+ snapshot can lag.
2. **Sustainability K%/SwStr skill-decomp** — `python scripts/xfp/pitcher_sustainability.py --players "<name>"`.
   A REGRESS bucket with K% down + SwStr down = the strikeouts are actually
   leaving, not just unlucky.
3. **Archetype trajectory + comp T+1** — `/sp-archetype profile <name>` /
   `/triangulate`. TRENDING_DOWN with a negative slope, and age-matched comps
   averaging low FP/start at T+1, confirm the down-trend.

**Rule:** if **≥2 of those three signal real decline**, DOWNGRADE the headline
from **"BUY-LOW"** to **"DECLINING — back-end / defensible drop, not a buy."**
Do not lead with the Stuff+ buy. (Lens-merge protocol: a LEVEL lens loses to
converging TRAJECTORY lenses — see `reference_lens_merge_protocol.md` SP rule.)

### Worked example — Framber Valdez 2026 (the canonical trap)

In-season Stuff+ **103** with lagging box-score results → the board flagged him
as a Stuff+ "keep / buy-low." Headlined that way it was WRONG. The decline
cross-check showed the erosion was substantially REAL, not luck:

- Archetype **STUFF rating crashed 56 → 46** YoY (lens 1 — real).
- Sustainability **K% −4.7 pp, SwStr −2.4 pp** (lens 2 — real skill erosion).
- Archetype **TRENDING_DOWN (slope −4.5)**; nearest age-matched comps
  (Bassitt / Sánchez / Arrieta / Miley / Quintana) averaged only **10.7 FP/start
  at T+1** (lens 3 — real).

3 of 3 signaled decline → correct headline: **"DECLINING veteran near
replacement — defensible drop, NOT a Stuff+ buy-low."** The Stuff+ 103 only
says the raw stuff hasn't fully collapsed yet; it is blind to the trajectory
the other three lenses caught.

---

## Guardrails

- **Single-lens by design** — Stuff+ only. It ignores rp3, archetype, injury, role,
  and the 10-SP-cap. Use it as a FILTER that feeds `/triangulate` or
  `/fa-pickup-deep-dive` for a final verdict, NOT as the verdict itself.
- **Stuff+ is the MEAN, not the floor.** It predicts who scores most RoS (via velo),
  NOT who avoids dud starts. For "which start do I bench / avoid bad days," use
  `/sp-floor` (bust-risk, driven by K−BB% not stuff) — a low-Stuff+/high-command
  arm (Messick) can be your highest-FLOOR start. Don't bench on Stuff+ for floor.
- **Verify ownership before acting** — tagging is name-matched (minor SP collision
  risk); confirm FA availability live (`get_all_teams()`, the Connelly-Early rule).
- **Don't penalize bad location.** If you're tempted to fade a high-Stuff+ arm for
  walks/command, re-read the Pérez finding — that instinct is a ratio-league habit
  the points scoring doesn't share.
- Headline is the projection; the breakout gap is the discovery lens, not a verdict.
- **Never headline a veteran "buy-low" without the DECLINE CROSS-CHECK above.**
  Stuff+ is a LEVEL lens, blind to trajectory — a lagging-results vet can be in
  real decline (Framber 2026). Run archetype STUFF slope + sustainability K%/SwStr
  + comp T+1 first; ≥2 declining → headline the DECLINE, not the buy.
