"""Shared helpers for DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from dopey_autonomy.public_champion_common import (
    ARTIFACT_ROOT,
    CHAMPION_ROOT,
    EVOLUTION_ROOT,
    LIVE_GATE_ROOT,
    OPTIONS_ENGINE_ROOT,
    SCOREBOARD_ROOT,
    SIGNAL_ROOT,
    TOURNAMENT_ROOT,
    date_from_text,
    is_test_symbol,
    max_drawdown,
    pnl_metrics,
    profit_factor,
    read_json_file,
    read_jsonl_file,
    record_with_hash,
    safe_float,
    sector_for_symbol,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_wealth_engine.common import REPO_ROOT, stable_hash


HARDENING_VERSION = "dopey-public-paper-champion-hardening-and-deep-stress-v1"
HARDENING_ROOT = ARTIFACT_ROOT / "champion_hardening"
TEST_SYMBOL_PREFIXES = ("SIM", "TEST", "FIXTURE", "SYNTH")

TRADES_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v4_trades.jsonl"
LEADERBOARD_PATH = TOURNAMENT_ROOT / "public_cohort_tournament_leaderboard_v4.jsonl"
GATE_SUMMARY_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_summary.json"
GATE_RESULTS_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_results.jsonl"
SCOREBOARD_V4_PATH = SCOREBOARD_ROOT / "public_signal_deepening_scoreboard_v4.json"
LIVE_GATE_V2_PATH = LIVE_GATE_ROOT / "public_signal_deepening_live_gate_status_v2.json"
SIGNAL_CANDIDATES_PATH = SIGNAL_ROOT / "public_signal_mutation_candidates_v4.jsonl"

CORE_MIN_PROFIT_FACTOR = 1.10
CORE_MIN_EXPECTANCY = 0.0
CORE_MAX_DRAWDOWN_ABS = 2500.0
HOLDOUT_SURVIVAL_RATE = 0.65


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hardening_proof_record(proof_id: str, status: str, payload: dict[str, object]) -> dict[str, object]:
    record = {
        "artifact_type": "public_champion_hardening_proof",
        "proof_id": proof_id,
        "status": status,
        "timestamp": utc_now_iso(),
        "bundle_version": HARDENING_VERSION,
        "payload": dict(payload),
        "paper_only": True,
        "live_blocked": True,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "real_orders_placed": False,
        "live_trading_enabled": False,
        "official_robinhood_market_data_allowed": True,
        "unofficial_robinhood_api_blocked": True,
        "robinhood_scraping_blocked": True,
        "robinhood_reverse_auth_blocked": True,
        "robinhood_live_trading_enabled": False,
    }
    return record_with_hash(record, "proof_hash")


def live_safety_fields() -> dict[str, object]:
    return {
        "paper_only": True,
        "public_data_only": True,
        "fixture_champion_count": 0,
        "credentials_created": False,
        "env_created": False,
        "credentials_present": False,
        "broker_connection_used": False,
        "broker_connection_enabled": False,
        "real_orders_placed": False,
        "real_order_enabled": False,
        "live_trading_enabled": False,
        "live_blocked": True,
        "official_robinhood_market_data_allowed": True,
        "unofficial_robinhood_api_blocked": True,
        "robinhood_scraping_blocked": True,
        "robinhood_reverse_auth_blocked": True,
        "robinhood_live_trading_enabled": False,
    }


def robinhood_policy_fields() -> dict[str, object]:
    return {
        "official_robinhood_market_data_allowed": True,
        "unofficial_robinhood_api_blocked": True,
        "robinhood_scraping_blocked": True,
        "robinhood_reverse_auth_blocked": True,
        "robinhood_live_trading_enabled": False,
    }


def load_champion_gate_summary() -> dict[str, object]:
    return read_json_file(GATE_SUMMARY_PATH)


def load_champion_gate_results() -> list[dict[str, object]]:
    return read_jsonl_file(GATE_RESULTS_PATH)


def load_public_trades() -> list[dict[str, object]]:
    trades = read_jsonl_file(TRADES_PATH)
    return [
        trade for trade in trades
        if str(trade.get("market_data_source_type", "")).startswith("public")
        and str(trade.get("trade_intent", "")) in {"long_call", "long_put"}
        and not is_test_symbol(str(trade.get("symbol", "")))
    ]


def champion_records() -> list[dict[str, object]]:
    return [
        result for result in load_champion_gate_results()
        if bool(result.get("public_data_paper_champion", False))
    ]


def trades_for_champion(champion: dict[str, object], trades: list[dict[str, object]]) -> list[dict[str, object]]:
    level = str(champion.get("cohort_level", "variant_id"))
    cohort_id = str(champion.get("cohort_id", ""))
    return [trade for trade in trades if str(trade.get(level, "")) == cohort_id]


def simv2_rows_in_artifact(path) -> int:
    path_obj = Path(path) if not isinstance(path, Path) else path
    if not path_obj.exists() or path_obj.suffix.lower() != ".jsonl":
        return 0
    count = 0
    for record in read_jsonl_file(path_obj):
        symbol = str(record.get("symbol", "")).upper()
        if any(symbol.startswith(prefix) for prefix in TEST_SYMBOL_PREFIXES):
            count += 1
    return count


def decision_artifacts_simv2_counts() -> dict[str, int]:
    paths = {
        "v4_trades": TRADES_PATH,
        "tournament": LEADERBOARD_PATH,
        "champion_gate": GATE_RESULTS_PATH,
        "scoreboard": SCOREBOARD_V4_PATH,
    }
    return {name: simv2_rows_in_artifact(path) for name, path in paths.items()}


def stress_case_definitions() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for label, multiplier, core in [
        ("slippage_baseline", 1.0, True),
        ("slippage_1_5x", 1.5, True),
        ("slippage_2_0x", 2.0, True),
        ("slippage_3_0x", 3.0, False),
    ]:
        cases.append({"stress_id": label, "stress_family": "slippage", "core": core, "multiplier": multiplier})
    for label, factor, core in [
        ("theta_baseline", 1.0, True),
        ("theta_accelerated", 1.75, True),
        ("theta_last_third_dte_penalty", 2.5, True),
        ("theta_hold_too_long_penalty", 3.0, False),
    ]:
        cases.append({"stress_id": label, "stress_family": "theta", "core": core, "multiplier": factor})
    for label, shock, core in [
        ("iv_minus_10pct", 0.10, True),
        ("iv_minus_25pct", 0.25, True),
        ("iv_minus_40pct", 0.40, False),
        ("iv_crush_after_entry", 0.35, True),
        ("iv_spike_against_position", 0.30, True),
    ]:
        cases.append({"stress_id": label, "stress_family": "iv_shock", "core": core, "shock": shock})
    for label, pct, core in [
        ("entry_degrade_0_25pct", 0.0025, True),
        ("entry_degrade_0_50pct", 0.0050, True),
        ("entry_degrade_1_00pct", 0.0100, False),
    ]:
        cases.append({"stress_id": label, "stress_family": "entry_degradation", "core": core, "pct": pct})
    for label, pct, core in [
        ("exit_degrade_0_25pct", 0.0025, True),
        ("exit_degrade_0_50pct", 0.0050, True),
        ("exit_degrade_1_00pct", 0.0100, False),
    ]:
        cases.append({"stress_id": label, "stress_family": "exit_degradation", "core": core, "pct": pct})
    for label, core in [
        ("gap_overnight_against", True),
        ("gap_high_low_adverse_fill", True),
    ]:
        cases.append({"stress_id": label, "stress_family": "gap_stress", "core": core})
    for label, count, core in [
        ("outlier_remove_best_1", 1, True),
        ("outlier_remove_best_3", 3, True),
        ("outlier_remove_top_5pct", 0, True),
    ]:
        cases.append({"stress_id": label, "stress_family": "outlier_removal", "core": core, "count": count})
    for label, core in [
        ("concentration_remove_best_symbol", True),
        ("concentration_remove_best_sector", True),
        ("concentration_remove_best_regime", True),
    ]:
        cases.append({"stress_id": label, "stress_family": "concentration", "core": core})
    for label, months, core in [
        ("recent_last_12_months", 12, True),
        ("recent_last_24_months", 24, True),
        ("recent_2025_2026_only", 0, False),
    ]:
        cases.append({"stress_id": label, "stress_family": "recent_only", "core": core, "months": months})
    for label, regime, core in [
        ("regime_high_volatility_only", "high_volatility", False),
        ("regime_low_volatility_only", "low_volatility", False),
        ("regime_bull_trend_only", "uptrend", False),
        ("regime_bear_trend_only", "downtrend", False),
        ("regime_sideways_only", "sideways", False),
    ]:
        cases.append({"stress_id": label, "stress_family": "regime_specific", "core": core, "regime": regime})
    return cases


def holdout_definitions() -> list[dict[str, object]]:
    return [
        {"holdout_id": "pre_2020", "start": "1970-01-01", "end": "2019-12-31", "core": True},
        {"holdout_id": "2020_shock", "start": "2020-01-01", "end": "2020-12-31", "core": True},
        {"holdout_id": "2021_bull_rotation", "start": "2021-01-01", "end": "2021-12-31", "core": True},
        {"holdout_id": "2022_bear_rate_shock", "start": "2022-01-01", "end": "2022-12-31", "core": True},
        {"holdout_id": "2023_trend_recovery", "start": "2023-01-01", "end": "2023-12-31", "core": True},
        {"holdout_id": "2024_trend_ai", "start": "2024-01-01", "end": "2024-12-31", "core": True},
        {"holdout_id": "2025_2026_recent", "start": "2025-01-01", "end": "2026-12-31", "core": True},
        {"holdout_id": "last_12_months", "months": 12, "core": True},
        {"holdout_id": "last_24_months", "months": 24, "core": True},
        {"holdout_id": "random_symbol_holdout", "mode": "random_symbol", "core": False},
        {"holdout_id": "sector_holdout", "mode": "sector", "core": False},
        {"holdout_id": "top_symbol_removed", "mode": "top_symbol", "core": True},
        {"holdout_id": "top_sector_removed", "mode": "top_sector", "core": True},
        {"holdout_id": "high_beta_only", "mode": "high_beta", "core": False},
        {"holdout_id": "etf_only", "mode": "etf", "core": False},
        {"holdout_id": "single_name_only", "mode": "single_name", "core": False},
        {"holdout_id": "mega_cap_tech_removed", "mode": "mega_cap_tech_removed", "core": False},
        {"holdout_id": "semiconductors_removed", "mode": "semiconductors_removed", "core": False},
        {"holdout_id": "financials_removed", "mode": "financials_removed", "core": False},
        {"holdout_id": "energy_removed", "mode": "energy_removed", "core": False},
    ]


def apply_stress_case(trades: list[dict[str, object]], case: dict[str, object]) -> list[dict[str, object]]:
    if not trades:
        return []
    family = str(case.get("stress_family", ""))
    if family == "outlier_removal":
        sorted_trades = sorted(trades, key=lambda item: safe_float(item.get("paper_pnl")), reverse=True)
        count = int(case.get("count", 0))
        if case["stress_id"] == "outlier_remove_top_5pct":
            remove_count = max(1, int(len(sorted_trades) * 0.05))
            return sorted_trades[remove_count:]
        return sorted_trades[count:]
    if family == "concentration":
        return _apply_concentration_filter(trades, str(case.get("stress_id", "")))
    if family == "recent_only":
        return _apply_recent_filter(trades, case)
    if family == "regime_specific":
        regime = str(case.get("regime", ""))
        if regime in {"uptrend", "downtrend", "sideways"}:
            return [t for t in trades if str(t.get("trend_regime", "")) == regime]
        return [t for t in trades if str(t.get("regime", "")) == regime]
    stressed: list[dict[str, object]] = []
    for trade in trades:
        pnl = safe_float(trade.get("paper_pnl"))
        slippage = safe_float(trade.get("slippage_cost"))
        theta = safe_float(trade.get("theta_decay_cost"))
        entry_spot = max(safe_float(trade.get("entry_spot")), 0.01)
        if family == "slippage":
            multiplier = safe_float(case.get("multiplier", 1.0))
            pnl -= slippage * max(multiplier - 1.0, 0.0)
        elif family == "theta":
            multiplier = safe_float(case.get("multiplier", 1.0))
            pnl -= theta * max(multiplier - 1.0, 0.0)
        elif family == "iv_shock":
            shock = safe_float(case.get("shock", 0.0))
            pnl -= abs(pnl) * shock + slippage * shock
        elif family == "entry_degradation":
            pnl -= entry_spot * safe_float(case.get("pct", 0.0))
        elif family == "exit_degradation":
            pnl -= entry_spot * safe_float(case.get("pct", 0.0))
        elif family == "gap_stress":
            pnl -= entry_spot * (0.015 if "overnight" in str(case.get("stress_id")) else 0.025)
        copy = dict(trade)
        copy["paper_pnl"] = round(pnl, 6)
        stressed.append(copy)
    return stressed


def _apply_concentration_filter(trades: list[dict[str, object]], stress_id: str) -> list[dict[str, object]]:
    if "symbol" in stress_id:
        top = Counter(str(t.get("symbol", "")) for t in trades).most_common(1)[0][0]
        return [t for t in trades if str(t.get("symbol", "")) != top]
    if "sector" in stress_id:
        top = Counter(sector_for_symbol(str(t.get("symbol", ""))) for t in trades).most_common(1)[0][0]
        return [t for t in trades if sector_for_symbol(str(t.get("symbol", ""))) != top]
    top = Counter(str(t.get("regime", "")) for t in trades).most_common(1)[0][0]
    return [t for t in trades if str(t.get("regime", "")) != top]


def _apply_recent_filter(trades: list[dict[str, object]], case: dict[str, object]) -> list[dict[str, object]]:
    if case.get("stress_id") == "recent_2025_2026_only":
        return [t for t in trades if str(t.get("entry_date", ""))[:4] in {"2025", "2026"}]
    months = int(case.get("months", 12))
    dates = [date_from_text(t.get("entry_date")) for t in trades]
    if not dates:
        return []
    latest = max(dates)
    cutoff_year = latest.year - (months // 12)
    cutoff_month = latest.month
    cutoff = date(cutoff_year, cutoff_month, 1)
    return [t for t in trades if date_from_text(t.get("entry_date")) >= cutoff]


def apply_holdout(trades: list[dict[str, object]], holdout: dict[str, object]) -> list[dict[str, object]]:
    mode = holdout.get("mode")
    if mode == "random_symbol":
        symbols = sorted({str(t.get("symbol", "")) for t in trades})
        if len(symbols) < 2:
            return trades
        drop = symbols[len(symbols) // 2]
        return [t for t in trades if str(t.get("symbol", "")) != drop]
    if mode == "sector":
        sectors = sorted({sector_for_symbol(str(t.get("symbol", ""))) for t in trades})
        if len(sectors) < 2:
            return trades
        drop = sectors[len(sectors) // 2]
        return [t for t in trades if sector_for_symbol(str(t.get("symbol", ""))) != drop]
    if mode == "top_symbol":
        top = Counter(str(t.get("symbol", "")) for t in trades).most_common(1)[0][0]
        return [t for t in trades if str(t.get("symbol", "")) != top]
    if mode == "top_sector":
        top = Counter(sector_for_symbol(str(t.get("symbol", ""))) for t in trades).most_common(1)[0][0]
        return [t for t in trades if sector_for_symbol(str(t.get("symbol", ""))) != top]
    if mode == "high_beta":
        high_beta = {"NVDA", "TSLA", "AMD", "SMCI", "META", "AMZN"}
        return [t for t in trades if str(t.get("symbol", "")).upper() in high_beta]
    if mode == "etf":
        etfs = {"SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "TLT", "IEF", "SHY", "HYG", "LQD", "GLD", "SLV", "USO"}
        return [t for t in trades if str(t.get("symbol", "")).upper() in etfs]
    if mode == "single_name":
        etfs = {"SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "TLT", "IEF", "SHY", "HYG", "LQD", "GLD", "SLV", "USO"}
        return [t for t in trades if str(t.get("symbol", "")).upper() not in etfs]
    if mode == "mega_cap_tech_removed":
        drop = {"AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN"}
        return [t for t in trades if str(t.get("symbol", "")).upper() not in drop]
    if mode == "semiconductors_removed":
        return [t for t in trades if sector_for_symbol(str(t.get("symbol", ""))) != "semiconductors"]
    if mode == "financials_removed":
        return [t for t in trades if sector_for_symbol(str(t.get("symbol", ""))) != "financials"]
    if mode == "energy_removed":
        return [t for t in trades if sector_for_symbol(str(t.get("symbol", ""))) != "energy"]
    if "months" in holdout:
        return _apply_recent_filter(trades, {"stress_id": str(holdout.get("holdout_id")), "months": holdout.get("months")})
    start = date_from_text(holdout.get("start"))
    end = date_from_text(holdout.get("end"))
    return [t for t in trades if start <= date_from_text(t.get("entry_date")) <= end]


def stress_metrics(trades: list[dict[str, object]]) -> dict[str, object]:
    metrics = pnl_metrics(trades)
    metrics["drawdown_adjusted_pnl"] = round(safe_float(metrics.get("net_pnl")) + safe_float(metrics.get("max_drawdown")), 6)
    return metrics


def stress_survived(metrics: dict[str, object], min_sample: int = 5) -> tuple[bool, str]:
    if int(metrics.get("sample_count", 0)) < min_sample:
        return False, "sample_count_inadequate"
    if safe_float(metrics.get("net_pnl")) <= 0.0:
        return False, "net_pnl_not_positive"
    if safe_float(metrics.get("expectancy")) <= CORE_MIN_EXPECTANCY:
        return False, "expectancy_not_positive"
    if safe_float(metrics.get("profit_factor")) <= CORE_MIN_PROFIT_FACTOR:
        return False, "profit_factor_below_core_threshold"
    if abs(min(safe_float(metrics.get("max_drawdown")), 0.0)) > CORE_MAX_DRAWDOWN_ABS:
        return False, "max_drawdown_above_threshold"
    return True, ""


def holdout_survived(metrics: dict[str, object], baseline: dict[str, object]) -> tuple[bool, str]:
    survived, reason = stress_survived(metrics, min_sample=3)
    if not survived:
        return False, reason
    baseline_expectancy = safe_float(baseline.get("expectancy"))
    if baseline_expectancy > 0.0 and safe_float(metrics.get("expectancy")) < baseline_expectancy * 0.35:
        return False, "expectancy_degraded_vs_baseline"
    return True, ""


def grouped_trades_by_champion(trades: list[dict[str, object]], champions: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for champion in champions:
        key = f"{champion.get('cohort_level')}::{champion.get('cohort_id')}"
        grouped[key] = trades_for_champion(champion, trades)
    return grouped


def write_stage_proof(path, proof_id: str, status: str, summary: dict[str, object]) -> None:
    write_jsonl_file(path, [hardening_proof_record(proof_id, status, summary)])
