"""
/triangulate engine — combine PL rank + our model (rh3/rp3/rprs2) + archetype model
into one unified player profile.

Usage:
    python scripts/xfp/run_triangulate.py "Aaron Judge"
    python scripts/xfp/run_triangulate.py "Reid Detmers" "Ryan Weathers" "Ryne Nelson"
    python scripts/xfp/run_triangulate.py --bucket SP "Reid Detmers"

Thin CLI shell. Analytical logic lives in `scripts/xfp/lib/`.
Other skills should import from `scripts.xfp.lib.triangulate_core` directly.
"""

from __future__ import annotations
import argparse, io, os, sys
import pandas as pd

# Force UTF-8 for stdout on Windows so arrows / accents don't crash
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Make `scripts.xfp.lib.*` importable when this file is run as a script
# (python scripts/xfp/run_triangulate.py). External skills that already have
# the project root on sys.path get this for free.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.xfp.lib.bucket_dispatch import resolve_player
from scripts.xfp.lib.pl_cache import pl_rank, pl_streamer_rank, _warn_stale_caches
from scripts.xfp.lib.triangulate_core import (
    model_row, archetype_row, synthesize, apply_overrides,
)

# ---------- presentation layer (stays in the CLI) ----------

def format_card(player, pl_main, pl_main_date, pl_stream, pl_stream_date, model, arche, verdict, rationale):
    lines = []
    bucket = player['bucket']
    lines.append(f"\n## {player['display_name']} ({bucket}) — {verdict}\n")
    lines.append(f"*{rationale}*\n")

    pl_label = {'H': 'PL Top150', 'SP': 'PL Top100', 'RP': 'PL Closers'}[bucket]
    model_label = {'H': 'rh3', 'SP': 'rp3', 'RP': 'rprs2'}[bucket]
    lines.append("| Lens | Rank | Headline | Detail |")
    lines.append("|---|---|---|---|")
    pl_show = f"#{pl_main}" if isinstance(pl_main, int) else pl_main
    lines.append(f"| **{pl_label}** | {pl_show} | — | cache {pl_main_date or 'MISSING'} |")
    if bucket == 'SP' and pl_stream != '—':
        lines.append(f"| **PL Streamer ({pl_stream_date})** | {pl_stream} | vs {pl_stream_date or '?'} | — |")
    if model['rank'] != '—':
        proj = model['proj']
        proj_s = f"{proj:.2f} {model['proj_label']}" if proj is not None else '—'
        sig = f"signal={model['signal']}" if bucket == 'RP' else ''
        rep = f"rep_d={model['rep_delta']:+.2f}" if model['rep_delta'] is not None else ''
        recf = f"recform={model['recform']:+.3f}" if model.get('recform') is not None else ''
        extra = f" | {model.get('extra','')}"
        detail = ' '.join(s for s in (sig, rep, recf) if s) + extra
        lines.append(f"| **{model_label}** | #{model['rank']} | {proj_s} | {detail} |")
    else:
        lines.append(f"| **{model_label}** | — | not in projection file | — |")
    if arche.get('have'):
        rstr = ' / '.join(f"{k}={v}" for k, v in arche['ratings'].items())
        ar_h = f"OVERALL {arche['overall']} ({arche['archetype']} / {arche['cell']})"
        cp = arche.get('career_pct')
        cpstr = f", career-pct {cp*100:.0f}%" if cp is not None and pd.notna(cp) else ''
        sl = arche.get('slope_3yr')
        slstr = f", 3yr-slope {sl:+.1f}" if sl is not None and pd.notna(sl) else ''
        lines.append(f"| **Archetype** | — | {ar_h} | {rstr} | traj {arche['traj_flag']}{slstr}{cpstr} |")
        arc = ' → '.join(f"{y}:{a}({o})" for y, a, o in arche['arc'])
        lines.append(f"\n**Career arc:** {arc}")
        if arche.get('t1_fp') is not None and pd.notna(arche['t1_fp']):
            unit = {'SP': 'start', 'H': 'PA', 'RP': 'g'}[bucket]
            lines.append(f"\n**Archetype T+1 projection:** {arche['t1_fp']:.3f} fp/{unit}")
        if bucket == 'RP':
            roles = []
            if arche.get('closer'):   roles.append('CLOSER')
            if arche.get('high_lev'): roles.append('HIGH_LEVERAGE')
            if arche.get('fireman'):  roles.append('FIREMAN')
            lev = arche.get('leverage_tier')
            tagstr = ', '.join(roles) if roles else 'non-role'
            lines.append(f"\n**Role tags:** {tagstr} | leverage_tier={lev}")
        v = arche.get('velo'); vt = arche.get('velo_tier')
        if v is not None and pd.notna(v):
            lines.append(f"\n**Velo:** {v:.1f} mph [{vt}]")
    else:
        lines.append(f"| **Archetype** | — | NOT AVAILABLE | {arche.get('reason','')} |")
    return '\n'.join(lines)


