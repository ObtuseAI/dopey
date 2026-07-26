"""Strong simple baselines that every candidate must beat after declared costs."""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping


BASELINE_IDS = (
    "no_trade",
    "underlying_only_risk_matched",
    "fixed_defined_risk_option",
    "delta_targeted_long_option",
    "fixed_vertical",
    "naive_immediate_paper_price",
    "naive_limit_paper_price",
    "fixed_fraction_allocation",
    "volatility_matched_allocation",
    "market_implied_distribution",
)


def baseline_specifications() -> Mapping[str, Mapping[str, str | bool]]:
    specifications: dict[str, Mapping[str, str | bool]] = {
        "no_trade": MappingProxyType({"mechanism": "abstain", "costs": "zero", "paper_only": True}),
        "underlying_only_risk_matched": MappingProxyType({"mechanism": "same frozen forecast expressed without options", "costs": "declared underlying cost model", "paper_only": True}),
        "fixed_defined_risk_option": MappingProxyType({"mechanism": "frozen option structure and maturity rule", "costs": "conservative paper executable price", "paper_only": True}),
        "delta_targeted_long_option": MappingProxyType({"mechanism": "nearest liquid contract to frozen absolute delta target", "costs": "conservative paper executable price", "paper_only": True}),
        "fixed_vertical": MappingProxyType({"mechanism": "frozen width defined-risk vertical", "costs": "leg-aware package degradation", "paper_only": True}),
        "naive_immediate_paper_price": MappingProxyType({"mechanism": "first valid quote after decision", "costs": "adverse side plus slippage", "paper_only": True}),
        "naive_limit_paper_price": MappingProxyType({"mechanism": "frozen price-improvement schedule", "costs": "missed fills and opportunity cost", "paper_only": True}),
        "fixed_fraction_allocation": MappingProxyType({"mechanism": "constant maximum-loss fraction", "costs": "full economic stack", "paper_only": True}),
        "volatility_matched_allocation": MappingProxyType({"mechanism": "inverse forecast volatility within hard caps", "costs": "full economic stack", "paper_only": True}),
        "market_implied_distribution": MappingProxyType({"mechanism": "option-implied forecast with no proprietary adjustment", "costs": "surface and executable quote constraints", "paper_only": True}),
    }
    return MappingProxyType(specifications)
