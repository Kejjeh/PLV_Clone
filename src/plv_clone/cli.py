"""
PLV Clone — command-line interface.

Entry point: `plv` (configured in pyproject.toml).

Commands:
    plv pull-data         Pull Statcast data for a date range.
    plv build-features    Build the feature-engineered pitch dataset.
    plv train-plv         Train all PLV sub-models.
    plv score-plv         Score a season's pitches and write PLV columns.
    plv build-leaderboards Build and export pitcher leaderboards.

NOTE: All outputs are clearly labelled as an unofficial public-data clone.
      This project does not claim parity with official Pitcher List PLV.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import typer

from plv_clone.utils.logging import configure_logging, get_logger
from plv_clone.league_config import SEASON_YEAR

app = typer.Typer(
    name="plv",
    help=(
        "PLV Clone — unofficial public-data clone of PLV and Process+ metrics.\n\n"
        "DISCLAIMER: Outputs are NOT official Pitcher List metrics. "
        "Built from public Statcast data only."
    ),
    add_completion=False,
)

configure_logging()
logger = get_logger(__name__)


@app.command(name="pull-data")
def pull_data(
    start: str = typer.Option("2021-04-01", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option("2023-11-01", help="End date (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", help="Re-pull even if cached"),
    reconcile_days: int = typer.Option(
        0,
        "--reconcile-days",
        help=(
            "Re-pull the most recent N days even if the manifest marks them complete. "
            "Use 7–14 to catch upstream Baseball Savant corrections. "
            "0 = disabled (default)."
        ),
    ),
) -> None:
    """Pull pitch-level Statcast data and store as year-partitioned Parquet."""
    from plv_clone.config import get_config
    from plv_clone.data.ingest_statcast import pull_statcast_range

    cfg = get_config()
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)

    typer.echo(f"Pulling Statcast data: {start_date} to {end_date}")
    if reconcile_days:
        typer.echo(f"Reconciliation mode: re-pulling last {reconcile_days} days.")
    df = pull_statcast_range(
        start_date=start_date,
        end_date=end_date,
        raw_dir=cfg.raw_data_dir,
        chunk_days=cfg.statcast_chunk_days,
        force_refresh=force,
        reconcile_days=reconcile_days if reconcile_days > 0 else None,
    )
    typer.echo(f"Done. {len(df):,} pitches available for {start_date} to {end_date}.")


@app.command(name="build-features")
def build_features(
    start: str = typer.Option("2021-04-01", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option("2023-11-01", help="End date (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", help="Re-pull raw data"),
) -> None:
    """Clean and feature-engineer the pitch dataset, writing Parquet partitions."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.build_pitch_dataset import run

    cfg = get_config()
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)

    typer.echo(f"Building features: {start_date} to {end_date}")
    out_dir = run(start_date=start_date, end_date=end_date, config=cfg, force_refresh=force)
    typer.echo(f"Features written to: {out_dir}")


@app.command(name="train-plv")
def train_plv() -> None:
    """Train all PLV sub-models (SwingModel, CalledStrikeModel, ContactModel, FoulModel, BattedBallValueModel)."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.train_plv import run

    cfg = get_config()
    typer.echo("Training PLV sub-models …")
    plv_model = run(config=cfg)
    typer.echo(f"PLV model saved to: {cfg.models_dir}")
    typer.echo(
        f"Scaling params: avg={plv_model.scaling_params.get('target_avg', 5.0):.1f} "
        f"(population mean={plv_model.scaling_params.get('mean', 0.0):.4f})"
    )


@app.command(name="score-plv")
def score_plv(
    year: int = typer.Argument(..., help="Season year to score (e.g. 2025)"),
) -> None:
    """Score all pitches for YEAR with PLV and write pitch-level Parquet."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.score_plv import run

    cfg = get_config()
    typer.echo(f"Scoring year={year} …")
    scored_df = run(year=year, config=cfg)
    typer.echo(
        f"Scored {len(scored_df):,} pitches. "
        f"PLV: mean={scored_df['plv'].mean():.3f}, "
        f"std={scored_df['plv'].std():.3f}, "
        f"range=[{scored_df['plv'].min():.2f}, {scored_df['plv'].max():.2f}]"
    )


