"""Runner for /volume-watch — playing-time movers board.

Surfaces PLAYING-TIME risers/faders by comparing the validated volume models
(xfp_volume / xfp_sp_volume, refresh steps 4.09/4.09b) against naive
season-to-date pace, ranked by FP IMPACT per team-game (volume gap x rate),
with a live ESPN ownership overlay (MINE / opponent team / FA).

  python scripts/xfp/run_volume_watch.py
  python scripts/xfp/run_volume_watch.py --names "Jac Caglianone, Kumar Rocker"
  python scripts/xfp/run_volume_watch.py --top 20

The volume-parallel of /trending: trending = getting physically BETTER,
volume-watch = playing MORE. Rule 13 — display/decision layer only; never
moves rh3/rp3.

Sections:
  1. VOLUME GAP board (works from day one): proj_ros vol vs naive pace,
     split RISERS / FADERS, ranked by |gap| x rate = FP/team-game impact.
  2. Day-over-day proj_volume delta (auto-activates once
     player_projection_history.parquet has >=7 days of proj_volume;
     prints 'insufficient history' until then — logging began 2026-07-09).
  3. Ownership overlay from a LIVE all_teams() walk (never stale context).

Output: console + data/outputs/volume_watch.csv
"""
import sys, argparse, unicodedata
# Windows cp1252 console guard — sections print — etc. (item 23)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
_REPO_ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]  # repo root, NOT cwd (issue #72)
sys.path.insert(0, str(_REPO_ROOT))
import numpy as np
import pandas as pd
from pathlib import Path

from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id
from scripts.xfp.lib.bucket_dispatch import _flip_lastfirst  # shared 'Last, First' flip (audit item 9)

OUT_CSV = Path('data/outputs/volume_watch.csv')
HIST_PATH = Path('data/research/player_projection_history.parquet')
DELTA_MIN_DAYS = 7          # day-over-day section activates at >= this many snapshots
DELTA_LOOKBACK_DAYS = 7     # WoW window once active

C = Path('data/research/xfp_cache')
HIT_MULTI = pd.read_csv(C / 'hitters_multiyr_2015_2026.csv')
SP_MULTI = pd.read_csv(C / 'sp_multiyr_2015_2025.csv')
try:
    RP_MULTI = pd.read_csv(C / 'relievers_multiyr_2018_2026.csv')
except Exception:
    RP_MULTI = None


# ── name helpers ─────────────────────────────────────────────────────────

# Name join key — OWNER: plv_clone.utils.name_match.safe_name_key. Order-
# PRESERVING, space-separated ("kyle schwarber"), collapses curly-vs-straight
# apostrophes, C.J./CJ and hyphens. NEVER re-derive locally: a local copy
# mis-keyed Ryan O'Hearn's U+2019 apostrophe and printed an opponent's player
# as a FREE AGENT (2026-07-28). NOT join_key — that one sorts tokens and drops
# separators, which is a different (order-independent) key.
from plv_clone.utils.name_match import safe_name_key as _norm  # noqa: E402


def display_name(name):
    return _flip_lastfirst(str(name).strip())


def _is_pitcher(pos):
    return str(pos).upper() in {'SP', 'RP', 'P'}


# ── ownership overlay (LIVE — /roster-verify rule) ───────────────────────

def build_ownership(hit_ids, sp_ids, hit_names_by_norm, sp_names_by_norm):
    """Walk live rosters -> {mlbam_id: team_name}. Returns (owner_map,
    my_team_name, n_unresolved). Anything absent from the map is FA
    (checked against ALL 8 rosters, so Connelly-Early safe)."""
    from plv_clone.league_state import default_state
    st = default_state()
    allp = st.all_teams()
    mine = st.my_roster()
    my_ids = set(mine['player_id'].dropna().astype('Int64').tolist())
    # derive MY team name live (never hardcode / session memory)
    my_team = None
    m = allp[allp['player_id'].isin(my_ids)]
    if not m.empty:
        my_team = m['team_name'].mode().iloc[0]

    owner, unresolved = {}, 0
    for _, r in allp.iterrows():
        nm, pos, team = r['player_name'], r['position'], r.get('pro_team')
        pid = None
        try:
            if _is_pitcher(pos):
                pid = resolve_pitcher_id(nm, team=team,
                                         role=('SP' if str(pos).upper() == 'SP' else 'RP'),
                                         sp_multiyr=SP_MULTI, rp_multiyr=RP_MULTI)
            else:
                pid = resolve_batter_id(nm, team=team, position=pos, multiyr=HIT_MULTI)
        except Exception:
            pid = None
        if pid is None:
            # fallback: normalized FULL-name match against the volume boards
            # (skip-on-ambiguous; never last-name contains)
            key = _norm(nm)
            cands = ([i for i in (hit_names_by_norm.get(key) or [])] +
                     [i for i in (sp_names_by_norm.get(key) or [])])
            if len(set(cands)) == 1:
                pid = cands[0]
        if pid is None:
            unresolved += 1
            continue
        owner[int(pid)] = r['team_name']
    return owner, my_team, unresolved, my_ids


