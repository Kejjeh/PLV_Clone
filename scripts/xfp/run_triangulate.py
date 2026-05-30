"""
/triangulate engine — combine PL rank + our model (rh3/rp3/rprs2) + archetype model
into one unified player profile.

Usage:
    python scripts/xfp/run_triangulate.py "Aaron Judge"
    python scripts/xfp/run_triangulate.py "Reid Detmers" "Ryan Weathers" "Ryne Nelson"
    python scripts/xfp/run_triangulate.py --bucket SP "Reid Detmers"

Reads PL ranks from data/research/pl_cache/ (the SKILL.md tells Claude how to
refresh those caches via WebFetch when stale).

Outputs a markdown card per player + a comparison table if multiple players.
"""

from __future__ import annotations
import argparse, json, os, sys, unicodedata, glob, io
import pandas as pd

# Force UTF-8 for stdout on Windows so arrows / accents don't crash
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PL_CACHE_DIR = 'data/research/pl_cache'
ARCHETYPE_PANELS = {
    'H':  'data/research/hitter_archetype_career_panel.parquet',
    'SP': 'data/research/sp_archetype_career_panel.parquet',
    'RP': 'data/research/rp_archetype_career_panel.parquet',
}
PROJECTIONS = {
    'H':  'data/outputs/xfp_rh3_projections.csv',
    'SP': 'data/outputs/xfp_rp3_projections.csv',
    'RP': 'data/outputs/xfp_rprs2_projections.csv',
}
PL_CACHE_FILES = {
    'H':         'pl_hitters_top150.json',
    'SP':        'pl_sps_top100.json',
    'SP_STREAM': 'pl_sp_streamers_latest.json',
    'RP':        'pl_closers.json',
}

# ---------- helpers ----------

def _norm(s: str) -> str:
    return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode('ascii').lower().strip()

def _flip_lastfirst(s: str) -> str:
    if ',' in str(s):
        a, b = s.split(',', 1)
        return f"{b.strip()} {a.strip()}"
    return str(s)

# ---------- name resolution ----------

def resolve_player(name: str, hint: str | None = None) -> dict | None:
    """Return {'id', 'bucket', 'display_name', 'team', 'position'} or None."""
    key = _norm(name)
    # Try each projection file; first hit wins. If bucket hint provided, try that first.
    order = [hint] + [b for b in ('H','SP','RP') if b != hint] if hint else ['H','SP','RP']
    for bucket in order:
        if bucket is None: continue
        df = pd.read_csv(PROJECTIONS[bucket])
        if bucket == 'H':
            df['_key'] = df['player_name'].apply(_norm)
            id_col, name_col = 'batter', 'player_name'
        elif bucket == 'SP':
            df['_key'] = df['player_name'].apply(_flip_lastfirst).apply(_norm)
            id_col, name_col = 'pitcher', 'player_name'
        else:  # RP — rprs2 uses 'name_api' (already in First Last form)
            df['_key'] = df['name_api'].apply(_norm)
            id_col, name_col = 'pitcher', 'name_api'
        m = df[df['_key'] == key]
        if not m.empty:
            r = m.iloc[0]
            disp = r[name_col]
            if bucket == 'SP':
                disp = _flip_lastfirst(disp)
            return {
                'id': int(r[id_col]),
                'bucket': bucket,
                'display_name': disp,
                'team': r.get('team', ''),
                'position': r.get('primary_position', '') if bucket == 'H' else bucket,
            }
    # Fallback: try archetype panels (for rookies not in projections yet)
    for bucket, panel in ARCHETYPE_PANELS.items():
        if not os.path.exists(panel): continue
        p = pd.read_parquet(panel)
        name_col = 'player_name' if 'player_name' in p.columns else 'name'
        p['_key'] = p[name_col].apply(_norm)
        m = p[p['_key'] == key]
        if not m.empty:
            r = m.sort_values('year').iloc[-1]
            id_col = 'batter' if bucket == 'H' else 'pitcher'
            return {
                'id': int(r[id_col]),
                'bucket': bucket,
                'display_name': r[name_col],
                'team': r.get('team', ''),
                'position': bucket,
            }
    return None

# ---------- PL rank ----------

