---
name: hitter-sustainability
description: ALIAS → /hitter-form --scope roster|fa. Recipe lives below; routing/triggers live on the canonical.
---

> **⚠ MERGED (2026-07-20) → `/hitter-form --scope roster` / `--scope fa`.** This
> SKILL holds the complete 9-marker sweep recipe (my-roster, fa-pool, and
> `--players` list modes) and stays live as the delegate; new invocations should
> prefer `/hitter-form` (routing + trigger phrases live on the canonical).

# hitter-sustainability

Direct mirror of `/pitcher-sustainability`: rh3 is the headline ROS
projection; the sustainability bucket and divergence signal layer on
top of it. The most valuable output is the **ACTIONABLE SIGNALS**
section that surfaces BUY-LOW (skills bullish, rh3 hasn't caught up)
and SELL-HIGH (skills bearish, rh3 still high) candidates.

For deep-dive on a single hitter or 2-3 narrative comparison, use
`/breakout-sustainability` instead — it has richer per-player analysis
with bat tracking + slump-or-decline framework.

---

## When to invoke

- Auditing your full hitter roster for hidden regression risk or
  buy-low candidates (Sunday roster review)
- Sizing up the FA hitter pool for actionable adds (BUY-LOW signals)
- Comparing 2-6 specific hitters head-to-head
- Validating a `/breakout-sustainability` verdict against rh3

## When NOT to invoke

- Deep-dive single-player narrative ("is X's breakout real?") →
  `/breakout-sustainability` is better
- Daily lineup decisions → use `/hitter-compare` for matchup-aware reads
- Pitcher sustainability → use `/pitcher-sustainability`

---

## Invocation

```bash
# Specific list (most common for trade evaluation)
python scripts/xfp/hitter_sustainability.py --players "Aaron Judge,Bo Bichette,Trea Turner"

# Whole roster audit (Sunday review)
python scripts/xfp/hitter_sustainability.py --scope my-roster

# FA pool sweep for buy-low candidates
python scripts/xfp/hitter_sustainability.py --scope fa-pool --min-2026-fp 2.0

# Universe for fa-pool sweeps: prefer LeagueState.available_fa_meaningful()
# over available_fa() — drops zero-PA callup / fringe noise (returns a
# (df, summary) tuple), ~6x speedup. Use available_fa() only when you need
# the full unfiltered ~963-name pool.

# Summary table only (no per-hitter detail)
python scripts/xfp/hitter_sustainability.py --scope my-roster --brief
```

---

## Understanding the output

Per-hitter block leads with:
- **rh3 per_game** (validated model, headline)
- **Bucket** (confidence layer)
- Per-year FP/game (current + baseline + delta)
- 9-marker table with ✓/✗ flags
- FP decomposition (skill vs luck attribution)
- Bull/base/bear ROS + E[FP/game]
- **Signal** (BUY_LOW / SELL_HIGH / CONFIRM / AGREE / INVESTIGATE)

Summary table at the end sorts by rh3 desc. The **ACTIONABLE SIGNALS**
block at the bottom is the call-to-action: surfaces only BUY-LOW and
SELL-HIGH hitters across the whole sweep.

---

## Hitter 9-marker checklist

| Marker | Favored direction | Material if Δ ≥ |
|---|---|---|
| Avg EV | + | 1.0 mph |
| EV90 (90th pct exit velocity) | + | 1.5 mph |
| HardHit% (95+ mph) | + | 3.0 pp |
| Barrel% | + | 1.5 pp |
| xwOBA-on-contact | + | 0.020 |
| K% | − | 2.0 pp |
| BB% | + | 1.5 pp |
| Chase% (o_swing) | − | 2.0 pp |
| SweetSpot% (8-32° launch angle) | + | 2.0 pp |

xwOBA-on-contact (`xwoba_on_contact`) is a marker used here as a
contact-quality diagnostic. Do NOT confuse with `xwoba_contact_to` —
the latter was REJECTED from RP3_FEATS on 2026-05-25 (algebraically
redundant given `xwoba_per_pa_to_sh + k_pct_to_sh + bb_pct_to_sh`
already in RP3_FEATS). The marker here is a human-readable signal,
not a model feature.

xwOBA-on-contact is NOT used in the FP decomposition
(redundant with Barrel%; would double-count).

FP decomposition uses **K%, BB%, Barrel%** with PA-per-game = 3.5
(matches rh3 pipeline's PA_PER_GAME_LEAGUE constant).

---

## Bucket → ROS probabilities

| Bucket | P(bull) | P(base) | P(bear) |
|---|---:|---:|---:|
| LEGIT | 40% | 45% | 15% |
| IMPROVING | 25% | 50% | 25% |
| MIXED | 20% | 40% | 40% |
| NOISE | 10% | 30% | 60% |
| STABLE | 20% | 60% | 20% |
| BAD_LUCK | 40% | 40% | 20% |
| REGRESS | 10% | 30% | 60% |

---

## Name-collision guard (mandatory before any rh3 lookup)

When building a `dict[name] → rh3 row` lookup, NEVER key on normalized
name alone. Two MLB players named "Max Muncy" exist (LAD batter_id 571970,
ATH batter_id 691777); a bare name dict silently assigns the wrong
projection. Canonical fix:

```python
import unicodedata
def _norm(s): return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode('ascii').lower().strip()

rh3 = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
rh3_idx = {}
dup_keys = set()
for _, row in rh3.iterrows():
    key = (_norm(row['player_name']), str(row.get('team', '')).upper())
    if key in rh3_idx:
        dup_keys.add(key)
    rh3_idx[key] = row
if dup_keys:
    print(f"WARNING: duplicate rh3 keys {dup_keys} — verify team-keyed resolution")

def rh3_row(name, team):
    return rh3_idx.get((_norm(name), str(team).upper()))
```

Use `pro_team` from the ESPN row as the second key. If unavailable, call
`resolve_batter_id(name, team=..., position=...)` from
`plv_clone.utils.name_match`.

---

## Anti-patterns this skill exists to prevent

- **Building `{_norm(name): row}` dicts from rh3 without team key.**
  Always key on `(norm_name, pro_team)` tuple to prevent same-name
  player collisions (canonical: Max Muncy LAD #39 vs ATH #331).
- **Trusting raw FP/game without skill check.** A hitter whose FP/g
  jumped 0.6 might be all BABIP (NOISE) or all skill (LEGIT) — same
  surface, opposite verdict.
- **Reading the bucket without the signal.** Bucket says how the
  STATCAST decomp interprets the year; signal says whether rh3 has
  caught up to it. Both matter.
- **Acting on small-sample 2026 calls.** If `n=2026 < 20 games`, the
  tool falls back to comparing the two most recent prior years. The
  output flags this with `⚠ 2026 sample too small`.
- **Comparing to `/breakout-sustainability` for sweep work.** That
  skill is single-player narrative-rich. Use THIS one for the wide
  scan, then drill into specific names with breakout-sustainability.


---

## Note (2026-06-03): complementary hitter boom_stack tag

For today-game right-tail context, layer in the live hitter `boom_stack=N/4`
from `/triangulate` (4 components: skill_spike_hitter / recform_hot_hitter /
opp_soft_hitter / lineup_amp_hitter). Sustainability is a RoS skill-decomp
layer; boom_stack is a per-game boom-rate tag. They answer different
questions and should be reported together for a hot hitter. See
`reference_hitter_boom_stack.md`.
