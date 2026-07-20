---
name: decision-gates
description: Pre-registered, self-pruning roster-decision gates. Use when a decision is being deferred to a measurable condition ("if his velo is still down next start, he's the cut", "two more cold starts and he's the drop", "if he keeps starting 5 of 6, claim him back") — register it as a gate instead of prose. Check gates every Monday (monday-morning Step 3c runs this) or any time before executing a deferred decision. Triggers - "add a gate", "check my gates", "what gates are open", "register this decision", "did the Messick gate trigger".
---

# decision-gates

First-class version of the July pattern (Messick post-break velo, Peralta 2H
thesis, Canzone-vs-Mead earmark, Clemens PT watch): every deferred roster
decision gets a MEASURABLE condition, a decision it controls, an expiry, and
a weekly check — instead of hand-edited prose that goes stale.

Engine + state:

```bash
python -X utf8 scripts/xfp/run_decision_gates.py check      # the Monday call
python -X utf8 scripts/xfp/run_decision_gates.py list
python -X utf8 scripts/xfp/run_decision_gates.py add --id <slug> --player "Name" \
    --bucket SP|RP|H --metric <m> --cmp "<|<=|>|>=" --threshold N [--n N] \
    --decision "what executing this gate means" \
    [--check-from YYYY-MM-DD] [--expires YYYY-MM-DD] [--notes "..."]
python -X utf8 scripts/xfp/run_decision_gates.py resolve <id>   # after acting
```

State lives in `data/research/decision_gates.json` (tracked — durable).

## Metrics (small on purpose)

| metric | measures | source |
|---|---|---|
| `fb_velo_last_start` | mean FF/SI velo in the LAST start (≥ check-from) | statcast_2026.parquet |
| `fp_lastN` | mean BrownU FP over last N games (bucket-aware) | boxscore store via lib/boom_bust |
| `fp_last_start` | last single-game FP | same |
| `games_lastN` | appearances in trailing N DAYS (PT watch) | boxscore store |
| `manual` | criteria text displayed verbatim, judged by eye | — |

Anything not expressible above → `--metric manual --criteria "..."`. Do NOT
grow the metric set casually — a gate metric is a decision input; new
automated metrics need the same scrutiny as any decision layer.

## Statuses

**OPEN** (awaiting data / before check-from) · **TRIGGERED** (condition met —
execute the decision, then `resolve <id>`) · **CLEARED** (data in, condition
false) · **EXPIRED** (prune). Rule 12: never edit a gate's decision text in
place — `remove` + `add` under a new id so the audit trail is honest.

## Rules of use

- A TRIGGERED gate is a strong prior, not an auto-execute: sanity-check with
  the current lens stack (/triangulate) before acting, especially when the
  metric is a proxy (e.g. `games_lastN` counts appearances, not starts).
- The 4-RP floor and all standing roster rules still bind whatever a gate
  says.
- Gates that control the SAME cut compete (Messick-velo vs Peralta-2H for
  the 7/27 Fried slot) — note the pairing in `--notes` on both.
- monday-morning Step 3c = `run_decision_gates.py check` (migrated
  2026-07-20; the four July gates were seeded into the state file then).
