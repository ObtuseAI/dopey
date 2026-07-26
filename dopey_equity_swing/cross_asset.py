"""Validated cross-asset regime context for equity-first swing research."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import date
from pathlib import Path
from typing import Any


EXPECTED_FIELDS = (
    "date",
    "symbol",
    "provider_symbol",
    "name",
    "asset_class",
    "subclass",
    "close",
    "volume",
    "source",
    "series_type",
    "contract_metadata_status",
)

MAX_AGE_CALENDAR_DAYS: dict[str, int] = {
    "crypto": 1,
    "futures": 4,
    "commodity": 4,
    "currency": 4,
}

DISCONTINUITY_LIMITS: dict[str, float] = {
    "equity_index": 0.15,
    "treasury": 0.05,
    "energy": 0.25,
    "precious_metal": 0.20,
    "industrial_metal": 0.18,
    "agriculture": 0.18,
    "dollar_index": 0.08,
    "major_fx": 0.08,
    "digital_asset": 0.30,
}

THEME_WEIGHTS: dict[str, dict[str, float]] = {
    "ai": {"NQ": 0.40, "ES": 0.25, "ZN": 0.20, "DXY": -0.15},
    "quantum": {"NQ": 0.35, "RTY": 0.25, "ES": 0.20, "ZN": 0.20},
    "financials": {"ES": 0.35, "RTY": 0.30, "ZN": -0.20, "DXY": 0.15},
    "energy": {"CL": 0.35, "BZ": 0.25, "NG": 0.15, "ES": 0.15, "DXY": -0.10},
    "crypto": {"BTC": 0.35, "ETH": 0.25, "NQ": 0.20, "DXY": -0.20},
    "ev": {"ES": 0.25, "RTY": 0.25, "NQ": 0.20, "CL": -0.15, "ZN": 0.15},
    "consumer": {"ES": 0.35, "RTY": 0.25, "CL": -0.15, "ZN": 0.15, "DXY": -0.10},
    "defensive": {"ES": 0.30, "ZN": 0.30, "GC": 0.20, "DXY": 0.20},
    "healthcare": {"ES": 0.40, "ZN": 0.30, "DXY": -0.15, "GC": 0.15},
    "industrials": {"ES": 0.30, "RTY": 0.25, "HG": 0.25, "CL": 0.10, "DXY": -0.10},
    "utilities": {"ZN": 0.40, "ES": 0.25, "NG": -0.20, "DXY": 0.15},
}


def load_cross_asset_snapshot(data_path: Path, manifest_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"cross-asset manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("provider_terms_reviewed") is not True:
        raise ValueError(f"cross-asset provider terms are not reviewed: {manifest_path}")
    if str(manifest.get("license_status", "")) != "reviewed_allowed_internal_research":
        raise ValueError(f"cross-asset license status is not allowed: {manifest.get('license_status')}")
    if str(manifest.get("dataset_status", "")) != "complete":
        raise ValueError(f"cross-asset manifest is not complete: status={manifest.get('dataset_status')}")
    if not data_path.exists():
        raise FileNotFoundError(f"cross-asset snapshot is missing: {data_path}")
    actual_hash = hashlib.sha256(data_path.read_bytes()).hexdigest()
    if actual_hash != str(manifest.get("file_sha256", "")):
        raise ValueError(
            f"cross-asset snapshot hash mismatch: path={data_path}, expected={manifest.get('file_sha256')}, actual={actual_hash}"
        )
    with data_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPECTED_FIELDS:
            raise ValueError(f"cross-asset schema mismatch: path={data_path}, fields={reader.fieldnames}")
        rows = [_normalize_row(dict(row)) for row in reader]
    if not rows:
        raise ValueError(f"cross-asset snapshot is empty: {data_path}")
    keys = [(str(row["symbol"]), str(row["date"])) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError(f"cross-asset snapshot contains duplicate symbol/date rows: path={data_path}")
    if int(manifest.get("row_count", -1)) != len(rows):
        raise ValueError(
            f"cross-asset row count does not match manifest: path={data_path}, expected={manifest.get('row_count')}, actual={len(rows)}"
        )
    return rows, manifest


def build_cross_asset_regime(
    rows: list[dict[str, Any]],
    macro_summary: dict[str, Any],
    treasury_rows: list[dict[str, str]],
    decision_date: date,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["symbol"]), []).append(row)
    states = {
        symbol: build_series_state(sorted(series, key=lambda row: str(row["date"])), decision_date)
        for symbol, series in sorted(grouped.items())
    }
    required = {"ES", "NQ", "RTY", "ZN", "ZB", "CL", "GC", "DXY", "BTC", "ETH"}
    missing = sorted(required - set(states))
    if missing:
        raise ValueError(f"cross-asset regime is missing required series: {missing}")
    blocked_required = sorted(symbol for symbol in required if states[symbol]["series_status"] != "usable")
    if blocked_required:
        details = {symbol: states[symbol]["quality_flags"] for symbol in blocked_required}
        raise ValueError(f"required cross-asset series failed freshness or continuity gates: {details}")
    risk_weights = {"ES": 0.22, "NQ": 0.18, "RTY": 0.14, "BTC": 0.10, "ETH": 0.06, "HG": 0.08, "DXY": -0.08, "GC": -0.05, "ZN": 0.05, "CL": 0.04}
    risk_score = _weighted_state(states, risk_weights)
    inflation_score = _weighted_state(states, {"CL": 0.24, "BZ": 0.18, "NG": 0.12, "GC": 0.14, "SI": 0.08, "HG": 0.10, "ZN": -0.14})
    growth_score = _weighted_state(states, {"ES": 0.24, "RTY": 0.22, "HG": 0.22, "CL": 0.12, "NQ": 0.12, "ZN": -0.08})
    curve = build_treasury_curve_context(macro_summary, treasury_rows)
    vol_term = macro_summary.get("vol_term_structure", {})
    backwardation = str(vol_term.get("term_structure_state", "")) == "backwardation_stress"
    shock_count = sum(
        state["shock_eligible"] and abs(float(state["return_shock_z"])) >= 2.0
        for state in states.values()
    )
    stress = _clamp01(0.50 * _signed_to_unit(-risk_score) + 0.25 * float(backwardation) + 0.25 * min(shock_count / 5.0, 1.0))
    theme_scores = {
        theme: round(_weighted_state(states, weights), 6)
        for theme, weights in sorted(THEME_WEIGHTS.items())
    }
    return {
        "artifact_type": "cross_asset_regime_context",
        "context_status": "complete",
        "decision_date": decision_date.isoformat(),
        "as_of_date": decision_date.isoformat(),
        "latest_source_date_max": max(str(state["latest_date"]) for state in states.values()),
        "latest_source_date_min": min(str(state["latest_date"]) for state in states.values()),
        "series_count": len(states),
        "asset_classes": sorted({str(row["asset_class"]) for row in rows}),
        "series_states": states,
        "risk_appetite_score": round(risk_score, 6),
        "inflation_pressure_score": round(inflation_score, 6),
        "growth_impulse_score": round(growth_score, 6),
        "systemic_stress_score": round(stress, 6),
        "shock_series_count": shock_count,
        "series_quality": {
            "usable_count": sum(state["series_status"] == "usable" for state in states.values()),
            "blocked_count": sum(state["series_status"] != "usable" for state in states.values()),
            "continuous_futures_proxy_count": sum(state["series_type"] == "continuous_futures_proxy" for state in states.values()),
            "historical_discontinuity_count": sum(int(state["historical_discontinuity_count"]) for state in states.values()),
        },
        "treasury_curve": curve,
        "volatility_term_structure": vol_term,
        "es_positioning": macro_summary.get("es_positioning", {}),
        "fed_liquidity": macro_summary.get("liquidity_impulse", {}),
        "theme_context_scores": theme_scores,
        "use_policy": "confirmation_contradiction_and_joint_risk_veto_only_no_primary_direction_authority",
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }


def build_series_state(rows: list[dict[str, Any]], decision_date: date) -> dict[str, Any]:
    if len(rows) < 65:
        raise ValueError(f"cross-asset series requires at least 65 rows: symbol={rows[0].get('symbol') if rows else ''}, rows={len(rows)}")
    closes = [float(row["close"]) for row in rows]
    latest_date = date.fromisoformat(str(rows[-1]["date"]))
    age_days = (decision_date - latest_date).days
    asset_class = str(rows[-1]["asset_class"])
    subclass = str(rows[-1]["subclass"])
    max_age = MAX_AGE_CALENDAR_DAYS.get(asset_class)
    if max_age is None:
        raise ValueError(f"unsupported cross-asset class for freshness policy: asset_class={asset_class}")
    raw_returns = [later / earlier - 1.0 for earlier, later in zip(closes, closes[1:]) if earlier > 0.0]
    discontinuity_limit = DISCONTINUITY_LIMITS[subclass]
    historical_discontinuities = [
        {"date": str(rows[index + 1]["date"]), "return": round(value, 6)}
        for index, value in enumerate(raw_returns)
        if abs(value) > discontinuity_limit
    ]
    latest_discontinuity = bool(raw_returns and abs(raw_returns[-1]) > discontinuity_limit)
    quality_flags: list[str] = []
    if age_days < 0:
        quality_flags.append("future_market_row_after_decision_date")
    if age_days > max_age:
        quality_flags.append("stale_for_asset_calendar")
    if latest_discontinuity and str(rows[-1].get("series_type", "")) == "continuous_futures_proxy":
        quality_flags.append("latest_move_could_be_roll_or_extreme_market_discontinuity")
    returns = [_return(closes, horizon) for horizon in (1, 5, 20, 60)]
    daily_returns = [later / earlier - 1.0 for earlier, later in zip(closes[-61:-1], closes[-60:]) if earlier > 0.0]
    reference = daily_returns[:-1]
    median_return = sorted(reference)[len(reference) // 2]
    absolute_deviations = sorted(abs(value - median_return) for value in reference)
    mad = absolute_deviations[len(absolute_deviations) // 2]
    robust_deviation = 1.4826 * mad
    shock_z = (daily_returns[-1] - median_return) / robust_deviation if robust_deviation > 0.0 else 0.0
    annualized_volatility = robust_deviation * math.sqrt(252.0)
    ma20 = sum(closes[-20:]) / 20.0
    ma50 = sum(closes[-50:]) / 50.0
    current = closes[-1]
    trend_component = 1.0 if current > ma20 > ma50 else -1.0 if current < ma20 < ma50 else 0.0
    momentum_component = _clamp_signed(0.55 * returns[1] / 0.08 + 0.45 * returns[2] / 0.20)
    directional_score = _clamp_signed(0.55 * trend_component + 0.45 * momentum_component)
    return {
        "symbol": rows[-1]["symbol"],
        "name": rows[-1]["name"],
        "asset_class": asset_class,
        "subclass": subclass,
        "latest_date": rows[-1]["date"],
        "age_calendar_days": age_days,
        "maximum_age_calendar_days": max_age,
        "series_status": "usable" if not quality_flags else "blocked",
        "quality_flags": quality_flags,
        "series_type": rows[-1].get("series_type", "unknown"),
        "contract_metadata_status": rows[-1].get("contract_metadata_status", "unknown"),
        "historical_discontinuity_count": len(historical_discontinuities),
        "latest_discontinuity_flag": latest_discontinuity,
        "recent_discontinuities": historical_discontinuities[-10:],
        "shock_eligible": not latest_discontinuity,
        "latest_close": round(current, 8),
        "return_1": round(returns[0], 6),
        "return_5": round(returns[1], 6),
        "return_20": round(returns[2], 6),
        "return_60": round(returns[3], 6),
        "ma20": round(ma20, 8),
        "ma50": round(ma50, 8),
        "directional_score": round(directional_score, 6),
        "annualized_volatility_60d": round(annualized_volatility, 6),
        "return_shock_z": round(shock_z, 6),
        "source": rows[-1]["source"],
    }


def build_treasury_curve_context(
    macro_summary: dict[str, Any],
    treasury_rows: list[dict[str, str]],
) -> dict[str, Any]:
    risk_free = macro_summary.get("risk_free_rate_30d_pct")
    by_date: dict[str, dict[float, float]] = {}
    for row in treasury_rows:
        try:
            by_date.setdefault(str(row["date"]), {})[float(row["maturity_years"])] = float(row["yield_pct"])
        except (KeyError, ValueError):
            continue
    if not by_date:
        raise ValueError("Treasury curve context requires validated maturity and yield rows")
    dates = sorted(by_date)
    latest_date = dates[-1]
    prior_date = dates[-2] if len(dates) >= 2 else latest_date
    latest = by_date[latest_date]
    prior = by_date[prior_date]
    required = (0.25, 2.0, 5.0, 10.0, 30.0)
    missing = [maturity for maturity in required if maturity not in latest]
    if missing:
        raise ValueError(f"latest Treasury curve is missing required maturities: date={latest_date}, maturities={missing}")
    yield_changes = {
        _maturity_label(maturity): round((latest[maturity] - prior[maturity]) * 100.0, 4)
        for maturity in required
        if maturity in prior
    }
    spread_2s10s = latest[10.0] - latest[2.0]
    spread_3m10y = latest[10.0] - latest[0.25]
    spread_5s30s = latest[30.0] - latest[5.0]
    return {
        "risk_free_rate_30d_pct": risk_free,
        "risk_free_source": macro_summary.get("risk_free_source", "unavailable"),
        "latest_curve_date": latest_date,
        "prior_curve_date": prior_date,
        "latest_yields_pct": {
            _maturity_label(maturity): round(latest[maturity], 6)
            for maturity in required
        },
        "daily_yield_changes_bp": yield_changes,
        "spread_2s10s_pct": round(spread_2s10s, 6),
        "spread_3m10y_pct": round(spread_3m10y, 6),
        "spread_5s30s_pct": round(spread_5s30s, 6),
        "curve_state": "inverted" if spread_2s10s < 0.0 or spread_3m10y < 0.0 else "positive_slope",
        "treasury_futures_role": "ZN_and_ZB_price_momentum_inverse_proxy_for_yield_pressure",
        "curve_detail_status": "current_curve_validated_in_macro_lane",
    }


def theme_context_score(regime: dict[str, Any], theme: str) -> float:
    scores = regime.get("theme_context_scores", {})
    return float(scores.get(theme, regime.get("risk_appetite_score", 0.0)))


def _normalize_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "date": str(row["date"]),
        "symbol": str(row["symbol"]),
        "provider_symbol": str(row["provider_symbol"]),
        "name": str(row["name"]),
        "asset_class": str(row["asset_class"]),
        "subclass": str(row["subclass"]),
        "close": float(row["close"]),
        "volume": int(row["volume"]),
        "source": str(row["source"]),
        "series_type": str(row["series_type"]),
        "contract_metadata_status": str(row["contract_metadata_status"]),
    }


def _return(values: list[float], horizon: int) -> float:
    return values[-1] / values[-horizon - 1] - 1.0 if values[-horizon - 1] > 0.0 else 0.0


def _weighted_state(states: dict[str, dict[str, Any]], weights: dict[str, float]) -> float:
    available = [
        (symbol, weight)
        for symbol, weight in weights.items()
        if symbol in states and states[symbol]["series_status"] == "usable"
    ]
    denominator = sum(abs(weight) for _, weight in available)
    if denominator <= 0.0:
        return 0.0
    return _clamp_signed(
        sum(float(states[symbol]["directional_score"]) * weight for symbol, weight in available) / denominator
    )


def _maturity_label(maturity: float) -> str:
    labels = {0.25: "3m", 2.0: "2y", 5.0: "5y", 10.0: "10y", 30.0: "30y"}
    return labels[maturity]


def _signed_to_unit(value: float) -> float:
    return _clamp01(0.5 + 0.5 * value)


def _clamp_signed(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
