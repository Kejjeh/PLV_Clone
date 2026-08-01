"""dpwin_history — durable record of the Delta-P(win) surface, per run.

WHY THIS EXISTS
---------------
``data/outputs/matchup_leverage.json`` is OVERWRITTEN every run, so the moment a
new run lands, the previous surface is gone. That makes one question
unanswerable, and it is exactly the question the decision ledger needs to ask:

    "When I made that move, what did we think its Delta-P(win) was —
     and what were the alternatives we passed on?"

Without an at-the-time record there is no counterfactual to settle against. So
this store keeps **every evaluated candidate move**, not just the chosen one: the
rejected surface IS the counterfactual. A row is written whether or not Josh acts
on it.

It is deliberately append-only and idempotent on
``(run_id, move_type, add_mlbam, drop_mlbam, add_key, drop_key, start_date)``,
using the same temp-file + ``os.replace`` upsert idiom as
``persist_transactions.py`` so a crashed or concurrent run cannot corrupt the
file.

IDENTITY KEYS + MIGRATION (2026-08-01, C2)
------------------------------------------
``add_key`` / ``drop_key`` carry the same identity semantics as the engine's
``_draw_key``: ``id:<mlbam>`` when the id resolved, else ``nm:<normalized
name>``, else ``''`` for a genuinely-absent leg (e.g. the drop leg of a pure
add — the ONLY case in which sentinel sharing is correct). Before these columns
existed, every unresolved mlbam collapsed to sentinel 0 inside the dedup key,
so two DISTINCT unresolved-id adds sharing a drop occupied ONE key and
``drop_duplicates(keep='last')`` silently evicted one — three consecutive live
runs each lost 54+ evaluated candidates while ``append`` reported the loss as
zero. The parquet on disk predates the new columns, so ``append`` migrates
backward-compatibly: legacy frames get ``add_key``/``drop_key`` DERIVED from
their stored (name, mlbam) legs — a pure function of columns every legacy row
already carries — so a re-appended run_id still dedupes against its legacy rows
instead of duplicating them. Rows whose distinct players were already collapsed
before the fix are unrecoverable; the derivation only prevents NEW loss.

WHAT A ROW MEANS
----------------
Each row is one counterfactual scored against a single run's baseline. ``dpwin``
is only comparable to other rows sharing a ``run_id`` — across runs the baseline
state differs (score, days remaining, cap remaining), so cross-run dpwin
comparison is meaningless. ``run_id`` embeds the snapshot time precisely because
the surface is a function of when it was measured.

``mc_se`` is stored alongside every dpwin so a later reader can tell a real edge
from simulation noise instead of re-deriving it. ``engine_version`` is stored so a
future engine change (a sigma recalibration, a sampler swap) does not silently
mix incomparable numbers in one panel — the 2026-07-29 hitter-variance fix moved
P(win) by up to 3 percentage points, and any pre-fix row must be readable as
pre-fix.

CONSUMERS
---------
* ``run_matchup_leverage.py`` — logs its three advice families every run.
* ``run_weekly_optimizer.py`` — logs the full searched surface (C3).
* ``reconcile_decisions.py`` — joins executed transactions back to the surface
  that motivated them, and picks the best *unexecuted* same-bucket candidate as
  the rejected alternative (C5).
"""
from __future__ import annotations

import os
import tempfile
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from plv_clone.paths import ROOT

HISTORY_PARQUET = ROOT / 'data' / 'research' / 'dpwin_history.parquet'

# Bumped whenever a change makes dpwin numerically incomparable to earlier rows.
#   1 = first version (post hitter-variance fix, post location-scaling fix,
#       post mlbam-keyed draws — i.e. everything from 2026-07-29 onward)
ENGINE_VERSION = 1

# Idempotency key. start_date distinguishes two adds of the SAME pitcher on
# different days (a two-start week is one candidate per start). add_key /
# drop_key (2026-08-01) carry name-fallback identity so two DISTINCT
# unresolved-id players can never share a key; the mlbam columns stay in the
# key so legacy rows keep exactly their historical distinctions.
KEY_COLS = ['run_id', 'move_type', 'add_mlbam', 'drop_mlbam',
            'add_key', 'drop_key', 'start_date']

MOVE_TYPES = frozenset({
    'add', 'drop', 'swap', 'bench_start', 'sit_hitter', 'hold',
})

