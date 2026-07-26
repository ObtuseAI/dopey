"""Deterministic synthetic underlying family records for 0DTE fixture replay."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .zero_dte_adversarial_fixture_models import ADVERSARIAL_RISK_VECTORS, FORBIDDEN_LIVE_MARKET_TOKENS


UNDERLYING_FAMILY_NAMES: frozenset[str] = frozenset({
    "index_like_etf",
    "megacap_liquid_equity",
    "high_beta_momentum_equity",
    "event_sensitive_equity",
    "low_liquidity_options_equity",
    "sector_rotation_equity",
    "gap_prone_equity",
    "mean_reversion_equity",
    "trend_persistence_equity",
    "volatility_crush_equity",
    "macro_sensitive_equity",
    "pin_risk_heavy_equity",
})

SYNTHETIC_SYMBOLS_BY_FAMILY: dict[str, str] = {
    "index_like_etf": "SYN_INDEX_A",
    "megacap_liquid_equity": "SYN_MEGA_A",
    "high_beta_momentum_equity": "SYN_MOMO_A",
    "event_sensitive_equity": "SYN_EVENT_A",
    "low_liquidity_options_equity": "SYN_LOWLIQ_A",
    "sector_rotation_equity": "SYN_SECTOR_A",
    "gap_prone_equity": "SYN_GAP_A",
    "mean_reversion_equity": "SYN_MEANREV_A",
    "trend_persistence_equity": "SYN_TREND_A",
    "volatility_crush_equity": "SYN_IVCRUSH_A",
    "macro_sensitive_equity": "SYN_MACRO_A",
    "pin_risk_heavy_equity": "SYN_PIN_A",
}

REAL_TICKER_LIKE_BLOCKLIST: frozenset[str] = frozenset({
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "AAPL",
    "MSFT",
    "TSLA",
    "NVDA",
    "META",
    "AMZN",
    "GOOG",
    "GOOGL",
})


@dataclass(frozen=True)
class ZeroDTEUnderlyingFamily:
    underlying_family_id: str
    family_name: str
    synthetic_underlying_symbol: str
    option_liquidity_archetype: str
    spread_archetype: str
    volatility_archetype: str
    gamma_theta_archetype: str
    event_sensitivity_archetype: str
    macro_sensitivity_archetype: str
    regime_sensitivity_archetype: str
    typical_0dte_risk_vectors: list[str]
    paper_only: bool
    live_blocked: bool
    family_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_underlying_family(self)
        payload = asdict(self)
        payload["family_hash"] = zero_dte_underlying_family_hash(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTEUnderlyingFamily":
        family = cls(
            underlying_family_id=_string_value(data, "underlying_family_id"),
            family_name=_string_value(data, "family_name"),
            synthetic_underlying_symbol=_string_value(data, "synthetic_underlying_symbol"),
            option_liquidity_archetype=_string_value(data, "option_liquidity_archetype"),
            spread_archetype=_string_value(data, "spread_archetype"),
            volatility_archetype=_string_value(data, "volatility_archetype"),
            gamma_theta_archetype=_string_value(data, "gamma_theta_archetype"),
            event_sensitivity_archetype=_string_value(data, "event_sensitivity_archetype"),
            macro_sensitivity_archetype=_string_value(data, "macro_sensitivity_archetype"),
            regime_sensitivity_archetype=_string_value(data, "regime_sensitivity_archetype"),
            typical_0dte_risk_vectors=_string_list_value(data, "typical_0dte_risk_vectors"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
            family_hash=_string_or_empty(data, "family_hash"),
        )
        validate_underlying_family(family)
        return family


def validate_underlying_family(family: ZeroDTEUnderlyingFamily) -> None:
    if family.family_name not in UNDERLYING_FAMILY_NAMES:
        raise ValueError(f"unsupported underlying family: {family.family_name}")
    if family.synthetic_underlying_symbol != SYNTHETIC_SYMBOLS_BY_FAMILY[family.family_name]:
        raise ValueError(f"unexpected synthetic symbol for family: {family.family_name}")
    if not family.synthetic_underlying_symbol.startswith("SYN_"):
        raise ValueError("underlying family must use SYN_ fixture symbols only")
    if family.synthetic_underlying_symbol in REAL_TICKER_LIKE_BLOCKLIST:
        raise ValueError("underlying family cannot use real ticker symbols")
    unknown_risks = [risk for risk in family.typical_0dte_risk_vectors if risk not in ADVERSARIAL_RISK_VECTORS]
    if unknown_risks:
        raise ValueError(f"unsupported family risk vectors: {unknown_risks}")
    if family.paper_only is not True or family.live_blocked is not True:
        raise ValueError("underlying families must be paper_only=true and live_blocked=true")
    encoded = json.dumps(asdict(family), sort_keys=True, ensure_ascii=False).lower()
    if any(token in encoded for token in FORBIDDEN_LIVE_MARKET_TOKENS):
        raise ValueError(f"underlying family contains forbidden live market reference: {family.underlying_family_id}")


def zero_dte_underlying_family_hash(family: ZeroDTEUnderlyingFamily) -> str:
    payload = asdict(family)
    payload["family_hash"] = ""
    return stable_cross_underlying_hash(payload)


def stable_cross_underlying_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _string_value(data: dict[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be non-empty str")
    return value


def _string_or_empty(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str")
    return value


def _bool_value(data: dict[str, Any], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _string_list_value(data: dict[str, Any], key: str) -> list[str]:
    value = data[key]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be list[str]")
    return list(value)
