"""Integration coverage for the readiness-neutral forward-accrual queue."""

from __future__ import annotations

from dopey.settlement.accrual import build_forward_accrual_monitor
from dopey.settlement.grading import SettlementPolicy, grade_forward_prediction
from dopey.settlement.predictions import build_forward_prediction
from dopey_equity_swing.market_structure import Bar


def _bar(symbol: str, day: str, close: float) -> Bar:
    return {
        "date": day,
        "symbol": symbol,
        "open": close,
        "high": close * 1.002,
        "low": close * 0.998,
        "close": close,
        "adjusted_close": close,
        "volume": 1_000_000,
        "source": "integration_test_only_not_readiness_evidence",
    }


def _prediction(symbol: str, market_time: str, event_time: str, horizon: int) -> dict[str, object]:
    return build_forward_prediction(
        symbol,
        event_time,
        market_time,
        {"bull": 0.6, "bear": 0.1, "neutral": 0.2, "unknown": 0.1},
        0.4,
        "ABSTAIN",
        (f"evidence:{symbol}",),
        f"point-in-time:{symbol}",
        True,
        horizon,
        {"technical_agent": 0.1},
        {"technical_agent": {"bull": 0.5, "bear": 0.1, "neutral": 0.25, "unknown": 0.15}},
    )


def test_forward_accrual_monitor_classifies_the_full_operator_queue() -> None:
    policy = SettlementPolicy(0.01, 0.0025, 5, 1e-12)
    recorded = _prediction(
        "SPY",
        "2026-07-06T20:00:00+00:00",
        "2026-07-06T21:00:00+00:00",
        2,
    )
    gradeable = _prediction(
        "QQQ",
        "2026-07-06T20:00:00+00:00",
        "2026-07-06T21:00:00+00:00",
        2,
    )
    missing_price = _prediction(
        "IWM",
        "2026-07-06T20:00:00+00:00",
        "2026-07-06T21:00:00+00:00",
        2,
    )
    pending = _prediction(
        "DIA",
        "2026-07-08T20:00:00+00:00",
        "2026-07-08T21:00:00+00:00",
        2,
    )
    quarantined = {
        "prediction_id": "legacy-without-proof",
        "symbol": "SPY",
        "minimum_settlement_date": "2026-07-08",
        "prediction_market_time": "2026-07-06T20:00:00+00:00",
        "paper_only": True,
        "live_blocked": True,
    }
    histories = {
        "QQQ": [_bar("QQQ", "2026-07-06", 100.0), _bar("QQQ", "2026-07-08", 102.0)],
        "IWM": [_bar("IWM", "2026-07-06", 100.0)],
        "DIA": [_bar("DIA", "2026-07-08", 100.0)],
    }
    recorded_rows = [_bar("SPY", "2026-07-06", 100.0), _bar("SPY", "2026-07-08", 103.0)]
    recorded_settlement = grade_forward_prediction(recorded, recorded_rows, "2026-07-08", policy)

    first = build_forward_accrual_monitor(
        (recorded, gradeable, missing_price, pending, quarantined),
        histories,
        (recorded_settlement,),
        "2026-07-08",
        policy,
    )
    second = build_forward_accrual_monitor(
        (quarantined, pending, missing_price, gradeable, recorded),
        histories,
        (recorded_settlement,),
        "2026-07-08",
        policy,
    )

    assert first["monitor_status"] == "operator_attention_required"
    assert first["settled_recorded_count"] == 1
    assert first["gradeable_unrecorded_count"] == 1
    assert first["due_missing_verified_price_count"] == 1
    assert first["pending_minimum_horizon_count"] == 1
    assert first["quarantined_missing_point_in_time_proof_count"] == 1
    assert first["next_minimum_settlement_date"] == "2026-07-10"
    assert first["early_grading_performed"] is False
    assert first["readiness_effect"] == "none_protected_external_gate"
    assert first["action_ready"] is False
    assert first["reproducibility_hash"] == second["reproducibility_hash"]
