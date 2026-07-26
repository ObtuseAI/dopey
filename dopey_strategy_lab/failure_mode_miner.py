"""Deterministic offline failure-mode mining for DOPEY replay and mutation records."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .mutation_constraints import constraint_updates_from_failure_modes


FAILURE_MODE_MINER_VERSION = "dopey-failure-mode-miner-v1"


@dataclass(frozen=True)
class FailureModeEvidence:
    source: str
    strategy_id: str
    family: str
    window_or_regime: str
    metric_name: str
    metric_value: float
    notes: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FailureModeMitigationHint:
    failure_mode_id: str
    mitigation_hint: str
    recommended_mutation_constraint_update: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FailureMode:
    failure_mode_id: str
    affected_strategy_ids: list[str]
    affected_family: str
    windows_or_regimes: list[str]
    evidence_score: float
    recurrence_count: int
    severity: str
    mitigation_hint: str
    recommended_mutation_constraint_update: str
    evidence: list[FailureModeEvidence] = field(default_factory=list)
    version: str = FAILURE_MODE_MINER_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["evidence"] = [item.to_dict() for item in self.evidence]
        return data


@dataclass(frozen=True)
class FailureModeCluster:
    cluster_id: str
    failure_mode_ids: list[str]
    affected_families: list[str]
    severity: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FailureModeRegistry:
    registry_id: str
    failure_modes: list[FailureMode]
    clusters: list[FailureModeCluster]
    mitigation_hints: list[FailureModeMitigationHint]
    constraint_updates: list[dict]
    version: str = FAILURE_MODE_MINER_VERSION

    def to_dict(self) -> dict:
        return {
            "registry_id": self.registry_id,
            "failure_modes": [mode.to_dict() for mode in self.failure_modes],
            "clusters": [cluster.to_dict() for cluster in self.clusters],
            "mitigation_hints": [hint.to_dict() for hint in self.mitigation_hints],
            "constraint_updates": list(self.constraint_updates),
            "version": self.version,
        }


MITIGATION_MAP: dict[str, tuple[str, str]] = {
    "high_spread_bad_fill_failure": (
        "avoid high-spread entries or require stronger fill quality",
        "increase bad-fill avoidance weighting",
    ),
    "low_liquidity_decay_failure": (
        "tighten liquidity and open-interest thresholds",
        "tighten liquidity thresholds",
    ),
    "IV_crush_against_vol_expansion": (
        "avoid post-event IV-crush windows for long-vol expansion",
        "raise IV-crush avoidance for vol expansion",
    ),
    "macro_shock_against_compression": (
        "avoid compression entries during macro shock regimes",
        "raise macro-shock avoidance for compression",
    ),
    "fakeout_against_directional": (
        "raise fakeout penalty before directional entries",
        "increase fakeout penalty for directional entries",
    ),
    "theta_decay_against_short_duration": (
        "tighten theta/gamma balance and DTE window",
        "tighten theta/gamma balance for short duration",
    ),
    "wrong_delta_direction": (
        "constrain delta sign against expected regime direction",
        "constrain directional delta sign",
    ),
    "overfit_train_only": (
        "raise validation/holdout consistency before promotion",
        "raise holdout consistency weighting",
    ),
    "holdout_collapse": (
        "penalize train-only mutations and require holdout survival",
        "raise holdout consistency weighting",
    ),
    "poor_greek_fit": (
        "raise Greek fit scoring and reject poor Greek profiles",
        "raise Greek fit weighting",
    ),
    "pattern_contradiction": (
        "require pattern agreement with family thesis",
        "raise pattern confidence weighting",
    ),
    "slippage_over_sensitivity": (
        "tighten slippage tolerance before paper promotion",
        "tighten slippage tolerance",
    ),
    "regime_mismatch": (
        "tighten family/regime filter before mutation",
        "tighten family regime filters",
    ),
    "mutation_drift": (
        "reject mutation drift outside family envelope",
        "reject family-envelope drift",
    ),
    "unsafe_structure_rejected": (
        "reject undefined-risk structures before scoring",
        "reject undefined-risk structures before scoring",
    ),
    "premium_overpayment_trap_failure": (
        "avoid overpaying high-IV premium without catalyst",
        "increase premium-overpayment penalty",
    ),
    "iv_crush_after_vol_expansion_failure": (
        "avoid long-vol after IV crush evidence",
        "strengthen post-event IV-crush avoidance",
    ),
    "front_event_bump_against_compression": (
        "avoid compression before front-expiry event bump",
        "block compression during front-expiry event bumps",
    ),
    "backwardation_against_compression": (
        "avoid compression during backwardation/macro shock",
        "strengthen compression macro/term guard",
    ),
    "skew_trap_against_directional": (
        "require directional skew alignment",
        "require directional skew alignment",
    ),
    "surface_instability_fakeout_failure": (
        "avoid unstable surface fakeout windows",
        "tighten unstable-surface fakeout guard",
    ),
    "short_duration_front_iv_instability": (
        "avoid short-duration entries during front-IV instability",
        "tighten short-duration front-IV instability guard",
    ),
    "term_structure_mismatch": (
        "require family term-structure fit",
        "tighten term-structure family fit",
    ),
    "wing_elevation_breakout_risk": (
        "avoid compression when wings imply breakout risk",
        "penalize wing-elevation breakout risk",
    ),
    # Macro-event fixture expansion failure modes
    "macro_fakeout_against_directional": (
        "avoid directional entries when macro context contradicts the breakout direction",
        "macro fakeout penalty",
    ),
    "event_gap_against_short_duration": (
        "avoid short-duration entries near macro event gaps",
        "stronger event-gap guard",
    ),
    "rate_shock_against_compression": (
        "avoid compression structures during rate-shock regimes",
        "rate-shock avoidance for compression",
    ),
    "vix_spike_against_compression": (
        "avoid compression structures during VIX/VVIX stress",
        "VIX/VVIX stress guard",
    ),
    "post_event_crush_against_vol_expansion": (
        "avoid long-vol expansion after event-driven IV crush",
        "post-event crush avoidance for vol expansion",
    ),
    "breadth_contradiction_against_directional": (
        "require breadth confirmation for directional entries",
        "breadth confirmation guard for directional",
    ),
    "liquidity_contraction_bad_fill_failure": (
        "avoid defined-risk entries when liquidity regime contracts",
        "liquidity-contraction guard for short-duration",
    ),
    "overnight_gap_slippage_failure": (
        "avoid overnight/futures-gap pressure windows",
        "overnight-risk penalty",
    ),
    "sector_rotation_mismatch": (
        "avoid directional entries when sector rotation chops the index",
        "sector-alignment guard",
    ),
    "macro_event_overfit": (
        "do not promote based on a single macro-event scenario",
        "macro holdout weighting",
    ),
    # Sector/peer/fundamental fixture expansion failure modes
    "peer_contradiction_against_directional": (
        "avoid directional entries when peer-relative context contradicts the breakout",
        "peer confirmation guard",
    ),
    "valuation_trap_against_directional": (
        "avoid directional entries when valuation trap risk is high",
        "valuation trap penalty",
    ),
    "low_dispersion_against_vol_expansion": (
        "avoid long-vol entries in low peer-dispersion windows",
        "peer-dispersion requirement for vol expansion",
    ),
    "post_event_clarity_against_vol_expansion": (
        "avoid long-vol entries in post-earnings quality windows",
        "low-dispersion requirement for compression / post-event clarity guard",
    ),
    "high_dispersion_against_compression": (
        "avoid compression entries in high-dispersion fundamental windows",
        "low-dispersion requirement for compression",
    ),
    "revision_shock_against_compression": (
        "avoid compression entries in revision-shock fundamental windows",
        "revision-shock guard for compression",
    ),
    "crowded_fakeout_against_short_duration": (
        "avoid short-duration entries in crowded-unwind fundamental windows",
        "crowding/fakeout penalty for short duration",
    ),
    "small_cap_liquidity_decay_against_short_duration": (
        "avoid short-duration entries in small-cap liquidity decay windows",
        "sector-liquidity guard",
    ),
    "sector_rotation_late_day_bad_fill": (
        "avoid short-duration entries during late-day sector rotation liquidity fade",
        "sector-rotation late-day guard",
    ),
    "fundamental_event_overfit": (
        "do not promote based on a single benign fundamental scenario",
        "fundamental holdout weighting",
    ),
}


def _severity(score: float, recurrence: int) -> str:
    if score >= 0.80 or recurrence >= 4:
        return "critical"
    if score >= 0.62 or recurrence >= 2:
        return "high"
    if score >= 0.40:
        return "medium"
    return "low"


def _mode(
    mode_id: str,
    row: dict,
    metric_name: str,
    metric_value: float,
    regime: str,
    notes: str,
) -> FailureMode:
    mitigation, update = MITIGATION_MAP[mode_id]
    score = round(max(0.0, min(1.0, metric_value)), 6)
    evidence = FailureModeEvidence(
        source="tournament_or_mutation_record",
        strategy_id=str(row.get("strategy_id", "")),
        family=str(row.get("strategy_family", "")),
        window_or_regime=regime,
        metric_name=metric_name,
        metric_value=score,
        notes=notes,
    )
    return FailureMode(
        failure_mode_id=mode_id,
        affected_strategy_ids=[str(row.get("strategy_id", ""))],
        affected_family=str(row.get("strategy_family", "")),
        windows_or_regimes=[regime] if regime else [],
        evidence_score=score,
        recurrence_count=1,
        severity=_severity(score, 1),
        mitigation_hint=mitigation,
        recommended_mutation_constraint_update=update,
        evidence=[evidence],
    )


def _row_float(row: dict, key: str, fallback: float) -> float:
    value = row.get(key, fallback)
    if value is None:
        return fallback
    return float(value)


def _event_overnight_gap(row: dict) -> float:
    return max(
        _row_float(row, "average_event_gap_risk_penalty", 0.0),
        _row_float(row, "average_overnight_futures_pressure", 0.0) if "average_overnight_futures_pressure" in row else 0.0,
    )


def _merge_modes(modes: list[FailureMode]) -> list[FailureMode]:
    merged: dict[tuple[str, str], list[FailureMode]] = {}
    for mode in modes:
        merged.setdefault((mode.failure_mode_id, mode.affected_family), []).append(mode)
    output: list[FailureMode] = []
    for (mode_id, family), group in merged.items():
        strategy_ids = sorted({sid for mode in group for sid in mode.affected_strategy_ids if sid})
        regimes = sorted({regime for mode in group for regime in mode.windows_or_regimes if regime})
        evidence = [item for mode in group for item in mode.evidence]
        score = round(sum(mode.evidence_score for mode in group) / len(group), 6)
        mitigation, update = MITIGATION_MAP[mode_id]
        output.append(FailureMode(
            failure_mode_id=mode_id,
            affected_strategy_ids=strategy_ids,
            affected_family=family,
            windows_or_regimes=regimes,
            evidence_score=score,
            recurrence_count=len(group),
            severity=_severity(score, len(group)),
            mitigation_hint=mitigation,
            recommended_mutation_constraint_update=update,
            evidence=evidence,
        ))
    return sorted(output, key=lambda mode: (mode.failure_mode_id, mode.affected_family))


def mine_failure_modes(
    tournament_rows: list[dict],
    mutation_rows: list[dict],
    unsafe_rejections: list[dict],
) -> FailureModeRegistry:
    modes: list[FailureMode] = []
    rows = tournament_rows + mutation_rows
    for row in rows:
        family = str(row.get("strategy_family", ""))
        worst_regimes = list(row.get("worst_regimes", []))
        worst_slippage = str(row.get("worst_slippage_regime", ""))
        worst_iv_surface_regime = str(row.get("worst_iv_surface_regime", ""))
        worst_iv_surface_scenario = str(row.get("worst_iv_surface_scenario", ""))
        avg_premium_overpayment = _row_float(row, "average_premium_overpayment_score", 0.0)
        avg_iv_crush = _row_float(row, "average_iv_crush_score", 0.0)
        avg_front_event_bump = _row_float(row, "average_front_event_bump_score", 0.0)
        avg_skew_trap = _row_float(row, "average_skew_trap_score", 0.0)
        avg_wing_elevation = _row_float(row, "average_wing_elevation_score", 0.0)
        avg_surface_instability = _row_float(row, "average_surface_instability_penalty", 0.0)
        avg_term_structure_risk = _row_float(row, "average_term_structure_risk_penalty", 0.0)
        if worst_slippage == "high_spread_bad_fill" or float(row.get("average_expected_slippage_pct", 0.0)) >= 0.05:
            modes.append(_mode("high_spread_bad_fill_failure", row, "expected_slippage_pct", 0.70, "high_spread_bad_fill", "high spread remained a worst fill regime"))
        if "low_liquidity_decay" in worst_regimes or float(row.get("average_liquidity_score", 1.0)) < 0.50:
            modes.append(_mode("low_liquidity_decay_failure", row, "average_liquidity_score", 0.65, "low_liquidity_decay", "liquidity decay affected family score"))
        if family == "volatility_expansion" and (
            str(row.get("worst_greek_risk_regime", "")) == "post_event_iv_crush"
            or float(row.get("average_iv_score", row.get("average_iv_context_score", 1.0))) < 0.45
        ):
            modes.append(_mode("IV_crush_against_vol_expansion", row, "iv_context_score", 0.74, "post_event_iv_crush", "long-vol expansion is exposed to IV crush"))
        if family == "volatility_compression" and (
            str(row.get("worst_greek_risk_regime", "")) == "macro_shock_risk_off"
            or "macro_shock_risk_off" in worst_regimes
        ):
            modes.append(_mode("macro_shock_against_compression", row, "macro_shock_pressure", 0.72, "macro_shock_risk_off", "compression is fragile in macro-shock regimes"))
        if family == "directional_convexity" and (
            "gap_reversal" in worst_regimes
            or "pattern-failed-breakout-reversal" in row.get("penalizing_pattern_ids", [])
        ):
            modes.append(_mode("fakeout_against_directional", row, "fakeout_pressure", 0.68, "gap_reversal", "directional entries are fakeout-sensitive"))
        if family == "short_duration_defined_risk" and (
            "low_liquidity_decay" in worst_regimes
            or float(row.get("average_theta_fit_score", 1.0)) < 0.65
        ):
            modes.append(_mode("theta_decay_against_short_duration", row, "theta_fit_score", 0.66, "low_liquidity_decay", "short-duration entries carry theta/liquidity risk"))
        if float(row.get("average_delta_fit_score", 1.0)) < 0.45:
            modes.append(_mode("wrong_delta_direction", row, "average_delta_fit_score", 0.60, str(row.get("worst_greek_risk_regime", "")), "delta fit was weak"))
        if row.get("overfit_level") == "high":
            modes.append(_mode("overfit_train_only", row, "overfit_level", 0.82, "train_validation_holdout", "high overfit detected"))
        if float(row.get("holdout_score", 0.0)) < -5.0:
            modes.append(_mode("holdout_collapse", row, "holdout_score", 0.78, "holdout", "holdout score collapsed"))
        if float(row.get("average_greek_fit_score", 1.0)) < 0.60:
            modes.append(_mode("poor_greek_fit", row, "average_greek_fit_score", 0.67, str(row.get("worst_greek_risk_regime", "")), "Greek fit below threshold"))
        if float(row.get("average_pattern_fixture_score", 1.0)) < 0.55:
            modes.append(_mode("pattern_contradiction", row, "average_pattern_fixture_score", 0.58, "pattern_fixture_corpus", "pattern score contradicted family thesis"))
        if float(row.get("slippage_robustness_score", 1.0)) < 0.57:
            modes.append(_mode("slippage_over_sensitivity", row, "slippage_robustness_score", 0.63, worst_slippage, "slippage robustness below threshold"))
        if float(row.get("family_regime_survival", 1.0)) < 0.40:
            modes.append(_mode("regime_mismatch", row, "family_regime_survival", 0.62, "multi_regime", "family did not survive target regimes"))
        if float(row.get("mutation_adjustment", 0.0)) < -0.02:
            modes.append(_mode("mutation_drift", row, "mutation_adjustment", 0.64, "mutation_population", "mutation adjustment was negative"))
        if avg_premium_overpayment >= 0.62:
            modes.append(_mode("premium_overpayment_trap_failure", row, "average_premium_overpayment_score", avg_premium_overpayment, worst_iv_surface_scenario or "premium_overpayment_trap", "IV surface marked high premium overpayment pressure"))
        if family == "volatility_expansion" and (
            avg_iv_crush >= 0.65
            or worst_iv_surface_regime == "post_event_iv_crush"
            or worst_iv_surface_scenario == "post_event_iv_crush"
        ):
            modes.append(_mode("iv_crush_after_vol_expansion_failure", row, "average_iv_crush_score", max(avg_iv_crush, 0.65), "post_event_iv_crush", "long-vol family collided with IV crush evidence"))
        if family == "volatility_compression" and avg_front_event_bump >= 0.55:
            modes.append(_mode("front_event_bump_against_compression", row, "average_front_event_bump_score", avg_front_event_bump, "front_expiry_event_bump", "compression family collided with a front-expiry event bump"))
        if family == "volatility_compression" and (
            avg_term_structure_risk >= 0.55
            or worst_iv_surface_regime == "macro_shock_risk_off"
            or worst_iv_surface_scenario == "macro_shock_backwardation"
        ):
            modes.append(_mode("backwardation_against_compression", row, "average_term_structure_risk_penalty", max(avg_term_structure_risk, 0.55), "macro_shock_risk_off", "compression family collided with backwardation or macro term stress"))
        if family == "directional_convexity" and avg_skew_trap >= 0.55:
            modes.append(_mode("skew_trap_against_directional", row, "average_skew_trap_score", avg_skew_trap, worst_iv_surface_scenario or "skew_distortion", "directional family carried skew-trap pressure"))
        if family == "directional_convexity" and avg_surface_instability >= 0.55:
            modes.append(_mode("surface_instability_fakeout_failure", row, "average_surface_instability_penalty", avg_surface_instability, worst_iv_surface_scenario or "unstable_surface_fakeout", "directional family collided with unstable-surface fakeout risk"))
        if family == "short_duration_defined_risk" and avg_front_event_bump >= 0.50:
            modes.append(_mode("short_duration_front_iv_instability", row, "average_front_event_bump_score", avg_front_event_bump, "front_expiry_event_bump", "short-duration family carried front-IV instability pressure"))
        if avg_term_structure_risk >= 0.62:
            modes.append(_mode("term_structure_mismatch", row, "average_term_structure_risk_penalty", avg_term_structure_risk, worst_iv_surface_regime or "term_structure_stress", "family term-state fit was weak"))
        if family == "volatility_compression" and avg_wing_elevation >= 0.62:
            modes.append(_mode("wing_elevation_breakout_risk", row, "average_wing_elevation_score", avg_wing_elevation, "wing_elevation_breakout", "compression family collided with wing-elevation breakout pressure"))

        # Macro-event fixture expansion detection
        avg_macro_fit = _row_float(row, "average_macro_fit_score", 1.0)
        avg_macro_risk = _row_float(row, "average_macro_risk_score", 0.0)
        avg_macro_contradiction = _row_float(row, "average_macro_contradiction_penalty", 0.0)
        avg_event_gap_risk = _row_float(row, "average_event_gap_risk_penalty", 0.0)
        avg_rate_shock_score = _row_float(row, "average_rate_shock_score", 0.0)
        avg_vix_vvix_stress = _row_float(row, "average_vix_vvix_stress_score", 0.0)
        avg_breadth_sector = _row_float(row, "average_breadth_sector_confirmation_score", 0.5)
        avg_liquidity_regime_macro = _row_float(row, "average_liquidity_regime_macro_score", 1.0)
        best_macro_scenario = str(row.get("best_macro_scenario", ""))
        worst_macro_scenario = str(row.get("worst_macro_scenario", ""))
        if family == "directional_convexity" and (
            avg_macro_contradiction >= 0.55
            or "gap_reversal" in worst_regimes
            or worst_macro_scenario in {"overnight_gap_risk", "sector_rotation_growth_to_value"}
        ):
            modes.append(_mode("macro_fakeout_against_directional", row, "average_macro_contradiction_penalty", max(avg_macro_contradiction, 0.55), worst_macro_scenario or "gap_reversal", "directional entry collided with contradictory macro context"))
        if family == "directional_convexity" and avg_breadth_sector < 0.42:
            modes.append(_mode("breadth_contradiction_against_directional", row, "average_breadth_sector_confirmation_score", 1.0 - avg_breadth_sector, worst_macro_scenario or "breadth_breakdown", "directional entry lacked breadth confirmation"))
        if family == "short_duration_defined_risk" and (
            avg_event_gap_risk >= 0.55
            or "event_vol_expansion" in worst_regimes
            or worst_macro_scenario in {"pre_fomc_vol_expansion", "overnight_gap_risk"}
        ):
            modes.append(_mode("event_gap_against_short_duration", row, "average_event_gap_risk_penalty", max(avg_event_gap_risk, 0.55), worst_macro_scenario or "event_vol_expansion", "short-duration entry collided with event-gap risk"))
        if family == "short_duration_defined_risk" and avg_liquidity_regime_macro < 0.38:
            modes.append(_mode("liquidity_contraction_bad_fill_failure", row, "average_liquidity_regime_macro_score", 1.0 - avg_liquidity_regime_macro, worst_macro_scenario or "liquidity_contraction_bad_fill", "short-duration entry collided with liquidity contraction"))
        if family == "volatility_compression" and (
            avg_rate_shock_score >= 0.65
            or worst_macro_scenario in {"hot_cpi_rate_shock"}
        ):
            modes.append(_mode("rate_shock_against_compression", row, "average_rate_shock_score", max(avg_rate_shock_score, 0.65), worst_macro_scenario or "hot_cpi_rate_shock", "compression family collided with rate-shock regime"))
        if family == "volatility_compression" and (
            avg_vix_vvix_stress >= 0.70
            or worst_macro_scenario in {"vix_vvix_spike"}
        ):
            modes.append(_mode("vix_spike_against_compression", row, "average_vix_vvix_stress_score", max(avg_vix_vvix_stress, 0.70), worst_macro_scenario or "vix_vvix_spike", "compression family collided with VIX/VVIX spike"))
        if family == "volatility_expansion" and (
            "post_event_iv_crush" in worst_regimes
            or worst_macro_scenario in {"post_fomc_iv_crush"}
        ):
            modes.append(_mode("post_event_crush_against_vol_expansion", row, "average_macro_risk_score", 0.70, worst_macro_scenario or "post_fomc_iv_crush", "long-vol family collided with post-event crush macro normalization"))
        if _event_overnight_gap(row) >= 0.60:
            modes.append(_mode("overnight_gap_slippage_failure", row, "average_event_gap_risk_penalty", avg_event_gap_risk, worst_macro_scenario or "overnight_gap_risk", "overnight/futures gap pressure hurt fill quality"))
        if family == "directional_convexity" and worst_macro_scenario in {"sector_rotation_growth_to_value"}:
            modes.append(_mode("sector_rotation_mismatch", row, "average_macro_fit_score", 1.0 - avg_macro_fit, worst_macro_scenario, "directional entry collided with sector-rotation chop"))
        if avg_macro_fit >= 0.75 and len(set(row.get("macro_event_risk_flags", []))) == 0:
            modes.append(_mode("macro_event_overfit", row, "average_macro_fit_score", avg_macro_fit, best_macro_scenario or "single_macro_scenario", "strategy overfit to a single benign macro scenario"))

        # Sector/peer/fundamental fixture expansion detection
        avg_fundamental_fit = _row_float(row, "average_fundamental_fit_score", 1.0)
        avg_sector_fit = _row_float(row, "average_sector_fit_score", 1.0)
        avg_peer_confirmation = _row_float(row, "average_peer_confirmation_score", 1.0)
        avg_fundamental_confirmation = _row_float(row, "average_fundamental_confirmation_score", 1.0)
        avg_valuation_risk = _row_float(row, "average_valuation_risk_score", 0.0)
        avg_earnings_quality = _row_float(row, "average_earnings_quality_score", 0.5)
        avg_crowding_risk = _row_float(row, "average_crowding_risk_score", 0.0)
        avg_fundamental_contradiction = _row_float(row, "average_fundamental_contradiction_penalty", 0.0)
        avg_fragility_penalty = _row_float(row, "average_fragility_penalty", 0.0)
        best_fundamental_scenario = str(row.get("best_fundamental_scenario", ""))
        worst_fundamental_scenario = str(row.get("worst_fundamental_scenario", ""))
        fundamental_risk_flags = list(row.get("fundamental_risk_flags", []))

        if family == "directional_convexity":
            if avg_fundamental_contradiction >= 0.55 or "peer_contradiction" in fundamental_risk_flags:
                modes.append(_mode(
                    "peer_contradiction_against_directional", row,
                    "average_fundamental_contradiction_penalty",
                    max(avg_fundamental_contradiction, 0.55),
                    worst_fundamental_scenario or "peer_contradiction",
                    "directional entry collided with peer-relative contradiction",
                ))
            if avg_valuation_risk >= 0.60 or "valuation_trap" in fundamental_risk_flags:
                modes.append(_mode(
                    "valuation_trap_against_directional", row,
                    "average_valuation_risk_score", max(avg_valuation_risk, 0.60),
                    worst_fundamental_scenario or "valuation_trap",
                    "directional entry collided with valuation trap",
                ))

        if family == "volatility_expansion":
            peer_dispersion_proxy = max(0.0, 1.0 - avg_peer_confirmation)
            if peer_dispersion_proxy < 0.30 or "low_dispersion_against_vol_expansion" in fundamental_risk_flags:
                modes.append(_mode(
                    "low_dispersion_against_vol_expansion", row,
                    "average_peer_confirmation_score", 1.0 - peer_dispersion_proxy,
                    worst_fundamental_scenario or "low_dispersion",
                    "long-vol family collided with low peer dispersion",
                ))
            if avg_earnings_quality >= 0.65 or "post_event_clarity_against_vol_expansion" in fundamental_risk_flags:
                modes.append(_mode(
                    "post_event_clarity_against_vol_expansion", row,
                    "average_earnings_quality_score", max(avg_earnings_quality, 0.65),
                    worst_fundamental_scenario or "post_event_clarity",
                    "long-vol family collided with post-event quality clarity",
                ))

        if family == "volatility_compression":
            if avg_crowding_risk >= 0.60 or "high_dispersion_against_compression" in fundamental_risk_flags:
                modes.append(_mode(
                    "high_dispersion_against_compression", row,
                    "average_crowding_risk_score", max(avg_crowding_risk, 0.60),
                    worst_fundamental_scenario or "high_dispersion",
                    "compression family collided with high-dispersion fundamental window",
                ))
            if avg_fundamental_contradiction >= 0.55 or "revision_shock_against_compression" in fundamental_risk_flags:
                modes.append(_mode(
                    "revision_shock_against_compression", row,
                    "average_fundamental_contradiction_penalty",
                    max(avg_fundamental_contradiction, 0.55),
                    worst_fundamental_scenario or "revision_shock",
                    "compression family collided with revision-shock fundamental window",
                ))

        if family == "short_duration_defined_risk":
            if avg_crowding_risk >= 0.65 or "crowded_fakeout_against_short_duration" in fundamental_risk_flags:
                modes.append(_mode(
                    "crowded_fakeout_against_short_duration", row,
                    "average_crowding_risk_score", max(avg_crowding_risk, 0.65),
                    worst_fundamental_scenario or "crowded_fakeout",
                    "short-duration family collided with crowded-fakeout fundamental window",
                ))
            if avg_fragility_penalty >= 0.55 or "small_cap_liquidity_decay_against_short_duration" in fundamental_risk_flags:
                modes.append(_mode(
                    "small_cap_liquidity_decay_against_short_duration", row,
                    "average_fragility_penalty", max(avg_fragility_penalty, 0.55),
                    worst_fundamental_scenario or "small_cap_liquidity_decay",
                    "short-duration family collided with small-cap liquidity decay",
                ))
            if "sector_rotation_late_day_bad_fill" in fundamental_risk_flags or (
                avg_sector_fit < 0.45 and avg_crowding_risk >= 0.50
            ):
                modes.append(_mode(
                    "sector_rotation_late_day_bad_fill", row,
                    "average_sector_fit_score", max(0.0, 1.0 - avg_sector_fit),
                    worst_fundamental_scenario or "sector_rotation_late_day",
                    "short-duration family collided with sector-rotation late-day liquidity fade",
                ))

        if avg_fundamental_fit >= 0.75 and len(fundamental_risk_flags) == 0:
            modes.append(_mode(
                "fundamental_event_overfit", row, "average_fundamental_fit_score",
                avg_fundamental_fit, best_fundamental_scenario or "single_fundamental_scenario",
                "strategy overfit to a single benign fundamental scenario",
            ))

    for rejection in unsafe_rejections:
        row = {
            "strategy_id": rejection.get("genome_id", ""),
            "strategy_family": rejection.get("family", ""),
        }
        modes.append(_mode("unsafe_structure_rejected", row, "unsafe_rejection", 0.90, "family_limit_validator", "unsafe mutation or structure rejected"))
        modes.append(_mode("mutation_drift", row, "family_limit_rejection", 0.72, "family_limit_validator", "mutation drift rejected by family envelope"))

    merged = _merge_modes(modes)
    hints = [
        FailureModeMitigationHint(
            mode.failure_mode_id,
            mode.mitigation_hint,
            mode.recommended_mutation_constraint_update,
        )
        for mode in merged
    ]
    clusters = [
        FailureModeCluster(
            cluster_id=f"cluster-{family or 'all'}",
            failure_mode_ids=sorted({mode.failure_mode_id for mode in merged if mode.affected_family == family}),
            affected_families=[family],
            severity=max(
                [mode.severity for mode in merged if mode.affected_family == family],
                default="low",
                key=lambda value: {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(value, 0),
            ),
        )
        for family in sorted({mode.affected_family for mode in merged})
    ]
    updates = [update.to_dict() for update in constraint_updates_from_failure_modes([mode.to_dict() for mode in merged])]
    return FailureModeRegistry(
        registry_id="dopey-failure-mode-registry-v1",
        failure_modes=merged,
        clusters=clusters,
        mitigation_hints=hints,
        constraint_updates=updates,
    )
