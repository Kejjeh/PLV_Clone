"""
/triangulate engine — combine PL rank + our model (rh3/rp3/rprs2) + archetype model
into one unified player profile.

Usage:
    python scripts/xfp/run_triangulate.py "Aaron Judge"
    python scripts/xfp/run_triangulate.py "Reid Detmers" "Ryan Weathers" "Ryne Nelson"
    python scripts/xfp/run_triangulate.py --bucket SP "Reid Detmers"

Thin CLI shell. Analytical logic lives in `scripts/xfp/lib/`.
Other skills should import from `scripts.xfp.lib.triangulate_core` directly.
"""

from __future__ import annotations
import argparse, io, json, os, sys
from collections import Counter
from datetime import datetime
import pandas as pd

# Force UTF-8 for stdout on Windows so arrows / accents don't crash
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Make `scripts.xfp.lib.*` importable when this file is run as a script
# (python scripts/xfp/run_triangulate.py). External skills that already have
# the project root on sys.path get this for free.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.xfp.lib.bucket_dispatch import resolve_player
from scripts.xfp.lib.pl_cache import pl_rank, pl_streamer_rank, _warn_stale_caches, print_refresh_instructions
from scripts.xfp.lib.triangulate_core import (
    model_row, archetype_row, synthesize, apply_overrides,
    consolidate_verdict, compute_confidence, build_watch_list, il_caveat,
    flatten_lenses, compute_actuals, flatten_actuals,
)
from scripts.xfp.lib.injury_status import il_status_for as _il_status_for
from scripts.xfp.lib.snapshots import write_snapshot, write_diff, truncate_report_for_stdout

# ---------- presentation layer (stays in the CLI) ----------