def own_tag(mlbam, owner, my_team):
    t = owner.get(int(mlbam))
    if t is None:
        return 'FA'
    return 'MINE' if t == my_team else t


# ── board construction ───────────────────────────────────────────────────

def load_hitter_board():
    v = pd.read_csv('data/outputs/xfp_volume_projections.csv')
    rh3 = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
    rate = rh3[['batter', 'primary_position', 'xfp_rh3_per_pa']].rename(
        columns={'batter': 'mlbam_id', 'primary_position': 'position',
                 'xfp_rh3_per_pa': 'rate'})
    d = v.merge(rate, on='mlbam_id', how='left')
    med = rate['rate'].median()
    d['rate_source'] = np.where(d['rate'].notna(), 'rh3', 'median_fallback')
    d['rate'] = d['rate'].fillna(med)
    d['position'] = d['position'].fillna('?')
    d['gap'] = d['proj_ros_pa_per_teamgame'] - d['naive_pace']
    d['impact'] = d['gap'] * d['rate']            # FP per team-game
    d['proj_vol'] = d['proj_ros_pa_per_teamgame']
    # Role vs availability (lib.volume_semantics, the one owner): a FADER gap
    # on an intact everyday role is an injury-risk discount, not a lineup
    # signal — display must not conflate them (Muncy canonical, 2026-08-29).
    from lib.volume_semantics import decompose_hitter_volume
    dec = d.apply(decompose_hitter_volume, axis=1, result_type='expand')
    d['in_role_vol'] = dec['in_role']
    d['fade_kind'] = dec['fade_kind']
    d['recent_vol'] = d['pa_last21'] / 21.0 * (162 / 162)  # PA per team-game proxy (L21 cal. days)
    d['player_type'] = 'H'
    fl = np.where(d['is_on_il_at_split'] > 0, 'IL@split', '')
    fl = np.where(d['rate_source'] == 'median_fallback',
                  np.where(fl == '', 'med-rate', fl + '+med-rate'), fl)
    d['flags'] = fl
    d['unit'] = 'PA/tg'
    d['recent_raw'] = d['pa_last21']
    return d


def load_sp_board():
    v = pd.read_csv('data/outputs/xfp_sp_volume_projections.csv')
    rp3 = pd.read_csv('data/outputs/xfp_rp3_projections.csv')
    rate = rp3[['pitcher', 'player_name', 'xfp_rp3_per_start', 'data_quality_tag']].rename(
        columns={'pitcher': 'mlbam_id', 'player_name': 'rp3_name',
                 'xfp_rp3_per_start': 'rate'})
    d = v.merge(rate, on='mlbam_id', how='left')
    # some volume rows carry no name/team (thin-sample arms) — backfill from rp3
    d['player_name'] = d['player_name'].fillna(d['rp3_name'])
    d = d[d['player_name'].notna()].copy()
    med = rate['rate'].median()
    d['rate_source'] = np.select(
        [d['data_quality_tag'].astype(str).str.startswith('data_driven'),
         d['data_quality_tag'].astype(str).str.contains('marcel', na=False)],
        ['rp3', 'rp3_marcel_prior'], default='median_fallback')
    d['rate'] = d['rate'].fillna(med)
    d['position'] = 'SP'
    d['gap'] = d['proj_ros_gs_per_teamgame'] - d['naive_pace']
    d['in_role_vol'] = np.nan   # SP availability decomposition: follow-up
    d['fade_kind'] = ''
    d['impact'] = d['gap'] * d['rate']            # FP per team-game
    d['proj_vol'] = d['proj_ros_gs_per_teamgame']
    d['recent_vol'] = d['gs_last21'] / 21.0
    d['player_type'] = 'SP'
    fl = np.where(d['is_on_il_at_split'] > 0, 'IL@split', '')
    ret = d['days_since_il_return_imp']
    fl = np.where(ret.notna() & (ret <= 30) & (ret >= 0),
                  np.where(fl == '', 'IL-return', fl + '+IL-return'), fl)
    fl = np.where(d['rate_source'] == 'rp3_marcel_prior',
                  np.where(fl == '', 'marcel-rate', fl + '+marcel-rate'), fl)
    d['flags'] = fl
    d['unit'] = 'GS/tg'
    d['recent_raw'] = d['gs_last21']
    return d


