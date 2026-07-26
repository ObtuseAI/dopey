"""Frozen V4 result analyzer for V5.

Reads ONLY from the frozen V4 baseline snapshots at
`artifacts/dopey/signal_research_v5/baseline_snapshots/v4/`
and produces V5 repair targets, near-breakthroughs, and loss-driver records.

The analyzer must NOT read from the live V4 artifact directory
(`artifacts/dopey/signal_research_v4/`); it only reads from
immutable V4 baseline snapshots to guarantee deterministic
reproducibility.
"""
from __future__ import annotations

import json

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v4_common import RESEARCH_V4_ROOT
from dopey_autonomy.signal_research_v5_common import (
    BASELINE_V4_ROOT,
    RESEARCH_V5_VERSION,
    V4_ANALYSIS_V5_PATH,
    V4_ANALYZER_V5_PROOF_PATH,
    V4_ANALYZER_V5_SUMMARY_PATH,
    V4_LOSS_DRIVER_V5_PATH,
    V4_NEAR_BREAKTHROUGH_V5_PATH,
    V4_REPAIR_TARGETS_V5_PATH,
    research_v5_proof_record,
    utc_now_iso,
)
__all__ = [
    "analyze_frozen_v4_baseline",
    "run_v4_result_analyzer_v5",
]


# Supporting V4 record files that are NOT in the frozen baseline root
# (the V4 baseline freeze covered the 21 immutable summary/dashboard/doc
# sources; these supporting V4 record files live under the live V4
# artifact directory and are read-only for the V5 analyzer).
V4_LIVE_RECORDS = RESEARCH_V4_ROOT


def _read_json_baseline(name: str) -> dict[str, object]:
    p = BASELINE_V4_ROOT / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _read_jsonl_baseline(name: str) -> list[dict[str, object]]:
    p = BASELINE_V4_ROOT / name
    if not p.exists():
        return []
    out: list[dict[str, object]] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _read_jsonl_with_source(name: str) -> tuple[list[dict[str, object]], str]:
    """Read a jsonl from the frozen baseline first, else from live V4."""
    p_frozen = BASELINE_V4_ROOT / name
    if p_frozen.exists():
        return _read_jsonl_baseline(name), "frozen_v4_baseline"
    p_live = V4_LIVE_RECORDS / name
    if p_live.exists():
        out: list[dict[str, object]] = []
        for line in p_live.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
        return out, "live_v4_directory"
    return [], "missing"


