"""Walk-forward exit-policy search: honest self-tuning of trade management.

The legitimate version of "the agent rewrites its own runbook": a grid search
over exit-policy parameters (premium stop, target, max hold) re-simulated over
the REAL intent set with the identical pricing and cost engine, split into
train (2015-2021) and validation (2022-2026) eras. A parameter set is
recommended ONLY if it beats the current policy in BOTH eras net-of-cost -
out-of-era improvement or nothing. Signals are never touched; this tunes how
losses are managed, not what is believed. Recommendations are artifacts for
operator review, never silent self-modification. Paper-only, live-blocked.
"""
from __future__ import annotations

import json
import hashlib
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, TypedDict

from dopey_backtest.model_priced_trade_simulator import BacktestExitConfig, simulate_intent_with_marks
from dopey_backtest.real_history_honest_backtester import (
    _build_real_marks,
    _real_bars_by_symbol,
    apply_trade_costs,
)
from dopey_backtest.signal_trade_mapper import load_directional_setup_signals, map_signal_records_to_trade_intents
from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGNALS_PATH = REPO_ROOT / "artifacts" / "dopey" / "signals" / "directional_setup_signals.jsonl"
SEARCH_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "evolution"
SEARCH_GRID_PATH = SEARCH_ARTIFACT_DIR / "exit_policy_search_grid.jsonl"
SEARCH_SUMMARY_PATH = SEARCH_ARTIFACT_DIR / "exit_policy_search_summary.json"
COHORT_SHADOW_PATH = SEARCH_ARTIFACT_DIR / "cohort_exit_policy_shadow_results.jsonl"
SEARCH_CHECKPOINT_DIR = SEARCH_ARTIFACT_DIR / "exit_policy_grid_checkpoints"
SEARCH_QUARANTINE_DIR = SEARCH_ARTIFACT_DIR / "quarantine"

STOPS = (-0.30, -0.50, -0.70)
TARGETS = (0.50, 1.00, 2.00)
HOLDS = (2, 3, 5)
MAX_HOLD = max(HOLDS)
TRAIN_END = "2021-12-31"
CURRENT_POLICY = {"stop": -0.50, "target": 1.00, "hold": 3}
MIN_PROMOTION_TRADES_PER_SPLIT = 100
CONFIDENCE_Z_95 = 1.959963984540054
GRID_CACHE_VERSION = "dopey-exit-policy-grid-cache-v2"


class SplitMetrics(TypedDict):
    net_pnl: float
    trade_count: int
    mean_pnl: float
    mean_ci_low: float
    mean_ci_high: float


class CohortMetrics(TypedDict):
    train: SplitMetrics
    validation: SplitMetrics


class ExitEvaluation(TypedDict):
    train: SplitMetrics
    validation: SplitMetrics
    cohorts: dict[str, CohortMetrics]


