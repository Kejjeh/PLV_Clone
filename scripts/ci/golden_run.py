"""golden_run.py — A/B output-equivalence verifier for behavior-preserving refactors.

Codifies the manual golden workflow used ~6x during the 2026-07-19 production
audit (docs/production_audit_2026-07-19.md): snapshot prod outputs, run the
pipelines on CURRENT code (phase A), apply the refactor, re-run (phase B), and
verify every output is identical — then ALWAYS restore the prod outputs, which
carry enrichment the raw pipeline run does not.

Data-coupled-golden lesson (tests/test_triangulate_golden.py): a golden capture
is only meaningful while its INPUTS are frozen. Phase A hashes every input;
phase B refuses to diff if any hash drifted — a drifted input means the A/B
diff measures the data refresh, not your refactor.

Usage:
  python scripts/ci/golden_run.py --target volume --phase A
  ... apply behavior-preserving edits ...
  python scripts/ci/golden_run.py --target volume --phase B

  # warm-skip artifacts predate the change? force a cold fit (models only):
  python scripts/ci/golden_run.py --target models --phase A --cold
  python scripts/ci/golden_run.py --target models --phase B --cold

  # after a crash mid --cold run:
  python scripts/ci/golden_run.py --restore

  # arbitrary pipeline:
  python scripts/ci/golden_run.py --target custom --phase A \
      --cmd "python -X utf8 scripts/xfp/build_sp_archetypes.py" \
      --outputs data/research/sp_ratings_master.csv \
      --inputs data/research/xfp_cache/sp_multiyr_2015_2025.csv

Exit codes: 0 = all outputs identical; 1 = diffs found / command failed;
2 = refusal (lock held, manifest missing, input drift, bad args).
"""
import argparse
import functools
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows-safe console (cp1252 chokes on the check/warn glyphs)
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass

# flush every print so parent progress interleaves correctly with child stdout
print = functools.partial(print, flush=True)

REPO = Path(__file__).resolve().parents[2]
OK, WARN = '✓', '⚠'

ROLLING = [
    'data/research/xfp_cache/rolling_hitters_2018_2026.csv',
    'data/research/xfp_cache/rolling_pitchers_2018_2026.csv',
    'data/research/xfp_cache/rolling_relievers_2018_2026.csv',
]

_ARCH_RES = 'data/research'
TARGETS = {
    'models': {
        'commands': [
            [sys.executable, '-X', 'utf8', 'scripts/xfp/xfp_rh3_pipeline.py'],
            [sys.executable, '-X', 'utf8', 'scripts/xfp/xfp_rp3_pipeline.py'],
            [sys.executable, '-X', 'utf8', 'scripts/xfp/xfp_rprs2_pipeline.py'],
        ],
        'outputs': [
            'data/outputs/xfp_rh3_projections.csv',
            'data/outputs/xfp_rp3_projections.csv',
            'data/outputs/xfp_rprs2_projections.csv',
        ],
        'inputs': ROLLING + ['data/research/xfp_cache/pitcher_counting_stats_2026.json'],
    },
    'volume': {
        'commands': [
            [sys.executable, '-X', 'utf8', 'scripts/xfp/xfp_volume_pipeline.py'],
            [sys.executable, '-X', 'utf8', 'scripts/xfp/xfp_sp_volume_pipeline.py'],
            [sys.executable, '-X', 'utf8', 'scripts/xfp/xfp_rp_volume_pipeline.py'],
        ],
        'outputs': [
            'data/outputs/xfp_volume_projections.csv',
            'data/outputs/xfp_sp_volume_projections.csv',
            'data/outputs/xfp_rp_volume_projections.csv',
        ],
        'inputs': list(ROLLING),
    },
    'archetypes': {
        'commands': [
            [sys.executable, '-X', 'utf8', 'scripts/xfp/build_sp_archetypes.py'],
            [sys.executable, '-X', 'utf8', 'scripts/xfp/build_hitter_archetypes.py'],
        ],
        'outputs': [
            f'{_ARCH_RES}/sp_ratings_master.csv',
            f'{_ARCH_RES}/sp_archetype_career_panel.parquet',
            f'{_ARCH_RES}/sp_archetype_definitions.json',
            f'{_ARCH_RES}/sp_archetype_stickiness.json',
            f'{_ARCH_RES}/sp_decline_baselines.json',
            f'{_ARCH_RES}/sp_boundary_validation.json',
            f'{_ARCH_RES}/hitter_ratings_master.csv',
            f'{_ARCH_RES}/hitter_archetype_career_panel.parquet',
            f'{_ARCH_RES}/hitter_archetype_definitions.json',
            f'{_ARCH_RES}/hitter_archetype_stickiness.json',
            f'{_ARCH_RES}/hitter_decline_baselines.json',
            f'{_ARCH_RES}/hitter_boundary_validation.json',
        ],
        'inputs': [
            'data/research/xfp_cache/sp_multiyr_2015_2025.csv',
            'data/research/xfp_cache/hitters_multiyr_2015_2026.csv',
            'data/research/xfp_cache/milb_pitcher_ages.csv',
            'data/research/xfp_cache/park_factors_2018_2026.csv',
            'data/research/xfp_cache/hitter_lineup_features_2018_2026.csv',
            'data/outputs/sp_age_career.csv',
            'data/outputs/hitter_age_career.csv',
        ],
    },
}

