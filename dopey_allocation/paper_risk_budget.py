"""Abstract paper risk budget for proof-weighted allocation."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class PaperRiskBudget:
    budget_id: str
    max_paper_attention_per_opportunity: float
    max_paper_premium_risk_units_per_opportunity: float
    max_paper_premium_risk_units_per_underlying_family: float
    max_paper_premium_risk_units_per_regime_family: float
    max_zero_dte_paper_exposure_share: float
    max_same_regime_concentration: float
    max_high_gamma_exposure: float
    max_high_theta_exposure: float
    max_iv_crush_exposure: float
    max_event_macro_exposure: float
    max_delayed_rotation_reserve: float
    max_paper_shadow_exposure: float
    paper_only: bool
    live_blocked: bool

    def __post_init__(self) -> None:
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("paper risk budget must be paper_only and live_blocked")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PaperRiskBudget":
        return cls(
            budget_id=str(record["budget_id"]),
            max_paper_attention_per_opportunity=float(record["max_paper_attention_per_opportunity"]),
            max_paper_premium_risk_units_per_opportunity=float(record["max_paper_premium_risk_units_per_opportunity"]),
            max_paper_premium_risk_units_per_underlying_family=float(record["max_paper_premium_risk_units_per_underlying_family"]),
            max_paper_premium_risk_units_per_regime_family=float(record["max_paper_premium_risk_units_per_regime_family"]),
            max_zero_dte_paper_exposure_share=float(record["max_zero_dte_paper_exposure_share"]),
            max_same_regime_concentration=float(record["max_same_regime_concentration"]),
            max_high_gamma_exposure=float(record["max_high_gamma_exposure"]),
            max_high_theta_exposure=float(record["max_high_theta_exposure"]),
            max_iv_crush_exposure=float(record["max_iv_crush_exposure"]),
            max_event_macro_exposure=float(record["max_event_macro_exposure"]),
            max_delayed_rotation_reserve=float(record["max_delayed_rotation_reserve"]),
            max_paper_shadow_exposure=float(record["max_paper_shadow_exposure"]),
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
        )


def default_paper_risk_budget() -> PaperRiskBudget:
    return PaperRiskBudget(
        budget_id="dopey-paper-risk-budget-v1",
        max_paper_attention_per_opportunity=1.0,
        max_paper_premium_risk_units_per_opportunity=3.0,
        max_paper_premium_risk_units_per_underlying_family=10.0,
        max_paper_premium_risk_units_per_regime_family=9.0,
        max_zero_dte_paper_exposure_share=0.35,
        max_same_regime_concentration=0.28,
        max_high_gamma_exposure=6.0,
        max_high_theta_exposure=6.0,
        max_iv_crush_exposure=4.0,
        max_event_macro_exposure=5.0,
        max_delayed_rotation_reserve=4.0,
        max_paper_shadow_exposure=5.0,
        paper_only=True,
        live_blocked=True,
    )
