"""OPERATOR TOOL - external-evolution fitness for the honest-backtest exit policy.

Fitness contract (consumed by the doofus external evolver, or run by hand):
prints diagnostics, then a bare 0..1 score as the LAST stdout line; exit 0 on
a scoreable run, non-zero when the dataset is not valid (candidate rejected).

What the score IS: the probabilistic Sharpe ratio (P[true SR > 0], skew/kurt
aware) of the HELD-OUT era (signal_date > 2021-12-31) daily portfolio return
series produced by re-running the honest in-memory backtest engine under the
CURRENT dopey_backtest/exit_policy_config.py constants. The train era never
contributes to the score, so a parameter change only scores higher by
generalizing out-of-era. Sample floors prevent "trade less, dodge the stats".

What the score is NOT: evidence. Search results are research recommendations
only (self_modification = artifact_recommendation_only_operator_applies).
The persistent trial ledger counts every evaluation ever run; the review-time
deflated Sharpe (holdout SR vs expected-max-SR under cumulative trials) is
written to last_eval.json for the human promotion decision - deflation is
applied to the SELECTED winner at review, not inside the search (in-search
deflation is a monotone shift that cannot change the argmax but would break
the determinism the evolver requires).

Known honest limitation: adjacent signal dates hold overlapping positions, so
the date series carries serial correlation and the PSR's n is optimistic.
Acceptable for a relative search fitness; never for an evidence claim.

Usage:  .venv\\Scripts\\python operator_tools\\operator_evolve_fitness.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey_backtest.model_priced_trade_simulator import default_exit_config  # noqa: E402
from dopey_backtest.real_history_honest_backtester import (  # noqa: E402
    HISTORY_SPINE_SUMMARY_PATH,
    compute_real_history_trade_records,
)
from dopey_research_pipeline.artifact_io import read_json_guarded, write_json_atomic  # noqa: E402
from dopey_stats.deflated_sharpe import (  # noqa: E402
    _moments,
    expected_max_sharpe,
    probabilistic_sharpe,
)

TRAIN_END_DATE = "2021-12-31"  # matches exit_policy_walkforward_search convention
MIN_HOLDOUT_DATES = 100        # score floors: below these the score is 0.0 so a
MIN_HOLDOUT_PATHS = 500        # candidate cannot win by starving the sample

STATE_DIR = Path(os.environ.get(
    "DOPEY_EVOLVE_STATE_DIR",
    str(REPO / "artifacts" / "dopey" / "evolution_fitness"),
))
TRIAL_LEDGER_PATH = STATE_DIR / "trial_ledger.json"
LAST_EVAL_PATH = STATE_DIR / "last_eval.json"


def unique_directional_paths(trade_records: list[dict]) -> list[dict]:
    """First record per (symbol, signal_date, strategy): the 7 signal families
    fan out over shared paths and would otherwise be counted ~7x."""
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict] = []
    for record in trade_records:
        key = (
            str(record.get("symbol", "")),
            str(record.get("signal_date", "")),
            str(record.get("candidate_strategy", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def daily_return_series(trade_records: list[dict]) -> list[tuple[str, float]]:
    """Equal-weight mean net trade return per signal_date, date-sorted."""
    by_date: dict[str, list[float]] = {}
    for record in trade_records:
        date = str(record.get("signal_date", ""))
        if not date:
            continue
        by_date.setdefault(date, []).append(float(record.get("trade_return_model_units", 0.0)))
    return [(date, sum(vals) / len(vals)) for date, vals in sorted(by_date.items())]


def split_by_era(records: list[dict], train_end: str = TRAIN_END_DATE) -> tuple[list[dict], list[dict]]:
    train = [r for r in records if str(r.get("signal_date", "")) <= train_end]
    holdout = [r for r in records if str(r.get("signal_date", "")) > train_end]
    return train, holdout


def sharpe_like(series: list[float]) -> float:
    n = len(series)
    if n < 2:
        return 0.0
    mean = sum(series) / n
    var = sum((v - mean) ** 2 for v in series) / (n - 1)
    # fp-dust guard: a constant series must score 0, not mean/1e-17 -> PSR 1.0
    if var < 1e-16:
        return 0.0
    return mean / var ** 0.5


def score_holdout(holdout_records: list[dict]) -> dict:
    """Deterministic 0..1 fitness from the held-out era only."""
    series = [v for _, v in daily_return_series(holdout_records)]
    n_dates = len(series)
    n_paths = len(holdout_records)
    sr = sharpe_like(series)
    _, skew, kurt = _moments(series)
    if n_dates < MIN_HOLDOUT_DATES or n_paths < MIN_HOLDOUT_PATHS:
        psr = 0.0
        floor_reason = f"sample_floor(dates {n_dates}<{MIN_HOLDOUT_DATES} or paths {n_paths}<{MIN_HOLDOUT_PATHS})"
    else:
        psr = probabilistic_sharpe(sr, 0.0, n_dates, skew, kurt)
        floor_reason = ""
    return {
        "holdout_dates": n_dates,
        "holdout_unique_paths": n_paths,
        "holdout_sharpe_like": round(sr, 6),
        "holdout_skew": round(skew, 6),
        "holdout_kurtosis": round(kurt, 6),
        "score_psr": round(psr, 6),
        "floor_reason": floor_reason,
    }


def bump_trial_ledger(exit_config_snapshot: dict) -> int:
    """Record this evaluation; return the DISTINCT-CONFIG trial count.

    The review-time deflation penalizes the best score by the breadth of the
    search (expected max Sharpe under N trials). N must count distinct
    candidate configurations examined - a deterministic re-evaluation of the
    SAME config (e.g. the nightly determinism check runs the fitness twice)
    adds zero data-snooping and must not inflate the penalty, or repeated
    monitoring would slowly strangle the lane. Total invocations are still
    kept (cumulative_evals) for the audit trail.
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        ledger, _source = read_json_guarded(TRIAL_LEDGER_PATH)
    except ValueError:
        ledger = None
    if not isinstance(ledger, dict):
        ledger = {"artifact_type": "evolution_fitness_trial_ledger", "cumulative_evals": 0, "first_eval_utc": now}
    config_hash = hashlib.sha256(
        json.dumps(exit_config_snapshot, sort_keys=True).encode("utf-8")
    ).hexdigest()
    config_counts = ledger.get("config_eval_counts")
    if not isinstance(config_counts, dict):
        # Migration from the pre-distinct ledger: every historical eval was of
        # some config; attribute the legacy total to "unattributed legacy
        # evals" as ONE distinct historical config-group so the penalty never
        # DROPS below what the legacy count already implied for review
        # continuity, while new configs count individually from here.
        config_counts = {}
        legacy_evals = int(ledger.get("cumulative_evals", 0))
        if legacy_evals > 0:
            config_counts["legacy_unattributed"] = legacy_evals
    config_counts[config_hash] = int(config_counts.get(config_hash, 0)) + 1
    ledger["config_eval_counts"] = config_counts
    ledger["cumulative_evals"] = int(ledger.get("cumulative_evals", 0)) + 1
    ledger["distinct_config_count"] = len(config_counts)
    ledger["last_eval_utc"] = now
    ledger["last_exit_config"] = exit_config_snapshot
    ledger["paper_only"] = True
    ledger["live_blocked"] = True
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    write_json_atomic(TRIAL_LEDGER_PATH, ledger)
    return int(ledger["distinct_config_count"])