COLD_PKLS = [
    'data/models/xfp_rh3_pipeline.pkl',
    'data/models/xfp_rp3_pipeline.pkl',
    'data/models/xfp_rprs2_pipeline.pkl',
]
STASH_ROOT = REPO / 'data/models/.golden_stash'


def scratch_root() -> Path:
    env = os.environ.get('GOLDEN_RUN_DIR')
    return Path(env) if env else REPO / 'data/research/.golden_run'


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def run_commands(commands):
    env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
    for argv in commands:
        print(f'\n>>> {subprocess.list2cmdline(argv)}')
        t0 = time.time()
        rc = subprocess.run(argv, cwd=str(REPO), env=env).returncode
        print(f'    ({time.time() - t0:.1f}s, exit {rc})')
        if rc != 0:
            raise RuntimeError(f'command failed (exit {rc}): {subprocess.list2cmdline(argv)}')


def rel_dest(base: Path, out_rel: str) -> Path:
    """Destination for an output copy, preserving repo-relative structure."""
    p = Path(out_rel)
    if p.is_absolute():
        try:
            p = p.relative_to(REPO)
        except ValueError:
            p = Path(p.name)
    return base / p


def copy_outputs(outputs, dest_base: Path, label: str):
    copied = []
    for out in outputs:
        src = REPO / out
        if not src.exists():
            print(f'{WARN} {label}: missing (not copied): {out}')
            continue
        dst = rel_dest(dest_base, out)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(out)
    return copied


def restore_prod(prod_dir: Path, outputs):
    restored = 0
    for out in outputs:
        src = rel_dest(prod_dir, out)
        if src.exists():
            dst = REPO / out
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            restored += 1
    print(f'{OK} restored {restored} prod output file(s) over the live copies '
          f'(prod outputs carry enrichment — never leave raw pipeline output live).')


def stash_models_cold():
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    stash = STASH_ROOT / ts
    stash.mkdir(parents=True, exist_ok=True)
    stashed = []
    for rel in COLD_PKLS:
        src = REPO / rel
        if not src.exists():
            print(f'{WARN} --cold: {rel} not present (already cold)')
            continue
        shutil.copy2(src, stash / src.name)   # COPY first, never move
        src.unlink()                          # then delete so pipelines cold-fit
        stashed.append(rel)
    print(f'{OK} --cold: stashed {len(stashed)} model pkl(s) to {stash}')
    return stash, stashed


