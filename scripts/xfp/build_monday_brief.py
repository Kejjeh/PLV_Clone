"""build_monday_brief — headless composer for data/outputs/monday_brief.md.

WHAT THIS IS
------------
A pure COMPOSER. It reads artifacts an earlier refresh already wrote and emits
one markdown brief. It does no modelling, no ESPN calls, no MLB Stats calls, and
no Pitcher List scraping. Everything it says is traceable to a file on disk.

WHY IT IS A SEPARATE SCRIPT FROM THE REFRESH
--------------------------------------------
The daily refresh (11:00 UTC, self-hosted runner) takes ~85-140 minutes and
writes the artifacts. The brief is the READ of those artifacts, and it has to be
correct even when it runs hours after the writer — a missed run on this runner
queues and fires whenever the PC next comes online. So:

  * IDEMPOTENT — running it twice on the same inputs writes the same bytes.
  * LATE-TOLERANT — nothing branches on "is it Monday morning". Ages are whole
    CALENDAR DAYS, so a run at 07:00 and a rerun at 19:00 the same day produce
    an identical body; the only wall-clock text in the file is the single
    `Brief built:` line, so reruns diff cleanly.
  * AGE-STAMPED — every artifact carries its age on the line that uses it. A
    brief built on a 3-day-old scorecard that does not SAY so is worse than no
    brief at all, because it launders staleness as freshness.
  * INDEPENDENTLY DEGRADING — a missing artifact yields an explicit
    "not available (run X)" line. Never an empty section, never a zero standing
    in for a number nobody computed (see docs/rh3_harness_root_bug_2026-07-28.md
    for what silent defaults cost us).
  * DECISION-FIRST — the top block is only things that need Josh to DO
    something: a FAILing data-health/sentinel tripwire, an SP-cap breach, a
    positive-dpwin move on the table. Statistics come after.

A section whose artifact is PRESENT but missing a field it needs renders a loud
`MALFORMED` line naming the field. That is a real defect (something wrote a
truncated artifact), so it is also reported on stderr and changes the exit code.

EXIT CODES
----------
  0  brief written, every present artifact parsed cleanly
  1  brief could NOT be written (hard failure)
  2  brief written, but >=1 artifact was present-and-malformed (loud, non-fatal:
     the brief still lands so the reader sees the rest)

USAGE
-----
  python scripts/xfp/build_monday_brief.py
  python scripts/xfp/build_monday_brief.py --out /tmp/brief.md --now 2026-07-30
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from plv_clone.paths import ROOT, OUTPUTS, RESEARCH

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

BRIEF_NAME = 'monday_brief.md'

# ── how to regenerate each artifact, quoted verbatim in the degraded lines ────
# The refresh step numbers are the ones printed by refresh_dashboards.py, so a
# reader can find the failing step in that run's log.
REGEN = {
    'model_scorecard.csv':  'python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)',
    'model_scorecard.md':   'python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)',
    'verdict_scorecard.csv': 'python scripts/xfp/run_verdict_scorecard.py  (refresh step 4.97b, Mondays only)',
    'dpwin_history.parquet': 'python scripts/xfp/run_matchup_leverage.py  (or run_weekly_optimizer.py — either appends)',
    'weekly_optimizer.json': 'python scripts/xfp/run_weekly_optimizer.py',
    'matchup_leverage.json': 'python scripts/xfp/run_matchup_leverage.py',
    'season_sim.json':       'python scripts/xfp/run_season_sim.py',
}

# Age (whole calendar days) past which an artifact is called STALE in the brief.
# Weekly artifacts get 8 days (one cadence + a day of slack); the per-period
# decision artifacts get 1, because a plan built against yesterday's roster can
# recommend dropping someone who is already gone.
STALE_AFTER_DAYS = {
    'model_scorecard.csv': 8,
    'model_scorecard.md': 8,
    'verdict_scorecard.csv': 8,
    'dpwin_history.parquet': 1,
    'weekly_optimizer.json': 1,
    'matchup_leverage.json': 1,
    'season_sim.json': 8,
}

PL_CACHE_FILES = (
    'pl_sps_top100.json',
    'pl_closers.json',
    'pl_hitters_top150.json',
    'pl_sp_streamers_latest.json',
)

WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday',
            'Friday', 'Saturday', 'Sunday')


class MalformedArtifact(Exception):
    """A present artifact is missing a field this brief needs.

    Raised instead of substituting a default. Callers catch it at the SECTION
    boundary so one truncated file cannot blank the whole brief, but the section
    says exactly which field is gone and the process exits non-zero.
    """


# ─────────────────────────────────────────────────────────────────────────────
# Artifact loading + age stamping
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Artifact:
    """One input file: whether it exists, how old it is, and how we know."""
    name: str
    path: Path
    exists: bool = False
    payload: Any = None
    read_error: str | None = None
    content_date: date | None = None   # the artifact's OWN as-of date, if it has one
    mtime_date: date | None = None     # filesystem fallback
    age_days: int | None = None
    age_basis: str = 'unavailable'

    @property
    def stale(self) -> bool:
        limit = STALE_AFTER_DAYS.get(self.name)
        return (limit is not None and self.age_days is not None
                and self.age_days > limit)

    @property
    def usable(self) -> bool:
        return self.exists and self.read_error is None and self.payload is not None

    def age_phrase(self) -> str:
        """Human age stamp. Every line that quotes this artifact carries it."""
        if not self.exists:
            return 'MISSING'
        if self.read_error:
            return f'UNREADABLE ({self.read_error})'
        if self.age_days is None:
            return 'age unknown'
        asof = self.content_date or self.mtime_date
        day = 'today' if self.age_days == 0 else (
            '1 day old' if self.age_days == 1 else f'{self.age_days} days old')
        tag = ' [STALE]' if self.stale else ''
        return f'as-of {asof}, {day} ({self.age_basis}){tag}'

    def missing_line(self) -> str:
        how = REGEN.get(self.name, f'regenerate {self.name}')
        if not self.exists:
            return f'- **not available** — `{self.path.name}` is MISSING. Run: `{how}`'
        return (f'- **not available** — `{self.path.name}` is UNREADABLE '
                f'({self.read_error}). Run: `{how}`')


def _parse_iso_date(raw: Any) -> date | None:
    """Parse a leading YYYY-MM-DD out of a string. None if it is not one."""
    if not isinstance(raw, str) or len(raw) < 10:
        return None
    try:
        return datetime.strptime(raw[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _load(name: str, path: Path, reader: Callable[[Path], Any],
          content_date_of: Callable[[Any], date | None] | None,
          today: date) -> Artifact:
    """Read one artifact, never raising: failures land on the Artifact itself."""
    art = Artifact(name=name, path=path)
    if not path.exists():
        return art
    art.exists = True
    try:
        art.mtime_date = datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError as exc:  # pragma: no cover - stat on an existing file
        art.read_error = f'stat failed: {exc}'
        return art
    try:
        art.payload = reader(path)
    except Exception as exc:
        art.read_error = f'{type(exc).__name__}: {exc}'
        return art
    if content_date_of is not None:
        try:
            art.content_date = content_date_of(art.payload)
        except Exception:
            art.content_date = None
    basis_date = art.content_date or art.mtime_date
    art.age_basis = 'content date' if art.content_date else 'file mtime'
    if basis_date is not None:
        art.age_days = (today - basis_date).days
    return art


def _read_json(path: Path) -> Any:
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


@dataclass
class BriefPaths:
    """Explicit paths so tests can point the composer at a temp directory."""
    model_scorecard_csv: Path
    model_scorecard_md: Path
    verdict_scorecard_csv: Path
    dpwin_history: Path
    weekly_optimizer: Path
    matchup_leverage: Path
    season_sim: Path
    pl_cache_dir: Path
    out: Path


def default_paths(outputs: Path | None = None,
                  research: Path | None = None,
                  out: Path | None = None) -> BriefPaths:
    outputs = Path(outputs) if outputs is not None else OUTPUTS
    research = Path(research) if research is not None else RESEARCH
    return BriefPaths(
        model_scorecard_csv=outputs / 'model_scorecard.csv',
        model_scorecard_md=outputs / 'model_scorecard.md',
        verdict_scorecard_csv=outputs / 'verdict_scorecard.csv',
        dpwin_history=research / 'dpwin_history.parquet',
        weekly_optimizer=outputs / 'weekly_optimizer.json',
        matchup_leverage=outputs / 'matchup_leverage.json',
        season_sim=outputs / 'season_sim.json',
        pl_cache_dir=research / 'pl_cache',
        out=Path(out) if out is not None else outputs / BRIEF_NAME,
    )


def load_artifacts(paths: BriefPaths, today: date) -> dict[str, Artifact]:
    def scorecard_date(df: pd.DataFrame) -> date | None:
        if 'date' not in df.columns or df.empty:
            return None
        return _parse_iso_date(str(df['date'].max()))

    def dpwin_date(df: pd.DataFrame) -> date | None:
        if 'snapshot_date' not in df.columns or df.empty:
            return None
        return _parse_iso_date(str(df['snapshot_date'].max()))

    def json_generated(payload: Any) -> date | None:
        if isinstance(payload, dict):
            return _parse_iso_date(payload.get('generated'))
        return None

    def optimizer_date(payload: Any) -> date | None:
        """weekly_optimizer.json has no `generated`; its run id is timestamped."""
        if isinstance(payload, dict):
            return _parse_iso_date(payload.get('dpwin_run_id'))
        return None

    return {
        'model_scorecard.csv': _load('model_scorecard.csv', paths.model_scorecard_csv,
                                     _read_csv, scorecard_date, today),
        'model_scorecard.md': _load('model_scorecard.md', paths.model_scorecard_md,
                                    _read_text, None, today),
        'verdict_scorecard.csv': _load('verdict_scorecard.csv', paths.verdict_scorecard_csv,
                                       _read_csv, None, today),
        'dpwin_history.parquet': _load('dpwin_history.parquet', paths.dpwin_history,
                                       _read_parquet, dpwin_date, today),
        'weekly_optimizer.json': _load('weekly_optimizer.json', paths.weekly_optimizer,
                                       _read_json, optimizer_date, today),
        'matchup_leverage.json': _load('matchup_leverage.json', paths.matchup_leverage,
                                       _read_json, json_generated, today),
        'season_sim.json': _load('season_sim.json', paths.season_sim,
                                 _read_json, json_generated, today),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Field access that refuses to guess
# ─────────────────────────────────────────────────────────────────────────────
def _req(payload: dict, key: str, artifact: str) -> Any:
    """Fetch a REQUIRED key. Raises rather than defaulting.

    The whole point: a missing `cap_remaining` must never read as 0 remaining
    starts, and a missing `pwin` must never read as a coin flip.
    """
    if not isinstance(payload, dict):
        raise MalformedArtifact(f'{artifact}: expected a JSON object, got {type(payload).__name__}')
    if key not in payload or payload[key] is None:
        raise MalformedArtifact(f'{artifact}: required field `{key}` is absent')
    return payload[key]


def _req_cols(df: pd.DataFrame, cols: tuple[str, ...], artifact: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise MalformedArtifact(
            f'{artifact}: required column(s) {", ".join(missing)} absent '
            f'(present: {", ".join(map(str, df.columns))})')


def _settled_total(df) -> str:
    """Total settled observations, or an explicit marker when a cell is unusable.

    Returns a STRING because "--" is a legitimate answer: silently summing a
    non-numeric cell as 0 would understate the sample while still looking valid.
    """
    n = pd.to_numeric(df['n'], errors='coerce')
    if n.isna().any():
        bad = int(n.isna().sum())
        return f'-- ({bad} of {len(n)} `n` cells non-numeric)'
    return str(int(n.sum()))


def _num(value: Any, key: str, artifact: str) -> float:
    """Strict numeric coercion — non-finite is MALFORMED, not a number.

    The NaN case is the one that matters and it was the gap here. `json.dumps`
    defaults to ``allow_nan=True``, so both upstream writers can legitimately emit
    the bare literal ``NaN``, and ``float('nan')`` sails through a try/except.
    A NaN ``cap_remaining`` then compares False against every threshold, so a real
    SP-cap BREACH renders as "Nothing FLAGGED" and the brief exits 0 — the exact
    silent-pass class this whole program spent the day removing. Non-finite now
    raises like any other malformed field.
    """
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise MalformedArtifact(f'{artifact}: field `{key}` is not numeric ({value!r})')
    if not math.isfinite(out):
        raise MalformedArtifact(
            f'{artifact}: field `{key}` is non-finite ({value!r}) — refusing to '
            f'treat it as a number. A NaN here would compare False against every '
            f'threshold and hide a real breach behind "Nothing FLAGGED".')
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Decision extraction — the top block
# ─────────────────────────────────────────────────────────────────────────────
# The three drift sentinels added 2026-07-29. Named explicitly so a FAIL on any
# of them is labelled as a SENTINEL failure rather than a generic tripwire: they
# guard the name-collision + FA-join machinery every board depends on.
DRIFT_SENTINELS = ('collision_team_reachability', 'collision_smoke', 'fa_join_coverage')
# The date those three checks landed in build_model_scorecard.py. A scorecard
# written BEFORE this has no sentinel rows for an innocent reason, and the brief
# says which reason it is — "absent because it predates the check" and "absent
# because the check silently stopped running" are different problems.
DRIFT_SENTINELS_ADDED = date(2026, 7, 29)

TRIPWIRE_SECTIONS = ('data_health', 'pipeline_staleness')


@dataclass
class Decisions:
    """What needs doing, and what we could not check because a file was absent."""
    urgent: list[str] = field(default_factory=list)
    advisory: list[str] = field(default_factory=list)
    unchecked: list[str] = field(default_factory=list)
    malformed: list[str] = field(default_factory=list)


def _scorecard_tripwires(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """(FAILs, WARNs) among data_health + pipeline_staleness rows."""
    _req_cols(df, ('section', 'metric', 'segment', 'status', 'note'), 'model_scorecard.csv')
    trip = df[df['section'].isin(TRIPWIRE_SECTIONS)]
    fails = trip[trip['status'] == 'FAIL'].to_dict('records')
    warns = trip[trip['status'] == 'WARN'].to_dict('records')
    return fails, warns


def collect_decisions(arts: dict[str, Artifact], paths: BriefPaths,
                      today: date) -> Decisions:
    dec = Decisions()

    # 1. Tripwires / drift sentinels ------------------------------------------
    sc = arts['model_scorecard.csv']
    if not sc.usable:
        dec.unchecked.append(
            f'data-health + drift-sentinel tripwires — `model_scorecard.csv` '
            f'{sc.age_phrase()}. Run: `{REGEN["model_scorecard.csv"]}`')
    else:
        try:
            fails, warns = _scorecard_tripwires(sc.payload)
            # Sentinel FAILs first: they invalidate the name-collision / FA-join
            # machinery every board reads, so they outrank an ordinary tripwire.
            fails.sort(key=lambda r: 0 if r['metric'] in DRIFT_SENTINELS else 1)
            for row in fails:
                kind = 'SENTINEL FAIL' if row['metric'] in DRIFT_SENTINELS else 'TRIPWIRE FAIL'
                dec.urgent.append(
                    f'**{kind}** `{row["metric"]}` ({row["segment"]}) — {row["note"]} '
                    f'[from model_scorecard.csv, {sc.age_phrase()}]')
            for row in warns:
                dec.advisory.append(
                    f'TRIPWIRE WARN `{row["metric"]}` ({row["segment"]}) — {row["note"]} '
                    f'[model_scorecard.csv, {sc.age_phrase()}]')
            if sc.stale:
                dec.advisory.append(
                    f'`model_scorecard.csv` is {sc.age_days}d old — these tripwires '
                    f'describe {sc.content_date or sc.mtime_date}, not today. '
                    f'Run: `{REGEN["model_scorecard.csv"]}`')
        except MalformedArtifact as exc:
            dec.malformed.append(str(exc))

    # 2. SP-start cap ---------------------------------------------------------
    ml = arts['matchup_leverage.json']
    if not ml.usable:
        dec.unchecked.append(
            f'SP-start cap position — `matchup_leverage.json` {ml.age_phrase()}. '
            f'Run: `{REGEN["matchup_leverage.json"]}`')
    else:
        try:
            cap = _num(_req(ml.payload, 'sp_cap', 'matchup_leverage.json'),
                       'sp_cap', 'matchup_leverage.json')
            banked = _num(_req(ml.payload, 'banked_sp_starts', 'matchup_leverage.json'),
                          'banked_sp_starts', 'matchup_leverage.json')
            remaining = _num(_req(ml.payload, 'cap_remaining', 'matchup_leverage.json'),
                             'cap_remaining', 'matchup_leverage.json')
            period = _req(ml.payload, 'period', 'matchup_leverage.json')
            stamp = f'[matchup_leverage.json, {ml.age_phrase()}]'
            if remaining < 0:
                dec.urgent.append(
                    f'**SP CAP BREACHED** period {period}: {banked:.0f} banked vs cap '
                    f'{cap:.0f} ({-remaining:.0f} over) — starts past the cap score ZERO. '
                    f'Run `/cap-check` then `/forced-drop-planner`. {stamp}')
            elif remaining == 0:
                dec.urgent.append(
                    f'**SP CAP EXHAUSTED** period {period}: {banked:.0f}/{cap:.0f} banked, '
                    f'0 remaining — every further start scores ZERO. Bench all remaining '
                    f'SP starts. {stamp}')
            elif remaining <= 2:
                dec.advisory.append(
                    f'SP cap TIGHT period {period}: {banked:.0f}/{cap:.0f} banked, '
                    f'{remaining:.0f} remaining — sequence the rest of the week before '
                    f'streaming. {stamp}')
            if ml.stale:
                dec.advisory.append(
                    f'`matchup_leverage.json` is {ml.age_days}d old, so the cap count '
                    f'above is {ml.age_days}d of starts behind. '
                    f'Run: `{REGEN["matchup_leverage.json"]}`')
        except MalformedArtifact as exc:
            dec.malformed.append(str(exc))

    # 3. Positive-dpwin moves on the table -----------------------------------
    wo = arts['weekly_optimizer.json']
    if not wo.usable:
        dec.unchecked.append(
            f'recommended add/drop plan — `weekly_optimizer.json` {wo.age_phrase()}. '
            f'Run: `{REGEN["weekly_optimizer.json"]}`')
    else:
        try:
            plan = _req(wo.payload, 'plan', 'weekly_optimizer.json')
            if not isinstance(plan, list):
                raise MalformedArtifact('weekly_optimizer.json: `plan` is not a list')
            stamp = f'[weekly_optimizer.json, {wo.age_phrase()}]'
            positives = []
            for mv in plan:
                dpwin = _num(_req(mv, 'dpwin', 'weekly_optimizer.json:plan[]'),
                             'dpwin', 'weekly_optimizer.json:plan[]')
                if dpwin > 0:
                    positives.append((mv, dpwin))
            if positives:
                # The optimizer's plan is SEQUENCED: step k is scored against the
                # roster AFTER step k-1, so step 2 routinely drops the very player
                # step 1 added. Presenting them as independent numbered decisions
                # invites acting on step 2 alone, which REVERSES step 1. So each
                # line is labelled with its position and the multi-step case says
                # so explicitly. (Found by adversarial review 2026-07-29.)
                n_steps = len(positives)
                for step, (mv, dpwin) in enumerate(positives, 1):
                    seq = (f'STEP {step} of {n_steps} (sequenced — do them IN ORDER; '
                           f'later steps are scored against the roster after the '
                           f'earlier ones and may drop a player an earlier step added)'
                           if n_steps > 1 else 'single move')
                    se = mv.get('mc_se')
                    sig = ''
                    if se is not None:
                        se_f = _num(se, 'mc_se', 'weekly_optimizer.json:plan[]')
                        sig = (' (> 2x MC se — a real gap)' if dpwin > 2 * se_f
                               else f' (WITHIN 2x MC se {se_f:.4f} — not distinguishable '
                                    f'from no move; break the tie on regime, not dpwin)')
                    dec.urgent.append(
                        f'**MOVE AVAILABLE — {seq}** ADD {mv.get("add", "?")} / DROP '
                        f'{mv.get("drop", "?")} for dP(win) +{dpwin:.4f}{sig}. '
                        f'Verify live rosters (`/roster-verify`) before executing. {stamp}')
            else:
                dec.advisory.append(
                    f'no positive-dpwin move in the optimizer plan — stand pat. {stamp}')
            if wo.stale:
                dec.advisory.append(
                    f'`weekly_optimizer.json` is {wo.age_days}d old — its plan was built '
                    f'against a {wo.age_days}d-old roster and FA pool; RE-RUN before '
                    f'executing anything above. Run: `{REGEN["weekly_optimizer.json"]}`')
        except MalformedArtifact as exc:
            dec.malformed.append(str(exc))

    # 4. Season sim behind the live period ------------------------------------
    # Every dpwin recommendation above is converted to TITLE equity using this
    # sim's value-of-win curve, so a sim computed two periods ago silently
    # mis-weights each move. Flag it here, not buried in section 5.
    ss = arts['season_sim.json']
    if not ss.usable:
        dec.unchecked.append(
            f'title-equity weighting of the moves above — `season_sim.json` '
            f'{ss.age_phrase()}. Run: `{REGEN["season_sim.json"]}`')
    elif isinstance(ss.payload, dict):
        sim_period = ss.payload.get('period')
        live_period = (ml.payload.get('period')
                       if ml.usable and isinstance(ml.payload, dict) else None)
        if isinstance(sim_period, int) and isinstance(live_period, int) and live_period > sim_period:
            dec.advisory.append(
                f'`season_sim.json` is {live_period - sim_period} period(s) behind '
                f'(sim {sim_period} vs live {live_period}) — the title-equity weight '
                f'applied to every move above comes from older standings. '
                f'Run: `{REGEN["season_sim.json"]}`')
        elif ss.stale:
            dec.advisory.append(
                f'`season_sim.json` is {ss.age_days}d old. '
                f'Run: `{REGEN["season_sim.json"]}`')

    # 5. PL caches that a board will read stale ------------------------------
    for line in _pl_stale_advisories(paths.pl_cache_dir, today):
        dec.advisory.append(line)

    return dec


@dataclass
class PLCacheRow:
    """One PL cache file's freshness, read-only. `problem` set => actionable."""
    fname: str
    fetched: date | None = None
    age_days: int | None = None
    stale: bool = False
    reason: str = ''
    problem: str | None = None   # MISSING / UNREADABLE / NO_DATE / CHECK_ERROR / STALE


