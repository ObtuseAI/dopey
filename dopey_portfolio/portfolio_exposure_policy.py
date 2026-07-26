"""Portfolio-level paper exposure policy."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PortfolioReplayPolicy:
    policy_id: str
    max_total_paper_premium_risk_units: float
    max_zero_dte_exposure_share: float
    max_swing_exposure_share: float
    max_paper_shadow_exposure_share: float
    max_delayed_rotation_reserve_share: float
    max_underlying_family_units: float
    max_regime_family_units: float
    max_synthetic_underlying_units: float
    max_high_gamma_units: float
    max_high_theta_units: float
    max_iv_crush_units: float
    max_event_macro_units: float
    max_same_direction_share: float
    max_open_positions: int
    max_new_entries_per_day: int
    max_zero_dte_entries_per_day: int
    max_delayed_exits_per_day: int
    low_liquidity_family_ids: list[str]
    paper_only: bool
    live_blocked: bool
    real_capital_sizing_allowed: bool
    broker_execution_allowed: bool
    live_threshold_mutation_allowed: bool

    def __post_init__(self) -> None:
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("portfolio replay policy must be paper_only and live_blocked")
        if self.real_capital_sizing_allowed is not False:
            raise ValueError("portfolio replay policy cannot allow real capital sizing")
        if self.broker_execution_allowed is not False:
            raise ValueError("portfolio replay policy cannot allow broker execution")
        if self.live_threshold_mutation_allowed is not False:
            raise ValueError("portfolio replay policy cannot mutate live thresholds")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PortfolioReplayPolicy":
        return cls(
            policy_id=str(record["policy_id"]),
            max_total_paper_premium_risk_units=float(record["max_total_paper_premium_risk_units"]),
            max_zero_dte_exposure_share=float(record["max_zero_dte_exposure_share"]),
            max_swing_exposure_share=float(record["max_swing_exposure_share"]),
            max_paper_shadow_exposure_share=float(record["max_paper_shadow_exposure_share"]),
            max_delayed_rotation_reserve_share=float(record["max_delayed_rotation_reserve_share"]),
            max_underlying_family_units=float(record["max_underlying_family_units"]),
            max_regime_family_units=float(record["max_regime_family_units"]),
            max_synthetic_underlying_units=float(record["max_synthetic_underlying_units"]),
            max_high_gamma_units=float(record["max_high_gamma_units"]),
            max_high_theta_units=float(record["max_high_theta_units"]),
            max_iv_crush_units=float(record["max_iv_crush_units"]),
            max_event_macro_units=float(record["max_event_macro_units"]),
            max_same_direction_share=float(record["max_same_direction_share"]),
            max_open_positions=int(record["max_open_positions"]),
            max_new_entries_per_day=int(record["max_new_entries_per_day"]),
            max_zero_dte_entries_per_day=int(record["max_zero_dte_entries_per_day"]),
            max_delayed_exits_per_day=int(record["max_delayed_exits_per_day"]),
            low_liquidity_family_ids=[str(value) for value in record["low_liquidity_family_ids"]],
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            real_capital_sizing_allowed=bool(record["real_capital_sizing_allowed"]),
            broker_execution_allowed=bool(record["broker_execution_allowed"]),
            live_threshold_mutation_allowed=bool(record["live_threshold_mutation_allowed"]),
        )


def default_portfolio_replay_policy() -> PortfolioReplayPolicy:
    return PortfolioReplayPolicy(
        policy_id="dopey-portfolio-replay-policy-v1",
        max_total_paper_premium_risk_units=60.0,
        max_zero_dte_exposure_share=0.35,
        max_swing_exposure_share=0.82,
        max_paper_shadow_exposure_share=0.10,
        max_delayed_rotation_reserve_share=0.16,
        max_underlying_family_units=12.0,
        max_regime_family_units=18.0,
        max_synthetic_underlying_units=8.0,
        max_high_gamma_units=8.0,
        max_high_theta_units=8.0,
        max_iv_crush_units=7.0,
        max_event_macro_units=6.0,
        max_same_direction_share=0.68,
        max_open_positions=28,
        max_new_entries_per_day=4,
        max_zero_dte_entries_per_day=2,
        max_delayed_exits_per_day=3,
        low_liquidity_family_ids=["underlying-family-05"],
        paper_only=True,
        live_blocked=True,
        real_capital_sizing_allowed=False,
        broker_execution_allowed=False,
        live_threshold_mutation_allowed=False,
    )


def portfolio_policy_status(snapshot: dict[str, Any], policy: PortfolioReplayPolicy) -> dict[str, Any]:
    total_units = float(snapshot.get("total_paper_premium_risk_units", 0.0))
    zero_units = float(snapshot.get("zero_dte_paper_units", 0.0))
    swing_units = float(snapshot.get("swing_paper_units", 0.0))
    shadow_units = float(snapshot.get("paper_shadow_units", 0.0))
    delayed_units = float(snapshot.get("delayed_rotation_reserved_units", 0.0))
    call_units = float(snapshot.get("call_units", 0.0))
    put_units = float(snapshot.get("put_units", 0.0))
    reasons: list[str] = []
    if total_units > policy.max_total_paper_premium_risk_units + 1e-9:
        reasons.append("total_paper_premium_risk_units_cap")
    if _share(zero_units, total_units) > policy.max_zero_dte_exposure_share + 1e-9:
        reasons.append("zero_dte_portfolio_exposure_cap")
    if _share(swing_units, total_units) > policy.max_swing_exposure_share + 1e-9:
        reasons.append("swing_portfolio_exposure_monitor")
    if _share(shadow_units, total_units) > policy.max_paper_shadow_exposure_share + 1e-9:
        reasons.append("paper_shadow_exposure_cap")
    if _share(delayed_units, total_units) > policy.max_delayed_rotation_reserve_share + 1e-9:
        reasons.append("delayed_rotation_reserve_cap")
    if float(snapshot.get("high_gamma_units", 0.0)) > policy.max_high_gamma_units + 1e-9:
        reasons.append("high_gamma_exposure_cap")
    if float(snapshot.get("high_theta_units", 0.0)) > policy.max_high_theta_units + 1e-9:
        reasons.append("high_theta_exposure_cap")
    if float(snapshot.get("iv_crush_exposed_units", 0.0)) > policy.max_iv_crush_units + 1e-9:
        reasons.append("iv_crush_exposure_cap")
    if float(snapshot.get("event_macro_exposed_units", 0.0)) > policy.max_event_macro_units + 1e-9:
        reasons.append("event_macro_exposure_cap")
    if _share(max(call_units, put_units), call_units + put_units) > policy.max_same_direction_share + 1e-9:
        reasons.append("call_put_imbalance_cap")
    for family_id, units in _float_map(snapshot.get("underlying_family_exposure", {})).items():
        limit = 1.0 if family_id in policy.low_liquidity_family_ids else policy.max_underlying_family_units
        if units > limit + 1e-9:
            reasons.append(f"underlying_family_cap:{family_id}")
    for regime_family, units in _float_map(snapshot.get("regime_family_exposure", {})).items():
        if units > policy.max_regime_family_units + 1e-9:
            reasons.append(f"regime_family_cap:{regime_family}")
    return {
        "policy_id": policy.policy_id,
        "status": "blocked" if reasons else "within_cap",
        "reason_codes": sorted(set(reasons)),
        "zero_dte_exposure_share": round(_share(zero_units, total_units), 6),
        "swing_exposure_share": round(_share(swing_units, total_units), 6),
        "paper_shadow_exposure_share": round(_share(shadow_units, total_units), 6),
        "delayed_rotation_reserve_share": round(_share(delayed_units, total_units), 6),
        "call_put_imbalance_share": round(_share(max(call_units, put_units), call_units + put_units), 6),
        "same_day_churn_allowed": False,
        "paper_shadow_contained": "paper_shadow_exposure_cap" not in reasons,
        "delayed_rotation_advisory_only": True,
        "allocator_feedback_advisory_only": True,
        "threshold_feedback_advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _share(numerator: float, denominator: float) -> float:
    if denominator <= 0.0:
        return 0.0
    return numerator / denominator


def _float_map(record: Any) -> dict[str, float]:
    if not isinstance(record, dict):
        return {}
    return {str(key): float(value) for key, value in record.items()}
