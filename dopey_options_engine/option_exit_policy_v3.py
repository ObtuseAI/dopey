"""Exit policy rules for model-priced public path simulation V3."""
from __future__ import annotations

from dopey_autonomy.public_champion_common import safe_float


def policy_thresholds(policy_name: str, hold_window: int, dte_bucket: int) -> dict[str, float | int]:
    if policy_name == "fast_scalp":
        return {"target_return": 0.38, "stop_return": -0.34, "max_hold_days": min(hold_window, 5), "theta_days": 2}
    if policy_name == "trend_follow":
        return {"target_return": 0.95, "stop_return": -0.52, "max_hold_days": hold_window, "theta_days": max(3, dte_bucket // 5)}
    if policy_name == "invalidation_strict":
        return {"target_return": 0.55, "stop_return": -0.42, "max_hold_days": hold_window, "theta_days": max(2, dte_bucket // 6)}
    if policy_name == "theta_protective":
        return {"target_return": 0.48, "stop_return": -0.38, "max_hold_days": min(hold_window, max(3, dte_bucket // 2)), "theta_days": max(3, dte_bucket // 4)}
    if policy_name == "volatility_expansion_hunter":
        return {"target_return": 0.78, "stop_return": -0.50, "max_hold_days": hold_window, "theta_days": max(2, dte_bucket // 6)}
    raise ValueError(f"unsupported exit policy: {policy_name}")


def choose_exit_event(
    signal: dict[str, object],
    entry_premium: float,
    path_marks: list[dict[str, object]],
) -> dict[str, object]:
    policy_name = str(signal["exit_policy"])
    hold_window = int(signal["hold_window"])
    dte_bucket = int(signal["dte_bucket"])
    thresholds = policy_thresholds(policy_name, hold_window, dte_bucket)
    target_return = safe_float(thresholds["target_return"])
    stop_return = safe_float(thresholds["stop_return"])
    max_hold_days = int(thresholds["max_hold_days"])
    theta_days = int(thresholds["theta_days"])
    invalidation = safe_float(signal["invalidation_level"])
    target_price = safe_float(signal["target_price"])
    intent = str(signal["trade_intent"])
    for mark in path_marks:
        day_index = int(mark["day_index"])
        if day_index <= 0:
            continue
        spot = safe_float(mark["spot"])
        option_value = safe_float(mark["option_value"])
        option_return = (option_value / entry_premium) - 1.0 if entry_premium > 0.0 else 0.0
        dte_remaining = int(mark["dte_remaining"])
        if intent == "long_call" and spot >= target_price:
            return exit_record(mark, "target_hit", option_return)
        if intent == "long_put" and spot <= target_price:
            return exit_record(mark, "target_hit", option_return)
        if intent == "long_call" and spot <= invalidation:
            return exit_record(mark, "invalidation_hit", option_return)
        if intent == "long_put" and spot >= invalidation:
            return exit_record(mark, "invalidation_hit", option_return)
        if option_return >= target_return:
            return exit_record(mark, "option_target_hit", option_return)
        if option_return <= stop_return:
            return exit_record(mark, "drawdown_stop", option_return)
        if dte_remaining <= theta_days and option_return < -0.08:
            return exit_record(mark, "theta_bleed_stop", option_return)
        if policy_name == "volatility_expansion_hunter" and safe_float(mark["iv_proxy"]) < safe_float(mark["entry_iv_proxy"]) * 0.78 and option_return < 0.0:
            return exit_record(mark, "volatility_shock_stop", option_return)
        if day_index >= max_hold_days:
            return exit_record(mark, "max_hold_days", option_return)
    if path_marks:
        final_mark = path_marks[-1]
        option_return = (safe_float(final_mark["option_value"]) / entry_premium) - 1.0 if entry_premium > 0.0 else 0.0
        return exit_record(final_mark, "time_stop", option_return)
    return {
        "exit_date": str(signal["timestamp"]),
        "exit_reason": "no_future_path",
        "exit_option_value": 0.0,
        "exit_spot": safe_float(signal["entry_price"]),
        "hold_days": 0,
        "option_return": -1.0,
    }


def exit_record(mark: dict[str, object], reason: str, option_return: float) -> dict[str, object]:
    return {
        "exit_date": str(mark["date"]),
        "exit_reason": reason,
        "exit_option_value": round(safe_float(mark["option_value"]), 6),
        "exit_spot": round(safe_float(mark["spot"]), 6),
        "hold_days": int(mark["day_index"]),
        "option_return": round(option_return, 6),
    }