def _pl_cache_rows(pl_dir: Path, today: date) -> tuple[list[PLCacheRow], str | None]:
    """Freshness of the four PL caches. Returns (rows, import_error).

    Read-only by design. Refreshing these needs a live agent WebSearch/WebFetch
    (refresh_dashboards.py step 7 documents why it is deliberately NOT a headless
    scrape), so this brief can only report and route.
    """
    try:
        from scripts.xfp.lib.pl_cache import _cache_is_stale  # noqa: PLC0415
    except Exception as exc:
        return [], f'{type(exc).__name__}: {exc}'
    rows: list[PLCacheRow] = []
    for fname in PL_CACHE_FILES:
        path = pl_dir / fname
        if not path.exists():
            rows.append(PLCacheRow(fname, problem='MISSING'))
            continue
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                fetched = _parse_iso_date(json.load(fh).get('fetched'))
        except Exception as exc:
            rows.append(PLCacheRow(fname, problem='UNREADABLE',
                                   reason=f'{type(exc).__name__}: {exc}'))
            continue
        if fetched is None:
            rows.append(PLCacheRow(fname, problem='NO_DATE',
                                   reason='no parseable `fetched` date'))
            continue
        age = (today - fetched).days
        try:
            stale, reason = _cache_is_stale(fname, fetched)
        except Exception as exc:
            rows.append(PLCacheRow(fname, fetched=fetched, age_days=age,
                                   problem='CHECK_ERROR',
                                   reason=f'{type(exc).__name__}: {exc}'))
            continue
        rows.append(PLCacheRow(fname, fetched=fetched, age_days=age, stale=stale,
                               reason=reason, problem='STALE' if stale else None))
    return rows, None


