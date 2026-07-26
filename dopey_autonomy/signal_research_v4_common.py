"""Shared helpers for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.signal_research_common import is_quarantined_signature, quarantine_overlap  # noqa: F401
from dopey_autonomy.signal_research_v2_common import (
    MUTATION_QUEUE_V2_PATH,
    RESEARCH_V2_ROOT,
    stable_family_id_from_label,
)
from dopey_autonomy.signal_research_v3_common import (
    MUTATION_QUEUE_V3_PATH,
    RESEARCH_V3_ROOT,
    STABLE_FAMILY_CONTINUATION,
    STABLE_FAMILY_VOLUME,
)
from dopey_autonomy.public_champion_common import ARTIFACT_ROOT, read_json_file, record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_wealth_engine.common import REPO_ROOT


__all__ = [
    "is_quarantined_signature",
    "quarantine_overlap",
    "stable_family_id_from_label",
    "load_v3_gate_summary",
    "load_v3_tournament_summary",
    "load_v3_mutation_queue_summary",
    "load_v3_path_simulator_summary",
    "load_v3_candidate_summary",
    "normalize_stable_family_id",
]


RESEARCH_V4_VERSION = "dopey-public-signal-research-breakthrough-v4"
RESEARCH_V4_ROOT = ARTIFACT_ROOT / "signal_research_v4"

V3_SUMMARY_PATH = RESEARCH_V3_ROOT / "public_signal_research_breakthrough_v3_summary.json"
V3_GATE_SUMMARY_PATH = RESEARCH_V3_ROOT / "research_breakthrough_gate_v3_summary.json"
V3_TOURNAMENT_SUMMARY_PATH = RESEARCH_V3_ROOT / "research_tournament_v3_summary.json"
V3_CANDIDATE_SUMMARY_PATH = RESEARCH_V3_ROOT / "research_candidate_generator_v3_summary.json"
V3_PATH_SIMULATOR_SUMMARY_PATH = RESEARCH_V3_ROOT / "research_path_simulator_v3_summary.json"
V3_MUTATION_QUEUE_SUMMARY_PATH = RESEARCH_V3_ROOT / "research_mutation_queue_v3_summary.json"
V3_MUTATION_EXEC_SUMMARY_PATH = RESEARCH_V3_ROOT / "research_mutation_queue_executor_v3_summary.json"
V3_NO_TRADE_PATH = RESEARCH_V3_ROOT / "research_no_trade_filter_records_v3.jsonl"

# V4 artifact paths
PREFLIGHT_SUMMARY_PATH = RESEARCH_V4_ROOT / "public_signal_research_v4_preflight_summary.json"
PREFLIGHT_FLAGS_PATH = RESEARCH_V4_ROOT / "public_signal_research_v4_preflight_flags.jsonl"
PREFLIGHT_PROOF_PATH = RESEARCH_V4_ROOT / "public_signal_research_v4_preflight_proof.jsonl"

MUTATION_EXEC_RECORDS_PATH = RESEARCH_V4_ROOT / "research_mutation_execution_records_v4.jsonl"
MUTATION_EXEC_FAILURES_PATH = RESEARCH_V4_ROOT / "research_mutation_execution_failures_v4.jsonl"
MUTATION_EXEC_SUMMARY_PATH = RESEARCH_V4_ROOT / "research_mutation_queue_executor_v4_summary.json"
MUTATION_EXEC_PROOF_PATH = RESEARCH_V4_ROOT / "research_mutation_queue_executor_v4_proof.jsonl"

PROFITABLE_SLICES_PATH = RESEARCH_V4_ROOT / "profitable_slice_records_v4.jsonl"
LOSS_DRIVER_SLICES_PATH = RESEARCH_V4_ROOT / "loss_driver_slice_records_v4.jsonl"
SLICE_PRUNING_PATH = RESEARCH_V4_ROOT / "slice_pruning_recommendations_v4.jsonl"
SLICE_RETUNE_PATH = RESEARCH_V4_ROOT / "slice_retune_recommendations_v4.jsonl"
PROFITABLE_SLICE_SUMMARY_PATH = RESEARCH_V4_ROOT / "profitable_slice_miner_v4_summary.json"
PROFITABLE_SLICE_PROOF_PATH = RESEARCH_V4_ROOT / "profitable_slice_miner_v4_proof.jsonl"

NO_TRADE_RULES_PATH = RESEARCH_V4_ROOT / "no_trade_filter_rules_v4.jsonl"
SELECTIVITY_POLICY_PATH = RESEARCH_V4_ROOT / "selectivity_policy_v4.json"
NO_TRADE_QUALITY_FLAGS_PATH = RESEARCH_V4_ROOT / "no_trade_filter_optimizer_quality_flags_v4.jsonl"
NO_TRADE_OPTIMIZER_SUMMARY_PATH = RESEARCH_V4_ROOT / "no_trade_filter_optimizer_v4_summary.json"
NO_TRADE_OPTIMIZER_PROOF_PATH = RESEARCH_V4_ROOT / "no_trade_filter_optimizer_v4_proof.jsonl"

FAMILY_SPLIT_PATH = RESEARCH_V4_ROOT / "family_template_splits_v4.jsonl"
VOLUME_RESCUE_PATH = RESEARCH_V4_ROOT / "volume_family_rescue_records_v4.jsonl"
FAMILY_SPLIT_QUALITY_FLAGS_PATH = RESEARCH_V4_ROOT / "family_template_splitter_quality_flags_v4.jsonl"
FAMILY_SPLIT_SUMMARY_PATH = RESEARCH_V4_ROOT / "family_template_splitter_v4_summary.json"
FAMILY_SPLIT_PROOF_PATH = RESEARCH_V4_ROOT / "family_template_splitter_v4_proof.jsonl"

CANDIDATES_V4_PATH = RESEARCH_V4_ROOT / "research_signal_candidates_v4.jsonl"
DENSITY_SCHEDULE_V4_PATH = RESEARCH_V4_ROOT / "research_candidate_density_schedule_v4.jsonl"
CANDIDATE_RANKINGS_V4_PATH = RESEARCH_V4_ROOT / "research_candidate_quality_rankings_v4.jsonl"
CANDIDATE_GENERATOR_SUMMARY_PATH = RESEARCH_V4_ROOT / "research_candidate_generator_v4_summary.json"
CANDIDATE_GENERATOR_PROOF_PATH = RESEARCH_V4_ROOT / "research_candidate_generator_v4_proof.jsonl"

PROFIT_HOLDOUT_SPLIT_SCORES_PATH = RESEARCH_V4_ROOT / "profit_holdout_split_scores_v4.jsonl"
PRIORITY_V4_PATH = RESEARCH_V4_ROOT / "candidate_pre_simulation_priority_v4.jsonl"
SCORER_SUMMARY_PATH = RESEARCH_V4_ROOT / "profit_holdout_split_scorer_v4_summary.json"
SCORER_PROOF_PATH = RESEARCH_V4_ROOT / "profit_holdout_split_scorer_v4_proof.jsonl"

TRADES_V4_PATH = RESEARCH_V4_ROOT / "research_path_trades_v4.jsonl"
EXIT_EVENTS_V4_PATH = RESEARCH_V4_ROOT / "research_path_exit_events_v4.jsonl"
SIMULATOR_QUALITY_FLAGS_PATH = RESEARCH_V4_ROOT / "research_path_simulator_quality_flags_v4.jsonl"
SIMULATOR_SUMMARY_PATH = RESEARCH_V4_ROOT / "research_path_simulator_v4_summary.json"
SIMULATOR_PROOF_PATH = RESEARCH_V4_ROOT / "research_path_simulator_v4_proof.jsonl"

TOURNAMENT_SCORES_V4_PATH = RESEARCH_V4_ROOT / "research_tournament_scores_v4.jsonl"
TOURNAMENT_LEADERBOARD_V4_PATH = RESEARCH_V4_ROOT / "research_tournament_leaderboard_v4.jsonl"
TOURNAMENT_HOLDOUT_V4_PATH = RESEARCH_V4_ROOT / "research_tournament_holdout_scores_v4.jsonl"
TOURNAMENT_REGIME_V4_PATH = RESEARCH_V4_ROOT / "research_tournament_regime_scores_v4.jsonl"
TOURNAMENT_COMPARISON_V4_PATH = RESEARCH_V4_ROOT / "research_v3_v4_comparison_v4.jsonl"
TOURNAMENT_SUMMARY_PATH = RESEARCH_V4_ROOT / "research_tournament_v4_summary.json"
TOURNAMENT_PROOF_PATH = RESEARCH_V4_ROOT / "research_tournament_v4_proof.jsonl"

BREAKTHROUGH_V4_PATH = RESEARCH_V4_ROOT / "research_breakthrough_candidates_v4.jsonl"
WATCHLIST_V4_PATH = RESEARCH_V4_ROOT / "research_watchlist_candidates_v4.jsonl"
REJECTIONS_V4_PATH = RESEARCH_V4_ROOT / "research_breakthrough_rejections_v4.jsonl"
GATE_V4_SUMMARY_PATH = RESEARCH_V4_ROOT / "research_breakthrough_gate_v4_summary.json"
GATE_V4_PROOF_PATH = RESEARCH_V4_ROOT / "research_breakthrough_gate_v4_proof.jsonl"

MUTATION_QUEUE_V4_PATH = RESEARCH_V4_ROOT / "research_mutation_queue_v4.jsonl"
MUTATION_QUEUE_V4_SUMMARY_PATH = RESEARCH_V4_ROOT / "research_mutation_queue_v4_summary.json"
MUTATION_QUEUE_V4_PROOF_PATH = RESEARCH_V4_ROOT / "research_mutation_queue_v4_proof.jsonl"

ARTIFACT_GUARD_V2_SUMMARY_PATH = ARTIFACT_ROOT / "active_policy" / "zero_dte_replay_outcomes_artifact_guard_v2_summary.json"
ARTIFACT_GUARD_V2_RECORDS_PATH = ARTIFACT_ROOT / "active_policy" / "zero_dte_replay_outcomes_artifact_guard_v2_records.jsonl"
ARTIFACT_GUARD_V2_PROOF_PATH = ARTIFACT_ROOT / "active_policy" / "zero_dte_replay_outcomes_artifact_guard_v2_proof.jsonl"

# Subfamily taxonomy
V4_CONTINUATION_SUBFAMILIES = (
    "continuation|pullback|high_volume",
    "continuation|pullback|relative_strength",
    "continuation|trend_pause|volume_confirmed",
    "continuation|post_compression_followthrough",
)
V4_VOLUME_SUBFAMILIES = (
    "volume|dry_up_breakout",
    "volume|dry_up_reclaim",
    "volume|climax_reversal_filter",
    "volume|range_compression_expansion",
)
V4_ALL_SUBFAMILIES = V4_CONTINUATION_SUBFAMILIES + V4_VOLUME_SUBFAMILIES

# Thresholds (mirrored from V3)
MIN_BREAKTHROUGH_PF = 1.10
MIN_BREAKTHROUGH_SAMPLE = 30
MIN_BREAKTHROUGH_SYMBOLS = 8
MIN_BREAKTHROUGH_SECTORS = 8
MIN_BREAKTHROUGH_SPLIT_PASS = 0.55
CORE_MIN_PROFIT_FACTOR = 1.10
CORE_MIN_EXPECTANCY = 0.0
CORE_MAX_DRAWDOWN_ABS = 2500.0

WATCHDOG_CANDIDATE_CAP = 60_000
MINIMUM_CANDIDATE_CAP = 25_000
WATCHDOG_SIM_CAP = 35_000
MINIMUM_SIM_CAP = 20_000
V4_TARGET_CANDIDATES = 50_000
V4_MIN_CANDIDATES = 25_000
V4_TARGET_TRADES = 30_000
V4_MIN_TRADES = 20_000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def research_v4_proof_record(proof_id: str, status: str, payload: dict[str, object]) -> dict[str, object]:
    record = {
        "artifact_type": "public_signal_research_v4_proof",
        "proof_id": proof_id,
        "status": status,
        "timestamp": utc_now_iso(),
        "bundle_version": RESEARCH_V4_VERSION,
        "payload": dict(payload),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(record, "proof_hash")


def write_stage_proof(path: Path, proof_id: str, status: str, summary: dict[str, object]) -> None:
    write_jsonl_file(path, [research_v4_proof_record(proof_id, status, summary)])


def load_v3_summary() -> dict[str, object]:
    return read_json_file(V3_SUMMARY_PATH)


def load_v3_gate_summary() -> dict[str, object]:
    return read_json_file(V3_GATE_SUMMARY_PATH)


def load_v3_tournament_summary() -> dict[str, object]:
    return read_json_file(V3_TOURNAMENT_SUMMARY_PATH)


def load_v3_candidate_summary() -> dict[str, object]:
    return read_json_file(V3_CANDIDATE_SUMMARY_PATH)


def load_v3_path_simulator_summary() -> dict[str, object]:
    return read_json_file(V3_PATH_SIMULATOR_SUMMARY_PATH)


def load_v3_mutation_queue_summary() -> dict[str, object]:
    return read_json_file(V3_MUTATION_QUEUE_SUMMARY_PATH)


def load_v3_mutation_exec_summary() -> dict[str, object]:
    return read_json_file(V3_MUTATION_EXEC_SUMMARY_PATH)


def normalize_stable_family_id(family_id: str) -> str:
    label = family_id.strip()
    if label in {STABLE_FAMILY_CONTINUATION, STABLE_FAMILY_VOLUME}:
        return label
    if label in {"continuation", "volume"}:
        return stable_family_id_from_label(label)
    if label.startswith("continuation|"):
        return STABLE_FAMILY_CONTINUATION
    if label.startswith("volume|"):
        return STABLE_FAMILY_VOLUME
    if label.startswith("continuation|") or label.startswith("volume|"):
        return label
    return label


def top_level_family(subfamily_id: str) -> str:
    return subfamily_id.split("|", 1)[0] if "|" in subfamily_id else subfamily_id


def is_continuation_subfamily(subfamily_id: str) -> bool:
    return subfamily_id in V4_CONTINUATION_SUBFAMILIES


def is_volume_subfamily(subfamily_id: str) -> bool:
    return subfamily_id in V4_VOLUME_SUBFAMILIES
