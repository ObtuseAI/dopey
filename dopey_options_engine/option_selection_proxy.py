"""Select paper-only option proxies from directional signals."""
from __future__ import annotations


def select_option_proxy(signal: dict, latest_feature: dict) -> dict:
    intent = str(signal["trade_intent"])
    spot = float(latest_feature["close"])
    if intent == "long_call":
        strike = round(spot * 1.01, 2)
        side = "call"
        delta_bucket = "45_delta_call_proxy"
    elif intent == "long_put":
        strike = round(spot * 0.99, 2)
        side = "put"
        delta_bucket = "45_delta_put_proxy"
    else:
        return {
            "option_side": "none",
            "strike_proxy": 0.0,
            "expiration_bucket": "none",
            "dte_bucket": "none",
            "moneyness_bucket": "none",
            "delta_bucket_proxy": "none",
        }
    return {
        "option_side": side,
        "strike_proxy": strike,
        "expiration_bucket": "monthly_30_to_45_dte",
        "dte_bucket": "30_to_45",
        "moneyness_bucket": "slightly_otm",
        "delta_bucket_proxy": delta_bucket,
    }

