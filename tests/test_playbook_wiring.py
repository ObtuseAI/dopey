"""Tests for the playbook wiring: settlement loop, lane context, supervisor stage."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from dopey.strategy_engineering.lane_context import load_lane_context
from dopey.strategy_engineering.playbook_scanner import (
    BIG_MOVER_SELECTION_POLICY_VERSION,
    PLAYBOOK_SCAN_VERSION,
)
from dopey.strategy_engineering.playbook_settlement import (
    RATED_FLOOR,
    family_trust_report,
    is_rating_eligible_settlement,
    record_detections,
    settle_matured,
    uses_legacy_direction_assumption,
    uses_legacy_dual_framing,
)
from dopey.strategy_engineering.run_playbook_research_stage import run_playbook_research_stage

_HEADER = "date,symbol,open,high,low,close,adjusted_close,volume,source"


def _write_history(root: Path, symbol: str, closes: list[float]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = [_HEADER]
    for i, close in enumerate(closes):
        day = f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}"
        lines.append(f"{day},{symbol},{close},{close * 1.01},{close * 0.99},{close},{close},1000000,test")
    (root / f"{symbol}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _detection(symbol: str, as_of: str, direction: str, setup: str = "ts_momentum_12m") -> dict:
    return {
        "detection_id": f"det-{symbol}-{as_of}-{direction}-{setup}",
        "setup_id": setup,
        "family": "momentum_trend",
        "symbol": symbol,
        "as_of_date": as_of,
        "direction": direction,
        "strength": 0.5,
        "horizon_days": (5,),
        "is_trade_signal": False,
        "paper_only": True,
        "live_blocked": True,
    }


# ------------------------------------------------------------------ #
# Settlement loop
# ------------------------------------------------------------------ #

def test_record_is_idempotent(tmp_path: Path):
    ledger = tmp_path / "detections.jsonl"
    report = {"detections": ({"detection_id": "a"}, {"detection_id": "b"})}
    first = record_detections(report, ledger_path=ledger)
    second = record_detections(report, ledger_path=ledger)
    assert first["appended"] == 2
    assert second["appended"] == 0 and second["already_recorded"] == 2


def test_recording_fails_closed_on_malformed_existing_ledger(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "detections.jsonl"
    ledger.write_text(
        '{"detection_id":"valid"}\n{"detection_id":\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="line_number=2"):
        record_detections(
            {"detections": ({"detection_id": "new"},)},
            ledger_path=ledger,
        )


def test_settlement_grades_hits_misses_and_contested(tmp_path: Path):
    # Rising series: long detections hit, short detections miss.
    closes = [100.0 + i for i in range(40)]
    bars = [{"date": f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
             "open": c, "high": c, "low": c, "close": c, "volume": 1e6}
            for i, c in enumerate(closes)]
    dledger, sledger = tmp_path / "d.jsonl", tmp_path / "s.jsonl"
    # Backdated detections with 5-day horizon, room to mature.
    record_detections({"detections": (
        _detection("UP", bars[10]["date"], "long"),
        _detection("UP", bars[12]["date"], "short"),
        _detection("UP", bars[-1]["date"], "long"),   # frontier: cannot mature
        _detection("UP", bars[14]["date"], "guard"),  # not direction-gradable
    )}, ledger_path=dledger)
    result = settle_matured({"UP": bars}, ledger_path=dledger, settlement_path=sledger)
    assert result["newly_settled"] == 3          # long, short, guard (recorded)
    assert result["still_pending"] == 1          # the frontier detection
    settled = [json.loads(line) for line in sledger.read_text().splitlines()]
    by_dir = {s["direction"]: s for s in settled}
    assert by_dir["long"]["graded"] and by_dir["long"]["hit"] is True
    assert by_dir["short"]["graded"] and by_dir["short"]["hit"] is False
    assert by_dir["guard"]["graded"] is False and by_dir["guard"]["hit"] is None
    # Long WITH the rising drift is not contested (agreeing with the tape).
    assert by_dir["long"]["contested_truth"] is False
    # Short AGAINST the rising drift is contested — and it missed.
    assert by_dir["short"]["contested_truth"] is True


def test_settlement_first_recorded_immutable(tmp_path: Path):
    closes = [100.0 + i for i in range(30)]
    bars = [{"date": f"2026-01-{i + 1:02d}" if i < 28 else f"2026-02-{i - 27:02d}",
             "open": c, "high": c, "low": c, "close": c, "volume": 1e6}
            for i, c in enumerate(closes)]
    dledger, sledger = tmp_path / "d.jsonl", tmp_path / "s.jsonl"
    record_detections({"detections": (_detection("UP", bars[5]["date"], "long"),)}, ledger_path=dledger)
    settle_matured({"UP": bars}, ledger_path=dledger, settlement_path=sledger)
    again = settle_matured({"UP": bars}, ledger_path=dledger, settlement_path=sledger)
    assert again["newly_settled"] == 0  # never re-settled


def test_trust_report_floors_honestly(tmp_path: Path):
    sledger = tmp_path / "s.jsonl"
    records = [
        {"detection_id": f"d{i}", "setup_id": "x", "family": "momentum_trend",
         "symbol": f"S{i}", "as_of_date": "2026-01-01",
         "settle_date": "2026-01-06", "graded": True,
         "hit": i % 2 == 0, "contested_truth": i < RATED_FLOOR - 1}
        for i in range(RATED_FLOOR + 10)
    ]
    sledger.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    report = family_trust_report(settlement_path=sledger, report_path=tmp_path / "trust.json")
    bucket = report["per_setup"]["x"]
    assert bucket["settled"] > RATED_FLOOR
    assert bucket["contested_settled"] == RATED_FLOOR - 1
    assert (
        bucket["trust_state"]
        == "unrated_insufficient_effective_contested_settlements"
    )
    assert bucket["effective_contested_settled"] == RATED_FLOOR - 1
    assert (
        bucket["rating_count_basis"]
        == "effective_contested_symbol_overlapping_settlement_window_clusters"
    )

    records.append(
        {
            "detection_id": "rated-at-contested-floor",
            "setup_id": "x",
            "family": "momentum_trend",
            "symbol": "RATED-FLOOR",
            "as_of_date": "2026-01-01",
            "settle_date": "2026-01-06",
            "graded": True,
            "hit": True,
            "contested_truth": True,
        }
    )
    sledger.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    rated_report = family_trust_report(
        settlement_path=sledger,
        report_path=tmp_path / "rated-trust.json",
    )
    assert rated_report["per_setup"]["x"]["trust_state"] == "rated"
    assert report["advisory_only_never_a_gate_input"] is True
    assert report["profit_or_edge_claimed"] is False


def test_overlapping_symbol_windows_count_as_one_effective_observation(
    tmp_path: Path,
) -> None:
    settlement_path = tmp_path / "overlapping.jsonl"
    first_day = date(2026, 1, 1)
    records = [
        {
            "detection_id": f"overlap-{index}",
            "setup_id": "ts_momentum_12m",
            "family": "momentum_trend",
            "symbol": "SAME",
            "as_of_date": str(first_day + timedelta(days=index)),
            "settle_date": str(first_day + timedelta(days=index + 5)),
            "graded": True,
            "hit": index % 2 == 0,
            "contested_truth": True,
        }
        for index in range(RATED_FLOOR + 10)
    ]
    settlement_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    report = family_trust_report(
        settlement_path=settlement_path,
        report_path=tmp_path / "overlapping-trust.json",
    )
    bucket = report["per_setup"]["ts_momentum_12m"]

    assert bucket["raw_contested_settled"] == RATED_FLOOR + 10
    assert bucket["effective_contested_settled"] == 1
    assert bucket["effective_contested_clusters_by_symbol"] == {"SAME": 1}
    assert bucket["rating_observation_count"] == 1
    assert (
        bucket["trust_state"]
        == "unrated_insufficient_effective_contested_settlements"
    )


def test_legacy_hard_coded_direction_settlements_are_not_rateable(
    tmp_path: Path,
) -> None:
    settlement_path = tmp_path / "legacy-direction.jsonl"
    records = [
        {
            "detection_id": f"legacy-{index}",
            "setup_id": "gamma_squeeze_flow",
            "family": "flow_positioning",
            "graded": True,
            "hit": True,
            "contested_truth": True,
        }
        for index in range(RATED_FLOOR + 10)
    ]
    settlement_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    report = family_trust_report(
        settlement_path=settlement_path,
        report_path=tmp_path / "legacy-trust.json",
    )
    bucket = report["per_family"]["flow_positioning"]

    assert bucket["trust_state"] == "unrated_legacy_direction_assumption"
    assert bucket["settled"] == 0
    assert bucket["contested_settled"] == 0
    assert bucket["raw_graded_settled"] == RATED_FLOOR + 10
    assert (
        bucket["legacy_direction_assumption_settled"]
        == RATED_FLOOR + 10
    )
    assert uses_legacy_direction_assumption(records[0]) is True
    assert is_rating_eligible_settlement(records[0]) is False
    assert is_rating_eligible_settlement(
        {
            "setup_id": "ts_momentum_12m",
            "graded": True,
        }
    ) is True


def test_legacy_big_mover_dual_framing_is_quarantined(
    tmp_path: Path,
) -> None:
    legacy = {
        "setup_id": "big_mover_momentum",
        "graded": True,
    }
    selected = {
        **legacy,
        "independently_selected_setup": True,
        "framing_selection_policy_version": (
            BIG_MOVER_SELECTION_POLICY_VERSION
        ),
        "source_playbook_scan_version": PLAYBOOK_SCAN_VERSION,
    }

    assert uses_legacy_dual_framing(legacy) is True
    assert is_rating_eligible_settlement(legacy) is False
    assert uses_legacy_dual_framing(selected) is False
    assert is_rating_eligible_settlement(selected) is True

    settlement_path = tmp_path / "legacy-dual.jsonl"
    settlement_path.write_text(
        "\n".join(
            json.dumps(
                {
                    **legacy,
                    "detection_id": f"legacy-dual-{index}",
                    "family": "momentum_trend",
                    "symbol": f"S{index}",
                    "as_of_date": "2026-01-01",
                    "settle_date": "2026-01-06",
                    "hit": True,
                    "contested_truth": True,
                }
            )
            for index in range(RATED_FLOOR + 1)
        )
        + "\n",
        encoding="utf-8",
    )
    report = family_trust_report(
        settlement_path=settlement_path,
        report_path=tmp_path / "legacy-dual-trust.json",
    )
    bucket = report["per_setup"]["big_mover_momentum"]

    assert bucket["trust_state"] == "unrated_legacy_dual_framing"
    assert bucket["settled"] == 0
    assert bucket["raw_contested_settled"] == RATED_FLOOR + 1
    assert bucket["eligible_contested_settled"] == 0
    assert bucket["legacy_dual_framing_settled"] == RATED_FLOOR + 1


# ------------------------------------------------------------------ #
# Lane context
# ------------------------------------------------------------------ #

def test_lane_context_all_gaps_when_artifacts_missing(tmp_path: Path):
    ctx = load_lane_context(
        macro_summary_path=tmp_path / "missing.json",
        positioning_path=tmp_path / "missing.jsonl",
    )
    assert ctx["loaded_state_count"] == 0
    assert len(ctx["gaps"]) == 8


def test_lane_context_maps_macro_states(tmp_path: Path):
    macro = {
        "vol_term_structure": {"term_structure_state": "backwardation_stress", "term_slope_9d_3m": -0.2},
        "liquidity_impulse": {"impulse_state": "draining", "impulse_4w_pct": -0.01},
        "es_positioning": {"noncomm_net_z_52w": -2.5},
        "attention": {
            "crowded_attention_candidates": ["MEME"],
            "attention_z_by_symbol": {"MEME": 3.1},
            "crowded_threshold_z": 2.0,
        },
        "short_flow": {
            "short_volume_ratio_by_symbol": {"FLOW": 0.71},
            "is_open_short_interest": False,
        },
        "short_crowding": {
            "by_symbol": {
                "HEAVY": {
                    "short_percent_float": 0.31,
                    "days_to_cover": 7.5,
                },
                "LIGHT": {
                    "short_percent_float": 0.04,
                    "days_to_cover": 1.2,
                },
            },
            "daily_short_volume_substituted": False,
        },
        "congress": {"notable_buying": ["AMD"], "honest_limits": "45d lag"},
        "fundamentals": {"short_candidates_tradable_now": ["ROT"]},
    }
    mpath = tmp_path / "macro.json"
    mpath.write_text(json.dumps(macro), encoding="utf-8")
    ppath = tmp_path / "pos.jsonl"
    ppath.write_text(json.dumps({"symbol": "SPY", "total_gex_dollar_per_pct": -5e7}) + "\n", encoding="utf-8")
    ctx = load_lane_context(macro_summary_path=mpath, positioning_path=ppath)
    states = ctx["states"]
    assert ctx["gaps"] == []
    assert states["vix_term_structure_state"]["detected"] is True     # backwardation
    assert states["liquidity_state"]["direction"] == "short"          # draining
    assert states["cot_state"]["direction"] == "long"                 # fade z=-2.5
    assert states["attention_state"]["detected"] is True
    assert states["attention_state"]["direction"] == "either"
    assert states["attention_state"]["directional_bias_allowed"] is False
    assert states["attention_state"]["research_priority_only"] is True
    assert states["attention_state"]["attention_z_by_symbol"] == {"MEME": 3.1}
    assert states["short_interest_state"]["crowded_short_symbols"] == ["HEAVY"]
    assert states["short_interest_state"]["direction"] == "either"
    assert states["short_interest_state"]["directional_bias_allowed"] is False
    assert states["short_interest_state"]["daily_short_volume_substituted"] is False
    assert states["gex_state"]["negative_gex_symbols"] == ["SPY"]
    assert states["gex_state"]["direction"] == "either"
    assert states["gex_state"]["directional_bias_allowed"] is False


# ------------------------------------------------------------------ #
# Supervisor stage
# ------------------------------------------------------------------ #

def test_stage_blocked_without_history(tmp_path: Path):
    summary = run_playbook_research_stage(
        history_root=tmp_path / "empty",
        chains_root=tmp_path / "chains",
    )
    assert summary["playbook_stage_status"] == "blocked_no_ohlcv_history"
    assert summary["paper_only"] is True and summary["live_blocked"] is True


def test_stage_end_to_end(tmp_path: Path):
    root = tmp_path / "hist"
    _write_history(root, "TREND", [100.0 * (1.02 ** i) for i in range(300)])
    summary = run_playbook_research_stage(
        history_root=root,
        chains_root=tmp_path / "chains",
    )
    assert summary["playbook_stage_status"] == "playbook_research_complete"
    assert summary["detections"] > 0
    assert summary["advisory_only_never_a_gate_input"] is True
    assert summary["profit_or_edge_claimed"] is False


def test_stage_registered_in_supervisor():
    from dopey_autonomy.run_resilient_research_supervisor import STAGES
    names = [name for name, _, _ in STAGES]
    assert "playbook_research" in names
    deps = dict((name, d) for name, _, d in STAGES)["playbook_research"]
    assert deps == ("history_validation",)
    assert "squeeze_bubble_intelligence" in names
    squeeze_dependencies = dict(
        (name, dependencies) for name, _, dependencies in STAGES
    )["squeeze_bubble_intelligence"]
    assert squeeze_dependencies == (
        "history_validation",
        "macro_context_gate",
        "chain_analytics_gate",
    )
