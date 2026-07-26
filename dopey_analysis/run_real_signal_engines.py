"""Run DOPEY's offline computed signal engines."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dopey_data.run_history_dataset_validation import run_history_dataset_validation
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR

from .history_signal_adapter import history_signal_input_summary, load_default_history_signal_input
from .signal_models import (
    SIGNAL_ENGINE_VERSION,
    SignalEngineRunResult,
    SignalQualityFlag,
    make_price_bar,
    make_signal_series,
    stable_signal_hash,
)
from .technical_signal_engine import (
    compute_breakout_signal,
    compute_fakeout_signal,
    compute_market_regime_signal,
    compute_momentum_signal,
    compute_relative_strength_signal,
    compute_trend_pullback_signal,
    compute_volatility_regime_signal,
    map_directional_setup_signal,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
SIGNAL_FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "signals"
SAMPLE_PRICE_SERIES_PATH = SIGNAL_FIXTURE_DIR / "sample_price_series.json"
SAMPLE_BENCHMARK_SERIES_PATH = SIGNAL_FIXTURE_DIR / "sample_benchmark_series.json"
SIGNAL_EXPECTED_MATH_CASES_PATH = SIGNAL_FIXTURE_DIR / "signal_expected_math_cases.json"
SIGNAL_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "signals"
SIGNAL_ENGINE_INPUT_SUMMARY_PATH = SIGNAL_ARTIFACT_DIR / "signal_engine_input_summary.json"
MOMENTUM_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "momentum_signals.jsonl"
BREAKOUT_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "breakout_signals.jsonl"
FAKEOUT_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "fakeout_signals.jsonl"
TREND_PULLBACK_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "trend_pullback_signals.jsonl"
VOLATILITY_REGIME_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "volatility_regime_signals.jsonl"
RELATIVE_STRENGTH_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "relative_strength_signals.jsonl"
MARKET_REGIME_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "market_regime_signals.jsonl"
DIRECTIONAL_SETUP_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "directional_setup_signals.jsonl"
SIGNAL_QUALITY_FLAGS_PATH = SIGNAL_ARTIFACT_DIR / "signal_quality_flags.jsonl"
SIGNAL_ENGINE_SUMMARY_PATH = SIGNAL_ARTIFACT_DIR / "signal_engine_summary.json"
SIGNAL_ENGINE_PROOF_PATH = SIGNAL_ARTIFACT_DIR / "signal_engine_proof.jsonl"
SIGNAL_ENGINE_REPORT_PATH = REPORTS_DIR / "DOPEY_REAL_SIGNAL_ENGINES_REPORT.md"
SIGNAL_ENGINE_LEDGER_PATH = REPORTS_DIR / "DOPEY_REAL_SIGNAL_ENGINES_ARTIFACT_LEDGER.md"


def run_real_signal_engines() -> dict[str, Any]:
    run_history_dataset_validation()
    fixture_bundle = build_signal_fixture_bundle()
    _write_fixture_files(fixture_bundle)
    history_input = load_default_history_signal_input()
    fixture_series = _fixture_signal_series(fixture_bundle)
    benchmark_series = _fixture_benchmark_series(fixture_bundle)
    input_summary = {
        **history_signal_input_summary(history_input),
        "signal_engine_version": SIGNAL_ENGINE_VERSION,
        "signal_engine_status": history_input.signal_status,
        "fixture_price_series_path": str(SAMPLE_PRICE_SERIES_PATH),
        "fixture_benchmark_series_path": str(SAMPLE_BENCHMARK_SERIES_PATH),
        "fixture_math_cases_path": str(SIGNAL_EXPECTED_MATH_CASES_PATH),
        "not_real_signal_evidence": True,
    }
    computed = _compute_fixture_signals(fixture_bundle["expected_cases"]["cases"], fixture_series, benchmark_series)
    directional = [
        map_directional_setup_signal(record)
        for records in computed.values()
        for record in records
    ]
    directional_dicts = [record.to_dict() for record in directional]
    quality_flags = [flag.to_dict() for flag in history_input.quality_flags]
    quality_flags.extend(_engine_quality_flags(history_input.history_dataset_status))
    family_records = {
        "momentum": computed["momentum"],
        "breakout": computed["breakout"],
        "fakeout": computed["fakeout"],
        "trend_pullback": computed["trend_pullback"],
        "volatility_regime": computed["volatility_regime"],
        "relative_strength": computed["relative_strength"],
        "market_regime": computed["market_regime"],
        "directional_setup": directional_dicts,
    }
    family_distribution = _family_distribution(family_records)
    direction_distribution = _direction_distribution(family_records)
    long_call_count = sum(1 for record in directional_dicts if record["long_call_candidate"])
    long_put_count = sum(1 for record in directional_dicts if record["long_put_candidate"])
    no_trade_count = sum(1 for record in directional_dicts if record["no_trade"])
    summary_seed = SignalEngineRunResult(
        artifact_type="signal_engine_summary",
        signal_engine_version=SIGNAL_ENGINE_VERSION,
        signal_engine_status=history_input.signal_status,
        history_dataset_status=history_input.history_dataset_status,
        real_history_used=history_input.real_history_used,
        fixture_only_case_count=len(fixture_bundle["expected_cases"]["cases"]),
        local_real_history_case_count=0 if not history_input.real_history_used else history_input.local_real_history_case_count,
        signal_family_distribution=family_distribution,
        direction_distribution=direction_distribution,
        long_call_candidate_count=long_call_count,
        long_put_candidate_count=long_put_count,
        no_trade_count=no_trade_count,
        quality_flags=sorted({flag["reason_code"] for flag in quality_flags}),
        not_real_edge_evidence=True,
        paper_only=True,
        live_blocked=True,
        next_recommended_target="DOPEY_HONEST_BACKTESTER_V1",
        artifact_paths=signal_artifact_paths(),
        run_hash="",
    )
    summary = summary_seed.to_dict()
    proof = _proof_record(summary)
    SIGNAL_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(SIGNAL_ENGINE_INPUT_SUMMARY_PATH, input_summary)
    _write_jsonl(MOMENTUM_SIGNALS_PATH, family_records["momentum"])
    _write_jsonl(BREAKOUT_SIGNALS_PATH, family_records["breakout"])
    _write_jsonl(FAKEOUT_SIGNALS_PATH, family_records["fakeout"])
    _write_jsonl(TREND_PULLBACK_SIGNALS_PATH, family_records["trend_pullback"])
    _write_jsonl(VOLATILITY_REGIME_SIGNALS_PATH, family_records["volatility_regime"])
    _write_jsonl(RELATIVE_STRENGTH_SIGNALS_PATH, family_records["relative_strength"])
    _write_jsonl(MARKET_REGIME_SIGNALS_PATH, family_records["market_regime"])
    _write_jsonl(DIRECTIONAL_SETUP_SIGNALS_PATH, directional_dicts)
    _write_jsonl(SIGNAL_QUALITY_FLAGS_PATH, quality_flags)
    _write_json(SIGNAL_ENGINE_SUMMARY_PATH, summary)
    _write_jsonl(SIGNAL_ENGINE_PROOF_PATH, [proof])
    _write_report(summary)
    _write_ledger(summary)
    return {
        "signal_engine_status": summary["signal_engine_status"],
        "history_dataset_status": summary["history_dataset_status"],
        "real_history_used": summary["real_history_used"],
        "fixture_only_case_count": summary["fixture_only_case_count"],
        "local_real_history_case_count": summary["local_real_history_case_count"],
        "signal_family_distribution": summary["signal_family_distribution"],
        "direction_distribution": summary["direction_distribution"],
        "long_call_candidate_count": summary["long_call_candidate_count"],
        "long_put_candidate_count": summary["long_put_candidate_count"],
        "no_trade_count": summary["no_trade_count"],
        "quality_flags": summary["quality_flags"],
        "not_real_edge_evidence": summary["not_real_edge_evidence"],
        "paper_only": summary["paper_only"],
        "live_blocked": summary["live_blocked"],
        "next_recommended_target": summary["next_recommended_target"],
        "artifact_paths": signal_artifact_paths(),
    }


def build_signal_fixture_bundle() -> dict[str, Any]:
    price_series = _build_sample_price_series()
    benchmark_series = _build_sample_benchmark_series()
    cases = _build_expected_math_cases()
    price_record = {
        "artifact_type": "signal_sample_price_series",
        "signal_engine_version": SIGNAL_ENGINE_VERSION,
        "series_count": len(price_series),
        "data_source_tier": "fixture_only",
        "real_history_used": False,
        "fixture_only": True,
        "not_real_signal_evidence": True,
        "paper_only": True,
        "live_blocked": True,
        "series": price_series,
    }
    benchmark_record = {
        "artifact_type": "signal_sample_benchmark_series",
        "signal_engine_version": SIGNAL_ENGINE_VERSION,
        "series_count": len(benchmark_series),
        "data_source_tier": "fixture_only",
        "real_history_used": False,
        "fixture_only": True,
        "not_real_signal_evidence": True,
        "paper_only": True,
        "live_blocked": True,
        "series": benchmark_series,
    }
    case_record = {
        "artifact_type": "signal_expected_math_cases",
        "signal_engine_version": SIGNAL_ENGINE_VERSION,
        "case_count": len(cases),
        "case_family_distribution": dict(sorted(Counter(case["case_family"] for case in cases).items())),
        "data_source_tier": "fixture_only",
        "real_history_used": False,
        "fixture_only": True,
        "not_real_signal_evidence": True,
        "paper_only": True,
        "live_blocked": True,
        "cases": cases,
    }
    price_record["reproducibility_hash"] = reproducibility_hash(price_record)
    benchmark_record["reproducibility_hash"] = reproducibility_hash(benchmark_record)
    case_record["reproducibility_hash"] = reproducibility_hash(case_record)
    return {
        "price_series": price_record,
        "benchmark_series": benchmark_record,
        "expected_cases": case_record,
    }


def signal_artifact_paths() -> dict[str, str]:
    return {
        "signal_engine_input_summary": str(SIGNAL_ENGINE_INPUT_SUMMARY_PATH),
        "momentum_signals": str(MOMENTUM_SIGNALS_PATH),
        "breakout_signals": str(BREAKOUT_SIGNALS_PATH),
        "fakeout_signals": str(FAKEOUT_SIGNALS_PATH),
        "trend_pullback_signals": str(TREND_PULLBACK_SIGNALS_PATH),
        "volatility_regime_signals": str(VOLATILITY_REGIME_SIGNALS_PATH),
        "relative_strength_signals": str(RELATIVE_STRENGTH_SIGNALS_PATH),
        "market_regime_signals": str(MARKET_REGIME_SIGNALS_PATH),
        "directional_setup_signals": str(DIRECTIONAL_SETUP_SIGNALS_PATH),
        "signal_quality_flags": str(SIGNAL_QUALITY_FLAGS_PATH),
        "signal_engine_summary": str(SIGNAL_ENGINE_SUMMARY_PATH),
        "signal_engine_proof": str(SIGNAL_ENGINE_PROOF_PATH),
        "sample_price_series": str(SAMPLE_PRICE_SERIES_PATH),
        "sample_benchmark_series": str(SAMPLE_BENCHMARK_SERIES_PATH),
        "signal_expected_math_cases": str(SIGNAL_EXPECTED_MATH_CASES_PATH),
        "signal_engine_report": str(SIGNAL_ENGINE_REPORT_PATH),
        "signal_engine_artifact_ledger": str(SIGNAL_ENGINE_LEDGER_PATH),
    }


def _compute_fixture_signals(
    cases: list[dict[str, Any]],
    series_by_symbol: dict[str, Any],
    benchmark_series: Any,
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {
        "momentum": [],
        "breakout": [],
        "fakeout": [],
        "trend_pullback": [],
        "volatility_regime": [],
        "relative_strength": [],
        "market_regime": [],
    }
    for case in cases:
        family = str(case["signal_family"])
        symbol = str(case["symbol"])
        series = series_by_symbol[symbol]
        signal_date = str(case["signal_date"])
        window = int(case["lookback_window"])
        if family == "momentum":
            signal = compute_momentum_signal(series, signal_date, window)
        elif family == "breakout":
            signal = compute_breakout_signal(series, signal_date, window)
        elif family == "fakeout":
            signal = compute_fakeout_signal(series, signal_date, window)
        elif family == "trend_pullback":
            signal = compute_trend_pullback_signal(series, signal_date, window)
        elif family == "volatility_regime":
            signal = compute_volatility_regime_signal(series, signal_date, window)
        elif family == "relative_strength":
            signal = compute_relative_strength_signal(series, benchmark_series, signal_date, window)
        elif family == "market_regime":
            signal = compute_market_regime_signal(series, signal_date, window)
        else:
            raise ValueError(f"unsupported fixture signal_family: {family}")
        signal_dict = signal.to_dict()
        signal_dict["fixture_case_id"] = case["case_id"]
        signal_dict["not_real_signal_evidence"] = True
        signal_dict["record_hash"] = stable_signal_hash(signal_dict)
        output[family].append(signal_dict)
    return output


def _fixture_signal_series(fixture_bundle: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for item in fixture_bundle["price_series"]["series"]:
        rows = item["bars"]
        bars = [
            make_price_bar(
                str(row["symbol"]),
                str(row["date"]),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["adjusted_close"]),
                int(row["volume"]),
                "fixture_only",
                False,
                True,
                True,
            )
            for row in rows
        ]
        output[str(item["symbol"])] = make_signal_series(str(item["symbol"]), bars, "fixture_only", False, True, True)
    return output


def _fixture_benchmark_series(fixture_bundle: dict[str, Any]) -> Any:
    item = fixture_bundle["benchmark_series"]["series"][0]
    bars = [
        make_price_bar(
            str(row["symbol"]),
            str(row["date"]),
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            float(row["adjusted_close"]),
            int(row["volume"]),
            "fixture_only",
            False,
            True,
            True,
        )
        for row in item["bars"]
    ]
    return make_signal_series(str(item["symbol"]), bars, "fixture_only", False, True, True)


def _build_sample_price_series() -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    series.append(_series_record("MOM_BULL", _trend_closes(90, 80.0, 0.85, 0.08), _constant_ranges(90, 0.45), _volumes(90, 1_000_000, 1_000)))
    series.append(_series_record("MOM_BEAR", _trend_closes(90, 160.0, -0.75, 0.08), _constant_ranges(90, 0.45), _volumes(90, 1_000_000, 1_000)))
    series.append(_series_record("BREAK_UP", _breakout_closes(True), _event_ranges(90, 0.45, 55, 64, 0.55), _event_volumes(90, 1_000_000, 55, 64, 1_900_000)))
    series.append(_series_record("BREAK_DOWN", _breakout_closes(False), _event_ranges(90, 0.45, 55, 64, 0.55), _event_volumes(90, 1_000_000, 55, 64, 1_900_000)))
    for index in range(1, 6):
        series.append(_series_record(f"FAKE_UP_{index:03d}", _fakeout_closes(True), _fakeout_ranges(True), _event_volumes(90, 1_000_000, 50, 51, 1_700_000)))
        series.append(_series_record(f"FAKE_DOWN_{index:03d}", _fakeout_closes(False), _fakeout_ranges(False), _event_volumes(90, 1_000_000, 50, 51, 1_700_000)))
        series.append(_series_record(f"PULL_UP_{index:03d}", _trend_closes(90, 82.0 + index, 0.55, 0.05), _event_ranges(90, 0.65, 60, 60, 8.0), _volumes(90, 1_100_000, 2_000)))
        series.append(_series_record(f"PULL_DOWN_{index:03d}", _trend_closes(90, 160.0 - index, -0.62, 0.05), _event_ranges(90, 0.65, 60, 60, 8.0), _volumes(90, 1_100_000, 2_000)))
    series.append(_series_record("VOL_EXP", _vol_expansion_closes(), _event_ranges(90, 0.20, 60, 89, 2.80), _volumes(90, 1_200_000, 3_000)))
    series.append(_series_record("VOL_COMP", _vol_compression_closes(), _vol_compression_ranges(), _volumes(90, 1_200_000, 3_000)))
    series.append(_series_record("RS_STRONG", _trend_closes(90, 100.0, 0.58, 0.04), _constant_ranges(90, 0.45), _volumes(90, 1_050_000, 1_000)))
    series.append(_series_record("RS_WEAK", _trend_closes(90, 110.0, -0.22, 0.04), _constant_ranges(90, 0.45), _volumes(90, 1_050_000, 1_000)))
    series.append(_series_record("REG_UP", _trend_closes(90, 100.0, 0.36, 0.03), _constant_ranges(90, 0.30), _volumes(90, 1_250_000, 1_000)))
    series.append(_series_record("REG_DOWN_HV", _regime_down_high_vol_closes(), _constant_ranges(90, 3.00), _volumes(90, 1_350_000, 2_000)))
    return series


def _build_sample_benchmark_series() -> list[dict[str, Any]]:
    return [
        _series_record("BENCH", _trend_closes(90, 100.0, 0.20, 0.02), _constant_ranges(90, 0.35), _volumes(90, 2_000_000, 1_000)),
    ]


def _build_expected_math_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for offset, index in enumerate(range(55, 60), start=1):
        cases.append(_case(f"momentum-bull-{offset:03d}", "momentum", "momentum", "MOM_BULL", index, 20, "bullish", "positive_momentum"))
        cases.append(_case(f"momentum-bear-{offset:03d}", "momentum", "momentum", "MOM_BEAR", index, 20, "bearish", "negative_momentum"))
    for offset, index in enumerate(range(55, 65), start=1):
        cases.append(_case(f"bullish-breakout-{offset:03d}", "bullish_breakout", "breakout", "BREAK_UP", index, 20, "bullish", "close_above_prior_high"))
        cases.append(_case(f"bearish-breakdown-{offset:03d}", "bearish_breakdown", "breakout", "BREAK_DOWN", index, 20, "bearish", "close_below_prior_low"))
    for index in range(1, 6):
        cases.append(_case(f"fakeout-up-{index:03d}", "fakeout", "fakeout", f"FAKE_UP_{index:03d}", 51, 20, "bearish", "close_back_inside_prior_range"))
        cases.append(_case(f"fakeout-down-{index:03d}", "fakeout", "fakeout", f"FAKE_DOWN_{index:03d}", 51, 20, "bullish", "close_back_inside_prior_range"))
        cases.append(_case(f"pullback-up-{index:03d}", "trend_pullback", "trend_pullback", f"PULL_UP_{index:03d}", 60, 20, "bullish", "continuation_confirmed"))
        cases.append(_case(f"pullback-down-{index:03d}", "trend_pullback", "trend_pullback", f"PULL_DOWN_{index:03d}", 60, 20, "bearish", "continuation_confirmed"))
    for offset, index in enumerate(range(65, 70), start=1):
        cases.append(_case(f"vol-expansion-{offset:03d}", "volatility_expansion_compression", "volatility_regime", "VOL_EXP", index, 20, "neutral", "volatility_expansion"))
    for offset, index in enumerate(range(75, 80), start=1):
        cases.append(_case(f"vol-compression-{offset:03d}", "volatility_expansion_compression", "volatility_regime", "VOL_COMP", index, 20, "neutral", "volatility_compression"))
    for offset, index in enumerate(range(55, 60), start=1):
        cases.append(_case(f"rs-strong-{offset:03d}", "relative_strength", "relative_strength", "RS_STRONG", index, 20, "bullish", "outperforming_benchmark"))
        cases.append(_case(f"rs-weak-{offset:03d}", "relative_strength", "relative_strength", "RS_WEAK", index, 20, "bearish", "underperforming_benchmark"))
    for offset, index in enumerate(range(70, 75), start=1):
        cases.append(_case(f"regime-up-{offset:03d}", "regime_classifier", "market_regime", "REG_UP", index, 20, "bullish", "trend_up"))
    for offset, index in enumerate(range(71, 80, 2), start=1):
        cases.append(_case(f"regime-down-high-vol-{offset:03d}", "regime_classifier", "market_regime", "REG_DOWN_HV", index, 20, "bearish", "trend_down"))
    if len(cases) != 80:
        raise ValueError(f"expected 80 signal fixture cases, got {len(cases)}")
    return cases


def _engine_quality_flags(history_dataset_status: str) -> list[dict[str, Any]]:
    flags = [
        _quality_flag_dict(
            "signal-fixture-only-math-validation",
            "warning",
            "fixture_math_validation_only",
            "signal outputs are deterministic fixture math validation, not real signal evidence",
            "fixture_only",
        ),
        _quality_flag_dict(
            "signal-no-real-edge-claim",
            "warning",
            "not_real_edge_evidence",
            "real OHLCV validation is missing; no trading edge, profitability, or live-readiness claim is allowed",
            "fixture_only",
        ),
    ]
    if history_dataset_status != "valid_real_dataset":
        flags.append(_quality_flag_dict(
            "signal-real-history-absent",
            "warning",
            "missing_real_history",
            "history spine did not provide a valid real dataset",
            "missing_real_history",
        ))
    return flags


def _quality_flag_dict(flag_id: str, severity: str, reason_code: str, message: str, data_source_tier: str) -> dict[str, Any]:
    record = SignalQualityFlag(
        artifact_type="signal_quality_flag",
        flag_id=flag_id,
        severity=severity,
        symbol="",
        signal_date="",
        signal_family="all",
        reason_code=reason_code,
        message=message,
        data_source_tier=data_source_tier,
        real_history_used=False,
        fixture_only=True,
        not_real_signal_evidence=True,
        paper_only=True,
        live_blocked=True,
        flag_hash="",
    )
    return record.to_dict()


def _series_record(symbol: str, closes: list[float], ranges: list[float], volumes: list[int]) -> dict[str, Any]:
    bars = []
    for index, close in enumerate(closes):
        previous_close = closes[index - 1] if index > 0 else close
        open_price = round((previous_close * 0.35) + (close * 0.65), 6)
        range_width = ranges[index]
        high = round(max(open_price, close) + range_width, 6)
        low = round(max(0.01, min(open_price, close) - range_width), 6)
        bar = make_price_bar(
            symbol,
            _date_at(index),
            open_price,
            high,
            low,
            close,
            close,
            volumes[index],
            "fixture_only",
            False,
            True,
            True,
        ).to_dict()
        bars.append(bar)
    return {
        "symbol": symbol,
        "bar_count": len(bars),
        "data_source_tier": "fixture_only",
        "real_history_used": False,
        "fixture_only": True,
        "not_real_signal_evidence": True,
        "bars": bars,
    }


def _case(
    case_id: str,
    case_family: str,
    signal_family: str,
    symbol: str,
    signal_index: int,
    lookback_window: int,
    expected_direction: str,
    expected_reason_code: str,
) -> dict[str, Any]:
    record = {
        "case_id": case_id,
        "case_family": case_family,
        "signal_family": signal_family,
        "symbol": symbol,
        "signal_date": _date_at(signal_index),
        "lookback_window": lookback_window,
        "expected_direction": expected_direction,
        "expected_reason_code": expected_reason_code,
        "data_source_tier": "fixture_only",
        "real_history_used": False,
        "fixture_only": True,
        "not_real_signal_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    record["case_hash"] = stable_signal_hash(record)
    return record


def _trend_closes(count: int, start: float, slope: float, cycle: float) -> list[float]:
    return [
        round(start + (index * slope) + ((index % 3) - 1) * cycle, 6)
        for index in range(count)
    ]


def _breakout_closes(bullish: bool) -> list[float]:
    closes = [round(100.0 + ((index % 5) - 2) * 0.12, 6) for index in range(90)]
    for index in range(55, 90):
        closes[index] = round((103.0 + ((index - 55) * 1.05)) if bullish else (97.0 - ((index - 55) * 1.05)), 6)
    return closes


def _fakeout_closes(bullish_attempt: bool) -> list[float]:
    closes = [round(100.0 + ((index % 4) - 1.5) * 0.18, 6) for index in range(90)]
    closes[50] = 103.4 if bullish_attempt else 96.6
    closes[51] = 100.25 if bullish_attempt else 99.75
    return closes


def _fakeout_ranges(bullish_attempt: bool) -> list[float]:
    ranges = _constant_ranges(90, 0.35)
    ranges[50] = 0.45
    ranges[51] = 0.40 if bullish_attempt else 0.40
    return ranges


def _vol_expansion_closes() -> list[float]:
    closes = [round(100.0 + index * 0.03, 6) for index in range(90)]
    for index in range(60, 90):
        direction = 1.0 if index % 2 == 0 else -1.0
        closes[index] = round(102.0 + ((index - 60) * 0.22) + (direction * (1.6 + ((index - 60) * 0.05))), 6)
    return closes


def _vol_compression_closes() -> list[float]:
    closes: list[float] = []
    for index in range(90):
        if index < 60:
            direction = 1.0 if index % 2 == 0 else -1.0
            closes.append(round(105.0 + direction * 2.2 + index * 0.02, 6))
        else:
            closes.append(round(106.0 + ((index % 3) - 1) * 0.04, 6))
    return closes


def _vol_compression_ranges() -> list[float]:
    return [
        2.5 if index < 60 else 0.18
        for index in range(90)
    ]


def _regime_down_high_vol_closes() -> list[float]:
    return [
        round(185.0 - (index * 0.72) + (2.2 if index % 2 == 0 else -2.2), 6)
        for index in range(90)
    ]


def _constant_ranges(count: int, value: float) -> list[float]:
    return [round(value, 6) for _ in range(count)]


def _event_ranges(count: int, base: float, start_index: int, end_index: int, event_value: float) -> list[float]:
    return [
        round(event_value if start_index <= index <= end_index else base, 6)
        for index in range(count)
    ]


def _volumes(count: int, start: int, step: int) -> list[int]:
    return [start + (index * step) for index in range(count)]


def _event_volumes(count: int, base: int, start_index: int, end_index: int, event_value: int) -> list[int]:
    return [
        event_value if start_index <= index <= end_index else base + (index * 500)
        for index in range(count)
    ]


def _family_distribution(family_records: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    return {
        family: len(records)
        for family, records in sorted(family_records.items())
    }


def _direction_distribution(family_records: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for records in family_records.values():
        for record in records:
            counter[str(record["direction"])] += 1
    return dict(sorted(counter.items()))


def _proof_record(summary: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "signal_engine_proof",
        "proof_id": "dopey-real-signal-engines-v1-proof",
        "signal_engine_version": SIGNAL_ENGINE_VERSION,
        "signal_engine_status": summary["signal_engine_status"],
        "history_dataset_status": summary["history_dataset_status"],
        "real_history_used": summary["real_history_used"],
        "fixture_only_case_count": summary["fixture_only_case_count"],
        "not_real_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_credentials": True,
        "no_scheduler": True,
        "no_real_sizing": True,
        "no_orders": True,
        "next_recommended_target": "DOPEY_HONEST_BACKTESTER_V1",
    }
    record["proof_hash"] = stable_signal_hash(record)
    return record


def _write_fixture_files(fixture_bundle: dict[str, Any]) -> None:
    SIGNAL_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(SAMPLE_PRICE_SERIES_PATH, fixture_bundle["price_series"])
    _write_json(SAMPLE_BENCHMARK_SERIES_PATH, fixture_bundle["benchmark_series"])
    _write_json(SIGNAL_EXPECTED_MATH_CASES_PATH, fixture_bundle["expected_cases"])


def _write_report(summary: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Real Signal Engines Report",
        "",
        "## Objective",
        "Build deterministic computed signal engines for offline long-call/long-put strategy research without broker access, credentials, live orders, real sizing, or market-data fetching.",
        "",
        "## Signal Families Implemented",
        "- momentum",
        "- breakout and breakdown",
        "- failed breakout / fakeout",
        "- trend pullback continuation",
        "- volatility expansion/compression",
        "- relative strength",
        "- market regime classifier",
        "- long-call/long-put directional setup mapper",
        "",
        "## Formulas And Definitions",
        "- momentum: weighted 5-day, 10-day, 20-day returns plus 20-day close slope.",
        "- breakout: close versus prior N-day high/low, with 20-day average-volume confirmation and distance score.",
        "- fakeout: prior bar outside the N-day range followed by the signal bar closing back inside that range.",
        "- trend pullback: 20-day and 50-day moving average trend state, moving-average touch, and continuation close confirmation.",
        "- volatility: annualized realized volatility from daily close returns, short/long realized-vol ratio, and rolling range compression.",
        "- relative strength: symbol N-day return minus benchmark N-day return, with missing-benchmark flags.",
        "- regime: trend state, volatility state, drawdown state, and risk proxy mapped to the fixed regime label set.",
        "- directional setup: bullish records map only to long-call candidates, bearish records map only to long-put candidates, neutral or low-confidence records map to no trade.",
        "",
        "## Data-Source Tier Policy",
        "- Allowed tiers: fixture_only, local_real_history, missing_real_history.",
        "- local_real_history is forbidden unless the history spine reports valid_real_dataset.",
        "- Fixture records are labeled fixture_only=true, real_history_used=false, not_real_signal_evidence=true.",
        "",
        "## Current Limitation",
        f"- history_dataset_status: `{summary['history_dataset_status']}`",
        f"- signal_engine_status: `{summary['signal_engine_status']}`",
        f"- real_history_used: `{str(summary['real_history_used']).lower()}`",
        "- The current run is math validation only and is not real signal evidence.",
        "",
        "## Sample Fixture Validation",
        f"- fixture_only_case_count: `{summary['fixture_only_case_count']}`",
        f"- signal_family_distribution: `{summary['signal_family_distribution']}`",
        f"- direction_distribution: `{summary['direction_distribution']}`",
        "",
        "## Long-Call / Long-Put Setup Mapping",
        f"- long_call_candidate_count: `{summary['long_call_candidate_count']}`",
        f"- long_put_candidate_count: `{summary['long_put_candidate_count']}`",
        f"- no_trade_count: `{summary['no_trade_count']}`",
        "- No spreads, short-volatility structures, naked selling, same-day churn, broker dependency, or real sizing are created.",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- broker_connection: `none`",
        "- credentials: `none`",
        "- scheduler: `none`",
        "- real_sizing: `none`",
        "- live_orders: `false`",
        "- not_real_edge_evidence: `true`",
        "",
        "## Validation Summary",
        "- Targeted tests are recorded in the session final status.",
        "- Full pytest timeout, if observed, remains inconclusive_timeout and is not a pass.",
        "",
        "## Limitations",
        "- No real OHLCV evidence exists while the history spine remains missing_real_dataset.",
        "- No profitability, edge, backtest validity, or live readiness is claimed.",
        "- Fixture series are toy math cases only.",
        "",
        "## Next Target",
        "- `DOPEY_HONEST_BACKTESTER_V1`",
    ]
    SIGNAL_ENGINE_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ledger(summary: dict[str, Any]) -> None:
    paths = signal_artifact_paths()
    lines = [
        "# DOPEY Real Signal Engines Artifact Ledger",
        "",
        "## Source Files",
        "- `dopey_analysis/signal_models.py`",
        "- `dopey_analysis/technical_signal_engine.py`",
        "- `dopey_analysis/history_signal_adapter.py`",
        "- `dopey_analysis/run_real_signal_engines.py`",
        "- `tests/test_real_signal_engines.py`",
        "",
        "## Fixture Files",
        f"- `{SAMPLE_PRICE_SERIES_PATH}` sha256=`{_file_sha256(SAMPLE_PRICE_SERIES_PATH)}`",
        f"- `{SAMPLE_BENCHMARK_SERIES_PATH}` sha256=`{_file_sha256(SAMPLE_BENCHMARK_SERIES_PATH)}`",
        f"- `{SIGNAL_EXPECTED_MATH_CASES_PATH}` sha256=`{_file_sha256(SIGNAL_EXPECTED_MATH_CASES_PATH)}`",
        "",
        "## Artifact Files",
    ]
    for key in [
        "signal_engine_input_summary",
        "momentum_signals",
        "breakout_signals",
        "fakeout_signals",
        "trend_pullback_signals",
        "volatility_regime_signals",
        "relative_strength_signals",
        "market_regime_signals",
        "directional_setup_signals",
        "signal_quality_flags",
        "signal_engine_summary",
        "signal_engine_proof",
    ]:
        path = Path(paths[key])
        lines.append(f"- `{path}` records=`{_record_count(path)}` sha256=`{_file_sha256(path)}`")
    lines.extend([
        "",
        "## Record Counts",
        f"- fixture_only_case_count: `{summary['fixture_only_case_count']}`",
        f"- local_real_history_case_count: `{summary['local_real_history_case_count']}`",
        f"- signal_family_distribution: `{summary['signal_family_distribution']}`",
        f"- direction_distribution: `{summary['direction_distribution']}`",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- not_real_edge_evidence: `true`",
        "- no broker, credentials, scheduler, real sizing, or orders created",
        "",
        "## Run Hash",
        f"- signal_engine_summary.run_hash: `{summary['run_hash']}`",
    ])
    SIGNAL_ENGINE_LEDGER_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_count(path: Path) -> int:
    if not path.exists():
        return 0
    if path.suffix.lower() == ".json":
        return 1
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def _date_at(index: int) -> str:
    return (date(2026, 1, 1) + timedelta(days=index)).isoformat()


def main() -> int:
    result = run_real_signal_engines()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
