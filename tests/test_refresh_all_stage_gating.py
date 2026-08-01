"""A failed substrate stage must stop the pipeline before the models run.

WHY THIS FILE EXISTS (audit 2026-08-01, item 15)
------------------------------------------------
refresh_all.py ran every stage unconditionally, counting failures and exiting 1
at the end. That exit code correctly gates the xfp-model PUBLISH — but only
AFTER the model pipelines have already run. So a failed
`build_rolling_hitters.py` left yesterday's rolling substrate on disk, rh3 read
it without complaint (there is no freshness guard on ROLLING_CSV), and
overwrote data/outputs/xfp_rh3_projections.csv with projections derived from
stale inputs. Those CSVs then reach the plv_clone data commit, every step
2a-4.97 consumer, and the permanent projection-history / decision-ledger
parquets.

Behaviour on a CLEAN run is unchanged by construction: with zero failures the
loop issues the identical stages in the identical order.

Every test replaces subprocess.run, so no pipeline script is ever executed.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

import refresh_all as RA  # noqa: E402


class Completed:
    def __init__(self, returncode):
        self.returncode = returncode
        self.stdout = "stub"
        self.stderr = "stub stderr"


@pytest.fixture
def pipeline(monkeypatch):
    """Drive refresh_all.main() with subprocess.run recorded, not executed."""

    def _drive(*fail_scripts: str, argv=("refresh_all.py",)):
        issued: list[str] = []

        def fake_run(cmd, **kwargs):
            script = Path(cmd[-1]).name
            issued.append(script)
            return Completed(1 if script in fail_scripts else 0)

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(sys, "argv", list(argv))
        with pytest.raises(SystemExit) as exc:
            RA.main()
        return issued, exc.value.code

    return _drive


def test_a_failed_substrate_stage_stops_before_the_model_pipelines(pipeline):
    """The shipped projection CSVs must not be rebuilt from a stale substrate."""
    issued, code = pipeline("build_rolling_hitters.py")

    assert "build_rolling_hitters.py" in issued, "the failing stage did run"
    assert "xfp_rh3_pipeline.py" not in issued, (
        "rh3 ran after its substrate build failed — it would read yesterday's "
        "rolling_hitters CSV and overwrite the shipped projections with it")
    assert "xfp_rp3_pipeline.py" not in issued
    assert "xfp_rprs2_pipeline.py" not in issued
    assert code == 1, "the caller's gate (ok_models) still depends on exit 1"


def test_a_failed_cosmetic_stage_does_not_withhold_the_rest(pipeline):
    """A broken index.html must not stop the pipeline's terminal artifacts.

    The tail stages produce pages, not inputs — nothing downstream reads them,
    so treating them like a substrate would cost a day of work for a display
    bug. The exit code still reports the failure so the caller's publish gate
    is unchanged.
    """
    issued, code = pipeline("build_weekly_fp_substrate.py")

    assert "build_index_dashboard.py" in issued, (
        "a failed weekly-FP substrate must not withhold the dashboard build")
    assert code == 1, "the failure is still reported to the caller"


def test_a_clean_run_issues_every_stage_in_declared_order(pipeline):
    """Behaviour preservation: nothing changes when nothing fails."""
    issued, code = pipeline()

    assert issued == [script for _, script, *_ in RA.STAGES]
    assert code == 0