def _load_pl_cache(filename: str) -> dict:
    path = os.path.join(PL_CACHE_DIR, filename)
    if not os.path.exists(path):
        return {'fetched': None, 'source_url': None, 'ranks': {}}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def pl_rank(name: str, bucket: str) -> tuple[int | str, str | None]:
    """Return (rank|'UR'|'—', cache_date)."""
    cache_key = bucket  # H / SP / RP
    cache = _load_pl_cache(PL_CACHE_FILES[cache_key])
    ranks = cache.get('ranks', {})
    fetched = cache.get('fetched')
    # exact-norm match
    nk = _norm(name)
    for pl_name, rk in ranks.items():
        if _norm(pl_name) == nk:
            return rk, fetched
    # If hitter or SP in the rankable universe but not found → UR (unranked)
    if ranks:
        return 'UR', fetched
    return '—', None

def pl_streamer_rank(name: str) -> tuple[str, str | None, str | None]:
    """For SPs only: return (rank+tier string, opp, cache_date) from streamer cache if present."""
    cache = _load_pl_cache(PL_CACHE_FILES['SP_STREAM'])
    ranks = cache.get('ranks', {})  # name -> {rank, tier, opp}
    fetched = cache.get('fetched')
    nk = _norm(name)
    for pl_name, info in ranks.items():
        if _norm(pl_name) == nk:
            return f"#{info.get('rank','?')} [{info.get('tier','?')}]", info.get('opp'), fetched
    return '—', None, fetched

# ---------- model row ----------

def model_row(player: dict) -> dict:
    bucket = player['bucket']
    df = pd.read_csv(PROJECTIONS[bucket])
    if bucket == 'H':
        m = df[df['batter'] == player['id']]
    else:
        m = df[df['pitcher'] == player['id']]
    if m.empty:
        return {'rank': '—', 'proj': None, 'signal': '—', 'rep_delta': None, 'recform': None}
    r = m.iloc[0]
    if bucket == 'H':
        return {
            'rank': int(r['rank']),
            'proj_label': 'fp/game',
            'proj': float(r['xfp_rh3_per_game']),
            'signal': r['signal'],
            'rep_delta': float(r['replacement_delta']),
            'recform': float(r['recency_form_gap']),
            'extra': f"pa_to={int(r['pa_to'])}",
        }
    if bucket == 'SP':
        return {
            'rank': int(r['rank']),
            'proj_label': 'fp/start',
            'proj': float(r['xfp_rp3_per_start']),
            'signal': r['signal'],
            'rep_delta': float(r['replacement_delta']),
            'recform': float(r['recency_form_gap']),
            'extra': f"gs_to={int(r['gs_to'])}",
        }
    # RP
    return {
        'rank': int(r['rank']),
        'proj_label': 'xfp_ros',
        'proj': float(r['xfp_ros']),
        'signal': r['signal'],
        'rep_delta': float(r['replacement_delta']),
        'recform': None,
        'extra': f"role={r['role_lag1']} sv_to={int(r.get('sv_to') or 0)} hld_to={int(r.get('hld_to') or 0)}",
    }

# ---------- archetype row ----------