_PL_REFRESH_HINT = ('Refresh in an interactive session '
                    '(`/triangulate --check-caches`); this brief cannot fetch '
                    'pitcherlist.com.')


def _pl_stale_advisories(pl_dir: Path, today: date) -> list[str]:
    """Advisory lines for the PL caches that a board would read stale."""
    rows, import_err = _pl_cache_rows(pl_dir, today)
    if import_err:
        return [f'PL cache staleness UNKNOWN — could not import '
                f'`scripts.xfp.lib.pl_cache` ({import_err})']
    out: list[str] = []
    for r in rows:
        if r.problem is None:
            continue
        if r.problem == 'STALE':
            out.append(f'PL cache `{r.fname}` is STALE — {r.reason} '
                       f'({r.age_days}d old). {_PL_REFRESH_HINT}')
        elif r.problem == 'MISSING':
            out.append(f'PL cache `{r.fname}` is MISSING. {_PL_REFRESH_HINT}')
        else:
            out.append(f'PL cache `{r.fname}` — {r.problem}: {r.reason}. '
                       f'Age unknown; do not assume current.')
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Sections
# ─────────────────────────────────────────────────────────────────────────────
def _section(title: str, body: list[str]) -> list[str]:
    while body and body[-1] == '':
        body = body[:-1]
    return [f'## {title}', ''] + body + ['']


