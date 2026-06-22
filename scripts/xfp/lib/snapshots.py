"""Snapshot + delta tracking for triangulate batch outputs."""
from __future__ import annotations
import json
import os
import re
from collections import Counter
from datetime import date
import pandas as pd

SNAPSHOT_DIR = 'data/research/triangulate_universe/snapshots'
DIFF_DIR = 'data/research/triangulate_universe'


def write_snapshot(df: pd.DataFrame, label: str) -> str:
    """Save a dated copy of `df` and return the path written."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    today = date.today().isoformat()
    safe_label = label.replace('/', '_').replace(' ', '_')
    path = os.path.join(SNAPSHOT_DIR, f"triangulate_{safe_label}_{today}.csv")
    df.to_csv(path, index=False)
    return path


# ── Run registry: a sibling .json manifest next to every --snapshot CSV ──────────
#
# Determinism note: scripts cannot call now()/Date.now() to mint an id at runtime
# (a fresh wall-clock read makes the same logical run irreproducible). The run_id is
# always DERIVED — from the snapshot CSV's mtime, or an explicit caller-supplied id.

def _value_counts(df: pd.DataFrame, col: str) -> dict:
    if col not in df.columns:
        return {}
    s = df[col].dropna()
    return {str(k): int(v) for k, v in Counter(s.astype(str)).items()}


def derive_run_id(snapshot_csv_path: str, explicit: str | None = None) -> str:
    """Return a deterministic run_id 'YYYYMMDD-HHMMSS'. Prefers an explicit id;
    otherwise derives it from the snapshot file's modification time (a stable
    property of the produced artifact, not a fresh wall-clock read)."""
    if explicit:
        return str(explicit)
    try:
        import time as _time
        ts = os.path.getmtime(snapshot_csv_path)
        return _time.strftime('%Y%m%d-%H%M%S', _time.localtime(ts))
    except Exception:
        # Fall back to the date encoded in the snapshot filename + zero clock.
        m = re.search(r'(\d{4})-(\d{2})-(\d{2})', os.path.basename(snapshot_csv_path))
        if m:
            return f"{m.group(1)}{m.group(2)}{m.group(3)}-000000"
        return "00000000-000000"


def write_run_manifest(df: pd.DataFrame, label: str, snapshot_csv_path: str,
                       run_id: str | None = None) -> str:
    """Emit a sibling .json manifest next to the snapshot CSV describing the run:
    run_id, label, timestamp, player_count, distributions (bucket / verdict /
    position_group), categories_found. Returns the manifest path."""
    rid = derive_run_id(snapshot_csv_path, run_id)
    # timestamp: ISO form of the same derived id (no fresh now()).
    try:
        iso_ts = (f"{rid[:4]}-{rid[4:6]}-{rid[6:8]}T{rid[9:11]}:{rid[11:13]}:{rid[13:15]}"
                  if len(rid) >= 15 and rid[8] == '-' else rid)
    except Exception:
        iso_ts = rid
    verdict_col = 'verdict_top' if 'verdict_top' in df.columns else 'verdict'
    categories = sorted(df['category'].dropna().astype(str).unique().tolist()) \
        if 'category' in df.columns else []
    manifest = {
        'run_id': rid,
        'label': label,
        'timestamp': iso_ts,
        'player_count': int(len(df)),
        'bucket_distribution': _value_counts(df, 'bucket'),
        'verdict_distribution': _value_counts(df, verdict_col),
        'position_group_distribution': _value_counts(df, 'position_group'),
        'category_distribution': _value_counts(df, 'category'),
        'owner_team_distribution': _value_counts(df, 'owner_team'),
        'categories_found': categories,
        'snapshot_csv': os.path.basename(snapshot_csv_path),
    }
    manifest_path = os.path.splitext(snapshot_csv_path)[0] + '.json'
    tmp = manifest_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, default=str)
    os.replace(tmp, manifest_path)
    return manifest_path


def list_runs() -> list[dict]:
    """Return all run manifests under SNAPSHOT_DIR, sorted by run_id ascending."""
    out = []
    if not os.path.isdir(SNAPSHOT_DIR):
        return out
    for fn in os.listdir(SNAPSHOT_DIR):
        if not fn.endswith('.json'):
            continue
        path = os.path.join(SNAPSHOT_DIR, fn)
        try:
            with open(path, encoding='utf-8') as f:
                m = json.load(f)
            if 'run_id' in m:
                m['_manifest'] = fn
                out.append(m)
        except Exception:
            continue
    return sorted(out, key=lambda m: str(m.get('run_id', '')))


def format_runs(runs: list[dict]) -> str:
    """Render the run manifests as a compact dated, sorted table for stdout."""
    if not runs:
        return "No triangulate run manifests found under " + SNAPSHOT_DIR
    lines = [f"# triangulate run registry ({len(runs)} runs)", "",
             "| run_id | label | players | buckets | categories |",
             "|---|---|---|---|---|"]
    for m in runs:
        buckets = m.get('bucket_distribution') or {}
        b_s = ' '.join(f"{k}:{v}" for k, v in sorted(buckets.items())) or '—'
        cats = ','.join(m.get('categories_found') or []) or '—'
        lines.append(f"| {m.get('run_id')} | {m.get('label','')} | "
                     f"{m.get('player_count','?')} | {b_s} | {cats} |")
    return "\n".join(lines)


def _key_col(df: pd.DataFrame) -> str:
    return 'player_name' if 'player_name' in df.columns else df.columns[0]


def compute_diff(prior_csv: str, current_csv: str) -> str:
    """Return a markdown report describing differences between two snapshots."""
    prior = pd.read_csv(prior_csv)
    current = pd.read_csv(current_csv)
    pk = _key_col(prior)
    ck = _key_col(current)

    prior_idx = {str(r[pk]): r for _, r in prior.iterrows()}
    cur_idx = {str(r[ck]): r for _, r in current.iterrows()}

    prior_names = set(prior_idx.keys())
    cur_names = set(cur_idx.keys())

    new_players = sorted(cur_names - prior_names)
    dropped = sorted(prior_names - cur_names)
    both = prior_names & cur_names

    verdict_changes = []
    override_changes = []
    for nm in sorted(both):
        po = prior_idx[nm]
        co = cur_idx[nm]
        pv = str(po.get('verdict', '')) if 'verdict' in po else ''
        cv = str(co.get('verdict', '')) if 'verdict' in co else ''
        if pv != cv:
            verdict_changes.append((nm, pv, cv, str(co.get('rationale', ''))))
        ptag = str(po.get('override_tag', '')) if 'override_tag' in po else ''
        ctag = str(co.get('override_tag', '')) if 'override_tag' in co else ''
        # Treat nan/'' as equal
        if (ptag or '') != (ctag or '') and not (ptag in ('nan', '') and ctag in ('nan', '')):
            override_changes.append((nm, ptag, ctag))

    today = date.today().isoformat()
    lines = [f"# triangulate diff — {today}", ""]
    lines.append(f"- Prior:   `{prior_csv}` ({len(prior_idx)} players)")
    lines.append(f"- Current: `{current_csv}` ({len(cur_idx)} players)")
    lines.append("")

    if not (new_players or dropped or verdict_changes or override_changes):
        lines.append("**No verdict changes.** Universe identical.")
    else:
        lines.append(f"## Verdict changes ({len(verdict_changes)})")
        if verdict_changes:
            lines.append("")
            lines.append("| Player | Prior verdict | New verdict | Rationale |")
            lines.append("|---|---|---|---|")
            for nm, pv, cv, rat in verdict_changes:
                rat_short = (rat[:120] + '…') if len(rat) > 120 else rat
                lines.append(f"| {nm} | {pv} | {cv} | {rat_short} |")
        else:
            lines.append("_None._")
        lines.append("")
        lines.append(f"## Override flips ({len(override_changes)})")
        if override_changes:
            lines.append("")
            lines.append("| Player | Prior override | New override |")
            lines.append("|---|---|---|")
            for nm, pt, ct in override_changes:
                lines.append(f"| {nm} | {pt or '—'} | {ct or '—'} |")
        else:
            lines.append("_None._")
        lines.append("")
        lines.append(f"## New players ({len(new_players)})")
        if new_players:
            lines.append(", ".join(new_players[:50]) + (" …" if len(new_players) > 50 else ""))
        else:
            lines.append("_None._")
        lines.append("")
        lines.append(f"## Dropped players ({len(dropped)})")
        if dropped:
            lines.append(", ".join(dropped[:50]) + (" …" if len(dropped) > 50 else ""))
        else:
            lines.append("_None._")

    return "\n".join(lines)


def write_diff(prior_csv: str, current_csv: str) -> tuple[str, str]:
    """Compute diff, write to DIFF_DIR, return (path, report_text)."""
    os.makedirs(DIFF_DIR, exist_ok=True)
    report = compute_diff(prior_csv, current_csv)
    today = date.today().isoformat()
    path = os.path.join(DIFF_DIR, f"diff_{today}.md")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(report)
    return path, report


def truncate_report_for_stdout(report: str, max_changes: int = 20) -> str:
    """Truncate the verdict-change table to top N rows for terminal display."""
    lines = report.splitlines()
    out = []
    in_verdict_table = False
    rows_seen = 0
    for ln in lines:
        if ln.startswith('## Verdict changes'):
            in_verdict_table = True
            out.append(ln)
            continue
        if in_verdict_table and ln.startswith('## '):
            in_verdict_table = False
            out.append(ln)
            continue
        if in_verdict_table and ln.startswith('| ') and not ln.startswith('| Player') and not ln.startswith('|---'):
            rows_seen += 1
            if rows_seen > max_changes:
                if rows_seen == max_changes + 1:
                    out.append(f"| … | _truncated_ | | (top {max_changes} shown) |")
                continue
        out.append(ln)
    return "\n".join(out)
