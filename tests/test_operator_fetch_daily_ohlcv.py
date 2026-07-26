"""Safety and transaction proofs for the operator OHLCV updater."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from dopey_data import history_validator
from dopey_data.history_models import history_manifest_hash
from dopey_data.history_validator import validate_history_dataset
from operator_tools import operator_fetch_daily_ohlcv as updater


CSV_HEADER = "date,symbol,open,high,low,close,adjusted_close,volume,source\n"
BASE_ROW = "2026-07-17,AAPL,100.0,102.0,99.0,101.0,101.0,1000,yahoo_finance\n"
NEW_ROW = "2026-07-20,AAPL,101.0,104.0,100.0,103.0,103.0,1200,yahoo_finance"


class _FakeIndex:
    def __init__(self, value: date) -> None:
        self._value = value

    def date(self) -> date:
        return self._value


class _FakeFrame:
    def __init__(self, row: dict[str, object]) -> None:
        self._row = row

    def iterrows(self) -> list[tuple[_FakeIndex, dict[str, object]]]:
        return [(_FakeIndex(date(2026, 7, 20)), self._row)]


class _FakeTicker:
    def __init__(self, row: dict[str, object]) -> None:
        self._row = row

    def history(self, period: str, auto_adjust: bool) -> _FakeFrame:
        assert period == "10d"
        assert auto_adjust is False
        return _FakeFrame(self._row)


class _EmptyFrame:
    index: tuple[object, ...] = ()

    def iterrows(self) -> list[tuple[_FakeIndex, dict[str, object]]]:
        return []


class _EmptyTicker:
    def history(self, period: str, auto_adjust: bool) -> _EmptyFrame:
        assert period == "10d"
        assert auto_adjust is False
        return _EmptyFrame()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _configure_transaction_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path]:
    repo = tmp_path / "repo"
    history_dir = repo / "dopey_data" / "history" / "raw"
    real_dir = repo / "dopey_data" / "real" / "raw" / "daily_ohlcv"
    history_manifest_path = repo / "dopey_data" / "history" / "history_dataset_manifest.json"
    real_manifest_path = repo / "dopey_data" / "real" / "manifests" / "real_data_manifest.json"
    history_path = history_dir / "AAPL.csv"
    real_path = real_dir / "AAPL.csv"
    for path in (history_path, real_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(CSV_HEADER + BASE_ROW, encoding="utf-8")
    history_manifest: dict[str, Any] = {
        "allowed_formats": ["csv"],
        "artifact_type": "history_dataset_manifest",
        "credential_required": False,
        "data_files": [
            {
                "format": "csv",
                "path": "raw/AAPL.csv",
                "row_count": 1,
                "sha256": _sha256(history_path),
                "source": "yahoo_finance",
                "symbols": ["AAPL"],
            }
        ],
        "dataset_id": "test-dataset",
        "dataset_status": "valid_real_dataset",
        "generated_real_data": False,
        "history_dataset_manifest_version": "test-v1",
        "manifest_reproducibility_hash": "",
        "network_fetch_performed": False,
        "optional_columns": ["source"],
        "paper_only": True,
        "raw_data_directory": history_dir.as_posix(),
        "required_columns": [
            "date",
            "symbol",
            "open",
            "high",
            "low",
            "close",
            "adjusted_close",
            "volume",
        ],
        "required_universe": ["AAPL"],
        "live_blocked": True,
    }
    history_manifest["manifest_reproducibility_hash"] = history_manifest_hash(history_manifest)
    _write_json(history_manifest_path, history_manifest)
    _write_json(
        real_manifest_path,
        {
            "file_hashes": {
                real_path.relative_to(repo).as_posix(): _sha256(real_path),
            }
        },
    )
    monkeypatch.setattr(updater, "REPO", repo)
    monkeypatch.setattr(updater, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(updater, "REAL_DIR", real_dir)
    monkeypatch.setattr(updater, "HISTORY_MANIFEST_PATH", history_manifest_path)
    monkeypatch.setattr(updater, "REAL_MANIFEST_PATH", real_manifest_path)
    return history_path, real_path, history_manifest_path, real_manifest_path


def _valid_history_result() -> dict[str, Any]:
    return {
        "dataset_status": "valid_real_dataset",
        "quality_flags": [],
        "validation": {"row_count": 2},
    }


def test_intraday_collection_stops_at_prior_completed_session() -> None:
    assert updater.latest_completed_market_session(
        datetime(2026, 7, 21, 19, 0, tzinfo=timezone.utc)
    ) == date(2026, 7, 20)


def test_post_close_collection_waits_for_provider_finalization_buffer() -> None:
    assert updater.latest_completed_market_session(
        datetime(2026, 7, 21, 20, 1, tzinfo=timezone.utc)
    ) == date(2026, 7, 20)
    assert updater.latest_completed_market_session(
        datetime(2026, 7, 21, 20, 31, tzinfo=timezone.utc)
    ) == date(2026, 7, 21)


def test_weekend_collection_can_catch_up_to_friday() -> None:
    assert updater.latest_completed_market_session(
        datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc)
    ) == date(2026, 7, 17)


@pytest.mark.parametrize(
    "invalid_field",
    [
        {"Open": math.nan},
        {"High": math.inf},
        {"Low": -math.inf},
        {"High": 100.0, "Close": 101.0},
        {"Low": 102.0, "Open": 101.0},
        {"Adj Close": math.nan},
        {"Volume": math.nan},
        {"Volume": -1},
        {"Volume": 1.5},
    ],
)
def test_provider_row_rejects_nonfinite_and_invalid_invariants(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    invalid_field: dict[str, object],
) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    (history_dir / "AAPL.csv").write_text(CSV_HEADER + BASE_ROW, encoding="utf-8")
    row: dict[str, object] = {
        "Open": 101.0,
        "High": 104.0,
        "Low": 100.0,
        "Close": 103.0,
        "Adj Close": 103.0,
        "Volume": 1200,
    }
    row.update(invalid_field)
    monkeypatch.setattr(updater, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(updater.yf, "Ticker", lambda symbol: _FakeTicker(row))

    with pytest.raises(updater.OhlcvDataValidationError):
        updater.collect_new_rows("AAPL", date(2026, 7, 20))


def test_empty_provider_frame_fails_when_a_newer_session_is_due(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    (history_dir / "AAPL.csv").write_text(
        CSV_HEADER + BASE_ROW,
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(updater.yf, "Ticker", lambda symbol: _EmptyTicker())

    with pytest.raises(
        updater.OhlcvDataValidationError,
        match="no eligible bar",
    ):
        updater.collect_new_rows("AAPL", date(2026, 7, 20))


def test_transaction_publishes_both_copies_and_manifests_after_full_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history_path, real_path, history_manifest_path, real_manifest_path = _configure_transaction_tree(
        monkeypatch,
        tmp_path,
    )
    validation_calls: list[tuple[Path, Path, bool]] = []

    def validate(manifest_path: Path, raw_dir: Path, write_placeholder: bool) -> dict[str, Any]:
        validation_calls.append((Path(manifest_path), Path(raw_dir), write_placeholder))
        return validate_history_dataset(manifest_path, raw_dir, write_placeholder)

    monkeypatch.setattr(history_validator, "REQUIRED_HISTORY_UNIVERSE", ("AAPL",))
    monkeypatch.setattr(updater, "validate_history_dataset", validate)
    result = updater.publish_refresh_transaction(
        {"AAPL": [NEW_ROW]},
        date(2026, 7, 20),
        datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
    )

    assert result["dataset_status"] == "valid_real_dataset"
    assert history_path.read_bytes() == real_path.read_bytes()
    assert history_path.read_text(encoding="utf-8").endswith(NEW_ROW + "\n")
    assert validation_calls == [(history_manifest_path, history_path.parent, False)]
    history_manifest = json.loads(history_manifest_path.read_text(encoding="utf-8"))
    assert history_manifest["data_files"][0]["row_count"] == 2
    assert history_manifest["data_files"][0]["sha256"] == _sha256(history_path)
    assert history_manifest["manifest_reproducibility_hash"] == history_manifest_hash(history_manifest)
    real_manifest = json.loads(real_manifest_path.read_text(encoding="utf-8"))
    relative = real_path.relative_to(tmp_path / "repo").as_posix()
    assert real_manifest["file_hashes"][relative] == _sha256(real_path)
    assert not history_manifest_path.with_name(".operator_fetch_daily_ohlcv.lock").exists()


def test_transaction_bootstraps_only_missing_real_copy_from_validated_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history_path, real_path, history_manifest_path, real_manifest_path = _configure_transaction_tree(
        monkeypatch,
        tmp_path,
    )
    real_path.unlink()
    real_manifest = json.loads(real_manifest_path.read_text(encoding="utf-8"))
    real_manifest["file_hashes"] = {}
    _write_json(real_manifest_path, real_manifest)
    monkeypatch.setattr(history_validator, "REQUIRED_HISTORY_UNIVERSE", ("AAPL",))

    result = updater.publish_refresh_transaction(
        {"AAPL": [NEW_ROW]},
        date(2026, 7, 20),
        datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
    )

    assert result["dataset_status"] == "valid_real_dataset"
    assert history_path.read_bytes() == real_path.read_bytes()
    assert history_path.read_text(encoding="utf-8").endswith(NEW_ROW + "\n")
    published_real_manifest = json.loads(real_manifest_path.read_text(encoding="utf-8"))
    relative = real_path.relative_to(tmp_path / "repo").as_posix()
    assert published_real_manifest["file_hashes"][relative] == _sha256(real_path)
    published_history_manifest = json.loads(history_manifest_path.read_text(encoding="utf-8"))
    assert published_history_manifest["data_files"][0]["sha256"] == _sha256(history_path)


def test_missing_real_bootstrap_rolls_back_creation_when_post_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history_path, real_path, history_manifest_path, real_manifest_path = _configure_transaction_tree(
        monkeypatch,
        tmp_path,
    )
    real_path.unlink()
    real_manifest = json.loads(real_manifest_path.read_text(encoding="utf-8"))
    real_manifest["file_hashes"] = {}
    _write_json(real_manifest_path, real_manifest)
    before = {
        path: path.read_bytes()
        for path in (history_path, history_manifest_path, real_manifest_path)
    }
    monkeypatch.setattr(history_validator, "REQUIRED_HISTORY_UNIVERSE", ("AAPL",))
    validation_call_count = 0

    def validate(manifest_path: Path, raw_dir: Path, write_placeholder: bool) -> dict[str, Any]:
        nonlocal validation_call_count
        validation_call_count += 1
        if validation_call_count == 1:
            return validate_history_dataset(manifest_path, raw_dir, write_placeholder)
        return {
            "dataset_status": "invalid_real_dataset",
            "quality_flags": [{"severity": "error", "reason_code": "injected_failure"}],
            "validation": {"row_count": 0},
        }

    monkeypatch.setattr(updater, "validate_history_dataset", validate)

    with pytest.raises(updater.OhlcvRefreshTransactionError, match="exact prior bytes"):
        updater.publish_refresh_transaction(
            {"AAPL": [NEW_ROW]},
            date(2026, 7, 20),
            datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
        )

    assert not real_path.exists()
    assert {
        path: path.read_bytes()
        for path in (history_path, history_manifest_path, real_manifest_path)
    } == before


def test_existing_copy_mismatch_remains_a_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history_path, real_path, history_manifest_path, real_manifest_path = _configure_transaction_tree(
        monkeypatch,
        tmp_path,
    )
    real_path.write_bytes(real_path.read_bytes() + b"\n")
    paths = (history_path, real_path, history_manifest_path, real_manifest_path)
    before = {path: path.read_bytes() for path in paths}

    with pytest.raises(updater.OhlcvRefreshTransactionError, match="copies differ"):
        updater.publish_refresh_transaction(
            {"AAPL": [NEW_ROW]},
            date(2026, 7, 20),
            datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
        )

    assert {path: path.read_bytes() for path in paths} == before


def test_tail_repair_transaction_replaces_both_copies_through_full_validator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history_path, real_path, history_manifest_path, _ = _configure_transaction_tree(
        monkeypatch,
        tmp_path,
    )
    baseline_hash = _sha256(history_path)
    candidate = (
        CSV_HEADER
        + "2026-07-17,AAPL,100.0,103.0,99.0,102.0,102.0,1100,yahoo_finance\n"
    ).encode("utf-8")
    validation_calls: list[tuple[Path, Path, bool]] = []

    def validate(manifest_path: Path, raw_dir: Path, write_placeholder: bool) -> dict[str, Any]:
        validation_calls.append((Path(manifest_path), Path(raw_dir), write_placeholder))
        return validate_history_dataset(manifest_path, raw_dir, write_placeholder)

    monkeypatch.setattr(history_validator, "REQUIRED_HISTORY_UNIVERSE", ("AAPL",))
    monkeypatch.setattr(updater, "validate_history_dataset", validate)
    result = updater.publish_tail_repair_transaction(
        {"AAPL": candidate},
        {"AAPL": baseline_hash},
        datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
    )

    assert result["dataset_status"] == "valid_real_dataset"
    assert history_path.read_bytes() == candidate
    assert real_path.read_bytes() == candidate
    assert validation_calls == [(history_manifest_path, history_path.parent, False)]


def test_tail_repair_transaction_rejects_changed_source_without_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _configure_transaction_tree(monkeypatch, tmp_path)
    before = {path: path.read_bytes() for path in paths}
    candidate = (CSV_HEADER + BASE_ROW).encode("utf-8")

    with pytest.raises(updater.OhlcvRefreshTransactionError, match="changed after repair candidate"):
        updater.publish_tail_repair_transaction(
            {"AAPL": candidate},
            {"AAPL": "0" * 64},
            datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
        )

    assert {path: path.read_bytes() for path in paths} == before


def test_invalid_post_write_validation_restores_exact_prior_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _configure_transaction_tree(monkeypatch, tmp_path)
    before = {path: path.read_bytes() for path in paths}
    monkeypatch.setattr(
        updater,
        "validate_history_dataset",
        lambda manifest_path, raw_dir, write_placeholder: {
            "dataset_status": "invalid_real_dataset",
            "quality_flags": [{"severity": "error", "reason_code": "test_failure"}],
            "validation": {"row_count": 0},
        },
    )

    with pytest.raises(updater.OhlcvRefreshTransactionError, match="exact prior bytes"):
        updater.publish_refresh_transaction(
            {"AAPL": [NEW_ROW]},
            date(2026, 7, 20),
            datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
        )

    assert {path: path.read_bytes() for path in paths} == before


def test_mid_publish_failure_restores_every_published_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history_path, real_path, history_manifest_path, real_manifest_path = _configure_transaction_tree(
        monkeypatch,
        tmp_path,
    )
    paths = (history_path, real_path, history_manifest_path, real_manifest_path)
    before = {path: path.read_bytes() for path in paths}
    real_replace = updater.os.replace
    failed = False

    def fail_once(source: Path, target: Path) -> None:
        nonlocal failed
        if Path(target) == real_path and not failed:
            failed = True
            raise OSError("injected publish failure")
        real_replace(source, target)

    monkeypatch.setattr(updater.os, "replace", fail_once)
    monkeypatch.setattr(updater, "validate_history_dataset", lambda *args: _valid_history_result())

    with pytest.raises(updater.OhlcvRefreshTransactionError, match="exact prior bytes"):
        updater.publish_refresh_transaction(
            {"AAPL": [NEW_ROW]},
            date(2026, 7, 20),
            datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
        )

    assert {path: path.read_bytes() for path in paths} == before


def test_full_history_validator_rejects_nonfinite_price(tmp_path: Path) -> None:
    history_root = tmp_path / "history"
    raw_dir = history_root / "raw"
    raw_dir.mkdir(parents=True)
    data_path = raw_dir / "AAPL.csv"
    data_path.write_text(
        CSV_HEADER
        + "2026-07-17,AAPL,nan,102.0,99.0,101.0,101.0,1000,yahoo_finance\n",
        encoding="utf-8",
    )
    manifest: dict[str, Any] = {
        "allowed_formats": ["csv"],
        "artifact_type": "history_dataset_manifest",
        "credential_required": False,
        "data_files": [
            {
                "format": "csv",
                "path": "raw/AAPL.csv",
                "row_count": 1,
                "sha256": _sha256(data_path),
                "source": "yahoo_finance",
                "symbols": ["AAPL"],
            }
        ],
        "dataset_id": "nonfinite-test",
        "dataset_status": "valid_real_dataset",
        "generated_real_data": False,
        "history_dataset_manifest_version": "test-v1",
        "manifest_reproducibility_hash": "",
        "network_fetch_performed": False,
        "optional_columns": ["source"],
        "paper_only": True,
        "raw_data_directory": raw_dir.as_posix(),
        "required_columns": [],
        "required_universe": [],
        "live_blocked": True,
    }
    manifest["manifest_reproducibility_hash"] = history_manifest_hash(manifest)
    manifest_path = history_root / "history_dataset_manifest.json"
    _write_json(manifest_path, manifest)

    result = validate_history_dataset(manifest_path, raw_dir, False)

    assert result["dataset_status"] == "invalid_real_dataset"
    assert "ohlcv_nonfinite" in {
        flag["reason_code"] for flag in result["quality_flags"]
    }