@app.command(name="build-leaderboards")
def build_leaderboards(
    year: int = typer.Argument(..., help="Season year (e.g. 2025)"),
    output_format: str = typer.Option("both", "--output-format", help="parquet | csv | both"),
    min_pitches: Optional[int] = typer.Option(None, "--min-pitches", help="Override minimum pitch threshold"),
) -> None:
    """Build and export PLV pitcher leaderboards for YEAR."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.build_leaderboards import run

    cfg = get_config()
    typer.echo(f"Building leaderboards for year={year} …")
    pitcher_lb, pitch_type_lb = run(
        year=year,
        config=cfg,
        output_format=output_format,
        min_pitches=min_pitches,
    )
    typer.echo(f"Pitcher leaderboard: {len(pitcher_lb)} qualified pitchers")
    typer.echo(f"Pitch-type leaderboard: {len(pitch_type_lb)} rows")
    typer.echo(f"Outputs written to: {cfg.outputs_dir}")


@app.command(name="train-pl-plv")
def train_pl_plv(
    train_year: int = typer.Option(2025, "--train-year", help="Reference season to fit scaling (e.g. 2025)"),
) -> None:
    """Fit PLPlvModel scaling parameters against Pitcher List reference data for TRAIN_YEAR."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.train_pl_plv import run

    cfg = get_config()
    typer.echo(f"Fitting PLPlvModel scaling from year={train_year} reference …")
    model = run(train_year=train_year, config=cfg)
    rv_method = model.scaling_params.get("rv_method", "delta_run_exp")
    typer.echo(f"rv_method={rv_method}  |  saved to: {cfg.models_dir}/pl_plv_scaling.json")


@app.command(name="score-pl-plv")
def score_pl_plv(
    year: int = typer.Argument(..., help="Season year to score (e.g. 2026)"),
) -> None:
    """Score pitchers for YEAR with PLPlvModel and write pl_plv_{year}.csv."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.score_pl_plv import run

    cfg = get_config()
    typer.echo(f"Scoring pl_plv for year={year} …")
    agg = run(year=year, config=cfg)
    typer.echo(
        f"Scored {len(agg)} qualified pitchers. "
        f"PLV: mean={agg['pl_plv'].mean():.3f}, "
        f"range=[{agg['pl_plv'].min():.2f}, {agg['pl_plv'].max():.2f}]"
    )
    typer.echo(f"Output written to: {cfg.outputs_dir / f'pl_plv_{year}.csv'}")


@app.command(name="build-exports")
def build_exports(
    year: int = typer.Argument(..., help="Season year (e.g. 2024)"),
    output_format: str = typer.Option("both", "--output-format", help="parquet | csv | both"),
) -> None:
    """Build all leaderboard and rolling-trend exports for YEAR (pitchers + hitters)."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.build_exports import run

    cfg = get_config()
    typer.echo(f"Building exports for year={year} …")
    exports = run(year=year, config=cfg, output_format=output_format)
    for name, df in exports.items():
        typer.echo(f"  {name}: {len(df)} rows")
    typer.echo(f"Outputs written to: {cfg.outputs_dir}")


@app.command(name="train-process")
def train_process() -> None:
    """Fit Process+ scaling parameters using the trained PLV sub-models."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.train_process_plus import run

    cfg = get_config()
    typer.echo("Fitting Process+ scaling parameters …")
    pp_model = run(config=cfg)
    sp = pp_model.scaling_params
    typer.echo(
        f"Process+ scaling params frozen. "
        f"n_qualified_hitters={sp.get('n_qualified_hitters', '?')} | "
        f"process mean={sp.get('process_mean', 0.0):.4f} "
        f"std={sp.get('process_std', 0.0):.4f}"
    )
    typer.echo(f"Params saved to: {cfg.models_dir}")


@app.command(name="score-process")
def score_process(
    year: int = typer.Argument(..., help="Season year to score (e.g. 2024)"),
    output_format: str = typer.Option("both", "--output-format", help="parquet | csv | both"),
    min_pa: Optional[int] = typer.Option(None, "--min-pa", help="Override minimum PA threshold"),
) -> None:
    """Score Process+ components for YEAR and write hitter leaderboard."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.score_process_plus import run

    cfg = get_config()
    typer.echo(f"Scoring Process+ for year={year} …")
    pitch_df, hitter_df = run(
        year=year,
        config=cfg,
        output_format=output_format,
        min_pa=min_pa,
    )
    typer.echo(
        f"Scored {len(pitch_df):,} pitches. "
        f"{len(hitter_df)} qualified hitters."
    )
    if len(hitter_df) > 0:
        typer.echo(
            f"Process+: mean={hitter_df['process_plus'].mean():.1f}, "
            f"range=[{hitter_df['process_plus'].min():.1f}, "
            f"{hitter_df['process_plus'].max():.1f}]"
        )
    typer.echo(f"Outputs written to: {cfg.outputs_dir}")


