"""Integration coverage for the expanded technical foundry and pattern layer."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from dopey.chronos.clocks import ClockDomain, ClockStamp
from dopey.technical.evidence import build_multi_timeframe_technical_evidence
from dopey.technical.foundry import ALL_TECHNICAL_SPECS
from dopey.technical.history_adapter import load_validated_symbol_history
from dopey_equity_swing.market_structure import Bar
from tests.public_source_fixtures import write_synthetic_history_manifest


def _history(symbol: str) -> list[Bar]:
    rows: list[Bar] = []
    start = date(2018, 1, 1)
    for index in range(2200):
        close = 100.0 + 0.03 * index + 2.0 * ((index % 20) / 20.0)
        rows.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "symbol": symbol,
                "open": close - 0.2,
                "high": close + 0.8,
                "low": close - 0.8,
                "close": close,
                "adjusted_close": close,
                "volume": 1_000_000 + index * 100,
                "source": "integration_test_only_not_readiness_evidence",
            }
        )
    return rows


def test_expanded_foundry_is_versioned_deterministic_and_non_actionable() -> None:
    clock = ClockStamp(
        domain=ClockDomain.DAILY,
        event_time="2026-07-14T20:10:00+00:00",
        market_time="2026-07-14T20:00:00+00:00",
        data_version="integration-history-v1",
        agent_version="integration-agent-v1",
        policy_version="dopey-constitution-v1",
        model_version="deterministic-v1",
        parent_event_id="",
        session_id="integration-session",
    )
    first = build_multi_timeframe_technical_evidence("SPY", _history("SPY"), clock)
    second = build_multi_timeframe_technical_evidence("SPY", _history("SPY"), clock)

    assert len(ALL_TECHNICAL_SPECS) == 62
    assert first["measurement_count"] == 186
    assert first["reproducibility_hash"] == second["reproducibility_hash"]
    assert first["structure_pattern_evidence_count"] == 3
    assert all(record["not_trade_decision"] is True for record in first["measurements"])
    assert all(record["patterns_are_probabilistic_not_truth"] is True for record in first["structure_pattern_evidence"])
    assert first["intraday_status"] == "unavailable_no_validated_local_intraday_history_not_synthesized"


def test_zero_range_history_is_explicitly_unavailable_not_a_runtime_error(
    tmp_path: Path,
) -> None:
    manifest_path = write_synthetic_history_manifest(
        tmp_path / "history",
        "CLSK",
        _history("CLSK"),
    )
    history, proof = load_validated_symbol_history("CLSK", manifest_path)
    clock = ClockStamp(
        domain=ClockDomain.DAILY,
        event_time="2026-07-15T01:05:03.133692+00:00",
        market_time="2026-07-14T20:00:00+00:00",
        data_version=str(proof["actual_sha256"]),
        agent_version="integration-agent-v1",
        policy_version="dopey-constitution-v1",
        model_version="deterministic-v1",
        parent_event_id="",
        session_id="integration-clsk-zero-range",
    )

    result = build_multi_timeframe_technical_evidence("CLSK", history, clock)
    ease_of_movement = [
        record
        for record in result["measurements"]
        if record["indicator"] == "EASE_OF_MOVEMENT"
    ]

    assert result["measurement_count"] == 186
    assert len(ease_of_movement) == 3
    assert all(record["not_trade_decision"] is True for record in ease_of_movement)
