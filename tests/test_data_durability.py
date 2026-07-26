"""Focused durability proofs for governed market-data operator paths."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from dopey_data import history_validator
from dopey_data.history_models import history_manifest_hash
from dopey_data.history_validator import placeholder_history_manifest_record
from operator_tools import operator_fetch_daily_ohlcv as ohlcv_updater
from operator_tools import operator_fetch_macro_context as macro_fetcher


CSV_HEADER = (
    "date,symbol,open,high,low,close,adjusted_close,volume,source\n"
)


def _write_history_manifest(
    root: Path,
    data_file_path: str,
    source_path: Path,
) -> Path:
    manifest_path = root / "history_dataset_manifest.json"
    record = placeholder_history_manifest_record(root / "raw")
    record["dataset_status"] = "operator_staged_real_dataset"
    record["data_files"] = [
        {
            "path": data_file_path,
            "format": "csv",
            "symbols": ["SPY"],
            "sha256": ohlcv_updater._file_sha256(source_path),
            "source": "yahoo_finance",
            "row_count": 2,
        }
    ]
    record["manifest_reproducibility_hash"] = history_manifest_hash(record)
    manifest_path.write_text(
        json.dumps(record, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _write_spy_rows(path: Path, days: tuple[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        f"{day},SPY,100,102,99,101,101,1000,yahoo_finance\n"
        for day in days
    ]
    path.write_text(CSV_HEADER + "".join(rows), encoding="utf-8")


def test_macro_atomic_writer_preserves_prior_generation_on_replace_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "macro.csv"
    target.write_text("prior\n", encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError(f"injected replace failure: source={source}, destination={destination}")

    monkeypatch.setattr(macro_fetcher.os, "replace", fail_replace)

    with pytest.raises(OSError, match="injected replace failure"):
        macro_fetcher._atomic_write_text(target, "next\n")

    assert target.read_text(encoding="utf-8") == "prior\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_history_validator_uses_exchange_sessions_and_fails_on_real_gap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(history_validator, "REQUIRED_HISTORY_UNIVERSE", ("SPY",))
    holiday_root = tmp_path / "holiday"
    holiday_file = holiday_root / "raw" / "SPY.csv"
    _write_spy_rows(holiday_file, ("2026-07-02", "2026-07-06"))
    holiday_manifest = _write_history_manifest(
        holiday_root,
        "raw/SPY.csv",
        holiday_file,
    )

    holiday_result = history_validator.validate_history_dataset(
        holiday_manifest,
        holiday_file.parent,
        False,
    )

    assert holiday_result["dataset_status"] == "valid_real_dataset"
    assert holiday_result["coverage_records"][0]["missing_weekday_count"] == 0

    gap_root = tmp_path / "gap"
    gap_file = gap_root / "raw" / "SPY.csv"
    _write_spy_rows(gap_file, ("2026-07-02", "2026-07-07"))
    gap_manifest = _write_history_manifest(gap_root, "raw/SPY.csv", gap_file)

    gap_result = history_validator.validate_history_dataset(
        gap_manifest,
        gap_file.parent,
        False,
    )

    assert gap_result["dataset_status"] == "invalid_real_dataset"
    assert gap_result["coverage_records"][0]["missing_dates"] == ["2026-07-06"]
    assert "missing_trading_sessions" in {
        flag["reason_code"] for flag in gap_result["quality_flags"]
    }


def test_history_manifest_cannot_escape_declared_raw_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(history_validator, "REQUIRED_HISTORY_UNIVERSE", ("SPY",))
    history_root = tmp_path / "history"
    escaped = history_root / "escaped.csv"
    _write_spy_rows(escaped, ("2026-07-02", "2026-07-06"))
    manifest_path = _write_history_manifest(
        history_root,
        "../escaped.csv",
        escaped,
    )

    result = history_validator.validate_history_dataset(
        manifest_path,
        history_root / "raw",
        False,
    )

    assert result["dataset_status"] == "invalid_real_dataset"
    assert "manifest_path_containment" in {
        flag["reason_code"] for flag in result["quality_flags"]
    }
    assert result["validation"]["row_count"] == 0


def test_history_manifest_rejects_absolute_data_file_reference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(history_validator, "REQUIRED_HISTORY_UNIVERSE", ("SPY",))
    history_root = tmp_path / "history"
    data_file = history_root / "raw" / "SPY.csv"
    _write_spy_rows(data_file, ("2026-07-02", "2026-07-06"))
    manifest_path = _write_history_manifest(
        history_root,
        str(data_file.resolve()),
        data_file,
    )

    result = history_validator.validate_history_dataset(
        manifest_path,
        data_file.parent,
        False,
    )

    assert result["dataset_status"] == "invalid_real_dataset"
    assert "manifest_path_containment" in {
        flag["reason_code"] for flag in result["quality_flags"]
    }
    assert result["validation"]["row_count"] == 0


def test_provider_fetch_retries_then_returns_and_uses_adaptive_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[tuple[str, str]] = []
    delays: list[float] = []
    sentinel = object()

    class TransientTicker:
        def __init__(self, symbol: str) -> None:
            self._symbol = symbol

        def history(self, period: str, auto_adjust: bool) -> Any:
            assert auto_adjust is False
            attempts.append((self._symbol, period))
            if len(attempts) < 3:
                raise ConnectionError("transient provider failure")
            return sentinel

    monkeypatch.setattr(ohlcv_updater.yf, "Ticker", TransientTicker)
    monkeypatch.setattr(ohlcv_updater.time, "sleep", delays.append)

    result = ohlcv_updater._fetch_provider_history_with_retries(
        "VIX",
        "3mo",
        3,
        0.5,
    )

    assert result is sentinel
    assert attempts == [("^VIX", "3mo"), ("^VIX", "3mo"), ("^VIX", "3mo")]
    assert delays == [0.5, 1.0]
    assert ohlcv_updater._provider_history_period(
        date(2026, 1, 1),
        date(2026, 7, 1),
    ) == "6mo"


def test_stale_dead_refresh_lock_is_preserved_and_recovered(tmp_path: Path) -> None:
    lock_path = tmp_path / ".operator_fetch_daily_ohlcv.lock"
    lock_path.write_text(
        json.dumps(
            {
                "pid": 2_147_483_647,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "owner_id": "dead-owner",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with ohlcv_updater._exclusive_refresh_lock(lock_path):
        assert lock_path.exists()
        current = json.loads(lock_path.read_text(encoding="utf-8"))
        assert current["pid"] == os.getpid()
        assert current["owner_id"] != "dead-owner"

    assert not lock_path.exists()
    quarantined = list(tmp_path.glob(f"{lock_path.name}.stale.*"))
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text(encoding="utf-8"))["owner_id"] == "dead-owner"


def test_fresh_live_refresh_lock_remains_exclusive(tmp_path: Path) -> None:
    lock_path = tmp_path / ".operator_fetch_daily_ohlcv.lock"
    lock_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "created_at_utc": (
                    datetime.now(timezone.utc) - timedelta(minutes=1)
                ).isoformat(),
                "owner_id": "live-owner",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ohlcv_updater.OhlcvRefreshTransactionError,
        match="fresh live process",
    ):
        with ohlcv_updater._exclusive_refresh_lock(lock_path):
            raise AssertionError("fresh live lock must not be acquired")

    assert json.loads(lock_path.read_text(encoding="utf-8"))["owner_id"] == "live-owner"