@app.command(name="build-target-boards")
def build_target_boards(
    year: int = typer.Argument(..., help="Season year (e.g. 2024)"),
    stage: Optional[str] = typer.Option(
        None, "--stage",
        help="Override season stage: early | mid | mature (default: auto-detect from median PA)",
    ),
) -> None:
    """Build fantasy target boards (buy, breakout, regression, discipline, power, pitcher PLV) for YEAR."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.build_target_boards import run

    if stage and stage not in ("early", "mid", "mature"):
        typer.echo(f"Invalid --stage value: {stage!r}. Must be early, mid, or mature.", err=True)
        raise typer.Exit(1)

    cfg = get_config()
    typer.echo(f"Building target boards for year={year} (stage={'auto' if not stage else stage}) ...")
    boards = run(year=year, config=cfg, stage=stage)
    for name, df in boards.items():
        typer.echo(f"  {name}: {len(df)} rows")
    typer.echo(f"CSVs written to: {cfg.outputs_dir}")


@app.command(name="calibrate-fantasy")
def calibrate_fantasy(
    years: str = typer.Option(
        "2023,2024",
        "--years",
        help="Comma-separated calibration years (e.g. 2023,2024)",
    ),
) -> None:
    """Fit hitter and pitcher fantasy-point rate models from historical data."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.build_fantasy_exports import calibrate_all

    cfg = get_config()
    cal_years = [int(y.strip()) for y in years.split(",")]
    typer.echo(f"Calibrating fantasy models on years={cal_years} ...")
    calibrate_all(config=cfg, calibration_years=cal_years)
    typer.echo(f"Calibration complete. Artifacts saved to: {cfg.models_dir}")