def format_card(player, pl_main, pl_main_date, pl_stream, pl_stream_date, model, arche, verdict, rationale,
                confidence=None, n_aligned=None, n_available=None, watch_list=None, verdict_top=None, reason_tag=None,
                actuals=None):
    lines = []
    bucket = player['bucket']
    lines.append(f"\n## {player['display_name']} ({bucket}) — {verdict}\n")
    lines.append(f"*{rationale}*\n")
    if confidence is not None and n_aligned is not None and n_available is not None:
        lines.append(f"**Confidence:** {confidence:.2f} ({n_aligned} of {n_available} signals agree) | verdict_top={verdict_top} | reason_tag={reason_tag}\n")

    # Physical-trend lens (display/conviction only — never moves the verdict or
    # the headline projection, CLAUDE.md #13). Hitter = 3-axis bat speed + attack
    # angle + fast-swing% (early-warning, stabilizes fast); pitcher = FB velo.
    # Engine + validation: scripts/xfp/lib/trend_signal.py,
    # data/research/validation_runs/early_season_bat_speed_2026-06-16.md.
    try:
        from scripts.xfp.lib.trend_signal import trend_for_mlbam
        _trend_tag, _ = trend_for_mlbam(int(player['id']), bucket)
        if _trend_tag:
            lines.append(f"**Physical trend:** {_trend_tag}\n")
    except Exception:
        pass

    # Blended xFP (Phase 3, additive — does NOT override verdict).
    try:
        from scripts.xfp.lib.blend_score import compute_blended_xfp
        blend = compute_blended_xfp(
            player_name=player['display_name'],
            player_type=bucket,
            mlbam_id=int(player['id']),
        )
        if blend.get('blended_xfp') is not None:
            unit = blend.get('display_unit') or ''
            ct = blend.get('confidence_tier') or 'unknown'
            # Phase 1 RP card display (2026-06-05): multi-component headline
            # surfacing ROS / per-G / rep_delta / role characterization.
            # H and SP cards remain UNCHANGED.
            if bucket == 'RP':
                ros = blend.get('ros_estimate')
                rep_d = blend.get('replacement_delta')
                role_char = blend.get('role_characterization') or 'Mixed role'
                vtier = blend.get('value_tier') or 'UNAVAILABLE'
                if ros is not None and rep_d is not None:
                    lines.append(
                        f"**RP Production:** ROS {ros:.0f} · "
                        f"{blend['blended_xfp']:.2f} FP/G · "
                        f"rep_delta {rep_d:+.1f} → {vtier} · "
                        f"{role_char}   ← confidence: {ct}\n"
                    )
                    # Honesty note for setup/holds-driven ADD/HOLD value.
                    if vtier in ('ADD', 'HOLD') and role_char == 'Setup / HLDS':
                        lines.append(
                            "*Value driven by holds (HLD×2 in BrownU). Per-G blend is "
                            "unit-comparable but narrow-range for RPs; ROS + rep_delta "
                            "carry the role/volume signal.*\n"
                        )
                    # Phase 2 — Live marginal vs same-role best FA today.
                    lm = blend.get('live_marginal')
                    lm_tier = blend.get('live_value_tier')
                    snap_label = blend.get('snapshot_label')
                    age_h = blend.get('snapshot_age_hours')
                    role_lag = blend.get('role') or 'role?'
                    if lm is not None:
                        best_nm = blend.get('best_fa_at_role') or '?'
                        best_ros = blend.get('best_fa_ros')
                        bros_s = f"{best_ros:.0f}" if best_ros is not None else "?"
                        age_s = f"{age_h:.1f}h" if age_h is not None else "?"
                        lines.append(
                            f"**Live marginal:** {lm:+.1f} FP vs best FA at "
                            f"{role_lag} ({best_nm}, ROS {bros_s}) → {lm_tier} · "
                            f"snapshot {snap_label} (age {age_s})\n"
                        )
                    else:
                        reason = blend.get('live_marginal_note') or 'unknown'
                        lines.append(
                            f"**Live marginal:** unavailable ({reason}, "
                            f"snapshot {snap_label or 'none'})\n"
                        )
                else:
                    # Fallback: rprs2 ROS unavailable.
                    lines.append(
                        f"**Blended xFP (per-G only):** {blend['blended_xfp']:.2f} FP/G "
                        f"[95% CI {blend['ci_lower_95']:.2f}-{blend['ci_upper_95']:.2f}] "
                        f"← confidence: {ct} · *rprs2 ROS unavailable*\n"
                    )
            else:
                lines.append(
                    f"**Blended xFP:** {blend['blended_xfp']:.2f} {unit} "
                    f"(95% CI [{blend['ci_lower_95']:.2f}, {blend['ci_upper_95']:.2f}]) "
                    f"  ← confidence: {ct}\n"
                )
                # Phase 2.5 (2026-06-06): live marginal for H and SP.
                lm = blend.get('live_marginal')
                lm_tier = blend.get('live_value_tier')
                snap_label = blend.get('snapshot_label')
                age_h = blend.get('snapshot_age_hours')
                if lm is not None:
                    best_nm = (blend.get('best_fa_at_position')
                               or blend.get('best_fa_at_role') or '?')
                    best_ros = blend.get('best_fa_ros')
                    bros_s = f"{best_ros:.0f}" if best_ros is not None else "?"
                    age_s = f"{age_h:.1f}h" if age_h is not None else "?"
                    if bucket == 'H':
                        pos_lbl = blend.get('position') or 'pos?'
                        lines.append(
                            f"**Live marginal:** {lm:+.1f} FP vs best FA "
                            f"{pos_lbl} ({best_nm}, ROS {bros_s}) → {lm_tier} · "
                            f"snapshot {snap_label} (age {age_s})\n"
                        )
                    else:  # SP
                        lines.append(
                            f"**Live marginal:** {lm:+.1f} FP vs best FA SP "
                            f"({best_nm}, ROS {bros_s}) → {lm_tier} · "
                            f"snapshot {snap_label} (age {age_s})\n"
                        )
                else:
                    reason = blend.get('live_marginal_note') or 'unknown'
                    lines.append(
                        f"**Live marginal:** unavailable ({reason}, "
                        f"snapshot {snap_label or 'none'})\n"
                    )
            for n in blend.get('notes') or []:
                lines.append(f"*{n}*\n")
    except Exception as _be:
        lines.append(f"*blend unavailable: {type(_be).__name__}*\n")
    if watch_list:
        lines.append(f"**Watch list:** " + "; ".join(watch_list) + "\n")

    pl_label = {'H': 'PL Top150', 'SP': 'PL Top100', 'RP': 'PL Closers'}[bucket]
    model_label = {'H': 'rh3', 'SP': 'rp3', 'RP': 'rprs2'}[bucket]
    lines.append("| Lens | Rank | Headline | Detail |")
    lines.append("|---|---|---|---|")
    pl_show = f"#{pl_main}" if isinstance(pl_main, int) else pl_main
    lines.append(f"| **{pl_label}** | {pl_show} | — | cache {pl_main_date or 'MISSING'} |")
    if bucket == 'SP' and pl_stream != '—':
        lines.append(f"| **PL Streamer ({pl_stream_date})** | {pl_stream} | vs {pl_stream_date or '?'} | — |")
    if model['rank'] != '—':
        proj = model['proj']
        # SP: append floor/ceiling band to the headline when available.
        if bucket == 'SP' and proj is not None and model.get('p25') is not None and model.get('p75') is not None:
            proj_s = f"{proj:.2f} ({model['p25']:.2f}-{model['p75']:.2f}) {model['proj_label']}"
        else:
            proj_s = f"{proj:.2f} {model['proj_label']}" if proj is not None else '—'
        sig = f"signal={model['signal']}" if bucket == 'RP' else ''
        rep = f"rep_d={model['rep_delta']:+.2f}" if model['rep_delta'] is not None else ''
        recf = f"recform={model['recform']:+.3f}" if model.get('recform') is not None else ''
        # SP: surface data quality tag alongside other detail tokens.
        dq = ''
        if bucket == 'SP' and model.get('data_quality_tag'):
            dq = f"dq={model['data_quality_tag']}"
        # SP boom-stack tag (validated 2026-06-03, SHIP_AS_TAG, tier-aware all SPs).
        bs_tok = ''
        if bucket == 'SP' and model.get('boom_stack') is not None:
            bs_val = model['boom_stack']
            br = model.get('boom_rate_expected')
            bu = model.get('boom_bust_rate_expected')
            tier = model.get('boom_tier')
            parts = [f"boom_stack={bs_val}/4"]
            if tier:
                parts.append(f"[tier={tier}]")
            if br is not None and bu is not None:
                parts.append(f"(boom%~{br*100:.1f}%, bust%~{bu*100:.1f}%)")
            elif br is not None:
                parts.append(f"(boom%~{br*100:.1f}%)")
            # HIGH-K ARM badge — INDEPENDENT standalone tag (validated 2026-06-03).
            # Compounds with boom_stack rather than replacing a component.
            if model.get('is_high_k_arm'):
                z = model.get('high_k_z_score')
                z_s = f" z={z:+.2f}" if isinstance(z, (int, float)) else ''
                parts.append(f"🔥HIGH-K{z_s}")
            # RECFORM HOT/COLD badge (Phase 3 Agent C, 2026-06-05).
            # DISPLAY ONLY — trailing-5-start fp_proxy z; absorbed by the
            # blend (r=+0.69 with fp_per_start_to), so this is context only.
            rf_tag = model.get('recform_tag')
            if rf_tag in ('HOT', 'COLD'):
                rfz = model.get('recform_z')
                rfz_s = f" z={rfz:+.2f}" if isinstance(rfz, (int, float)) else ''
                rf_icon = '🔥' if rf_tag == 'HOT' else '🧊'
                parts.append(f"{rf_icon}RECFORM {rf_tag}{rfz_s}")
            # CATCHER FRAMING badge (validated 2026-06-03, SHIP_AS_DISPLAY_TAG).
            # Independent of boom_stack + HIGH-K — pure context layer.
            if model.get('is_elite_framer'):
                parts.append("🧊ELITE FRAMER")
            elif model.get('is_framing_tax'):
                parts.append("⚠FRAMING TAX")
            # IL_RETURN salvage tag (validated 2026-06-03, +2.93 pp bust lift).
            # Standalone display tag — never overrides verdict.
            if model.get('is_first_back_long_il'):
                ild = model.get('il_return_days_since_last_start')
                ild_s = f" ({ild}d)" if isinstance(ild, int) else ''
                parts.append(f"🏥IL RETURN{ild_s}")
            bs_tok = ' '.join(parts)
        # Hitter boom-stack advisory tag (validated 2026-06-03, SHIP-CAUTIOUS).
        hbs_tok = ''
        if bucket == 'H' and model.get('hitter_boom_stack') is not None:
            hbs_val = model['hitter_boom_stack']
            hbr = model.get('hitter_boom_rate_expected')
            if hbr is not None:
                hbs_tok = f"boom_stack={hbs_val}/4 (boom%~{hbr*100:.1f}%)"
            else:
                hbs_tok = f"boom_stack={hbs_val}/4"
        # sp-decline velo-trajectory token (vYoY/vIn/v2y + SEVERE/LOW-VELO tier).
        # Display/conviction lens only — never moves the rp3 headline (CLAUDE.md #13).
        velo_tok = ''
        if bucket == 'SP':
            _fm = {'VV': '▼▼', 'v': '▼', '^': '▲'}
            vparts = []
            for key, fkey, lbl in (('velo_yoy', 'velo_yoy_flag', 'vYoY'),
                                   ('velo_in', 'velo_in_flag', 'vIn'),
                                   ('velo_2y', 'velo_2y_flag', 'v2y')):
                val = model.get(key)
                if val is not None:
                    arrow = _fm.get(model.get(fkey) or '', '')
                    vparts.append(f"{lbl}{val:+.1f}{arrow}")
            if vparts:
                sev = model.get('velo_severity')
                sev_s = f" {sev}" if sev else ''
                velo_tok = "velo[" + " ".join(vparts) + "]" + sev_s
            dtier = model.get('decline_tier')
            if dtier and dtier != 'STABLE':
                g = model.get('decline_gap')
                velo_tok += f" sp-decline={dtier}" + (f"(gap{g:+.0f})" if g is not None else '')
        extra = f" | {model.get('extra','')}"
        detail = ' '.join(s for s in (sig, rep, recf, dq, bs_tok, hbs_tok, velo_tok) if s) + extra
        lines.append(f"| **{model_label}** | #{model['rank']} | {proj_s} | {detail} |")
        # sp-decline velo-trajectory callout — fires on SEVERE / DECLINE-RISK.
        if bucket == 'SP':
            sev = model.get('velo_severity')
            dtier = model.get('decline_tier')
            if sev == 'SEVERE':
                lines.append(
                    "\n⚠ **SEVERE velo fade** — YoY *and* in-season velo both down "
                    "(validated ~49% forward bust / −2.5 FP/start, 2.1× base; "
                    "velo_signal_2026-06-13). The strongest velo cutoff — read this as a "
                    "trajectory VETO on any Stuff+/PL buy-low. Conviction flag, not a "
                    "headline mover (CLAUDE.md #13)."
                )
            elif sev == 'LOW-VELO':
                lines.append(
                    "\n⚠ *LOW-VELO tilt* — a velo drop on a sub-median-velo (finesse) arm "
                    "bites ~2× harder (no margin). Conviction flag only."
                )
            if dtier == 'DECLINE-RISK':
                g = model.get('decline_gap'); lp = model.get('decline_level_pctl')
                g_s = f"gap {g:+.0f}" if g is not None else ''
                lp_s = f"lvlPct {lp:.0f}" if lp is not None else ''
                lines.append(
                    f"\n⚠ **sp-decline DECLINE-RISK** ({', '.join(s for s in (lp_s, g_s) if s)}) "
                    "— below-average whiff/K LEVEL with FP propped above it → RoS FP regresses "
                    "DOWN. If a Stuff+/PL buy-low is on the table, this is the trajectory lens "
                    "that VETOES the buy (Framber 2026). Context flag — does NOT move rp3."
                )
        # SP: boom-stack tier-aware callout block (display tag only; not a verdict override).
        if bucket == 'SP' and isinstance(model.get('boom_stack'), int):
            bs_val = model['boom_stack']
            tier = model.get('boom_tier')
            comps = model.get('boom_components') or {}
            lit = [k for k, v in comps.items() if v]
            br = model.get('boom_rate_expected')
            bu = model.get('boom_bust_rate_expected')

            # Boom flag callout — print at stack >= 2 (any tier).
            if bs_val >= 2:
                br_s = f"~{br*100:.1f}% boom rate" if br is not None else ''
                bu_s = f", ~{bu*100:.1f}% bust" if bu is not None else ''
                tier_s = f" [tier={tier}]" if tier else ''
                lines.append(
                    f"\n**Boom-stack flag{tier_s}:** boom_stack={bs_val}/4 "
                    f"({', '.join(lit) if lit else 'no components lit'}) — {br_s}{bu_s}. "
                    f"Display tag only, not a verdict override."
                )

            # Ace + boom_stack >= 2 high-conviction callout.
            if tier == 'ace' and bs_val >= 2:
                lines.append(
                    f"\n🎯 **Ace + boom_stack≥2** = high-conviction boom shot "
                    f"(historical 35-57% boom rate at ace tier)."
                )

            # Anti-predictive skill_spike at sp2_sp3 / backend tiers.
            if model.get('boom_skill_spike_anti_predictive'):
                lines.append(
                    f"\n⚠ **skill_spike at this tier is historically regression-predictive** "
                    f"(not boom-predictive). At {tier} tier, recent K%-spike + BB%-drop "
                    f"has negative per-component lift (Backend −4.1 pp / SP2_SP3 −3.4 pp). "
                    f"Treat as mean-reversion risk, not continuation signal."
                )

            # HIGH-K ARM standalone callout (always fires when flag=True).
            if model.get('is_high_k_arm'):
                z = model.get('high_k_z_score')
                cohort = model.get('high_k_cohort_label')
                z_s = f"z={z:+.2f}" if isinstance(z, (int, float)) else 'z>=+0.5'
                cohort_s = f" within {cohort} cohort" if cohort else ''
                lines.append(
                    f"\n🔥 **HIGH-K ARM:** season K% {z_s}{cohort_s}. "
                    f"Standalone boom edge +6.84 pp (p=2.6e-11, n=1,039 historical, "
                    f"validated 2026-06-03). Independent of boom_stack — compounds on top."
                )

            # RECFORM HOT/COLD verbal explanation (Phase 3 Agent C, 2026-06-05).
            # Honesty: Agent 5 found recform_hot's R² is absorbed by
            # `fp_per_start_to` (r=+0.69) so this is NOT a verdict modifier
            # nor a headline-blend contributor — just explanatory color.
            rf_tag2 = model.get('recform_tag')
            if rf_tag2 in ('HOT', 'COLD'):
                rfz2 = model.get('recform_z')
                rfz2_s = f"z={rfz2:+.2f}" if isinstance(rfz2, (int, float)) else ''
                rf_ts = model.get('recform_trail_starts')
                rf_mfp = model.get('recform_mean_per_start_fp')
                rf_ts_s = f", trailing {rf_ts} starts" if isinstance(rf_ts, int) else ''
                rf_mfp_s = f", ~{rf_mfp:.1f} fp/start" if isinstance(rf_mfp, (int, float)) else ''
                icon = '🔥' if rf_tag2 == 'HOT' else '🧊'
                lines.append(
                    f"\n{icon} *RECFORM {rf_tag2} ({rfz2_s}){rf_ts_s}{rf_mfp_s}:* "
                    f"trailing-5-start fp_proxy z-score; correlated with "
                    f"`fp_per_start_to` and absorbed by the blended xFP — "
                    f"surfaced here as explanatory color, not as a verdict modifier."
                )

            # Compound HIGH-K + boom_stack >= 2 callout (the actionable case).
            if model.get('is_high_k_arm') and bs_val >= 2:
                amp = model.get('high_k_boom_lift_expected')
                amp_s = f"~+{amp:.1f} pp" if isinstance(amp, (int, float)) else "~+9-17 pp"
                lines.append(
                    f"\n🔥🎯 **HIGH-K ARM + boom_stack≥2** — tier-amplified boom EV. "
                    f"Expect {amp_s} on top of base stack signal "
                    f"(stack=2: +9.48 pp / stack=3: +16.82 pp historical, monotonic amplification)."
                )

            # CATCHER FRAMING callouts (independent display tag — validated 2026-06-03).
            # SHIP_AS_DISPLAY_TAG (NOT a 5th boom_stack component). Within-pitcher
            # paired test t=2.40, p=0.017 (n=208), +3.06 pp boom-rate gap Q5-Q1.
            if model.get('is_elite_framer'):
                cn = model.get('catcher_modal_name') or 'modal catcher'
                csaa = model.get('catcher_csaa')
                csaa_s = f"CSAA {csaa:+.2f}" if isinstance(csaa, (int, float)) else "Q5"
                lines.append(
                    f"\n🧊 **ELITE FRAMER:** {cn} ({csaa_s}, Q5). "
                    f"Within-pitcher paired test p=0.017; historical +3-7 pp boom rate "
                    f"at boom_stack 0/1 (where existing tags don't already fire)."
                )
            elif model.get('is_framing_tax'):
                cn = model.get('catcher_modal_name') or 'modal catcher'
                csaa = model.get('catcher_csaa')
                csaa_s = f"CSAA {csaa:+.2f}" if isinstance(csaa, (int, float)) else "Q1"
                lines.append(
                    f"\n⚠ **FRAMING TAX:** {cn} ({csaa_s}, Q1, bottom-tier framer). "
                    f"Historical −3 pp boom rate within-pitcher (p=0.017). "
                    f"Soriano-O'Hoppe is the canonical case."
                )

            # IL_RETURN salvage tag callout (validated 2026-06-03).
            # Salvaged from rejected bust_stack_v2 research program — the only
            # component with independently-significant bust lift. Display tag
            # only — does NOT override verdict.
            if model.get('is_first_back_long_il'):
                ild = model.get('il_return_days_since_last_start')
                last = model.get('il_return_last_start_date')
                ref_src = model.get('il_return_reference_source')
                ref_str = (
                    "next scheduled start" if ref_src == 'next_scheduled'
                    else "today" if ref_src == 'today' else "reference date"
                )
                last_s = f" (last MLB start {last})" if last else ''
                lines.append(
                    f"\n🏥 **IL RETURN start** — pitcher's previous MLB outing was "
                    f"{ild}d ago{last_s}; gap to {ref_str} >= 30d. "
                    f"Historical bust rate +2.93 pp at first-back-from-long-IL "
                    f"starts (n=640, p=0.044; salvaged from bust_stack_v2 research). "
                    f"Cross-reference `/sp-rehab-tracker` for MiLB rehab quality if applicable. "
                    f"Display tag only, not a verdict override."
                )
        # Hitter boom-stack callout block — fires at boom_stack >= 2.
        # Display tag only, advisory; not a verdict override.
        if bucket == 'H' and isinstance(model.get('hitter_boom_stack'), int) \
                and model['hitter_boom_stack'] >= 2:
            hbs_val = model['hitter_boom_stack']
            hcomps = model.get('hitter_boom_components') or {}
            hlit = [k for k, v in hcomps.items() if v]
            hbr = model.get('hitter_boom_rate_expected')
            hbu = model.get('hitter_boom_bust_expected')
            hbr_s = f"~{hbr*100:.1f}% boom rate" if hbr is not None else ''
            hbu_s = f", ~{hbu*100:.1f}% bust" if hbu is not None else ''
            lines.append(
                f"\n🎯 **Hitter boom flag:** boom_stack={hbs_val}/4 "
                f"({', '.join(hlit) if hlit else 'no components lit'}) — "
                f"historically 27-34% chance of >=10 FP game ({hbr_s}{hbu_s} vs "
                f"23.9% baseline). Advisory tag only; stack=3 still busts 37.5%."
            )
            # Lineup-amp specific callout when component 4 fires.
            if hcomps.get('lineup_amp_hitter'):
                d4 = (model.get('hitter_boom_detail') or {}).get('lineup_amp_hitter') or {}
                n_lit = d4.get('n_teammates_lit')
                n_lit_s = f"{n_lit} teammates" if isinstance(n_lit, int) else "≥2 teammates"
                lines.append(
                    f"\n🌊 **LINEUP STACK** — {n_lit_s} also in boom-eligible form "
                    f"(team boom rate ~34% historical at lineup_stack=3+, validated 2026-06-03)."
                )
        # SP: when marcel and data-driven estimates disagree by >= 2 FP, flag it explicitly.
        if bucket == 'SP' and model.get('marcel_data_divergence') is not None:
            m_b = model.get('marcel_baseline')
            d_d = model.get('data_driven_estimate')
            div = model.get('marcel_data_divergence')
            lines.append(
                f"\n**Marcel vs data divergence:** model and Marcel disagree by {div:.2f} FP "
                f"(marcel={m_b:.2f}, data-driven={d_d:.2f}) — treat the headline as a blend; "
                f"weight Marcel side more when data_quality_tag indicates thin data."
            )
    else:
        lines.append(f"| **{model_label}** | — | not in projection file | — |")
    if arche.get('have'):
        rstr = ' / '.join(f"{k}={v}" for k, v in arche['ratings'].items())
        ar_h = f"OVERALL {arche['overall']} ({arche['archetype']} / {arche['cell']})"
        cp = arche.get('career_pct')
        cpstr = f", career-pct {cp*100:.0f}%" if cp is not None and pd.notna(cp) else ''
        sl = arche.get('slope_3yr')
        slstr = f", 3yr-slope {sl:+.1f}" if sl is not None and pd.notna(sl) else ''
        lines.append(f"| **Archetype** | — | {ar_h} | {rstr} | traj {arche['traj_flag']}{slstr}{cpstr} |")
        arc = ' → '.join(f"{y}:{a}({o})" for y, a, o in arche['arc'])
        lines.append(f"\n**Career arc:** {arc}")
        if arche.get('t1_fp') is not None and pd.notna(arche['t1_fp']):
            unit = {'SP': 'start', 'H': 'PA', 'RP': 'g'}[bucket]
            lines.append(f"\n**Archetype T+1 projection:** {arche['t1_fp']:.3f} fp/{unit}")
        if bucket == 'RP':
            roles = []
            if arche.get('closer'):   roles.append('CLOSER')
            if arche.get('high_lev'): roles.append('HIGH_LEVERAGE')
            if arche.get('fireman'):  roles.append('FIREMAN')
            lev = arche.get('leverage_tier')
            tagstr = ', '.join(roles) if roles else 'non-role'
            lines.append(f"\n**Role tags:** {tagstr} | leverage_tier={lev}")
        v = arche.get('velo'); vt = arche.get('velo_tier')
        if v is not None and pd.notna(v):
            lines.append(f"\n**Velo:** {v:.1f} mph [{vt}]")
    else:
        lines.append(f"| **Archetype** | — | NOT AVAILABLE | {arche.get('reason','')} |")

    # ── Process / Sustainability Panel ────────────────────────────────────────
    # Display-only conviction layer (CLAUDE.md #13 — does not move the projection).
    sl = model.get('sustainability') or {}
    pv = sl.get('process_verdict', '')
    if pv and pv != 'INSUFFICIENT_DATA':
        from scripts.xfp.lib.sustainability_lens import verdict_prefix, verdict_label
        icon = verdict_prefix(pv)
        lbl  = verdict_label(pv)
        detail = sl.get('process_detail', '')
        if bucket in ('SP', 'RP'):
            k24  = sl.get('k_pct_24');  k25  = sl.get('k_pct_25');  k26  = sl.get('k_pct_26')
            sw24 = sl.get('swstr_pct_24'); sw25 = sl.get('swstr_pct_25'); sw26 = sl.get('swstr_pct_26')
            def _p(v): return f"{v*100:.1f}%" if v is not None else "—"
            k_trail  = " -> ".join(_p(x) for x in (k24, k25, k26)  if x is not None)
            sw_trail = " -> ".join(_p(x) for x in (sw24, sw25, sw26) if x is not None)
            lines.append(
                f"\n{icon} **Process [{lbl}]** K%: {k_trail} | SwStr%: {sw_trail}\n"
                f"*{detail}*"
            )
        else:
            xw24 = sl.get('xwobacon_24'); xw25 = sl.get('xwobacon_25'); xw26 = sl.get('xwobacon_26')
            xwl  = sl.get('xwobacon_l21d')
            brl  = sl.get('barrel_pct_26');  brll = sl.get('barrel_pct_l21d')
            k26v = sl.get('k_pct_26');       k_l  = sl.get('k_pct_l21d')
            def _x(v): return f"{v:.3f}" if v is not None else "—"
            def _pp(v): return f"{v*100:.1f}%" if v is not None else "—"
            xw_trail = " -> ".join(_x(x) for x in (xw24, xw25, xw26) if x is not None)
            l21_str  = f" | L21d xwOBACON {_x(xwl)}" if xwl is not None else ""
            brl_str  = f" | Brl% {_pp(brl)}/{_pp(brll)}" if brl is not None else ""
            k_str    = f" | K% {_pp(k26v)}/{_pp(k_l)}" if k26v is not None else ""
            lines.append(
                f"\n{icon} **Process [{lbl}]** xwOBACON: {xw_trail}{l21_str}{brl_str}{k_str}\n"
                f"*{detail}*"
            )

    # ── Splits table (platoon vs L/R + home/road + luck-by-split) — context-only
    def _r(v): return f"{v:.3f}" if v is not None else "—"
    spl = model.get('splits') or {}
    ha = model.get('home_away') or {}
    es = model.get('expected_splits') or {}
    srows = []
    if spl and spl.get('dominant_side'):
        nL, nR = int(spl.get('pa_vs_L') or 0), int(spl.get('pa_vs_R') or 0)
        read = (f"hit harder by {spl['dominant_side']}HB" if bucket in ('SP', 'RP')
                else f"stronger vs {spl['dominant_side']}HP")
        srows.append(f"| Platoon | {_r(spl.get('rate_vs_L'))} (n{nL}) | {_r(spl.get('rate_vs_R'))} (n{nR}) | {read} |")
        if es and (es.get('vs_L') or es.get('vs_R')):
            def _sx(side):
                v = es.get(side)
                return f"{v['xwoba']:.3f}x/{v['woba']:.3f}a {v['regression'][:4].lower()}" if v else "—"
            srows.append(f"| ↳ expected (luck) | {_sx('vs_L')} | {_sx('vs_R')} | xwOBA vs actual, by side |")
    if ha and ha.get('dominant_side'):
        nh, na = int(ha.get('pa_home') or 0), int(ha.get('pa_away') or 0)
        srows.append(f"| Home/Road | {_r(ha.get('rate_home'))} (n{nh}) | {_r(ha.get('rate_away'))} (n{na}) | leans {ha['dominant_side']} |")
    if srows:
        unit = 'xwOBA-allowed' if bucket in ('SP', 'RP') else 'xwOBA'
        lines.append(f"\n**📐 Splits & luck ({unit}; context-only)**\n"
                     "| Lens | vs L / Home | vs R / Road | Read |\n|---|---|---|---|\n" + "\n".join(srows))

    # Overall luck + TTO (single-metric, kept as compact lines)
    exp = model.get('expected') or {}
    if exp and exp.get('gap') is not None:
        g = exp['gap']; lab = 'xwOBA-allowed' if bucket in ('SP', 'RP') else 'xwOBA'
        tail = {'OVERPERFORMING': (' — regression UP coming' if bucket in ('SP', 'RP') else ' — due for negative regression'),
                'UNDERPERFORMING': (' — ratios should improve' if bucket in ('SP', 'RP') else ' — bounce due'),
                'ALIGNED': ''}.get(exp['regression'], '')
        lines.append(f"\n🎲 **Expected (luck)** {lab} {exp['xwoba']:.3f} vs actual {exp['woba']:.3f} "
                     f"(gap {g:+.3f}) — {exp['regression']}{tail}")
    tto = model.get('tto_decay') or {}
    if bucket == 'SP' and tto.get('penalty') is not None:
        w = "" if tto.get('sample_ok') else " (small sample)"
        lines.append(f"🔁 **3rd-time-through** {tto['tto1_rate']:.3f}→{tto['tto3_rate']:.3f} core fp/PA "
                     f"(penalty {tto['penalty']:+.3f}) → {tto['tier']} (career){w}")

    # ── Boom/Bust realized actuals table (boxscore store; reuse precomputed) ──
    if actuals is None:
        from scripts.xfp.lib.triangulate_core import compute_actuals as _ca
        actuals = _ca(int(player['id']), bucket)
    _thr = {'SP': '≥20 / <5', 'RP': '≥6 / <0', 'H': '≥10 / <2'}.get(bucket, '')
    bb = actuals.get('boom_bust')
    win = actuals.get('boom_window') or ''
    thr = _thr
    if bb:
        lines.append(
            f"\n**📊 Boom/Bust actuals ({win}, BrownU FP; boom/bust {thr}; context-only)**\n"
            "| mean | std | boom% | bust% | min–max | L3 | trend |\n|---|---|---|---|---|---|---|\n"
            f"| {bb['mean']} | {bb['std']} | {bb['boom_pct']}% | {bb['bust_pct']}% | "
            f"{bb['min']}–{bb['max']} | {bb['l3_mean']} | {bb['trend']} |\n"
            f"_last {len(bb['last'])}: {bb['last']}_")

    # ── In-season archetype trajectory (OVERALL + main domains over time) ──────
    traj = actuals.get('trajectory')
    if traj and traj.get('points'):
        doms = traj['domains']
        cad = 'per start' if traj['xkey'] == 'start_no' else 'weekly'
        hdr = "| pt | OVR | " + " | ".join(d[:4].title() for d in doms) + " | archetype |"
        sep = "|---|---|" + "---|" * (len(doms) + 1)
        body = [f"| {p['label']} | {p.get('OVERALL')} | "
                + " | ".join(str(p.get(d) if p.get(d) is not None else '—') for d in doms)
                + f" | {p.get('archetype')} |" for p in traj['points']]
        lines.append(f"\n**📈 In-season archetype trajectory ({cad}; 20-80, context-only)**\n"
                     f"{hdr}\n{sep}\n" + "\n".join(body))

    return '\n'.join(lines)


