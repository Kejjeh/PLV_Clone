---
name: player-id-resolve
description: Resolve ambiguous player names to the correct MLBAM batter/pitcher ID before any projection lookup. Required whenever building a dict[name→id] or dict[name→projection] mapping in Python, especially for players with known same-name collisions. The canonical case: Max Muncy LAD (3B) vs Max Muncy ATH (C) — naive _norm() key collision caused a false drop recommendation. Invoke this check before /fa-replacement-pool, /roster-audit, /league-deep-audit, /hitter-compare, or any analysis that joins player names to projection CSVs.
---

## The problem

Name-based dict lookups fail silently for same-name players. The `_norm()` function (from `hitter_sustainability.py`) normalizes names to a lowercase, stripped key — e.g., `"Max Muncy"` and `"max muncy"` both become `"muncymax"`. When two MLB players share a name, both rows map to the same key in a dict comprehension. The last-written row wins, and no error is raised. The lookup "succeeds" with the wrong player's projection, stat line, or drop signal.

The canonical case (2026-05-25): a roster vs FA evaluation recommended dropping Max Muncy (LAD, 3B) because `rh3_lu.get(_norm("Max Muncy"))` silently returned the ATH Muncy (C, batter_id=691777, proj=0.379, signal=`drop`) instead of the LAD Muncy (3B, batter_id=571970, proj=0.578, signal=`hold`). The wrong projection was not `None`, so no guard clause caught it.

## Known collisions (maintain this list)

| Name | Team1 | Pos1 | Batter ID1 | Team2 | Pos2 | Batter ID2 | Notes |
|------|-------|------|------------|-------|------|------------|-------|
| Max Muncy | LAD | 3B | 571970 | ATH | C | 691777 | Collision caused false drop signal on 2026-05-25 |
| Logan Henderson | NYM | SP | (lookup) | BAL | SS | (lookup) | Last-name substring fallback in roster_tag misattributed 2026-05-25; fix is two-pass match in `/roster-verify` |

Note: this list grows. When a new collision is discovered, add it here AND to `plv_clone/utils/name_match.py` `KNOWN_COLLISIONS` dict.

## The fix — three options (in order of preference)

**Option 1 — Use resolve_batter_id() (best)**

```python
from plv_clone.utils.name_match import resolve_batter_id
bid = resolve_batter_id(name, team='LAD', position='3B')
```

This consults the `KNOWN_COLLISIONS` dict and raises `ValueError` rather than guessing silently.

**Option 2 — Key on (name, team) tuple**

```python
rh3_lu = {}
for _, r in rh3.iterrows():
    key_full = (_norm(r['player_name']), r.get('pro_team', ''))
    key_name = _norm(r['player_name'])
    rh3_lu[key_full] = r  # preferred key
    rh3_lu[key_name] = r  # fallback (last-write wins — acceptable for non-collision names)

# Lookup: try (name, team) first, fall back to name-only
def get_rh3(name, team=''):
    return rh3_lu.get((_norm(name), team)) or rh3_lu.get(_norm(name))
```

**Option 3 — Collision detection at build time**

```python
seen = {}
for _, r in rh3.iterrows():
    nk = _norm(r['player_name'])
    if nk in seen:
        print(f"WARNING: collision on key '{nk}': {seen[nk]['player_name']} vs {r['player_name']}")
    seen[nk] = r
```

Run this during any audit script startup. Log all collisions so they can be added to `KNOWN_COLLISIONS`.

## When to apply this skill

- Any time you write `dict[_norm(name)] = row` over a CSV with multiple players
- Any time you do `rh3_lu.get(_norm(player_name))` for a roster player
- Any time you compare a roster vs a projection file by name join
- When a projection value looks wrong for a well-known player (e.g., Aaron Judge showing 0.39 rh3 — check for collision before assuming the model is wrong)

## Anti-patterns

- Building `{_norm(name): row for ...}` over rh3/rp3/rprs2 without collision detection — last row silently wins
- Checking only if the proj is `None` — a wrong proj (0.379 for Muncy LAD) will not be `None`, so the lookup "succeeds" with wrong data
- Assuming low ownership % implies a player is a FA — always verify with `get_all_teams()` (separate issue but related: Julio Rodriguez appeared at 0% owned in ESPN FA pool on 2026-05-25 but was actually rostered on Frendy's Fantastic Team)

## Relationship to other skills

- `/fa-replacement-pool` Step 3 — apply Option 2 when building the hitter lookup dict
- `/roster-audit` Step 5 — apply Option 2 or 3 when joining projections to roster
- `/league-deep-audit` — uses `_norm()` extensively; apply Option 3 at startup for any audit run
- `/hitter-compare` — single-player lookups; apply Option 1 (`resolve_batter_id`) when user names a player