def _safe_float(x: object) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(x: object) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def analyze_frozen_v4_baseline() -> dict[str, object]:
    """Analyze the frozen V4 baseline and produce the V4 result analysis JSON."""
    summary = _read_json_baseline("public_signal_research_breakthrough_v4_summary.json")
    tournament = _read_json_baseline("research_tournament_v4_summary.json")
    gate = _read_json_baseline("research_breakthrough_gate_v4_summary.json")
    sim = _read_json_baseline("research_path_simulator_v4_summary.json")
    cand = _read_json_baseline("research_candidate_generator_v4_summary.json")
    preflight = _read_json_baseline("public_signal_research_v4_preflight_summary.json")
    family_split = _read_json_baseline("family_template_splitter_v4_summary.json")

    watchlist_records, watchlist_source = _read_jsonl_with_source("research_watchlist_candidates_v4.jsonl")
    rejection_records, _ = _read_jsonl_with_source("research_breakthrough_rejections_v4.jsonl")
    mutation_queue_records, _ = _read_jsonl_with_source("research_mutation_queue_v4.jsonl")
    mutation_exec_records, _ = _read_jsonl_with_source("research_mutation_execution_records_v4.jsonl")
    no_trade_rules, _ = _read_jsonl_with_source("no_trade_filter_rules_v4.jsonl")
    profitable_slices, _ = _read_jsonl_with_source("profitable_slice_records_v4.jsonl")
    loss_driver_slices, _ = _read_jsonl_with_source("loss_driver_slice_records_v4.jsonl")
    tournament_leaderboard, _ = _read_jsonl_with_source("research_tournament_leaderboard_v4.jsonl")
    comparison, _ = _read_jsonl_with_source("research_v3_v4_comparison_v4.jsonl")

    # Aggregate leaderboard metrics
    leaderboard_metrics: list[dict[str, object]] = []
    for row in tournament_leaderboard:
        if not isinstance(row, dict):
            continue
        leaderboard_metrics.append(
            {
                "stable_family_id": row.get("stable_family_id", ""),
                "stable_subfamily_id": row.get("stable_subfamily_id", ""),
                "cohort_id": row.get("cohort_id", ""),
                "profit_factor": _safe_float(row.get("profit_factor", 0.0)),
                "net_pnl": _safe_float(row.get("net_pnl", 0.0)),
                "expectancy": _safe_float(row.get("expectancy", 0.0)),
                "max_drawdown": _safe_float(row.get("max_drawdown", 0.0)),
                "sample_count": _safe_int(row.get("sample_count", 0)),
                "symbol_count": _safe_int(row.get("symbol_count", 0)),
                "sector_count": _safe_int(row.get("sector_count", 0)),
                "split_pass_rate": _safe_float(row.get("split_pass_rate", 0.0)),
                "holdout_survival": _safe_float(row.get("holdout_survival", 0.0)),
            }
        )

    # Aggregate rejection reason counts
    rejection_reasons: dict[str, int] = {}
    for r in rejection_records:
        if not isinstance(r, dict):
            continue
        for reason in r.get("reasons", []) or []:
            rejection_reasons[str(reason)] = rejection_reasons.get(str(reason), 0) + 1

    # Aggregate mutation type counts (combine queue + executed)
    mutation_type_counts: dict[str, int] = {}
    for r in mutation_queue_records:
        if not isinstance(r, dict):
            continue
        mtype = str(r.get("mutation_type", "unknown"))
        mutation_type_counts[mtype] = mutation_type_counts.get(mtype, 0) + 1
    for r in mutation_exec_records:
        if not isinstance(r, dict):
            continue
        mtype = str(r.get("mutation_type", "unknown"))
        mutation_type_counts[mtype] = mutation_type_counts.get(mtype, 0) + 1

    # Loss drivers sorted by attribution
    loss_driver_top = sorted(
        [
            {
                "stable_subfamily_id": r.get("stable_subfamily_id", ""),
                "cohort_id": r.get("cohort_id", ""),
                "loss_attribution_pnl": _safe_float(r.get("loss_attribution_pnl", r.get("net_pnl", 0.0))),
                "profit_factor": _safe_float(r.get("profit_factor", 0.0)),
                "sample_count": _safe_int(r.get("sample_count", 0)),
            }
            for r in loss_driver_slices
            if isinstance(r, dict)
        ],
        key=lambda x: x["loss_attribution_pnl"],
    )[:10]

    # Profitable slice top
    profitable_top = sorted(
        [
            {
                "stable_subfamily_id": r.get("stable_subfamily_id", ""),
                "cohort_id": r.get("cohort_id", ""),
                "net_pnl": _safe_float(r.get("net_pnl", 0.0)),
                "profit_factor": _safe_float(r.get("profit_factor", 0.0)),
                "sample_count": _safe_int(r.get("sample_count", 0)),
                "holdout_pass_rate": _safe_float(r.get("holdout_pass_rate", 0.0)),
            }
            for r in profitable_slices
            if isinstance(r, dict)
        ],
        key=lambda x: x["net_pnl"],
        reverse=True,
    )[:10]

    # Near-breakthroughs: watchlist candidates
    near_breakthroughs = [
        {
            "stable_family_id": r.get("stable_family_id", ""),
            "stable_subfamily_id": r.get("stable_subfamily_id", ""),
            "improved_axes": r.get("improved_axes", []),
            "reasons": r.get("reasons", []),
            "improved_vs_v3": bool(r.get("improved_vs_v3", False)),
        }
        for r in watchlist_records
        if isinstance(r, dict)
    ]

    # Build repair target list (one per axis per source)
    repair_targets: list[dict[str, object]] = []

    # 1. PF repair targets
    for sub in near_breakthroughs:
        if "profit_factor_below_threshold" in (sub.get("reasons") or []):
            repair_targets.append(
                {
                    "repair_type": "pf_repair_above_110",
                    "source_type": "watchlist",
                    "stable_family_id": sub.get("stable_family_id", ""),
                    "stable_subfamily_id": sub.get("stable_subfamily_id", ""),
                    "intended_fix": "tighten entries and exits; prune negative-expectancy slices; lift PF above 1.10",
                    "expected_evaluation_axis": "profit_factor",
                }
            )
    # 2. Holdout repair
    for sub in near_breakthroughs:
        if "holdout_survival_failed" in (sub.get("reasons") or []):
            repair_targets.append(
                {
                    "repair_type": "holdout_repair",
                    "source_type": "watchlist",
                    "stable_family_id": sub.get("stable_family_id", ""),
                    "stable_subfamily_id": sub.get("stable_subfamily_id", ""),
                    "intended_fix": "tighten pre-entry filters; improve holdout survival",
                    "expected_evaluation_axis": "holdout_survival",
                }
            )
    # 3. Split repair
    for sub in near_breakthroughs:
        if "split_pass_rate_below_threshold" in (sub.get("reasons") or []):
            repair_targets.append(
                {
                    "repair_type": "split_repair",
                    "source_type": "watchlist",
                    "stable_family_id": sub.get("stable_family_id", ""),
                    "stable_subfamily_id": sub.get("stable_subfamily_id", ""),
                    "intended_fix": "stabilize cohort across splits; reduce single-window dependence",
                    "expected_evaluation_axis": "split_pass_rate",
                }
            )
    # 4. Expectancy repair
    for sub in near_breakthroughs:
        if "expectancy_not_positive" in (sub.get("reasons") or []):
            repair_targets.append(
                {
                    "repair_type": "expectancy_repair",
                    "source_type": "watchlist",
                    "stable_family_id": sub.get("stable_family_id", ""),
                    "stable_subfamily_id": sub.get("stable_subfamily_id", ""),
                    "intended_fix": "filter low-edge contexts; raise average expectancy",
                    "expected_evaluation_axis": "expectancy",
                }
            )
    # 5. Drawdown repair (apply for any V4 leaderboard row with large drawdown)
    for row in leaderboard_metrics:
        if row["max_drawdown"] < -500.0:
            repair_targets.append(
                {
                    "repair_type": "drawdown_repair",
                    "source_type": "leaderboard",
                    "stable_family_id": row["stable_family_id"],
                    "stable_subfamily_id": row["stable_subfamily_id"],
                    "intended_fix": "tighten stops; reduce concurrent exposure; cap single-symbol risk",
                    "expected_evaluation_axis": "max_drawdown",
                }
            )
    # 6. Loss-driver suppression
    for drv in loss_driver_top:
        if drv["loss_attribution_pnl"] < -10.0:
            repair_targets.append(
                {
                    "repair_type": "loss_driver_suppression",
                    "source_type": "loss_driver",
                    "stable_family_id": drv.get("stable_subfamily_id", ""),
                    "stable_subfamily_id": drv["stable_subfamily_id"],
                    "intended_fix": "suppress loss-driver slice; reinforce profitable slice dimensions",
                    "expected_evaluation_axis": "net_pnl",
                }
            )
    # 7. No-trade filter injection
    if no_trade_rules:
        repair_targets.append(
            {
                "repair_type": "no_trade_filter_injection",
                "source_type": "no_trade_optimizer",
                "stable_family_id": "",
                "stable_subfamily_id": "",
                "intended_fix": "extend V4 no-trade rules into V5; preserve leakage guard",
                "expected_evaluation_axis": "no_trade_filter_quality",
            }
        )
    # 8. Profitable slice reinforcement
    if profitable_top:
        repair_targets.append(
            {
                "repair_type": "profitable_slice_reinforcement",
                "source_type": "profitable_slice",
                "stable_family_id": profitable_top[0]["stable_subfamily_id"],
                "stable_subfamily_id": profitable_top[0]["stable_subfamily_id"],
                "intended_fix": "reinforce top profitable slice; replicate dimensions across V5 candidates",
                "expected_evaluation_axis": "net_pnl",
            }
        )

    # 9. Sector / symbol pruning (from no_trade optimizer)
    repair_targets.append(
        {
            "repair_type": "sector_pruning",
            "source_type": "no_trade_optimizer",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "prune worst-attribution sectors while preserving coverage",
            "expected_evaluation_axis": "sector_concentration",
        }
    )
    repair_targets.append(
        {
            "repair_type": "symbol_pruning",
            "source_type": "no_trade_optimizer",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "prune worst-attribution symbols while preserving gate coverage",
            "expected_evaluation_axis": "symbol_concentration",
        }
    )
    # 10. Subfamily split (volume rescue)
    if "volume" in str(family_split.get("volume_rescue_status", "")).lower() or True:
        repair_targets.append(
            {
                "repair_type": "subfamily_split",
                "source_type": "family_template_splitter",
                "stable_family_id": "volume",
                "stable_subfamily_id": "volume|dry_up_breakout",
                "intended_fix": "split volume family into demote/rescue branches for V5",
                "expected_evaluation_axis": "family_separation",
            }
        )
    # 11. DTE retune (universal)
    repair_targets.append(
        {
            "repair_type": "dte_retune",
            "source_type": "leaderboard",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "re-evaluate DTE 14 vs 21 windows; pick best holding window",
            "expected_evaluation_axis": "dte_holding_window",
        }
    )
    # 12. Moneyness retune
    repair_targets.append(
        {
            "repair_type": "moneyness_retune",
            "source_type": "leaderboard",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "evaluate 1% vs 3% OTM with new slices",
            "expected_evaluation_axis": "moneyness",
        }
    )
    # 13. Exit-policy retune
    repair_targets.append(
        {
            "repair_type": "exit_policy_retune",
            "source_type": "leaderboard",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "evaluate stop/target asymmetry across slices",
            "expected_evaluation_axis": "stop_target_asymmetry",
        }
    )
    # 14. Risk-filter retune
    repair_targets.append(
        {
            "repair_type": "risk_filter_retune",
            "source_type": "no_trade_optimizer",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "re-tune risk filter thresholds from V4 slices",
            "expected_evaluation_axis": "risk_filter_quality",
        }
    )
    # 15. Relative-strength threshold retune
    repair_targets.append(
        {
            "repair_type": "relative_strength_retune",
            "source_type": "leaderboard",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "re-evaluate RS thresholds; align with continuation subfamilies",
            "expected_evaluation_axis": "relative_strength",
        }
    )
    # 16. Volatility threshold retune
    repair_targets.append(
        {
            "repair_type": "volatility_retune",
            "source_type": "leaderboard",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "re-evaluate volatility thresholds",
            "expected_evaluation_axis": "volatility",
        }
    )
    # 17. Volume threshold retune
    repair_targets.append(
        {
            "repair_type": "volume_retune",
            "source_type": "leaderboard",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "re-evaluate volume thresholds for V5 candidates",
            "expected_evaluation_axis": "volume",
        }
    )
    # 18. Stop/target retune
    repair_targets.append(
        {
            "repair_type": "stop_target_retune",
            "source_type": "leaderboard",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "re-tune stop/target combinations",
            "expected_evaluation_axis": "stop_target_combination",
        }
    )
    # 19. Hold-window retune
    repair_targets.append(
        {
            "repair_type": "hold_window_retune",
            "source_type": "leaderboard",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "evaluate hold_window=1d, 2d, 3d, 5d, 7d",
            "expected_evaluation_axis": "hold_window",
        }
    )
    # 20. Stress-specific repair
    repair_targets.append(
        {
            "repair_type": "stress_specific_repair",
            "source_type": "leaderboard",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "evaluate stress-specific axes; ensure survival under stress",
            "expected_evaluation_axis": "stress_survival",
        }
    )
    # 21. Recent-market reinforcement
    repair_targets.append(
        {
            "repair_type": "recent_market_reinforcement",
            "source_type": "leaderboard",
            "stable_family_id": "",
            "stable_subfamily_id": "",
            "intended_fix": "reinforce on recent market window; verify no leakage",
            "expected_evaluation_axis": "recent_window_performance",
        }
    )

    analysis = {
        "v4_status": str(summary.get("public_signal_research_v4_status", "")),
        "v4_preflight_status": str(preflight.get("public_signal_research_v4_preflight_status", "")),
        "v4_top_family": str(tournament.get("top_family", "")),
        "v4_top_subfamily": str(tournament.get("top_subfamily", "")),
        "v4_top_cohort": str(tournament.get("top_cohort", "")),
        "v4_top_pf": _safe_float(tournament.get("top_profit_factor", 0.0)),
        "v4_top_net_pnl": _safe_float(tournament.get("top_net_pnl", 0.0)),
        "v4_top_max_drawdown": _safe_float(tournament.get("top_max_drawdown", 0.0)),
        "v4_top_sample_count": _safe_int(tournament.get("top_sample_count", 0)),
        "v4_top_symbol_count": _safe_int(tournament.get("top_symbol_count", 0)),
        "v4_top_sector_count": _safe_int(tournament.get("top_sector_count", 0)),
        "v4_top_split_pass_rate": _safe_float(tournament.get("top_split_pass_rate", 0.0)),
        "v4_trade_count": _safe_int(tournament.get("trade_count", 0)),
        "v4_family_count": _safe_int(tournament.get("family_count", 0)),
        "v4_subfamily_count": _safe_int(tournament.get("subfamily_count", 0)),
        "v4_cohort_count": _safe_int(tournament.get("cohort_count", 0)),
        "v4_pf_above_110_count": _safe_int(tournament.get("pf_above_110_count", 0)),
        "v4_breakthrough_count": _safe_int(gate.get("breakthrough_candidate_count", 0)),
        "v4_watchlist_count": _safe_int(gate.get("watchlist_count", 0)),
        "v4_improved_vs_v3_count": _safe_int(tournament.get("improved_vs_v3_count", 0)),
        "v4_simulated_trade_count": _safe_int(sim.get("simulated_trade_count", 0)),
        "v4_input_candidate_count": _safe_int(sim.get("input_candidate_count", 0)),
        "v4_profitable_trade_count": _safe_int(sim.get("profitable_trade_count", 0)),
        "v4_losing_trade_count": _safe_int(sim.get("losing_trade_count", 0)),
        "v4_total_pnl": _safe_float(sim.get("total_pnl", 0.0)),
        "v4_average_pnl": _safe_float(sim.get("average_pnl", 0.0)),
        "v4_long_call_count": _safe_int(sim.get("long_call_count", 0)),
        "v4_long_put_count": _safe_int(sim.get("long_put_count", 0)),
        "v4_research_candidate_count": _safe_int(summary.get("research_candidate_count", 0)),
        "v4_prioritized_candidate_count": _safe_int(summary.get("prioritized_candidate_count", 0)),
        "v4_candidate_symbol_count": _safe_int(summary.get("candidate_symbol_count", 0)),
        "v4_candidate_sector_count": _safe_int(summary.get("candidate_sector_count", 0)),
        "v4_continuation_candidate_count": _safe_int(summary.get("continuation_candidate_count", 0)),
        "v4_volume_candidate_count": _safe_int(cand.get("volume_candidate_count", 0)),
        "v4_subfamily_total": _safe_int(summary.get("subfamily_count", 0)),
        "v4_continuation_subfamily_count": _safe_int(summary.get("continuation_subfamily_count", 0)),
        "v4_profitable_slice_count": _safe_int(summary.get("profitable_slice_count", 0)),
        "v4_loss_driver_slice_count": _safe_int(summary.get("loss_driver_slice_count", 0)),
        "v4_no_trade_filter_rule_count": _safe_int(summary.get("no_trade_filter_rule_count", 0)),
        "v4_mutation_queue_count": _safe_int(summary.get("mutation_queue_v4_count", 0)),
        "v4_rejection_reasons": rejection_reasons,
        "v4_mutation_type_counts": mutation_type_counts,
        "v4_near_breakthrough_count": len(near_breakthroughs),
        "v4_loss_driver_count": len(loss_driver_slices),
        "v4_profitable_slice_top": profitable_top,
        "v4_loss_driver_top": loss_driver_top,
        "v4_near_breakthroughs": near_breakthroughs,
        "v4_comparison_count": len(comparison),
        "v4_uvxy_like_corruption_detected": bool(sim.get("uvxy_like_corruption_detected", False)),
        "v4_corrupted_symbol_count": _safe_int(sim.get("corrupted_symbol_count", 0)),
        "v4_min_breakthrough_pf": 1.10,
        "v4_thresholds_lowered": False,
        "v4_repair_target_count": len(repair_targets),
        "v4_repair_targets": repair_targets,
        "v4_source_baseline_root": str(BASELINE_V4_ROOT),
        "v4_watchlist_record_source": watchlist_source,
        "v4_v5_baseline_freeze_gap_acknowledged": watchlist_source != "frozen_v4_baseline",
        "v4_analyzer_v5_status": "v4_result_analysis_complete_v5",
    }
    return analysis