def archetype_row(player: dict) -> dict:
    bucket = player['bucket']
    panel_path = ARCHETYPE_PANELS[bucket]
    if not os.path.exists(panel_path):
        return {'have': False, 'reason': 'panel missing'}
    p = pd.read_parquet(panel_path)
    id_col = 'batter' if bucket == 'H' else 'pitcher'
    rows = p[p[id_col] == player['id']].sort_values('year')
    if rows.empty:
        return {'have': False, 'reason': 'not in archetype panel (insufficient innings/PA)'}
    cur = rows[rows['year'] == 2026]
    if cur.empty:
        cur = rows.iloc[[-1]]
    r = cur.iloc[0]
    out = {
        'have': True,
        'year': int(r['year']),
        'archetype': r.get('archetype'),
        'cell': r.get('cell'),
        'stuff_subtype': r.get('stuff_subtype'),
        'age': int(r['age']) if pd.notna(r.get('age')) else None,
        'age_tier': r.get('age_tier'),
        'overall': int(r['OVERALL']) if pd.notna(r.get('OVERALL')) else None,
        'traj_flag': r.get('traj_flag'),
        'slope_3yr': r.get('OVERALL_slope_3yr'),
        'career_pct': r.get('OVERALL_career_pct'),
        't1_fp': r.get('t1_fp_projection'),
        't2_fp': r.get('t2_fp_projection'),
        'velo': r.get('avg_velo'),
        'velo_tier': r.get('velo_tier'),
        'boundary_tier': r.get('boundary_tier'),
    }
    # bucket-specific ratings
    if bucket == 'SP':
        out['ratings'] = {'STUFF': int(r['STUFF']), 'MOVEMENT': int(r['MOVEMENT']), 'CONTROL': int(r['CONTROL'])}
        out['pitch_archetype'] = r.get('pitch_archetype')
    elif bucket == 'RP':
        out['ratings'] = {'STUFF': int(r['STUFF']), 'CONTROL': int(r['CONTROL']), 'BATTED_BALL': int(r['BATTED_BALL'])}
        out['leverage_tier'] = r.get('leverage_tier')
        out['closer'] = r.get('CLOSER')
        out['fireman'] = r.get('FIREMAN')
        out['high_lev'] = r.get('HIGH_LEVERAGE')
    else:  # H
        # hitter ratings are typically C/P/D in the panel
        for k in ('C','P','D','SB'):
            if k in p.columns:
                out.setdefault('ratings', {})[k] = int(r[k]) if pd.notna(r.get(k)) else None
    # career arc — last 4 years
    arc = rows.tail(4)[['year','archetype','OVERALL']]
    out['arc'] = [(int(y), a, int(o) if pd.notna(o) else None) for y,a,o in zip(arc['year'],arc['archetype'],arc['OVERALL'])]
    return out

# ---------- verdict synthesis ----------

def synthesize(player, pl_main, pl_main_date, pl_stream, pl_stream_date, model, arche):
    """Return a verdict tag + 1-2 sentence rationale."""
    bucket = player['bucket']
    notes = []
    # Pull comparable numbers
    pl_r = pl_main
    m_r = model.get('rank')
    a_t1 = arche.get('t1_fp') if arche.get('have') else None
    a_traj = arche.get('traj_flag') if arche.get('have') else None
    a_cell = arche.get('cell') if arche.get('have') else None
    a_archetype = arche.get('archetype') if arche.get('have') else None

    # Archetype trajectory + cell-based reads
    if arche.get('have'):
        if a_traj == 'TRENDING_UP' and isinstance(pl_r, int) and isinstance(m_r, int) and (m_r - pl_r) > 50:
            return 'BUY — archetype breakout', f"Archetype TRENDING_UP to {a_archetype} ({a_cell}); PL has caught it (#{pl_r}); model lagging (#{m_r}). Buy before model catches up."
        if a_traj == 'TRENDING_DOWN' and isinstance(pl_r, int) and pl_r <= 50:
            notes.append(f"⚠ Archetype TRENDING_DOWN (slope {arche['slope_3yr']:+.1f}) while PL still has him #{pl_r} — sell-high candidate.")
        if a_archetype in ('GENERIC_HR_PRONE','FILLER','WILD_MID','PIT_CHF'):
            notes.append(f"⚠ Archetype flag: {a_archetype} — bottom-tier process profile.")
        if a_traj in ('CAREER_LOW',) and arche.get('career_pct',0) == 0:
            notes.append(f"⚠ Career-low season ({arche['career_pct']*100:.0f}% career-percentile).")
        velo_tier = arche.get('velo_tier')
        if velo_tier == 'FINESSE' and a_traj == 'TRENDING_DOWN':
            notes.append("⚠ FINESSE velo tier + declining = drop tier.")

    # PL high, model high, archetype OVERALL high → strong hold
    if isinstance(pl_r, int) and isinstance(m_r, int) and arche.get('have'):
        ov = arche.get('overall',50)
        if pl_r <= 30 and m_r <= 50 and ov >= 55:
            return 'STRONG HOLD/BUY', f"All 3 lenses agree — PL #{pl_r}, model #{m_r}, archetype OVERALL {ov} ({a_archetype}). High conviction."

    # Disagreement triage
    if isinstance(pl_r, int) and isinstance(m_r, int):
        gap = m_r - pl_r
        if gap > 60 and arche.get('have') and arche.get('overall',50) < 50 and a_traj != 'TRENDING_UP':
            return 'FADE — PL chasing outcomes', f"PL #{pl_r} but model #{m_r} and archetype OVERALL {arche['overall']} ({a_archetype}) — process doesn't support PL rank."
        if gap < -50 and arche.get('have') and arche.get('overall',50) >= 55:
            return 'BUY — model anchored on prior', f"Model #{m_r} but PL #{pl_r} and archetype OVERALL {arche['overall']} ({a_archetype}) — model lagging."

    if not notes:
        return 'MIXED — see profile', "Signals don't converge to a single verdict; weigh the rate metrics against the trajectory before acting."
    return 'CAUTION', ' '.join(notes)