def compare_table(rows):
    out = ["\n## Comparison\n"]
    out.append("| Player | Bucket | PL | Model | Archetype OVERALL | Velo traj | T+1 | Traj "
               "| Boom/Bust (μ b%/B%) | OVR arc | Verdict |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    _arrow = {'UP': '▲', 'DOWN': '▼', 'FLAT': '▬'}
    for r in rows:
        p = r['player']; pl = r['pl_main']; m = r['model']; a = r['arche']
        pl_show = f"#{pl}" if isinstance(pl, int) else pl
        m_show = f"#{m['rank']} ({m['proj']:.2f})" if m['rank'] != '—' and m.get('proj') is not None else '—'
        if a.get('have'):
            a_show = f"{a['overall']} ({a['archetype']})"
            t1 = f"{a['t1_fp']:.2f}" if a.get('t1_fp') is not None and pd.notna(a['t1_fp']) else '—'
            tr = a['traj_flag']
        else:
            a_show = '—'; t1 = '—'; tr = '—'
        # SP velo-trajectory summary cell: severity tag, else the YoY flag/value.
        velo_show = '—'
        if p['bucket'] == 'SP':
            sev = m.get('velo_severity')
            if sev:
                velo_show = sev
            elif m.get('velo_yoy') is not None:
                arrow = {'VV': '▼▼', 'v': '▼', '^': '▲'}.get(m.get('velo_yoy_flag') or '', '')
                velo_show = f"{m['velo_yoy']:+.1f}{arrow}"
        # Realized actuals cells (boom/bust + in-season OVERALL arc) — context-only.
        act = r.get('actuals') or {}
        bb = act.get('boom_bust')
        bb_show = (f"{bb['mean']}{_arrow.get(bb['trend'], '')} {bb['boom_pct']}/{bb['bust_pct']}%"
                   if bb else '—')
        traj = act.get('trajectory')
        pts = (traj or {}).get('points') or []
        arc_show = (f"{pts[0].get('OVERALL')}→{pts[-1].get('OVERALL')}"
                    if len(pts) >= 2 else '—')
        out.append(f"| {p['display_name']} | {p['bucket']} | {pl_show} | {m_show} | {a_show} "
                   f"| {velo_show} | {t1} | {tr} | {bb_show} | {arc_show} | {r['verdict']} |")
    return '\n'.join(out)


def _verdict_matches(verdict: str, filters: list[str]) -> bool:
    if not filters:
        return True
    v = verdict.lower()
    return any(tok in v for tok in filters)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('names', nargs='*', help='Player names (or use --names-file)')
    ap.add_argument('--bucket', choices=['H', 'SP', 'RP'], default=None,
                    help='Force a position bucket (otherwise auto-detected)')
    ap.add_argument('--names-file', default=None, help='CSV with a player_name column (batch mode)')
    ap.add_argument('--csv-out', default=None, help='Write batch results to this CSV (instead of per-player cards)')
    ap.add_argument('--json-out', default=None, help='Write batch results to this JSON file (dashboard-friendly). May coexist with --csv-out.')
    ap.add_argument('--filter', default=None,
                    help='Comma-separated verdict substrings (case-insensitive). Only emit matching rows/cards.')
    ap.add_argument('--summary-only', action='store_true',
                    help='Interactive mode: suppress per-player cards, print only comparison table.')
    ap.add_argument('--snapshot', default=None, metavar='LABEL',
                    help='After a batch run, also save the CSV to data/research/triangulate_universe/snapshots/triangulate_LABEL_YYYY-MM-DD.csv')
    ap.add_argument('--diff', default=None, metavar='PRIOR_CSV',
                    help='After current run, emit a markdown diff vs PRIOR_CSV (verdict changes, new/dropped players, override flips).')
    ap.add_argument('--check-caches', action='store_true',
                    help='Print refresh instructions for stale PL cache files and exit.')
    args = ap.parse_args()

    if args.check_caches:
        print_refresh_instructions()
        return

    _warn_stale_caches()

    filters = []
    if args.filter:
        filters = [t.strip().lower() for t in args.filter.split(',') if t.strip()]

    input_df = None
    if args.names_file:
        input_df = pd.read_csv(args.names_file)
        name_list = input_df['player_name'].dropna().astype(str).tolist()
    else:
        name_list = args.names

    category_map = {}
    if input_df is not None and 'category' in input_df.columns:
        for _, row in input_df.iterrows():
            nm = row.get('player_name')
            if pd.notna(nm):
                category_map[str(nm)] = row.get('category')

    batch_out = bool(args.csv_out or args.json_out)
    rows = []
    csv_rows = []
    json_rows = []
    for name in name_list:
        player = resolve_player(name, args.bucket)
        if not player:
            if batch_out:
                rec = {'player_name': name, 'bucket': '?', 'resolved': False}
                if category_map:
                    rec['category'] = category_map.get(name)
                if args.csv_out:
                    csv_rows.append(rec)
                if args.json_out:
                    json_rows.append({
                        'name': name, 'bucket': '?', 'resolved': False,
                        'category': category_map.get(name) if category_map else None,
                    })
            else:
                print(f"\n### {name} — NOT FOUND in projections or archetype panels.\n")
            continue
        bucket = player['bucket']
        model = model_row(player)
        m_rank_int = model.get('rank') if isinstance(model.get('rank'), int) else None
        pl_main, pl_main_date = pl_rank(player['display_name'], bucket, model_rank=m_rank_int)
        pl_stream, pl_stream_opp, pl_stream_date = pl_streamer_rank(player['display_name']) if bucket == 'SP' else ('—', None, None)
        arche = archetype_row(player)
        verdict, rationale = synthesize(player, pl_main, pl_main_date, pl_stream, pl_stream_date, model, arche)
        verdict, rationale, override_tag = apply_overrides(verdict, rationale, player, arche, model)

        # IL caveat — inject live ESPN injury status (cached offline) so an
        # injured player isn't surfaced as a naked BUY. See injury_status.
        il_status = _il_status_for(player['display_name'])
        _il_mark = il_caveat(il_status)
        if _il_mark:
            verdict = f"{_il_mark} {verdict}"
            override_tag = override_tag or 'IL'

        verdict_top, reason_tag = consolidate_verdict(verdict)
        m_rank_for_conf = model.get('rank') if isinstance(model.get('rank'), int) else None
        confidence, n_aligned, n_avail = compute_confidence(verdict_top, pl_main, m_rank_for_conf, arche)
        watch_list = build_watch_list(verdict_top, reason_tag, model, arche, pl_main)

        if not _verdict_matches(verdict, filters):
            continue

        # Realized actuals (boom/bust + in-season trajectory) — computed once per
        # player and reused by the card, the batch serializers, and the comparison
        # grid. Boom/bust now reads the materialized boxscore store (~1ms); the
        # trajectory builders are cached so the cost is paid once per process.
        actuals = compute_actuals(int(player['id']), bucket)
        rows.append({
            'player': player, 'pl_main': pl_main, 'pl_main_date': pl_main_date,
            'pl_stream': pl_stream, 'pl_stream_date': pl_stream_date,
            'model': model, 'arche': arche, 'verdict': verdict, 'rationale': rationale,
            'override_tag': override_tag, 'il_status': il_status,
            'verdict_top': verdict_top, 'reason_tag': reason_tag,
            'confidence': confidence, 'n_aligned': n_aligned, 'n_avail': n_avail,
            'watch_list': watch_list, 'actuals': actuals,
        })
        # Blended xFP for batch parity — the card leads with it; surface it (and an
        # explicit headline_source) in batch output so CSV/JSON consumers headline the
        # same Tier-A number the cards/slate-grids do (feedback #12). Display-only.
        try:
            from scripts.xfp.lib.blend_score import compute_blended_xfp
            _blend = compute_blended_xfp(player_name=player['display_name'],
                                         player_type=bucket, mlbam_id=int(player['id'])) or {}
        except Exception:
            _blend = {}
        _bx = _blend.get('blended_xfp')
        _headline_src = 'blended_xfp' if _bx is not None else {'H': 'rh3', 'SP': 'rp3', 'RP': 'rprs2'}.get(bucket, 'model')
        _mp = model.get('proj')
        _headline_proj = _bx if _bx is not None else (_mp if isinstance(_mp, (int, float)) else None)
        if args.json_out:
            def _num(x):
                if x is None: return None
                try:
                    if pd.isna(x): return None
                except Exception:
                    pass
                if isinstance(x, (int, float)): return x
                return None
            jrec = {
                'name': player['display_name'],
                'bucket': bucket,
                'team': player.get('team') if isinstance(player, dict) else None,
                'pl_rank': pl_main if isinstance(pl_main, int) else None,
                'pl_rank_raw': pl_main if isinstance(pl_main, int) else (str(pl_main) if pl_main is not None else None),
                'model_rank': model.get('rank') if isinstance(model.get('rank'), int) else None,
                'model_proj': _num(model.get('proj')),
                'model_proj_label': model.get('proj_label'),
                'blended_xfp': _num(_bx),
                'blend_confidence': _blend.get('confidence_tier'),
                'blend_unit': _blend.get('display_unit'),
                'headline_proj': _num(_headline_proj),
                'headline_source': _headline_src,
                'model_signal': model.get('signal'),
                'arche_have': bool(arche.get('have')),
                'arche_overall': arche.get('overall') if arche.get('have') else None,
                'arche_label': arche.get('archetype') if arche.get('have') else None,
                'arche_cell': arche.get('cell') if arche.get('have') else None,
                'arche_traj': arche.get('traj_flag') if arche.get('have') else None,
                'arche_t1_fp': _num(arche.get('t1_fp')) if arche.get('have') else None,
                'arche_career_pct': _num(arche.get('career_pct')) if arche.get('have') else None,
                'verdict': verdict,
                'rationale': rationale,
                'override_tag': override_tag,
                'il_status': il_status,
                'category': category_map.get(name) if category_map else None,
            }
            # context-only lenses (platoon / expected / home-road / TTO) — flat columns
            jrec.update(flatten_lenses(model, bucket))
            # realized actuals — nested (JSON handles the full boom/bust + trajectory)
            jrec['boom_bust'] = actuals.get('boom_bust')
            jrec['boom_window'] = actuals.get('boom_window')
            jrec['trajectory'] = actuals.get('trajectory')
            json_rows.append(jrec)
        if args.csv_out:
            rec = {
                'player_name': player['display_name'],
                'bucket': bucket,
                'pl_rank': pl_main if isinstance(pl_main, int) else None,
                'pl_rank_raw': pl_main,
                'model_rank': model.get('rank') if model.get('rank') != '—' else None,
                'model_proj': model.get('proj'),
                'blended_xfp': _bx,
                'blend_confidence': _blend.get('confidence_tier'),
                'headline_proj': _headline_proj,
                'headline_source': _headline_src,
                'model_signal': model.get('signal'),
                'model_rep_delta': model.get('rep_delta'),
                'model_recform': model.get('recform'),
                'schedule_idx': model.get('schedule_idx') if bucket == 'SP' else None,
                'arche_have': arche.get('have', False),
                'arche_overall': arche.get('overall') if arche.get('have') else None,
                'arche_label': arche.get('archetype') if arche.get('have') else None,
                'arche_cell': arche.get('cell') if arche.get('have') else None,
                'arche_traj': arche.get('traj_flag') if arche.get('have') else None,
                'arche_slope_3yr': arche.get('slope_3yr') if arche.get('have') else None,
                'arche_career_pct': arche.get('career_pct') if arche.get('have') else None,
                'arche_t1_fp': arche.get('t1_fp') if arche.get('have') else None,
                'arche_age': arche.get('age') if arche.get('have') else None,
                'arche_age_tier': arche.get('age_tier') if arche.get('have') else None,
                'arche_velo': arche.get('velo') if arche.get('have') else None,
                'arche_velo_tier': arche.get('velo_tier') if arche.get('have') else None,
                'verdict': verdict,
                'verdict_top': verdict_top,
                'reason_tag': reason_tag,
                'confidence': confidence,
                'confidence_n_aligned': n_aligned,
                'confidence_n_available': n_avail,
                'watch_list': '; '.join(watch_list) if watch_list else '',
                'rationale': rationale,
                'override_tag': override_tag,
                # sp-decline velo-trajectory lens (SP only; blank for H/RP)
                'decline_tier': model.get('decline_tier'),
                'velo_severity': model.get('velo_severity'),
                'velo_yoy': model.get('velo_yoy'),
                'velo_in': model.get('velo_in'),
                'velo_2y': model.get('velo_2y'),
            }
            # context-only lenses (platoon / expected / home-road / TTO) — flat columns
            rec.update(flatten_lenses(model, bucket))
            # realized actuals (boom/bust + in-season trajectory) — flat columns
            rec.update(flatten_actuals(actuals))
            if category_map:
                rec['category'] = category_map.get(name)
            csv_rows.append(rec)
        if not batch_out and not args.summary_only:
            print(format_card(player, pl_main, pl_main_date, pl_stream, pl_stream_date, model, arche, verdict, rationale,
                              confidence=confidence, n_aligned=n_aligned, n_available=n_avail,
                              watch_list=watch_list, verdict_top=verdict_top, reason_tag=reason_tag,
                              actuals=actuals))

    if args.csv_out:
        df_out = pd.DataFrame(csv_rows)
        # within_bucket_rank: per (category, bucket) group, rank by model_rank asc.
        # None when no category column present.
        if 'category' in df_out.columns and 'bucket' in df_out.columns and 'model_rank' in df_out.columns:
            df_out['within_bucket_rank'] = (
                df_out.groupby(['category', 'bucket'])['model_rank']
                      .rank(method='min', ascending=True, na_option='bottom')
            )
            df_out['within_bucket_rank'] = df_out['within_bucket_rank'].astype('Int64')
        else:
            df_out['within_bucket_rank'] = None
        df_out.to_csv(args.csv_out, index=False)
        print(f"Wrote {len(df_out)} rows to {args.csv_out}")
        if args.snapshot:
            snap_path = write_snapshot(df_out, args.snapshot)
            print(f"Snapshot written: {snap_path}")
        if args.diff:
            diff_path, report = write_diff(args.diff, args.csv_out)
            print(f"Diff written: {diff_path}\n")
            print(truncate_report_for_stdout(report, max_changes=20))
    if args.json_out:
        resolved = [r for r in json_rows if r.get('resolved', True) is not False]
        verdict_counts = dict(Counter(r['verdict'] for r in resolved if r.get('verdict')))
        override_counts = dict(Counter(r['override_tag'] for r in resolved if r.get('override_tag')))
        bucket_counts = dict(Counter(r['bucket'] for r in resolved if r.get('bucket')))
        payload = {
            'generated': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
            'n_players': len(resolved),
            'n_unresolved': len(json_rows) - len(resolved),
            'verdict_counts': verdict_counts,
            'override_counts': override_counts,
            'bucket_counts': bucket_counts,
            'players': json_rows,
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)) or '.', exist_ok=True)
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, default=str)
        print(f"Wrote {len(json_rows)} rows to {args.json_out}")
    if not batch_out and len(rows) > 1:
        print(compare_table(rows))


if __name__ == '__main__':
    main()
