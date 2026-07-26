"""Deterministic, source-backed strategy evidence dossiers for DOPEY research."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import os
import statistics
import subprocess
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, cast

from dopey_backtest.trade_records_recovery import (
    BACKTEST_TRADE_RECORDS_INCIDENT,
    VerifiedLedgerResolution,
    resolve_verified_trade_ledger,
)


STRATEGY_EVIDENCE_DOSSIER_VERSION = "dopey-strategy-evidence-dossier-v2"
DOSSIER_EVALUATOR_VERSION = "dopey-evidence-gates-pareto-v2"
MINIMUM_OOS_TRADE_COUNT = 100
STRESSED_COST_MULTIPLIER = 2.0


def build_strategy_evidence_dossier(
    repository_root: Path,
    source_paths: Mapping[str, Path],
    runs_root: Path,
    latest_summary_path: Path,
) -> dict[str, object]:
    """Build or reuse one content-addressed evidence dossier."""

    required_keys = {
        "backtest_summary",
        "trades",
        "folds",
        "metric_set",
        "bootstrap",
        "deflated_sharpe",
        "multiple_testing",
        "truth_decision",
        "baseline_summary",
        "fitness_decision",
        "mutation_registry",
    }
    missing_keys = sorted(required_keys - set(source_paths))
    if missing_keys:
        raise KeyError(f"strategy dossier source path mapping is incomplete: missing_keys={missing_keys}")
    resolved_sources = {key: path.resolve() for key, path in source_paths.items()}
    ledger_resolution = _resolve_canonical_trade_ledger(
        repository_root,
        resolved_sources,
    )
    if ledger_resolution is not None:
        resolved_sources["trades"] = Path(ledger_resolution["resolved_path"])
    source_hashes = {key: _required_file_hash(path) for key, path in sorted(resolved_sources.items())}
    gate_config = {
        "minimum_oos_trade_count": MINIMUM_OOS_TRADE_COUNT,
        "stressed_cost_multiplier": STRESSED_COST_MULTIPLIER,
        "eligibility_rule": "all_hard_gates_must_pass",
        "ranking_rule": "eligible_first_then_lexicographic_lower_bound_order",
        "pareto_rule": "nondominated_on_declared_comparable_model_unit_dimensions",
    }
    source_identity = {
        "version": STRATEGY_EVIDENCE_DOSSIER_VERSION,
        "evaluator_version": DOSSIER_EVALUATOR_VERSION,
        "source_hashes": source_hashes,
        "gate_config": gate_config,
    }
    run_id = f"dossier-{_stable_hash(source_identity)[:20]}"
    run_directory = runs_root.resolve() / run_id
    cached_summary = run_directory / "summary.json"
    if cached_summary.is_file():
        summary = _read_json_object(cached_summary)
        if str(summary.get("run_id", "")) != run_id:
            raise ValueError(f"cached strategy dossier run_id mismatch: path={cached_summary}, expected={run_id}")
        latest = dict(summary)
        latest["cache_status"] = "content_addressed_cache_hit"
        latest["run_directory"] = str(run_directory)
        _write_json_atomic(latest_summary_path, latest)
        _publish_latest_capital_exposure(run_directory, latest_summary_path.parent)
        return latest

    temporary_directory = runs_root.resolve() / f".{run_id}.building-{os.getpid()}"
    if temporary_directory.exists():
        raise FileExistsError(f"strategy dossier temporary directory already exists: path={temporary_directory}")
    temporary_directory.mkdir(parents=True, exist_ok=False)

    backtest_summary = _read_json_object(resolved_sources["backtest_summary"])
    metric_set = _read_json_object(resolved_sources["metric_set"])
    bootstrap = _read_json_object(resolved_sources["bootstrap"])
    deflated_sharpe = _read_json_object(resolved_sources["deflated_sharpe"])
    multiple_testing = _read_json_object(resolved_sources["multiple_testing"])
    truth_decision = _read_json_object(resolved_sources["truth_decision"])
    baseline_summary = _read_json_object(resolved_sources["baseline_summary"])
    fitness_decision = _read_json_object(resolved_sources["fitness_decision"])
    fold_records = list(_read_jsonl_objects(resolved_sources["folds"]))
    mutation_search = _mutation_trial_summary(resolved_sources["mutation_registry"])

    trade_output_path = temporary_directory / "trades.csv"
    stream_result = _stream_trade_evidence(
        resolved_sources["trades"],
        trade_output_path,
        (
            ledger_resolution["resolved_sha256"]
            if ledger_resolution is not None
            else None
        ),
        ledger_resolution["record_count"] if ledger_resolution is not None else None,
    )
    expected_trade_count = _required_int(backtest_summary, "trade_record_count")
    if int(stream_result["trade_count"]) != expected_trade_count:
        raise ValueError(
            "strategy dossier trade count does not match the backtest summary: "
            f"streamed={stream_result['trade_count']}, expected={expected_trade_count}"
        )
    candidate_records = _candidate_scorecards(
        cast(dict[str, dict[str, object]], stream_result["candidate_accumulators"]),
        fold_records,
        baseline_summary,
        backtest_summary,
    )
    eligible_candidates = [record for record in candidate_records if bool(record["eligible"])]
    frontier_source = eligible_candidates if eligible_candidates else candidate_records
    frontier_ids = _pareto_frontier(frontier_source)
    frontier_status = "eligible_pareto_frontier" if eligible_candidates else "diagnostic_only_no_eligible_candidates"
    ranked_candidates = sorted(candidate_records, key=_candidate_lexicographic_key)
    capital_exposure = _capital_exposure_artifact(run_id, ranked_candidates)

    equity_curve = _build_equity_curve(cast(dict[str, dict[str, float]], stream_result["daily_totals"]))
    drawdown_episodes = _drawdown_episodes(equity_curve)
    exposures = _exposure_rows(cast(dict[tuple[str, str, str], dict[str, float]], stream_result["exposures"]))
    robustness_rows = _robustness_rows(
        candidate_records,
        metric_set,
        bootstrap,
        deflated_sharpe,
        multiple_testing,
        truth_decision,
    )
    failure_modes = _failure_modes(candidate_records, truth_decision, backtest_summary, fitness_decision)

    _write_csv(temporary_directory / "fold_metrics.csv", _fold_rows(fold_records))
    _write_csv(temporary_directory / "equity_curve.csv", equity_curve)
    _write_csv(temporary_directory / "drawdowns.csv", drawdown_episodes)
    _write_csv(temporary_directory / "exposure_analysis.csv", exposures)
    _write_csv(temporary_directory / "robustness_tests.csv", robustness_rows)
    _write_csv(
        temporary_directory / "pareto_frontier.csv",
        [record for record in ranked_candidates if str(record["candidate_id"]) in frontier_ids],
    )
    _write_json(temporary_directory / "strategy_scorecards.json", {
        "artifact_type": "strategy_evidence_scorecards",
        "run_id": run_id,
        "ranking_policy": gate_config["ranking_rule"],
        "candidates": ranked_candidates,
        "paper_only": True,
        "live_blocked": True,
    })
    _write_json(temporary_directory / "failure_modes.json", failure_modes)
    _write_json(temporary_directory / "capital_exposure.json", capital_exposure)
    _write_csv(
        temporary_directory / "capital_exposure.csv",
        cast(list[dict[str, object]], capital_exposure["candidate_diagnostics"]),
    )
    _write_json(
        temporary_directory / "candidate_partition_manifest.json",
        _candidate_partition_manifest(run_id, cast(dict[str, dict[str, object]], stream_result["candidate_accumulators"])),
    )

    truth_state = {
        "history_dataset_status": str(backtest_summary.get("history_dataset_status", "unknown")),
        "real_history_used": bool(backtest_summary.get("real_history_used", False)),
        "pricing_source_distribution": backtest_summary.get("pricing_source_tier_distribution", {}),
        "real_option_chain_used": bool(backtest_summary.get("real_option_chain_used", False)),
        "truth_decision": str(truth_decision.get("truth_decision", "unknown")),
        "fitness_decision": str(fitness_decision.get("fitness_decision", "unknown")),
        "promotion_allowed": False,
        "profitability_claim_allowed": False,
    }
    summary: dict[str, object] = {
        "artifact_type": "strategy_evidence_dossier_summary",
        "dossier_version": STRATEGY_EVIDENCE_DOSSIER_VERSION,
        "evaluator_version": DOSSIER_EVALUATOR_VERSION,
        "run_id": run_id,
        "dossier_status": "complete_no_eligible_candidates" if not eligible_candidates else "complete_research_eligible_candidates",
        "headline": _dossier_headline(candidate_records, eligible_candidates, truth_state),
        "candidate_count": len(candidate_records),
        "eligible_candidate_count": len(eligible_candidates),
        "diagnostic_frontier_count": len(frontier_ids),
        "frontier_status": frontier_status,
        "frontier_candidate_ids": sorted(frontier_ids),
        "trade_count": int(stream_result["trade_count"]),
        "source_trade_hash": str(stream_result["source_trade_hash"]),
        "gross_model_unit_pnl": round(float(stream_result["gross_model_unit_pnl"]), 6),
        "net_model_unit_pnl": round(float(stream_result["net_model_unit_pnl"]), 6),
        "total_cost_model_units": round(float(stream_result["total_cost_model_units"]), 6),
        "annualized_return": None,
        "annualized_return_unavailable_reason": "model_unit_pnl_has_no_valid_capital_denominator",
        "calmar_ratio": None,
        "calmar_unavailable_reason": "return_and_drawdown_are_not_in_comparable_capital_normalized_units",
        "capital_normalization": {
            "status": capital_exposure["normalization_status"],
            "denominator": "entry_premium_model_units",
            "diagnostic_only": True,
            "real_capital_denominator_available": False,
            "artifact": "capital_exposure.json",
        },
        "truth_state": truth_state,
        "selection_risk": {
            "effective_trials": deflated_sharpe.get("effective_trials"),
            "deflated_sharpe_model_units": deflated_sharpe.get("deflated_sharpe_model_units"),
            "diagnostic_only": bool(deflated_sharpe.get("diagnostic_only", True)),
            "mutation_registry_records": mutation_search["registry_record_count"],
            "mutation_attempts_recorded": mutation_search["mutation_attempt_count"],
        },
        "gate_config": gate_config,
        "source_hashes": source_hashes,
        "paper_only": True,
        "live_blocked": True,
        "not_profitability_claim": True,
        "promotion_allowed": False,
    }
    summary["summary_hash"] = _stable_hash(summary)
    _write_json(temporary_directory / "summary.json", summary)
    (temporary_directory / "report.html").write_text(
        _render_report_html(summary, ranked_candidates, frontier_ids, drawdown_episodes),
        encoding="utf-8",
    )

    revision = _repository_revision(repository_root)
    artifact_hashes = {
        path.name: _required_file_hash(path)
        for path in sorted(temporary_directory.iterdir(), key=lambda item: item.name)
        if path.is_file()
    }
    manifest: dict[str, object] = {
        "artifact_type": "strategy_evidence_dossier_manifest",
        "dossier_version": STRATEGY_EVIDENCE_DOSSIER_VERSION,
        "run_id": run_id,
        "data_snapshot_hash": _stable_hash(source_hashes),
        "configuration_hash": _stable_hash(gate_config),
        "source_paths": {key: str(path) for key, path in sorted(resolved_sources.items())},
        "source_hashes": source_hashes,
        "artifact_hashes": artifact_hashes,
        "code_revision": revision,
        "evaluator_version": DOSSIER_EVALUATOR_VERSION,
        "reproduction_command": ".venv\\Scripts\\python.exe -m dopey_reporting.run_strategy_evidence_dossier",
        "paper_only": True,
        "live_blocked": True,
    }
    manifest["manifest_hash"] = _stable_hash(manifest)
    _write_json(temporary_directory / "manifest.json", manifest)
    temporary_directory.replace(run_directory)

    latest = dict(summary)
    latest["cache_status"] = "content_addressed_run_built"
    latest["run_directory"] = str(run_directory)
    latest["manifest_hash"] = str(manifest["manifest_hash"])
    _write_json_atomic(latest_summary_path, latest)
    _publish_latest_capital_exposure(run_directory, latest_summary_path.parent)
    return latest


def default_dossier_source_paths(repository_root: Path) -> dict[str, Path]:
    """Return the canonical evidence inputs without performing any reads."""

    root = repository_root.resolve()
    return {
        "backtest_summary": root / "artifacts" / "dopey" / "backtest" / "backtest_run_summary.json",
        "trades": root / "artifacts" / "dopey" / "backtest" / "backtest_trade_records.jsonl",
        "folds": root / "artifacts" / "dopey" / "backtest" / "era_walk_forward_cohort_stats.jsonl",
        "metric_set": root / "artifacts" / "dopey" / "stats" / "backtest_metric_set.json",
        "bootstrap": root / "artifacts" / "dopey" / "stats" / "bootstrap_confidence_intervals.json",
        "deflated_sharpe": root / "artifacts" / "dopey" / "stats" / "deflated_sharpe_result.json",
        "multiple_testing": root / "artifacts" / "dopey" / "stats" / "multiple_testing_adjustment.json",
        "truth_decision": root / "artifacts" / "dopey" / "stats" / "statistical_truth_decision.json",
        "baseline_summary": root / "artifacts" / "dopey" / "backtest" / "baseline_arbitration_summary.json",
        "fitness_decision": root / "artifacts" / "dopey" / "fitness" / "fitness_decision.json",
        "mutation_registry": root / "artifacts" / "dopey" / "mutations" / "mutation_registry.jsonl",
    }


def _resolve_canonical_trade_ledger(
    repository_root: Path,
    resolved_sources: Mapping[str, Path],
) -> VerifiedLedgerResolution | None:
    root = repository_root.resolve()
    backtest_root = root / "artifacts" / "dopey" / "backtest"
    canonical_trades = backtest_root / "backtest_trade_records.jsonl"
    canonical_summary = backtest_root / "backtest_run_summary.json"
    if (
        resolved_sources["trades"] != canonical_trades.resolve()
        or resolved_sources["backtest_summary"] != canonical_summary.resolve()
    ):
        return None
    return resolve_verified_trade_ledger(
        canonical_trades,
        backtest_root / "backtest_trade_records.recovered.jsonl",
        backtest_root / "backtest_trade_records.recovery_manifest.json",
        (canonical_summary, backtest_root / "backtest_proof.jsonl"),
        BACKTEST_TRADE_RECORDS_INCIDENT,
    )


def _stream_trade_evidence(
    source_path: Path,
    output_path: Path,
    expected_source_sha256: str | None,
    expected_record_count: int | None,
) -> dict[str, object]:
    candidate_accumulators: dict[str, dict[str, object]] = {}
    daily_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"net": 0.0, "gross": 0.0, "cost": 0.0, "trades": 0.0})
    exposures: dict[tuple[str, str, str], dict[str, float]] = defaultdict(lambda: {"trade_count": 0.0, "net_pnl": 0.0})
    digest = hashlib.sha256()
    trade_count = 0
    gross_total = 0.0
    net_total = 0.0
    cost_total = 0.0
    fieldnames = (
        "trade_id",
        "candidate_id",
        "symbol",
        "direction",
        "signal_family",
        "option_structure",
        "entry_date",
        "exit_date",
        "holding_steps",
        "gross_model_unit_pnl",
        "cost_model_units",
        "net_model_unit_pnl",
        "trade_return_model_units",
        "entry_premium_model_units",
        "outcome",
        "pricing_source_tier",
        "data_source_tier",
    )
    with source_path.open("rb") as source, output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for line_number, raw_line in enumerate(source, start=1):
            digest.update(raw_line)
            if not raw_line.strip():
                continue
            try:
                parsed = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid trade JSONL: path={source_path}, line={line_number}, error={error}") from error
            if not isinstance(parsed, dict):
                raise TypeError(f"trade JSONL row must be an object: path={source_path}, line={line_number}")
            record = cast(dict[str, object], parsed)
            signal_family = _required_string(record, "signal_family")
            option_structure = _required_string(record, "option_structure")
            candidate_id = f"{signal_family}|{option_structure}"
            symbol = _required_string(record, "symbol")
            direction = _required_string(record, "direction")
            entry_date = _required_string(record, "entry_date")
            exit_date = _required_string(record, "exit_date")
            net_pnl = _required_float(record, "path_pnl")
            gross_pnl = _required_float(record, "path_pnl_gross_mid")
            cost = _required_float(record, "trade_cost_premium_units")
            holding_steps = _required_int(record, "holding_steps")
            entry_premium = _optional_positive_float(record, "entry_premium")
            accumulator = candidate_accumulators.setdefault(candidate_id, _new_candidate_accumulator(candidate_id, signal_family, option_structure))
            cast(Any, accumulator["partition_digest"]).update(raw_line)
            _accumulate_candidate(
                accumulator,
                record,
                net_pnl,
                gross_pnl,
                cost,
                holding_steps,
                entry_date,
                exit_date,
                symbol,
                entry_premium,
            )
            daily = daily_totals[exit_date]
            daily["net"] += net_pnl
            daily["gross"] += gross_pnl
            daily["cost"] += cost
            daily["trades"] += 1.0
            for axis, key in (("symbol", symbol), ("direction", direction), ("signal_family", signal_family), ("structure", option_structure)):
                exposure = exposures[(candidate_id, axis, key)]
                exposure["trade_count"] += 1.0
                exposure["net_pnl"] += net_pnl
            writer.writerow({
                "trade_id": _required_string(record, "trade_id"),
                "candidate_id": candidate_id,
                "symbol": symbol,
                "direction": direction,
                "signal_family": signal_family,
                "option_structure": option_structure,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "holding_steps": holding_steps,
                "gross_model_unit_pnl": round(gross_pnl, 6),
                "cost_model_units": round(cost, 6),
                "net_model_unit_pnl": round(net_pnl, 6),
                "trade_return_model_units": record.get("trade_return_model_units"),
                "entry_premium_model_units": round(entry_premium, 6) if entry_premium is not None else None,
                "outcome": record.get("win_loss_marker"),
                "pricing_source_tier": record.get("pricing_source_tier"),
                "data_source_tier": record.get("data_source_tier"),
            })
            trade_count += 1
            gross_total += gross_pnl
            net_total += net_pnl
            cost_total += cost
    observed_source_sha256 = digest.hexdigest()
    if (
        expected_source_sha256 is not None
        and observed_source_sha256 != expected_source_sha256
    ):
        raise ValueError(
            "strategy dossier trade source changed after ledger resolution: "
            f"path={source_path}, expected_sha256={expected_source_sha256}, "
            f"observed_sha256={observed_source_sha256}"
        )
    if expected_record_count is not None and trade_count != expected_record_count:
        raise ValueError(
            "strategy dossier trade count changed after ledger resolution: "
            f"path={source_path}, expected={expected_record_count}, "
            f"observed={trade_count}"
        )
    return {
        "trade_count": trade_count,
        "source_trade_hash": observed_source_sha256,
        "gross_model_unit_pnl": gross_total,
        "net_model_unit_pnl": net_total,
        "total_cost_model_units": cost_total,
        "candidate_accumulators": candidate_accumulators,
        "daily_totals": dict(daily_totals),
        "exposures": dict(exposures),
    }


def _new_candidate_accumulator(candidate_id: str, signal_family: str, option_structure: str) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "signal_family": signal_family,
        "option_structure": option_structure,
        "trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "net_pnl": 0.0,
        "gross_pnl": 0.0,
        "cost": 0.0,
        "holding_steps": 0,
        "positive_pnl": 0.0,
        "negative_pnl": 0.0,
        "pnl_values": [],
        "daily_pnl": {},
        "symbols": set(),
        "pricing_tiers": defaultdict(int),
        "entry_premium_total": 0.0,
        "entry_premium_values": [],
        "trade_return_on_entry_premium_values": [],
        "entry_capital_events": defaultdict(lambda: {"premium": 0.0, "positions": 0}),
        "exit_capital_events": defaultdict(lambda: {"premium": 0.0, "positions": 0}),
        "capital_denominator_trade_count": 0,
        "partition_digest": hashlib.sha256(),
    }


def _accumulate_candidate(
    accumulator: dict[str, object],
    record: Mapping[str, object],
    net_pnl: float,
    gross_pnl: float,
    cost: float,
    holding_steps: int,
    entry_date: str,
    exit_date: str,
    symbol: str,
    entry_premium: float | None,
) -> None:
    accumulator["trade_count"] = int(accumulator["trade_count"]) + 1
    accumulator["win_count"] = int(accumulator["win_count"]) + (1 if net_pnl > 0.0 else 0)
    accumulator["loss_count"] = int(accumulator["loss_count"]) + (1 if net_pnl < 0.0 else 0)
    accumulator["net_pnl"] = float(accumulator["net_pnl"]) + net_pnl
    accumulator["gross_pnl"] = float(accumulator["gross_pnl"]) + gross_pnl
    accumulator["cost"] = float(accumulator["cost"]) + cost
    accumulator["holding_steps"] = int(accumulator["holding_steps"]) + holding_steps
    accumulator["positive_pnl"] = float(accumulator["positive_pnl"]) + max(net_pnl, 0.0)
    accumulator["negative_pnl"] = float(accumulator["negative_pnl"]) + min(net_pnl, 0.0)
    cast(list[float], accumulator["pnl_values"]).append(net_pnl)
    daily_pnl = cast(dict[str, float], accumulator["daily_pnl"])
    daily_pnl[exit_date] = daily_pnl.get(exit_date, 0.0) + net_pnl
    cast(set[str], accumulator["symbols"]).add(symbol)
    pricing_tiers = cast(dict[str, int], accumulator["pricing_tiers"])
    tier = str(record.get("pricing_source_tier", "unknown"))
    pricing_tiers[tier] = pricing_tiers.get(tier, 0) + 1
    if entry_premium is not None:
        accumulator["entry_premium_total"] = float(accumulator["entry_premium_total"]) + entry_premium
        cast(list[float], accumulator["entry_premium_values"]).append(entry_premium)
        cast(list[float], accumulator["trade_return_on_entry_premium_values"]).append(net_pnl / entry_premium)
        accumulator["capital_denominator_trade_count"] = int(accumulator["capital_denominator_trade_count"]) + 1
        entry_events = cast(dict[str, dict[str, float | int]], accumulator["entry_capital_events"])
        exit_events = cast(dict[str, dict[str, float | int]], accumulator["exit_capital_events"])
        entry_event = entry_events[entry_date]
        exit_event = exit_events[exit_date]
        entry_event["premium"] = float(entry_event["premium"]) + entry_premium
        entry_event["positions"] = int(entry_event["positions"]) + 1
        exit_event["premium"] = float(exit_event["premium"]) + entry_premium
        exit_event["positions"] = int(exit_event["positions"]) + 1


def _candidate_scorecards(
    accumulators: Mapping[str, dict[str, object]],
    fold_records: Sequence[dict[str, object]],
    baseline_summary: Mapping[str, object],
    backtest_summary: Mapping[str, object],
) -> list[dict[str, object]]:
    folds_by_candidate: dict[str, list[dict[str, object]]] = defaultdict(list)
    for fold in fold_records:
        candidate_id = str(fold.get("cohort_id", ""))
        if candidate_id:
            folds_by_candidate[candidate_id].append(fold)
    raw_baselines = baseline_summary.get("baseline_net_by_cohort", {})
    baseline_net = cast(dict[str, object], raw_baselines) if isinstance(raw_baselines, dict) else {}
    blocked_policy_violations = int(backtest_summary.get("blocked_policy_violation_count", 0))
    real_option_chain_used = bool(backtest_summary.get("real_option_chain_used", False))
    records: list[dict[str, object]] = []
    for candidate_id, accumulator in sorted(accumulators.items()):
        pnl_values = sorted(cast(list[float], accumulator["pnl_values"]))
        trade_count = int(accumulator["trade_count"])
        net_pnl = float(accumulator["net_pnl"])
        gross_pnl = float(accumulator["gross_pnl"])
        cost = float(accumulator["cost"])
        mean = net_pnl / trade_count
        stddev = statistics.stdev(pnl_values) if trade_count > 1 else 0.0
        downside = [min(value, 0.0) for value in pnl_values]
        downside_deviation = math.sqrt(sum(value * value for value in downside) / trade_count)
        candidate_folds = folds_by_candidate.get(candidate_id, [])
        fold_expectancies = [float(fold.get("average_pnl", 0.0)) for fold in candidate_folds]
        positive_folds = sum(1 for value in fold_expectancies if value > 0.0)
        fold_required = max(2, math.ceil(len(fold_expectancies) * 0.67)) if fold_expectancies else 1
        candidate_baseline = float(baseline_net.get(candidate_id, 0.0))
        baseline_delta = net_pnl - candidate_baseline
        stressed_cost_expectancy = (gross_pnl - STRESSED_COST_MULTIPLIER * cost) / trade_count
        equity_curve = _build_equity_curve({key: {"net": value, "gross": value, "cost": 0.0, "trades": 0.0} for key, value in cast(dict[str, float], accumulator["daily_pnl"]).items()})
        max_drawdown = min((float(row["drawdown_model_units"]) for row in equity_curve), default=0.0)
        capital = _candidate_capital_diagnostics(accumulator, max_drawdown)
        gates = [
            _gate("minimum_oos_trade_count", trade_count >= MINIMUM_OOS_TRADE_COUNT, trade_count, MINIMUM_OOS_TRADE_COUNT),
            _gate("positive_after_stressed_costs", stressed_cost_expectancy > 0.0, stressed_cost_expectancy, 0.0),
            _gate("matched_baseline_superiority", baseline_delta > 0.0, baseline_delta, 0.0),
            _gate("walk_forward_fold_stability", positive_folds >= fold_required, positive_folds, fold_required),
            _gate("no_policy_or_catastrophic_fixture_failure", blocked_policy_violations == 0, blocked_policy_violations, 0),
            _gate("real_option_quote_evidence", real_option_chain_used, int(real_option_chain_used), 1),
            {
                "gate_id": "declared_drawdown_budget_compliance",
                "status": "unavailable",
                "observed": capital["max_drawdown_to_peak_model_premium"],
                "required": "operator_declared_real_capital_drawdown_budget",
                "reason": "model_premium_exposure_is_diagnostic_and_not_a_real_capital_budget",
            },
        ]
        eligible = all(str(gate["status"]) == "pass" for gate in gates)
        records.append({
            "candidate_id": candidate_id,
            "signal_family": accumulator["signal_family"],
            "option_structure": accumulator["option_structure"],
            "trade_count": trade_count,
            "symbol_count": len(cast(set[str], accumulator["symbols"])),
            "net_model_unit_pnl": round(net_pnl, 6),
            "gross_model_unit_pnl": round(gross_pnl, 6),
            "total_cost_model_units": round(cost, 6),
            "expectancy_model_units": round(mean, 6),
            "stressed_cost_expectancy_model_units": round(stressed_cost_expectancy, 6),
            "win_rate": round(int(accumulator["win_count"]) / trade_count, 6),
            "profit_factor": round(float(accumulator["positive_pnl"]) / abs(float(accumulator["negative_pnl"])), 6) if float(accumulator["negative_pnl"]) < 0.0 else None,
            "average_win_model_units": round(float(accumulator["positive_pnl"]) / max(int(accumulator["win_count"]), 1), 6),
            "average_loss_model_units": round(float(accumulator["negative_pnl"]) / max(int(accumulator["loss_count"]), 1), 6),
            "average_holding_steps": round(int(accumulator["holding_steps"]) / trade_count, 3),
            "per_trade_sharpe_like": round(mean / stddev, 6) if stddev > 0.0 else None,
            "per_trade_sortino_like": round(mean / downside_deviation, 6) if downside_deviation > 0.0 else None,
            "max_drawdown_model_units": round(max_drawdown, 6),
            "capital_diagnostics": capital,
            "tail_loss_p05_model_units": round(_quantile(pnl_values, 0.05), 6),
            "worst_trade_model_units": round(pnl_values[0], 6),
            "fold_count": len(fold_expectancies),
            "positive_fold_count": positive_folds,
            "worst_fold_expectancy_model_units": round(min(fold_expectancies), 6) if fold_expectancies else None,
            "fold_expectancy_dispersion": round(statistics.pstdev(fold_expectancies), 6) if len(fold_expectancies) > 1 else 0.0,
            "matched_baseline_net_model_units": round(candidate_baseline, 6),
            "matched_baseline_delta_model_units": round(baseline_delta, 6),
            "pricing_source_tiers": dict(sorted(cast(dict[str, int], accumulator["pricing_tiers"]).items())),
            "hard_gates": gates,
            "gate_failure_count": sum(1 for gate in gates if str(gate["status"]) != "pass"),
            "eligible": eligible,
            "promotion_allowed": False,
            "evidence_class": "real_underlying_history_model_priced_options_diagnostic_only",
        })
    return records


def _candidate_capital_diagnostics(
    accumulator: Mapping[str, object],
    max_drawdown: float,
) -> dict[str, object]:
    trade_count = int(accumulator["trade_count"])
    denominator_trade_count = int(accumulator["capital_denominator_trade_count"])
    entry_premiums = sorted(cast(list[float], accumulator["entry_premium_values"]))
    trade_returns = sorted(cast(list[float], accumulator["trade_return_on_entry_premium_values"]))
    entry_events = cast(dict[str, dict[str, float | int]], accumulator["entry_capital_events"])
    exit_events = cast(dict[str, dict[str, float | int]], accumulator["exit_capital_events"])
    active_premium = 0.0
    active_positions = 0
    peak_premium = 0.0
    peak_positions = 0
    for event_date in sorted(set(entry_events) | set(exit_events)):
        entry_event = entry_events.get(event_date, {"premium": 0.0, "positions": 0})
        active_premium += float(entry_event["premium"])
        active_positions += int(entry_event["positions"])
        peak_premium = max(peak_premium, active_premium)
        peak_positions = max(peak_positions, active_positions)
        exit_event = exit_events.get(event_date, {"premium": 0.0, "positions": 0})
        active_premium -= float(exit_event["premium"])
        active_positions -= int(exit_event["positions"])
        if active_premium < -1e-8 or active_positions < 0:
            raise ValueError(
                "strategy dossier capital event ledger became negative: "
                f"candidate_id={accumulator['candidate_id']}, date={event_date}, "
                f"active_premium={active_premium}, active_positions={active_positions}"
            )
    if abs(active_premium) > 1e-8 or active_positions != 0:
        raise ValueError(
            "strategy dossier capital event ledger did not settle to zero: "
            f"candidate_id={accumulator['candidate_id']}, active_premium={active_premium}, "
            f"active_positions={active_positions}"
        )
    status = (
        "complete_model_premium_diagnostic"
        if trade_count > 0 and denominator_trade_count == trade_count
        else "partial_missing_entry_premium"
    )
    return {
        "normalization_status": status,
        "denominator_trade_count": denominator_trade_count,
        "missing_denominator_trade_count": trade_count - denominator_trade_count,
        "entry_premium_total_model_units": round(float(accumulator["entry_premium_total"]), 6),
        "entry_premium_mean_model_units": round(statistics.mean(entry_premiums), 6) if entry_premiums else None,
        "entry_premium_median_model_units": round(statistics.median(entry_premiums), 6) if entry_premiums else None,
        "peak_concurrent_entry_premium_model_units": round(peak_premium, 6) if entry_premiums else None,
        "peak_concurrent_position_count": peak_positions if entry_premiums else None,
        "mean_trade_return_on_entry_premium": round(statistics.mean(trade_returns), 6) if trade_returns else None,
        "median_trade_return_on_entry_premium": round(statistics.median(trade_returns), 6) if trade_returns else None,
        "p05_trade_return_on_entry_premium": round(_quantile(trade_returns, 0.05), 6) if trade_returns else None,
        "max_drawdown_to_peak_model_premium": round(max_drawdown / peak_premium, 6) if peak_premium > 0.0 else None,
        "real_capital_denominator_available": False,
        "annualization_allowed": False,
        "diagnostic_only": True,
    }


def _capital_exposure_artifact(
    run_id: str,
    candidates: Sequence[dict[str, object]],
) -> dict[str, object]:
    diagnostics = [
        {
            "candidate_id": candidate["candidate_id"],
            "trade_count": candidate["trade_count"],
            **cast(dict[str, object], candidate["capital_diagnostics"]),
        }
        for candidate in candidates
    ]
    complete_count = sum(
        1
        for row in diagnostics
        if row["normalization_status"] == "complete_model_premium_diagnostic"
    )
    normalization_status = (
        "complete_model_premium_diagnostic"
        if diagnostics and complete_count == len(diagnostics)
        else "partial_missing_entry_premium"
    )
    artifact: dict[str, object] = {
        "artifact_type": "strategy_capital_exposure_diagnostics",
        "artifact_version": "dopey-strategy-capital-exposure-v1",
        "run_id": run_id,
        "normalization_status": normalization_status,
        "candidate_count": len(diagnostics),
        "complete_candidate_count": complete_count,
        "candidate_diagnostics": diagnostics,
        "denominator_semantics": "modeled_entry_premium_for_defined_risk_long_premium_structures",
        "real_capital_denominator_available": False,
        "annualized_return_available": False,
        "profitability_claim_allowed": False,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    artifact["artifact_hash"] = _stable_hash(artifact)
    return artifact


def _candidate_partition_manifest(
    run_id: str,
    accumulators: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    partitions = [
        {
            "candidate_id": candidate_id,
            "trade_count": int(accumulator["trade_count"]),
            "partition_hash": cast(Any, accumulator["partition_digest"]).hexdigest(),
        }
        for candidate_id, accumulator in sorted(accumulators.items())
    ]
    manifest: dict[str, object] = {
        "artifact_type": "strategy_candidate_partition_manifest",
        "manifest_version": "dopey-strategy-partition-manifest-v1",
        "run_id": run_id,
        "partition_count": len(partitions),
        "partitions": partitions,
        "reuse_status": "identity_ready_recomputation_still_whole_source",
        "paper_only": True,
        "live_blocked": True,
    }
    manifest["manifest_hash"] = _stable_hash(manifest)
    return manifest


def _gate(gate_id: str, passed: bool, observed: object, required: object) -> dict[str, object]:
    return {
        "gate_id": gate_id,
        "status": "pass" if passed else "fail",
        "observed": observed,
        "required": required,
        "reason": "threshold_satisfied" if passed else "threshold_not_satisfied",
    }


def _pareto_frontier(candidates: Sequence[dict[str, object]]) -> set[str]:
    dimensions = (
        "stressed_cost_expectancy_model_units",
        "matched_baseline_delta_model_units",
        "worst_fold_expectancy_model_units",
        "max_drawdown_model_units",
    )
    frontier: set[str] = set()
    for candidate in candidates:
        dominated = False
        for challenger in candidates:
            if challenger is candidate:
                continue
            comparable = [
                (float(challenger[dimension]), float(candidate[dimension]))
                for dimension in dimensions
                if challenger.get(dimension) is not None and candidate.get(dimension) is not None
            ]
            if comparable and all(left >= right for left, right in comparable) and any(left > right for left, right in comparable):
                dominated = True
                break
        if not dominated:
            frontier.add(str(candidate["candidate_id"]))
    return frontier


def _candidate_lexicographic_key(candidate: Mapping[str, object]) -> tuple[object, ...]:
    worst_fold_expectancy = candidate["worst_fold_expectancy_model_units"]
    return (
        0 if bool(candidate["eligible"]) else 1,
        int(candidate["gate_failure_count"]),
        -float(worst_fold_expectancy) if worst_fold_expectancy is not None else math.inf,
        -float(candidate["stressed_cost_expectancy_model_units"]),
        -float(candidate["matched_baseline_delta_model_units"]),
        -float(candidate["max_drawdown_model_units"]),
        str(candidate["candidate_id"]),
    )


def _build_equity_curve(daily_totals: Mapping[str, Mapping[str, float]]) -> list[dict[str, object]]:
    cumulative = 0.0
    peak = 0.0
    rows: list[dict[str, object]] = []
    for observation_date, totals in sorted(daily_totals.items()):
        net = float(totals.get("net", 0.0))
        cumulative += net
        peak = max(peak, cumulative)
        rows.append({
            "date": observation_date,
            "trade_count": int(totals.get("trades", 0.0)),
            "gross_model_unit_pnl": round(float(totals.get("gross", 0.0)), 6),
            "cost_model_units": round(float(totals.get("cost", 0.0)), 6),
            "net_model_unit_pnl": round(net, 6),
            "cumulative_model_unit_pnl": round(cumulative, 6),
            "running_peak_model_units": round(peak, 6),
            "drawdown_model_units": round(cumulative - peak, 6),
        })
    return rows


def _drawdown_episodes(equity_curve: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    episodes: list[dict[str, object]] = []
    active_start = ""
    trough_date = ""
    trough_value = 0.0
    observation_count = 0
    for row in equity_curve:
        current_date = str(row["date"])
        drawdown = float(row["drawdown_model_units"])
        if drawdown < 0.0:
            if not active_start:
                active_start = current_date
                trough_date = current_date
                trough_value = drawdown
                observation_count = 0
            observation_count += 1
            if drawdown < trough_value:
                trough_date = current_date
                trough_value = drawdown
            continue
        if active_start:
            episodes.append(_drawdown_episode(active_start, trough_date, current_date, trough_value, observation_count, True))
            active_start = ""
    if active_start:
        episodes.append(_drawdown_episode(active_start, trough_date, "", trough_value, observation_count, False))
    return episodes


def _drawdown_episode(
    start_date: str,
    trough_date: str,
    recovery_date: str,
    maximum_drawdown: float,
    observation_count: int,
    recovered: bool,
) -> dict[str, object]:
    end_date = recovery_date if recovery_date else trough_date
    calendar_days = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days
    return {
        "start_date": start_date,
        "trough_date": trough_date,
        "recovery_date": recovery_date,
        "recovered": recovered,
        "maximum_drawdown_model_units": round(maximum_drawdown, 6),
        "duration_observation_days": observation_count,
        "duration_calendar_days": calendar_days,
    }


def _exposure_rows(exposures: Mapping[tuple[str, str, str], Mapping[str, float]]) -> list[dict[str, object]]:
    totals: dict[tuple[str, str], float] = defaultdict(float)
    for (candidate_id, axis, _), values in exposures.items():
        totals[(candidate_id, axis)] += float(values["trade_count"])
    rows: list[dict[str, object]] = []
    for (candidate_id, axis, key), values in sorted(exposures.items()):
        denominator = totals[(candidate_id, axis)]
        rows.append({
            "candidate_id": candidate_id,
            "axis": axis,
            "key": key,
            "trade_count": int(values["trade_count"]),
            "trade_share": round(float(values["trade_count"]) / denominator, 6) if denominator else 0.0,
            "net_model_unit_pnl": round(float(values["net_pnl"]), 6),
        })
    return rows


def _fold_rows(records: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    keys = (
        "cohort_id", "signal_family", "candidate_strategy", "era", "sample_count", "meets_min_sample",
        "average_pnl", "net_pnl", "win_rate", "profit_factor", "paper_only", "live_blocked",
    )
    return [{key: record.get(key) for key in keys} for record in records]


def _robustness_rows(
    candidates: Sequence[dict[str, object]],
    metric_set: Mapping[str, object],
    bootstrap: Mapping[str, object],
    deflated_sharpe: Mapping[str, object],
    multiple_testing: Mapping[str, object],
    truth_decision: Mapping[str, object],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        for gate in cast(list[dict[str, object]], candidate["hard_gates"]):
            rows.append({
                "scope": str(candidate["candidate_id"]),
                "test_id": gate["gate_id"],
                "status": gate["status"],
                "observed": gate["observed"],
                "required": gate["required"],
                "diagnostic_only": True,
            })
    global_tests = (
        ("global", "bootstrap_mean_ci", bootstrap.get("mean_pnl_ci"), "interval_reported", True),
        ("global", "deflated_sharpe", deflated_sharpe.get("deflated_sharpe_model_units"), ">0", True),
        ("global", "effective_trials", deflated_sharpe.get("effective_trials"), "all_trials_accounted", True),
        ("global", "multiple_testing", multiple_testing.get("adjustment_status"), "selection_aware", True),
        ("global", "truth_decision", truth_decision.get("truth_decision"), "real_evidence_sufficient", True),
        ("global", "max_drawdown_model_units", metric_set.get("max_drawdown_model_units"), "declared_capital_normalized_limit", True),
    )
    rows.extend({
        "scope": scope,
        "test_id": test_id,
        "status": "diagnostic_only",
        "observed": observed,
        "required": required,
        "diagnostic_only": diagnostic_only,
    } for scope, test_id, observed, required, diagnostic_only in global_tests)
    return rows


def _failure_modes(
    candidates: Sequence[dict[str, object]],
    truth_decision: Mapping[str, object],
    backtest_summary: Mapping[str, object],
    fitness_decision: Mapping[str, object],
) -> dict[str, object]:
    candidate_failures = {
        str(candidate["candidate_id"]): [
            str(gate["gate_id"])
            for gate in cast(list[dict[str, object]], candidate["hard_gates"])
            if str(gate["status"]) != "pass"
        ]
        for candidate in candidates
    }
    return {
        "artifact_type": "strategy_evidence_failure_modes",
        "truth_blocked_reason_codes": list(truth_decision.get("blocked_reason_codes", [])),
        "backtest_quality_flags": list(backtest_summary.get("quality_flags", [])),
        "fitness_blocked_reason_codes": list(fitness_decision.get("blocked_reason_codes", [])),
        "candidate_gate_failures": candidate_failures,
        "dominant_failure": "model_priced_options_without_real_quote_or_chain_evidence",
        "paper_only": True,
        "live_blocked": True,
    }


def _mutation_trial_summary(path: Path) -> dict[str, int]:
    registry_records = 0
    mutation_attempts = 0
    for record in _read_jsonl_objects(path):
        registry_records += 1
        mutation_attempts += int(record.get("mutations_generated", 0))
    return {"registry_record_count": registry_records, "mutation_attempt_count": mutation_attempts}


def _dossier_headline(
    candidates: Sequence[dict[str, object]],
    eligible_candidates: Sequence[dict[str, object]],
    truth_state: Mapping[str, object],
) -> str:
    if not bool(truth_state["real_option_chain_used"]):
        return (
            f"{len(candidates)} cohorts were interrogated; none may be promoted because option outcomes remain "
            "model-priced and the hard evidence gate requires real executable quote evidence."
        )
    if not eligible_candidates:
        return f"{len(candidates)} cohorts were interrogated; no candidate survived every hard eligibility gate."
    return f"{len(eligible_candidates)} of {len(candidates)} cohorts survived the declared research-eligibility gates."


def _render_report_html(
    summary: Mapping[str, object],
    candidates: Sequence[dict[str, object]],
    frontier_ids: set[str],
    drawdowns: Sequence[dict[str, object]],
) -> str:
    candidate_rows = "".join(
        "<tr>"
        f"<td><b>{html.escape(str(candidate['candidate_id']))}</b><small>{html.escape(str(candidate['evidence_class']))}</small></td>"
        f"<td>{int(candidate['trade_count']):,}</td>"
        f"<td>{float(candidate['expectancy_model_units']):.4f}</td>"
        f"<td>{float(candidate['stressed_cost_expectancy_model_units']):.4f}</td>"
        f"<td>{float(candidate['matched_baseline_delta_model_units']):,.1f}</td>"
        f"<td>{int(candidate['positive_fold_count'])}/{int(candidate['fold_count'])}</td>"
        f"<td><span class='state {'frontier' if str(candidate['candidate_id']) in frontier_ids else 'blocked'}'>"
        f"{'DIAGNOSTIC FRONTIER' if str(candidate['candidate_id']) in frontier_ids else 'DOMINATED / BLOCKED'}</span></td>"
        "</tr>"
        for candidate in candidates
    )
    worst_drawdown = min((float(row["maximum_drawdown_model_units"]) for row in drawdowns), default=0.0)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DOPEY Strategy Evidence Dossier</title><style>
:root{{--ink:#0a0d0b;--panel:#111612;--line:#263128;--type:#d8dfd4;--dim:#829083;--acid:#8fbf9a;--rust:#d46e57;--ochre:#c9a95e}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--ink);color:var(--type);font:13px/1.45 Inter,Segoe UI,sans-serif}}
main{{max-width:1500px;margin:auto;padding:28px}} header{{display:grid;grid-template-columns:1fr auto;gap:24px;border-top:1px solid #536157;border-bottom:1px solid var(--line);padding:22px 0}}
h1{{margin:4px 0;font-size:36px;letter-spacing:.08em;font-weight:500}} h1 span{{color:var(--acid)}} .eyebrow,.tag,th,.state{{font:10px ui-monospace,Consolas,monospace;letter-spacing:.12em}}
header p{{max-width:920px;color:var(--dim);margin:8px 0 0}} .seal{{border:1px solid #47634c;padding:14px 18px;color:var(--acid);align-self:center}}
.metrics{{display:grid;grid-template-columns:repeat(6,1fr);border:1px solid var(--line);margin:18px 0}} .metric{{padding:18px;border-right:1px solid var(--line)}} .metric:last-child{{border:0}} .metric b{{display:block;font:24px ui-monospace,Consolas,monospace;font-weight:400}} .metric span{{color:var(--dim);font-size:9px;letter-spacing:.08em}}
.truth{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;margin:16px 0}} .card{{background:var(--panel);border:1px solid var(--line);padding:16px}} .card h2{{font-size:12px;letter-spacing:.1em;margin:0 0 10px}} .card p{{color:var(--dim);margin:0}} table{{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line)}} th,td{{padding:11px;border-bottom:1px solid var(--line);text-align:right}} th:first-child,td:first-child{{text-align:left}} td small{{display:block;color:var(--dim);font-size:9px}} .state{{display:inline-block;padding:4px 6px;border:1px solid}} .frontier{{color:var(--ochre);border-color:#6e5d32}} .blocked{{color:var(--rust);border-color:#6b352b}}
footer{{margin:24px 0;color:var(--dim);font:10px ui-monospace,Consolas,monospace}} @media(max-width:1000px){{.metrics{{grid-template-columns:repeat(2,1fr)}}.truth{{grid-template-columns:1fr}}table{{font-size:10px}}}}
</style></head><body><main>
<header><div><span class="eyebrow">DOPEY / EVIDENCE DOSSIER / {html.escape(str(summary['run_id']))}</span><h1>STRATEGY <span>INTERROGATION</span></h1><p>{html.escape(str(summary['headline']))}</p></div><div class="seal">PAPER ONLY // LIVE BLOCKED</div></header>
<section class="metrics"><div class="metric"><b>{int(summary['trade_count']):,}</b><span>MODEL-PRICED TRADES</span></div><div class="metric"><b>{int(summary['candidate_count'])}</b><span>COHORTS</span></div><div class="metric"><b>{int(summary['eligible_candidate_count'])}</b><span>HARD-GATE SURVIVORS</span></div><div class="metric"><b>{int(summary['diagnostic_frontier_count'])}</b><span>DIAGNOSTIC FRONTIER</span></div><div class="metric"><b>{float(summary['total_cost_model_units']):,.0f}</b><span>COST UNITS</span></div><div class="metric"><b>{worst_drawdown:,.0f}</b><span>WORST DRAWDOWN UNITS</span></div></section>
<section class="truth"><div class="card"><h2>THE HONEST ANSWER</h2><p>Real underlying history is present. Option outcomes are model-priced, not executable quote-priced evidence. Annualized return and Calmar remain unavailable because no defensible capital denominator exists.</p></div><div class="card"><h2>SELECTION LAW</h2><p>Hard gates determine eligibility. Pareto dominance and lexicographic ordering explain the survivors; no blended score can conceal a failed gate.</p></div><div class="card"><h2>FRONTIER STATUS</h2><p>{html.escape(str(summary['frontier_status']).replace('_',' ').upper())}</p></div></section>
<table><thead><tr><th>CANDIDATE</th><th>TRADES</th><th>EXPECTANCY</th><th>2X COST</th><th>VS BASELINE</th><th>POSITIVE FOLDS</th><th>STATE</th></tr></thead><tbody>{candidate_rows}</tbody></table>
<footer>SOURCE HASH {html.escape(str(summary['source_trade_hash']))} // PROFITABILITY CLAIM PROHIBITED // PROMOTION ALLOWED: FALSE</footer>
</main></body></html>"""