def _guard(art: Artifact, render: Callable[[], list[str]],
           malformed: list[str]) -> list[str]:
    """Render a section, degrading loudly instead of raising."""
    if not art.usable:
        return [art.missing_line()]
    try:
        return render()
    except MalformedArtifact as exc:
        malformed.append(str(exc))
        how = REGEN.get(art.name, f'regenerate {art.name}')
        return [f'- **MALFORMED** — {exc}. Run: `{how}`']


def _decisions_section(dec: Decisions) -> list[str]:
    out: list[str] = []
    if dec.urgent:
        out.append('### Needs a decision')
        out.append('')
        out += [f'{i}. {line}' for i, line in enumerate(dec.urgent, 1)]
        out.append('')
    else:
        out.append('### Needs a decision')
        out.append('')
        if dec.unchecked:
            out.append('- Nothing FLAGGED — but the checks below could not run, '
                       'so this is **not** an all-clear.')
        else:
            out.append('- Nothing flagged by any available artifact.')
        out.append('')
    if dec.advisory:
        out.append('### Worth knowing')
        out.append('')
        out += [f'- {line}' for line in dec.advisory]
        out.append('')
    if dec.unchecked:
        out.append('### COULD NOT CHECK (artifact absent)')
        out.append('')
        out += [f'- {line}' for line in dec.unchecked]
        out.append('')
    if dec.malformed:
        out.append('### MALFORMED ARTIFACTS (a writer produced a truncated file)')
        out.append('')
        out += [f'- {line}' for line in dec.malformed]
        out.append('')
    return out