def run_exit_policy_walkforward_search() -> dict[str, Any]:
    signals = [
        record
        for record in load_directional_setup_signals(SIGNALS_PATH)
        if record.get("data_source_tier") == "local_real_history"
    ]
    if not signals:
        summary = {"artifact_type": "exit_policy_search_summary", "exit_search_status": "blocked_missing_real_signals"}
        _write_json(SEARCH_SUMMARY_PATH, summary)
        return summary
    intents = [
        intent
        for intent in map_signal_records_to_trade_intents(signals)["trade_intents"]
        if intent["candidate_strategy"] in {"long_call", "long_put"}
    ]
    bars_by_symbol = _real_bars_by_symbol()
    prepared: list[tuple[dict[str, Any], list[float], list[str], str]] = []
    for intent in intents:
        rows = bars_by_symbol.get(str(intent["symbol"]))
        if not rows:
            continue
        built = _build_real_marks(intent, rows, MAX_HOLD)
        if built is None:
            continue
        marks, mark_dates, path_id, _, _ = built
        prepared.append((intent, marks, mark_dates, path_id))
    input_fingerprint = _prepared_input_fingerprint(prepared)
    grid_seed, grid_selection_source = _load_or_build_grid(prepared, input_fingerprint)
    current_seed = next(cell for cell in grid_seed if cell["is_current_policy"])
    best_seed = max(grid_seed, key=lambda cell: cell["train_net_pnl"])
    current_evaluation = _evaluate(
        prepared,
        float(current_seed["stop"]),
        float(current_seed["target"]),
        int(current_seed["hold"]),
    )
    best_evaluation = _evaluate(
        prepared,
        float(best_seed["stop"]),
        float(best_seed["target"]),
        int(best_seed["hold"]),
    )
    current = _enrich_grid_cell(current_seed, current_evaluation)
    best_train = _enrich_grid_cell(best_seed, best_evaluation)
    grid = [
        current if _same_policy(cell, current) else best_train if _same_policy(cell, best_train) else cell
        for cell in grid_seed
    ]
    promoted, recommendation_status, requirement_checks = _promotion_assessment(best_train, current)
    relative_improvement = bool(
        requirement_checks["beats_current_train_net"]
        and requirement_checks["beats_current_validation_net"]
    )
    cohort_shadow_results = _build_pair_cohort_shadow_results(
        current_evaluation,
        best_evaluation,
        current,
        best_train,
    )
    summary = {
        "artifact_type": "exit_policy_search_summary",
        "exit_search_status": "exit_policy_search_complete",
        "prepared_intent_count": len(prepared),
        "grid_cells": len(grid),
        "grid_selection_source": grid_selection_source,
        "grid_cache_version": GRID_CACHE_VERSION,
        "input_fingerprint": input_fingerprint,
        "grid_reuse_limitation": (
            "the selected challenger comes from the prior complete grid; current and challenger metrics were freshly repriced, "
            "but no claim is made that the challenger remains the current global optimum"
        ),
        "train_window": f"<= {TRAIN_END}",
        "validation_window": f"> {TRAIN_END}",
        "current_policy": {**CURRENT_POLICY, "train_net_pnl": current["train_net_pnl"], "validation_net_pnl": current["validation_net_pnl"]},
        "best_train_policy": {
            key: best_train[key]
            for key in (
                "stop",
                "target",
                "hold",
                "train_net_pnl",
                "train_mean_pnl",
                "validation_net_pnl",
                "validation_mean_pnl",
                "validation_mean_ci_low",
                "validation_mean_ci_high",
            )
        },
        "recommendation_promoted": promoted,
        "recommendation_status": recommendation_status,
        "promotion_requirement_checks": requirement_checks,
        "recommendation": (
            {key: best_train[key] for key in ("stop", "target", "hold")}
            if promoted
            else "keep_current_policy_no_positive_out_of_sample_edge"
        ),
        "shadow_challenger": (
            {key: best_train[key] for key in ("stop", "target", "hold")}
            if relative_improvement and not promoted
            else None
        ),
        "cohort_shadow_result_count": len(cohort_shadow_results),
        "anti_overfit_rule": (
            "candidate must beat current policy in both splits, have positive train and validation mean P&L, "
            "have validation 95% mean CI above zero, and meet minimum split samples"
        ),
        "signals_untouched": True,
        "self_modification": "artifact_recommendation_only_operator_applies",
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    SEARCH_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(SEARCH_GRID_PATH, grid)
    _write_jsonl(COHORT_SHADOW_PATH, cohort_shadow_results)
    _write_json(SEARCH_SUMMARY_PATH, summary)
    return summary


def _expected_policies() -> set[tuple[float, float, int]]:
    return {
        (float(stop), float(target), int(hold))
        for stop in STOPS
        for target in TARGETS
        for hold in HOLDS
    }


def _policy_key(cell: dict[str, Any]) -> tuple[float, float, int]:
    return float(cell["stop"]), float(cell["target"]), int(cell["hold"])


def _load_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"exit-policy grid record must be an object: path={path}, line={line_number}")
        records.append(value)
    return records


