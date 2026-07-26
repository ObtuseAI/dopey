"""Compute DOPEY signal families over validated real OHLCV history.

This is the real-data lane of the signal engines. It consumes hash-pinned
local real history through the history spine adapter (never fixtures, never
network) and computes the same signal families the fixture lane validates,
producing dated, symbol-level directional setups for the honest backtester.

Leak policy: every signal at signal_date uses bars up to and including
signal_date only (enforced by technical_signal_engine._bars_through_date).
Paper-only, live-blocked, long-call/long-put/no-trade universe.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR

from .history_signal_adapter import HISTORY_SPINE_SUMMARY_PATH, load_default_history_signal_input
from .signal_models import SIGNAL_ENGINE_VERSION, make_signal_series
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
SIGNAL_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "signals"
MOMENTUM_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "momentum_signals.jsonl"
BREAKOUT_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "breakout_signals.jsonl"
FAKEOUT_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "fakeout_signals.jsonl"
TREND_PULLBACK_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "trend_pullback_signals.jsonl"
VOLATILITY_REGIME_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "volatility_regime_signals.jsonl"
RELATIVE_STRENGTH_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "relative_strength_signals.jsonl"
MARKET_REGIME_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "market_regime_signals.jsonl"
DIRECTIONAL_SETUP_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "directional_setup_signals.jsonl"
FRESH_DIRECTIONAL_SETUP_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "directional_setup_signals_fresh.jsonl"
REAL_SIGNAL_ENGINE_SUMMARY_PATH = SIGNAL_ARTIFACT_DIR / "real_history_signal_engine_summary.json"
REAL_SIGNAL_ENGINE_PROOF_PATH = SIGNAL_ARTIFACT_DIR / "real_history_signal_engine_proof.jsonl"
REAL_SIGNAL_ENGINE_REPORT_PATH = REPORTS_DIR / "DOPEY_REAL_HISTORY_SIGNAL_ENGINE_REPORT.md"

INCREMENTAL_STATE_PATH = SIGNAL_ARTIFACT_DIR / "real_signal_engine_incremental_state.json"
INCREMENTAL_STATE_VERSION = "dopey-real-signal-incremental-v1"

EVALUATION_START_DATE = "2015-01-01"
# 3 (was 10): the forward walk is signal-supply-bound - at cadence 10 the
# 100-trade evidence sample needs ~6 weeks; at 3 it needs ~2. Signals stay
# leak-free (bars <= t only); denser emission just means more ex-ante bets.
# Backtest trades overlap more temporally; per-cohort stats remain the unit.
EVALUATION_CADENCE_TRADING_DAYS = 3
LOOKBACK_WINDOW = 20
BENCHMARK_SYMBOL = "SPY"
CONTEXT_ONLY_SYMBOLS: frozenset[str] = frozenset({"VIX"})

FAMILY_COMPUTERS = (
    ("momentum", compute_momentum_signal),
    ("breakout", compute_breakout_signal),
    ("fakeout", compute_fakeout_signal),
    ("trend_pullback", compute_trend_pullback_signal),
    ("volatility_regime", compute_volatility_regime_signal),
    ("market_regime", compute_market_regime_signal),
)


FAMILY_ARTIFACT_PATHS = {
    "momentum": MOMENTUM_SIGNALS_PATH,
    "breakout": BREAKOUT_SIGNALS_PATH,
    "fakeout": FAKEOUT_SIGNALS_PATH,
    "trend_pullback": TREND_PULLBACK_SIGNALS_PATH,
    "volatility_regime": VOLATILITY_REGIME_SIGNALS_PATH,
    "relative_strength": RELATIVE_STRENGTH_SIGNALS_PATH,
    "market_regime": MARKET_REGIME_SIGNALS_PATH,
}


def run_real_history_signal_engine() -> dict[str, Any]:
    """Compute (or incrementally extend) the signal families over real history.

    Appending a session never shifts prior evaluation dates (the cadence grid
    is positional, anchored at the start), so when the incremental state
    proves each symbol's prior grid is an exact prefix of today's grid, only
    NEW evaluation dates are computed and appended - identical output to a
    full recompute at a fraction of the cost. Any mismatch (engine version,
    cadence, lookback, revised history, shrunk series) fails closed into the
    full recompute.
    """
    history_spine_summary = _load_json(HISTORY_SPINE_SUMMARY_PATH)
    history_spine_hash = str(history_spine_summary.get("reproducibility_hash", ""))
    reusable = _reusable_summary(history_spine_hash)
    if reusable is not None:
        return reusable
    history_input = load_default_history_signal_input()
    if not history_input.real_history_used:
        summary = _blocked_summary(history_input.history_dataset_status)
        _write_json(REAL_SIGNAL_ENGINE_SUMMARY_PATH, summary)
        return summary
    series_by_symbol = {
        symbol: make_signal_series(symbol, bars, "local_real_history", True, False, False)
        for symbol, bars in history_input.series_by_symbol.items()
        if bars
    }
    benchmark = series_by_symbol.get(BENCHMARK_SYMBOL)
    state = _load_json(INCREMENTAL_STATE_PATH) if INCREMENTAL_STATE_PATH.exists() else {}
    plan = _incremental_plan(state, series_by_symbol)
    if plan is not None:
        return _incremental_append(
            plan, state, series_by_symbol, benchmark, history_input, history_spine_hash
        )
    return _full_recompute(series_by_symbol, benchmark, history_input, history_spine_hash)


def _compute_signal_records(
    series_by_symbol: dict[str, Any],
    benchmark: Any,
    dates_by_symbol: dict[str, list[str]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], int]:
    """The single compute core: identical for full and incremental passes."""
    family_records: dict[str, list[dict[str, Any]]] = {name: [] for name, _ in FAMILY_COMPUTERS}
    family_records["relative_strength"] = []
    directional: list[dict[str, Any]] = []
    evaluated_points = 0
    for symbol in sorted(dates_by_symbol):
        series = series_by_symbol[symbol]
        for signal_date in dates_by_symbol[symbol]:
            evaluated_points += 1
            per_point: list[dict[str, Any]] = []
            for family_name, computer in FAMILY_COMPUTERS:
                record = computer(series, signal_date, LOOKBACK_WINDOW).to_dict()
                family_records[family_name].append(record)
                per_point.append(record)
            rs_record = compute_relative_strength_signal(
                series,
                benchmark if symbol != BENCHMARK_SYMBOL else None,
                signal_date,
                LOOKBACK_WINDOW,
            ).to_dict()
            family_records["relative_strength"].append(rs_record)
            per_point.append(rs_record)
            directional.extend(
                map_directional_setup_signal(record).to_dict() for record in per_point
            )
    return family_records, directional, evaluated_points


def _directional_totals(directional: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "long_call_candidate_count": sum(1 for r in directional if r["long_call_candidate"]),
        "long_put_candidate_count": sum(1 for r in directional if r["long_put_candidate"]),
        "no_trade_count": sum(1 for r in directional if r["no_trade"]),
        "direction_distribution": dict(Counter(r["direction"] for r in directional)),
    }


def _eval_dates_prefix_hash(dates: list[str], count: int) -> str:
    import hashlib

    return hashlib.sha256(",".join(dates[:count]).encode("utf-8")).hexdigest()


def _incremental_plan(
    state: dict[str, Any],
    series_by_symbol: dict[str, Any],
) -> dict[str, list[str]] | None:
    """dates-to-compute per symbol, or None when only a full recompute is honest."""
    if state.get("state_version") != INCREMENTAL_STATE_VERSION:
        return None
    grid = state.get("grid", {})
    if (
        grid.get("engine_version") != SIGNAL_ENGINE_VERSION
        or grid.get("cadence") != EVALUATION_CADENCE_TRADING_DAYS
        or grid.get("lookback") != LOOKBACK_WINDOW
        or grid.get("evaluation_start_date") != EVALUATION_START_DATE
    ):
        return None
    per_symbol = state.get("per_symbol", {})
    if not isinstance(per_symbol, dict) or not per_symbol:
        return None
    tracked_symbols = set(per_symbol) - CONTEXT_ONLY_SYMBOLS
    current_symbols = set(series_by_symbol) - CONTEXT_ONLY_SYMBOLS
    if tracked_symbols - current_symbols:
        # Appending cannot remove stale rows for a departed symbol from the
        # seven family ledgers. Force a full rewrite so removed symbols stop
        # participating in downstream backtests.
        return None
    plan: dict[str, list[str]] = {}
    for symbol, series in series_by_symbol.items():
        if symbol in CONTEXT_ONLY_SYMBOLS:
            continue
        dates = _evaluation_dates(series)
        prior = per_symbol.get(symbol)
        if prior is None:
            plan[symbol] = dates  # new symbol: full history is "new"
            continue
        count = int(prior.get("eval_date_count", -1))
        if count < 0 or len(dates) < count:
            return None  # shrunk series = revised history: fail closed
        if _eval_dates_prefix_hash(dates, count) != str(prior.get("eval_dates_prefix_hash", "")):
            return None  # grid shifted = revised history: fail closed
        plan[symbol] = dates[count:]
    return plan


def _incremental_state(
    series_by_symbol: dict[str, Any],
    totals: dict[str, Any],
    prior_per_symbol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    per_symbol = dict(prior_per_symbol or {})
    for symbol, series in series_by_symbol.items():
        if symbol in CONTEXT_ONLY_SYMBOLS:
            continue
        dates = _evaluation_dates(series)
        per_symbol[symbol] = {
            "eval_date_count": len(dates),
            "eval_dates_prefix_hash": _eval_dates_prefix_hash(dates, len(dates)),
            "max_eval_date": dates[-1] if dates else "",
        }
    return {
        "artifact_type": "real_signal_engine_incremental_state",
        "state_version": INCREMENTAL_STATE_VERSION,
        "grid": {
            "engine_version": SIGNAL_ENGINE_VERSION,
            "cadence": EVALUATION_CADENCE_TRADING_DAYS,
            "lookback": LOOKBACK_WINDOW,
            "evaluation_start_date": EVALUATION_START_DATE,
        },
        "per_symbol": per_symbol,
        "totals": totals,
    }


def _merged_totals(prior: dict[str, Any], new_family: dict[str, list[dict[str, Any]]],
                   new_directional: list[dict[str, Any]], new_points: int) -> dict[str, Any]:
    new_dir = _directional_totals(new_directional)
    distribution = Counter(prior.get("direction_distribution", {}))
    distribution.update(new_dir["direction_distribution"])
    family_counts = dict(prior.get("family_signal_counts", {}))
    for name, records in new_family.items():
        family_counts[name] = int(family_counts.get(name, 0)) + len(records)
    return {
        "evaluation_point_count": int(prior.get("evaluation_point_count", 0)) + new_points,
        "family_signal_counts": family_counts,
        "directional_setup_count": int(prior.get("directional_setup_count", 0)) + len(new_directional),
        "long_call_candidate_count": int(prior.get("long_call_candidate_count", 0)) + new_dir["long_call_candidate_count"],
        "long_put_candidate_count": int(prior.get("long_put_candidate_count", 0)) + new_dir["long_put_candidate_count"],
        "no_trade_count": int(prior.get("no_trade_count", 0)) + new_dir["no_trade_count"],
        "direction_distribution": dict(sorted(distribution.items())),
    }


def _incremental_append(
    plan: dict[str, list[str]],
    state: dict[str, Any],
    series_by_symbol: dict[str, Any],
    benchmark: Any,
    history_input: Any,
    history_spine_hash: str,
) -> dict[str, Any]:
    active_plan = {symbol: dates for symbol, dates in plan.items() if dates}
    family_records, directional, evaluated_points = _compute_signal_records(
        series_by_symbol, benchmark, active_plan
    )
    SIGNAL_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for name, path in FAMILY_ARTIFACT_PATHS.items():
        _append_jsonl(path, family_records[name])
    _append_jsonl(DIRECTIONAL_SETUP_SIGNALS_PATH, directional)
    prior_fresh = _load_jsonl(FRESH_DIRECTIONAL_SETUP_SIGNALS_PATH)
    fresh_directional = _fresh_directional_records(prior_fresh + directional)
    _write_jsonl(FRESH_DIRECTIONAL_SETUP_SIGNALS_PATH, fresh_directional)
    totals = _merged_totals(state.get("totals", {}), family_records, directional, evaluated_points)
    new_state = _incremental_state(series_by_symbol, totals, state.get("per_symbol", {}))
    _write_json(INCREMENTAL_STATE_PATH, new_state)
    incremental_meta = {
        "signal_engine_mode": "incremental_append",
        "incremental_new_evaluation_points": evaluated_points,
        "incremental_new_directional_count": len(directional),
        "incremental_symbols_extended": sorted(active_plan),
        "incremental_policy": "append_only_when_prior_grid_is_exact_prefix_else_full_recompute",
    }
    return _finalize_summary(
        totals, series_by_symbol, history_input, history_spine_hash,
        len(fresh_directional), incremental_meta,
    )


def _full_recompute(
    series_by_symbol: dict[str, Any],
    benchmark: Any,
    history_input: Any,
    history_spine_hash: str,
) -> dict[str, Any]:
    dates_by_symbol = {
        symbol: _evaluation_dates(series)
        for symbol, series in series_by_symbol.items()
        if symbol not in CONTEXT_ONLY_SYMBOLS
    }
    family_records, directional, evaluated_points = _compute_signal_records(
        series_by_symbol, benchmark, dates_by_symbol
    )
    SIGNAL_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for name, path in FAMILY_ARTIFACT_PATHS.items():
        _write_jsonl(path, family_records[name])
    _write_jsonl(DIRECTIONAL_SETUP_SIGNALS_PATH, directional)
    fresh_directional = _fresh_directional_records(directional)
    _write_jsonl(FRESH_DIRECTIONAL_SETUP_SIGNALS_PATH, fresh_directional)
    totals = _merged_totals({}, family_records, directional, evaluated_points)
    _write_json(INCREMENTAL_STATE_PATH, _incremental_state(series_by_symbol, totals))
    return _finalize_summary(
        totals, series_by_symbol, history_input, history_spine_hash,
        len(fresh_directional), {"signal_engine_mode": "full_recompute"},
    )


def _finalize_summary(
    totals: dict[str, Any],
    series_by_symbol: dict[str, Any],
    history_input: Any,
    history_spine_hash: str,
    fresh_count: int,
    mode_meta: dict[str, Any],
) -> dict[str, Any]:
    summary = {
        "artifact_type": "real_history_signal_engine_summary",
        "signal_engine_version": SIGNAL_ENGINE_VERSION,
        "signal_engine_status": "local_real_history_signals_computed",
        "history_dataset_status": history_input.history_dataset_status,
        "history_spine_reproducibility_hash": history_spine_hash,
        "real_history_used": True,
        "data_source_tier": "local_real_history",
        "evaluation_start_date": EVALUATION_START_DATE,
        "evaluation_cadence_trading_days": EVALUATION_CADENCE_TRADING_DAYS,
        "lookback_window": LOOKBACK_WINDOW,
        "benchmark_symbol": BENCHMARK_SYMBOL,
        "context_only_symbols": sorted(CONTEXT_ONLY_SYMBOLS),
        "symbols_evaluated": sorted(
            symbol for symbol in series_by_symbol if symbol not in CONTEXT_ONLY_SYMBOLS
        ),
        "evaluation_point_count": totals["evaluation_point_count"],
        "family_signal_counts": dict(sorted(totals["family_signal_counts"].items())),
        "directional_setup_count": totals["directional_setup_count"],
        "fresh_directional_setup_count": fresh_count,
        "long_call_candidate_count": totals["long_call_candidate_count"],
        "long_put_candidate_count": totals["long_put_candidate_count"],
        "no_trade_count": totals["no_trade_count"],
        "direction_distribution": dict(sorted(totals["direction_distribution"].items())),
        **mode_meta,
        "leak_policy": "signals_use_bars_through_signal_date_only",
        "fixture_only": False,
        "not_real_signal_evidence": False,
        "real_option_chain_used": False,
        "paper_only": True,
        "live_blocked": True,
        "no_network_market_data": True,
        "artifact_paths": {
            "directional_setup_signals": str(DIRECTIONAL_SETUP_SIGNALS_PATH),
            "fresh_directional_setup_signals": str(FRESH_DIRECTIONAL_SETUP_SIGNALS_PATH),
            "real_history_signal_engine_summary": str(REAL_SIGNAL_ENGINE_SUMMARY_PATH),
        },
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    _write_json(REAL_SIGNAL_ENGINE_SUMMARY_PATH, summary)
    _write_jsonl(REAL_SIGNAL_ENGINE_PROOF_PATH, [_proof(summary)])
    _write_report(summary)
    return summary


def _reusable_summary(history_spine_hash: str) -> dict[str, Any] | None:
    required_outputs = (
        MOMENTUM_SIGNALS_PATH,
        BREAKOUT_SIGNALS_PATH,
        FAKEOUT_SIGNALS_PATH,
        TREND_PULLBACK_SIGNALS_PATH,
        VOLATILITY_REGIME_SIGNALS_PATH,
        RELATIVE_STRENGTH_SIGNALS_PATH,
        MARKET_REGIME_SIGNALS_PATH,
        DIRECTIONAL_SETUP_SIGNALS_PATH,
        FRESH_DIRECTIONAL_SETUP_SIGNALS_PATH,
    )
    if not history_spine_hash or not REAL_SIGNAL_ENGINE_SUMMARY_PATH.exists():
        return None
    previous = _load_json(REAL_SIGNAL_ENGINE_SUMMARY_PATH)
    if previous.get("history_spine_reproducibility_hash") != history_spine_hash:
        return None
    if not all(path.is_file() and path.stat().st_size > 0 for path in required_outputs):
        return None
    return {
        **previous,
        "signal_engine_status": "current_history_signals_reused",
        "cached_signal_engine_status": previous.get("signal_engine_status", ""),
        "cache_policy": "reuse_only_when_history_spine_hash_and_every_signal_artifact_match",
    }


def _fresh_directional_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid_dates = [
        date.fromisoformat(str(record["signal_date"]))
        for record in records
        if str(record.get("signal_date", ""))
    ]
    if not valid_dates:
        return []
    cutoff = max(valid_dates) - timedelta(days=7)
    return [
        record
        for record in records
        if str(record.get("signal_date", ""))
        and date.fromisoformat(str(record["signal_date"])) >= cutoff
    ]


def adopt_current_signal_generation() -> dict[str, Any]:
    history_summary = _load_json(HISTORY_SPINE_SUMMARY_PATH)
    signal_summary = _load_json(REAL_SIGNAL_ENGINE_SUMMARY_PATH)
    history_hash = str(history_summary.get("reproducibility_hash", ""))
    history_end_date = str(history_summary.get("date_range", {}).get("end_date", ""))
    required_outputs = (
        MOMENTUM_SIGNALS_PATH,
        BREAKOUT_SIGNALS_PATH,
        FAKEOUT_SIGNALS_PATH,
        TREND_PULLBACK_SIGNALS_PATH,
        VOLATILITY_REGIME_SIGNALS_PATH,
        RELATIVE_STRENGTH_SIGNALS_PATH,
        MARKET_REGIME_SIGNALS_PATH,
        DIRECTIONAL_SETUP_SIGNALS_PATH,
    )
    if not history_hash or not history_end_date:
        raise RuntimeError("history spine is missing its reproducibility hash or end date")
    if signal_summary.get("signal_engine_status") != "local_real_history_signals_computed":
        raise RuntimeError(
            "only a completed real-history signal generation can be adopted: "
            f"status={signal_summary.get('signal_engine_status')}"
        )
    if not all(path.is_file() and path.stat().st_size > 0 for path in required_outputs):
        raise RuntimeError("one or more required signal outputs are missing or empty")
    if REAL_SIGNAL_ENGINE_SUMMARY_PATH.stat().st_mtime < HISTORY_SPINE_SUMMARY_PATH.stat().st_mtime:
        raise RuntimeError("signal summary predates the current history generation")
    cutoff = date.fromisoformat(history_end_date) - timedelta(days=7)
    fresh_records: list[dict[str, Any]] = []
    with DIRECTIONAL_SETUP_SIGNALS_PATH.open("r", encoding="utf-8") as signal_file:
        for line_number, line in enumerate(signal_file, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise TypeError(
                    "directional signal row must be an object during cache adoption: "
                    f"line={line_number}"
                )
            signal_date = str(record.get("signal_date", ""))
            if signal_date and date.fromisoformat(signal_date) >= cutoff:
                fresh_records.append(record)
    _write_jsonl(FRESH_DIRECTIONAL_SETUP_SIGNALS_PATH, fresh_records)
    adopted = {
        **{key: value for key, value in signal_summary.items() if key != "reproducibility_hash"},
        "history_spine_reproducibility_hash": history_hash,
        "fresh_directional_setup_count": len(fresh_records),
        "artifact_paths": {
            **dict(signal_summary.get("artifact_paths", {})),
            "fresh_directional_setup_signals": str(FRESH_DIRECTIONAL_SETUP_SIGNALS_PATH),
        },
        "cache_adoption_policy": "adopt_only_completed_signal_generation_newer_than_hash_pinned_history_summary",
    }
    adopted["reproducibility_hash"] = reproducibility_hash(adopted)
    _write_json(REAL_SIGNAL_ENGINE_SUMMARY_PATH, adopted)
    return adopted


def _evaluation_dates(series: Any) -> list[str]:
    dates = [bar.date for bar in series.bars]
    eligible = [
        (index, value)
        for index, value in enumerate(dates)
        if value >= EVALUATION_START_DATE and index >= LOOKBACK_WINDOW
    ]
    return [value for position, (index, value) in enumerate(eligible) if position % EVALUATION_CADENCE_TRADING_DAYS == 0]


def _blocked_summary(history_dataset_status: str) -> dict[str, Any]:
    summary = {
        "artifact_type": "real_history_signal_engine_summary",
        "signal_engine_version": SIGNAL_ENGINE_VERSION,
        "signal_engine_status": "blocked_missing_valid_real_history",
        "history_dataset_status": history_dataset_status,
        "real_history_used": False,
        "directional_setup_count": 0,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary


def _proof(summary: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "real_history_signal_engine_proof",
        "proof_id": "real-history-signal-engine-proof-v1",
        "signal_engine_status": summary["signal_engine_status"],
        "real_history_used": summary["real_history_used"],
        "evaluation_point_count": summary["evaluation_point_count"],
        "directional_setup_count": summary["directional_setup_count"],
        "long_call_candidate_count": summary["long_call_candidate_count"],
        "long_put_candidate_count": summary["long_put_candidate_count"],
        "no_trade_count": summary["no_trade_count"],
        "network_fetch_performed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["proof_hash"] = reproducibility_hash(record)
    return record


def _write_report(summary: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Real History Signal Engine Report",
        "",
        "## Objective",
        "Compute the DOPEY signal families over validated, hash-pinned local real OHLCV history and emit dated directional setups for the honest backtester.",
        "",
        "## Data Source",
        f"- history_dataset_status: `{summary['history_dataset_status']}`",
        f"- real_history_used: `{str(summary['real_history_used']).lower()}`",
        "- data_source_tier: `local_real_history`",
        "- No fixtures, no synthetic rows, no network market data.",
        "",
        "## Evaluation Grid",
        f"- evaluation_start_date: `{summary['evaluation_start_date']}`",
        f"- cadence: every `{summary['evaluation_cadence_trading_days']}` trading days",
        f"- lookback_window: `{summary['lookback_window']}`",
        f"- benchmark_symbol: `{summary['benchmark_symbol']}`",
        f"- context_only_symbols (no options signals): `{summary['context_only_symbols']}`",
        f"- symbols_evaluated: `{len(summary['symbols_evaluated'])}`",
        f"- evaluation_point_count: `{summary['evaluation_point_count']}`",
        "",
        "## Leak Policy",
        "- Signals at a date use bars through that date only.",
        "",
        "## Output",
        f"- directional_setup_count: `{summary['directional_setup_count']}`",
        f"- long_call_candidate_count: `{summary['long_call_candidate_count']}`",
        f"- long_put_candidate_count: `{summary['long_put_candidate_count']}`",
        f"- no_trade_count: `{summary['no_trade_count']}`",
        "",
        "## Boundaries",
        "- Signals are research inputs, not edge evidence, profitability, or live readiness.",
        "- paper_only: `true`; live_blocked: `true`.",
    ]
    REAL_SIGNAL_ENGINE_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"signal JSON dependency must be an object: path={path}")
    return value


def _append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Append with rollback: a failed write truncates back to the original size
    so a torn trailing line can never corrupt the artifact (the market_structure
    UnicodeDecodeError incident class)."""
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n" for record in records
    )
    import os

    with path.open("a", encoding="utf-8") as handle:
        original_size = handle.tell()
        try:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        except Exception:
            handle.flush()
            handle.truncate(original_size)
            raise


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise TypeError(f"jsonl row must be an object: path={path}, line={line_number}")
        records.append(record)
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