def ensure_real_signals() -> bool:
    """Self-heal: fixture-lane runs can overwrite the shared signals artifact
    (documented V8 hazard). If the staged signals are not real-history tier,
    regenerate them from the governed spine (deterministic) before scoring."""
    from dopey_backtest.real_history_honest_backtester import DIRECTIONAL_SETUP_SIGNALS_PATH
    try:
        first_line = ""
        with DIRECTIONAL_SETUP_SIGNALS_PATH.open(encoding="utf-8") as handle:
            first_line = handle.readline()
        tier = str(json.loads(first_line).get("data_source_tier", "")) if first_line.strip() else ""
    except (OSError, json.JSONDecodeError):
        tier = ""
    if tier == "local_real_history":
        return True
    print(f"signals artifact tier '{tier}' != local_real_history: regenerating from spine", flush=True)
    from dopey_analysis.real_history_signal_engine import run_real_history_signal_engine
    summary = run_real_history_signal_engine()
    return str(summary.get("signal_engine_status", "")) == "local_real_history_signals_computed"


def main() -> int:
    try:
        spine = json.loads(HISTORY_SPINE_SUMMARY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("history spine summary unreadable", flush=True)
        return 2
    if str(spine.get("dataset_status", "")) != "valid_real_dataset":
        print(f"history dataset not valid: {spine.get('dataset_status')}", flush=True)
        return 2
    if not ensure_real_signals():
        print("real signals unavailable and regeneration failed", flush=True)
        return 2

    exit_config = default_exit_config()
    config_snapshot = {
        "premium_stop_pct": exit_config.premium_stop_pct,
        "premium_target_pct": exit_config.premium_target_pct,
        "max_holding_steps": exit_config.max_holding_steps,
    }
    computed = compute_real_history_trade_records(exit_config)
    unique = unique_directional_paths(computed["trade_records"])
    train_records, holdout_records = split_by_era(unique)
    scored = score_holdout(holdout_records)

    # Train-era context for the human review (never part of the score).
    train_series = [v for _, v in daily_return_series(train_records)]
    train_sr = sharpe_like(train_series)

    trials = bump_trial_ledger(config_snapshot)
    # Review-time deflation: the SELECTED candidate must clear luck's expected
    # best across everything this search has ever evaluated.
    n_dates = max(int(scored["holdout_dates"]), 2)
    sr_star = expected_max_sharpe(trials, 1.0 / max(n_dates - 1, 1))
    review_dsr = probabilistic_sharpe(
        float(scored["holdout_sharpe_like"]), sr_star, n_dates,
        float(scored["holdout_skew"]), float(scored["holdout_kurtosis"]),
    ) if not scored["floor_reason"] else 0.0

    diagnostics = {
        "artifact_type": "evolution_fitness_evaluation",
        "exit_config": config_snapshot,
        "train_end_date": TRAIN_END_DATE,
        "train_dates": len(train_series),
        "train_unique_paths": len(train_records),
        "train_sharpe_like": round(train_sr, 6),
        **scored,
        "cumulative_trials": trials,
        "expected_max_sharpe_under_trials": round(sr_star, 6),
        "review_dsr_probability": round(review_dsr, 6),
        "evidence_class": "research_search_fitness_not_evidence",
        "self_modification": "artifact_recommendation_only_operator_applies",
        "paper_only": True,
        "live_blocked": True,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json_atomic(LAST_EVAL_PATH, diagnostics)
    print(json.dumps(diagnostics, sort_keys=True), flush=True)
    print(f"{diagnostics['score_psr']:.6f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
