"""Portfolio exposure snapshot models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .portfolio_hashing import stable_portfolio_hash


@dataclass(frozen=True)
class PortfolioExposureSnapshot:
    snapshot_id: str
    portfolio_id: str
    trading_day_index: int
    total_paper_attention_weight: float
    total_paper_premium_risk_units: float
    zero_dte_paper_units: float
    swing_paper_units: float
    paper_shadow_units: float
    delayed_rotation_reserved_units: float
    call_units: float
    put_units: float
    high_gamma_units: float
    high_theta_units: float
    iv_crush_exposed_units: float
    event_macro_exposed_units: float
    underlying_family_exposure: dict[str, float]
    regime_family_exposure: dict[str, float]
    strategy_type_exposure: dict[str, float]
    constraint_status: dict[str, Any]
    paper_only: bool
    live_blocked: bool
    exposure_hash: str

    def __post_init__(self) -> None:
        values = [
            self.total_paper_attention_weight,
            self.total_paper_premium_risk_units,
            self.zero_dte_paper_units,
            self.swing_paper_units,
            self.paper_shadow_units,
            self.delayed_rotation_reserved_units,
            self.call_units,
            self.put_units,
            self.high_gamma_units,
            self.high_theta_units,
            self.iv_crush_exposed_units,
            self.event_macro_exposed_units,
        ]
        if any(value < 0.0 for value in values):
            raise ValueError("portfolio exposure values must be non-negative")
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("portfolio exposure snapshot must be paper_only and live_blocked")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PortfolioExposureSnapshot":
        return cls(
            snapshot_id=str(record["snapshot_id"]),
            portfolio_id=str(record["portfolio_id"]),
            trading_day_index=int(record["trading_day_index"]),
            total_paper_attention_weight=float(record["total_paper_attention_weight"]),
            total_paper_premium_risk_units=float(record["total_paper_premium_risk_units"]),
            zero_dte_paper_units=float(record["zero_dte_paper_units"]),
            swing_paper_units=float(record["swing_paper_units"]),
            paper_shadow_units=float(record["paper_shadow_units"]),
            delayed_rotation_reserved_units=float(record["delayed_rotation_reserved_units"]),
            call_units=float(record["call_units"]),
            put_units=float(record["put_units"]),
            high_gamma_units=float(record["high_gamma_units"]),
            high_theta_units=float(record["high_theta_units"]),
            iv_crush_exposed_units=float(record["iv_crush_exposed_units"]),
            event_macro_exposed_units=float(record["event_macro_exposed_units"]),
            underlying_family_exposure={str(key): float(value) for key, value in record["underlying_family_exposure"].items()},
            regime_family_exposure={str(key): float(value) for key, value in record["regime_family_exposure"].items()},
            strategy_type_exposure={str(key): float(value) for key, value in record["strategy_type_exposure"].items()},
            constraint_status=dict(record["constraint_status"]),
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            exposure_hash=str(record.get("exposure_hash", "")),
        )


def portfolio_exposure_hash(snapshot: PortfolioExposureSnapshot) -> str:
    payload = snapshot.to_dict()
    payload["exposure_hash"] = ""
    return stable_portfolio_hash(payload)

