"""Replay-only constraint recommendations derived from failure feedback profiles."""
from __future__ import annotations

from .failure_feedback_models import ConstraintTuningRecommendation, FailureModeAggregate, FamilyFailureProfile


SAFETY_RULES: tuple[str, ...] = (
    "replay_only",
    "paper_only",
    "live_trading_disabled",
    "defined_risk_required",
    "no_naked_undefined_risk_selling",
    "no_broker_connection",
)

FAILURE_RECOMMENDATION_MAP: dict[str, tuple[tuple[str, str, str], ...]] = {
    "high_spread_bad_fill_failure": (
        ("max_spread_threshold", "tighten max spread threshold", "reduce accepted spread pressure in replay mutations"),
        ("slippage_penalty", "increase slippage penalty", "raise bad-fill cost in tournament-compatible scoring"),
        ("liquidity_minimum", "increase liquidity minimum", "require stronger fillability before research promotion"),
        ("short_duration_aggressiveness", "reduce short-duration aggressiveness in bad-fill windows", "guard short-DTE replay entries in bad-fill regimes"),
    ),
    "low_liquidity_decay_failure": (
        ("fillability_score_minimum", "increase minimum fillability score", "penalize low fillability in replay mutations"),
        ("open_interest_volume_penalty", "penalize low OI/volume more strongly", "increase deterministic low-depth penalty"),
        ("liquidity_robustness_required", "require stronger liquidity robustness for promotion", "block weak-liquidity research promotion"),
    ),
    "IV_crush_against_vol_expansion": (
        ("iv_expansion_threshold", "raise IV expansion threshold", "require stronger long-vol confirmation"),
        ("iv_crush_risk_penalty", "penalize high IV crush risk", "raise post-event IV-crush guard"),
        ("theta_premium_overpayment_penalty", "increase theta/premium overpayment penalty", "penalize long-premium overpayment"),
        ("event_vol_confirmation", "require stronger event-vol confirmation", "tighten event-vol replay filter"),
    ),
    "macro_shock_against_compression": (
        ("macro_shock_avoidance", "strengthen macro-shock avoidance", "avoid compression entries during risk-off windows"),
        ("compression_shock_penalty", "penalize compression structures in shock/risk-off windows", "raise compression contradiction penalty"),
        ("breakout_macro_contradiction_penalty", "increase breakout/macro contradiction penalty", "guard range structures against macro breakout pressure"),
    ),
    "fakeout_against_directional": (
        ("fakeout_penalty", "increase fakeout penalty", "penalize failed-breakout pattern contradiction"),
        ("pattern_confirmation", "require stronger pattern confirmation", "raise continuation confirmation requirement"),
        ("invalidation_sensitivity", "tighten invalidation sensitivity", "exit or reject stale directional replay setups faster"),
    ),
    "theta_decay_against_short_duration": (
        ("theta_tolerance", "reduce theta tolerance in chop/liquidity-decay windows", "tighten short-duration theta guard"),
        ("breakout_confirmation", "require cleaner breakout confirmation", "avoid chop/fakeout short-DTE replay entries"),
        ("time_decay_invalidation", "strengthen time-decay exit/invalidation", "tighten short-duration invalidation"),
    ),
    "overfit_train_only": (
        ("holdout_weighting", "increase holdout weighting", "reward multi-window survival over train-only improvement"),
        ("overfit_penalty", "increase overfit penalty", "penalize train-only replay gains"),
        ("promotion_score_adjustment", "reduce promotion score for train-only improvements", "block research promotion on train-only score deltas"),
        ("multi_regime_consistency", "require multi-regime consistency", "require more families/regimes before acceptance"),
        ("holdout_consistency_guard", "require stronger walk-forward consistency evidence",
         "block research promotion until stronger walk-forward consistency passes rolling + blocked + regime + stress splits"),
    ),
    "holdout_collapse": (
        ("holdout_weighting", "increase holdout weighting", "raise holdout survival pressure"),
        ("overfit_penalty", "increase overfit penalty", "reject holdout collapse candidates"),
        ("promotion_score_adjustment", "reduce promotion score for train-only improvements", "block train-only replay gains"),
        ("multi_regime_consistency", "require multi-regime consistency", "require validation and holdout consistency"),
        ("holdout_consistency_guard", "require stronger walk-forward consistency evidence",
         "block research promotion until stronger walk-forward consistency passes holdout windows"),
    ),
    "unsafe_structure_rejected": (
        ("mutation_ban_pattern", "add explicit mutation ban pattern", "record rejected unsafe mutation type"),
        ("family_envelope_validator", "strengthen family envelope validator", "keep family-specific rejection active"),
        ("blocked_mutation_type", "record blocked mutation type", "preserve unsafe rejection evidence"),
    ),
    "premium_overpayment_trap_failure": (
        ("premium_overpayment_penalty", "strengthen premium-overpayment penalty", "penalize high IV rank without enough movement confirmation"),
        ("iv_entry_value_guard", "require better IV entry value", "avoid overpaying fixture premium in replay"),
    ),
    "iv_crush_after_vol_expansion_failure": (
        ("post_event_crush_avoidance", "strengthen post-event crush avoidance", "block long-vol replay entries after event-vol collapse"),
        ("iv_expansion_confirmation", "tighten IV expansion confirmation", "require catalyst-backed IV expansion before long-vol mutations"),
    ),
    "front_event_bump_against_compression": (
        ("front_event_bump_guard", "block compression during front-expiry event bumps", "avoid defined-risk compression before event-vol release"),
        ("compression_term_guard", "strengthen compression term guard", "require normalizing term structure before compression replay"),
    ),
    "backwardation_against_compression": (
        ("compression_macro_term_guard", "strengthen compression macro/term guard", "avoid compression in backwardation or shock windows"),
        ("term_structure_penalty", "increase term-structure risk penalty", "penalize backwardation for compression candidates"),
    ),
    "skew_trap_against_directional": (
        ("directional_skew_alignment", "require directional skew alignment", "avoid directional entries against distorted skew"),
        ("skew_trap_penalty", "increase skew trap penalty", "penalize skew distortion in fakeout-prone replay"),
    ),
    "surface_instability_fakeout_failure": (
        ("surface_stability_guard", "tighten unstable-surface fakeout guard", "require stable IV surface before directional replay entries"),
        ("fakeout_surface_penalty", "increase surface-instability fakeout penalty", "combine fakeout and unstable-surface pressure"),
    ),
    "short_duration_front_iv_instability": (
        ("short_duration_front_iv_guard", "tighten short-duration front-IV instability guard", "avoid short-DTE entries during front-IV shock"),
        ("short_duration_event_bump_penalty", "increase front-event bump penalty", "penalize short-DTE structures near event bumps"),
    ),
    "term_structure_mismatch": (
        ("term_structure_family_fit", "tighten term-structure family fit", "require family-specific term-state agreement"),
        ("term_risk_penalty", "increase term-structure risk penalty", "penalize unstable term regimes"),
    ),
    "wing_elevation_breakout_risk": (
        ("wing_elevation_breakout_guard", "penalize wing-elevation breakout risk", "avoid compression when elevated wings imply breakout pressure"),
        ("skew_wing_confirmation", "require stronger skew/wing confirmation", "demand safer wing context before replay promotion"),
    ),
    # Macro-event fixture expansion recommendations
    "macro_fakeout_against_directional": (
        ("macro_fakeout_penalty", "penalize macro fakeout risk for directional entries", "avoid directional entries when macro contradicts breakout"),
        ("macro_contradiction_penalty", "increase macro contradiction penalty", "downgrade directional setups against macro fakeout"),
    ),
    "event_gap_against_short_duration": (
        ("event_gap_guard", "stronger event-gap guard", "block short-DTE entries near macro event windows"),
        ("short_duration_event_bump_penalty", "increase short-duration event-bump penalty", "penalize short-DTE structures near event bumps"),
    ),
    "rate_shock_against_compression": (
        ("rate_shock_avoidance", "rate-shock avoidance for compression", "avoid compression during rate-shock regimes"),
        ("compression_macro_term_guard", "strengthen compression macro guard", "guard compression against CPI/FOMC/rate shocks"),
    ),
    "vix_spike_against_compression": (
        ("vix_vvix_stress_guard", "VIX/VVIX stress guard", "avoid compression during vol-index stress"),
        ("compression_vol_stress_penalty", "penalize compression under vol stress", "raise compression penalty when VIX/VVIX spike"),
    ),
    "post_event_crush_against_vol_expansion": (
        ("post_event_crush_avoidance", "post-event crush avoidance for vol expansion", "block long-vol entries after macro-event normalization"),
        ("iv_expansion_confirmation", "require catalyst-backed IV expansion", "confirm IV expansion before long-vol replay"),
    ),
    "breadth_contradiction_against_directional": (
        ("breadth_confirmation_guard", "breadth confirmation guard for directional", "require breadth confirmation for directional entries"),
        ("macro_breadth_penalty", "penalize directional entries with weak breadth", "downgrade directional setups when breadth contradicts"),
    ),
    "liquidity_contraction_bad_fill_failure": (
        ("liquidity_contraction_guard", "liquidity-contraction guard for short-duration", "avoid short-DTE entries during liquidity contraction"),
        ("liquidity_robustness_required", "require stronger liquidity robustness", "block weak-liquidity research promotion"),
    ),
    "overnight_gap_slippage_failure": (
        ("overnight_risk_penalty", "overnight-risk penalty", "avoid entries when overnight/futures gap pressure is high"),
        ("slippage_penalty", "increase slippage penalty", "raise bad-fill cost in macro-gap windows"),
    ),
    "sector_rotation_mismatch": (
        ("sector_alignment_guard", "sector-alignment guard", "avoid directional entries during sector-rotation chop"),
        ("macro_fakeout_penalty", "penalize macro fakeout risk", "downgrade entries when sector rotation contradicts thesis"),
    ),
    "macro_event_overfit": (
        ("macro_holdout_weighting", "macro holdout weighting", "do not promote based on a single macro scenario"),
        ("multi_regime_consistency", "require multi-regime consistency", "require survival across multiple macro regimes"),
    ),
}


