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
) -> None:
    """Pull pitch-level Statcast data and store as year-partitioned Parquet."""
    from plv_clone.config import get_config
    from plv_clone.data.ingest_statcast import pull_statcast_range

    cfg = get_config()
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)

    typer.echo(f"Pulling Statcast data: {start_date} to {end_date}")
    df = pull_statcast_range(
        start_date=start_date,
        end_date=end_date,
        raw_dir=cfg.raw_data_dir,
        chunk_days=cfg.statcast_chunk_days,
        force_refresh=force,
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
    year: int = typer.Argument(..., help="Season year (e.g. 2024)"),
    output_format: str = typer.Option("both", "--output-format", help="parquet | csv | both"),
    pa_per_game: float = typer.Option(3.5, "--pa-per-game", help="PA/game assumption for hitters"),
    ip_per_start: float = typer.Option(5.5, "--ip-per-start", help="IP/start for SP projection"),
) -> None:
    """Build hitter and pitcher fantasy-point leaderboard exports for YEAR."""
    from plv_clone.config import get_config
    from plv_clone.pipelines.build_fantasy_exports import run

    cfg = get_config()
    typer.echo(f"Building fantasy exports for year={year} ...")
    exports = run(
        year=year,
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
) -> None:
    """Pull any new Statcast data and rebuild all outputs for YEAR.

    Checks the manifest for the last-pulled date, pulls only new data
    (up to today minus --lag days for Statcast availability), then re-runs:
      score-plv → score-process → build-exports → build-target-boards → build-fantasy-exports

    Safe to run daily — skips the pull entirely if already up to date.
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

    # ── Determine pull window ──────────────────────────────────────────────
    season_start = date(target_year, 3, 15)   # Opening Day is typically late March
    pull_start = (last_date + timedelta(days=1)) if last_date else season_start
    pull_end   = available_through

    needs_pull = pull_start <= pull_end

    typer.echo(f"PLV update — year={target_year}")
    typer.echo(f"  Last manifest date : {last_date or 'none'}")
    typer.echo(f"  Available through  : {available_through}  (today minus {lag}d lag)")
    if needs_pull:
        typer.echo(f"  Pull window        : {pull_start} → {pull_end}")
    else:
        typer.echo("  Data is up to date — no pull needed.")

    if dry_run:
        if needs_pull:
            typer.echo(f"\n[dry-run] Would pull {pull_start} to {pull_end}")
        if not skip_scoring:
            typer.echo(f"[dry-run] Would run: score-plv {target_year}")
            typer.echo(f"[dry-run] Would run: score-process {target_year}")
        typer.echo(f"[dry-run] Would run: build-exports {target_year}")
        typer.echo(f"[dry-run] Would run: build-target-boards {target_year}")
        typer.echo(f"[dry-run] Would run: build-fantasy-exports {target_year}")
        raise typer.Exit(0)

    # ── Pull new data ──────────────────────────────────────────────────────
    if needs_pull:
        from plv_clone.data.ingest_statcast import pull_statcast_range
        from plv_clone.pipelines.build_pitch_dataset import run as build_features_run

        typer.echo(f"\nPulling {pull_start} to {pull_end} …")
        pull_statcast_range(
            start_date=pull_start,
            end_date=pull_end,
            raw_dir=cfg.raw_data_dir,
            chunk_days=cfg.statcast_chunk_days,
        )
        typer.echo("Building features for new data …")
        build_features_run(
            start_date=pull_start,
            end_date=pull_end,
            config=cfg,
        )
    else:
        typer.echo("Skipping pull (already up to date).")

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

    typer.echo(f"\nUpdate complete. All outputs written to: {cfg.outputs_dir}")


if __name__ == "__main__":
    app()
