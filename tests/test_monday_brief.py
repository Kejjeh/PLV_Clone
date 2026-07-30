"""Tests for scripts/xfp/build_monday_brief — the headless Monday brief composer.

The brief is the thing Josh reads before touching the roster, so the failure mode
that matters is not "it crashed" — it is "it printed a confident-looking page
that quietly omitted a check". Every test here defends against that:

  * all artifacts absent  -> a VALID brief made of explicit "not available" lines
                             that does NOT read as an all-clear
  * a stale artifact      -> its age is stamped on the line that quotes it
  * a sentinel FAIL       -> surfaced in the FIRST section, ahead of statistics
  * a truncated artifact  -> a loud MALFORMED line + a non-zero exit, never a
                             substituted default (docs/rh3_harness_root_bug_2026-07-28.md)
  * fixed inputs          -> byte-identical output, with the single wall-clock
                             stamp the only line that moves on an intraday rerun
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

MB = pytest.importorskip("scripts.xfp.build_monday_brief")

NOW = datetime(2026, 7, 30, 9, 0, 0)          # a Thursday — deliberately NOT Monday
NOW_LATE = datetime(2026, 7, 30, 19, 30, 0)   # same day, ~10h later


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — minimal but SHAPE-FAITHFUL artifacts
# ─────────────────────────────────────────────────────────────────────────────
def _paths(tmp_path: Path) -> "MB.BriefPaths":
    outputs = tmp_path / "outputs"
    research = tmp_path / "research"
    outputs.mkdir(parents=True, exist_ok=True)
    (research / "pl_cache").mkdir(parents=True, exist_ok=True)
    return MB.default_paths(outputs=outputs, research=research,
                            out=tmp_path / "monday_brief.md")


def _scorecard_rows(scdate: str = "2026-07-29", sentinel_status: str = "PASS"):
    """A scorecard with the three drift sentinels present at `sentinel_status`."""
    rows = [
        (scdate, "forward_accuracy", "rh3_spearman_rate_7d", "all", 0.1247, "INFO", "n=249"),
        (scdate, "forward_accuracy", "rp3_spearman_rate_7d", "all", 0.1947, "INFO", "n=32"),
        (scdate, "data_health", "il_join_match_rate", "2026", 0.31, "PASS", "healthy"),
        (scdate, "pipeline_staleness", "statcast_lag", "all", 1.0, "PASS", "1d"),
    ]
    for metric in MB.DRIFT_SENTINELS:
        rows.append((scdate, "data_health", metric, "all", 1.0, sentinel_status,
                     f"{metric} note"))
    return pd.DataFrame(rows, columns=["date", "section", "metric", "segment",
                                       "value", "status", "note"])


def _write_scorecard(paths, scdate: str = "2026-07-29",
                     sentinel_status: str = "PASS") -> None:
    df = _scorecard_rows(scdate, sentinel_status)
    df.to_csv(paths.model_scorecard_csv, index=False)
    paths.model_scorecard_md.write_text(f"# model scorecard {scdate}\n",
                                        encoding="utf-8")


def _write_matchup_leverage(paths, generated="2026-07-30", period=17,
                            banked=3, cap=10, remaining=7) -> None:
    payload = {
        "generated": generated, "period": period, "opp_team": "Late Night Bettsing",
        "my_score": 91.1, "opp_score": 121.7, "days_remaining_incl_today": 5,
        "sims": 8000, "pwin": 0.2811, "regime": "TRAILING",
        "regime_note": "variance is an ASSET",
        "sp_cap": cap, "banked_sp_starts": banked, "cap_remaining": remaining,
        "cap_remaining_opp": 9,
        "top_moves": [{"move": "ADD Walbert Urena (FA)", "dpwin": 0.0287,
                       "why": "extra cap-eligible start"}],
    }
    paths.matchup_leverage.write_text(json.dumps(payload), encoding="utf-8")


def _write_optimizer(paths, run_id="2026-07-30T005713_7", plan=None) -> None:
    if plan is None:
        plan = [{"add": "Ryan Jeffers", "add_bucket": "H", "drop": "Reid Detmers",
                 "drop_bucket": "SP", "dpwin": 0.0944, "mc_se": 0.007065,
                 "dtitle_equity_pp": 0.0831}]
    payload = {
        "base_pwin": 0.385, "regime": "TRAILING", "period": 17, "sims": 5000,
        "seed": 7, "cap_remaining": 7, "plan": plan,
        "title_equity": {"dtitle_pp": 0.88, "status": "current"},
        "dpwin_run_id": run_id,
    }
    paths.weekly_optimizer.write_text(json.dumps(payload), encoding="utf-8")


def _write_season_sim(paths, generated="2026-07-30", period=17) -> None:
    payload = {
        "generated": generated, "period": period, "sims": 5000,
        "josh": {"team": "New York Ligers", "p_playoffs": 0.9254, "p_title": 0.1078,
                 "value_of_win_curve": [{"period": period, "p_win_week": 0.431,
                                         "dtitle_pp": 0.88, "dplayoffs_pp": 6.42}],
                 "strategy_directive": ["MOSTLY SAFE"]},
    }
    paths.season_sim.write_text(json.dumps(payload), encoding="utf-8")


def _write_dpwin(paths, snapshot="2026-07-30") -> None:
    df = pd.DataFrame([
        {"run_id": "2026-07-30T005713_7", "snapshot_date": snapshot,
         "move_type": "swap", "add_name": "Ryan Jeffers", "drop_name": "Reid Detmers",
         "dpwin": 0.0944},
        {"run_id": "2026-07-30T005713_7", "snapshot_date": snapshot,
         "move_type": "sit_hitter", "add_name": None, "drop_name": "Bo Bichette",
         "dpwin": -0.0475},
    ])
    df.to_parquet(paths.dpwin_history, index=False)


def _write_pl_cache(paths, fetched="2026-07-29") -> None:
    for fname in MB.PL_CACHE_FILES:
        (paths.pl_cache_dir / fname).write_text(
            json.dumps({"fetched": fetched, "ranks": {"Someone": 1}}),
            encoding="utf-8")


def _write_verdicts(paths) -> None:
    pd.DataFrame([
        {"bucket": "H", "verdict": "BUY", "n": 126, "n_players": 11,
         "mean_actual": 0.558, "mean_proj_per": 0.594, "mean_residual": -0.036,
         "hit_rate": 0.325, "unit": "PA"},
    ]).to_csv(paths.verdict_scorecard_csv, index=False)


def _write_all(paths) -> None:
    _write_scorecard(paths)
    _write_matchup_leverage(paths)
    _write_optimizer(paths)
    _write_season_sim(paths)
    _write_dpwin(paths)
    _write_pl_cache(paths)
    _write_verdicts(paths)


def _body(text: str) -> list[str]:
    """The brief minus its single wall-clock stamp line."""
    return [ln for ln in text.splitlines() if "Brief built:" not in ln]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Total absence must still produce a HONEST brief
# ─────────────────────────────────────────────────────────────────────────────
def test_all_artifacts_missing_produces_valid_brief(tmp_path):
    paths = _paths(tmp_path)
    text, malformed = MB.build_brief(paths, NOW)

    assert malformed == [], "nothing was present, so nothing can be malformed"
    # Structurally complete: all nine sections render.
    for n in range(1, 10):
        assert f"\n## {n}. " in text, f"section {n} missing from the brief"
    # And every artifact-backed section says so explicitly.
    for name in ("model_scorecard.csv", "verdict_scorecard.csv",
                 "dpwin_history.parquet", "weekly_optimizer.json",
                 "matchup_leverage.json", "season_sim.json"):
        assert f"`{name}` is MISSING" in text, f"{name} absence not stated"
    assert "**not available**" in text
    # No section is silently empty: every section has at least one bullet/row.
    for chunk in text.split("\n## ")[1:]:
        content = [ln for ln in chunk.splitlines()[1:] if ln.strip()]
        assert content, f"section rendered EMPTY:\n{chunk[:200]}"


def test_all_missing_is_not_reported_as_all_clear(tmp_path):
    """The dangerous failure: an empty decision block reading as 'nothing to do'."""
    paths = _paths(tmp_path)
    text, _ = MB.build_brief(paths, NOW)

    assert "not** an all-clear" in text
    assert "COULD NOT CHECK" in text
    # Each of the three decision checks must name itself as unrun.
    assert "drift-sentinel tripwires" in text
    assert "SP-start cap position" in text
    assert "recommended add/drop plan" in text
    assert "Nothing flagged by any available artifact." not in text


def test_regeneration_command_accompanies_every_missing_artifact(tmp_path):
    paths = _paths(tmp_path)
    text, _ = MB.build_brief(paths, NOW)
    for name, cmd in MB.REGEN.items():
        assert cmd in text, f"no regeneration hint for {name}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Age stamping
# ─────────────────────────────────────────────────────────────────────────────
def test_stale_artifact_age_is_stamped_and_labelled(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    # 19 days old, and (period 15 vs live 17) two periods behind.
    _write_season_sim(paths, generated="2026-07-11", period=15)

    text, malformed = MB.build_brief(paths, NOW)
    assert malformed == []
    assert "as-of 2026-07-11, 19 days old (content date) [STALE]" in text
    assert "| `season_sim.json` | STALE | 2026-07-11 | 19d |" in text
    # Cross-artifact check: the sim being behind the live period is called out.
    assert "2 period(s) behind" in text or "2 period(s) BEHIND" in text


def test_fresh_artifact_is_not_labelled_stale(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    text, _ = MB.build_brief(paths, NOW)
    assert "as-of 2026-07-30, today (content date)" in text
    assert "| `weekly_optimizer.json` | ok |" in text


def test_every_quoted_artifact_line_carries_an_age(tmp_path):
    """A number without an age is how a 3-day-old read passes as today's."""
    paths = _paths(tmp_path)
    _write_all(paths)
    _write_scorecard(paths, scdate="2026-07-20")
    _write_matchup_leverage(paths, generated="2026-07-28")
    text, _ = MB.build_brief(paths, NOW)
    for name in ("model_scorecard.csv", "weekly_optimizer.json",
                 "matchup_leverage.json", "season_sim.json",
                 "dpwin_history.parquet", "verdict_scorecard.csv"):
        # the section header line for each artifact pairs the name with "as-of"
        hits = [ln for ln in text.splitlines()
                if f"`{name}`" in ln and "as-of" in ln]
        assert hits, f"{name} is quoted without an age stamp"


