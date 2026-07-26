from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from dopey_attention.engine import (
    AttentionDataError,
    AttentionPaths,
    build_attention_snapshot,
    default_attention_policy,
    write_attention_snapshot,
)
from dopey_data.history_models import (
    ALLOWED_HISTORY_FORMATS,
    OPTIONAL_HISTORY_COLUMNS,
    REQUIRED_HISTORY_COLUMNS,
    history_manifest_hash,
)


def test_attention_snapshot_is_as_of_safe_and_source_provenanced(
    tmp_path: Path,
) -> None:
    decision_time = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    first_paths, market_date = _write_fixture_repository(
        tmp_path / "first", decision_time, 9_999_999
    )
    second_paths, second_market_date = _write_fixture_repository(
        tmp_path / "second", decision_time, 1
    )

    first = build_attention_snapshot(
        first_paths,
        ["AAPL"],
        market_date,
        decision_time,
        default_attention_policy(),
    )
    second = build_attention_snapshot(
        second_paths,
        ["AAPL"],
        second_market_date,
        decision_time,
        default_attention_policy(),
    )

    first_symbol = first["symbols"][0]
    second_symbol = second["symbols"][0]
    assert first["status"] == "partial"
    assert first["future_observation_consumed"] is False
    assert first["live_blocked"] is True
    assert first["live_execution_allowed"] is False
    assert first["trade_promotion_allowed"] is False
    assert first["directional_signal_allowed"] is False
    assert first_symbol["directional_bias"] is None
    assert first_symbol["attention_score"] == second_symbol["attention_score"]
    assert (
        first_symbol["component_scores"]["market_activity"][
            "source_slice_sha256"
        ]
        == second_symbol["component_scores"]["market_activity"][
            "source_slice_sha256"
        ]
    )
    assert (
        first_symbol["component_scores"]["market_activity"][
            "future_observation_count_excluded"
        ]
        == 1
    )
    assert first_symbol["component_scores"]["options_activity"]["score"] == 0.5
    assert first_symbol["component_scores"]["options_activity"]["status"] == (
        "scored_session_snapshot"
    )
    assert first_symbol["component_scores"]["news_event_intensity"]["input_count"] == 1
    assert first_symbol["completeness_ratio"] == 1.0
    assert len(first_symbol["provenance_sha256"]) == 64
    assert len(first["snapshot_sha256"]) == 64

    output_path = tmp_path / "attention_snapshot.json"
    write_attention_snapshot(first, output_path)
    published = json.loads(output_path.read_text(encoding="utf-8"))
    assert published["snapshot_sha256"] == first["snapshot_sha256"]


def test_attention_abstains_when_mandatory_market_evidence_is_missing(
    tmp_path: Path,
) -> None:
    decision_time = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    paths, market_date = _write_fixture_repository(
        tmp_path / "repository", decision_time, 1000
    )

    snapshot = build_attention_snapshot(
        paths,
        ["AAPL", "MSFT"],
        market_date,
        decision_time,
        default_attention_policy(),
    )

    by_symbol = {record["symbol"]: record for record in snapshot["symbols"]}
    assert by_symbol["AAPL"]["attention_score"] is not None
    assert by_symbol["MSFT"]["status"] == "abstained"
    assert by_symbol["MSFT"]["attention_score"] is None
    assert by_symbol["MSFT"]["missing_components"] == [
        "market_activity",
        "options_activity",
        "price_volatility_discontinuity",
    ]
    assert "history_manifest_missing_symbol:MSFT" in by_symbol["MSFT"][
        "component_scores"
    ]["market_activity"]["missing_reasons"]


def test_attention_writer_rejects_mutated_payload(tmp_path: Path) -> None:
    decision_time = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    paths, market_date = _write_fixture_repository(
        tmp_path / "repository", decision_time, 1000
    )
    snapshot = build_attention_snapshot(
        paths,
        ["AAPL"],
        market_date,
        decision_time,
        default_attention_policy(),
    )
    snapshot["symbols"][0]["attention_score"] = 1.0

    with pytest.raises(AttentionDataError, match="hash mismatch"):
        write_attention_snapshot(snapshot, tmp_path / "mutated.json")


