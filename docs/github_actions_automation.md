# Dashboard automation — GitHub Actions

Two scheduled workflows keep the BrownU dashboards current. Added 2026-06-16.

| Workflow | File | Runner | When | What it does |
|---|---|---|---|---|
| **Daily full refresh** | `.github/workflows/daily-refresh.yml` | **self-hosted** (your PC) | 11:00 UTC daily (07:00 ET EDT) | Runs `refresh_dashboards.py` — statcast pull, **rh3/rp3/rprs2 retrain**, all dashboards, publishes `xfp-model`, then commits the regenerated `data/` back to `plv_clone`. |
| **Live matchup** | `.github/workflows/live-matchup.yml` | cloud (`ubuntu-latest`) | hourly, **only while MLB games are live** | Rebuilds `matchup.html` + `live_dashboard.html` from the committed model CSVs + live ESPN/MLB, publishes to `xfp-model`. |

The daily job is the only one that moves the projection numbers. The live job
layers fresh rosters/scores/win-prob on top of whatever the daily job last
committed.

---

## One-time setup

### 1. ESPN secrets — already done ✅

`ESPN_LEAGUE_ID`, `ESPN_S2`, `ESPN_SWID`, `ESPN_YEAR` already exist as repo
secrets (the existing `build-report.yml` uses them and runs green), so the
cloud live job authenticates to ESPN out of the box.

### 2. `XFP_MODEL_TOKEN` secret — **you must add this** (for the cloud live job)

The cloud job runs in `PLV_Clone` but publishes to the **separate** `xfp-model`
repo. The default `GITHUB_TOKEN` can't reach another repo, so it needs a token:

1. GitHub → your avatar → **Settings → Developer settings → Personal access
   tokens → Fine-grained tokens → Generate new token**.
2. **Resource owner:** `Kejjeh`. **Repository access:** *Only select
   repositories* → `xfp-model`.
3. **Permissions → Repository permissions → Contents: Read and write.**
4. Generate, copy the token.
5. In **`PLV_Clone` → Settings → Secrets and variables → Actions → New
   repository secret**: name `XFP_MODEL_TOKEN`, paste the value.

Set a calendar reminder to rotate it before it expires (fine-grained tokens
max out at ~1 year). If it lapses, the live job's publish step fails but
nothing else breaks.

> Alternative if you'd rather not manage a PAT: add a **deploy key** to
> `xfp-model` and switch the `live-matchup.yml` checkout to SSH. The PAT is
> simpler for a solo setup.

### 3. Self-hosted runner — **you must install this** (for the daily job)

1. **`PLV_Clone` → Settings → Actions → Runners → New self-hosted runner →
   Windows / x64.**
2. Run the download + `./config.cmd` commands GitHub shows (they embed a
   one-time registration token). Accept the **default labels** — the auto
   labels `self-hosted`, `Windows`, `X64` are what `daily-refresh.yml` targets.
3. When prompted **"Run as service"**, choose **Yes**, and install it **under
   your own Windows user account** (not `LocalSystem`). This is what makes the
   git push and your Python "just work":
   - **Git credentials:** running as you reuses the saved GitHub credentials
     in Windows Credential Manager (the same ones the manual `git push` uses).
   - **Python + deps:** the service must see the same `python` you use by hand
     (with `pybaseball`, `lightgbm`, `scikit-learn`, etc. installed). If you
     use a conda/venv, install/run the runner from inside that activated
     environment, or make sure that interpreter is first on the **system**
     PATH the service inherits.
4. Confirm the runner shows **Idle** (green) under Settings → Actions → Runners.

The **Diagnostics** step in the daily workflow prints which `python` and `git`
the runner resolves — check it on the first run if anything misbehaves.

---

## Game-gating ("start when games start, stop when they end")

`scripts/xfp/ci_games_live.py` asks the MLB Stats API whether any game is
currently `Live` (checking yesterday+today ET, so late west-coast games that
cross midnight UTC still count). The workflow's cheap `gate` job runs every
tick; the heavier `publish` job runs **only** when the gate returns
`live=true`. When the last game goes Final, the gate returns false and nothing
rebuilds — so it naturally stops for the night.

- The cron window (`16:00–23:00` and `00:00–06:00` UTC ≈ noon–2am ET) is just
  the *polling* window. The gate is the real switch, so empty ticks cost only
  the ~30-second gate job.
- **Fail-open:** if the MLB API errors, the gate returns `live=true` so the
  live dashboard never silently freezes during game hours.

---

## Testing / operating

- **Run either job on demand:** Actions tab → pick the workflow → **Run
  workflow** (`workflow_dispatch`). The live job has a **force** input to
  rebuild even when no games are live (useful for a smoke test).
- **Local gate check:** `python scripts/xfp/ci_games_live.py`.
- Scheduled runs only fire while the runner/cloud is reachable. A missed
  self-hosted run queues (~24h) and runs when the PC is back. GitHub disables
  *scheduled* workflows after 60 days of zero repo activity — the daily auto
  commit keeps the repo active.

## Notes / gotchas

- The builders are now path-portable via `PLV_ROOT` / `PLV_XFP_DOCS` env vars
  (default to the local Windows paths when unset, so manual runs are
  unchanged). The cloud job sets them to the runner workspace + the checked-out
  `xfp-model`.
- The cloud job installs only light deps (`pandas numpy pyarrow requests
  espn-api`) and sets `PYTHONPATH=src:.` — it never does `pip install -e .`
  (which would drag in pybaseball/lightgbm/sklearn).
- The cloud job does **not** commit to `plv_clone` (avoids hourly commit
  noise); it only publishes the two HTML dashboards to `xfp-model`.
- The matchup builder falls back to canonical `rp3` if the `il_fixed` shim is
  >24h stale (never hard-fails), so a day-old shim won't break the cloud build.