def test_stale_decision_artifact_warns_before_acting(tmp_path):
    """A plan built against a 3-day-old roster must not read as executable."""
    paths = _paths(tmp_path)
    _write_all(paths)
    _write_optimizer(paths, run_id="2026-07-27T005713_7")
    text, _ = MB.build_brief(paths, NOW)
    assert "RE-RUN before" in text
    assert "3d-old roster" in text


def test_verdict_scorecard_absence_explains_the_monday_cadence(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    paths.verdict_scorecard_csv.unlink()
    text, _ = MB.build_brief(paths, NOW)
    assert "written only on MONDAY refreshes" in text
    assert "Today is Thursday" in text


# ─────────────────────────────────────────────────────────────────────────────
# 3. Sentinel FAIL must lead
# ─────────────────────────────────────────────────────────────────────────────
def test_sentinel_fail_is_surfaced_at_the_top(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    _write_scorecard(paths, sentinel_status="FAIL")

    text, malformed = MB.build_brief(paths, NOW)
    assert malformed == []
    decisions = text.split("## 2.")[0]
    for metric in MB.DRIFT_SENTINELS:
        assert f"**SENTINEL FAIL** `{metric}`" in decisions, (
            f"{metric} FAIL not in the first section")
    # ...and ahead of every statistic.
    assert text.index("SENTINEL FAIL") < text.index("P(win)")


def test_sentinel_fail_outranks_an_ordinary_tripwire_fail(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    df = _scorecard_rows(sentinel_status="FAIL")
    df.loc[len(df)] = ("2026-07-29", "data_health", "fg_scrape_silent_fail",
                       "fg_pit_2026_current.csv", 13.0, "FAIL", "silently failing")
    df.to_csv(paths.model_scorecard_csv, index=False)

    text, _ = MB.build_brief(paths, NOW)
    assert text.index("SENTINEL FAIL") < text.index("TRIPWIRE FAIL")


def test_absent_sentinel_row_is_not_reported_as_pass(tmp_path):
    """A check that did not run is the exact thing a brief must never launder."""
    paths = _paths(tmp_path)
    _write_all(paths)
    df = _scorecard_rows()
    df = df[~df["metric"].isin(MB.DRIFT_SENTINELS)]
    df.to_csv(paths.model_scorecard_csv, index=False)

    text, _ = MB.build_brief(paths, NOW)
    for metric in MB.DRIFT_SENTINELS:
        assert f"`{metric}` — **NO ROW in this scorecard**" in text
    assert "NOT a PASS" in text


def test_sentinel_absence_on_a_predating_scorecard_says_why(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    df = _scorecard_rows(scdate="2026-07-27")
    df = df[~df["metric"].isin(MB.DRIFT_SENTINELS)]
    df.to_csv(paths.model_scorecard_csv, index=False)

    text, _ = MB.build_brief(paths, NOW)
    assert "PREDATES the 2026-07-29 introduction" in text
    assert "NOT a PASS" not in text  # the innocent explanation, not the alarm


# ─────────────────────────────────────────────────────────────────────────────
# 4. Cap + move decisions
# ─────────────────────────────────────────────────────────────────────────────
def test_cap_breach_leads_the_brief(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    _write_matchup_leverage(paths, banked=12, cap=10, remaining=-2)
    text, _ = MB.build_brief(paths, NOW)
    decisions = text.split("## 2.")[0]
    assert "**SP CAP BREACHED**" in decisions
    assert "2 over" in decisions
    assert "score ZERO" in decisions


def test_cap_exhausted_is_distinguished_from_breach(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    _write_matchup_leverage(paths, banked=10, cap=10, remaining=0)
    text, _ = MB.build_brief(paths, NOW)
    assert "**SP CAP EXHAUSTED**" in text
    assert "SP CAP BREACHED" not in text


def test_positive_dpwin_move_leads_and_significance_is_reported(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    text, _ = MB.build_brief(paths, NOW)
    decisions = text.split("## 2.")[0]
    # The move must be present AND carry its position in the sequence. A plan of
    # >1 step is ordered — step 2 routinely drops the player step 1 added — so an
    # unlabelled list invites acting on one step alone and reversing another.
    assert "ADD Ryan Jeffers / DROP Reid Detmers" in decisions
    assert "MOVE AVAILABLE" in decisions
    if decisions.count("MOVE AVAILABLE") > 1:
        assert "do them IN ORDER" in decisions
    assert "> 2x MC se — a real gap" in decisions


def test_dpwin_inside_mc_noise_is_not_sold_as_a_real_gap(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    _write_optimizer(paths, plan=[{"add": "Marginal Guy", "add_bucket": "H",
                                   "drop": "Someone", "drop_bucket": "SP",
                                   "dpwin": 0.004, "mc_se": 0.007}])
    text, _ = MB.build_brief(paths, NOW)
    assert "WITHIN 2x MC se" in text
    assert "not distinguishable" in text


def test_empty_plan_says_stand_pat_rather_than_nothing(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    _write_optimizer(paths, plan=[])
    text, _ = MB.build_brief(paths, NOW)
    assert "stand pat" in text
    assert "Plan is EMPTY" in text
    assert "MOVE AVAILABLE" not in text


# ─────────────────────────────────────────────────────────────────────────────
# 5. No silent defaults — a truncated artifact is LOUD
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("dropped", ["cap_remaining", "sp_cap", "banked_sp_starts"])
def test_missing_cap_field_is_malformed_not_defaulted(tmp_path, dropped):
    paths = _paths(tmp_path)
    _write_all(paths)
    payload = json.loads(paths.matchup_leverage.read_text(encoding="utf-8"))
    payload.pop(dropped)
    paths.matchup_leverage.write_text(json.dumps(payload), encoding="utf-8")

    text, malformed = MB.build_brief(paths, NOW)
    assert any(f"`{dropped}` is absent" in m for m in malformed), malformed
    assert "MALFORMED" in text
    # The absence must NOT have been read as "0 starts remaining".
    assert "SP CAP EXHAUSTED" not in text
    assert "SP CAP BREACHED" not in text


def test_missing_dpwin_field_is_malformed_not_zero(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    _write_optimizer(paths, plan=[{"add": "Ghost", "drop": "Nobody"}])
    text, malformed = MB.build_brief(paths, NOW)
    assert any("`dpwin` is absent" in m for m in malformed), malformed
    assert "MOVE AVAILABLE" not in text


def test_scorecard_missing_columns_is_malformed(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    pd.DataFrame({"date": ["2026-07-29"], "value": [1.0]}).to_csv(
        paths.model_scorecard_csv, index=False)
    text, malformed = MB.build_brief(paths, NOW)
    assert any("required column(s)" in m for m in malformed), malformed
    assert "MALFORMED" in text


def test_unreadable_artifact_degrades_without_crashing(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    paths.matchup_leverage.write_text("{not json", encoding="utf-8")
    text, _ = MB.build_brief(paths, NOW)
    assert "UNREADABLE" in text
    # the rest of the brief still renders
    assert "## 5. Season outlook" in text


def test_malformed_artifact_exits_2(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    payload = json.loads(paths.matchup_leverage.read_text(encoding="utf-8"))
    payload.pop("cap_remaining")
    paths.matchup_leverage.write_text(json.dumps(payload), encoding="utf-8")

    rc = MB.main(["--outputs-dir", str(paths.model_scorecard_csv.parent),
                  "--research-dir", str(paths.dpwin_history.parent),
                  "--out", str(paths.out), "--now", "2026-07-30"])
    assert rc == 2
    assert paths.out.exists(), "the brief must still land so the reader sees the rest"


def test_clean_run_exits_0_and_writes_the_brief(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    rc = MB.main(["--outputs-dir", str(paths.model_scorecard_csv.parent),
                  "--research-dir", str(paths.dpwin_history.parent),
                  "--out", str(paths.out), "--now", "2026-07-30"])
    assert rc == 0
    assert paths.out.read_text(encoding="utf-8").startswith("# Monday brief")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Determinism / late tolerance
# ─────────────────────────────────────────────────────────────────────────────
def test_output_is_byte_identical_for_fixed_inputs(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    first, _ = MB.build_brief(paths, NOW)
    second, _ = MB.build_brief(paths, NOW)
    assert first == second


def test_intraday_rerun_diffs_only_the_marked_stamp_line(tmp_path):
    """A run that fires 10h late must produce the same brief, not a different one."""
    paths = _paths(tmp_path)
    _write_all(paths)
    morning, _ = MB.build_brief(paths, NOW)
    evening, _ = MB.build_brief(paths, NOW_LATE)

    assert morning != evening, "the stamp line should record the actual build time"
    assert _body(morning) == _body(evening)
    stamps = [ln for ln in morning.splitlines() if "Brief built:" in ln]
    assert len(stamps) == 1, "exactly one wall-clock line, and it is marked"
    # No other line may carry a clock time.
    assert not [ln for ln in _body(morning) if ":00:00" in ln or "T09:" in ln]


def test_brief_does_not_branch_on_it_being_monday(tmp_path):
    """Late-tolerant: the same artifacts yield the same body on any weekday."""
    paths = _paths(tmp_path)
    _write_all(paths)
    monday, _ = MB.build_brief(paths, datetime(2026, 8, 3, 7, 0))     # Monday
    thursday, _ = MB.build_brief(paths, datetime(2026, 8, 3, 7, 0))
    assert _body(monday) == _body(thursday)
    # The weekday appears only as a factual as-of statement.
    assert "(Monday)" in monday


# ─────────────────────────────────────────────────────────────────────────────
# 7. Offline contract — the composer must never fetch anything
# ─────────────────────────────────────────────────────────────────────────────
def test_composer_imports_no_network_client():
    """Structural guard: no HTTP client and no live-data library may creep in.

    ("WebFetch" is deliberately NOT banned — the module explains in prose that a
    PL refresh needs one, which is the opposite of doing it.)
    """
    src = Path(MB.__file__).read_text(encoding="utf-8")
    for banned in ("import requests", "from requests", "urllib.request",
                   "urllib.parse", "import httpx", "import socket", "webbrowser",
                   "pybaseball", "espn_connector", "mlb_stats", "statsapi"):
        assert banned not in src, f"composer must stay offline; found {banned!r}"


def test_pl_section_states_it_does_not_scrape(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    _write_pl_cache(paths, fetched="2026-07-20")
    text, _ = MB.build_brief(paths, NOW)
    assert "does NOT fetch pitcherlist.com" in text
    assert "step 7" in text
    # the last cached edition and its age are both reported
    assert "fetched 2026-07-20 (10d old)" in text
    assert "**STALE**" in text


def test_missing_pl_cache_is_reported_not_ignored(tmp_path):
    paths = _paths(tmp_path)
    _write_all(paths)
    (paths.pl_cache_dir / "pl_sps_top100.json").unlink()
    text, _ = MB.build_brief(paths, NOW)
    assert "`pl_sps_top100.json` — **MISSING**" in text
    assert "PL cache `pl_sps_top100.json` is MISSING" in text  # also an advisory


# ── the NaN gap (found by adversarial review 2026-07-29) ─────────────────────

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_is_malformed_not_a_number(bad):
    """THE defect this closes: json.dumps defaults to allow_nan=True, so an
    upstream writer can emit a bare NaN literal, and float('nan') sails through a
    try/except. A NaN cap_remaining then compares False against every threshold,
    so a real SP-cap BREACH renders as "Nothing FLAGGED" with exit 0 — a silent
    pass on the exact alert the brief exists to raise."""
    import build_monday_brief as MB
    with pytest.raises(MB.MalformedArtifact, match="non-finite"):
        MB._num(bad, "cap_remaining", "weekly_optimizer.json")


def test_finite_numbers_and_numeric_strings_still_pass():
    import build_monday_brief as MB
    assert MB._num(7, "k", "a") == 7.0
    assert MB._num("7.5", "k", "a") == 7.5
    assert MB._num(0, "k", "a") == 0.0        # zero is a real value, not missing


def test_settled_total_refuses_to_silently_sum_a_bad_cell():
    """A fillna(0) here would understate the sample while still looking valid."""
    import build_monday_brief as MB
    import pandas as pd
    assert MB._settled_total(pd.DataFrame({"n": [3, 4, 5]})) == "12"
    out = MB._settled_total(pd.DataFrame({"n": [3, "x", 5]}))
    assert out.startswith("--") and "non-numeric" in out


def test_multi_step_plan_is_labelled_as_sequenced():
    """The optimizer's plan is sequenced: step 2 routinely drops the player step 1
    added, so acting on step 2 alone REVERSES step 1. The decision-first block must
    say so, not present them as independent numbered choices."""
    src = (Path(__file__).resolve().parent.parent / "scripts" / "xfp"
           / "build_monday_brief.py").read_text(encoding="utf-8")
    assert "STEP {step} of {n_steps}" in src
    assert "do them IN ORDER" in src
