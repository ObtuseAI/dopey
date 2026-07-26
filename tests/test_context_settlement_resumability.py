"""Integration proof for bounded, immutable external-context settlement."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from dopey_equity_swing.context_settlement import settle_context_decisions


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")


def _write_history(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("date", "symbol", "open", "high", "low", "close", "adjusted_close", "volume", "source"),
        )
        writer.writeheader()
        for index, close in enumerate((100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0)):
            writer.writerow({
                "date": f"2026-01-{index + 2:02d}",
                "symbol": "TEST",
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "adjusted_close": close,
                "volume": 1000,
                "source": "operator_staged_real_dataset",
            })


def test_context_settlement_resumes_without_rewriting_decisions(tmp_path: Path) -> None:
    history_path = tmp_path / "history" / "raw" / "TEST.csv"
    manifest_path = tmp_path / "history" / "history_dataset_manifest.json"
    validation_path = tmp_path / "artifacts" / "history_dataset_validation.json"
    decision_path = tmp_path / "artifacts" / "context_decisions.jsonl"
    outcome_path = tmp_path / "artifacts" / "context_outcomes.jsonl"
    cursor_path = tmp_path / "artifacts" / "context_cursor.json"
    operation_path = tmp_path / "artifacts" / "latest_context_settlement.json"
    _write_history(history_path)
    manifest_hash = "manifest-test-hash"
    _write_json(manifest_path, {
        "artifact_type": "history_dataset_manifest",
        "history_dataset_manifest_version": "test-v1",
        "dataset_id": "test-real-history",
        "dataset_status": "operator_staged_real_dataset",
        "raw_data_directory": str(history_path.parent),
        "required_universe": ["TEST"],
        "required_columns": ["date", "symbol", "open", "high", "low", "close", "adjusted_close", "volume", "source"],
        "optional_columns": [],
        "allowed_formats": ["csv"],
        "data_files": [{
            "path": "raw/TEST.csv",
            "format": "csv",
            "symbols": ["TEST"],
            "row_count": 7,
            "sha256": _hash(history_path),
            "source": "operator_staged_real_dataset",
        }],
        "generated_real_data": False,
        "network_fetch_performed": False,
        "credential_required": False,
        "paper_only": True,
        "live_blocked": True,
        "manifest_reproducibility_hash": manifest_hash,
    })
    _write_json(validation_path, {
        "dataset_status": "valid_real_dataset",
        "manifest_reproducibility_hash": manifest_hash,
        "end_date": "2026-01-08",
    })
    decisions = [
        {
            "decision_id": f"decision-{index}",
            "symbol": "TEST",
            "market_as_of": "2026-01-02",
            "expected_hold_trading_days": 2,
            "entry_reference_price": 100.0,
            "equity_direction": "bullish",
            "target_price": 103.0,
            "invalidation_price": 95.0,
        }
        for index in range(3)
    ]
    _write_jsonl(decision_path, decisions)
    decision_hash_before = _hash(decision_path)

    first = settle_context_decisions(
        decision_path,
        outcome_path,
        manifest_path,
        validation_path,
        cursor_path,
        operation_path,
        1,
    )
    second = settle_context_decisions(
        decision_path,
        outcome_path,
        manifest_path,
        validation_path,
        cursor_path,
        operation_path,
        1,
    )
    third = settle_context_decisions(
        decision_path,
        outcome_path,
        manifest_path,
        validation_path,
        cursor_path,
        operation_path,
        1,
    )
    rerun = settle_context_decisions(
        decision_path,
        outcome_path,
        manifest_path,
        validation_path,
        cursor_path,
        operation_path,
        1,
    )

    assert [first["newly_resolved_count"], second["newly_resolved_count"], third["newly_resolved_count"]] == [1, 1, 1]
    assert rerun["newly_resolved_count"] == 0
    assert rerun["unresolved_count_after"] == 0
    assert len(outcome_path.read_text(encoding="utf-8").splitlines()) == 3
    assert _hash(decision_path) == decision_hash_before
    assert json.loads(cursor_path.read_text(encoding="utf-8"))["pending_count"] == 0
    assert json.loads(operation_path.read_text(encoding="utf-8"))["operation_status"] == "complete"