def _write_fixture_repository(
    repository_root: Path,
    decision_time: datetime,
    future_volume: int,
) -> tuple[AttentionPaths, date]:
    history_root = repository_root / "dopey_data" / "history"
    history_raw = history_root / "raw"
    history_raw.mkdir(parents=True)
    dates = _weekday_dates(date(2026, 2, 2), 101)
    market_date = dates[-2]
    history_path = history_raw / "AAPL.csv"
    rows = _history_rows(dates, future_volume)
    _write_csv(history_path, rows, list(REQUIRED_HISTORY_COLUMNS) + ["source"])
    history_manifest_path = history_root / "history_dataset_manifest.json"
    history_payload: dict[str, Any] = {
        "artifact_type": "history_dataset_manifest",
        "history_dataset_manifest_version": "fixture-v1",
        "dataset_id": "attention-engine-fixture",
        "dataset_status": "operator_staged_real_dataset",
        "raw_data_directory": "raw",
        "required_universe": ["AAPL"],
        "required_columns": list(REQUIRED_HISTORY_COLUMNS),
        "optional_columns": list(OPTIONAL_HISTORY_COLUMNS),
        "allowed_formats": list(ALLOWED_HISTORY_FORMATS),
        "data_files": [
            {
                "path": "raw/AAPL.csv",
                "format": "csv",
                "symbols": ["AAPL"],
                "sha256": _sha256(history_path),
                "source": "fixture_authentic_provider",
                "row_count": len(rows),
            }
        ],
        "generated_real_data": False,
        "network_fetch_performed": False,
        "credential_required": False,
        "paper_only": True,
        "live_blocked": True,
        "manifest_reproducibility_hash": "",
    }
    history_payload["manifest_reproducibility_hash"] = history_manifest_hash(
        history_payload
    )
    history_manifest_path.write_text(
        json.dumps(history_payload), encoding="utf-8"
    )

    news_root = repository_root / "dopey_data" / "real" / "raw" / "news"
    news_root.mkdir(parents=True)
    news_data_path = news_root / "news_events.jsonl"
    news_event = {
        "event_id": "apple-event-1",
        "published_at": (decision_time - timedelta(hours=2)).isoformat(),
        "ingested_at": (decision_time - timedelta(hours=1)).isoformat(),
        "source_id": "fixture_official_source",
        "source_type": "official_rss",
        "source_authority": "official_us_government",
        "source_domain": "example.gov",
        "title": "Apple releases a market update",
        "summary": "",
        "url": "https://example.gov/apple-update",
    }
    news_data_path.write_text(
        json.dumps(news_event) + "\n", encoding="utf-8"
    )
    manifest_root = repository_root / "dopey_data" / "real" / "manifests"
    manifest_root.mkdir(parents=True)
    news_manifest_path = manifest_root / "news_context_manifest.json"
    news_manifest_path.write_text(
        json.dumps(
            {
                "created_at": (decision_time - timedelta(minutes=30)).isoformat(),
                "event_count": 1,
                "file_sha256": _sha256(news_data_path),
                "pipeline_status": "complete",
                "provider_terms_reviewed": True,
                "full_text_stored": False,
            }
        ),
        encoding="utf-8",
    )

    options_chain_root = (
        repository_root / "dopey_data" / "real" / "raw" / "options_chains"
    )
    option_snapshot_root = options_chain_root / market_date.isoformat()
    option_snapshot_root.mkdir(parents=True)
    option_path = option_snapshot_root / "AAPL_chain.csv"
    option_rows = [
        {
            "snapshot_date": market_date.isoformat(),
            "symbol": "AAPL",
            "expiry": (market_date + timedelta(days=10)).isoformat(),
            "dte_calendar": "10",
            "option_type": "call",
            "strike": "125",
            "bid": "2.00",
            "ask": "2.20",
            "mid": "2.10",
            "last": "2.05",
            "volume": "50",
            "open_interest": "100",
            "implied_vol": "0.30",
            "underlying_spot": "125",
            "source": "fixture_option_snapshot",
        }
    ]
    _write_csv(option_path, option_rows, list(option_rows[0]))
    option_relative = option_path.relative_to(repository_root).as_posix()
    options_manifest_path = manifest_root / "options_data_manifest.json"
    options_manifest_path.write_text(
        json.dumps(
            {
                "created_at": (decision_time - timedelta(minutes=20)).isoformat(),
                "paper_only": True,
                "live_blocked": True,
                "not_live_data": True,
                "not_real_data": False,
                "snapshot_dates": [market_date.isoformat()],
                "file_hashes": {option_relative: _sha256(option_path)},
            }
        ),
        encoding="utf-8",
    )
    return (
        {
            "repository_root": repository_root,
            "history_manifest_path": history_manifest_path,
            "news_data_path": news_data_path,
            "news_manifest_path": news_manifest_path,
            "options_chain_root": options_chain_root,
            "options_manifest_path": options_manifest_path,
        },
        market_date,
    )


def _weekday_dates(start: date, count: int) -> list[date]:
    output: list[date] = []
    cursor = start
    while len(output) < count:
        if cursor.weekday() < 5:
            output.append(cursor)
        cursor += timedelta(days=1)
    return output


def _history_rows(dates: list[date], future_volume: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, observed_date in enumerate(dates):
        close = 100.0 + index * 0.25
        volume = 5000 + (index % 11) * 50
        if index == len(dates) - 2:
            volume = 14_000
        if index == len(dates) - 1:
            volume = future_volume
            close = 300.0
        rows.append(
            {
                "date": observed_date.isoformat(),
                "symbol": "AAPL",
                "open": close - 0.10,
                "high": close + 1.00,
                "low": close - 1.00,
                "close": close,
                "adjusted_close": close,
                "volume": volume,
                "source": "fixture_authentic_provider",
            }
        )
    return rows


def _write_csv(
    path: Path, rows: list[dict[str, Any]], fieldnames: list[str]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
