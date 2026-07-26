"""Baseline arbitration for the real-history honest lane.

Separates signal from drift: for each strategy (long_call / long_put) build a
seeded random-entry baseline paired one-to-one to the cohort's OWN (symbol,
month) anchors - identical universe composition and era concentration, random
entry day - priced and exited by the IDENTICAL engine (same tenor, IV proxy,
exit rules, cost stack). Confidence intervals resample month clusters to retain
within-month dependence and apply familywise error control across cohorts.

Deterministic (fixed seed), leak-free, model-priced, paper-only.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR

from .model_priced_trade_simulator import default_exit_config, simulate_intent_with_marks
from .real_history_honest_backtester import (
    _build_real_marks,
    _real_bars_by_symbol,
    apply_trade_costs,
)
from .trade_records_recovery import (
    iter_verified_trade_records,
    resolve_default_backtest_trade_ledger,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKTEST_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "backtest"
BACKTEST_TRADE_RECORDS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_trade_records.jsonl"
BASELINE_TRADES_PATH = BACKTEST_ARTIFACT_DIR / "baseline_random_entry_trades.jsonl"
BASELINE_ARBITRATION_PATH = BACKTEST_ARTIFACT_DIR / "baseline_arbitration_verdicts.jsonl"
BASELINE_SUMMARY_PATH = BACKTEST_ARTIFACT_DIR / "baseline_arbitration_summary.json"
BASELINE_REPORT_PATH = REPORTS_DIR / "DOPEY_BASELINE_ARBITRATION_REPORT.md"

BASELINE_SEED = 20260709
BASELINE_START_DATE = "2015-01-01"
BOOTSTRAP_ITERATIONS = 2000
ALPHA_CONFIDENCE = 0.95
MIN_BASELINE_COHORT_SAMPLE = 30
MIN_BASELINE_MONTH_CLUSTERS = 12
BASELINE_POLICY_VERSION = "dopey-cohort-matched-baseline-v2"


def run_baseline_arbitration() -> dict[str, Any]:
    if not BACKTEST_TRADE_RECORDS_PATH.exists():
        summary = {"artifact_type": "baseline_arbitration_summary", "baseline_status": "blocked_missing_backtest_records"}
        _write_json(BASELINE_SUMMARY_PATH, summary)
        return summary
    ledger_resolution = resolve_default_backtest_trade_ledger()
    real_trades = list(iter_verified_trade_records(ledger_resolution))
    real_trades = [record for record in real_trades if record.get("real_history_used") is True]
    if not real_trades:
        summary = {"artifact_type": "baseline_arbitration_summary", "baseline_status": "blocked_no_real_trades"}
        _write_json(BASELINE_SUMMARY_PATH, summary)
        return summary
    bars_by_symbol = _real_bars_by_symbol()
    strategy_counts: dict[str, int] = defaultdict(int)
    real_cohorts: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in real_trades:
        strategy = str(record["candidate_strategy"])
        strategy_counts[strategy] += 1
        real_cohorts[(str(record["signal_family"]), strategy)].append(record)
    baseline_trades = _build_baseline_trades(real_cohorts, bars_by_symbol)
    verdicts = _verdicts(real_trades, baseline_trades)
    ranked_verdicts = sorted(verdicts, key=lambda record: float(record["mean_difference"]), reverse=True)
    summary = {
        "artifact_type": "baseline_arbitration_summary",
        "baseline_status": "baseline_arbitration_complete",
        "baseline_seed": BASELINE_SEED,
        "baseline_policy_version": BASELINE_POLICY_VERSION,
        "backtest_trade_resolution_status": ledger_resolution["status"],
        "backtest_trade_resolved_sha256": ledger_resolution["resolved_sha256"],
        "backtest_trade_verified_record_count": ledger_resolution[
            "verified_record_hash_count"
        ],
        "baseline_policy": "one_to_one_cohort_matched_symbol_and_month_random_day_same_pricing_exit_cost_engine",
        "inference_policy": "paired_month_cluster_bootstrap_with_bonferroni_familywise_control",
        "real_trade_count": len(real_trades),
        "baseline_trade_count": len(baseline_trades),
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "baseline_net_by_strategy": {
            strategy: round(sum(float(record["path_pnl"]) for record in records), 6)
            for strategy, records in sorted(_group(baseline_trades, "candidate_strategy").items())
        },
        "baseline_net_by_cohort": {
            cohort_id: round(sum(float(record["path_pnl"]) for record in records), 6)
            for cohort_id, records in sorted(_group(baseline_trades, "comparison_cohort_id").items())
        },
        "one_to_one_match_complete": len(baseline_trades) == len(real_trades),
        "verdict_count": len(verdicts),
        "cohorts_beating_baseline": sum(1 for verdict in verdicts if verdict["beats_baseline_ci"]),
        "cohorts_with_positive_mean_difference": sum(
            1 for verdict in verdicts if float(verdict["mean_difference"]) > 0.0
        ),
        "research_lead_cohort": str(ranked_verdicts[0]["cohort_id"]) if ranked_verdicts else "",
        "research_lead_mean_difference": (
            float(ranked_verdicts[0]["mean_difference"]) if ranked_verdicts else 0.0
        ),
        "data_source_tier": "local_real_history",
        "real_history_used": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    _write_jsonl(BASELINE_TRADES_PATH, baseline_trades)
    _write_jsonl(BASELINE_ARBITRATION_PATH, verdicts)
    _write_json(BASELINE_SUMMARY_PATH, summary)
    _write_report(summary, verdicts)
    return summary


def _build_baseline_trades(
    real_cohorts: dict[tuple[str, str], list[dict[str, Any]]],
    bars_by_symbol: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Build one random control for every real trade within its symbol-month."""
    rng = random.Random(BASELINE_SEED)
    exit_config = default_exit_config()
    eligible_by_month: dict[tuple[str, str], list[int]] = {}
    for symbol in sorted(symbol for symbol in bars_by_symbol if symbol != "VIX"):
        rows = bars_by_symbol[symbol]
        eligible = [
            index
            for index, row in enumerate(rows)
            if row["date"] >= BASELINE_START_DATE and index + 2 < len(rows)
        ]
        for index in eligible:
            month = str(rows[index]["date"])[:7]
            eligible_by_month.setdefault((symbol, month), []).append(index)
    trades: list[dict[str, Any]] = []
    for (family, strategy), cohort_records in sorted(real_cohorts.items()):
        cohort_id = f"{family}|{strategy}"
        for anchor_index, real_record in enumerate(cohort_records):
            symbol = str(real_record["symbol"])
            anchor_date = str(real_record["signal_date"])
            anchor_month = anchor_date[:7]
            positions = eligible_by_month.get((symbol, anchor_month), [])
            if not positions:
                raise ValueError(
                    f"no matched baseline dates: cohort_id={cohort_id}, symbol={symbol}, month={anchor_month}"
                )
            position = positions[rng.randrange(len(positions))]
            rows = bars_by_symbol[symbol]
            signal_date = rows[position]["date"]
            intent = {
                "intent_id": f"baseline-{family}-{strategy}-{anchor_index:06d}",
                "symbol": symbol,
                "signal_id": f"baseline-{family}-{strategy}-{anchor_index:06d}",
                "signal_family": "random_entry_baseline",
                "signal_date": signal_date,
                "direction": "bullish" if strategy == "long_call" else "bearish",
                "candidate_strategy": strategy,
                "option_structure": strategy,
                "data_source_tier": "local_real_history",
                "reason_codes": ["random_entry_baseline"],
            }
            built = _build_real_marks(intent, rows, exit_config.max_holding_steps)
            if built is None:
                raise ValueError(
                    f"matched baseline mark construction failed: cohort_id={cohort_id}, "
                    f"symbol={symbol}, signal_date={signal_date}"
                )
            marks, mark_dates, path_id, iv_used, _ = built
            simulated = simulate_intent_with_marks(
                intent, marks, mark_dates, path_id, "valid_real_dataset", exit_config
            )
            simulated_records = list(simulated["trade_records"])
            if len(simulated_records) != 1:
                raise ValueError(
                    f"matched baseline must produce one trade: cohort_id={cohort_id}, "
                    f"symbol={symbol}, record_count={len(simulated_records)}"
                )
            relabeled = dict(simulated_records[0])
            relabeled["real_history_used"] = True
            relabeled["fixture_only"] = False
            relabeled["data_source_tier"] = "local_real_history"
            relabeled["iv_proxy_used"] = iv_used
            relabeled["comparison_cohort_id"] = cohort_id
            relabeled["comparison_trade_id"] = str(real_record["trade_id"])
            relabeled["comparison_anchor_symbol"] = symbol
            relabeled["comparison_anchor_month"] = anchor_month
            relabeled["comparison_anchor_signal_date"] = anchor_date
            relabeled["baseline_policy_version"] = BASELINE_POLICY_VERSION
            trades.append(apply_trade_costs(relabeled))
    return trades


