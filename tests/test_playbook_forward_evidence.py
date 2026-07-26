"""Integration proof for append-only composite Playbook forward evidence."""

from __future__ import annotations

import json
from pathlib import Path

from dopey.strategy_engineering.playbook_forward_evidence import (
    update_playbook_forward_evidence,
)


def _write_history(root: Path, symbol: str, closes: list[float]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = ["date,symbol,open,high,low,close,adjusted_close,volume,source"]
    for index, close in enumerate(closes, start=1):
        day = f"2026-01-{index:02d}"
        lines.append(
            f"{day},{symbol},{close},{close},{close},{close},{close},1000000,test"
        )
    (root / f"{symbol}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _recommendation(
    recommendation_id: str,
    symbol: str,
    horizon: str,
    direction: str,
    score: float,
) -> dict[str, object]:
    return {
        "recommendation_id": recommendation_id,
        "symbol": symbol,
        "category": f"{horizon}_{direction}",
        "horizon": horizon,
        "directional_bias": direction,
        "research_priority_score": score,
        "score_breakdown": {
            "within_setup_signal": score,
            "forward_trust": 0.0,
            "valuation_fit": 50.0,
        },
        "recommendation_state": "watchlist_needs_trigger",
        "valuation_context": {
            "valuation_gate": "passed_current_point_in_time_valuation"
        },
    }


def _rankings() -> dict[str, object]:
    recommendations = {
        "short-bull": _recommendation(
            "short-bull", "BULL", "short_term", "bullish", 70.0
        ),
        "long-bear": _recommendation("long-bear", "BEAR", "long_term", "bearish", 65.0),
    }
    return {
        "schema_version": "dopey-playbook-rankings-v2",
        "generated_utc": "2026-01-31T22:00:00+00:00",
        "market_data_as_of": "2026-01-01",
        "input_fingerprint": "a" * 64,
        "content_hash": "b" * 64,
        "source_artifacts": [{"path": "source.json", "sha256": "c" * 64}],
        "ranking_method": {
            "short_term_weights": {"signal": 0.5, "valuation": 0.5},
            "long_term_weights": {"signal": 0.4, "valuation": 0.6},
            "forward_trust_method": "positive_skill_above_50pct",
            "valuation_use": "horizon_aware",
            "weight_calibration_status": "provisional",
            "automatic_weight_tuning_allowed": False,
        },
        "recommendations": recommendations,
    }


def test_composite_forward_evidence_is_append_only_idempotent_and_non_promotional(
    tmp_path: Path,
) -> None:
    history_root = tmp_path / "history"
    _write_history(history_root, "BULL", [100.0 + index for index in range(30)])
    _write_history(history_root, "BEAR", [100.0 - index for index in range(30)])
    snapshot_path = tmp_path / "snapshots.jsonl"
    settlement_path = tmp_path / "settlements.jsonl"
    report_path = tmp_path / "report.json"

    first = update_playbook_forward_evidence(
        _rankings(),
        history_root,
        "d" * 64,
        snapshot_path,
        settlement_path,
        report_path,
    )
    second = update_playbook_forward_evidence(
        _rankings(),
        history_root,
        "d" * 64,
        snapshot_path,
        settlement_path,
        report_path,
    )

    assert first["newly_recorded_snapshot_count"] == 2
    assert first["snapshot_count"] == 2
    assert first["raw_snapshot_ledger_count"] == 2
    assert first["same_market_date_duplicate_snapshot_count"] == 0
    assert first["duplicate_snapshots_counted_as_evidence"] is False
    assert (
        first["same_market_date_model_variants_counted_as_independent_evidence"]
        is False
    )
    assert first["snapshot_evidence_identity_fields"] == [
        "market_data_as_of",
        "symbol",
        "category",
        "evaluation_horizon_trading_days",
    ]
    assert first["newly_settled_count"] == 2
    assert first["settled_count"] == 2
    assert first["raw_settlement_ledger_count"] == 2
    assert first["non_evidentiary_raw_settlement_count"] == 0
    assert first["duplicate_settlements_counted_as_evidence"] is False
    assert first["pending_count"] == 0
    assert first["sample_sufficient"] is False
    assert first["weight_calibration_status"] == (
        "provisional_weights_insufficient_forward_rank_evidence"
    )
    assert first["automatic_weight_tuning_allowed"] is False
    assert first["weight_activation_allowed"] is False
    assert first["brier_score_claimed"] is False
    assert first["expected_calibration_error_claimed"] is False
    assert first["order_construction_allowed"] is False
    assert first["strategy_promotion_allowed"] is False
    assert first["paper_only"] is True
    assert first["live_blocked"] is True

    assert second["newly_recorded_snapshot_count"] == 0
    assert second["snapshot_count"] == 2
    assert second["raw_snapshot_ledger_count"] == 2
    assert second["same_market_date_duplicate_snapshot_count"] == 0
    assert second["newly_settled_count"] == 0
    assert second["settled_count"] == 2
    assert len(snapshot_path.read_text(encoding="utf-8").splitlines()) == 2
    settlement_rows = [
        json.loads(line)
        for line in settlement_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(settlement_rows) == 2
    assert all(row["directionally_correct"] is True for row in settlement_rows)
    assert {row["evaluation_horizon_trading_days"] for row in settlement_rows} == {
        5,
        20,
    }
    assert all(row["price_field"] == "adjusted_close" for row in settlement_rows)
    assert all(row["not_trade_evidence"] is True for row in settlement_rows)
    assert (
        json.loads(report_path.read_text(encoding="utf-8"))["reproducibility_hash"]
        == second["reproducibility_hash"]
    )


def test_same_market_date_refresh_does_not_double_weight_forward_evidence(
    tmp_path: Path,
) -> None:
    history_root = tmp_path / "history"
    _write_history(history_root, "BULL", [100.0, 101.0, 102.0])
    _write_history(history_root, "BEAR", [100.0, 99.0, 98.0])
    snapshot_path = tmp_path / "snapshots.jsonl"
    settlement_path = tmp_path / "settlements.jsonl"
    report_path = tmp_path / "report.json"

    first = update_playbook_forward_evidence(
        _rankings(),
        history_root,
        "d" * 64,
        snapshot_path,
        settlement_path,
        report_path,
    )
    first_rows = snapshot_path.read_text(encoding="utf-8").splitlines()

    revised_rankings = _rankings()
    revised_rankings["generated_utc"] = "2026-01-31T23:00:00+00:00"
    revised_rankings["input_fingerprint"] = "e" * 64
    revised_rankings["content_hash"] = "f" * 64
    revised_rankings["source_artifacts"] = [{"path": "source.json", "sha256": "1" * 64}]
    revised_ranking_method = revised_rankings["ranking_method"]
    assert isinstance(revised_ranking_method, dict)
    revised_ranking_method["weight_calibration_status"] = "intraday_review"
    revised_ranking_method["short_term_weights"] = {
        "signal": 0.4,
        "valuation": 0.6,
    }
    revised_recommendations = revised_rankings["recommendations"]
    assert isinstance(revised_recommendations, dict)
    revised_short = revised_recommendations["short-bull"]
    assert isinstance(revised_short, dict)
    revised_short["research_priority_score"] = 99.0
    revised_breakdown = revised_short["score_breakdown"]
    assert isinstance(revised_breakdown, dict)
    revised_breakdown["within_setup_signal"] = 99.0

    second = update_playbook_forward_evidence(
        revised_rankings,
        history_root,
        "d" * 64,
        snapshot_path,
        settlement_path,
        report_path,
    )

    assert first["newly_recorded_snapshot_count"] == 2
    assert second["newly_recorded_snapshot_count"] == 0
    assert second["snapshot_count"] == 2
    assert second["raw_snapshot_ledger_count"] == 2
    assert second["same_market_date_duplicate_snapshot_count"] == 0
    assert second["duplicate_snapshots_counted_as_evidence"] is False
    assert snapshot_path.read_text(encoding="utf-8").splitlines() == first_rows


def test_legacy_same_date_duplicates_remain_raw_but_not_evidentiary(
    tmp_path: Path,
) -> None:
    history_root = tmp_path / "history"
    _write_history(history_root, "BULL", [100.0 + index for index in range(30)])
    _write_history(history_root, "BEAR", [100.0 - index for index in range(30)])
    snapshot_path = tmp_path / "snapshots.jsonl"
    settlement_path = tmp_path / "settlements.jsonl"
    report_path = tmp_path / "report.json"

    update_playbook_forward_evidence(
        _rankings(),
        history_root,
        "d" * 64,
        snapshot_path,
        settlement_path,
        report_path,
    )
    snapshot_rows = [
        json.loads(line)
        for line in snapshot_path.read_text(encoding="utf-8").splitlines()
    ]
    settlement_rows = [
        json.loads(line)
        for line in settlement_path.read_text(encoding="utf-8").splitlines()
    ]
    duplicate_snapshot_ids: dict[str, str] = {}
    duplicate_snapshots: list[dict[str, object]] = []
    for index, row in enumerate(snapshot_rows, start=1):
        original_snapshot_id = str(row["snapshot_id"])
        duplicate_snapshot_id = f"playbook-forward-snapshot:legacy-{index}"
        duplicate_snapshot_ids[original_snapshot_id] = duplicate_snapshot_id
        duplicate = dict(row)
        duplicate["snapshot_id"] = duplicate_snapshot_id
        duplicate["snapshot_payload_hash"] = str(index) * 64
        duplicate["input_fingerprint"] = str(index + 2) * 64
        duplicate_snapshots.append(duplicate)
    duplicate_settlements: list[dict[str, object]] = []
    for index, row in enumerate(settlement_rows, start=1):
        duplicate = dict(row)
        duplicate["snapshot_id"] = duplicate_snapshot_ids[str(row["snapshot_id"])]
        duplicate["snapshot_payload_hash"] = str(index) * 64
        duplicate["settlement_id"] = f"playbook-forward-settlement:legacy-{index}"
        duplicate["settlement_payload_hash"] = str(index + 4) * 64
        duplicate_settlements.append(duplicate)
    with snapshot_path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in duplicate_snapshots:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    with settlement_path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in duplicate_settlements:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    report = update_playbook_forward_evidence(
        _rankings(),
        history_root,
        "d" * 64,
        snapshot_path,
        settlement_path,
        report_path,
    )

    assert report["snapshot_count"] == 2
    assert report["raw_snapshot_ledger_count"] == 4
    assert report["same_market_date_duplicate_snapshot_count"] == 2
    assert report["settled_count"] == 2
    assert report["raw_settlement_ledger_count"] == 4
    assert report["non_evidentiary_raw_settlement_count"] == 2
    assert report["duplicate_snapshots_counted_as_evidence"] is False
    assert report["duplicate_settlements_counted_as_evidence"] is False
    assert len(snapshot_path.read_text(encoding="utf-8").splitlines()) == 4
    assert len(settlement_path.read_text(encoding="utf-8").splitlines()) == 4


def test_unmatured_snapshot_stays_pending_without_synthetic_outcome(
    tmp_path: Path,
) -> None:
    history_root = tmp_path / "history"
    _write_history(history_root, "BULL", [100.0, 101.0, 102.0])
    _write_history(history_root, "BEAR", [100.0, 99.0, 98.0])

    report = update_playbook_forward_evidence(
        _rankings(),
        history_root,
        "d" * 64,
        tmp_path / "snapshots.jsonl",
        tmp_path / "settlements.jsonl",
        tmp_path / "report.json",
    )

    assert report["settled_count"] == 0
    assert report["pending_count"] == 2
    assert report["pending_by_status"] == {"pending_minimum_horizon": 2}
    assert report["mean_within_batch_horizon_rank_ic"] is None
    assert report["directional_accuracy"] is None