def _matchup_section(arts: dict[str, Artifact], malformed: list[str]) -> list[str]:
    ml = arts['matchup_leverage.json']

    def render() -> list[str]:
        p = ml.payload
        pwin = _num(_req(p, 'pwin', 'matchup_leverage.json'), 'pwin', 'matchup_leverage.json')
        lines = [
            f'- `matchup_leverage.json` — {ml.age_phrase()}',
            f'- Period **{_req(p, "period", "matchup_leverage.json")}** vs '
            f'**{_req(p, "opp_team", "matchup_leverage.json")}** — '
            f'{_num(_req(p, "my_score", "matchup_leverage.json"), "my_score", "matchup_leverage.json"):.1f} '
            f'to {_num(_req(p, "opp_score", "matchup_leverage.json"), "opp_score", "matchup_leverage.json"):.1f}, '
            f'{_req(p, "days_remaining_incl_today", "matchup_leverage.json")}d left incl. today',
            f'- **P(win) {pwin:.3f}** — regime **{_req(p, "regime", "matchup_leverage.json")}**',
            f'- Regime directive: {p.get("regime_note", "(no regime_note in artifact)")}',
            f'- SP cap {_num(_req(p, "banked_sp_starts", "matchup_leverage.json"), "banked_sp_starts", "matchup_leverage.json"):.0f}'
            f'/{_num(_req(p, "sp_cap", "matchup_leverage.json"), "sp_cap", "matchup_leverage.json"):.0f} banked, '
            f'{_num(_req(p, "cap_remaining", "matchup_leverage.json"), "cap_remaining", "matchup_leverage.json"):.0f} remaining '
            f'(opp {_num(_req(p, "cap_remaining_opp", "matchup_leverage.json"), "cap_remaining_opp", "matchup_leverage.json"):.0f})',
        ]
        top = p.get('top_moves')
        if isinstance(top, list) and top:
            lines.append('- Top leverage moves from this run:')
            for mv in top[:5]:
                dpwin = _num(_req(mv, 'dpwin', 'matchup_leverage.json:top_moves[]'),
                             'dpwin', 'matchup_leverage.json:top_moves[]')
                lines.append(f'  - {mv.get("move", "?")} — dP(win) {dpwin:+.4f}'
                             f' ({mv.get("why", "no rationale in artifact")})')
        else:
            lines.append('- No `top_moves` in this run (field absent or empty).')
        return lines

    return _guard(ml, render, malformed)


