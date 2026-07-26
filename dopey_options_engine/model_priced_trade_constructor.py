"""Convert aggressive signals into model-priced long-premium option candidates."""
from __future__ import annotations

from dopey_wealth_engine.common import stable_hash

from .model_priced_greeks_proxy import price_long_option_proxy
from .option_selection_proxy import select_option_proxy


def construct_model_priced_trades(signals: list[dict], features_by_symbol: dict[str, dict], rankings_by_signal: dict[str, dict]) -> tuple[list[dict], list[dict], list[dict]]:
    candidates: list[dict] = []
    selection_records: list[dict] = []
    greeks_records: list[dict] = []
    for signal in signals:
        symbol = str(signal["symbol"])
        feature = features_by_symbol.get(symbol, {})
        if not feature:
            continue
        selection = select_option_proxy(signal, feature)
        selection_record = {
            "artifact_type": "option_selection_proxy_record",
            "signal_id": signal["signal_id"],
            "underlying_symbol": symbol,
            "market_data_source_type": signal.get("market_data_source_type", feature.get("market_data_source_type", "fixture_fallback")),
            **selection,
            "paper_only": True,
            "live_blocked": True,
        }
        selection_record["record_hash"] = stable_hash(selection_record)
        selection_records.append(selection_record)
        if signal["trade_intent"] not in {"long_call", "long_put"}:
            candidate = _no_trade_candidate(signal, feature)
            candidates.append(candidate)
            continue
        volatility = max(float(feature.get("realized_vol_21", 0.2)), 0.08)
        greeks = price_long_option_proxy(float(feature["close"]), float(selection["strike_proxy"]), 38, volatility, str(selection["option_side"]))
        greeks_record = {
            "artifact_type": "model_priced_greeks_proxy_record",
            "signal_id": signal["signal_id"],
            "underlying_symbol": symbol,
            **greeks,
            "market_data_source_type": signal.get("market_data_source_type", feature.get("market_data_source_type", "fixture_fallback")),
            "realized_volatility_proxy": round(volatility, 6),
            "paper_only": True,
            "live_blocked": True,
        }
        greeks_record["record_hash"] = stable_hash(greeks_record)
        greeks_records.append(greeks_record)
        quality = rankings_by_signal.get(str(signal["signal_id"]), {})
        model_price = float(greeks["model_price"])
        candidate = {
            "artifact_type": "model_priced_trade_candidate",
            "underlying_symbol": symbol,
            "signal_id": signal["signal_id"],
            "trade_intent": signal["trade_intent"],
            "option_side": selection["option_side"],
            "estimated_underlying_price": float(feature["close"]),
            "strike_proxy": selection["strike_proxy"],
            "expiration_bucket": selection["expiration_bucket"],
            "dte_bucket": selection["dte_bucket"],
            "moneyness_bucket": selection["moneyness_bucket"],
            "delta_bucket_proxy": selection["delta_bucket_proxy"],
            "model_price": model_price,
            "max_loss": model_price,
            "slippage_stress": round(max(model_price * 0.12, 0.03), 4),
            "theta_decay_stress": greeks["theta_decay_stress"],
            "iv_shock_stress": greeks["iv_shock_stress"],
            "liquidity_proxy": signal["liquidity_proxy_score"],
            "position_quality_score": round(float(quality.get("quality_score", 0.0)), 6),
            "paper_trade_allowed": bool(quality.get("paper_trade_candidate", False)),
            "no_trade_reason": "",
            "quote_priced": False,
            "model_priced": True,
            "paper_only": True,
            "live_blocked": True,
            "market_data_source_type": signal.get("market_data_source_type", feature.get("market_data_source_type", "fixture_fallback")),
            "strategy_family": signal["setup_family"],
            "volatility_regime": signal["volatility_regime"],
            "trend_regime": signal["trend_regime"],
            "target_move": signal["target_move"],
            "risk_score": signal["risk_score"],
        }
        candidate["record_hash"] = stable_hash(candidate)
        candidates.append(candidate)
    return candidates, selection_records, greeks_records


def _no_trade_candidate(signal: dict, feature: dict) -> dict:
    candidate = {
        "artifact_type": "model_priced_trade_candidate",
        "underlying_symbol": signal["symbol"],
        "signal_id": signal["signal_id"],
        "trade_intent": "no_trade",
        "option_side": "none",
        "estimated_underlying_price": float(feature["close"]),
        "strike_proxy": 0.0,
        "expiration_bucket": "none",
        "dte_bucket": "none",
        "moneyness_bucket": "none",
        "delta_bucket_proxy": "none",
        "model_price": 0.0,
        "max_loss": 0.0,
        "slippage_stress": 0.0,
        "theta_decay_stress": 0.0,
        "iv_shock_stress": 0.0,
        "liquidity_proxy": signal["liquidity_proxy_score"],
        "position_quality_score": 0.0,
        "paper_trade_allowed": False,
        "no_trade_reason": signal.get("no_trade_reason", "signal_quality_gate"),
        "quote_priced": False,
        "model_priced": True,
        "paper_only": True,
        "live_blocked": True,
        "market_data_source_type": signal.get("market_data_source_type", feature.get("market_data_source_type", "fixture_fallback")),
        "strategy_family": signal["setup_family"],
        "volatility_regime": signal["volatility_regime"],
        "trend_regime": signal["trend_regime"],
        "target_move": 0.0,
        "risk_score": signal["risk_score"],
    }
    candidate["record_hash"] = stable_hash(candidate)
    return candidate
