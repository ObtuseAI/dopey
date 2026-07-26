"""Failure-mode feedback constraints for offline DOPEY mutation scoring."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


MUTATION_CONSTRAINT_VERSION = "dopey-mutation-constraints-v1"


@dataclass(frozen=True)
class MutationConstraintUpdate:
    failure_mode_id: str
    affected_family: str
    constraint_update: str
    weight: float

    def to_dict(self) -> dict:
        return asdict(self)


FAILURE_MODE_CONSTRAINT_UPDATES: dict[str, str] = {
    "high_spread_bad_fill_failure": "increase bad-fill avoidance weighting",
    "low_liquidity_decay_failure": "tighten liquidity thresholds",
    "IV_crush_against_vol_expansion": "raise IV-crush avoidance for vol expansion",
    "macro_shock_against_compression": "raise macro-shock avoidance for compression",
    "fakeout_against_directional": "increase fakeout penalty for directional entries",
    "theta_decay_against_short_duration": "tighten theta/gamma balance for short duration",
    "wrong_delta_direction": "constrain directional delta sign",
    "overfit_train_only": "raise holdout consistency weighting",
    "holdout_collapse": "raise holdout consistency weighting",
    "poor_greek_fit": "raise Greek fit weighting",
    "pattern_contradiction": "raise pattern confidence weighting",
    "slippage_over_sensitivity": "tighten slippage tolerance",
    "regime_mismatch": "tighten family regime filters",
    "mutation_drift": "reject family-envelope drift",
    "unsafe_structure_rejected": "reject undefined-risk structures before scoring",
    "premium_overpayment_trap_failure": "increase premium-overpayment penalty",
    "iv_crush_after_vol_expansion_failure": "strengthen post-event IV-crush avoidance",
    "front_event_bump_against_compression": "block compression during front-expiry event bumps",
    "backwardation_against_compression": "strengthen compression macro/term guard",
    "skew_trap_against_directional": "require directional skew alignment",
    "surface_instability_fakeout_failure": "tighten unstable-surface fakeout guard",
    "short_duration_front_iv_instability": "tighten short-duration front-IV instability guard",
    "term_structure_mismatch": "tighten term-structure family fit",
    "wing_elevation_breakout_risk": "penalize wing-elevation breakout risk",
}


def constraint_updates_from_failure_modes(failure_modes: list[dict]) -> list[MutationConstraintUpdate]:
    updates: list[MutationConstraintUpdate] = []
    for mode in failure_modes:
        mode_id = str(mode.get("failure_mode_id", ""))
        update = FAILURE_MODE_CONSTRAINT_UPDATES.get(mode_id, "record mitigation before next mutation")
        severity = str(mode.get("severity", "medium"))
        weight = {"low": 0.001, "medium": 0.002, "high": 0.003, "critical": 0.004}.get(severity, 0.002)
        updates.append(MutationConstraintUpdate(
            failure_mode_id=mode_id,
            affected_family=str(mode.get("affected_family", "")),
            constraint_update=update,
            weight=weight,
        ))
    return updates


def score_penalty_from_constraint_updates(strategy_family: str, updates: list[MutationConstraintUpdate]) -> float:
    penalty = 0.0
    for update in updates:
        if update.affected_family == strategy_family or update.affected_family == "all":
            penalty += update.weight
    return round(penalty, 6)
