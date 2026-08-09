---
name: decision-trend
description: In-season hitter swing-DECISION tracker — chase%, z-swing%, decision_gap vs the hitter's own pre-window baseline, flagging real approach changes (APPROACH SHIFT ▲/▼, drifting, stable). Use when asked "is X's approach changing", "decision trend", "who's getting more/less selective", or before any FA-hitter compare. Windows are validated (decision_window_study 2026-07-18): L21 = solid read, L7 = early hint. Rule 13 — detects behavior change, NEVER re-ranks; decision shifts add ~0 forward FP beyond the scoring level (all 20 cells null).
---

# decision-trend

## What this is

Plate-discipline parallel of `/trending` (which covers the physical axis:
bat speed / attack angle). Computes chase%, z-swing%, decision_gap
(zSwing − chase), swing% over L21 and L7 from pitch-level statcast, deltas
vs the hitter's OWN season baseline before the window, z-scored against
cross-player spreads → `stable / drifting ▲▼ / APPROACH SHIFT ▲▼`.

## Evidence base (do not re-derive)

`decision_window_study.py` (13,939 obs / 483 players / 2024-26, FDR):
- Persistence: ALL windows real — even L7 chase carries r=0.20 beyond the
  hitter's own baseline, monotone to r~0.36-0.42 at L45. No noise cliff.
- FP relevance: ALL null. A decision shift is real BEHAVIOR long before /
  without being real fantasy VALUE. Hence Rule 13: context lens only.

## Run

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/run_decision_trend.py            # my roster
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/run_decision_trend.py --names "A,B,C"
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/run_decision_trend.py --scope fa  # FA pool
```

### `--scope fa` (added 2026-08-09)

Scans the free-agent hitter pool (live roster scan, never `percent_owned`),
filtered to `--min-pa-vol` projected PA/team-game since an approach change on
a bench bat is unactionable either way.

**Expect most rows to come back `sample short — below stabilization min`, and
treat that as the ANSWER, not a failure.** On the first live run **1 of 143**
FA hitters cleared 150 OOZ + 150 IZ pitches in an L21 window. Part-time
players simply do not accumulate decision-grade samples that fast — which is
exactly why the gate exists, and exactly the read you would have gotten wrong
by eyeballing raw chase% on 70 pitches.

**FA scope answers "whose approach is changing out there", NOT "who should I
add."** The FP-relevance finding below is unchanged by scope: a decision shift
is real behavior with ~0 forward-FP value beyond the scoring level. An FA
board is the single easiest place to misread that, so the flag help text says
so too.

## Reading rules

1. LOWER chase = better; HIGHER decision_gap = better. swing% is
   direction-neutral (aggression, not quality).
2. An APPROACH SHIFT ▼ (Muncy 2026-07-18: chase +6.3pp) is a watch flag,
   not a demotion — pair with `/trending` (physical) + the FP level before
   any roster action.
3. High z-swing + high chase = swing-mode, not selectivity (Rafaela
   canonical: L7 chase 62%).
4. Name resolution: resolver falls back to MLB `people/search` (accent-
   tolerant). If a row prints "no 2026 pitches", the id is wrong — check
   collisions (`/player-id-resolve`), don't trust the row.