def _optimizer_section(arts: dict[str, Artifact], malformed: list[str]) -> list[str]:
    wo = arts['weekly_optimizer.json']

    def render() -> list[str]:
        p = wo.payload
        lines = [
            f'- `weekly_optimizer.json` — {wo.age_phrase()}',
            f'- Base P(win) '
            f'{_num(_req(p, "base_pwin", "weekly_optimizer.json"), "base_pwin", "weekly_optimizer.json"):.3f}, '
            f'regime {_req(p, "regime", "weekly_optimizer.json")}, '
            f'period {_req(p, "period", "weekly_optimizer.json")}, '
            f'{_req(p, "sims", "weekly_optimizer.json")} sims '
            f'(seed {_req(p, "seed", "weekly_optimizer.json")}), '
            f'cap remaining {_req(p, "cap_remaining", "weekly_optimizer.json")}',
        ]
        plan = _req(p, 'plan', 'weekly_optimizer.json')
        if plan:
            lines.append('- Recommended sequenced plan:')
            for i, mv in enumerate(plan, 1):
                dpwin = _num(_req(mv, 'dpwin', 'weekly_optimizer.json:plan[]'),
                             'dpwin', 'weekly_optimizer.json:plan[]')
                se = mv.get('mc_se')
                se_txt = f', mc_se {_num(se, "mc_se", "weekly_optimizer.json:plan[]"):.4f}' if se is not None else ''
                eq = mv.get('dtitle_equity_pp')
                eq_txt = f', title equity {_num(eq, "dtitle_equity_pp", "weekly_optimizer.json:plan[]"):+.4f}pp' if eq is not None else ''
                lines.append(
                    f'  {i}. ADD {mv.get("add", "?")} ({mv.get("add_bucket", "?")}) / '
                    f'DROP {mv.get("drop", "?")} ({mv.get("drop_bucket", "?")}) — '
                    f'dP(win) {dpwin:+.4f}{se_txt}{eq_txt}')
        else:
            lines.append('- Plan is EMPTY — the optimizer found no move worth making.')
        te = p.get('title_equity')
        if isinstance(te, dict):
            note = te.get('note')
            status = te.get('status', 'status absent')
            lines.append(f'- Title-equity weight: {te.get("dtitle_pp", "absent")}pp per win '
                         f'(status **{status}**)')
            if note:
                lines.append(f'  - {note}')
        else:
            lines.append('- No `title_equity` block in this run.')
        return lines

    return _guard(wo, render, malformed)


def _dpwin_section(arts: dict[str, Artifact], malformed: list[str]) -> list[str]:
    dh = arts['dpwin_history.parquet']

    def render() -> list[str]:
        df = dh.payload
        _req_cols(df, ('run_id', 'snapshot_date', 'move_type', 'dpwin'),
                  'dpwin_history.parquet')
        if df.empty:
            return [f'- `dpwin_history.parquet` — {dh.age_phrase()} — store is EMPTY '
                    f'(0 rows). Run: `{REGEN["dpwin_history.parquet"]}`']
        latest_snap = str(df['snapshot_date'].max())
        latest = df[df['snapshot_date'].astype(str) == latest_snap]
        runs = sorted(latest['run_id'].astype(str).unique())
        lines = [
            f'- `dpwin_history.parquet` — {dh.age_phrase()}',
            f'- {len(df)} counterfactual rows over '
            f'{df["snapshot_date"].astype(str).nunique()} snapshot day(s) '
            f'({df["snapshot_date"].astype(str).min()} -> {latest_snap})',
            f'- Latest snapshot {latest_snap}: {len(latest)} rows from '
            f'{len(runs)} run(s) [{", ".join(runs)}]',
        ]
        # mergesort = stable, so ties resolve by the parquet's row order rather
        # than quicksort's implementation detail: same file -> same brief bytes.
        best = (latest.dropna(subset=['dpwin'])
                      .sort_values('dpwin', ascending=False, kind='mergesort')
                      .groupby('move_type', sort=True)
                      .head(1)
                      .sort_values('move_type', kind='mergesort'))
        if best.empty:
            lines.append('- No scored dpwin rows in the latest snapshot.')
        else:
            lines.append('- Best-scoring alternative per move_type in the latest snapshot:')
            for _, r in best.iterrows():
                who = r.get('add_name') if isinstance(r.get('add_name'), str) else r.get('drop_name')
                who = who if isinstance(who, str) else '(unnamed)'
                lines.append(f'  - `{r["move_type"]}` {who} — dP(win) {float(r["dpwin"]):+.4f}')
        return lines

    return _guard(dh, render, malformed)


def _season_sim_section(arts: dict[str, Artifact], malformed: list[str]) -> list[str]:
    ss = arts['season_sim.json']
    ml = arts['matchup_leverage.json']

    def render() -> list[str]:
        p = ss.payload
        josh = _req(p, 'josh', 'season_sim.json')
        lines = [
            f'- `season_sim.json` — {ss.age_phrase()}',
            f'- **{_req(josh, "team", "season_sim.json:josh")}** — '
            f'P(playoffs) {_num(_req(josh, "p_playoffs", "season_sim.json:josh"), "p_playoffs", "season_sim.json:josh"):.3f}, '
            f'P(title) {_num(_req(josh, "p_title", "season_sim.json:josh"), "p_title", "season_sim.json:josh"):.3f} '
            f'(sim period {_req(p, "period", "season_sim.json")}, '
            f'{_req(p, "sims", "season_sim.json")} sims)',
        ]
        # Cross-artifact staleness: the sim's period vs the live matchup period.
        # This is the check that catches "title odds computed two periods ago".
        if ml.usable and isinstance(ml.payload, dict):
            live_period = ml.payload.get('period')
            sim_period = p.get('period')
            if isinstance(live_period, int) and isinstance(sim_period, int):
                behind = live_period - sim_period
                if behind > 0:
                    lines.append(
                        f'- **{behind} period(s) BEHIND** the live matchup '
                        f'(sim period {sim_period} vs live {live_period}) — the odds and '
                        f'the value-of-win curve are computed off older standings. '
                        f'Run: `{REGEN["season_sim.json"]}`')
                else:
                    lines.append(f'- Sim period {sim_period} matches the live matchup period.')
        curve = josh.get('value_of_win_curve')
        if isinstance(curve, list) and curve:
            lines.append('- Value of winning each remaining period (dP(title), pp):')
            for row in curve:
                lines.append(
                    f'  - period {row.get("period", "?")}: '
                    f'dtitle {_num(_req(row, "dtitle_pp", "season_sim.json:value_of_win_curve[]"), "dtitle_pp", "season_sim.json:value_of_win_curve[]"):+.2f}pp, '
                    f'dplayoffs {_num(_req(row, "dplayoffs_pp", "season_sim.json:value_of_win_curve[]"), "dplayoffs_pp", "season_sim.json:value_of_win_curve[]"):+.2f}pp '
                    f'(P(win week) {row.get("p_win_week", "absent")})')
        else:
            lines.append('- No `value_of_win_curve` in this run.')
        directive = josh.get('strategy_directive')
        if isinstance(directive, list) and directive:
            lines.append('- Strategy directive from the sim:')
            lines += [f'  - {d}' for d in directive]
        return lines

    return _guard(ss, render, malformed)