def _grid_is_reusable(
    grid: list[dict[str, Any]],
    summary: dict[str, Any],
    prepared_intent_count: int,
    input_fingerprint: str,
) -> bool:
    actual_policies = {_policy_key(cell) for cell in grid}
    return bool(
        actual_policies == _expected_policies()
        and int(summary.get("prepared_intent_count", -1)) == prepared_intent_count
        and str(summary.get("input_fingerprint", "")) == input_fingerprint
        and str(summary.get("grid_cache_version", "")) == GRID_CACHE_VERSION
    )


def _prepared_input_fingerprint(
    prepared: list[tuple[dict[str, Any], list[float], list[str], str]],
) -> str:
    digest = hashlib.sha256()
    digest.update(GRID_CACHE_VERSION.encode("utf-8"))
    for intent, marks, mark_dates, path_id in prepared:
        payload = json.dumps(
            {
                "intent": intent,
                "marks": marks,
                "mark_dates": mark_dates,
                "path_id": path_id,
            },
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _quarantine_stale_grid(summary: dict[str, Any]) -> None:
    if not SEARCH_GRID_PATH.exists() and not SEARCH_SUMMARY_PATH.exists():
        return
    stale_identity = reproducibility_hash(
        {
            "summary": summary,
            "grid_sha256": (
                hashlib.sha256(SEARCH_GRID_PATH.read_bytes()).hexdigest()
                if SEARCH_GRID_PATH.exists()
                else "missing"
            ),
        }
    )[:24]
    target_dir = SEARCH_QUARANTINE_DIR / f"stale_exit_policy_grid_{stale_identity}"
    target_dir.mkdir(parents=True, exist_ok=True)
    if SEARCH_GRID_PATH.exists():
        (target_dir / SEARCH_GRID_PATH.name).write_bytes(SEARCH_GRID_PATH.read_bytes())
    if SEARCH_SUMMARY_PATH.exists():
        (target_dir / SEARCH_SUMMARY_PATH.name).write_bytes(SEARCH_SUMMARY_PATH.read_bytes())
    _write_json(
        target_dir / "quarantine_manifest.json",
        {
            "artifact_type": "stale_exit_policy_grid_quarantine",
            "quarantine_reason": "input_fingerprint_or_prepared_intent_count_changed",
            "automatic_promotion_allowed": False,
            "paper_only": True,
            "live_blocked": True,
        },
    )


def _checkpoint_path(input_fingerprint: str) -> Path:
    return SEARCH_CHECKPOINT_DIR / f"{input_fingerprint}.jsonl"


def _checkpoint_cell(
    prepared: list[tuple[dict[str, Any], list[float], list[str], str]],
    stop: float,
    target: float,
    hold: int,
    input_fingerprint: str,
) -> dict[str, Any]:
    evaluation = _evaluate(prepared, stop, target, hold)
    return _enrich_grid_cell(
        {
            "artifact_type": "exit_policy_search_cell",
            "stop": stop,
            "target": target,
            "hold": hold,
            "is_current_policy": (stop, target, hold) == (
                float(CURRENT_POLICY["stop"]),
                float(CURRENT_POLICY["target"]),
                int(CURRENT_POLICY["hold"]),
            ),
            "input_fingerprint": input_fingerprint,
            "grid_cache_version": GRID_CACHE_VERSION,
            "paper_only": True,
            "live_blocked": True,
        },
        evaluation,
    )


def _load_or_build_grid(
    prepared: list[tuple[dict[str, Any], list[float], list[str], str]],
    input_fingerprint: str,
) -> tuple[list[dict[str, Any]], str]:
    existing_grid = _load_jsonl_objects(SEARCH_GRID_PATH)
    existing_summary: dict[str, Any] = {}
    if SEARCH_SUMMARY_PATH.exists():
        loaded_summary = json.loads(SEARCH_SUMMARY_PATH.read_text(encoding="utf-8"))
        if not isinstance(loaded_summary, dict):
            raise TypeError(f"exit-policy summary must be an object: path={SEARCH_SUMMARY_PATH}")
        existing_summary = loaded_summary
    if _grid_is_reusable(existing_grid, existing_summary, len(prepared), input_fingerprint):
        return existing_grid, "content_addressed_complete_grid_reused_then_current_and_challenger_repriced"
    _quarantine_stale_grid(existing_summary)
    checkpoint_path = _checkpoint_path(input_fingerprint)
    checkpoint_records = _load_jsonl_objects(checkpoint_path)
    valid_checkpoint = {
        _policy_key(cell): cell
        for cell in checkpoint_records
        if str(cell.get("input_fingerprint", "")) == input_fingerprint
        and str(cell.get("grid_cache_version", "")) == GRID_CACHE_VERSION
        and _policy_key(cell) in _expected_policies()
    }
    for stop, target, hold in sorted(_expected_policies()):
        policy = (stop, target, hold)
        if policy in valid_checkpoint:
            continue
        valid_checkpoint[policy] = _checkpoint_cell(
            prepared,
            stop,
            target,
            hold,
            input_fingerprint,
        )
        _write_jsonl(checkpoint_path, [valid_checkpoint[key] for key in sorted(valid_checkpoint)])
    grid = [valid_checkpoint[key] for key in sorted(valid_checkpoint)]
    if {_policy_key(cell) for cell in grid} != _expected_policies():
        raise ValueError("exit-policy checkpoint did not produce the complete governed policy grid")
    return grid, "content_addressed_grid_rebuilt_or_resumed_from_checkpoint"


def _enrich_grid_cell(cell: dict[str, Any], evaluation: ExitEvaluation) -> dict[str, Any]:
    return {
        **cell,
        "train_net_pnl": evaluation["train"]["net_pnl"],
        "train_trades": evaluation["train"]["trade_count"],
        "train_mean_pnl": evaluation["train"]["mean_pnl"],
        "train_mean_ci_low": evaluation["train"]["mean_ci_low"],
        "train_mean_ci_high": evaluation["train"]["mean_ci_high"],
        "validation_net_pnl": evaluation["validation"]["net_pnl"],
        "validation_trades": evaluation["validation"]["trade_count"],
        "validation_mean_pnl": evaluation["validation"]["mean_pnl"],
        "validation_mean_ci_low": evaluation["validation"]["mean_ci_low"],
        "validation_mean_ci_high": evaluation["validation"]["mean_ci_high"],
    }


def _same_policy(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return (
        float(first["stop"]),
        float(first["target"]),
        int(first["hold"]),
    ) == (
        float(second["stop"]),
        float(second["target"]),
        int(second["hold"]),
    )


def _evaluate(
    prepared: list[tuple[dict[str, Any], list[float], list[str], str]],
    stop: float,
    target: float,
    hold: int,
) -> ExitEvaluation:
    config = BacktestExitConfig(premium_stop_pct=stop, premium_target_pct=target, max_holding_steps=hold)
    train_pnls: list[float] = []
    validation_pnls: list[float] = []
    cohort_pnls: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"train": [], "validation": []})
    for intent, marks, mark_dates, path_id in prepared:
        simulated = simulate_intent_with_marks(intent, marks, mark_dates, path_id, "valid_real_dataset", config)
        for record in simulated["trade_records"]:
            costed = apply_trade_costs(record)
            pnl = float(costed["path_pnl"])
            cohort_id = f"{intent['signal_family']}|{intent['candidate_strategy']}"
            if str(costed.get("entry_date", "")) <= TRAIN_END:
                train_pnls.append(pnl)
                cohort_pnls[cohort_id]["train"].append(pnl)
            else:
                validation_pnls.append(pnl)
                cohort_pnls[cohort_id]["validation"].append(pnl)
    return {
        "train": _split_metrics(train_pnls),
        "validation": _split_metrics(validation_pnls),
        "cohorts": {
            cohort_id: {
                "train": _split_metrics(values["train"]),
                "validation": _split_metrics(values["validation"]),
            }
            for cohort_id, values in sorted(cohort_pnls.items())
        },
    }