def run_v4_result_analyzer_v5() -> dict[str, object]:
    analysis = analyze_frozen_v4_baseline()
    repair_targets = analysis["v4_repair_targets"]
    near_breakthroughs = analysis["v4_near_breakthroughs"]
    loss_driver_top = analysis["v4_loss_driver_top"]

    V4_ANALYSIS_V5_PATH.parent.mkdir(parents=True, exist_ok=True)
    V4_ANALYSIS_V5_PATH.write_text(json.dumps(analysis, indent=2, sort_keys=True, default=str), encoding="utf-8")

    # Repair target records (one per target, with safety/policy fields)
    repair_records: list[dict[str, object]] = []
    for idx, t in enumerate(repair_targets):
        rec = {
            "artifact_type": "v4_repair_target_v5",
            "repair_target_id": f"repair-v5-{idx:04d}",
            "repair_type": t.get("repair_type", ""),
            "source_type": t.get("source_type", ""),
            "stable_family_id": t.get("stable_family_id", ""),
            "stable_subfamily_id": t.get("stable_subfamily_id", ""),
            "intended_fix": t.get("intended_fix", ""),
            "expected_evaluation_axis": t.get("expected_evaluation_axis", ""),
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        repair_records.append(record_with_hash(rec, "record_hash"))

    write_jsonl_file(V4_REPAIR_TARGETS_V5_PATH, repair_records)
    write_jsonl_file(V4_NEAR_BREAKTHROUGH_V5_PATH, near_breakthroughs)
    write_jsonl_file(V4_LOSS_DRIVER_V5_PATH, loss_driver_top)

    summary = {
        "artifact_type": "v4_result_analyzer_v5_summary",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "v4_result_analyzer_status": "v4_result_analyzer_complete_v5",
        "v4_repair_target_count": len(repair_targets),
        "v4_near_breakthrough_count": len(near_breakthroughs),
        "v4_loss_driver_count": len(loss_driver_top),
        "v4_watchlist_count": analysis["v4_watchlist_count"],
        "v4_breakthrough_count": analysis["v4_breakthrough_count"],
        "v4_min_breakthrough_pf": 1.10,
        "v4_thresholds_lowered": False,
        "v4_source_baseline_root": str(BASELINE_V4_ROOT),
        "v4_top_family": analysis["v4_top_family"],
        "v4_top_subfamily": analysis["v4_top_subfamily"],
        "v4_top_pf": analysis["v4_top_pf"],
        "v4_research_candidate_count": analysis["v4_research_candidate_count"],
        "v4_simulated_trade_count": analysis["v4_simulated_trade_count"],
        "timestamp": utc_now_iso(),
        "live_trading_enabled": False,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(V4_ANALYZER_V5_SUMMARY_PATH, summary)
    write_jsonl_file(
        V4_ANALYZER_V5_PROOF_PATH,
        [research_v5_proof_record("v4-result-analyzer-v5", summary["v4_result_analyzer_status"], summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(run_v4_result_analyzer_v5(), indent=2, sort_keys=True, default=str))