def compare_table(rows):
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


def _verdict_matches(verdict: str, filters: list[str]) -> bool:
    if not filters:
        return True
    v = verdict.lower()
    return any(tok in v for tok in filters)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('names', nargs='*', help='Player names (or use --names-file)')
    ap.add_argument('--bucket', choices=['H', 'SP', 'RP'], default=None,
                    help='Force a position bucket (otherwise auto-detected)')
    ap.add_argument('--names-file', default=None, help='CSV with a player_name column (batch mode)')
    ap.add_argument('--csv-out', default=None, help='Write batch results to this CSV (instead of per-player cards)')
    ap.add_argument('--filter', default=None,
                    help='Comma-separated verdict substrings (case-insensitive). Only emit matching rows/cards.')
    ap.add_argument('--summary-only', action='store_true',
                    help='Interactive mode: suppress per-player cards, print only comparison table.')
    args = ap.parse_args()

    _warn_stale_caches()

    filters = []
    if args.filter:
        filters = [t.strip().lower() for t in args.filter.split(',') if t.strip()]

    input_df = None
    if args.names_file:
        input_df = pd.read_csv(args.names_file)
        name_list = input_df['player_name'].dropna().astype(str).tolist()
    else:
        name_list = args.names

    category_map = {}
    if input_df is not None and 'category' in input_df.columns:
        for _, row in input_df.iterrows():
            nm = row.get('player_name')
            if pd.notna(nm):
                category_map[str(nm)] = row.get('category')

    rows = []
    csv_rows = []
    for name in name_list:
        player = resolve_player(name, args.bucket)
        if not player:
            if args.csv_out:
                rec = {'player_name': name, 'bucket': '?', 'resolved': False}
                if category_map:
                    rec['category'] = category_map.get(name)
                csv_rows.append(rec)
            else:
                print(f"\n### {name} — NOT FOUND in projections or archetype panels.\n")
            continue
        bucket = player['bucket']
        model = model_row(player)
        m_rank_int = model.get('rank') if isinstance(model.get('rank'), int) else None
        pl_main, pl_main_date = pl_rank(player['display_name'], bucket, model_rank=m_rank_int)
        pl_stream, pl_stream_opp, pl_stream_date = pl_streamer_rank(player['display_name']) if bucket == 'SP' else ('—', None, None)
        arche = archetype_row(player)
        verdict, rationale = synthesize(player, pl_main, pl_main_date, pl_stream, pl_stream_date, model, arche)
        verdict, rationale, override_tag = apply_overrides(verdict, rationale, player, arche, model)

        if not _verdict_matches(verdict, filters):
            continue

        rows.append({
            'player': player, 'pl_main': pl_main, 'pl_main_date': pl_main_date,
            'pl_stream': pl_stream, 'pl_stream_date': pl_stream_date,
            'model': model, 'arche': arche, 'verdict': verdict, 'rationale': rationale,
            'override_tag': override_tag,
        })
        if args.csv_out:
            rec = {
                'player_name': player['display_name'],
                'bucket': bucket,
                'pl_rank': pl_main if isinstance(pl_main, int) else None,
                'pl_rank_raw': pl_main,
                'model_rank': model.get('rank') if model.get('rank') != '—' else None,
                'model_proj': model.get('proj'),
                'model_signal': model.get('signal'),
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
                'override_tag': override_tag,
            }
            if category_map:
                rec['category'] = category_map.get(name)
            csv_rows.append(rec)
        else:
            if not args.summary_only:
                print(format_card(player, pl_main, pl_main_date, pl_stream, pl_stream_date, model, arche, verdict, rationale))

    if args.csv_out:
        pd.DataFrame(csv_rows).to_csv(args.csv_out, index=False)
        print(f"Wrote {len(csv_rows)} rows to {args.csv_out}")
    elif len(rows) > 1:
        print(compare_table(rows))


if __name__ == '__main__':
    main()
