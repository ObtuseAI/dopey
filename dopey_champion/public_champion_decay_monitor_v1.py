"""Champion decay and stability monitor for public paper champions."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import (
    HARDENING_ROOT,
    champion_records,
    live_safety_fields,
    load_public_trades,
    profit_factor,
    trades_for_champion,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import (
    expectancy,
    max_drawdown,
    record_with_hash,
    safe_float,
    write_jsonl_file,
)


RECORDS_PATH = HARDENING_ROOT / "public_champion_decay_records_v1.jsonl"
ALERTS_PATH = HARDENING_ROOT / "public_champion_decay_alerts_v1.jsonl"
SUMMARY_PATH = HARDENING_ROOT / "public_champion_decay_monitor_v1_summary.json"
PROOF_PATH = HARDENING_ROOT / "public_champion_decay_monitor_v1_proof.jsonl"


def run_public_champion_decay_monitor_v1() -> dict[str, object]:
    champions = champion_records()
    trades = load_public_trades()
    records: list[dict[str, object]] = []
    alerts: list[dict[str, object]] = []
    stable_count = 0
    degraded_count = 0

    for champion in champions:
        champion_key = str(champion.get("cohort_id", ""))
        cohort_trades = sorted(
            trades_for_champion(champion, trades),
            key=lambda item: str(item.get("entry_date", "")),
        )
        pnl_values = [safe_float(trade.get("paper_pnl")) for trade in cohort_trades]
        rolling_20 = rolling_window_expectancy(pnl_values, 20)
        rolling_50 = rolling_window_expectancy(pnl_values, 50)
        rolling_pf = rolling_window_profit_factor(pnl_values, 20)
        rolling_dd = rolling_window_drawdown(pnl_values, 20)
        recent = pnl_values[-20:] if len(pnl_values) >= 20 else pnl_values
        history = pnl_values[:-20] if len(pnl_values) > 20 else []
        recent_expectancy = expectancy(recent)
        history_expectancy = expectancy(history) if history else recent_expectancy
        degradation = 0.0
        if history_expectancy > 0.0:
            degradation = round((history_expectancy - recent_expectancy) / history_expectancy, 6)
        density = Counter(str(trade.get("entry_date", ""))[:7] for trade in cohort_trades)
        losing_streak, recovery = streak_metrics(pnl_values)
        alert_ids: list[str] = []
        if degradation > 0.35:
            alert_ids.append("recent_vs_history_degradation")
        if rolling_20 < 0.0 and len(pnl_values) >= 20:
            alert_ids.append("rolling_20_expectancy_negative")
        if rolling_dd < -500.0:
            alert_ids.append("rolling_drawdown_severe")
        if losing_streak >= 8:
            alert_ids.append("max_losing_streak_high")
        if alert_ids:
            degraded_count += 1
            for alert_id in alert_ids:
                alerts.append(record_with_hash({
                    "artifact_type": "public_champion_decay_alert_v1",
                    "champion_name": champion_key,
                    "alert_id": alert_id,
                    "rolling_20_trade_expectancy": rolling_20,
                    "rolling_50_trade_expectancy": rolling_50,
                    "recent_vs_history_degradation": degradation,
                    **live_safety_fields(),
                }, "record_hash"))
        else:
            stable_count += 1
        records.append(record_with_hash({
            "artifact_type": "public_champion_decay_record_v1",
            "champion_name": champion_key,
            "rolling_20_trade_expectancy": rolling_20,
            "rolling_50_trade_expectancy": rolling_50,
            "rolling_drawdown": rolling_dd,
            "rolling_profit_factor": rolling_pf,
            "rolling_split_pass_rate": champion.get("split_pass_rate", 0.0),
            "recent_vs_history_degradation": degradation,
            "sample_density_by_month": dict(density.most_common(12)),
            "max_losing_streak": losing_streak,
            "recovery_time_trades": recovery,
            "performance_after_high_drawdown": performance_after_drawdown(pnl_values),
            "performance_after_volatility_regime_shift": regime_shift_performance(cohort_trades),
            "decay_alert_ids": alert_ids,
            "stable_flag": not alert_ids,
            **live_safety_fields(),
        }, "record_hash"))

    summary = {
        "artifact_type": "public_champion_decay_monitor_v1_summary",
        "public_champion_decay_monitor_version": "dopey-public-champion-decay-monitor-v1",
        "decay_monitor_status": "decay_monitor_complete",
        "champions_monitored": len(champions),
        "decay_alert_count": len(alerts),
        "stable_champion_count": stable_count,
        "degraded_champion_count": degraded_count,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(RECORDS_PATH, records)
    write_jsonl_file(ALERTS_PATH, alerts)
    write_stage_proof(PROOF_PATH, "public-champion-decay-monitor-v1", str(summary["decay_monitor_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def rolling_window_expectancy(pnl_values: list[float], window: int) -> float:
    if not pnl_values:
        return 0.0
    return expectancy(pnl_values[-window:])


def rolling_window_profit_factor(pnl_values: list[float], window: int) -> float:
    if not pnl_values:
        return 0.0
    return profit_factor(pnl_values[-window:])


def rolling_window_drawdown(pnl_values: list[float], window: int) -> float:
    if not pnl_values:
        return 0.0
    return max_drawdown(pnl_values[-window:])


def streak_metrics(pnl_values: list[float]) -> tuple[int, int]:
    """Return (max consecutive losses, trades to recover that streak's losses).

    recovery_time_trades counts trades after the worst losing streak until its
    cumulative losses are earned back; 0 means the streak never recovered (or
    there was no losing streak).
    """
    max_streak = 0
    worst_streak_loss = 0.0
    current = 0
    current_loss = 0.0
    streak_end = 0
    for index, value in enumerate(pnl_values):
        if value < 0.0:
            current += 1
            current_loss += value
            if current > max_streak or (
                current == max_streak and current_loss < worst_streak_loss
            ):
                max_streak = current
                worst_streak_loss = current_loss
                streak_end = index + 1
        else:
            current = 0
            current_loss = 0.0
    if max_streak == 0:
        return 0, 0
    recovered = 0.0
    for trades, value in enumerate(pnl_values[streak_end:], start=1):
        recovered += value
        if recovered + worst_streak_loss >= 0.0:
            return max_streak, trades
    return max_streak, 0


def performance_after_drawdown(pnl_values: list[float]) -> float:
    if len(pnl_values) < 10:
        return 0.0
    equity = 0.0
    peak = 0.0
    drawdown_index = 0
    worst = 0.0
    for index, pnl in enumerate(pnl_values):
        equity += pnl
        peak = max(peak, equity)
        dd = equity - peak
        if dd < worst:
            worst = dd
            drawdown_index = index
    tail = pnl_values[drawdown_index + 1: drawdown_index + 11]
    return expectancy(tail) if tail else 0.0


def regime_shift_performance(trades: list[dict[str, object]]) -> float:
    if len(trades) < 10:
        return 0.0
    regimes = [str(trade.get("regime", "")) for trade in trades]
    if len(set(regimes)) < 2:
        return 0.0
    pivot = len(trades) // 2
    return expectancy([safe_float(trade.get("paper_pnl")) for trade in trades[pivot:]])


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_decay_records_v1": str(RECORDS_PATH),
        "public_champion_decay_alerts_v1": str(ALERTS_PATH),
        "public_champion_decay_monitor_v1_summary": str(SUMMARY_PATH),
        "public_champion_decay_monitor_v1_proof": str(PROOF_PATH),
    }