# ---------- output ----------

def format_card(player, pl_main, pl_main_date, pl_stream, pl_stream_date, model, arche, verdict, rationale):
    lines = []
    bucket = player['bucket']
    lines.append(f"\n## {player['display_name']} ({bucket}) — {verdict}\n")
    lines.append(f"*{rationale}*\n")

    # 3-source table
    pl_label = {'H':'PL Top150', 'SP':'PL Top100', 'RP':'PL Closers'}[bucket]
    model_label = {'H':'rh3', 'SP':'rp3', 'RP':'rprs2'}[bucket]
    lines.append("| Lens | Rank | Headline | Detail |")
    lines.append("|---|---|---|---|")
    pl_show = f"#{pl_main}" if isinstance(pl_main, int) else pl_main
    lines.append(f"| **{pl_label}** | {pl_show} | — | cache {pl_main_date or 'MISSING'} |")
    if bucket == 'SP' and pl_stream != '—':
        lines.append(f"| **PL Streamer ({pl_stream_date})** | {pl_stream} | vs {pl_stream_date or '?'} | — |")
    if model['rank'] != '—':
        proj = model['proj']
        proj_s = f"{proj:.2f} {model['proj_label']}" if proj is not None else '—'
        sig = f"signal={model['signal']}"
        rep = f"rep_d={model['rep_delta']:+.2f}" if model['rep_delta'] is not None else ''
        recf = f"recform={model['recform']:+.3f}" if model.get('recform') is not None else ''
        extra = f" | {model.get('extra','')}"
        lines.append(f"| **{model_label}** | #{model['rank']} | {proj_s} | {sig} {rep} {recf}{extra} |")
    else:
        lines.append(f"| **{model_label}** | — | not in projection file | — |")
    if arche.get('have'):
        rstr = ' / '.join(f"{k}={v}" for k,v in arche['ratings'].items())
        ar_h = f"OVERALL {arche['overall']} ({arche['archetype']} / {arche['cell']})"
        cp = arche.get('career_pct')
        cpstr = f", career-pct {cp*100:.0f}%" if cp is not None and pd.notna(cp) else ''
        sl = arche.get('slope_3yr')
        slstr = f", 3yr-slope {sl:+.1f}" if sl is not None and pd.notna(sl) else ''
        lines.append(f"| **Archetype** | — | {ar_h} | {rstr} | traj {arche['traj_flag']}{slstr}{cpstr} |")
        # Career arc inline
        arc = ' → '.join(f"{y}:{a}({o})" for y,a,o in arche['arc'])
        lines.append(f"\n**Career arc:** {arc}")
        # T+1
        if arche.get('t1_fp') is not None and pd.notna(arche['t1_fp']):
            unit = {'SP':'start', 'H':'PA', 'RP':'g'}[bucket]
            lines.append(f"\n**Archetype T+1 projection:** {arche['t1_fp']:.3f} fp/{unit}")
        # Role/leverage for RPs
        if bucket == 'RP':
            roles = []
            if arche.get('closer'): roles.append('CLOSER')
            if arche.get('high_lev'): roles.append('HIGH_LEVERAGE')
            if arche.get('fireman'): roles.append('FIREMAN')
            lev = arche.get('leverage_tier')
            tagstr = ', '.join(roles) if roles else 'non-role'
            lines.append(f"\n**Role tags:** {tagstr} | leverage_tier={lev}")
        # Velo
        v = arche.get('velo'); vt = arche.get('velo_tier')
        if v is not None and pd.notna(v):
            lines.append(f"\n**Velo:** {v:.1f} mph [{vt}]")
    else:
        lines.append(f"| **Archetype** | — | NOT AVAILABLE | {arche.get('reason','')} |")
    return '\n'.join(lines)

