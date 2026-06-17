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

### 2. Cross-repo publish credential — already done ✅ (write-scoped deploy key)

The cloud job runs in `PLV_Clone` but publishes to the **separate** `xfp-model`
repo, which the default `GITHUB_TOKEN` can't reach. This is wired with an SSH
**deploy key** (set up 2026-06-16 via `gh` CLI — no action needed):

- `xfp-model` has a read-write deploy key titled **`plv-live-ci`**.
- `PLV_Clone` has the matching private key as the secret
  **`XFP_MODEL_DEPLOY_KEY`**, consumed by `live-matchup.yml`'s xfp-model
  checkout (`ssh-key:`).

Why a deploy key over a PAT: least-privilege (only `xfp-model`'s git, not the
whole account), **no expiry to rotate**, and it was creatable entirely from the
CLI (no browser / 2FA dance). To revoke: delete the `plv-live-ci` key from
`xfp-model` → Settings → Deploy keys and remove the secret. To regenerate:
`ssh-keygen -t ed25519`, `gh repo deploy-key add <pub> --allow-write -R
Kejjeh/xfp-model`, `gh secret set XFP_MODEL_DEPLOY_KEY -R Kejjeh/PLV_Clone < <priv>`.

### 3. Self-hosted runner — **you must install this** (for the daily job)

**Quick path** — open PowerShell **as Administrator** and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ci\install_self_hosted_runner.ps1
```

It downloads the latest runner into `C:\actions-runner`, fetches a registration
token via `gh` (nothing to copy/paste), and launches `config.cmd`. Answer the
prompts as the script header explains — the important ones are **"Run as
service: Y"** and **entering your own Windows account** for the service. Then
confirm the runner shows **Idle** under PLV_Clone → Settings → Actions →
Runners, and trigger *Daily full refresh* once (Actions → Run workflow) to
smoke-test.

**Manual path** (equivalent, if you prefer the GitHub UI): Settings → Actions →
Runners → New self-hosted runner → Windows/x64, then follow the shown commands.

Why the service must run as **you** (both paths):
- **Git credentials:** reuses the saved GitHub creds in Windows Credential
  Manager (the same ones the manual `git push` uses). `NETWORK SERVICE` has none.
- **Python + deps:** the service must see the same `python` you use by hand
  (with `pybaseball`/`lightgbm`/`scikit-learn` etc.). If you use a conda/venv,
  make that interpreter first on the **system** PATH the service inherits.

The **Diagnostics** step in `daily-refresh.yml` prints which `python`/`git` the
runner resolved — check it on the first run if anything misbehaves.

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
  unchanged). The cloud job sets `PLV_ROOT` to the runner workspace, builds the
  HTML into `data/outputs/`, then copies it into the checked-out `xfp-model`
  and pushes (build decoupled from the token-gated publish).
- The cloud job installs only light deps (`pandas numpy pyarrow requests
  espn-api`) and sets `PYTHONPATH=src:.` — it never does `pip install -e .`
  (which would drag in pybaseball/lightgbm/sklearn).
- The cloud job does **not** commit to `plv_clone` (avoids hourly commit
  noise); it only publishes the two HTML dashboards to `xfp-model`.
- The matchup builder falls back to canonical `rp3` if the `il_fixed` shim is
  >24h stale (never hard-fails), so a day-old shim won't break the cloud build.
- **Two writers to `xfp-model`:** both jobs push to the Pages repo (cloud =
  matchup/live during games; daily = full dashboard set), so each does
  `git fetch && git merge -X ours --no-edit && git push` before publishing —
  whichever ran most recently wins on the overlapping HTML and neither push is
  rejected. (Added 2026-06-16 after the first daily run's xfp-model push was
  rejected non-fast-forward because the cloud job had pushed in between.)
