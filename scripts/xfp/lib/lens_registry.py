"""lens_registry — the authoritative declaration of every triangulate CONTEXT lens.

One place that says, per lens family: exactly which batch columns it emits, whether it
is validated vs experimental, and (load-bearing) that it is CONTEXT-ONLY. "Context-only"
means the lens NEVER becomes a projection-model feature — it may inform the displayed
verdict/conviction, but it can never move the rh3/rp3/rprs2/blended headline number
(CLAUDE.md #13; validated non-additive 2026-06-11, lens_value_add_2026-06-11.md).

This registry exists so the invariant is ENFORCED, not just remembered:
tests/test_lens_context_only.py cross-checks it both directions —
  (1) no model feature list (RH3_FEATS / RP3_FEATS / RPRS2 feats) may contain a
      context-only lens column (a lens can't leak into the projection), and
  (2) every column the flatten_lenses/flatten_actuals/flatten_extra serializers emit
      must be a registered context-only column (no rogue column escapes the contract).

Exact column names (not name prefixes) are used deliberately: a prefix like "split_"
would wrongly swallow the legitimate model feature "split_day", and "tto_" would miss
"tto1_rate". Adding/renaming a serialized column => update the family here, or the
coverage test fails loudly.
"""
from __future__ import annotations

# family -> metadata. `columns` are the EXACT batch-column names the family emits.
LENS_FAMILIES: dict[str, dict] = {
    "platoon_splits": {
        "columns": ("split_rate_vs_L", "split_rate_vs_R", "split_lift_vs_L_pct",
                    "split_lift_vs_R_pct", "split_pa_vs_L", "split_pa_vs_R", "split_dominant"),
        "context_only": True, "validated": True,
        "desc": "xwOBA vs LHP/RHP (H) / LHB/RHB (SP)",
        "accessor": "lib.splits", "validation_ref": None,
    },
    "expected_vs_actual": {
        "columns": ("xstat_xwoba", "xstat_woba", "xstat_gap", "xstat_regression",
                    "xstat_vs_L_xwoba", "xstat_vs_L_woba", "xstat_vs_L_reg", "xstat_vs_L_pa",
                    "xstat_vs_R_xwoba", "xstat_vs_R_woba", "xstat_vs_R_reg", "xstat_vs_R_pa"),
        "context_only": True, "validated": True,
        "desc": "expected-vs-actual wOBA (luck), overall + by split",
        "accessor": "lib.expected_stats", "validation_ref": None,
    },
    "home_away": {
        "columns": ("ha_rate_home", "ha_rate_away", "ha_lift_home_pct", "ha_lift_away_pct",
                    "ha_dominant"),
        "context_only": True, "validated": True,
        "desc": "home/road xwOBA split",
        "accessor": "lib.home_away", "validation_ref": None,
    },
    "tto_decay": {
        "columns": ("tto_tier", "tto_penalty", "tto1_rate", "tto3_rate"),
        "context_only": True, "validated": True,
        "desc": "times-through-order decay (SP)",
        "accessor": "lib.lineup_pass", "validation_ref": None,
    },
    "boom_bust": {
        "columns": ("bb_window", "bb_n", "bb_mean", "bb_std", "bb_boom_pct", "bb_bust_pct",
                    "bb_boom_ci", "bb_bust_ci", "bb_rate_precise",
                    "bb_min", "bb_max", "bb_l3_mean", "bb_trend", "bb_last"),
        "context_only": True, "validated": True,
        "desc": ("realized boom/bust actuals (boxscore store); rates carry n + a "
                 "95% Wilson CI and bb_rate_precise — never RANK on a rate with "
                 "bb_rate_precise False"),
        "accessor": "lib.boom_bust", "validation_ref": None,
    },
    "pl_streamer_tier": {
        "columns": ("pl_stream_rank", "pl_stream_tier"),
        "context_only": True, "validated": True,
        "desc": ("Pitcher List daily streamer tier/rank. MEASURED on 2,016 "
                 "pitcher-days / 86 slates: tiers are monotonic (Auto-Start "
                 "13.86 FP -> Do Not Start 8.04) and Auto beats Probably by "
                 "+2.68 FP [CI +1.62,+3.71]. It also adds signal BEYOND rp3 "
                 "(partial r +0.068 [+0.028,+0.107]) — but a 50/50 blend gains "
                 "only +0.03 FP at top-1/slate, the decision that matters, so "
                 "this stays context-only pending a Rule-9 run."),
        "accessor": "backfill_pl_streamers", "validation_ref":
            "pl_streamer_tier_2026-08-07.md",
    },
    "in_season_trajectory": {
        "columns": ("traj_n", "traj_cadence", "traj_first_label", "traj_last_label",
                    "traj_ovr_first", "traj_ovr_last", "traj_ovr_delta", "traj_last_archetype",
                    "traj_dom_deltas", "traj_dom_last"),
        "context_only": True, "validated": True,
        "desc": "in-season archetype OVERALL + domain trajectory",
        "accessor": "lib.season_snapshots", "validation_ref": None,
    },
    "stuff_plus": {
        "columns": ("stuff_plus", "stuff_proj_ros_fp", "stuff_breakout_gap"),
        "context_only": True, "validated": True,
        "desc": "FanGraphs Stuff+ level + RoS proj + breakout gap (SP)",
        "accessor": "lib.extra_lenses.stuff_lens",
        "validation_ref": "fg_pitch_modeling_inseason_2026-06-06.md",
    },
    "sp_floor": {
        "columns": ("floor_bust_prob", "floor_tier"),
        "context_only": True, "validated": True,
        "desc": "per-start bust probability + SAFE/MODERATE/RISKY tier (SP)",
        "accessor": "lib.extra_lenses.floor_lens",
        "validation_ref": "sp_floor_model_2026-06-06.md",
    },
    "floor_adjusted": {
        "columns": ("floor_adj_xfp", "floor_adj_penalty", "floor_flag"),
        "context_only": True, "validated": True,
        "desc": "risk-aware FP/start (rp3 mean docked/credited by sp_floor bust risk) "
                "+ mean-vs-floor conflict flag (SP). DECISION-LAYER, headline unchanged.",
        "accessor": "lib.extra_lenses.floor_adjusted_xfp",
        "validation_ref": "floor_adjusted_ranking_2026-06-24.md",
    },
    "stuff_command": {
        "columns": ("stuff_cmd_tag", "stuff_cmd_swstr_d", "stuff_cmd_velo_d",
                    "stuff_cmd_bb_d", "stuff_cmd_yoy_swstr_d"),
        "context_only": True, "experimental": True,
        "desc": "within-season STUFF-vs-COMMAND divergence (SP): STUFF-DECLINE (structural, "
                "persistent — Framber) vs COMMAND-WATCH (reversible wobble — Soriano).",
        "accessor": "lib.extra_lenses.stuff_command_lens",
        "validation_ref": "floor_adjusted_ranking_2026-06-24.md",
    },
    "next_start": {
        "columns": ("next_start_date", "next_opp", "next_venue", "next_park_env", "next_opp_env"),
        "context_only": True, "experimental": True,
        "desc": "next-start matchup CONTEXT (SP): venue/opp + park-environment (Coors=EXTREME-"
                "HITTER) + opp tier. A bench-decision FLAG — validated NON-predictive as a "
                "projection multiplier (per-start noise swamps it), so context-only by design.",
        "accessor": "lib.extra_lenses.next_start_lens",
        "validation_ref": "next_start_park_2026-06-24.md",
    },
    "physical_trend": {
        "columns": ("trend_tag",),
        "context_only": True, "validated": True,
        "desc": "bat-speed/attack-angle (H) or FB velo (P) physical trend",
        "accessor": "lib.extra_lenses.trend_lens",
        "validation_ref": "early_season_bat_speed_2026-06-16.md",
    },
    "shadow_scout": {
        "columns": ("shadow_grade", "shadow_verdict"),
        "context_only": True, "experimental": True,
        "desc": "20-80 process grade for unranked SPs (no rp3/archetype)",
        "accessor": "lib.extra_lenses.shadow_lens",
        "validation_ref": None,
    },
}

# Every context-only column the serializers may emit.
CONTEXT_ONLY_COLUMNS: frozenset[str] = frozenset(
    c for fam in LENS_FAMILIES.values() if fam.get("context_only")
    for c in fam["columns"]
)


def is_context_only_column(name: str) -> bool:
    """True if a batch column is a registered context-only lens column."""
    return name in CONTEXT_ONLY_COLUMNS


def family_of(column: str) -> str | None:
    for fam, meta in LENS_FAMILIES.items():
        if column in meta["columns"]:
            return fam
    return None


def validated_families() -> list[str]:
    return [k for k, v in LENS_FAMILIES.items() if v.get("validated")]


def experimental_families() -> list[str]:
    return [k for k, v in LENS_FAMILIES.items() if v.get("experimental")]
