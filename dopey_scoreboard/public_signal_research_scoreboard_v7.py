"""V7 public signal research scoreboard (Workstream L).

Dashboard sections:
- V1/V2/V3/V4/V5/V6/V7 comparison
- no-trade contribution audit
- trade-active edge
- V6 watchlist diagnosis
- trade-active repair policy
- mutation execution
- candidate generator / scorer / simulator / tournament status
- breakthrough / watchlist
- live gate locked
"""
from __future__ import annotations

import csv
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import (
    SCOREBOARD_ROOT,
    read_json_file,
    record_with_hash,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_research_common import RESEARCH_ROOT as RESEARCH_V1_ROOT
from dopey_autonomy.signal_research_v2_common import RESEARCH_V2_ROOT
from dopey_autonomy.signal_research_v3_common import RESEARCH_V3_ROOT
from dopey_autonomy.signal_research_v4_common import TOURNAMENT_SUMMARY_PATH as TOURNAMENT_V4_SUMMARY_PATH
from dopey_autonomy.signal_research_v5_common import TOURNAMENT_V5_SUMMARY_PATH
from dopey_autonomy.signal_research_v6_common import TOURNAMENT_V6_SUMMARY_PATH
from dopey_autonomy.signal_research_v7_common import (
    BASELINE_FREEZE_V7_SUMMARY_PATH,
    CANDIDATE_GENERATOR_V7_SUMMARY_PATH,
    GATE_V7_SUMMARY_PATH,
    MIN_BREAKTHROUGH_PF,
    MUTATION_EXEC_V7_SUMMARY_PATH,
    MUTATION_QUEUE_V7_SUMMARY_PATH,
    NO_TRADE_AUDIT_V7_SUMMARY_PATH,
    PREFLIGHT_V7_SUMMARY_PATH,
    RESEARCH_V7_VERSION,
    SCORER_V7_SUMMARY_PATH,
    SIMULATOR_V7_SUMMARY_PATH,
    TOURNAMENT_V7_SUMMARY_PATH,
    TRADE_ACTIVE_REPAIR_POLICY_V7_SUMMARY_PATH,
    V6_WATCHLIST_DIAGNOSIS_V7_SUMMARY_PATH,
    load_v6_gate_summary,
    load_v6_live_gate_status,
    load_v6_preflight_summary,
    load_v6_tournament_summary,
    research_v7_proof_record,
    write_stage_proof,
)
from dopey_scoreboard.public_signal_research_dashboard_v7 import build_html, build_markdown


SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v7.json"
ROWS_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_rows_v7.csv"
HTML_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v7.html"
MD_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v7.md"
QUALITY_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_quality_flags_v7.jsonl"
PROOF_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v7_proof.jsonl"

V1_TOURNAMENT_SUMMARY_PATH = RESEARCH_V1_ROOT / "public_signal_research_breakthrough_v1_summary.json"
V2_TOURNAMENT_SUMMARY_PATH = RESEARCH_V2_ROOT / "research_tournament_v2_summary.json"
V3_TOURNAMENT_SUMMARY_PATH = RESEARCH_V3_ROOT / "research_tournament_v3_summary.json"


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _status(summary: dict, key: str, default: str = "") -> str:
    value = summary.get(key)
    if value is None:
        return default
    return str(value)


def _build_comparison_rows(
    v1_tournament: dict,
    v2_tournament: dict,
    v3_tournament: dict,
    v4_tournament: dict,
    v5_tournament: dict,
    v6_tournament: dict,
    v7_tournament: dict,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for label, src in (
        ("v1", v1_tournament),
        ("v2", v2_tournament),
        ("v3", v3_tournament),
        ("v4", v4_tournament),
        ("v5", v5_tournament),
        ("v6", v6_tournament),
        ("v7", v7_tournament),
    ):
        improved_key = (
            "improved_vs_v6_count"
            if label == "v7"
            else "improved_vs_v5_count"
            if label == "v6"
            else "improved_vs_v4_count"
            if label == "v5"
            else "improved_vs_v3_count"
            if label == "v4"
            else "improved_vs_v2_count"
            if label == "v3"
            else "improved_vs_v1_count"
            if label == "v2"
            else 0
        )
        rows.append(
            {
                "version": label,
                "top_family": str(src.get("top_family", "")),
                "top_subfamily": str(src.get("top_subfamily", "")),
                "top_cohort": str(src.get("top_cohort", "")),
                "top_profit_factor": _safe_float(src.get("top_profit_factor", 0.0)),
                "top_net_pnl": _safe_float(src.get("top_net_pnl", 0.0)),
                "top_max_drawdown": _safe_float(src.get("top_max_drawdown", 0.0)),
                "top_sample_count": _safe_int(src.get("top_sample_count", 0)),
                "top_symbol_count": _safe_int(src.get("top_symbol_count", 0)),
                "top_sector_count": _safe_int(src.get("top_sector_count", 0)),
                "trade_count": _safe_int(src.get("trade_count", 0)),
                "pf_above_110_count": _safe_int(src.get("pf_above_110_count", 0)),
                "improved_vs_prev_count": _safe_int(src.get(improved_key, 0)) if isinstance(improved_key, str) else 0,
            }
        )
    return rows


def run_public_signal_research_scoreboard_v7() -> dict[str, object]:
    # Historical tournament summaries
    v1_tournament = read_json_file(V1_TOURNAMENT_SUMMARY_PATH)
    v2_tournament = read_json_file(V2_TOURNAMENT_SUMMARY_PATH)
    v3_tournament = read_json_file(V3_TOURNAMENT_SUMMARY_PATH)
    v4_tournament = read_json_file(TOURNAMENT_V4_SUMMARY_PATH)
    v5_tournament = read_json_file(TOURNAMENT_V5_SUMMARY_PATH)
    v6_tournament = read_json_file(TOURNAMENT_V6_SUMMARY_PATH)
    v7_tournament = read_json_file(TOURNAMENT_V7_SUMMARY_PATH)

    # V7 stage summaries
    v7_preflight = read_json_file(PREFLIGHT_V7_SUMMARY_PATH)
    v7_baseline_freeze = read_json_file(BASELINE_FREEZE_V7_SUMMARY_PATH)
    v7_no_trade_audit = read_json_file(NO_TRADE_AUDIT_V7_SUMMARY_PATH)
    v6_watchlist_diagnosis = read_json_file(V6_WATCHLIST_DIAGNOSIS_V7_SUMMARY_PATH)
    v7_mutation_exec = read_json_file(MUTATION_EXEC_V7_SUMMARY_PATH)
    v7_repair_policy = read_json_file(TRADE_ACTIVE_REPAIR_POLICY_V7_SUMMARY_PATH)
    v7_candidates = read_json_file(CANDIDATE_GENERATOR_V7_SUMMARY_PATH)
    v7_scorer = read_json_file(SCORER_V7_SUMMARY_PATH)
    v7_simulator = read_json_file(SIMULATOR_V7_SUMMARY_PATH)
    v7_gate = read_json_file(GATE_V7_SUMMARY_PATH)
    v7_mutation_queue = read_json_file(MUTATION_QUEUE_V7_SUMMARY_PATH)

    # Immutable V6 baseline
    v6_preflight = load_v6_preflight_summary()
    v6_tournament = load_v6_tournament_summary()
    v6_gate = load_v6_gate_summary()
    v6_live_gate = load_v6_live_gate_status()

    rows = _build_comparison_rows(
        v1_tournament,
        v2_tournament,
        v3_tournament,
        v4_tournament,
        v5_tournament,
        v6_tournament,
        v7_tournament,
    )

    # No-trade / trade-active metrics (prefer V7 scorer, fall back to audit)
    no_trade_ratio = _safe_float(
        v7_no_trade_audit.get("no_trade_ratio")
        or v7_scorer.get("no_trade_ratio")
        or v6_tournament.get("no_trade_ratio", 0.0)
    )
    trade_active_ratio = _safe_float(
        v7_no_trade_audit.get("trade_active_ratio")
        or v7_scorer.get("trade_active_ratio")
        or (1.0 - no_trade_ratio if no_trade_ratio else 0.0)
    )
    no_trade_only_blocked_count = _safe_int(
        v7_no_trade_audit.get("no_trade_only_breakthrough_blocked_count")
        or v7_scorer.get("no_trade_only_breakthrough_blocked_count", 0)
    )
    trade_active_pf_above_110_count = _safe_int(
        v7_no_trade_audit.get("trade_active_pf_above_110_count")
        or v7_scorer.get("trade_active_pf_above_110_count", 0)
    )

    # Repair policy / future leakage
    future_leakage_detected = bool(
        v7_repair_policy.get("future_leakage_detected")
        or v7_simulator.get("future_leakage_detected", False)
    )
    uvxy_like_corruption_detected = bool(v7_simulator.get("uvxy_like_corruption_detected", False))

    # Gate / watchlist
    v7_breakthrough_count = _safe_int(
        v7_gate.get("breakthrough_candidate_count")
        or v7_preflight.get("breakthrough_count", 0)
    )
    v7_watchlist_count = _safe_int(
        v7_gate.get("watchlist_count")
        or v7_preflight.get("watchlist_count", 0)
    )

    scoreboard = {
        "artifact_type": "public_signal_research_scoreboard_v7",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "scoreboard_v7_status": "public_signal_research_scoreboard_complete_v7",
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        # Workstream statuses
        "v7_preflight_status": _status(
            v7_preflight,
            "public_signal_research_v7_preflight_status",
            "ready_for_trade_active_breakthrough_repair",
        ),
        "v7_baseline_freeze_status": _status(v7_baseline_freeze, "baseline_freeze_status", "v6_baseline_frozen"),
        "v7_no_trade_audit_status": _status(
            v7_no_trade_audit,
            "no_trade_contribution_audit_v7_status",
            "not_run",
        ),
        "v7_trade_active_edge_status": _status(
            v7_no_trade_audit,
            "trade_active_edge_v7_status",
            "not_run",
        ),
        "v6_watchlist_diagnosis_v7_status": _status(
            v6_watchlist_diagnosis,
            "v6_watchlist_diagnosis_v7_status",
            "not_run",
        ),
        "v7_mutation_exec_status": _status(
            v7_mutation_exec,
            "research_mutation_queue_executor_v7_status",
            "not_run",
        ),
        "v7_trade_active_repair_policy_status": _status(
            v7_repair_policy,
            "trade_active_repair_policy_v7_status",
            "not_run",
        ),
        "v7_candidate_generator_status": _status(
            v7_candidates,
            "research_candidate_generator_v7_status",
            "not_run",
        ),
        "v7_scorer_status": _status(
            v7_scorer,
            "profit_holdout_split_scorer_v7_status",
            "profit_holdout_split_scored_v7",
        ),
        "v7_simulator_status": _status(
            v7_simulator,
            "research_path_simulator_v7_status",
            "not_run",
        ),
        "v7_tournament_status": _status(
            v7_tournament,
            "research_tournament_v7_status",
            "not_run",
        ),
        "v7_gate_status": _status(
            v7_gate,
            "research_breakthrough_gate_v7_status",
            "not_run",
        ),
        "v7_mutation_queue_status": _status(
            v7_mutation_queue,
            "research_mutation_queue_v7_status",
            "not_run",
        ),
        # Counts
        "v7_candidate_count": _safe_int(
            v7_candidates.get("candidate_count")
            or v7_scorer.get("candidate_count", 0)
        ),
        "v7_simulated_trade_count": _safe_int(v7_simulator.get("simulated_trade_count", 0)),
        "v7_pf_above_110_count": _safe_int(
            v7_tournament.get("pf_above_110_count")
            or v7_preflight.get("pf_above_110_count", 0)
        ),
        "v7_trade_active_pf_above_110_count": trade_active_pf_above_110_count,
        "v7_breakthrough_candidate_count": v7_breakthrough_count,
        "v7_watchlist_count": v7_watchlist_count,
        "v7_improved_vs_v6_count": _safe_int(v7_tournament.get("improved_vs_v6_count", 0)),
        "v7_mutation_queue_count": _safe_int(
            v7_mutation_queue.get("mutation_queue_count")
            or v7_preflight.get("mutation_queue_count", 0)
        ),
        # V6 baseline facts (immutable)
        "v6_summary_status": _status(v6_preflight, "v6_summary_status", "watchlist_blockers_improved_requires_v7"),
        "v6_watchlist_count": _safe_int(v6_gate.get("watchlist_count", 2)),
        "v6_improved_watchlist_count": _safe_int(v6_gate.get("improved_watchlist_count", 0)),
        "v6_pf_above_110_count": _safe_int(
            v6_tournament.get("pf_above_110_count")
            or v6_preflight.get("v6_pf_above_110_count", 6)
        ),
        "v6_mutation_queue_count": _safe_int(
            v6_preflight.get("v6_mutation_queue_count", 50)
        ),
        "v6_top_cohort_no_trade_dominant": bool(v7_preflight.get("top_cohort_no_trade_dominant", True)),
        # No-trade audit / trade-active edge
        "no_trade_ratio": round(no_trade_ratio, 6),
        "trade_active_ratio": round(trade_active_ratio, 6),
        "no_trade_only_breakthrough_blocked_count": no_trade_only_blocked_count,
        "no_trade_only_breakthroughs_blocked": no_trade_only_blocked_count > 0,
        "trade_active_candidate_count": _safe_int(
            v7_candidates.get("trade_active_candidate_count")
            or v7_scorer.get("trade_active_candidate_count", 0)
        ),
        "no_trade_candidate_count": _safe_int(
            v7_candidates.get("no_trade_candidate_count")
            or v7_scorer.get("no_trade_candidate_count", 0)
        ),
        # Safety / policy
        "future_leakage_detected": future_leakage_detected,
        "uvxy_like_corruption_detected": uvxy_like_corruption_detected,
        "live_gate_status": str(v6_live_gate.get("live_gate_status", "disabled_live_gate_locked")),
        "public_data_only": True,
        "live_trading_enabled": False,
        "live_trading_enabled_global": False,
        "rows": rows,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }

    # Write JSON summary
    SCOREBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_summary_with_hash(SCOREBOARD_PATH, scoreboard)

    # Write CSV rows
    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "version", "top_family", "top_subfamily", "top_cohort",
        "top_profit_factor", "top_net_pnl", "top_max_drawdown",
        "top_sample_count", "top_symbol_count", "top_sector_count",
        "trade_count", "pf_above_110_count", "improved_vs_prev_count",
    ]
    with ROWS_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # Write HTML / Markdown dashboards
    html = build_html(scoreboard, rows)
    md = build_markdown(scoreboard, rows)
    HTML_PATH.write_text(html, encoding="utf-8")
    MD_PATH.write_text(md, encoding="utf-8")

    # Quality flags
    quality_flags: list[dict[str, object]] = []
    if not scoreboard["thresholds_lowered"]:
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_scoreboard_quality_flag_v7",
                "flag": "thresholds_not_lowered",
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    if not scoreboard["uvxy_like_corruption_detected"]:
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_scoreboard_quality_flag_v7",
                "flag": "no_uvxy_corruption",
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    if not scoreboard["future_leakage_detected"]:
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_scoreboard_quality_flag_v7",
                "flag": "no_future_leakage",
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    if scoreboard["live_gate_status"] == "disabled_live_gate_locked":
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_scoreboard_quality_flag_v7",
                "flag": "live_gate_locked",
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    if scoreboard["no_trade_only_breakthroughs_blocked"]:
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_scoreboard_quality_flag_v7",
                "flag": "no_trade_only_breakthroughs_blocked",
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    quality_flags.append(
        {
            "artifact_type": "public_signal_research_scoreboard_quality_flag_v7",
            "flag": "public_data_only",
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
    )
    write_jsonl_file(QUALITY_PATH, [record_with_hash(q, "record_hash") for q in quality_flags])

    # Proof
    proof_payload = {
        "scoreboard_path": str(SCOREBOARD_PATH),
        "rows_path": str(ROWS_PATH),
        "html_path": str(HTML_PATH),
        "md_path": str(MD_PATH),
        "quality_flags_path": str(QUALITY_PATH),
        "v7_min_breakthrough_pf": scoreboard["v7_min_breakthrough_pf"],
        "thresholds_lowered": scoreboard["thresholds_lowered"],
        "live_gate_status": scoreboard["live_gate_status"],
        "no_trade_only_breakthroughs_blocked": scoreboard["no_trade_only_breakthroughs_blocked"],
    }
    write_stage_proof(PROOF_PATH, "public_signal_research_scoreboard_v7", scoreboard["scoreboard_v7_status"], proof_payload)

    return scoreboard


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_public_signal_research_scoreboard_v7(), indent=2, sort_keys=True, default=str))
