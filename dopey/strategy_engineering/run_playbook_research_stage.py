"""Supervisor stage: autonomous playbook research pass.

One governed pass wiring the whole loop:
scan every computable setup -> record detections to the immutable ledger ->
settle every matured prior detection against the spine -> refresh the
per-family earned-trust report. Lane-dependent setups read the macro/chain
artifacts when present; absences are typed gaps.

Advisory research telemetry only: nothing here can promote, size, gate, or
order. A missing spine reports a degraded status honestly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_research_pipeline.artifact_io import write_json_atomic

from .lane_context import load_lane_context
from .option_roi_discovery import discover_option_roi_strategies
from .playbook_scanner import scan_playbook
from .playbook_settlement import (
    PLAYBOOK_ARTIFACT_DIR,
    family_trust_report,
    record_detections,
    settle_matured,
)
from .situational_scorecard import SCORECARD_VERSION
from .swing_target_discovery import discover_swing_targets, load_ohlcv_history
from .trade_memory import MEMORY_VERSION, OUTCOME_UNIT
from .trade_memory_active import load_active_trade_memory_summary

REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_ROOT = REPO_ROOT / "dopey_data" / "history" / "raw"
CHAINS_ROOT = REPO_ROOT / "dopey_data" / "real" / "raw" / "options_chains"
SCAN_REPORT_PATH = PLAYBOOK_ARTIFACT_DIR / "playbook_scan_report.json"
OPTION_EXTREMES_REPORT_PATH = PLAYBOOK_ARTIFACT_DIR / "option_extremes_report.json"
MARKET_EXTREMES_REPORT_PATH = PLAYBOOK_ARTIFACT_DIR / "market_extremes_report.json"
STAGE_SUMMARY_PATH = PLAYBOOK_ARTIFACT_DIR / "playbook_stage_summary.json"


def run_playbook_research_stage(
    *,
    history_root: Path | None = None,
    chains_root: Path | None = None,
) -> dict[str, Any]:
    root = history_root or HISTORY_ROOT
    chains = chains_root or CHAINS_ROOT
    lane = load_lane_context()
    scan = scan_playbook(root, lane_context=lane["states"], max_detections=1_000)
    option_extremes = discover_option_roi_strategies(chains)
    market_extremes = discover_swing_targets(root, chains_root=chains)

    if scan["status"] != "complete":
        summary = {
            "artifact_type": "playbook_research_stage_summary",
            "playbook_stage_version": "dopey-playbook-stage-v2",
            "playbook_stage_status": "blocked_no_ohlcv_history",
            "lane_states_loaded": lane["loaded_state_count"],
            "lane_gaps": lane["gaps"],
            "option_extremes_status": option_extremes["status"],
            "market_extremes_status": market_extremes["status"],
            "paper_only": True,
            "live_blocked": True,
        }
        _write(summary, scan, option_extremes, market_extremes)
        return summary

    bars_by_symbol = load_ohlcv_history(root)
    recording = record_detections(scan)
    settlement = settle_matured(bars_by_symbol)
    trust = family_trust_report()

    summary = {
        "artifact_type": "playbook_research_stage_summary",
        "playbook_stage_version": "dopey-playbook-stage-v2",
        "playbook_stage_status": "playbook_research_complete",
        "symbols_scanned": scan["symbols_scanned"],
        "setups_scanned": scan["setups_scanned"],
        "detections": scan["detection_count"],
        "detector_error_count": scan["detector_error_count"],
        "detections_per_family": scan["detections_per_family"],
        "new_detections_recorded": recording["appended"],
        "newly_settled": settlement["newly_settled"],
        "settlements_pending": settlement["still_pending"],
        "graded_settlements_total": trust["graded_settlements"],
        "rated_setups": sum(
            1 for bucket in trust["per_setup"].values() if bucket["trust_state"] == "rated"
        ),
        "lane_states_loaded": lane["loaded_state_count"],
        "lane_gaps": lane["gaps"],
        "option_extremes_status": option_extremes["status"],
        "option_winner_count": option_extremes.get("winner_count", 0),
        "option_loser_count": option_extremes.get("loser_count", 0),
        "market_extremes_status": market_extremes["status"],
        "stock_gainer_count": market_extremes.get("gainer_count", 0),
        "stock_decliner_count": market_extremes.get("decliner_count", 0),
        "market_extreme_count": market_extremes.get("biggest_mover_count", 0),
        "advisory_only_never_a_gate_input": True,
        "profit_or_edge_claimed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["compression_expansion_study"] = _compression_study_context()
    summary["cross_lane_convergence"] = _cross_lane_convergence_context()
    summary["trade_memory"] = _trade_memory_context()
    summary["situational_scorecard"] = _situational_scorecard_context()
    summary["pre_snap_reads"] = _pre_snap_reads_context()
    summary["reclamation_bench"] = _reclamation_bench_context()
    _write(summary, scan, option_extremes, market_extremes)
    return summary


def _reclamation_bench_context() -> dict[str, Any]:
    """Soft read of the reclamation bench: which refused ideas warrant re-test."""
    bench_path = (
        Path(__file__).resolve().parent.parent.parent
        / "artifacts" / "dopey" / "strategy_engineering" / "reclamation_bench.json"
    )
    if not bench_path.exists():
        return {"bench_status": "not_yet_run"}
    try:
        bench = json.loads(bench_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"bench_status": f"unreadable:{error}"}
    return {
        "bench_status": "present",
        "headline": str(bench.get("headline", "")),
        "retest_recommended": bench.get("retest_recommended", []),
        "advisory_only_never_a_gate_input": True,
    }


def _pre_snap_reads_context() -> dict[str, Any]:
    """Soft read of the latest pre-snap audibles on the open book. Advisory."""
    reads_path = (
        Path(__file__).resolve().parent.parent.parent
        / "artifacts" / "dopey" / "strategy_engineering" / "pre_snap_reads.json"
    )
    if not reads_path.exists():
        return {"pre_snap_status": "not_yet_run"}
    try:
        result = json.loads(reads_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"pre_snap_status": f"unreadable:{error}"}
    return {
        "pre_snap_status": "present",
        "as_of_date": result.get("as_of_date"),
        "audible_counts": result.get("audible_counts", {}),
        "no_trade_audibles": result.get("no_trade_audibles"),
        "advisory_only_never_a_gate_input": True,
    }


def _situational_scorecard_context() -> dict[str, Any]:
    """Soft read of the situational call sheet: what to AVOID, what to monitor.

    Advisory only. The dominant, highest-conviction content is the AVOID list,
    a research risk-control finding rather than an edge claim. Never a gate
    input.
    """
    card_path = (
        Path(__file__).resolve().parent.parent.parent
        / "artifacts" / "dopey" / "strategy_engineering" / "situational_scorecard.json"
    )
    if not card_path.exists():
        return {"scorecard_status": "not_yet_built"}
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"scorecard_status": f"unreadable:{error}"}
    observed_version = str(card.get("scorecard_version", ""))
    if observed_version != SCORECARD_VERSION:
        return {
            "scorecard_status": "incompatible_scorecard_version",
            "expected_scorecard_version": SCORECARD_VERSION,
            "observed_scorecard_version": observed_version or "missing",
            "advisory_only_never_a_gate_input": True,
        }
    return {
        "scorecard_status": "present",
        "headline": str(card.get("headline", "")),
        "avoid_count": len(card.get("avoid_list", [])),
        "monitor_candidate_count": len(card.get("monitor_candidates", [])),
        "advisory_only_never_a_gate_input": True,
    }


def _trade_memory_context() -> dict[str, Any]:
    """Soft read of the Trade Memory Graph: the worst historical entry context.

    Advisory only. Surfaces, per family, which stretch bucket had the worst
    mean outcome historically - context for a reviewer, never a gate input.
    """
    memory_directory = (
        Path(__file__).resolve().parent.parent.parent
        / "artifacts" / "dopey" / "trade_memory"
    )
    try:
        summary = load_active_trade_memory_summary(memory_directory)
    except FileNotFoundError:
        return {"trade_memory_status": "not_yet_built_or_pointer_missing"}
    except (OSError, TypeError, ValueError) as error:
        return {"trade_memory_status": f"unreadable_active_generation:{error}"}
    observed_version = str(summary.get("memory_version", ""))
    if observed_version != MEMORY_VERSION:
        return {
            "trade_memory_status": "incompatible_memory_version",
            "expected_memory_version": MEMORY_VERSION,
            "observed_memory_version": observed_version or "missing",
            "advisory_only_never_a_gate_input": True,
        }
    worst_context: dict[str, str] = {}
    for family, report in summary.get("per_family", {}).items():
        buckets = report.get("conditional_by_stretch", {})
        rated = {k: v for k, v in buckets.items() if v.get("count", 0) >= 200}
        if rated:
            worst = min(
                rated.items(),
                key=lambda item: item[1][
                    "mean_trade_return_model_units"
                ],
            )
            worst_context[family] = worst[0]
    return {
        "trade_memory_status": "present",
        "indexed_trade_count": summary.get("indexed_trade_count"),
        "outcome_unit": OUTCOME_UNIT,
        "worst_stretch_context_by_family": worst_context,
        "advisory_only_never_a_gate_input": True,
    }


def _cross_lane_convergence_context() -> dict[str, Any]:
    """Soft read of the cross-lane convergence report, if it has ever run.

    Advisory context only: a corroborated sign across independent lanes raises
    confidence in a research hypothesis; it never gates or promotes. A missing
    artifact is a normal not-yet-run state.
    """
    from .cross_lane_convergence import CONVERGENCE_PATH

    if not CONVERGENCE_PATH.exists():
        return {"convergence_status": "not_yet_run"}
    try:
        report = json.loads(CONVERGENCE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"convergence_status": f"unreadable:{error}"}
    return {
        "convergence_status": "present",
        "headline": str(report.get("headline", "")),
        "corroborated_findings": report.get("corroborated_findings", []),
        "contested_findings": report.get("contested_findings", []),
        "advisory_only_never_a_gate_input": True,
    }


def _compression_study_context() -> dict[str, Any]:
    """Soft read of the two-question compression study, if it has ever run.

    Advisory context only (the study can argue a squeeze setup down, never
    promote it); a missing artifact is a normal accruing state, not an error.
    """
    from .compression_expansion_study import STUDY_PATH

    if not STUDY_PATH.exists():
        return {"study_status": "not_yet_run"}
    try:
        study = json.loads(STUDY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"study_status": f"unreadable:{error}"}
    return {
        "study_status": "present",
        "study_version": str(study.get("study_version", "")),
        "range_question_survives": bool(
            study.get("range_question", {}).get("survives_both_eras_same_sign_above_null")
        ),
        "directional_claim_supported": bool(
            study.get("direction_question", {}).get("directional_claim_supported")
        ),
    }


def _write(
    summary: dict[str, Any],
    scan: dict[str, Any],
    option_extremes: dict[str, Any],
    market_extremes: dict[str, Any],
) -> None:
    PLAYBOOK_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_atomic(SCAN_REPORT_PATH, scan)
    write_json_atomic(OPTION_EXTREMES_REPORT_PATH, option_extremes)
    write_json_atomic(MARKET_EXTREMES_REPORT_PATH, market_extremes)
    write_json_atomic(STAGE_SUMMARY_PATH, summary)


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(run_playbook_research_stage(), indent=2, default=str))