def _recommendation_id(family: str, failure_mode_id: str, index: int) -> str:
    clean_mode = failure_mode_id.replace("_", "-").replace("/", "-")
    clean_family = family.replace("_", "-")
    return f"rec-{clean_family}-{clean_mode}-{index:02d}"


def build_constraint_tuning_recommendations(
    family_profiles: list[FamilyFailureProfile],
    aggregates: list[FailureModeAggregate],
) -> list[ConstraintTuningRecommendation]:
    aggregates_by_family: dict[str, list[FailureModeAggregate]] = {
        profile.strategy_family: [
            item for item in aggregates if item.strategy_family == profile.strategy_family
        ]
        for profile in family_profiles
    }
    recommendations: list[ConstraintTuningRecommendation] = []
    for profile in family_profiles:
        family_aggregates = sorted(
            aggregates_by_family[profile.strategy_family],
            key=lambda item: (-item.recurrence_count, -item.severity_score, item.failure_mode_id),
        )
        seen_modes: list[str] = []
        for aggregate in family_aggregates:
            if aggregate.failure_mode_id in seen_modes:
                continue
            seen_modes.append(aggregate.failure_mode_id)
            entries = FAILURE_RECOMMENDATION_MAP.get(aggregate.failure_mode_id, ())
            for index, (tuning_key, title, action) in enumerate(entries, start=1):
                recommendations.append(ConstraintTuningRecommendation(
                    recommendation_id=_recommendation_id(profile.strategy_family, aggregate.failure_mode_id, index),
                    strategy_family=profile.strategy_family,
                    failure_mode_id=aggregate.failure_mode_id,
                    tuning_key=tuning_key,
                    recommendation=title,
                    bounded_action=action,
                    target_scope="offline_fixture_replay",
                    replay_only=True,
                    advisory=True,
                    safety_rules=list(SAFETY_RULES),
                    rationale=(
                        f"{aggregate.failure_mode_id} recurred {aggregate.recurrence_count} times "
                        f"for {profile.strategy_family} with severity {aggregate.severity}"
                    ),
                ))
    return sorted(
        recommendations,
        key=lambda item: (item.strategy_family, item.failure_mode_id, item.tuning_key, item.recommendation_id),
    )