def unstash_models(stash: Path, stashed):
    for rel in stashed:
        src = stash / Path(rel).name
        if src.exists():
            shutil.copy2(src, REPO / rel)
    try:
        shutil.rmtree(stash)
        if STASH_ROOT.exists() and not any(STASH_ROOT.iterdir()):
            STASH_ROOT.rmdir()
    except OSError as e:
        print(f'{WARN} could not remove stash dir {stash}: {e}')
    print(f'{OK} --cold: restored {len(stashed)} model pkl(s) from stash.')


def cmd_restore():
    """Recover after a crash: restore the newest .golden_stash/<ts>/ pkls."""
    if not STASH_ROOT.exists() or not any(STASH_ROOT.iterdir()):
        print('No .golden_stash found — nothing to restore.')
        return 0
    stash = sorted(STASH_ROOT.iterdir())[-1]
    n = 0
    for f in stash.iterdir():
        shutil.copy2(f, REPO / 'data/models' / f.name)
        n += 1
    shutil.rmtree(stash)
    if not any(STASH_ROOT.iterdir()):
        STASH_ROOT.rmdir()
    print(f'{OK} restored {n} pkl(s) from {stash} and removed the stash.')
    lock = scratch_root() / 'LOCK'
    if lock.exists():
        lock.unlink()
        print(f'{OK} removed stale lockfile {lock}')
    return 0


def diff_csv(a: Path, b: Path) -> str:
    import pandas as pd
    try:
        da, db = pd.read_csv(a), pd.read_csv(b)
    except Exception as e:
        return f'DIFFERENT (unreadable as CSV: {e})'
    try:
        pd.testing.assert_frame_equal(da, db)
        return 'EQUIVALENT (frames equal; byte diff is float formatting only)'
    except AssertionError as e:
        if list(da.columns) != list(db.columns):
            only_a = [c for c in da.columns if c not in db.columns]
            only_b = [c for c in db.columns if c not in da.columns]
            return f'DIFFERENT (columns: only-A={only_a} only-B={only_b})'
        if len(da) != len(db):
            return f'DIFFERENT (row count {len(da)} vs {len(db)})'
        bad = []
        for c in da.columns:
            try:
                pd.testing.assert_series_equal(da[c], db[c], check_names=False)
            except AssertionError:
                bad.append(c)
            if len(bad) >= 5:
                break
        detail = f'first differing columns: {bad}' if bad else str(e).splitlines()[0]
        return f'DIFFERENT ({detail})'


def diff_parquet(a: Path, b: Path) -> str:
    import pandas as pd
    try:
        da, db = pd.read_parquet(a), pd.read_parquet(b)
    except Exception as e:
        return f'DIFFERENT (unreadable as parquet: {e})'
    if da.equals(db):
        return 'EQUIVALENT (DataFrames equal; byte diff is encoding only)'
    bad = [c for c in da.columns if c not in db.columns or not da[c].equals(db[c])][:5]
    return f'DIFFERENT (first differing columns: {bad})'


def diff_output(a: Path, b: Path) -> str:
    """Return 'IDENTICAL' / 'EQUIVALENT ...' / 'DIFFERENT ...' / 'MISSING ...'."""
    if not a.exists():
        return 'MISSING (no phase-A copy)'
    if not b.exists():
        return 'MISSING (phase-B run produced no file)'
    if a.stat().st_size == b.stat().st_size and md5_file(a) == md5_file(b):
        return 'IDENTICAL'
    suf = a.suffix.lower()
    if suf == '.csv':
        return diff_csv(a, b)
    if suf == '.parquet':
        return diff_parquet(a, b)
    if suf == '.json':
        try:
            with open(a, encoding='utf-8') as fa, open(b, encoding='utf-8') as fb:
                if json.load(fa) == json.load(fb):
                    return 'EQUIVALENT (JSON payload equal; byte diff is formatting only)'
        except Exception:
            pass
        return 'DIFFERENT (json bytes + payload differ)'
    return 'DIFFERENT (bytes differ)'