def _verdict_section(arts: dict[str, Artifact], today: date,
                     malformed: list[str]) -> list[str]:
    vs = arts['verdict_scorecard.csv']
    if not vs.usable:
        # This one is legitimately Monday-only, so say WHY it may be absent
        # rather than implying something broke.
        return [
            vs.missing_line(),
            f'- Note: the verdict scorecard is written only on MONDAY refreshes '
            f'(step 4.97b). Today is {WEEKDAYS[today.weekday()]}; an absent file '
            f'is expected if no Monday refresh has completed since the last purge.',
        ]

    def render() -> list[str]:
        df = vs.payload
        _req_cols(df, ('bucket', 'verdict', 'n', 'n_players', 'mean_actual'),
                  'verdict_scorecard.csv')
        lines = [
            f'- `verdict_scorecard.csv` — {vs.age_phrase()} '
            f'(no date column in this artifact, so the age is mtime-based)',
            # No fillna(0): a non-numeric `n` cell must not silently contribute
            # zero observations and make the sample look smaller-but-valid.
            f'- {len(df)} bucket x verdict cells over '
            f'{_settled_total(df)} settled observations',
            '',
            '| bucket | verdict | n | players | mean actual | mean proj | residual | hit rate |',
            '|---|---|---|---|---|---|---|---|',
        ]
        for _, r in df.iterrows():
            def cell(col: str, fmt: str = '{:.3f}') -> str:
                if col not in df.columns:
                    return 'n/a'
                v = r[col]
                if pd.isna(v):
                    return '--'
                try:
                    return fmt.format(float(v))
                except (TypeError, ValueError):
                    return str(v)
            lines.append(
                f'| {r["bucket"]} | {r["verdict"]} | {cell("n", "{:.0f}")} | '
                f'{cell("n_players", "{:.0f}")} | {cell("mean_actual")} | '
                f'{cell("mean_proj_per")} | {cell("mean_residual")} | {cell("hit_rate")} |')
        return lines

    return _guard(vs, render, malformed)


def _model_health_section(arts: dict[str, Artifact], malformed: list[str]) -> list[str]:
    sc = arts['model_scorecard.csv']
    md = arts['model_scorecard.md']

    def render() -> list[str]:
        df = sc.payload
        _req_cols(df, ('section', 'metric', 'segment', 'value', 'status', 'note'),
                  'model_scorecard.csv')
        trip = df[df['section'].isin(TRIPWIRE_SECTIONS)]
        counts = trip['status'].value_counts().to_dict()
        summary = ', '.join(f'{k} {v}' for k, v in sorted(counts.items()))
        lines = [
            f'- `model_scorecard.csv` — {sc.age_phrase()}',
            f'- Tripwires (data_health + pipeline_staleness): {summary or "none"}',
        ]
        # Drift-sentinel roll call: state each one explicitly, including if the
        # row is absent, so "the sentinel did not run" cannot read as "passed".
        lines.append(f'- Drift sentinels (added {DRIFT_SENTINELS_ADDED.isoformat()}):')
        asof = sc.content_date
        predates = asof is not None and asof < DRIFT_SENTINELS_ADDED
        for metric in DRIFT_SENTINELS:
            rows = df[df['metric'] == metric]
            if rows.empty:
                why = (f'this scorecard is as-of {asof}, which PREDATES the '
                       f'{DRIFT_SENTINELS_ADDED.isoformat()} introduction — expected; '
                       f'the next Monday scorecard will carry it'
                       if predates else
                       'the check did not run, and that is NOT a PASS — '
                       'investigate build_model_scorecard.py')
                lines.append(f'  - `{metric}` — **NO ROW in this scorecard**: {why}')
                continue
            for _, r in rows.iterrows():
                lines.append(f'  - `{metric}` ({r["segment"]}): **{r["status"]}** — {r["note"]}')
        fwd = df[(df['section'] == 'forward_accuracy')
                 & (df['segment'] == 'all')
                 & (df['metric'].astype(str).str.contains('spearman_rate|vs_prior_delta'))]
        if fwd.empty:
            lines.append('- No forward-accuracy `all`-segment rows in this scorecard.')
        else:
            lines.append('- Forward accuracy (all-segment headline rows):')
            for _, r in fwd.iterrows():
                val = r['value']
                val_txt = f'{float(val):.4f}' if pd.notna(val) else 'INSUFFICIENT'
                lines.append(f'  - `{r["metric"]}` = {val_txt} [{r["status"]}]')
        if md.usable:
            lines.append(f'- Full rendered scorecard: `{md.path.name}` — {md.age_phrase()}')
        else:
            lines.append(f'- Rendered `model_scorecard.md` {md.age_phrase()} — '
                         f'CSV above is the source of truth for this brief.')
        return lines

    return _guard(sc, render, malformed)


