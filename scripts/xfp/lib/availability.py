"""availability — IL-return / role-state volume overlay (built TDD 2026-08-12).

WHY THIS EXISTS. The validated volume models project a player's season pace
forward. That is correct for steady-state players and validated to beat naive
pace — but it is structurally blind to STATE CHANGES: an IL'd player's pace
carries months of zeros forward (Oneil Cruz 2026-08-12: pace said 2.25 PA/tg,
his when-active rate was 4.42 with activation two days out). Every projection
miss in the 2026-08-12 session audit was an availability error, not a rate
error. This module owns exactly that seam.

CONTRACT. Pure function over a plain player dict — no IO, no network. Callers
(board builders) assemble the dict from live sources. The overlay:
  - passes steady ACTIVE players through UNCHANGED (the volume model owns them);
  - replaces pace-forward volume for IL'd players with
    when-active rate x team games after the return date;
  - never fabricates: an IL'd player with no return date stays on model volume,
    flagged, rather than getting an invented number.

GATE STATUS (Study C verdict, 2026-08-12 — prereg_availability_suite_2026-08-12.md):
**FAILED for automatic shipping — DIAGNOSTIC ONLY.** The realistic variant
(estimated return = placement + min stint + 10d) WORSENED median |RoS PA error|
by 83.8% vs pace-forward (79.7 vs 43.4 PA) on 683 player-asof rows 2021-2025,
because estimated dates + full-time-after-return overpredict. Boards therefore
keep PACE-FORWARD as the headline volume. The ORACLE variant (true return date)
cut median error 25.6% and lifted Spearman 0.384→0.684 — the construction is
sound when the date is right, so a PROSPECTIVE study of the ESPN-return-date
variant is registered (prereg_overlay_prospective_2026-08-12.md). Until it
settles, every consumer must label overlay outputs as diagnostic.
"""
from __future__ import annotations

from datetime import date

ROTATION_LEN = 5               # team games per rotation turn
SP_RAMP_DISCOUNT_STARTS = 0.6  # effective starts lost to stretch-out outings
ROLE_SHRINK_PA_TG = 0.5        # recent usage this far under model -> flag


def pace_forward_ros_fp(*, rate: float | None, per_teamgame: float | None,
                        team_games_remaining: int) -> float | None:
    """The HEADLINE construction: rate x volume x remaining team games.

    This is the shipped, gate-passing quantity — `RoS TOTALS = rate x volume`
    (validated 2026-07-09), with volume coming from the validated companions
    (`proj_ros_pa_per_teamgame` for hitters, `proj_ros_gs_per_teamgame` for
    starters). It lives here, next to the overlay it is deliberately NOT, so
    that no caller can reach for one thinking it got the other.

    Why it is a shared primitive rather than two inline expressions (audit
    2026-08-14): the board built hitter headlines this way but built SP
    headlines from the availability overlay — IL-return lattice plus the 0.6
    ramp discount — so one column carried two different quantities and an
    SP-vs-hitter comparison on it compared apples to a gate that had failed.
    The failed Study C gate applies to the METHOD, not to one bucket.

    Returns None when either input is missing: a league-average fill would be
    an invented projection wearing a real player's name.
    """
    if rate is None or per_teamgame is None:
        return None
    if per_teamgame < 0 or team_games_remaining < 0:
        raise ValueError(
            f"pace_forward_ros_fp: negative input (per_teamgame={per_teamgame}, "
            f"team_games_remaining={team_games_remaining})")
    return float(rate) * float(per_teamgame) * int(team_games_remaining)


def when_active_pa_rate(statcast_df, mlbam: int, min_games: int = 1) -> float | None:
    """PA per game ACTUALLY PLAYED, from pitch-level statcast rows.

    This is the rate the pace-forward construction destroys for IL'd players:
    Cruz's season pace (2.25 PA/teamgame) included two months of zeros; his
    per-game-played rate was 4.42. PA = distinct (game_pk, at_bat_number) for
    this batter; games = distinct game_pk he appeared in.
    """
    d = statcast_df[statcast_df["batter"] == mlbam]
    games = d["game_pk"].nunique()
    if games < min_games:
        return None
    pa = d.drop_duplicates(["game_pk", "at_bat_number"]).shape[0]
    return pa / games


def ros_volume(player: dict, *, team_remaining_dates: list[date], today: date) -> dict:
    """Rest-of-season volume for one player, availability-aware.

    player keys (H bucket): bucket='H', status 'ACTIVE'|'IL',
      model_pa_per_teamgame, when_active_pa_per_game, return_date (date|None).
    `team_remaining_dates`: the player's MLB team's remaining game dates —
    the module counts games ON or after a return date itself, so callers
    never hand-count schedule fractions.
    Returns {proj_ros_pa, frac_available, source, flags}.
    """
    n_remaining = len(team_remaining_dates)
    if player["status"] == "IL" and player.get("return_date") is not None:
        games_after = sum(1 for d in team_remaining_dates if d >= player["return_date"])
        frac = games_after / n_remaining if n_remaining else 0.0
        if player["bucket"] == "SP":
            # Rotation share: one start per ROTATION_LEN team games, less a
            # ramp discount for stretch-out outings (assumption pending the
            # post-IL ramp study — see prereg_availability_suite_2026-08-12).
            raw_starts = games_after / ROTATION_LEN
            return {
                "proj_ros_starts": max(0.0, raw_starts - SP_RAMP_DISCOUNT_STARTS),
                "frac_available": frac,
                "source": "il_return_overlay",
                "flags": ["rehab_ramp"],
            }
        return {
            "proj_ros_pa": player["when_active_pa_per_game"] * games_after,
            "frac_available": frac,
            "source": "il_return_overlay",
            "flags": [],
        }
    flags = []
    if player["status"] == "IL":
        # IL'd with no return date: never fabricate a date — keep the model's
        # number but tell the board the volume is availability-uncertain.
        flags.append("no_return_date")
    recent = player.get("recent_pa_per_teamgame")
    if (player["status"] == "ACTIVE" and recent is not None
            and player["model_pa_per_teamgame"] - recent >= ROLE_SHRINK_PA_TG):
        # The Muncy pattern: role decisions are sticky manager choices, so a
        # sustained recent-usage gap is a genuine availability signal — but v1
        # only FLAGS it. Repricing volume off a 2-week window is exactly the
        # recency trap the hitter-rate studies killed; a blend ships only if
        # the Study-C-style backtest earns it.
        flags.append("role_shrink")
    return {
        "proj_ros_pa": player["model_pa_per_teamgame"] * n_remaining,
        "frac_available": 1.0,
        "source": "model_passthrough",
        "flags": flags,
    }