def attach_ownership(dh, dsp):
    hit_by_norm, sp_by_norm = {}, {}
    for _, r in dh.iterrows():
        hit_by_norm.setdefault(_norm(r['player_name']), []).append(int(r['mlbam_id']))
    for _, r in dsp.iterrows():
        sp_by_norm.setdefault(_norm(r['player_name']), []).append(int(r['mlbam_id']))
    owner, my_team, unresolved, _ = build_ownership(None, None, hit_by_norm, sp_by_norm)
    for d in (dh, dsp):
        d['own'] = [own_tag(i, owner, my_team) for i in d['mlbam_id']]
    return my_team, unresolved


# ── day-over-day delta (activates as panel history accumulates) ──────────

def volume_delta_section():
    if not HIST_PATH.exists():
        print('\n=== DAY-OVER-DAY proj_volume DELTA ===')
        print('  insufficient history (0 days) — snapshot logger not found')
        return None
    h = pd.read_parquet(HIST_PATH)
    h = h[h['proj_volume'].notna()].copy()
    days = sorted(h['snapshot_date'].unique())
    print('\n=== DAY-OVER-DAY proj_volume DELTA (WoW once >=%d days logged) ===' % DELTA_MIN_DAYS)
    if len(days) < DELTA_MIN_DAYS:
        print(f'  insufficient history ({len(days)} day{"s" if len(days) != 1 else ""} of '
              f'proj_volume logged: {", ".join(days)}) — auto-activates at {DELTA_MIN_DAYS}')
        return None
    latest = days[-1]
    # nearest snapshot >= LOOKBACK days back
    target = pd.Timestamp(latest) - pd.Timedelta(days=DELTA_LOOKBACK_DAYS)
    prior = max([d for d in days if pd.Timestamp(d) <= target], default=days[0])
    a = h[h['snapshot_date'] == latest].set_index(['player_type', 'mlbam_id'])
    b = h[h['snapshot_date'] == prior].set_index(['player_type', 'mlbam_id'])
    j = a[['player_name', 'proj_volume']].join(
        b[['proj_volume']], rsuffix='_prior', how='inner')
    j['d_vol'] = j['proj_volume'] - j['proj_volume_prior']
    print(f'  window: {prior} -> {latest}')
    for ptype, label in [('H', 'HITTERS (d PA/tg)'), ('SP', 'SP (d GS/tg)')]:
        sub = j.loc[ptype] if ptype in j.index.get_level_values(0) else pd.DataFrame()
        if sub.empty:
            continue
        print(f'  -- {label}: top movers --')
        for _, r in sub.reindex(sub['d_vol'].abs().sort_values(ascending=False).index).head(10).iterrows():
            arrow = 'UP  ' if r['d_vol'] > 0 else 'DOWN'
            print(f"    {arrow} {display_name(r['player_name']):<24} {r['proj_volume_prior']:.3f} -> "
                  f"{r['proj_volume']:.3f}  ({r['d_vol']:+.3f})")
    return j


# ── rendering ────────────────────────────────────────────────────────────

HDR = (f"{'player':<24} {'tm':<4} {'pos':<4} {'own':<22} {'proj':>6} {'pace':>6} "
       f"{'gap':>7} {'pct':>5} {'L21':>4} {'rate':>6} {'impact':>7}  flags")


def row_line(r):
    team = r['team'] if pd.notna(r['team']) else '?'
    l21 = f"{r['recent_raw']:.0f}" if pd.notna(r['recent_raw']) else '-'
    return (f"{display_name(r['player_name']):<24} {str(team):<4} {str(r['position']):<4} "
            f"{str(r['own'])[:21]:<22} {r['proj_vol']:>6.3f} {r['naive_pace']:>6.3f} "
            f"{r['gap']:>+7.3f} {r['volume_percentile']:>5.0f} {l21:>4} {r['rate']:>6.2f} "
            f"{r['impact']:>+7.3f}  {r['flags']}")


def print_section(title, df, top):
    print(f"\n--- {title} ---")
    if df.empty:
        print('  (none)')
        return
    print('  ' + HDR)
    for _, r in df.head(top).iterrows():
        print('  ' + row_line(r))