# Every column, in order. Written even when empty so the schema is stable and a
# downstream reader never has to guess.
COLUMNS = [
    # run context — identical across all rows of one run
    'run_id', 'generated_at', 'snapshot_date', 'engine_version',
    'period', 'regime', 'base_pwin', 'my_score', 'opp_score',
    'days_remaining', 'cap_remaining_mine', 'sims', 'seed',
    # the move
    'move_type',
    'add_name', 'add_mlbam', 'add_bucket', 'add_key',
    'drop_name', 'drop_mlbam', 'drop_bucket', 'drop_key',
    'start_date',
    # the measurement
    'dpwin', 'pwin_scenario', 'mc_se',
    # season bridge (C4; NaN until it lands)
    'dtitle_pp_per_win', 'dtitle_equity_pp',
    # provenance
    'rank_in_run', 'candidate_source',
]


def make_run_id(snapshot: datetime | None = None, seed: int = 0) -> str:
    """``{YYYY-MM-DD}T{HHMMSS}_{seed}``.

    The time component is not decoration: two runs on the same day against a
    changed roster produce genuinely different surfaces, and a reconciler
    matching an executed transaction needs to know WHICH one it came from.
    """
    ts = snapshot or datetime.now()
    return f"{ts.date().isoformat()}T{ts.strftime('%H%M%S')}_{int(seed)}"


def _norm_mlbam(v) -> int:
    """0 means 'not applicable' (e.g. the drop leg of a pure add).

    A sentinel rather than NaN because it participates in the dedup key, and
    pandas ``drop_duplicates`` treats NaN != NaN — which would silently defeat
    idempotency and let a re-run double every add row.
    """
    try:
        if v is None or (isinstance(v, float) and v != v):
            return 0
        return int(v)
    except (TypeError, ValueError):
        return 0


# The name-fallback key normalizes through the ONE canonical join_key — the
# same function behind leverage_engine._draw_key's nm: fallback — so a
# dpwin add_key and an engine draw key for the same unresolved player are
# EQUAL across modules, and the no-new-normalizers guard stays satisfied
# (a first draft hand-rolled a local copy here; the guard caught it).
from plv_clone.utils.name_match import join_key as _canonical_name_key  # noqa: E402


def _missing_safe_name_key(name) -> str:
    """NaN/None-tolerant wrapper over the canonical ``join_key`` — the wrapper
    only owns the missing-value contract ('' sentinel); the normalization
    itself is never local (the no-new-normalizers guard forbids a ``_norm*``
    def here by name, and rightly: a first draft hand-rolled one)."""
    if name is None or (isinstance(name, float) and name != name):
        return ''
    return _canonical_name_key(str(name))


def _leg_key(name, mlbam) -> str:
    """Identity key for one move leg — ``_draw_key`` semantics (C2, 2026-08-01).

    ``id:<mlbam>`` when the id resolved, else ``nm:<normalized name>``, else
    ``''``: the empty sentinel is reserved for a leg that is GENUINELY absent
    (the drop leg of a pure add, the add leg of a pure drop/bench), which is
    the only case in which two rows sharing it is correct.
    """
    m = _norm_mlbam(mlbam)
    if m:
        return f'id:{m}'
    nm = _missing_safe_name_key(name)
    if nm:
        return f'nm:{nm}'
    return ''