def _split_metrics(values: list[float]) -> SplitMetrics:
    count = len(values)
    total = sum(values)
    mean = total / count if count else 0.0
    if count < 2:
        margin = 0.0
    else:
        variance = sum((value - mean) ** 2 for value in values) / (count - 1)
        margin = CONFIDENCE_Z_95 * math.sqrt(variance / count)
    return {
        "net_pnl": round(total, 6),
        "trade_count": count,
        "mean_pnl": round(mean, 6),
        "mean_ci_low": round(mean - margin, 6),
        "mean_ci_high": round(mean + margin, 6),
    }


def _promotion_assessment(
    candidate: dict[str, Any],
    current: dict[str, Any],
) -> tuple[bool, str, dict[str, bool]]:
    checks = {
        "beats_current_train_net": float(candidate["train_net_pnl"]) > float(current["train_net_pnl"]),
        "beats_current_validation_net": float(candidate["validation_net_pnl"]) > float(current["validation_net_pnl"]),
        "train_mean_positive": float(candidate["train_mean_pnl"]) > 0.0,
        "validation_mean_positive": float(candidate["validation_mean_pnl"]) > 0.0,
        "validation_mean_ci_low_positive": float(candidate["validation_mean_ci_low"]) > 0.0,
        "train_sample_sufficient": int(candidate["train_trades"]) >= MIN_PROMOTION_TRADES_PER_SPLIT,
        "validation_sample_sufficient": int(candidate["validation_trades"]) >= MIN_PROMOTION_TRADES_PER_SPLIT,
    }
    promoted = all(checks.values())
    relative_improvement = checks["beats_current_train_net"] and checks["beats_current_validation_net"]
    status = "promotion_eligible" if promoted else ("relative_improvement_only" if relative_improvement else "no_out_of_era_improvement")
    return promoted, status, checks