def _verdicts(real_trades: list[dict[str, Any]], baseline_trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    verdicts: list[dict[str, Any]] = []
    cohorts = _group(real_trades, "signal_family", "candidate_strategy")
    eligible_cohort_count = sum(
        1 for records in cohorts.values() if len(records) >= MIN_BASELINE_COHORT_SAMPLE
    )
    adjusted_confidence = 1.0 - ((1.0 - ALPHA_CONFIDENCE) / max(eligible_cohort_count, 1))
    real_by_trade_id = {str(record["trade_id"]): record for record in real_trades}
    if len(real_by_trade_id) != len(real_trades):
        raise ValueError("real baseline arbitration input contains duplicate trade_id values")
    baseline_by_cohort = _group(baseline_trades, "comparison_cohort_id")
    rng = random.Random(BASELINE_SEED + 1)
    for (family, strategy), records in sorted(cohorts.items()):
        if len(records) < MIN_BASELINE_COHORT_SAMPLE:
            continue
        cohort_id = f"{family}|{strategy}"
        matched_baselines = baseline_by_cohort.get(cohort_id, [])
        if len(matched_baselines) != len(records):
            raise ValueError(
                f"baseline pairing is incomplete: cohort_id={cohort_id}, "
                f"real_count={len(records)}, baseline_count={len(matched_baselines)}"
            )
        paired_differences: list[tuple[float, str]] = []
        cohort_pnls: list[float] = []
        baseline_pnls: list[float] = []
        for baseline in matched_baselines:
            trade_id = str(baseline["comparison_trade_id"])
            real_record = real_by_trade_id.get(trade_id)
            if real_record is None:
                raise ValueError(f"baseline references unknown real trade: trade_id={trade_id}")
            cohort_pnl = float(real_record["path_pnl"])
            baseline_pnl = float(baseline["path_pnl"])
            cohort_pnls.append(cohort_pnl)
            baseline_pnls.append(baseline_pnl)
            paired_differences.append(
                (cohort_pnl - baseline_pnl, str(baseline["comparison_anchor_month"]))
            )
        month_count = len({month for _, month in paired_differences})
        if month_count < MIN_BASELINE_MONTH_CLUSTERS:
            continue
        diff_mean = _mean([difference for difference, _ in paired_differences])
        low, high = _bootstrap_month_cluster_ci(paired_differences, rng, adjusted_confidence)
        verdict = {
            "artifact_type": "baseline_arbitration_verdict",
            "cohort_id": cohort_id,
            "signal_family": family,
            "candidate_strategy": strategy,
            "cohort_sample": len(cohort_pnls),
            "baseline_sample": len(baseline_pnls),
            "matched_pair_count": len(paired_differences),
            "month_cluster_count": month_count,
            "cohort_mean_net_pnl": round(_mean(cohort_pnls), 6),
            "baseline_mean_net_pnl": round(_mean(baseline_pnls), 6),
            "mean_difference": round(diff_mean, 6),
            "difference_ci_low": round(low, 6),
            "difference_ci_high": round(high, 6),
            "beats_baseline_ci": bool(low > 0.0),
            "worse_than_baseline_ci": bool(high < 0.0),
            "indistinguishable_from_baseline": bool(low <= 0.0 <= high),
            "nominal_confidence": ALPHA_CONFIDENCE,
            "familywise_adjusted_confidence": round(adjusted_confidence, 6),
            "multiple_testing_method": "bonferroni",
            "bootstrap_resampling_unit": "anchor_month_cluster",
            "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
            "baseline_policy_version": BASELINE_POLICY_VERSION,
            "not_edge_evidence": True,
            "paper_only": True,
            "live_blocked": True,
        }
        verdicts.append(verdict)
    return verdicts


def _bootstrap_month_cluster_ci(
    paired_differences: list[tuple[float, str]],
    rng: random.Random,
    confidence: float,
) -> tuple[float, float]:
    differences_by_month: dict[str, list[float]] = defaultdict(list)
    for difference, month in paired_differences:
        differences_by_month[month].append(difference)
    months = sorted(differences_by_month)
    if not months:
        raise ValueError("month-cluster bootstrap requires at least one month")
    diffs: list[float] = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        sampled_months = [months[rng.randrange(len(months))] for _ in range(len(months))]
        sampled_differences = [
            difference
            for month in sampled_months
            for difference in differences_by_month[month]
        ]
        diffs.append(_mean(sampled_differences))
    diffs.sort()
    tail = (1.0 - confidence) / 2.0
    low_index = int(tail * len(diffs))
    high_index = min(int((1.0 - tail) * len(diffs)), len(diffs) - 1)
    return diffs[low_index], diffs[high_index]


def _group(records: list[dict[str, Any]], *fields: str) -> dict[Any, list[dict[str, Any]]]:
    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = tuple(str(record.get(field, "")) for field in fields)
        grouped[key if len(key) > 1 else key[0]].append(record)
    return dict(grouped)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _write_report(summary: dict[str, Any], verdicts: list[dict[str, Any]]) -> None:
    lines = [
        "# DOPEY Baseline Arbitration Report",
        "",
        "## Question",
        "Do the real-lane cohorts beat a seeded random-entry baseline run through the identical",
        "pricing, exit, and cost engine - or is their P&L just market drift?",
        "",
        f"- baseline trades: `{summary.get('baseline_trade_count', 0)}` (seed `{BASELINE_SEED}`)",
        f"- cohorts evaluated: `{summary.get('verdict_count', 0)}`",
        f"- cohorts beating baseline after familywise control (nominal {ALPHA_CONFIDENCE:.0%}): "
        f"`{summary.get('cohorts_beating_baseline', 0)}`",
        "",
        "## Verdicts (mean net P&L per trade, cohort minus baseline)",
    ]
    for verdict in sorted(verdicts, key=lambda record: record["mean_difference"], reverse=True):
        status = (
            "BEATS baseline"
            if verdict["beats_baseline_ci"]
            else ("WORSE than baseline" if verdict["worse_than_baseline_ci"] else "indistinguishable")
        )
        lines.append(
            f"- `{verdict['cohort_id']}`: diff `{verdict['mean_difference']}` "
            f"clustered CI [`{verdict['difference_ci_low']}`, `{verdict['difference_ci_high']}`] "
            f"(months `{verdict['month_cluster_count']}`) -> {status}"
        )
    lines.extend(
        [
            "",
            "## Honest Limits",
            "- Model-priced marks on both sides; identical engine, so the comparison isolates entry-signal value.",
            "- Month-cluster resampling and Bonferroni control reduce false confidence from overlapping trades and cohort search.",
            "- Beating baseline is necessary, not sufficient: era stability and real chains still gate promotion.",
            "- paper_only: `true`; live_blocked: `true`.",
        ]
    )
    BASELINE_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