def compare_table(rows):
    """Render a comparison table across all profiled players."""
    out = ["\n## Comparison\n"]
    out.append("| Player | Bucket | PL | Model | Archetype OVERALL | T+1 | Traj | Verdict |")
    out.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        p = r['player']; pl = r['pl_main']; m = r['model']; a = r['arche']
        pl_show = f"#{pl}" if isinstance(pl, int) else pl
        m_show = f"#{m['rank']} ({m['proj']:.2f})" if m['rank'] != '—' and m.get('proj') is not None else '—'
        if a.get('have'):
            a_show = f"{a['overall']} ({a['archetype']})"
            t1 = f"{a['t1_fp']:.2f}" if a.get('t1_fp') is not None and pd.notna(a['t1_fp']) else '—'
            tr = a['traj_flag']
        else:
            a_show = '—'; t1 = '—'; tr = '—'
        out.append(f"| {p['display_name']} | {p['bucket']} | {pl_show} | {m_show} | {a_show} | {t1} | {tr} | {r['verdict']} |")
    return '\n'.join(out)

# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('names', nargs='*', help='Player names (or use --names-file)')
    ap.add_argument('--bucket', choices=['H','SP','RP'], default=None,
                    help='Force a position bucket (otherwise auto-detected)')
    ap.add_argument('--names-file', default=None, help='CSV with a player_name column (batch mode)')
    ap.add_argument('--csv-out', default=None, help='Write batch results to this CSV (instead of per-player cards)')
    args = ap.parse_args()

    if args.names_file:
        nf = pd.read_csv(args.names_file)
        name_list = nf['player_name'].dropna().astype(str).tolist()
    else:
        name_list = args.names

    rows = []
    csv_rows = []
    for name in name_list:
        player = resolve_player(name, args.bucket)
        if not player:
            csv_rows.append({'player_name': name, 'bucket': '?', 'resolved': False})
            if not args.csv_out:
                print(f"\n### {name} — NOT FOUND in projections or archetype panels.\n")
            continue
        bucket = player['bucket']
        pl_main, pl_main_date = pl_rank(player['display_name'], bucket)
        pl_stream, pl_stream_opp, pl_stream_date = pl_streamer_rank(player['display_name']) if bucket == 'SP' else ('—', None, None)
        model = model_row(player)
        arche = archetype_row(player)
        verdict, rationale = synthesize(player, pl_main, pl_main_date, pl_stream, pl_stream_date, model, arche)
        rows.append({
            'player': player, 'pl_main': pl_main, 'pl_main_date': pl_main_date,
            'pl_stream': pl_stream, 'pl_stream_date': pl_stream_date,
            'model': model, 'arche': arche, 'verdict': verdict, 'rationale': rationale,
        })
        if args.csv_out:
            csv_rows.append({
                'player_name': player['display_name'],
                'bucket': bucket,
                'pl_rank': pl_main if isinstance(pl_main, int) else None,
                'pl_rank_raw': pl_main,
                'model_rank': model.get('rank') if model.get('rank') != '—' else None,
                'model_proj': model.get('proj'),
                'model_rep_delta': model.get('rep_delta'),
                'model_recform': model.get('recform'),
                'arche_have': arche.get('have', False),
                'arche_overall': arche.get('overall') if arche.get('have') else None,
                'arche_label': arche.get('archetype') if arche.get('have') else None,
                'arche_cell': arche.get('cell') if arche.get('have') else None,
                'arche_traj': arche.get('traj_flag') if arche.get('have') else None,
                'arche_slope_3yr': arche.get('slope_3yr') if arche.get('have') else None,
                'arche_career_pct': arche.get('career_pct') if arche.get('have') else None,
                'arche_t1_fp': arche.get('t1_fp') if arche.get('have') else None,
                'arche_age': arche.get('age') if arche.get('have') else None,
                'arche_age_tier': arche.get('age_tier') if arche.get('have') else None,
                'arche_velo': arche.get('velo') if arche.get('have') else None,
                'arche_velo_tier': arche.get('velo_tier') if arche.get('have') else None,
                'verdict': verdict,
                'rationale': rationale,
            })
        else:
            print(format_card(player, pl_main, pl_main_date, pl_stream, pl_stream_date, model, arche, verdict, rationale))

    if args.csv_out:
        pd.DataFrame(csv_rows).to_csv(args.csv_out, index=False)
        print(f"Wrote {len(csv_rows)} rows to {args.csv_out}")
    elif len(rows) > 1:
        print(compare_table(rows))

if __name__ == '__main__':
    main()
