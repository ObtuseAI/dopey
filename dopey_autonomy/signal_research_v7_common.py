"""Shared helpers for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7.

V7 takes the 2 V6 improved watchlist candidates, the 6 PF-above-threshold V6
candidates, and the 50 V6 mutation queue entries, then attempts to convert
no-trade-dominant watchlist results into honest trade-active breakthroughs.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import (
    ARTIFACT_ROOT,
    LIVE_GATE_ROOT,
    SCOREBOARD_ROOT,
    read_json_file,
    read_jsonl_file,
    record_with_hash,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_research_v6_common import (
    RESEARCH_V6_ROOT,
    V6_ALL_SUBFAMILIES,
    V6_CONTINUATION_SUBFAMILIES,
    V6_VOLUME_SUBFAMILIES,
)
from dopey_wealth_engine.common import REPO_ROOT
from dopey_core.repo_paths import REPORTS_DIR


__all__ = [
    "load_v6_summary",
    "load_v6_preflight_summary",
    "load_v6_validation_summary",
    "load_v6_tournament_summary",
    "load_v6_gate_summary",
    "load_v6_mutation_queue_records",
    "load_v6_mutation_queue_summary",
    "load_v6_watchlist_records",
    "load_v6_rejection_records",
    "load_v6_live_gate_status",
    "load_v6_timeout_records",
    "load_v6_simulator_summary",
    "load_v6_candidate_summary",
    "load_v6_tournament_leaderboard",
    "load_v6_tournament_holdout",
    "load_v6_tournament_comparison",
    "load_v6_mutation_exec_records",
    "load_v6_gate_rejection_analysis",
    "load_v6_trade_active_blocker_matrix",
    "is_forbidden_symbol",
    "utc_now_iso",
    "research_v7_proof_record",
    "write_stage_proof",
    "write_baseline_snapshot",
    "baseline_snapshot_sources_v6",
    "json_dump_safe",
]


RESEARCH_V7_VERSION = "dopey-public-signal-research-breakthrough-v7"
RESEARCH_V7_ROOT = ARTIFACT_ROOT / "signal_research_v7"
BASELINE_V6_ROOT = RESEARCH_V7_ROOT / "baseline_snapshots" / "v6"

# Workstream A — preflight / baseline freeze
PREFLIGHT_V7_SUMMARY_PATH = RESEARCH_V7_ROOT / "public_signal_research_v7_preflight_summary.json"
PREFLIGHT_V7_FLAGS_PATH = RESEARCH_V7_ROOT / "public_signal_research_v7_preflight_flags.jsonl"
PREFLIGHT_V7_PROOF_PATH = RESEARCH_V7_ROOT / "public_signal_research_v7_preflight_proof.jsonl"

BASELINE_FREEZE_V7_SUMMARY_PATH = RESEARCH_V7_ROOT / "public_signal_research_v7_baseline_freeze_summary.json"
BASELINE_SNAPSHOT_V7_MANIFEST_PATH = RESEARCH_V7_ROOT / "public_signal_research_v7_baseline_snapshot_manifest.jsonl"
BASELINE_FREEZE_V7_PROOF_PATH = RESEARCH_V7_ROOT / "public_signal_research_v7_baseline_freeze_proof.jsonl"

# Workstream B — no-trade contribution audit V7
NO_TRADE_CONTRIBUTION_RECORDS_V7_PATH = RESEARCH_V7_ROOT / "no_trade_contribution_records_v7.jsonl"
TRADE_ACTIVE_EDGE_RECORDS_V7_PATH = RESEARCH_V7_ROOT / "trade_active_edge_records_v7.jsonl"
NO_TRADE_DOMINANCE_FLAGS_V7_PATH = RESEARCH_V7_ROOT / "no_trade_dominance_flags_v7.jsonl"
NO_TRADE_AUDIT_V7_SUMMARY_PATH = RESEARCH_V7_ROOT / "no_trade_contribution_audit_v7_summary.json"
NO_TRADE_AUDIT_V7_PROOF_PATH = RESEARCH_V7_ROOT / "no_trade_contribution_audit_v7_proof.jsonl"

# Workstream C — V6 watchlist diagnosis V7
V6_WATCHLIST_DIAGNOSIS_V7_PATH = RESEARCH_V7_ROOT / "v6_watchlist_diagnosis_v7.jsonl"
V6_GATE_BLOCKER_ANALYSIS_V7_PATH = RESEARCH_V7_ROOT / "v6_gate_blocker_analysis_v7.jsonl"
V6_TRADE_ACTIVE_BLOCKER_MATRIX_V7_PATH = RESEARCH_V7_ROOT / "v6_trade_active_blocker_matrix_v7.jsonl"
V6_WATCHLIST_DIAGNOSIS_V7_SUMMARY_PATH = RESEARCH_V7_ROOT / "v6_watchlist_diagnosis_v7_summary.json"
V6_WATCHLIST_DIAGNOSIS_V7_PROOF_PATH = RESEARCH_V7_ROOT / "v6_watchlist_diagnosis_v7_proof.jsonl"

# Workstream D — V6 mutation queue executor V7
MUTATION_EXEC_V7_RECORDS_PATH = RESEARCH_V7_ROOT / "research_mutation_execution_records_v7.jsonl"
MUTATION_EXEC_V7_EXPANSION_PATH = RESEARCH_V7_ROOT / "research_mutation_expansion_records_v7.jsonl"
MUTATION_EXEC_V7_FAILURES_PATH = RESEARCH_V7_ROOT / "research_mutation_execution_failures_v7.jsonl"
MUTATION_EXEC_V7_SUMMARY_PATH = RESEARCH_V7_ROOT / "research_mutation_queue_executor_v7_summary.json"
MUTATION_EXEC_V7_PROOF_PATH = RESEARCH_V7_ROOT / "research_mutation_queue_executor_v7_proof.jsonl"

# Workstream E — trade-active repair policy V7
TRADE_ACTIVE_REPAIR_POLICY_V7_PATH = RESEARCH_V7_ROOT / "trade_active_repair_policy_v7.json"
TRADE_ACTIVE_REPAIR_RULES_V7_PATH = RESEARCH_V7_ROOT / "trade_active_repair_rules_v7.jsonl"
FUTURE_LEAKAGE_GUARD_V7_PATH = RESEARCH_V7_ROOT / "future_leakage_guard_records_v7.jsonl"
TRADE_ACTIVE_REPAIR_POLICY_V7_SUMMARY_PATH = RESEARCH_V7_ROOT / "trade_active_repair_policy_v7_summary.json"
TRADE_ACTIVE_REPAIR_POLICY_V7_PROOF_PATH = RESEARCH_V7_ROOT / "trade_active_repair_policy_v7_proof.jsonl"

# Workstream F — candidate generator V7
CANDIDATES_V7_PATH = RESEARCH_V7_ROOT / "research_signal_candidates_v7.jsonl"
DENSITY_SCHEDULE_V7_PATH = RESEARCH_V7_ROOT / "research_candidate_density_schedule_v7.jsonl"
CANDIDATE_RANKINGS_V7_PATH = RESEARCH_V7_ROOT / "research_candidate_quality_rankings_v7.jsonl"
CANDIDATE_GENERATOR_V7_SUMMARY_PATH = RESEARCH_V7_ROOT / "research_candidate_generator_v7_summary.json"
CANDIDATE_GENERATOR_V7_PROOF_PATH = RESEARCH_V7_ROOT / "research_candidate_generator_v7_proof.jsonl"

# Workstream G — pre-simulation scorer V7
PROFIT_HOLDOUT_SPLIT_SCORES_V7_PATH = RESEARCH_V7_ROOT / "profit_holdout_split_scores_v7.jsonl"
PRIORITY_V7_PATH = RESEARCH_V7_ROOT / "candidate_pre_simulation_priority_v7.jsonl"
SCORER_V7_SUMMARY_PATH = RESEARCH_V7_ROOT / "profit_holdout_split_scorer_v7_summary.json"
SCORER_V7_PROOF_PATH = RESEARCH_V7_ROOT / "profit_holdout_split_scorer_v7_proof.jsonl"

# Workstream H — path simulator V7
TRADES_V7_PATH = RESEARCH_V7_ROOT / "research_path_trades_v7.jsonl"
EXIT_EVENTS_V7_PATH = RESEARCH_V7_ROOT / "research_path_exit_events_v7.jsonl"
SIMULATOR_QUALITY_V7_PATH = RESEARCH_V7_ROOT / "research_path_simulator_quality_flags_v7.jsonl"
SIMULATOR_V7_SUMMARY_PATH = RESEARCH_V7_ROOT / "research_path_simulator_v7_summary.json"
SIMULATOR_V7_PROOF_PATH = RESEARCH_V7_ROOT / "research_path_simulator_v7_proof.jsonl"

# Workstream I — tournament V7
TOURNAMENT_SCORES_V7_PATH = RESEARCH_V7_ROOT / "research_tournament_scores_v7.jsonl"
TOURNAMENT_LEADERBOARD_V7_PATH = RESEARCH_V7_ROOT / "research_tournament_leaderboard_v7.jsonl"
TOURNAMENT_HOLDOUT_V7_PATH = RESEARCH_V7_ROOT / "research_tournament_holdout_scores_v7.jsonl"
TOURNAMENT_REGIME_V7_PATH = RESEARCH_V7_ROOT / "research_tournament_regime_scores_v7.jsonl"
TOURNAMENT_COMPARISON_V7_PATH = RESEARCH_V7_ROOT / "research_v6_v7_comparison_v7.jsonl"
TOURNAMENT_V7_SUMMARY_PATH = RESEARCH_V7_ROOT / "research_tournament_v7_summary.json"
TOURNAMENT_V7_PROOF_PATH = RESEARCH_V7_ROOT / "research_tournament_v7_proof.jsonl"

# Workstream J — breakthrough gate V7
BREAKTHROUGH_V7_PATH = RESEARCH_V7_ROOT / "research_breakthrough_candidates_v7.jsonl"
WATCHLIST_V7_PATH = RESEARCH_V7_ROOT / "research_watchlist_candidates_v7.jsonl"
REJECTIONS_V7_PATH = RESEARCH_V7_ROOT / "research_breakthrough_rejections_v7.jsonl"
GATE_V7_SUMMARY_PATH = RESEARCH_V7_ROOT / "research_breakthrough_gate_v7_summary.json"
GATE_V7_PROOF_PATH = RESEARCH_V7_ROOT / "research_breakthrough_gate_v7_proof.jsonl"

# Workstream K — mutation queue V7
MUTATION_QUEUE_V7_PATH = RESEARCH_V7_ROOT / "research_mutation_queue_v7.jsonl"
MUTATION_QUEUE_V7_SUMMARY_PATH = RESEARCH_V7_ROOT / "research_mutation_queue_v7_summary.json"
MUTATION_QUEUE_V7_PROOF_PATH = RESEARCH_V7_ROOT / "research_mutation_queue_v7_proof.jsonl"

# V6 source paths (immutable after baseline freeze)
V6_SUMMARY_PATH = RESEARCH_V6_ROOT / "public_signal_research_breakthrough_v6_summary.json"
V6_PREFLIGHT_SUMMARY_PATH = RESEARCH_V6_ROOT / "public_signal_research_v6_preflight_summary.json"
V6_VALIDATION_SUMMARY_PATH = RESEARCH_V6_ROOT / "public_signal_research_breakthrough_v6_validation_summary.json"
V6_TIMEOUT_RECORDS_PATH = RESEARCH_V6_ROOT / "public_signal_research_breakthrough_v6_timeout_records.jsonl"
V6_TOURNAMENT_SUMMARY_PATH = RESEARCH_V6_ROOT / "research_tournament_v6_summary.json"
V6_TOURNAMENT_LEADERBOARD_PATH = RESEARCH_V6_ROOT / "research_tournament_leaderboard_v6.jsonl"
V6_TOURNAMENT_HOLDOUT_PATH = RESEARCH_V6_ROOT / "research_tournament_holdout_scores_v6.jsonl"
V6_TOURNAMENT_COMPARISON_PATH = RESEARCH_V6_ROOT / "research_v5_v6_comparison_v6.jsonl"
V6_GATE_SUMMARY_PATH = RESEARCH_V6_ROOT / "research_breakthrough_gate_v6_summary.json"
V6_GATE_REJECTIONS_PATH = RESEARCH_V6_ROOT / "research_breakthrough_rejections_v6.jsonl"
V6_WATCHLIST_PATH = RESEARCH_V6_ROOT / "research_watchlist_candidates_v6.jsonl"
V6_MUTATION_QUEUE_PATH = RESEARCH_V6_ROOT / "research_mutation_queue_v6.jsonl"
V6_MUTATION_QUEUE_SUMMARY_PATH = RESEARCH_V6_ROOT / "research_mutation_queue_v6_summary.json"
V6_MUTATION_EXEC_RECORDS_PATH = RESEARCH_V6_ROOT / "research_mutation_execution_records_v6.jsonl"
V6_SIMULATOR_SUMMARY_PATH = RESEARCH_V6_ROOT / "research_path_simulator_v6_summary.json"
V6_CANDIDATE_SUMMARY_PATH = RESEARCH_V6_ROOT / "research_candidate_generator_v6_summary.json"
V6_SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v6.json"
V6_LIVE_GATE_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v6.json"
V6_GATE_REJECTION_ANALYSIS_PATH = RESEARCH_V6_ROOT / "v5_gate_rejection_analysis_v6.jsonl"
V6_BREAKTHROUGH_BLOCKER_MATRIX_PATH = RESEARCH_V6_ROOT / "v5_breakthrough_blocker_matrix_v6.jsonl"
V6_NO_TRADE_RULES_PATH = RESEARCH_V6_ROOT / "breakthrough_blocker_repair_rules_v6.jsonl"
V6_BLOCKER_REPAIR_POLICY_PATH = RESEARCH_V6_ROOT / "breakthrough_blocker_repair_policy_v6.json"

# Thresholds (hard floor, never lowered)
MIN_BREAKTHROUGH_PF = 1.10
MIN_BREAKTHROUGH_SAMPLE = 30
MIN_BREAKTHROUGH_SYMBOLS = 8
MIN_BREAKTHROUGH_SECTORS = 8
MIN_BREAKTHROUGH_SPLIT_PASS = 0.55
DRAWDOWN_ABS_MAX = 2500.0

# V7 caps
V7_TARGET_CANDIDATES = 30_000
V7_MIN_CANDIDATES = 18_000
WATCHDOG_CANDIDATE_CAP_V7 = 50_000
V7_TARGET_TRADES = 18_000
V7_MIN_TRADES = 10_000
WATCHDOG_SIM_CAP_V7 = 30_000
V7_MAX_FAMILY_SHARE = 0.60
V7_MAX_NO_TRADE_RATIO = 0.35
V7_MIN_TRADE_ACTIVE_SAMPLE = 20

V7_CONTINUATION_SUBFAMILIES = V6_CONTINUATION_SUBFAMILIES
V7_VOLUME_SUBFAMILIES = V6_VOLUME_SUBFAMILIES
V7_ALL_SUBFAMILIES = V7_CONTINUATION_SUBFAMILIES + V7_VOLUME_SUBFAMILIES
V7_HOLD_WINDOWS = (1, 2, 3, 5, 7)

FORBIDDEN_TOKENS = ("SIM", "TEST", "FIXTURE", "SYNTH")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def research_v7_proof_record(proof_id: str, status: str, payload: dict[str, object]) -> dict[str, object]:
    record = {
        "artifact_type": "public_signal_research_v7_proof",
        "proof_id": proof_id,
        "status": status,
        "timestamp": utc_now_iso(),
        "bundle_version": RESEARCH_V7_VERSION,
        "payload": dict(payload),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(record, "proof_hash")


def write_stage_proof(path: Path, proof_id: str, status: str, summary: dict[str, object]) -> None:
    write_jsonl_file(path, [research_v7_proof_record(proof_id, status, summary)])


def is_forbidden_symbol(symbol: str) -> bool:
    upper = symbol.upper()
    return any(t in upper for t in FORBIDDEN_TOKENS)


def load_v6_summary() -> dict[str, object]:
    return read_json_file(V6_SUMMARY_PATH)


def load_v6_preflight_summary() -> dict[str, object]:
    return read_json_file(V6_PREFLIGHT_SUMMARY_PATH)


def load_v6_validation_summary() -> dict[str, object]:
    return read_json_file(V6_VALIDATION_SUMMARY_PATH)


def load_v6_tournament_summary() -> dict[str, object]:
    return read_json_file(V6_TOURNAMENT_SUMMARY_PATH)


def load_v6_gate_summary() -> dict[str, object]:
    return read_json_file(V6_GATE_SUMMARY_PATH)


def load_v6_mutation_queue_records() -> list[dict[str, object]]:
    if V6_MUTATION_QUEUE_PATH.exists():
        return read_jsonl_file(V6_MUTATION_QUEUE_PATH)
    return []


def load_v6_mutation_queue_summary() -> dict[str, object]:
    return read_json_file(V6_MUTATION_QUEUE_SUMMARY_PATH)


def load_v6_watchlist_records() -> list[dict[str, object]]:
    if V6_WATCHLIST_PATH.exists():
        return read_jsonl_file(V6_WATCHLIST_PATH)
    return []


def load_v6_rejection_records() -> list[dict[str, object]]:
    if V6_GATE_REJECTIONS_PATH.exists():
        return read_jsonl_file(V6_GATE_REJECTIONS_PATH)
    return []


def load_v6_live_gate_status() -> dict[str, object]:
    return read_json_file(V6_LIVE_GATE_PATH)


def load_v6_timeout_records() -> list[dict[str, object]]:
    if V6_TIMEOUT_RECORDS_PATH.exists():
        return read_jsonl_file(V6_TIMEOUT_RECORDS_PATH)
    return []


def load_v6_simulator_summary() -> dict[str, object]:
    return read_json_file(V6_SIMULATOR_SUMMARY_PATH)


def load_v6_candidate_summary() -> dict[str, object]:
    return read_json_file(V6_CANDIDATE_SUMMARY_PATH)


def load_v6_tournament_leaderboard() -> list[dict[str, object]]:
    if V6_TOURNAMENT_LEADERBOARD_PATH.exists():
        return read_jsonl_file(V6_TOURNAMENT_LEADERBOARD_PATH)
    return []


def load_v6_tournament_holdout() -> list[dict[str, object]]:
    if V6_TOURNAMENT_HOLDOUT_PATH.exists():
        return read_jsonl_file(V6_TOURNAMENT_HOLDOUT_PATH)
    return []


def load_v6_tournament_comparison() -> list[dict[str, object]]:
    if V6_TOURNAMENT_COMPARISON_PATH.exists():
        return read_jsonl_file(V6_TOURNAMENT_COMPARISON_PATH)
    return []


def load_v6_mutation_exec_records() -> list[dict[str, object]]:
    if V6_MUTATION_EXEC_RECORDS_PATH.exists():
        return read_jsonl_file(V6_MUTATION_EXEC_RECORDS_PATH)
    return []


def load_v6_gate_rejection_analysis() -> list[dict[str, object]]:
    if V6_GATE_REJECTION_ANALYSIS_PATH.exists():
        return read_jsonl_file(V6_GATE_REJECTION_ANALYSIS_PATH)
    return []


def load_v6_trade_active_blocker_matrix() -> list[dict[str, object]]:
    if V6_BREAKTHROUGH_BLOCKER_MATRIX_PATH.exists():
        return read_jsonl_file(V6_BREAKTHROUGH_BLOCKER_MATRIX_PATH)
    return []


def load_v6_no_trade_rules() -> list[dict[str, object]]:
    if V6_NO_TRADE_RULES_PATH.exists():
        return read_jsonl_file(V6_NO_TRADE_RULES_PATH)
    return []


def load_v6_blocker_repair_policy() -> dict[str, object]:
    return read_json_file(V6_BLOCKER_REPAIR_POLICY_PATH)


def sha256_bytes(data: bytes) -> str:
    import hashlib as _hl
    return _hl.sha256(data).hexdigest()


def write_baseline_snapshot(src: Path, dest_dir: Path) -> dict[str, object] | None:
    if not src.exists():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    try:
        data = src.read_bytes()
    except OSError:
        return None
    dest.write_bytes(data)
    return {
        "source_path": str(src),
        "destination_path": str(dest),
        "file_size": len(data),
        "sha256": sha256_bytes(data),
        "copied": True,
        "baseline_snapshot": True,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
    }


def baseline_snapshot_sources_v6() -> list[Path]:
    """Immutable V6 sources to freeze before V7 mutates anything."""
    return [
        V6_SUMMARY_PATH,
        V6_PREFLIGHT_SUMMARY_PATH,
        V6_VALIDATION_SUMMARY_PATH,
        V6_TIMEOUT_RECORDS_PATH,
        RESEARCH_V6_ROOT / "research_tournament_v6_summary.json",
        RESEARCH_V6_ROOT / "research_tournament_leaderboard_v6.jsonl",
        RESEARCH_V6_ROOT / "research_tournament_holdout_scores_v6.jsonl",
        RESEARCH_V6_ROOT / "research_tournament_regime_scores_v6.jsonl",
        RESEARCH_V6_ROOT / "research_v5_v6_comparison_v6.jsonl",
        RESEARCH_V6_ROOT / "research_breakthrough_gate_v6_summary.json",
        RESEARCH_V6_ROOT / "research_breakthrough_rejections_v6.jsonl",
        RESEARCH_V6_ROOT / "research_watchlist_candidates_v6.jsonl",
        RESEARCH_V6_ROOT / "research_mutation_queue_v6.jsonl",
        RESEARCH_V6_ROOT / "research_mutation_queue_v6_summary.json",
        RESEARCH_V6_ROOT / "research_mutation_execution_records_v6.jsonl",
        RESEARCH_V6_ROOT / "research_mutation_execution_failures_v6.jsonl",
        RESEARCH_V6_ROOT / "research_mutation_expansion_records_v6.jsonl",
        RESEARCH_V6_ROOT / "breakthrough_blocker_repair_policy_v6.json",
        RESEARCH_V6_ROOT / "breakthrough_blocker_repair_rules_v6.jsonl",
        RESEARCH_V6_ROOT / "future_leakage_guard_records_v6.jsonl",
        RESEARCH_V6_ROOT / "research_path_simulator_v6_summary.json",
        RESEARCH_V6_ROOT / "research_candidate_generator_v6_summary.json",
        RESEARCH_V6_ROOT / "v5_gate_rejection_analysis_v6.jsonl",
        RESEARCH_V6_ROOT / "v5_breakthrough_blocker_matrix_v6.jsonl",
        RESEARCH_V6_ROOT / "v5_watchlist_diagnosis_v6.jsonl",
        V6_LIVE_GATE_PATH,
        SCOREBOARD_ROOT / "public_signal_research_scoreboard_v6.json",
        SCOREBOARD_ROOT / "public_signal_research_dashboard_v6.html",
        SCOREBOARD_ROOT / "public_signal_research_dashboard_v6.md",
        REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6_REPORT.md",
        REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6_ARTIFACT_LEDGER.md",
        REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6_COMMANDS.md",
        RESEARCH_V6_ROOT / "public_signal_research_breakthrough_v6_session_copy_manifest.json",
    ]


def json_dump_safe(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, default=str)
