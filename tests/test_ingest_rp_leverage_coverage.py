"""RP leverage / IR join coverage + cache staleness — behavioral spec.

`leverage_tier` and `FIREMAN` are built by left-merging two manually-scraped
caches (FanGraphs gmLI, Baseball-Reference inherited runners) onto the RP panel.
Neither merge had a post-merge check, so when the caches stopped being refreshed
the current season's join coverage collapsed (2026: 182/229 = 79.5% gmLI, 181/229
= 79.0% IR, against 99.3-100% in every complete prior season) and the build still
emitted a tier for every reliever — the 47 unmatched arms silently falling back
to the SV/HLD binary with FIREMAN uniformly False.

Two failure shapes must both be visible, because they are not the same problem:
  * COVERAGE — a share of the current cohort is missing from the cache;
  * STALENESS — the rows that DID join were measured months ago (the 2026 cache
    tops out at G=28 while the joined rows now sit at median G=40), so a build
    can read 100% covered and still be running on a two-month-old measurement.

Visibility only: no tier, no gmLI value, and no projection changes.
"""
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
import build_rp_archetypes as rpa  # noqa: E402


CUR, PREV = 2026, 2025


def _panel(cur_matched, cur_total, col="gmli"):
    """A panel where the prior complete season joins fully and the current one
    joins only `cur_matched` of `cur_total`."""
    rows = [{"year": PREV, "pitcher": 10_000 + i, col: 1.1} for i in range(60)]
    for i in range(cur_total):
        rows.append({"year": CUR, "pitcher": 20_000 + i,
                     col: 1.1 if i < cur_matched else np.nan})
    return pd.DataFrame(rows)


def _cache(tmp_path, age_days=0.0, name="fangraphs_rp_leverage_2018_2026.csv"):
    p = tmp_path / name
    p.write_text("mlb_id,season,gmli\n1,2026,1.1\n", encoding="utf-8")
    when = time.time() - age_days * 86400
    os.utime(p, (when, when))
    return p


def test_degraded_current_season_coverage_is_reported_and_warned(tmp_path, capsys):
    """A cache covering only part of the current cohort is called out, with the
    rate, the comparator season, and what the degradation reaches."""
    report = rpa.report_join_coverage(
        _panel(182, 229), col="gmli", cache_path=_cache(tmp_path),
        label="FanGraphs leverage", affects="leverage_tier / FIREMAN")

    out = capsys.readouterr().out
    assert report["year"] == CUR
    assert report["matched"] == 182 and report["n"] == 229
    assert report["rate"] == pytest.approx(0.795, abs=0.001)
    assert report["prev_year"] == PREV
    assert report["prev_rate"] == pytest.approx(1.0)
    assert report["status"] == "FAIL"
    assert "182/229" in out and "79.5" in out
    assert "WARNING" in out and "leverage_tier / FIREMAN" in out


def test_full_coverage_on_a_fresh_cache_is_quiet(tmp_path, capsys):
    """The signal stays meaningful — a healthy build does not cry wolf."""
    report = rpa.report_join_coverage(
        _panel(229, 229), col="gmli", cache_path=_cache(tmp_path),
        label="FanGraphs leverage", affects="leverage_tier / FIREMAN")

    assert report["status"] == "PASS"
    assert "WARNING" not in capsys.readouterr().out


def test_a_stale_cache_warns_even_when_coverage_looks_complete(tmp_path, capsys):
    """The load-bearing half: rows that joined can still be a two-month-old
    measurement, so cache age is reported independently of the join rate."""
    report = rpa.report_join_coverage(
        _panel(229, 229), col="gmli", cache_path=_cache(tmp_path, age_days=63),
        label="FanGraphs leverage", affects="leverage_tier / FIREMAN")

    out = capsys.readouterr().out
    assert report["age_days"] >= 62
    assert report["status"] == "FAIL"
    assert "63" in out and "WARNING" in out


def test_a_missing_cache_is_announced_not_silently_skipped(tmp_path, capsys):
    """No cache at all is a reportable state, not an absence of news."""
    report = rpa.report_join_coverage(
        _panel(229, 229), col="gmli", cache_path=tmp_path / "absent.csv",
        label="FanGraphs leverage", affects="leverage_tier / FIREMAN")

    assert report["status"] == "FAIL"
    assert "WARNING" in capsys.readouterr().out


# ── wiring (review round 2026-08-01) ─────────────────────────────────────────
# The four tests above call report_join_coverage() directly. Deleting BOTH
# production call sites left them 100% green — i.e. the entire deliverable of
# a BLOCKING finding was unpinned, and the silent failure it was raised for
# (leverage_tier / FIREMAN emitted as complete off a 62.8-day-old, 79.5%-
# covered cache) could return with zero test objection.

def test_both_production_joins_report_their_coverage():
    """Every cache join that can silently degrade reports its coverage: the
    FanGraphs leverage join (feeds leverage_tier / HIGH_LEVERAGE) and the
    Baseball-Reference IR join (feeds FIREMAN) each invoke the reporter, and
    each names the columns it affects — so a degraded join can never be
    emitted as if it were complete.

    DISCLOSURE (review 2026-08-01): this is an AST call-site pin, not a
    behavioral drive of build_ratings_panel() (which needs the full cache
    stack). It was mutation-verified on 2026-08-01: deleting the gmli call
    site fails this test. A behavioral end-to-end companion needs a synthetic
    full-cache fixture — recorded in the audit backlog."""
    import ast
    src = Path(rpa.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
             == "report_join_coverage"]
    assert len(calls) >= 2, (
        "both cache joins must report coverage — a missing call is exactly "
        "the silent degradation this guard exists for")
    affected = set()
    for c in calls:
        for kw in c.keywords:
            if kw.arg == "affects" and isinstance(kw.value, ast.Constant):
                affected.add(kw.value.value)
    joined = " ".join(affected).lower()
    assert "leverage_tier" in joined, "the leverage join must declare its columns"
    assert "fireman" in joined, "the IR join must declare its columns"


def test_all_nan_year_column_does_not_crash_the_build(tmp_path):
    """A visibility guard must never abort the build it was added to observe:
    when to_numeric coerces a malformed year column entirely to NaN the panel
    is non-empty but has no usable years, and `years[-1]` raised IndexError.
    Report FAIL instead — that IS the signal."""
    panel = pd.DataFrame({"year": [np.nan, np.nan], "gmli": [1.0, np.nan]})
    cache = _cache(tmp_path)
    out = rpa.report_join_coverage(panel, col="gmli", cache_path=cache,
                                   label="FanGraphs leverage",
                                   affects="leverage_tier / HIGH_LEVERAGE")
    assert out["status"] == "FAIL"
    assert out["year"] is None and out["rate"] is None
