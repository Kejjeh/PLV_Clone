"""il_marcel — the projection rp3 declines to make for an IL'd starter.

rp3 tags these arms `marcel_il` and returns a SUPPRESSED prior with gs_to=0.
That is not a forecast, it is a "no signal" placeholder — and ranking a stash
pool by it put Corbin Burnes below replacement level on the 2026-08-05 board.

Validated 2026-08-05 on 272 pitcher-seasons / 122 pitchers (2024-2026),
predicting season Y from PRIOR seasons only, GS-weighted:

    last season only   wRMSE 4.236   wMAE 3.131   corr 0.146
    league mean        wRMSE 3.540   wMAE 2.761   --
    il_marcel          wRMSE 3.085   wMAE 2.310   corr 0.174

and the confidence tiers order correctly (HIGH wRMSE 2.714 / corr 0.284 vs
LOW 3.700 / corr 0.038).
"""
import pytest

IM = pytest.importorskip("scripts.xfp.lib.il_marcel")


def line(season, gs, fp_per_start):
    """A SeasonLine engineered to land on an exact FP/start.

    FP = K + IP*3.3 - H - 2*ER - BB - HBP; hold everything at zero but K, so
    K = fp_per_start * gs.
    """
    return IM.SeasonLine(season=season, gs=gs, ip=0.0,
                         k=int(round(fp_per_start * gs)), h=0, er=0, bb=0, hbp=0)


def test_fp_per_start_uses_the_brownu_formula():
    s = IM.SeasonLine(season=2025, gs=2, ip=12.0, k=14, h=8, er=3, bb=2, hbp=1)
    # 14 + 39.6 - 8 - 6 - 2 - 1 = 36.6 over 2 starts
    assert s.fp == pytest.approx(36.6)
    assert s.fp_per_start == pytest.approx(18.3)


def test_a_pitcher_with_no_history_gets_league_average_not_zero():
    """The failure mode being replaced: an unknown must not project as bad."""
    est = IM.project([], as_of_season=2026)
    assert est.fp_per_start == IM.LEAGUE_FP_PER_START
    assert est.confidence == 'NONE'


def test_the_current_season_is_never_used():
    """An IL'd pitcher's current season is the sample the injury destroyed.
    Letting it in would re-import the very suppression this module exists to
    route around."""
    hist = [line(2026, 30, 20.0), line(2025, 30, 11.0)]
    est = IM.project(hist, as_of_season=2026)
    assert est.fp_per_start < 12.0, 'the 2026 line leaked into a 2026 projection'


def test_recent_seasons_outweigh_older_ones():
    recent_good = IM.project([line(2025, 30, 16.0), line(2023, 30, 8.0)],
                             as_of_season=2026)
    recent_bad = IM.project([line(2025, 30, 8.0), line(2023, 30, 16.0)],
                            as_of_season=2026)
    assert recent_good.fp_per_start > recent_bad.fp_per_start


def test_a_cameo_cannot_outvote_a_full_season():
    """4 dominant starts must not erase 30 mediocre ones — the weighting is by
    GS as well as by recency."""
    est = IM.project([line(2025, 4, 25.0), line(2024, 30, 10.0)],
                     as_of_season=2026)
    assert est.fp_per_start < 14.0


def test_thin_history_regresses_hard_toward_league_average():
    thin = IM.project([line(2025, 5, 20.0)], as_of_season=2026)
    thick = IM.project([line(2025, 32, 20.0)], as_of_season=2026)
    assert thin.fp_per_start < thick.fp_per_start
    assert abs(thin.fp_per_start - IM.LEAGUE_FP_PER_START) < \
        abs(thick.fp_per_start - IM.LEAGUE_FP_PER_START)


def test_regression_pulls_from_both_directions():
    """A bad-but-thin record must be pulled UP, not just good ones down."""
    est = IM.project([line(2025, 6, 3.0)], as_of_season=2026)
    assert est.fp_per_start > 3.0


def test_confidence_tracks_effective_sample():
    """Boundaries are the ones the 2026-08-05 validation scored, and they came
    out correctly ordered (HIGH wRMSE 2.714 / LOW 3.700), so they are pinned
    rather than tuned. Note ONE full season is MEDIUM -- effective starts is
    recency-weighted GS normalised by the top weight, so 32 GS reads as 32 and
    HIGH (>=45) needs more than a single year of evidence."""
    two_full = [line(2025, 32, 12.0), line(2024, 32, 12.0)]
    assert IM.project(two_full, as_of_season=2026).confidence == 'HIGH'
    assert IM.project([line(2025, 32, 12.0)], as_of_season=2026).confidence == 'MEDIUM'
    assert IM.project([line(2025, 22, 12.0)], as_of_season=2026).confidence == 'MEDIUM'
    assert IM.project([line(2025, 10, 12.0)], as_of_season=2026).confidence == 'LOW'