def render_group(d, label, top):
    """RISERS/FADERS boards for one position group, FA/MINE first."""
    risers = d[d['gap'] > 0].sort_values('impact', ascending=False)
    faders = d[d['gap'] < 0].sort_values('impact')
    print_section(f'{label}: FA RISERS (pickup edge — role expanding before the box score shows it)',
                  risers[risers['own'] == 'FA'], top)
    print_section(f'{label}: MINE FADERS (warning — my role-eroders)',
                  faders[faders['own'] == 'MINE'], top)
    print_section(f'{label}: TOP RISERS (all owners)', risers, top)
    print_section(f'{label}: TOP FADERS (all owners)', faders, top)
    return risers, faders


def name_cards(dh, dsp, names):
    boards = pd.concat([dh, dsp], ignore_index=True)
    boards['norm'] = boards['player_name'].map(_norm)
    print('=== VOLUME WATCH — ad-hoc cards ===')
    for nm in [x.strip() for x in names.split(',') if x.strip()]:
        rows = boards[boards['norm'] == _norm(nm)]
        if rows.empty:
            print(f"\n{nm}: no volume-model row (below PA/GS floor, RP, or not in 2026 sample)")
            continue
        for _, r in rows.iterrows():
            unit = r['unit']
            direction = 'RISER' if r['gap'] > 0 else ('FADER' if r['gap'] < 0 else 'FLAT')
            if direction == 'FADER' and r.get('fade_kind'):
                direction = f"FADER ({r['fade_kind']})"  # ROLE = lineup signal; AVAILABILITY = injury discount, role intact
            print(f"\n{display_name(r['player_name'])} ({r['team']}, {r['position']}) — {r['own']} — {direction}")
            if r.get('fade_kind') == 'AVAILABILITY':
                print(f"  in-role volume  : {r['in_role_vol']:.3f} {r['unit']} when active — use THIS for daily start/sit; proj prices missed-time risk")
            print(f"  proj RoS volume : {r['proj_vol']:.3f} {unit}   naive pace: {r['naive_pace']:.3f}   "
                  f"gap: {r['gap']:+.3f}  (volume pct {r['volume_percentile']:.0f})")
            print(f"  recent (L21d)   : {r['recent_vol']:.3f} {unit}")
            print(f"  rate ({r['rate_source']}): {r['rate']:.2f} FP/{'PA' if r['player_type']=='H' else 'start'}"
                  f"   ->  impact {r['impact']:+.3f} FP/team-game")
            if r['flags']:
                print(f"  flags           : {r['flags']}")


# ── main ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--names', default=None, help='comma-separated names for ad-hoc cards')
    ap.add_argument('--top', type=int, default=15)
    args = ap.parse_args()

    dh, dsp = load_hitter_board(), load_sp_board()
    my_team, unresolved = attach_ownership(dh, dsp)

    if args.names:
        name_cards(dh, dsp, args.names)
        volume_delta_section()
        return

    print('=== VOLUME WATCH — playing-time movers (model RoS volume vs naive season pace) ===')
    print(f'  my team: {my_team}   hitters: {len(dh)}   SPs: {len(dsp)}   '
          f'unresolved rostered->mlbam: {unresolved}')
    print('  impact = (proj_vol - pace) x rate = FP per TEAM-GAME the volume move is worth.')
    print('  Rule 13: display/decision layer — headline projections stay rh3/rp3.')

    render_group(dh, 'HITTERS', args.top)
    render_group(dsp, 'SP', args.top)
    volume_delta_section()

    cols = ['player_type', 'mlbam_id', 'player_name', 'team', 'position', 'own',
            'proj_vol', 'in_role_vol', 'naive_pace', 'gap', 'volume_percentile',
            'recent_raw', 'rate', 'rate_source', 'impact', 'flags', 'fade_kind', 'unit']
    out = pd.concat([dh[cols], dsp[cols]], ignore_index=True)
    out['player_name'] = out['player_name'].map(display_name)
    out['direction'] = np.where(out['gap'] > 0, 'RISER', np.where(out['gap'] < 0, 'FADER', 'FLAT'))
    # A FADER whose role is intact is an injury-risk discount, not a lineup
    # signal — say which (lib.volume_semantics; Muncy canonical 2026-08-29).
    avail = (out['direction'] == 'FADER') & (out['fade_kind'] == 'AVAILABILITY')
    out.loc[avail, 'direction'] = 'FADER-AVAIL'
    out = out.reindex(out['impact'].abs().sort_values(ascending=False).index)
    out.to_csv(OUT_CSV, index=False)
    print(f'\nwrote {OUT_CSV} ({len(out)} rows)')


if __name__ == '__main__':
    main()
