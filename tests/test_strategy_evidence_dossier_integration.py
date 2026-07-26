"""Integration coverage for the source-backed Strategy Evidence Dossier."""
from __future__ import annotations

import json
from pathlib import Path

from dopey_reporting.strategy_evidence_dossier import build_strategy_evidence_dossier


def _write_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")


def test_strategy_evidence_dossier_is_content_addressed_and_fail_closed(tmp_path: Path) -> None:
    sources = {name: tmp_path / "sources" / filename for name, filename in {
        "backtest_summary": "backtest_summary.json",
        "trades": "trades.jsonl",
        "folds": "folds.jsonl",
        "metric_set": "metric_set.json",
        "bootstrap": "bootstrap.json",
        "deflated_sharpe": "deflated_sharpe.json",
        "multiple_testing": "multiple_testing.json",
        "truth_decision": "truth_decision.json",
        "baseline_summary": "baseline_summary.json",
        "fitness_decision": "fitness_decision.json",
        "mutation_registry": "mutation_registry.jsonl",
    }.items()}
    trades: list[dict[str, object]] = []
    for index, pnl in enumerate((1.0, -0.8, 0.6, -0.9, 0.4, -0.7)):
        trades.append({
            "trade_id": f"trade-{index}",
            "signal_family": "breakout",
            "option_structure": "long_call",
            "symbol": "TEST",
            "direction": "bullish",
            "entry_date": f"2026-01-{index + 1:02d}",
            "exit_date": f"2026-01-{index + 2:02d}",
            "entry_premium": 2.0,
            "path_pnl": pnl,
            "path_pnl_gross_mid": pnl + 0.1,
            "trade_cost_premium_units": 0.1,
            "holding_steps": 1,
            "trade_return_model_units": pnl,
            "win_loss_marker": "win_model_validation_only" if pnl > 0.0 else "loss_model_validation_only",
            "pricing_source_tier": "model_priced",
            "data_source_tier": "local_real_history",
        })
    _write_jsonl(sources["trades"], trades)
    _write_json(sources["backtest_summary"], {
        "trade_record_count": len(trades),
        "blocked_policy_violation_count": 0,
        "history_dataset_status": "valid_real_dataset",
        "real_history_used": True,
        "real_option_chain_used": False,
        "pricing_source_tier_distribution": {"model_priced": len(trades), "quote_priced": 0},
        "quality_flags": ["missing_real_option_chain"],
    })
    _write_jsonl(sources["folds"], [{
        "cohort_id": "breakout|long_call",
        "signal_family": "breakout",
        "candidate_strategy": "long_call",
        "era": f"era-{index}",
        "sample_count": 2,
        "meets_min_sample": False,
        "average_pnl": value,
        "net_pnl": value * 2.0,
        "win_rate": 0.5,
        "profit_factor": 1.0,
        "paper_only": True,
        "live_blocked": True,
    } for index, value in enumerate((0.1, -0.2, 0.05))])
    _write_json(sources["metric_set"], {"max_drawdown_model_units": -1.5})
    _write_json(sources["bootstrap"], {"mean_pnl_ci": [-0.5, 0.5]})
    _write_json(sources["deflated_sharpe"], {
        "deflated_sharpe_model_units": -0.1,
        "effective_trials": 3,
        "diagnostic_only": True,
    })
    _write_json(sources["multiple_testing"], {"adjustment_status": "diagnostic_only"})
    _write_json(sources["truth_decision"], {
        "truth_decision": "insufficient_real_evidence",
        "blocked_reason_codes": ["missing_real_option_chain"],
    })
    _write_json(sources["baseline_summary"], {"baseline_net_by_cohort": {"breakout|long_call": 0.0}})
    _write_json(sources["fitness_decision"], {
        "fitness_decision": "hold_no_promotion",
        "blocked_reason_codes": ["truth_gate_blocked"],
    })
    _write_jsonl(sources["mutation_registry"], [{"mutations_generated": 7}])

    repository_root = Path(__file__).resolve().parent.parent
    first = build_strategy_evidence_dossier(
        repository_root,
        sources,
        tmp_path / "runs",
        tmp_path / "runs" / "latest_dossier.json",
    )
    second = build_strategy_evidence_dossier(
        repository_root,
        sources,
        tmp_path / "runs",
        tmp_path / "runs" / "latest_dossier.json",
    )
    run_directory = Path(str(first["run_directory"]))
    scorecards = json.loads((run_directory / "strategy_scorecards.json").read_text(encoding="utf-8"))

    assert first["dossier_status"] == "complete_no_eligible_candidates"
    assert first["eligible_candidate_count"] == 0
    assert first["annualized_return"] is None
    assert first["capital_normalization"]["status"] == "complete_model_premium_diagnostic"
    assert first["promotion_allowed"] is False
    assert first["selection_risk"]["mutation_attempts_recorded"] == 7
    assert second["cache_status"] == "content_addressed_cache_hit"
    assert scorecards["candidates"][0]["eligible"] is False
    assert (run_directory / "report.html").is_file()
    assert (run_directory / "trades.csv").is_file()
    assert (run_directory / "pareto_frontier.csv").is_file()
    capital = json.loads((run_directory / "capital_exposure.json").read_text(encoding="utf-8"))
    assert capital["annualized_return_available"] is False
    assert capital["candidate_diagnostics"][0]["peak_concurrent_entry_premium_model_units"] == 4.0
