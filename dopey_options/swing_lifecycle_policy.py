"""Offline swing lifecycle policy for long-premium options."""
from __future__ import annotations

from .swing_option_models import SwingOptionCandidate


def evaluate_swing_lifecycle(
    candidate: SwingOptionCandidate,
    close_day_index: int,
    structure: str,
    live_allowed: bool,
) -> dict:
    if live_allowed:
        return _blocked("live_path_rejected")
    if structure not in {"long_call", "long_put"}:
        return _blocked("unsupported_structure_rejected")
    if candidate.option_type not in {"call", "put"}:
        return _blocked("unsupported_option_type_rejected")
    if close_day_index == 0:
        return {
            "decision": "blocked_same_day_normal_close",
            "allowed": False,
            "reason_codes": ["same_day_round_trip_rejected"],
            "no_day_trade_result": "same_day_close_blocked",
            "paper_only": True,
            "live_blocked": True,
        }
    return {
        "decision": "close_allowed_next_trading_day_or_later",
        "allowed": True,
        "reason_codes": [],
        "no_day_trade_result": "next_day_close_allowed",
        "paper_only": True,
        "live_blocked": True,
    }


def _blocked(reason: str) -> dict:
    return {
        "decision": "blocked",
        "allowed": False,
        "reason_codes": [reason],
        "no_day_trade_result": reason,
        "paper_only": True,
        "live_blocked": True,
    }
