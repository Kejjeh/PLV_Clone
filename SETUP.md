# Setup — plv_clone

Fantasy baseball model + tooling for the BrownU league. Windows / Python **3.13**
(lockfile generated on 3.13.12, 2026-07-04).

## Install

```bash
git clone <plv_clone>            # this repo
git clone <xfp-model> xfp-model  # sibling repo (GitHub Pages dashboards) at ./xfp-model/
pip install -r requirements.lock # full pin of the working environment
```

Key top-level deps: pandas, numpy, scikit-learn, pybaseball, espn-api, joblib,
requests. ESPN credentials go in `.env` (see `app/espn_connector.py`).

Gitignored data caches (`data/research/xfp_cache/*.csv`, `data/outputs/*.parquet`)
must be bootstrapped on a new machine — run `scripts/xfp/refresh_xfp_statcast.py`
per training year, then a full refresh.

## The two daily commands

```bash
# 1. Daily refresh — pulls statcast, rebuilds all models, regenerates
#    dashboards, commits+pushes xfp-model. Once per day.
python scripts/xfp/refresh_dashboards.py

# 2. Tests — always via the token-saving summarizer, never raw pytest
#    (full log cached to .cache/test-logs/<ts>.log)
python scripts/ci/run_summary.py -- python -m pytest
```

See `CLAUDE.md` for league rules, validated models, skills, and gotchas.