def _pl_cache_section(pl_dir: Path, today: date) -> list[str]:
    """PL cache AGES only. This composer never fetches pitcherlist.com.

    refresh_dashboards.py step 7 documents why: the PL caches need a live
    WebSearch/WebFetch, which is an agent capability, not a headless scrape.
    So the brief reports what the last cached edition is and how old it is, and
    routes the refresh to an interactive session.
    """
    lines = [
        '- Read-only: this brief does NOT fetch pitcherlist.com. Per '
        '`refresh_dashboards.py` step 7 the PL caches need a live agent '
        'WebSearch/WebFetch (deliberately not another headless scrape), so '
        'refresh them in an interactive session (`/triangulate --check-caches`).',
    ]
    rows, import_err = _pl_cache_rows(pl_dir, today)
    if import_err:
        lines.append(f'- **not available** — could not import the cadence checker '
                     f'`scripts.xfp.lib.pl_cache` ({import_err}); PL cache ages unknown.')
        return lines
    for r in rows:
        if r.problem == 'MISSING':
            lines.append(f'- `{r.fname}` — **MISSING**')
        elif r.problem == 'UNREADABLE':
            lines.append(f'- `{r.fname}` — **UNREADABLE** ({r.reason})')
        elif r.problem == 'NO_DATE':
            lines.append(f'- `{r.fname}` — present but {r.reason}; age UNKNOWN '
                         f'(do not assume current)')
        elif r.problem == 'CHECK_ERROR':
            lines.append(f'- `{r.fname}` — fetched {r.fetched} ({r.age_days}d old); '
                         f'cadence check errored ({r.reason})')
        else:
            mark = '**STALE**' if r.stale else 'current'
            lines.append(f'- `{r.fname}` — fetched {r.fetched} ({r.age_days}d old) '
                         f'— {mark}: {r.reason}')
    return lines


def _provenance_section(arts: dict[str, Artifact]) -> list[str]:
    lines = [
        '| artifact | status | as-of | age | basis | regenerate with |',
        '|---|---|---|---|---|---|',
    ]
    for name in sorted(arts):
        art = arts[name]
        if not art.exists:
            status = 'MISSING'
        elif art.read_error:
            status = 'UNREADABLE'
        elif art.stale:
            status = 'STALE'
        else:
            status = 'ok'
        asof = art.content_date or art.mtime_date
        age = f'{art.age_days}d' if art.age_days is not None else '--'
        lines.append(
            f'| `{name}` | {status} | {asof if asof else "--"} | {age} | '
            f'{art.age_basis} | `{REGEN.get(name, "--")}` |')
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Compose
# ─────────────────────────────────────────────────────────────────────────────
def build_brief(paths: BriefPaths, now: datetime) -> tuple[str, list[str]]:
    """Compose the brief. Returns (markdown, malformed_messages).

    Deterministic given (paths' file contents, now.date()). The only wall-clock
    text is the single `Brief built:` line, so an intraday rerun diffs to one
    line.
    """
    today = now.date()
    arts = load_artifacts(paths, today)
    dec = collect_decisions(arts, paths, today)
    malformed = list(dec.malformed)

    body: list[str] = [
        '# Monday brief — New York Ligers (BrownU)',
        '',
        f'_As-of date **{today.isoformat()}** ({WEEKDAYS[today.weekday()]}). '
        'Composed offline from artifacts already on disk — no live ESPN, MLB '
        'Stats, or Pitcher List calls. Every number below is stamped with the '
        'age of the file it came from._',
        '',
        f'<!-- Brief built: {now.isoformat(timespec="seconds")} — the ONLY '
        'wall-clock stamp in this file; the body depends on the calendar date '
        'only, so intraday reruns diff to this line alone. -->',
        '',
    ]
    body += _section('1. Decisions', _decisions_section(dec))
    body += _section('2. This period — P(win) and cap',
                     _matchup_section(arts, malformed))
    body += _section('3. Recommended plan (weekly optimizer)',
                     _optimizer_section(arts, malformed))
    body += _section('4. Delta-P(win) surface (durable counterfactual store)',
                     _dpwin_section(arts, malformed))
    body += _section('5. Season outlook (title odds, value of a win)',
                     _season_sim_section(arts, malformed))
    body += _section('6. Decision quality (settled verdicts)',
                     _verdict_section(arts, today, malformed))
    body += _section('7. Model + data health', _model_health_section(arts, malformed))
    body += _section('8. Pitcher List cache ages (no scraping here)',
                     _pl_cache_section(paths.pl_cache_dir, today))
    body += _section('9. Provenance', _provenance_section(arts))

    # de-dup while preserving order (a section can re-report a decision malform)
    seen: set[str] = set()
    uniq = [m for m in malformed if not (m in seen or seen.add(m))]
    return '\n'.join(body).rstrip() + '\n', uniq


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=None,
                    help='output path (default data/outputs/monday_brief.md)')
    ap.add_argument('--outputs-dir', default=None, help='override data/outputs')
    ap.add_argument('--research-dir', default=None, help='override data/research')
    ap.add_argument('--now', default=None,
                    help='as-of date YYYY-MM-DD (testing / replay). Default: today.')
    ap.add_argument('--print', dest='do_print', action='store_true',
                    help='also print the brief to stdout')
    args = ap.parse_args(argv)

    if args.now:
        try:
            now = datetime.strptime(args.now[:10], '%Y-%m-%d')
        except ValueError:
            print(f'ERROR: --now must be YYYY-MM-DD, got {args.now!r}', file=sys.stderr)
            return 1
    else:
        now = datetime.now()

    paths = default_paths(outputs=args.outputs_dir, research=args.research_dir,
                          out=args.out)
    try:
        text, malformed = build_brief(paths, now)
    except Exception as exc:  # composition itself broke — loud, exit 1
        print(f'ERROR: brief composition failed: {type(exc).__name__}: {exc}',
              file=sys.stderr)
        raise

    try:
        paths.out.parent.mkdir(parents=True, exist_ok=True)
        paths.out.write_text(text, encoding='utf-8')
    except OSError as exc:
        print(f'ERROR: could not write {paths.out}: {exc}', file=sys.stderr)
        return 1

    print(f'wrote {paths.out} ({len(text.splitlines())} lines)')
    if args.do_print:
        print()
        print(text)
    if malformed:
        print(f'\n! {len(malformed)} MALFORMED artifact issue(s) — the brief was '
              f'written but these are real defects:', file=sys.stderr)
        for m in malformed:
            print(f'  - {m}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