def _ensure_key_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible migration for frames lacking add_key/drop_key.

    Panels written before 2026-08-01 carry only the mlbam sentinel columns.
    Derive the identity keys from the stored (name, mlbam) legs — a pure
    function of columns every legacy row already carries — so a re-appended
    run_id dedupes against its legacy rows instead of duplicating them.
    Present-but-blank keys on rows with a real leg are re-derived the same way.
    """
    df = df.copy()
    n = len(df)
    for leg in ('add', 'drop'):
        kc = f'{leg}_key'
        names = (df[f'{leg}_name'].tolist()
                 if f'{leg}_name' in df.columns else [None] * n)
        ids = (df[f'{leg}_mlbam'].tolist()
               if f'{leg}_mlbam' in df.columns else [None] * n)
        derived = [_leg_key(nm, m) for nm, m in zip(names, ids)]
        if kc in df.columns:
            df[kc] = [c if isinstance(c, str) and c else d
                      for c, d in zip(df[kc].tolist(), derived)]
        else:
            df[kc] = derived
    return df


def build_rows(
    *,
    run_id: str,
    state: dict,
    regime: str,
    base_pwin: float,
    sims: int,
    seed: int,
    moves: Iterable[dict],
    generated_at: datetime | None = None,
) -> pd.DataFrame:
    """Shape a run's evaluated moves into history rows.

    ``moves`` items: ``{move_type, dpwin, pwin (or pwin_scenario), mc_se,
    add:{name,mlbam,bucket}?, drop:{name,mlbam,bucket}?, start_date?,
    candidate_source?, dtitle_pp_per_win?, dtitle_equity_pp?}``.

    Rank is assigned here, by descending dpwin within the run, so every writer
    gets the same ordering semantics rather than each inventing one.
    """
    ts = generated_at or datetime.now()
    mu = state.get('mu') or {}
    ctx = {
        'run_id': run_id,
        'generated_at': ts.isoformat(timespec='seconds'),
        'snapshot_date': ts.date().isoformat(),
        'engine_version': ENGINE_VERSION,
        'period': state.get('period'),
        'regime': regime,
        'base_pwin': round(float(base_pwin), 6),
        'my_score': mu.get('my_score'),
        'opp_score': mu.get('opp_score'),
        'days_remaining': state.get('days_remaining'),
        'cap_remaining_mine': state.get('cap_remaining_mine'),
        'sims': int(sims),
        'seed': int(seed),
    }

    recs = []
    for m in moves:
        mt = m.get('move_type')
        if mt not in MOVE_TYPES:
            raise ValueError(
                f'unknown move_type {mt!r}; expected one of {sorted(MOVE_TYPES)}')
        add = m.get('add') or {}
        drop = m.get('drop') or {}
        recs.append({
            **ctx,
            'move_type': mt,
            'add_name': add.get('name'),
            'add_mlbam': _norm_mlbam(add.get('mlbam')),
            'add_bucket': add.get('bucket'),
            'add_key': _leg_key(add.get('name'), add.get('mlbam')),
            'drop_name': drop.get('name'),
            'drop_mlbam': _norm_mlbam(drop.get('mlbam')),
            'drop_bucket': drop.get('bucket'),
            'drop_key': _leg_key(drop.get('name'), drop.get('mlbam')),
            'start_date': m.get('start_date') or '',
            'dpwin': (None if m.get('dpwin') is None
                      else round(float(m['dpwin']), 6)),
            'pwin_scenario': (None if m.get('pwin', m.get('pwin_scenario')) is None
                              else round(float(m.get('pwin', m.get('pwin_scenario'))), 6)),
            'mc_se': (None if m.get('mc_se') is None
                      else round(float(m['mc_se']), 6)),
            'dtitle_pp_per_win': m.get('dtitle_pp_per_win'),
            'dtitle_equity_pp': m.get('dtitle_equity_pp'),
            'rank_in_run': None,
            'candidate_source': m.get('candidate_source'),
        })

    df = pd.DataFrame(recs, columns=COLUMNS)
    if not df.empty:
        order = df['dpwin'].rank(ascending=False, method='first')
        df['rank_in_run'] = order.astype('Int64')
    return df


def _norm_key_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize the idempotency-key columns so equality is well-defined."""
    df = df.copy()
    for c in KEY_COLS:
        if c.endswith('_mlbam'):
            df[c] = df[c].map(_norm_mlbam)
        else:
            df[c] = df[c].fillna('').astype(str)
    return df