@app.command(name="build-fantasy-exports")
def build_fantasy_exports(
    year: Optional[int] = typer.Argument(None, help="Season year (e.g. 2024). Omit to run all available years."),
    output_format: str = typer.Option("both", "--output-format", help="parquet | csv | both"),
    pa_per_game: float = typer.Option(3.5, "--pa-per-game", help="PA/game assumption for hitters"),
    ip_per_start: float = typer.Option(5.5, "--ip-per-start", help="IP/start for SP projection"),
) -> None:
    """Build hitter and pitcher fantasy-point leaderboard exports for YEAR (or all years if omitted)."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.build_fantasy_exports import run
    import re

    cfg = get_config()

    if year is None:
        found = sorted({
            int(m.group(1))
            for f in cfg.outputs_dir.glob("master_pitcher_*.csv")
            if (m := re.search(r"master_pitcher_(\d{4})\.csv", f.name))
        })
        if not found:
            typer.echo("No master_pitcher_YYYY.csv files found — nothing to build.")
            raise typer.Exit(1)
        typer.echo(f"No year specified — running all available years: {found}")
        years = found
    else:
        years = [year]

    for yr in years:
        typer.echo(f"Building fantasy exports for year={yr} ...")
        exports = run(
            year=yr,
            config=cfg,
            pa_per_game=pa_per_game,
            ip_per_start=ip_per_start,
            output_format=output_format,
        )
        for name, df in exports.items():
            typer.echo(f"  {name}: {len(df)} rows")
        typer.echo(f"Outputs written to: {cfg.outputs_dir}")


@app.command(name="update")
def update(
    year: Optional[int] = typer.Option(
        None, "--year",
        help="Season year to update (default: current calendar year)",
    ),
    lag: int = typer.Option(
        2, "--lag",
        help="Days behind today to treat as available (Statcast typically lags 1-2 days)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Show what would be updated without pulling or rebuilding anything",
    ),
    skip_scoring: bool = typer.Option(
        False, "--skip-scoring",
        help="Skip score-plv and score-process (use if models have not changed)",
    ),
    push: bool = typer.Option(
        False, "--push",
        help="Commit updated outputs and push to origin/main after a successful run",
    ),
) -> None:
    """Pull any new Statcast data and rebuild all outputs for YEAR.

    Checks the manifest for the last-pulled date, pulls only new data
    (up to today minus --lag days for Statcast availability), then re-runs:
      build-features (full season) -> score-plv -> score-process ->
      build-exports -> build-target-boards -> build-fantasy-exports

    Safe to run daily. Pass --push to auto-commit and deploy to GitHub Pages.
    """
    import json
    from datetime import date, timedelta
    from pathlib import Path

    from plv_clone.config import get_config

    cfg = get_config()

    today = date.today()
    target_year = year or today.year
    available_through = today - timedelta(days=lag)

    # ── Read manifest ──────────────────────────────────────────────────────
    manifest_path = cfg.raw_data_dir / "manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    year_manifest = manifest.get(str(target_year), {})
    last_date_str = year_manifest.get("last_date")
    last_date = date.fromisoformat(last_date_str) if last_date_str else None

    features_through_str = year_manifest.get("features_built_through")
    features_through = date.fromisoformat(features_through_str) if features_through_str else None

    # ── Determine pull window ──────────────────────────────────────────────
    season_start = date(target_year, 3, 15)   # Opening Day is typically late March
    pull_start = (last_date + timedelta(days=1)) if last_date else season_start
    pull_end   = available_through

    needs_pull     = pull_start <= pull_end
    features_stale = features_through is None or features_through < available_through

    typer.echo(f"PLV update — year={target_year}")
    typer.echo(f"  Last manifest date    : {last_date or 'none'}")
    typer.echo(f"  Features built through: {features_through or 'none'}")
    typer.echo(f"  Available through     : {available_through}  (today minus {lag}d lag)")
    if needs_pull:
        typer.echo(f"  Pull window           : {pull_start} to {pull_end}")
    else:
        typer.echo("  Data is up to date — no pull needed.")
    if features_stale and not needs_pull:
        typer.echo("  Features are stale — will rebuild full season.")

    if dry_run:
        if needs_pull:
            typer.echo(f"\n[dry-run] Would pull {pull_start} to {pull_end}")
        if needs_pull or features_stale:
            typer.echo(f"[dry-run] Would run: build-features {season_start} to {pull_end} (full season)")
        if not skip_scoring:
            typer.echo(f"[dry-run] Would run: score-plv {target_year}")
            typer.echo(f"[dry-run] Would run: score-process {target_year}")
        typer.echo(f"[dry-run] Would run: build-exports {target_year}")
        typer.echo(f"[dry-run] Would run: build-target-boards {target_year}")
        typer.echo(f"[dry-run] Would run: build-fantasy-exports {target_year}")
        if push:
            typer.echo(f"[dry-run] Would commit + push (data: refresh {target_year} through {pull_end})")
        raise typer.Exit(0)

    # ── Pull new data ──────────────────────────────────────────────────────
    if needs_pull:
        from plv_clone.data.ingest_statcast import pull_statcast_range

        typer.echo(f"\nPulling {pull_start} to {pull_end} ...")
        pull_statcast_range(
            start_date=pull_start,
            end_date=pull_end,
            raw_dir=cfg.raw_data_dir,
            chunk_days=cfg.statcast_chunk_days,
        )
    else:
        typer.echo("Skipping pull (already up to date).")

    # ── Build features (always full-season when stale or new data arrived) ─
    # Batter features use an expanding window: they must be computed from
    # Opening Day forward so each batter's tendencies include their full
    # season history. Incremental builds (new dates only) silently produce
    # wrong features for all prior dates.
    if needs_pull or features_stale:
        from plv_clone.pipelines.build_pitch_dataset import run as build_features_run

        typer.echo(f"\nBuilding features {season_start} to {pull_end} (full season) ...")
        build_features_run(
            start_date=season_start,
            end_date=pull_end,
            config=cfg,
        )
        # Record the feature build date in manifest so future runs skip this
        # when data is already current.
        if str(target_year) not in manifest:
            manifest[str(target_year)] = {}
        manifest[str(target_year)]["features_built_through"] = str(pull_end)
        manifest_path.write_text(json.dumps(manifest, indent=2))

    # ── Score ──────────────────────────────────────────────────────────────
    if not skip_scoring or needs_pull:
        from plv_clone.pipelines.score_plv import run as score_plv_run
        from plv_clone.pipelines.score_process_plus import run as score_pp_run

        typer.echo(f"\nScoring PLV for {target_year} …")
        scored_plv = score_plv_run(year=target_year, config=cfg)
        typer.echo(f"  PLV scored: {len(scored_plv):,} pitches")

        typer.echo(f"Scoring Process+ for {target_year} …")
        _, hitter_df = score_pp_run(year=target_year, config=cfg)
        typer.echo(f"  Process+ scored: {len(hitter_df)} qualified hitters")
    else:
        typer.echo("\nSkipping scoring (--skip-scoring).")

    # ── Rebuild exports ────────────────────────────────────────────────────
    from plv_clone.pipelines.build_exports import run as build_exports_run
    from plv_clone.pipelines.build_target_boards import run as build_boards_run
    from plv_clone.pipelines.build_fantasy_exports import run as build_fantasy_run

    typer.echo(f"\nBuilding exports for {target_year} …")
    exports = build_exports_run(year=target_year, config=cfg)
    for name, df in exports.items():
        typer.echo(f"  {name}: {len(df)} rows")

    typer.echo(f"\nBuilding target boards for {target_year} …")
    boards = build_boards_run(year=target_year, config=cfg)
    for name, df in boards.items():
        typer.echo(f"  {name}: {len(df)} rows")

    typer.echo(f"\nBuilding fantasy exports for {target_year} …")
    fantasy = build_fantasy_run(year=target_year, config=cfg)
    for name, df in fantasy.items():
        typer.echo(f"  {name}: {len(df)} rows")

    # Add the dashboard signal / risk_flag / sample_tier columns. Runs last
    # so both master_hitter and pitcher_fantasy are present and get enriched
    # in a single pass.
    from plv_clone.pipelines.enrich_outputs import enrich_outputs as _enrich
    typer.echo(f"\nEnriching exports for {target_year} …")
    _enrich(target_year, cfg.outputs_dir)

    typer.echo(f"\nUpdate complete. All outputs written to: {cfg.outputs_dir}")

    # ── Commit + push ──────────────────────────────────────────────────────
    if push:
        import subprocess
        date_str = str(pull_end)
        typer.echo(f"\nCommitting and pushing (data: refresh {target_year} through {date_str}) ...")
        subprocess.run(
            ["git", "add", "data/outputs/", "data/raw/manifest.json"],
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"data: refresh {target_year} through {date_str}"],
            check=True,
        )
        subprocess.run(["git", "push", "origin", "main"], check=True)
        typer.echo("Pushed. GitHub Pages will redeploy in ~60s.")


@app.command(name="generate-report")
def generate_report_cmd(
    year: int = typer.Option(SEASON_YEAR, "--year", help="Season year"),
) -> None:
    """Generate the standalone HTML process report for YEAR.

    Reads pre-built CSVs from data/outputs/, fetches live ESPN data,
    and writes data/outputs/process_report_{year}.html.
    """
    import sys
    from pathlib import Path

    # generate_report.py was archived to scripts/_attic/ (2026-09-01,
    # ADR-0009 addendum) — this command still works for a historical rebuild.
    # cli.py lives at src/plv_clone/cli.py → 3 parents up = project root.
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    for _d in (scripts_dir, scripts_dir / "_attic"):
        sys.path.insert(0, str(_d))

    try:
        from generate_report import run as report_run
    except ImportError:
        typer.echo("ERROR: could not import scripts/_attic/generate_report.py", err=True)
        raise typer.Exit(1)

    rc = report_run(year)
    if rc != 0:
        raise typer.Exit(rc)


if __name__ == "__main__":
    app()