def _repository_revision(repository_root: Path) -> dict[str, object]:
    head = _run_git(repository_root, ("rev-parse", "HEAD"))
    status = _run_git(repository_root, ("status", "--porcelain=v1", "--untracked-files=no"))
    return {
        "git_commit": head.strip(),
        "working_tree_dirty": bool(status.strip()),
        "tracked_status_hash": hashlib.sha256(status.encode("utf-8")).hexdigest(),
        "dossier_source_hash": _required_file_hash(Path(__file__)),
    }


def _run_git(repository_root: Path, arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "strategy dossier git evidence command failed: "
            f"arguments={list(arguments)}, return_code={completed.returncode}, stderr={completed.stderr[-2000:]}"
        )
    return completed.stdout


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        return 0.0
    position = probability * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[lower])
    fraction = position - lower
    return float(sorted_values[lower]) * (1.0 - fraction) + float(sorted_values[upper]) * fraction


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"strategy dossier source is missing: path={path}")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
        raise TypeError(f"strategy dossier JSON source must be an object: path={path}")
    return cast(dict[str, object], parsed)


def _read_jsonl_objects(path: Path) -> Iterable[dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"strategy dossier JSONL source is missing: path={path}")
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            parsed = json.loads(line)
            if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
                raise TypeError(f"strategy dossier JSONL row must be an object: path={path}, line={line_number}")
            yield cast(dict[str, object], parsed)


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _csv_value(value: object) -> object:
    if isinstance(value, (dict, list, tuple, set)):
        normalized = sorted(value) if isinstance(value, set) else value
        return json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return value