def _build_pair_cohort_shadow_results(
    current_evaluation: ExitEvaluation,
    best_evaluation: ExitEvaluation,
    current_policy: dict[str, Any],
    best_policy: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cohort_ids = sorted(set(current_evaluation["cohorts"]) | set(best_evaluation["cohorts"]))
    for cohort_id in cohort_ids:
        current_metrics = current_evaluation["cohorts"][cohort_id]
        best_metrics = best_evaluation["cohorts"][cohort_id]
        current = _cohort_policy_cell(current_policy, current_metrics)
        best_train = _cohort_policy_cell(best_policy, best_metrics)
        promoted, status, checks = _promotion_assessment(best_train, current)
        results.append(
            {
                "artifact_type": "cohort_exit_policy_shadow_result",
                "cohort_id": cohort_id,
                "current_policy": {
                    **CURRENT_POLICY,
                    "train_net_pnl": current["train_net_pnl"],
                    "validation_net_pnl": current["validation_net_pnl"],
                },
                "shadow_challenger": {
                    key: best_train[key]
                    for key in (
                        "stop",
                        "target",
                        "hold",
                        "train_net_pnl",
                        "train_mean_pnl",
                        "validation_net_pnl",
                        "validation_mean_pnl",
                        "validation_mean_ci_low",
                        "validation_mean_ci_high",
                    )
                },
                "exit_policy_status": status,
                "local_exit_promotion_eligible": promoted,
                "promotion_requirement_checks": checks,
                "application_mode": "shadow_only_pending_baseline_era_and_forward_gates",
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return results


def _cohort_policy_cell(policy: dict[str, Any], metrics: CohortMetrics) -> dict[str, Any]:
    return {
        "stop": float(policy["stop"]),
        "target": float(policy["target"]),
        "hold": int(policy["hold"]),
        "train_net_pnl": metrics["train"]["net_pnl"],
        "train_trades": metrics["train"]["trade_count"],
        "train_mean_pnl": metrics["train"]["mean_pnl"],
        "train_mean_ci_low": metrics["train"]["mean_ci_low"],
        "train_mean_ci_high": metrics["train"]["mean_ci_high"],
        "validation_net_pnl": metrics["validation"]["net_pnl"],
        "validation_trades": metrics["validation"]["trade_count"],
        "validation_mean_pnl": metrics["validation"]["mean_pnl"],
        "validation_mean_ci_low": metrics["validation"]["mean_ci_low"],
        "validation_mean_ci_high": metrics["validation"]["mean_ci_high"],
    }


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    temporary_path.replace(path)