def append(rows: pd.DataFrame, path: Path | None = None) -> dict:
    """Idempotent upsert. Returns ``{added, replaced, evicted, total}``.

    Re-running the same run_id replaces its rows rather than duplicating them,
    so a retried or resumed run cannot inflate the panel.

    HONEST ACCOUNTING (2026-08-01): ``replaced`` counts old rows intentionally
    overwritten by an incoming row with the same key; ``evicted`` counts
    DISTINCT evaluated rows that collapsed onto one key within this append —
    which should be zero, and when it is not, a loud line is printed, because
    the evicted rows are the counterfactual surface the ledger settles against.
    The old ``added = max(total - before, 0)`` arithmetic reported a 54-row
    identity-collapse loss as zero.
    """
    p = Path(path) if path is not None else HISTORY_PARQUET
    if rows is None or rows.empty:
        return {'added': 0, 'replaced': 0, 'evicted': 0,
                'total': (len(pd.read_parquet(p)) if p.exists() else 0)}

    # Identity-key migration first: a legacy-shaped frame (no add_key/drop_key)
    # gets them derived from its stored legs rather than being rejected.
    rows = _ensure_key_cols(rows)
    missing = [c for c in KEY_COLS if c not in rows.columns]
    if missing:
        raise ValueError(f'rows missing key columns {missing}')

    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        try:
            old = pd.read_parquet(p)
        except Exception as e:
            # Loud, not silent: a corrupt panel is a real problem, and quietly
            # starting fresh would destroy the counterfactual record the ledger
            # depends on.
            raise RuntimeError(
                f'{p} exists but could not be read ({e}). Refusing to overwrite '
                f'the dpwin history — move the file aside deliberately if it is '
                f'genuinely corrupt.') from e
        old = _norm_key_cols(_ensure_key_cols(old))
        before = len(old)
    else:
        old = None
        before = 0

    inc = _norm_key_cols(rows)
    inc_dedup = inc.drop_duplicates(subset=KEY_COLS, keep='last')
    evicted = len(inc) - len(inc_dedup)
    if evicted:
        print(f'  !! dpwin history: {evicted} evaluated row(s) EVICTED — '
              f'distinct rows collapsed onto one idempotency key within a '
              f'single append. Distinct candidates must never share a key '
              f'(the C2 identity-collapse signature); check the writer.')

    inc_keys = set(map(tuple, inc_dedup[KEY_COLS].values))
    old_keys = set(map(tuple, old[KEY_COLS].values)) if before else set()
    replaced = len(old_keys & inc_keys)
    added = len(inc_keys - old_keys)

    combined = (pd.concat([old, inc_dedup], ignore_index=True)
                if before else inc_dedup)
    combined = (combined.drop_duplicates(subset=KEY_COLS, keep='last')
                        .reset_index(drop=True))
    # keep declared column order; tolerate extra columns from a newer writer
    cols = [c for c in COLUMNS if c in combined.columns]
    combined = combined[cols + [c for c in combined.columns if c not in cols]]

    fd, tmp = tempfile.mkstemp(suffix='.parquet', dir=str(p.parent))
    os.close(fd)
    try:
        combined.to_parquet(tmp, index=False)
        os.replace(tmp, p)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

    return {'added': added, 'replaced': replaced, 'evicted': evicted,
            'total': len(combined)}


def log_run(*, state: dict, regime: str, base_pwin: float, sims: int, seed: int,
            moves: Iterable[dict], run_id: str | None = None,
            path: Path | None = None, verbose: bool = True) -> str:
    """Build + append in one call. Returns the run_id actually used.

    Fail-soft by DESIGN at the call site, not here: a logging failure must never
    take down a live advice run, so callers wrap this in try/except and print a
    warning. Here we raise, so the caller can decide.
    """
    rid = run_id or make_run_id(seed=seed)
    rows = build_rows(run_id=rid, state=state, regime=regime,
                      base_pwin=base_pwin, sims=sims, seed=seed, moves=moves)
    res = append(rows, path=path)
    if verbose:
        p = Path(path) if path is not None else HISTORY_PARQUET
        ev = f' / {res["evicted"]} EVICTED' if res.get('evicted') else ''
        print(f'  dpwin history: {res["added"]} new / {res["replaced"]} replaced'
              f'{ev} -> {res["total"]} rows  ({p.name}, run {rid})')
    return rid


def load(path: Path | None = None) -> pd.DataFrame:
    """Read the panel (empty, correctly-typed frame when absent)."""
    p = Path(path) if path is not None else HISTORY_PARQUET
    if not p.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_parquet(p)


def latest_run_for(snapshot_date: str, path: Path | None = None) -> Optional[str]:
    """Most recent run_id at or before ``snapshot_date`` — the reconciler's hook
    for "which surface motivated this transaction?" (C5)."""
    df = load(path)
    if df.empty:
        return None
    sub = df[df['snapshot_date'].astype(str) <= str(snapshot_date)]
    if sub.empty:
        return None
    return str(sub.sort_values(['snapshot_date', 'generated_at']).iloc[-1]['run_id'])


__all__ = [
    'HISTORY_PARQUET', 'ENGINE_VERSION', 'KEY_COLS', 'COLUMNS', 'MOVE_TYPES',
    'make_run_id', 'build_rows', 'append', 'log_run', 'load', 'latest_run_for',
]