def resolve_target(args):
    if args.target == 'custom':
        if not args.cmd or not args.outputs:
            print('ERROR: --target custom requires at least one --cmd and --outputs.')
            sys.exit(2)
        commands = [shlex.split(c) for c in args.cmd]
        spec = {'commands': commands, 'outputs': list(args.outputs),
                'inputs': list(args.inputs or [])}
        if not spec['inputs']:
            print(f'{WARN} custom target with no --inputs: phase B cannot detect '
                  f'data drift — the A/B diff is only trustworthy if you KNOW the '
                  f'inputs were frozen.')
        return spec
    spec = TARGETS[args.target]
    return {'commands': [list(c) for c in spec['commands']],
            'outputs': list(spec['outputs']), 'inputs': list(spec['inputs'])}


def phase_a(args, spec, tdir: Path):
    prod_dir, a_dir = tdir / 'prod', tdir / 'A'
    for d in (prod_dir, a_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    print(f'[A] snapshotting prod outputs -> {prod_dir}')
    prod_copied = copy_outputs(spec['outputs'], prod_dir, 'prod')

    print('[A] hashing inputs (md5)')
    input_hashes = {}
    for rel in spec['inputs']:
        p = REPO / rel
        if not p.exists():
            print(f'ERROR: input missing: {rel} — refusing to capture a golden '
                  f'against an absent input.')
            sys.exit(2)
        input_hashes[rel] = md5_file(p)
        print(f'    {input_hashes[rel]}  {rel}')

    stash = None
    try:
        if args.cold:
            stash = stash_models_cold()
        print('[A] running commands on CURRENT code')
        run_commands(spec['commands'])
        print(f'[A] copying outputs -> {a_dir}')
        a_copied = copy_outputs(spec['outputs'], a_dir, 'A')
        missing = [o for o in spec['outputs'] if o not in a_copied]
        if missing:
            print(f'ERROR: phase-A run did not produce: {missing}')
            sys.exit(1)
    finally:
        if stash is not None:
            unstash_models(*stash)
        restore_prod(prod_dir, prod_copied)

    manifest = {
        'target': args.target,
        'commands': [subprocess.list2cmdline(c) for c in spec['commands']],
        'outputs': spec['outputs'],
        'inputs': input_hashes,
        'prod_copied': prod_copied,
        'cold': bool(args.cold),
        'captured_at': datetime.now().isoformat(timespec='seconds'),
    }
    with open(tdir / 'manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    print(f'\n{OK} phase A complete. Apply your edits, then run --phase B '
          f'(same --target{" --cold" if args.cold else ""}).')
    return 0


def phase_b(args, spec, tdir: Path):
    prod_dir, a_dir = tdir / 'prod', tdir / 'A'
    mpath = tdir / 'manifest.json'
    if not mpath.exists():
        print(f'ERROR: no manifest at {mpath} — run --phase A first for '
              f'--target {args.target}. Refusing to diff against nothing.')
        sys.exit(2)
    with open(mpath, encoding='utf-8') as f:
        manifest = json.load(f)
    if manifest.get('target') != args.target:
        print(f'ERROR: manifest was captured for target {manifest.get("target")!r}, '
              f'not {args.target!r}.')
        sys.exit(2)
    if bool(manifest.get('cold')) != bool(args.cold):
        print(f'{WARN} phase A cold={manifest.get("cold")} but phase B '
              f'cold={bool(args.cold)} — warm-vs-cold diffs are meaningless '
              f'(warm-skip artifacts predate the change). Use matching flags.')

    print('[B] verifying input hashes against the phase-A manifest')
    drifted = []
    for rel, want in manifest['inputs'].items():
        p = REPO / rel
        got = md5_file(p) if p.exists() else '<missing>'
        if got != want:
            drifted.append((rel, want, got))
    if drifted:
        print('ERROR: INPUT DRIFT — the A/B diff would measure a data refresh, '
              'not your refactor (the data-coupled-golden lesson). Drifted:')
        for rel, want, got in drifted:
            print(f'    {rel}\n        A: {want}\n        B: {got}')
        print('Re-run --phase A on current code to recapture, then --phase B.')
        sys.exit(2)
    print(f'{OK} all {len(manifest["inputs"])} input hashes match phase A.')

    stash, run_err, results = None, None, {}
    try:
        if args.cold:
            stash = stash_models_cold()
        print('[B] running commands on EDITED code')
        run_commands(spec['commands'])
        print('\n[B] diffing outputs vs phase A')
        for out in spec['outputs']:
            verdict = diff_output(rel_dest(a_dir, out), REPO / out)
            mark = OK if verdict == 'IDENTICAL' else WARN
            print(f'  {mark} {out}: {verdict}')
            results[out] = verdict
    except RuntimeError as e:
        run_err = str(e)
        print(f'ERROR: {run_err}')
    finally:
        if stash is not None:
            unstash_models(*stash)
        restore_prod(prod_dir, manifest.get('prod_copied', spec['outputs']))

    if run_err:
        return 1
    n_id = sum(1 for v in results.values() if v == 'IDENTICAL')
    print(f'\n[B] verdict: {n_id}/{len(results)} outputs byte-IDENTICAL.')
    if n_id == len(results):
        print(f'{OK} refactor is output-equivalent. Safe to commit.')
        return 0
    print(f'{WARN} NOT byte-identical. EQUIVALENT = pandas-equal (formatting-only '
          f'drift — inspect why serialization changed); DIFFERENT = behavior '
          f'changed. If outputs SHOULD change, this is /validate-feature '
          f'territory, not a golden run.')
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--target', choices=['models', 'volume', 'archetypes', 'custom'])
    ap.add_argument('--phase', choices=['A', 'B'])
    ap.add_argument('--restore', action='store_true',
                    help='crash recovery: restore newest data/models/.golden_stash/<ts>/')
    ap.add_argument('--cold', action='store_true',
                    help='models target: stash+delete the 3 model pkls so pipelines cold-fit')
    ap.add_argument('--force', action='store_true', help='override a held lockfile')
    ap.add_argument('--cmd', action='append', help='custom target: command (repeatable)')
    ap.add_argument('--outputs', nargs='+', help='custom target: output paths (repo-relative)')
    ap.add_argument('--inputs', nargs='+', help='custom target: input paths to hash-freeze')
    args = ap.parse_args()

    if args.restore:
        sys.exit(cmd_restore())
    if not args.target or not args.phase:
        ap.error('--target and --phase are required (or --restore)')
    if args.cold and args.target != 'models':
        ap.error('--cold only applies to --target models (the 3 warm-skip pkls)')

    spec = resolve_target(args)
    root = scratch_root()
    tdir = root / args.target
    tdir.mkdir(parents=True, exist_ok=True)

    lock = root / 'LOCK'
    if lock.exists() and not args.force:
        print(f'ERROR: lockfile present: {lock}\n'
              f'  ({lock.read_text(encoding="utf-8").strip()})\n'
              f'Another golden run — or a concurrent refresh_dashboards.py — would '
              f'corrupt BOTH phases (outputs rewritten mid-diff, inputs drifting '
              f'under the hashes). If the previous run crashed, check --restore, '
              f'then re-run with --force.')
        sys.exit(2)
    lock.write_text(f'pid={os.getpid()} phase={args.phase} target={args.target} '
                    f'started={datetime.now().isoformat(timespec="seconds")}\n',
                    encoding='utf-8')
    try:
        rc = phase_a(args, spec, tdir) if args.phase == 'A' else phase_b(args, spec, tdir)
    finally:
        if lock.exists():
            lock.unlink()
    sys.exit(rc)


if __name__ == '__main__':
    main()