def _write_json(path: Path, record: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(record), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_json_atomic(path: Path, record: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    _write_json(temporary, record)
    temporary.replace(path)


def _publish_latest_capital_exposure(run_directory: Path, latest_directory: Path) -> None:
    capital_path = run_directory / "capital_exposure.json"
    capital = _read_json_object(capital_path)
    latest = dict(capital)
    latest["run_directory"] = str(run_directory.resolve())
    _write_json_atomic(latest_directory / "latest_capital_exposure.json", latest)


def _required_string(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"strategy dossier record requires nonempty string field: key={key}, value={value!r}")
    return value


def _required_float(record: Mapping[str, object], key: str) -> float:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"strategy dossier record requires numeric field: key={key}, value={value!r}")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"strategy dossier record requires finite field: key={key}, value={value!r}")
    return numeric


def _optional_positive_float(record: Mapping[str, object], key: str) -> float | None:
    value = record.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"strategy dossier record requires optional numeric field: key={key}, value={value!r}")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"strategy dossier record requires positive finite field: key={key}, value={value!r}")
    return numeric


def _required_int(record: Mapping[str, object], key: str) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"strategy dossier record requires integer field: key={key}, value={value!r}")
    return value


def _required_file_hash(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"strategy dossier source is missing: path={path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_hash(record: Mapping[str, object]) -> str:
    normalized = {key: value for key, value in record.items() if not key.endswith("_hash")}
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