def test_the_raw_estimate_is_reported_beside_the_regressed_one():
    """A caller comparing two arms needs to see how much of the number is the
    pitcher and how much is the prior."""
    est = IM.project([line(2025, 30, 16.0)], as_of_season=2026)
    assert est.raw_fp_per_start == pytest.approx(16.0, abs=0.05)
    assert est.fp_per_start < est.raw_fp_per_start


def test_preinjury_starts_this_year_move_the_projection():
    """8 strong starts before the injury is the freshest evidence there is, and
    rp3 discards it."""
    base = IM.project([line(2025, 30, 11.0)], as_of_season=2026)
    hot = IM.blend_current(base, line(2026, 8, 20.0))
    cold = IM.blend_current(base, line(2026, 8, 4.0))
    assert hot.fp_per_start > base.fp_per_start > cold.fp_per_start


def test_blending_nothing_is_a_no_op():
    base = IM.project([line(2025, 30, 13.0)], as_of_season=2026)
    assert IM.blend_current(base, None) == base
    assert IM.blend_current(base, line(2026, 0, 0.0)) == base


def test_blending_raises_effective_sample_and_can_lift_confidence():
    base = IM.project([line(2025, 18, 12.0)], as_of_season=2026)
    blended = IM.blend_current(base, line(2026, 9, 12.0))
    assert blended.effective_starts > base.effective_starts


# -- hitters ------------------------------------------------------------------
# Validated 2026-08-05 on 447 hitter-seasons / 169 hitters (2024-2026),
# predicting year Y from prior years only, PA-weighted:
#     league mean (.484)  wRMSE 0.1286  wMAE 0.0999
#     last season only    wRMSE 0.1111  wMAE 0.0876  corr 0.383
#     project_hitter      wRMSE 0.0971  wMAE 0.0781  corr 0.402
# Hitters project markedly better than pitchers (0.402 vs 0.174), which is the
# expected shape -- year-to-year hitting is the more stable signal.

def bat(season, pa, fp_per_pa, g=None):
    """A BatterSeason engineered onto an exact FP/PA. FP = R+TB+RBI+BB+HBP+SB-K;
    hold all but TB at zero so TB carries the rate."""
    return IM.BatterSeason(season=season, g=g or max(pa // 4, 1), pa=pa,
                           r=0, tb=int(round(fp_per_pa * pa)), rbi=0,
                           bb=0, hbp=0, sb=0, k=0)


def test_hitter_fp_uses_the_brownu_formula():
    s = IM.BatterSeason(season=2025, g=100, pa=400, r=60, tb=180, rbi=55,
                        bb=40, hbp=5, sb=10, k=90)
    assert s.fp == pytest.approx(260)
    assert s.fp_per_pa == pytest.approx(0.65)


def test_hitter_with_no_history_gets_league_average():
    est = IM.project_hitter([], as_of_season=2026)
    assert est.fp_per_start == IM.LEAGUE_FP_PER_PA
    assert est.confidence == "NONE"


def test_hitter_current_season_is_never_used():
    est = IM.project_hitter([bat(2026, 600, 0.80), bat(2025, 600, 0.48)],
                            as_of_season=2026)
    assert est.fp_per_start < 0.55


def test_hitter_thin_history_regresses_toward_league():
    thin = IM.project_hitter([bat(2025, 60, 0.80)], as_of_season=2026)
    thick = IM.project_hitter([bat(2025, 650, 0.80)], as_of_season=2026)
    assert thin.fp_per_start < thick.fp_per_start
    assert abs(thin.fp_per_start - IM.LEAGUE_FP_PER_PA) < \
        abs(thick.fp_per_start - IM.LEAGUE_FP_PER_PA)


def test_hitter_recency_beats_older_seasons():
    good_now = IM.project_hitter([bat(2025, 600, 0.70), bat(2023, 600, 0.35)],
                                 as_of_season=2026)
    bad_now = IM.project_hitter([bat(2025, 600, 0.35), bat(2023, 600, 0.70)],
                                as_of_season=2026)
    assert good_now.fp_per_start > bad_now.fp_per_start


def test_hitter_preinjury_pa_this_year_moves_the_projection():
    base = IM.project_hitter([bat(2025, 600, 0.48)], as_of_season=2026)
    hot = IM.blend_current_hitter(base, bat(2026, 150, 0.75))
    cold = IM.blend_current_hitter(base, bat(2026, 150, 0.25))
    assert hot.fp_per_start > base.fp_per_start > cold.fp_per_start
    assert IM.blend_current_hitter(base, None) == base
