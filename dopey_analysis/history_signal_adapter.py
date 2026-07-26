"""History-spine adapter for offline signal engine inputs."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dopey_data.history_validator import validate_default_history_dataset

from .signal_models import PriceBar, SignalQualityFlag, make_price_bar, make_signal_series


REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY_SPINE_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "history" / "history_spine_summary.json"
VALID_REAL_DATASET_STATUS = "valid_real_dataset"
MISSING_REAL_HISTORY_SIGNAL_STATUS = "missing_real_history_signal_validation_only"


@dataclass(frozen=True)
class HistorySignalInput:
    signal_status: str
    history_dataset_status: str
    real_history_used: bool
    local_real_history_case_count: int
    series_by_symbol: dict[str, list[PriceBar]]
    quality_flags: list[SignalQualityFlag]
    history_spine_summary_path: str
    paper_only: bool
    live_blocked: bool
    no_network_market_data: bool
    no_fake_real_rows: bool

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["series_by_symbol"] = {
            symbol: [bar.to_dict() for bar in bars]
            for symbol, bars in sorted(self.series_by_symbol.items())
        }
        record["quality_flags"] = [flag.to_dict() for flag in self.quality_flags]
        record["paper_only"] = True
        record["live_blocked"] = True
        record["no_network_market_data"] = True
        record["no_fake_real_rows"] = True
        return record


def load_history_signal_input(history_spine_summary_path: Path | str) -> HistorySignalInput:
    target = Path(history_spine_summary_path)
    summary = _load_json(target)
    dataset_status = str(summary.get("dataset_status", "missing_real_dataset"))
    if dataset_status != VALID_REAL_DATASET_STATUS:
        flags = [
            _quality_flag(
                "signal-missing-real-history",
                "",
                "",
                "all",
                "warning",
                "missing_real_history",
                "history spine dataset_status is not valid_real_dataset; signal run is fixture/math validation only",
                "missing_real_history",
                False,
                True,
            ),
            _quality_flag(
                "signal-validation-only",
                "",
                "",
                "all",
                "warning",
                "missing_real_history_signal_validation_only",
                "computed signal machinery is available, but no real OHLCV signal evidence is claimed",
                "missing_real_history",
                False,
                True,
            ),
        ]
        return HistorySignalInput(
            signal_status=MISSING_REAL_HISTORY_SIGNAL_STATUS,
            history_dataset_status=dataset_status,
            real_history_used=False,
            local_real_history_case_count=0,
            series_by_symbol={},
            quality_flags=flags,
            history_spine_summary_path=str(target),
            paper_only=True,
            live_blocked=True,
            no_network_market_data=True,
            no_fake_real_rows=True,
        )
    result = validate_default_history_dataset()
    if result["dataset_status"] != VALID_REAL_DATASET_STATUS:
        flags = [
            _quality_flag(
                "signal-real-history-spine-recheck-failed",
                "",
                "",
                "all",
                "error",
                "history_spine_recheck_failed",
                "history spine summary reported valid_real_dataset, but local spine reload did not validate",
                "missing_real_history",
                False,
                True,
            ),
        ]
        return HistorySignalInput(
            signal_status=MISSING_REAL_HISTORY_SIGNAL_STATUS,
            history_dataset_status=str(result["dataset_status"]),
            real_history_used=False,
            local_real_history_case_count=0,
            series_by_symbol={},
            quality_flags=flags,
            history_spine_summary_path=str(target),
            paper_only=True,
            live_blocked=True,
            no_network_market_data=True,
            no_fake_real_rows=True,
        )
    series_by_symbol = _series_from_history_bars(result["bars_loaded"])
    flags = [
        _quality_flag(
            "signal-local-real-history-loaded",
            "",
            "",
            "all",
            "info",
            "local_real_history_loaded",
            "signals loaded hash-pinned local real OHLCV rows through the history spine",
            "local_real_history",
            True,
            False,
        ),
    ]
    return HistorySignalInput(
        signal_status="local_real_history_signal_computation_ready",
        history_dataset_status=VALID_REAL_DATASET_STATUS,
        real_history_used=True,
        local_real_history_case_count=sum(len(bars) for bars in series_by_symbol.values()),
        series_by_symbol=series_by_symbol,
        quality_flags=flags,
        history_spine_summary_path=str(target),
        paper_only=True,
        live_blocked=True,
        no_network_market_data=True,
        no_fake_real_rows=True,
    )


def load_default_history_signal_input() -> HistorySignalInput:
    return load_history_signal_input(HISTORY_SPINE_SUMMARY_PATH)


def history_signal_input_summary(record: HistorySignalInput) -> dict[str, Any]:
    return {
        "artifact_type": "signal_engine_input_summary",
        "signal_status": record.signal_status,
        "history_dataset_status": record.history_dataset_status,
        "real_history_used": record.real_history_used,
        "local_real_history_case_count": record.local_real_history_case_count,
        "history_spine_summary_path": record.history_spine_summary_path,
        "quality_flags": sorted({flag.reason_code for flag in record.quality_flags}),
        "network_market_data_fetch_performed": False,
        "fake_real_rows_generated": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _series_from_history_bars(rows: list[dict[str, Any]]) -> dict[str, list[PriceBar]]:
    grouped: dict[str, list[PriceBar]] = {}
    for row in rows:
        bar = make_price_bar(
            str(row["symbol"]),
            str(row["date"]),
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            float(row["adjusted_close"]),
            int(row["volume"]),
            "local_real_history",
            True,
            False,
            False,
        )
        grouped.setdefault(bar.symbol, []).append(bar)
    return {
        symbol: make_signal_series(symbol, bars, "local_real_history", True, False, False).bars
        for symbol, bars in grouped.items()
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"dataset_status": "missing_real_dataset"}
    text = path.read_text(encoding="utf-8").strip()
    return json.loads(text) if text else {"dataset_status": "missing_real_dataset"}


def _quality_flag(
    flag_id: str,
    symbol: str,
    signal_date: str,
    signal_family: str,
    severity: str,
    reason_code: str,
    message: str,
    data_source_tier: str,
    real_history_used: bool,
    fixture_only: bool,
) -> SignalQualityFlag:
    record = SignalQualityFlag(
        artifact_type="signal_quality_flag",
        flag_id=flag_id,
        severity=severity,
        symbol=symbol,
        signal_date=signal_date,
        signal_family=signal_family,
        reason_code=reason_code,
        message=message,
        data_source_tier=data_source_tier,
        real_history_used=real_history_used,
        fixture_only=fixture_only,
        not_real_signal_evidence=not real_history_used,
        paper_only=True,
        live_blocked=True,
        flag_hash="",
    )
    return SignalQualityFlag(**record.to_dict())
