"""Shared helpers for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6.

V6 takes the 6 V5 PF-above-threshold watchlist candidates and the 132 V5
mutation queue entries, then repairs the remaining breakthrough blockers.
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
from dopey_autonomy.signal_research_v5_common import (
    RESEARCH_V5_ROOT,
    V5_CONTINUATION_SUBFAMILIES,
    V5_VOLUME_SUBFAMILIES,
)
from dopey_wealth_engine.common import REPO_ROOT
from dopey_core.repo_paths import REPORTS_DIR


__all__ = [
    "load_v5_summary",
    "load_v5_preflight_summary",
    "load_v5_validation_summary",
    "load_v5_tournament_summary",
    "load_v5_gate_summary",
    "load_v5_mutation_queue_records",
    "load_v5_mutation_queue_summary",
    "load_v5_watchlist_records",
    "load_v5_rejection_records",
    "load_v5_live_gate_status",
    "load_v5_timeout_records",
    "load_v5_expensive_lane_summary",
    "load_v5_simulator_summary",
    "load_v5_candidate_summary",
    "is_forbidden_symbol",
    "utc_now_iso",
    "research_v6_proof_record",
    "write_stage_proof",
    "write_baseline_snapshot",
    "baseline_snapshot_sources_v5",
    "json_dump_safe",
]


RESEARCH_V6_VERSION = "dopey-public-signal-research-breakthrough-v6"
RESEARCH_V6_ROOT = ARTIFACT_ROOT / "signal_research_v6"
BASELINE_V5_ROOT = RESEARCH_V6_ROOT / "baseline_snapshots" / "v5"

# Workstream A — preflight / baseline freeze
PREFLIGHT_V6_SUMMARY_PATH = RESEARCH_V6_ROOT / "public_signal_research_v6_preflight_summary.json"
PREFLIGHT_V6_FLAGS_PATH = RESEARCH_V6_ROOT / "public_signal_research_v6_preflight_flags.jsonl"
PREFLIGHT_V6_PROOF_PATH = RESEARCH_V6_ROOT / "public_signal_research_v6_preflight_proof.jsonl"

BASELINE_FREEZE_V6_SUMMARY_PATH = RESEARCH_V6_ROOT / "public_signal_research_v6_baseline_freeze_summary.json"
BASELINE_SNAPSHOT_V6_MANIFEST_PATH = RESEARCH_V6_ROOT / "public_signal_research_v6_baseline_snapshot_manifest.jsonl"
BASELINE_FREEZE_V6_PROOF_PATH = RESEARCH_V6_ROOT / "public_signal_research_v6_baseline_freeze_proof.jsonl"

# Workstream B — V5 gate rejection / watchlist diagnosis
V5_GATE_REJECTION_ANALYSIS_V6_PATH = RESEARCH_V6_ROOT / "v5_gate_rejection_analysis_v6.jsonl"
V5_BREAKTHROUGH_BLOCKER_MATRIX_V6_PATH = RESEARCH_V6_ROOT / "v5_breakthrough_blocker_matrix_v6.jsonl"
V5_WATCHLIST_DIAGNOSIS_V6_PATH = RESEARCH_V6_ROOT / "v5_watchlist_diagnosis_v6.jsonl"
V5_GATE_REJECTION_ANALYZER_V6_SUMMARY_PATH = RESEARCH_V6_ROOT / "v5_gate_rejection_analyzer_v6_summary.json"
V5_GATE_REJECTION_ANALYZER_V6_PROOF_PATH = RESEARCH_V6_ROOT / "v5_gate_rejection_analyzer_v6_proof.jsonl"

# Workstream C — V5 mutation queue executor V6
MUTATION_EXEC_V6_RECORDS_PATH = RESEARCH_V6_ROOT / "research_mutation_execution_records_v6.jsonl"
MUTATION_EXEC_V6_EXPANSION_PATH = RESEARCH_V6_ROOT / "research_mutation_expansion_records_v6.jsonl"
MUTATION_EXEC_V6_FAILURES_PATH = RESEARCH_V6_ROOT / "research_mutation_execution_failures_v6.jsonl"
MUTATION_EXEC_V6_SUMMARY_PATH = RESEARCH_V6_ROOT / "research_mutation_queue_executor_v6_summary.json"
MUTATION_EXEC_V6_PROOF_PATH = RESEARCH_V6_ROOT / "research_mutation_queue_executor_v6_proof.jsonl"

# Workstream D — blocker repair policy
BLOCKER_REPAIR_POLICY_V6_PATH = RESEARCH_V6_ROOT / "breakthrough_blocker_repair_policy_v6.json"
BLOCKER_REPAIR_RULES_V6_PATH = RESEARCH_V6_ROOT / "breakthrough_blocker_repair_rules_v6.jsonl"
FUTURE_LEAKAGE_GUARD_V6_PATH = RESEARCH_V6_ROOT / "future_leakage_guard_records_v6.jsonl"
BLOCKER_REPAIR_POLICY_V6_SUMMARY_PATH = RESEARCH_V6_ROOT / "breakthrough_blocker_repair_policy_v6_summary.json"
BLOCKER_REPAIR_POLICY_V6_PROOF_PATH = RESEARCH_V6_ROOT / "breakthrough_blocker_repair_policy_v6_proof.jsonl"

# Workstream E — candidate generator V6
CANDIDATES_V6_PATH = RESEARCH_V6_ROOT / "research_signal_candidates_v6.jsonl"
DENSITY_SCHEDULE_V6_PATH = RESEARCH_V6_ROOT / "research_candidate_density_schedule_v6.jsonl"
CANDIDATE_RANKINGS_V6_PATH = RESEARCH_V6_ROOT / "research_candidate_quality_rankings_v6.jsonl"
CANDIDATE_GENERATOR_V6_SUMMARY_PATH = RESEARCH_V6_ROOT / "research_candidate_generator_v6_summary.json"
CANDIDATE_GENERATOR_V6_PROOF_PATH = RESEARCH_V6_ROOT / "research_candidate_generator_v6_proof.jsonl"

# Workstream F — pre-simulation scorer V6
PROFIT_HOLDOUT_SPLIT_SCORES_V6_PATH = RESEARCH_V6_ROOT / "profit_holdout_split_scores_v6.jsonl"
PRIORITY_V6_PATH = RESEARCH_V6_ROOT / "candidate_pre_simulation_priority_v6.jsonl"
SCORER_V6_SUMMARY_PATH = RESEARCH_V6_ROOT / "profit_holdout_split_scorer_v6_summary.json"
SCORER_V6_PROOF_PATH = RESEARCH_V6_ROOT / "profit_holdout_split_scorer_v6_proof.jsonl"

# Workstream G — path simulator V6
TRADES_V6_PATH = RESEARCH_V6_ROOT / "research_path_trades_v6.jsonl"
EXIT_EVENTS_V6_PATH = RESEARCH_V6_ROOT / "research_path_exit_events_v6.jsonl"
SIMULATOR_QUALITY_V6_PATH = RESEARCH_V6_ROOT / "research_path_simulator_quality_flags_v6.jsonl"
SIMULATOR_V6_SUMMARY_PATH = RESEARCH_V6_ROOT / "research_path_simulator_v6_summary.json"
SIMULATOR_V6_PROOF_PATH = RESEARCH_V6_ROOT / "research_path_simulator_v6_proof.jsonl"

# Workstream H — tournament V6
TOURNAMENT_SCORES_V6_PATH = RESEARCH_V6_ROOT / "research_tournament_scores_v6.jsonl"
TOURNAMENT_LEADERBOARD_V6_PATH = RESEARCH_V6_ROOT / "research_tournament_leaderboard_v6.jsonl"
TOURNAMENT_HOLDOUT_V6_PATH = RESEARCH_V6_ROOT / "research_tournament_holdout_scores_v6.jsonl"
TOURNAMENT_REGIME_V6_PATH = RESEARCH_V6_ROOT / "research_tournament_regime_scores_v6.jsonl"
TOURNAMENT_COMPARISON_V6_PATH = RESEARCH_V6_ROOT / "research_v5_v6_comparison_v6.jsonl"
TOURNAMENT_V6_SUMMARY_PATH = RESEARCH_V6_ROOT / "research_tournament_v6_summary.json"
TOURNAMENT_V6_PROOF_PATH = RESEARCH_V6_ROOT / "research_tournament_v6_proof.jsonl"

# Workstream I — breakthrough gate V6
BREAKTHROUGH_V6_PATH = RESEARCH_V6_ROOT / "research_breakthrough_candidates_v6.jsonl"
WATCHLIST_V6_PATH = RESEARCH_V6_ROOT / "research_watchlist_candidates_v6.jsonl"
REJECTIONS_V6_PATH = RESEARCH_V6_ROOT / "research_breakthrough_rejections_v6.jsonl"
GATE_V6_SUMMARY_PATH = RESEARCH_V6_ROOT / "research_breakthrough_gate_v6_summary.json"
GATE_V6_PROOF_PATH = RESEARCH_V6_ROOT / "research_breakthrough_gate_v6_proof.jsonl"

# Workstream J — mutation queue V6
MUTATION_QUEUE_V6_PATH = RESEARCH_V6_ROOT / "research_mutation_queue_v6.jsonl"
MUTATION_QUEUE_V6_SUMMARY_PATH = RESEARCH_V6_ROOT / "research_mutation_queue_v6_summary.json"
MUTATION_QUEUE_V6_PROOF_PATH = RESEARCH_V6_ROOT / "research_mutation_queue_v6_proof.jsonl"

# V5 source paths (immutable after baseline freeze)
V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "public_signal_research_breakthrough_v5_summary.json"
V5_PREFLIGHT_SUMMARY_PATH = RESEARCH_V5_ROOT / "public_signal_research_v5_preflight_summary.json"
V5_VALIDATION_SUMMARY_PATH = RESEARCH_V5_ROOT / "public_signal_research_breakthrough_v5_validation_summary.json"
V5_TOURNAMENT_SUMMARY_PATH = RESEARCH_V5_ROOT / "research_tournament_v5_summary.json"
V5_GATE_SUMMARY_PATH = RESEARCH_V5_ROOT / "research_breakthrough_gate_v5_summary.json"
V5_MUTATION_QUEUE_PATH = RESEARCH_V5_ROOT / "research_mutation_queue_v5.jsonl"
V5_MUTATION_QUEUE_SUMMARY_PATH = RESEARCH_V5_ROOT / "research_mutation_queue_v5_summary.json"
V5_WATCHLIST_PATH = RESEARCH_V5_ROOT / "research_watchlist_candidates_v5.jsonl"
V5_REJECTIONS_PATH = RESEARCH_V5_ROOT / "research_breakthrough_rejections_v5.jsonl"
V5_LIVE_GATE_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v5.json"
V5_TIMEOUT_RECORDS_PATH = RESEARCH_V5_ROOT / "public_signal_research_breakthrough_v5_timeout_records.jsonl"
V5_EXPENSIVE_LANE_SUMMARY_PATH = RESEARCH_V5_ROOT / "public_signal_research_expensive_lane_summary_v5.json"
V5_SIMULATOR_SUMMARY_PATH = RESEARCH_V6_ROOT / "research_path_simulator_v5_summary.json"
V5_CANDIDATE_SUMMARY_PATH = RESEARCH_V5_ROOT / "research_candidate_generator_v5_summary.json"

# Thresholds (hard floor, never lowered)
MIN_BREAKTHROUGH_PF = 1.10
MIN_BREAKTHROUGH_SAMPLE = 30
MIN_BREAKTHROUGH_SYMBOLS = 8
MIN_BREAKTHROUGH_SECTORS = 8
MIN_BREAKTHROUGH_SPLIT_PASS = 0.55
DRAWDOWN_ABS_MAX = 2500.0

# V6 caps
V6_TARGET_CANDIDATES = 35_000
V6_MIN_CANDIDATES = 20_000
WATCHDOG_CANDIDATE_CAP_V6 = 50_000
V6_TARGET_TRADES = 20_000
V6_MIN_TRADES = 12_000
WATCHDOG_SIM_CAP_V6 = 30_000
V6_MAX_FAMILY_SHARE = 0.65

V6_CONTINUATION_SUBFAMILIES = V5_CONTINUATION_SUBFAMILIES
V6_VOLUME_SUBFAMILIES = V5_VOLUME_SUBFAMILIES
V6_ALL_SUBFAMILIES = V6_CONTINUATION_SUBFAMILIES + V6_VOLUME_SUBFAMILIES
V6_HOLD_WINDOWS = (1, 2, 3, 5, 7)

FORBIDDEN_TOKENS = ("SIM", "TEST", "FIXTURE", "SYNTH")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def research_v6_proof_record(proof_id: str, status: str, payload: dict[str, object]) -> dict[str, object]:
    record = {
        "artifact_type": "public_signal_research_v6_proof",
        "proof_id": proof_id,
        "status": status,
        "timestamp": utc_now_iso(),
        "bundle_version": RESEARCH_V6_VERSION,
        "payload": dict(payload),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(record, "proof_hash")


def write_stage_proof(path: Path, proof_id: str, status: str, summary: dict[str, object]) -> None:
    write_jsonl_file(path, [research_v6_proof_record(proof_id, status, summary)])


def is_forbidden_symbol(symbol: str) -> bool:
    upper = symbol.upper()
    return any(t in upper for t in FORBIDDEN_TOKENS)


def load_v5_summary() -> dict[str, object]:
    return read_json_file(V5_SUMMARY_PATH)


def load_v5_preflight_summary() -> dict[str, object]:
    return read_json_file(V5_PREFLIGHT_SUMMARY_PATH)


def load_v5_validation_summary() -> dict[str, object]:
    return read_json_file(V5_VALIDATION_SUMMARY_PATH)


def load_v5_tournament_summary() -> dict[str, object]:
    return read_json_file(V5_TOURNAMENT_SUMMARY_PATH)


def load_v5_gate_summary() -> dict[str, object]:
    return read_json_file(V5_GATE_SUMMARY_PATH)


def load_v5_mutation_queue_records() -> list[dict[str, object]]:
    if V5_MUTATION_QUEUE_PATH.exists():
        return read_jsonl_file(V5_MUTATION_QUEUE_PATH)
    return []


def load_v5_mutation_queue_summary() -> dict[str, object]:
    return read_json_file(V5_MUTATION_QUEUE_SUMMARY_PATH)


def load_v5_watchlist_records() -> list[dict[str, object]]:
    if V5_WATCHLIST_PATH.exists():
        return read_jsonl_file(V5_WATCHLIST_PATH)
    return []


def load_v5_rejection_records() -> list[dict[str, object]]:
    if V5_REJECTIONS_PATH.exists():
        return read_jsonl_file(V5_REJECTIONS_PATH)
    return []


def load_v5_live_gate_status() -> dict[str, object]:
    return read_json_file(V5_LIVE_GATE_PATH)


def load_v5_timeout_records() -> list[dict[str, object]]:
    if V5_TIMEOUT_RECORDS_PATH.exists():
        return read_jsonl_file(V5_TIMEOUT_RECORDS_PATH)
    return []


def load_v5_expensive_lane_summary() -> dict[str, object]:
    return read_json_file(V5_EXPENSIVE_LANE_SUMMARY_PATH)


def load_v5_simulator_summary() -> dict[str, object]:
    return read_json_file(V5_SIMULATOR_SUMMARY_PATH)


def load_v5_candidate_summary() -> dict[str, object]:
    return read_json_file(V5_CANDIDATE_SUMMARY_PATH)


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


def baseline_snapshot_sources_v5() -> list[Path]:
    """Immutable V5 sources to freeze before V6 mutates anything."""
    return [
        V5_SUMMARY_PATH,
        V5_PREFLIGHT_SUMMARY_PATH,
        V5_VALIDATION_SUMMARY_PATH,
        V5_TIMEOUT_RECORDS_PATH,
        RESEARCH_V5_ROOT / "research_tournament_v5_summary.json",
        RESEARCH_V5_ROOT / "research_tournament_leaderboard_v5.jsonl",
        RESEARCH_V5_ROOT / "research_breakthrough_gate_v5_summary.json",
        RESEARCH_V5_ROOT / "research_breakthrough_rejections_v5.jsonl",
        RESEARCH_V5_ROOT / "research_watchlist_candidates_v5.jsonl",
        RESEARCH_V5_ROOT / "research_mutation_queue_v5.jsonl",
        RESEARCH_V5_ROOT / "research_mutation_queue_v5_summary.json",
        RESEARCH_V5_ROOT / "research_path_simulator_v5_summary.json",
        RESEARCH_V5_ROOT / "research_candidate_generator_v5_summary.json",
        V5_LIVE_GATE_PATH,
        SCOREBOARD_ROOT / "public_signal_research_scoreboard_v5.json",
        REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5_REPORT.md",
        REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5_ARTIFACT_LEDGER.md",
        REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5_COMMANDS.md",
        RESEARCH_V5_ROOT / "public_signal_research_breakthrough_v5_session_copy_manifest.json",
    ]


def json_dump_safe(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, default=str)
