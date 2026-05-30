"""Snapshot + delta tracking for triangulate batch outputs."""
from __future__ import annotations
import os
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
