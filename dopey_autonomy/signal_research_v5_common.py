"""Shared helpers for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5.

V5 is a baseline-freezing, audit-completing, PF/holdout/split finishing loop
that continues from V4's `pf_holdout_split_improved_requires_v5` branch.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import (
    ARTIFACT_ROOT,
    LIVE_GATE_ROOT,
    SCOREBOARD_ROOT,
    read_json_file,
    read_jsonl_file,
    record_with_hash,
    write_jsonl_file,
)
from dopey_autonomy.signal_research_common import is_quarantined_signature, quarantine_overlap  # noqa: F401
from dopey_autonomy.signal_research_v2_common import stable_family_id_from_label  # noqa: F401
from dopey_autonomy.signal_research_v3_common import (  # noqa: F401
    STABLE_FAMILY_CONTINUATION,
    STABLE_FAMILY_VOLUME,
)
from dopey_autonomy.signal_research_v4_common import (
    GATE_V4_SUMMARY_PATH,
    MUTATION_QUEUE_V4_PATH,
    MUTATION_QUEUE_V4_SUMMARY_PATH,
    MUTATION_EXEC_RECORDS_PATH as MUTATION_EXEC_RECORDS_V4_PATH,
    MUTATION_EXEC_SUMMARY_PATH as MUTATION_EXEC_SUMMARY_V4_PATH,
    NO_TRADE_OPTIMIZER_SUMMARY_PATH as NO_TRADE_OPTIMIZER_SUMMARY_V4_PATH,
    NO_TRADE_RULES_PATH as NO_TRADE_RULES_V4_PATH,
    PREFLIGHT_SUMMARY_PATH as PREFLIGHT_SUMMARY_V4_PATH,
    PROFITABLE_SLICE_SUMMARY_PATH as PROFITABLE_SLICE_SUMMARY_V4_PATH,
    REJECTIONS_V4_PATH,
    RESEARCH_V4_ROOT,
    SIMULATOR_SUMMARY_PATH as SIMULATOR_SUMMARY_V4_PATH,
    TOURNAMENT_SUMMARY_PATH as TOURNAMENT_SUMMARY_V4_PATH,
    WATCHLIST_V4_PATH,
)
from dopey_wealth_engine.common import REPO_ROOT
from dopey_core.repo_paths import REPORTS_DIR


__all__ = [
    "is_quarantined_signature",
    "quarantine_overlap",
    "stable_family_id_from_label",
    "load_v4_summary",
    "load_v4_preflight_summary",
    "load_v4_tournament_summary",
    "load_v4_gate_summary",
    "load_v4_mutation_queue_summary",
    "load_v4_mutation_exec_summary",
    "load_v4_no_trade_summary",
    "load_v4_profitable_slice_summary",
    "load_v4_simulator_summary",
    "load_v4_candidate_summary",
    "load_v4_scoreboard_summary",
    "load_v4_live_gate_status",
    "load_v4_validation_summary",
    "load_v4_timeout_records",
    "normalize_stable_family_id_v5",
    "top_level_family",
]


RESEARCH_V5_VERSION = "dopey-public-signal-research-breakthrough-v5"
RESEARCH_V5_ROOT = ARTIFACT_ROOT / "signal_research_v5"
BASELINE_V4_ROOT = RESEARCH_V5_ROOT / "baseline_snapshots" / "v4"

# V5 artifact paths
PREFLIGHT_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "public_signal_research_v5_preflight_summary.json"
PREFLIGHT_V5_FLAGS_PATH = RESEARCH_V5_ROOT / "public_signal_research_v5_preflight_flags.jsonl"
PREFLIGHT_V5_PROOF_PATH = RESEARCH_V5_ROOT / "public_signal_research_v5_preflight_proof.jsonl"

BASELINE_FREEZE_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "public_signal_research_v5_baseline_freeze_summary.json"
BASELINE_SNAPSHOT_V5_MANIFEST_PATH = RESEARCH_V5_ROOT / "public_signal_research_v5_baseline_snapshot_manifest.jsonl"
BASELINE_FREEZE_V5_PROOF_PATH = RESEARCH_V5_ROOT / "public_signal_research_v5_baseline_freeze_proof.jsonl"

SAFE_APPEND_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "safe_append_docs_v5_summary.json"
SAFE_APPEND_V5_BACKUPS_PATH = RESEARCH_V5_ROOT / "safe_append_docs_v5_backups.jsonl"
SAFE_APPEND_V5_RECORDS_PATH = RESEARCH_V5_ROOT / "safe_append_docs_v5_records.jsonl"
SAFE_APPEND_V5_PROOF_PATH = RESEARCH_V5_ROOT / "safe_append_docs_v5_proof.jsonl"

EXPENSIVE_LANE_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "public_signal_research_expensive_lane_summary_v5.json"
EXPENSIVE_LANE_V5_RECORDS_PATH = RESEARCH_V5_ROOT / "public_signal_research_expensive_lane_records_v5.jsonl"
EXPENSIVE_LANE_V5_TIMEOUT_PATH = RESEARCH_V5_ROOT / "public_signal_research_expensive_lane_timeout_records_v5.jsonl"
EXPENSIVE_LANE_V5_PROOF_PATH = RESEARCH_V5_ROOT / "public_signal_research_expensive_lane_proof_v5.jsonl"

V4_ANALYSIS_V5_PATH = RESEARCH_V5_ROOT / "v4_result_analysis_v5.json"
V4_REPAIR_TARGETS_V5_PATH = RESEARCH_V5_ROOT / "v4_repair_targets_v5.jsonl"
V4_NEAR_BREAKTHROUGH_V5_PATH = RESEARCH_V5_ROOT / "v4_near_breakthrough_records_v5.jsonl"
V4_LOSS_DRIVER_V5_PATH = RESEARCH_V5_ROOT / "v4_loss_driver_records_v5.jsonl"
V4_ANALYZER_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "v4_result_analyzer_v5_summary.json"
V4_ANALYZER_V5_PROOF_PATH = RESEARCH_V5_ROOT / "v4_result_analyzer_v5_proof.jsonl"

MUTATION_EXEC_V5_RECORDS_PATH = RESEARCH_V5_ROOT / "research_mutation_execution_records_v5.jsonl"
MUTATION_EXEC_V5_EXPANSION_PATH = RESEARCH_V5_ROOT / "research_mutation_expansion_records_v5.jsonl"
MUTATION_EXEC_V5_FAILURES_PATH = RESEARCH_V5_ROOT / "research_mutation_execution_failures_v5.jsonl"
MUTATION_EXEC_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "research_mutation_queue_executor_v5_summary.json"
MUTATION_EXEC_V5_PROOF_PATH = RESEARCH_V5_ROOT / "research_mutation_queue_executor_v5_proof.jsonl"

NO_TRADE_RULES_V5_PATH = RESEARCH_V5_ROOT / "no_trade_filter_rules_v5.jsonl"
SELECTIVITY_POLICY_V5_PATH = RESEARCH_V5_ROOT / "selectivity_policy_v5.json"
FUTURE_LEAKAGE_GUARD_V5_PATH = RESEARCH_V5_ROOT / "future_leakage_guard_records_v5.jsonl"
NO_TRADE_QUALITY_V5_PATH = RESEARCH_V5_ROOT / "no_trade_filter_optimizer_quality_flags_v5.jsonl"
NO_TRADE_OPTIMIZER_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "no_trade_filter_optimizer_v5_summary.json"
NO_TRADE_OPTIMIZER_V5_PROOF_PATH = RESEARCH_V5_ROOT / "no_trade_filter_optimizer_v5_proof.jsonl"

CANDIDATES_V5_PATH = RESEARCH_V5_ROOT / "research_signal_candidates_v5.jsonl"
DENSITY_SCHEDULE_V5_PATH = RESEARCH_V5_ROOT / "research_candidate_density_schedule_v5.jsonl"
CANDIDATE_RANKINGS_V5_PATH = RESEARCH_V5_ROOT / "research_candidate_quality_rankings_v5.jsonl"
CANDIDATE_GENERATOR_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "research_candidate_generator_v5_summary.json"
CANDIDATE_GENERATOR_V5_PROOF_PATH = RESEARCH_V5_ROOT / "research_candidate_generator_v5_proof.jsonl"

PROFIT_HOLDOUT_SPLIT_SCORES_V5_PATH = RESEARCH_V5_ROOT / "profit_holdout_split_scores_v5.jsonl"
PRIORITY_V5_PATH = RESEARCH_V5_ROOT / "candidate_pre_simulation_priority_v5.jsonl"
SCORER_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "profit_holdout_split_scorer_v5_summary.json"
SCORER_V5_PROOF_PATH = RESEARCH_V5_ROOT / "profit_holdout_split_scorer_v5_proof.jsonl"

TRADES_V5_PATH = RESEARCH_V5_ROOT / "research_path_trades_v5.jsonl"
EXIT_EVENTS_V5_PATH = RESEARCH_V5_ROOT / "research_path_exit_events_v5.jsonl"
SIMULATOR_QUALITY_V5_PATH = RESEARCH_V5_ROOT / "research_path_simulator_quality_flags_v5.jsonl"
SIMULATOR_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "research_path_simulator_v5_summary.json"
SIMULATOR_V5_PROOF_PATH = RESEARCH_V5_ROOT / "research_path_simulator_v5_proof.jsonl"

TOURNAMENT_SCORES_V5_PATH = RESEARCH_V5_ROOT / "research_tournament_scores_v5.jsonl"
TOURNAMENT_LEADERBOARD_V5_PATH = RESEARCH_V5_ROOT / "research_tournament_leaderboard_v5.jsonl"
TOURNAMENT_HOLDOUT_V5_PATH = RESEARCH_V5_ROOT / "research_tournament_holdout_scores_v5.jsonl"
TOURNAMENT_REGIME_V5_PATH = RESEARCH_V5_ROOT / "research_tournament_regime_scores_v5.jsonl"
TOURNAMENT_COMPARISON_V5_PATH = RESEARCH_V5_ROOT / "research_v4_v5_comparison_v5.jsonl"
TOURNAMENT_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "research_tournament_v5_summary.json"
TOURNAMENT_V5_PROOF_PATH = RESEARCH_V5_ROOT / "research_tournament_v5_proof.jsonl"

BREAKTHROUGH_V5_PATH = RESEARCH_V5_ROOT / "research_breakthrough_candidates_v5.jsonl"
WATCHLIST_V5_PATH = RESEARCH_V5_ROOT / "research_watchlist_candidates_v5.jsonl"
REJECTIONS_V5_PATH = RESEARCH_V5_ROOT / "research_breakthrough_rejections_v5.jsonl"
GATE_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "research_breakthrough_gate_v5_summary.json"
GATE_V5_PROOF_PATH = RESEARCH_V5_ROOT / "research_breakthrough_gate_v5_proof.jsonl"

MUTATION_QUEUE_V5_PATH = RESEARCH_V5_ROOT / "research_mutation_queue_v5.jsonl"
MUTATION_QUEUE_V5_SUMMARY_PATH = RESEARCH_V5_ROOT / "research_mutation_queue_v5_summary.json"
MUTATION_QUEUE_V5_PROOF_PATH = RESEARCH_V5_ROOT / "research_mutation_queue_v5_proof.jsonl"

# V4 summary path (V5 baseline snapshot source)
V4_SUMMARY_PATH = RESEARCH_V4_ROOT / "public_signal_research_breakthrough_v4_summary.json"
V4_VALIDATION_SUMMARY_PATH = RESEARCH_V4_ROOT / "public_signal_research_breakthrough_v4_validation_summary.json"
V4_TIMEOUT_RECORDS_PATH = RESEARCH_V4_ROOT / "public_signal_research_breakthrough_v4_timeout_records.jsonl"
V4_PREFLIGHT_PROOF_PATH = RESEARCH_V4_ROOT / "public_signal_research_v4_preflight_proof.jsonl"

# Thresholds
MIN_BREAKTHROUGH_PF = 1.10  # hard rule: never lowered
MIN_BREAKTHROUGH_SAMPLE = 30
MIN_BREAKTHROUGH_SYMBOLS = 8
MIN_BREAKTHROUGH_SECTORS = 8
MIN_BREAKTHROUGH_SPLIT_PASS = 0.55

# V5 caps (watchdog-safe)
V5_TARGET_CANDIDATES = 40_000
V5_MIN_CANDIDATES = 20_000
WATCHDOG_CANDIDATE_CAP_V5 = 50_000
V5_TARGET_TRADES = 25_000
V5_MIN_TRADES = 15_000
WATCHDOG_SIM_CAP_V5 = 30_000

# V5 family share cap (any single family may not exceed this share of candidates)
V5_MAX_FAMILY_SHARE = 0.70

# V5 risk caps
V5_LOSS_DRIVER_ENTRY_SPOT = 1_000_000.0  # any entry_spot > 1e6 is treated as data corruption
V5_MAX_SINGLE_SYMBOL_PNL_SHARE = 0.30  # any single symbol may not contribute more than 30% of net P&L
V5_QUARANTINED_SUBFAMILIES: tuple[str, ...] = ()  # explicit empty by default; only set on real failure
V5_HOLD_WINDOWS: tuple[int, ...] = (1, 2, 3, 5, 7)

# V5 subfamilies (same 8 as V4; reinforced with V5 mutations)
V5_CONTINUATION_SUBFAMILIES = (
    "continuation|pullback|high_volume",
    "continuation|pullback|relative_strength",
    "continuation|trend_pause|volume_confirmed",
    "continuation|post_compression_followthrough",
)
V5_VOLUME_SUBFAMILIES = (
    "volume|dry_up_breakout",
    "volume|dry_up_reclaim",
    "volume|climax_reversal_filter",
    "volume|range_compression_expansion",
)
V5_ALL_SUBFAMILIES = V5_CONTINUATION_SUBFAMILIES + V5_VOLUME_SUBFAMILIES

# Forbidden tokens in symbols for final-decision rows
FORBIDDEN_TOKENS = ("SIM", "TEST", "FIXTURE", "SYNTH")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def research_v5_proof_record(proof_id: str, status: str, payload: dict[str, object]) -> dict[str, object]:
    record = {
        "artifact_type": "public_signal_research_v5_proof",
        "proof_id": proof_id,
        "status": status,
        "timestamp": utc_now_iso(),
        "bundle_version": RESEARCH_V5_VERSION,
        "payload": dict(payload),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(record, "proof_hash")


def write_stage_proof(path: Path, proof_id: str, status: str, summary: dict[str, object]) -> None:
    write_jsonl_file(path, [research_v5_proof_record(proof_id, status, summary)])


# ------------------ V4 baseline loaders ------------------

def load_v4_summary() -> dict[str, object]:
    return read_json_file(V4_SUMMARY_PATH)


def load_v4_preflight_summary() -> dict[str, object]:
    return read_json_file(PREFLIGHT_SUMMARY_V4_PATH)


def load_v4_tournament_summary() -> dict[str, object]:
    return read_json_file(TOURNAMENT_SUMMARY_V4_PATH)


def load_v4_gate_summary() -> dict[str, object]:
    return read_json_file(GATE_V4_SUMMARY_PATH)


def load_v4_mutation_queue_summary() -> dict[str, object]:
    return read_json_file(MUTATION_QUEUE_V4_SUMMARY_PATH)


def load_v4_mutation_exec_summary() -> dict[str, object]:
    return read_json_file(MUTATION_EXEC_SUMMARY_V4_PATH)


def load_v4_no_trade_summary() -> dict[str, object]:
    return read_json_file(NO_TRADE_OPTIMIZER_SUMMARY_V4_PATH)


def load_v4_profitable_slice_summary() -> dict[str, object]:
    return read_json_file(PROFITABLE_SLICE_SUMMARY_V4_PATH)


def load_v4_simulator_summary() -> dict[str, object]:
    return read_json_file(SIMULATOR_SUMMARY_V4_PATH)


def load_v4_candidate_summary() -> dict[str, object]:
    return read_json_file(RESEARCH_V4_ROOT / "research_candidate_generator_v4_summary.json")


def load_v4_scoreboard_summary() -> dict[str, object]:
    return read_json_file(SCOREBOARD_ROOT / "public_signal_research_scoreboard_v4.json")


def load_v4_live_gate_status() -> dict[str, object]:
    return read_json_file(LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v4.json")


def load_v4_validation_summary() -> dict[str, object]:
    return read_json_file(V4_VALIDATION_SUMMARY_PATH)


def load_v4_timeout_records() -> list[dict[str, object]]:
    if V4_TIMEOUT_RECORDS_PATH.exists():
        return read_jsonl_file(V4_TIMEOUT_RECORDS_PATH)
    return []


def load_v4_mutation_queue_records() -> list[dict[str, object]]:
    if MUTATION_QUEUE_V4_PATH.exists():
        return read_jsonl_file(MUTATION_QUEUE_V4_PATH)
    return []


def load_v4_watchlist_records() -> list[dict[str, object]]:
    if WATCHLIST_V4_PATH.exists():
        return read_jsonl_file(WATCHLIST_V4_PATH)
    return []


def load_v4_rejections_records() -> list[dict[str, object]]:
    if REJECTIONS_V4_PATH.exists():
        return read_jsonl_file(REJECTIONS_V4_PATH)
    return []


def load_v4_mutation_exec_records() -> list[dict[str, object]]:
    if MUTATION_EXEC_RECORDS_V4_PATH.exists():
        return read_jsonl_file(MUTATION_EXEC_RECORDS_V4_PATH)
    return []


def load_v4_no_trade_rules() -> list[dict[str, object]]:
    if NO_TRADE_RULES_V4_PATH.exists():
        return read_jsonl_file(NO_TRADE_RULES_V4_PATH)
    return []


# ------------------ Utilities ------------------

def normalize_stable_family_id_v5(family_id: str) -> str:
    label = family_id.strip()
    if label in {STABLE_FAMILY_CONTINUATION, STABLE_FAMILY_VOLUME}:
        return label
    if label.startswith("continuation|"):
        return STABLE_FAMILY_CONTINUATION
    if label.startswith("volume|"):
        return STABLE_FAMILY_VOLUME
    return label


def top_level_family(subfamily_id: str) -> str:
    return subfamily_id.split("|", 1)[0] if "|" in subfamily_id else subfamily_id


def is_continuation_subfamily_v5(subfamily_id: str) -> bool:
    return subfamily_id in V5_CONTINUATION_SUBFAMILIES


def is_volume_subfamily_v5(subfamily_id: str) -> bool:
    return subfamily_id in V5_VOLUME_SUBFAMILIES


def is_forbidden_symbol(symbol: str) -> bool:
    upper = symbol.upper()
    return any(t in upper for t in FORBIDDEN_TOKENS)


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


def baseline_snapshot_sources() -> list[Path]:
    return [
        V4_SUMMARY_PATH,
        PREFLIGHT_SUMMARY_V4_PATH,
        V4_PREFLIGHT_PROOF_PATH,
        RESEARCH_V4_ROOT / "research_candidate_generator_v4_summary.json",
        RESEARCH_V4_ROOT / "profit_holdout_split_scorer_v4_summary.json",
        SIMULATOR_SUMMARY_V4_PATH,
        TOURNAMENT_SUMMARY_V4_PATH,
        GATE_V4_SUMMARY_PATH,
        MUTATION_QUEUE_V4_SUMMARY_PATH,
        MUTATION_EXEC_SUMMARY_V4_PATH,
        NO_TRADE_OPTIMIZER_SUMMARY_V4_PATH,
        PROFITABLE_SLICE_SUMMARY_V4_PATH,
        SCOREBOARD_ROOT / "public_signal_research_scoreboard_v4.json",
        SCOREBOARD_ROOT / "public_signal_research_dashboard_v4.html",
        SCOREBOARD_ROOT / "public_signal_research_dashboard_v4.md",
        LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v4.json",
        V4_VALIDATION_SUMMARY_PATH,
        V4_TIMEOUT_RECORDS_PATH,
        REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4_REPORT.md",
        REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4_ARTIFACT_LEDGER.md",
        REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4_COMMANDS.md",
    ]


def safe_append_bytes(path: Path, marker: bytes, payload: bytes) -> dict[str, object]:
    """Append bytes payload to path only if marker not already present. Returns record."""
    if not path.exists():
        original_bytes = b""
        backup_path = path.with_suffix(path.suffix + ".v5_backup")
    else:
        try:
            original_bytes = path.read_bytes()
        except OSError as exc:
            return {
                "append_status": "read_failed",
                "path": str(path),
                "error": str(exc),
            }
        backup_path = path.with_suffix(path.suffix + ".v5_backup")
        try:
            backup_path.write_bytes(original_bytes)
        except OSError as exc:
            return {
                "append_status": "backup_failed",
                "path": str(path),
                "error": str(exc),
            }
    if marker in original_bytes:
        return {
            "append_status": "already_present",
            "path": str(path),
            "backup_path": str(backup_path),
        }
    try:
        with path.open("ab") as fh:
            if original_bytes and not original_bytes.endswith(b"\n"):
                fh.write(b"\n")
            fh.write(payload)
    except OSError as exc:
        return {
            "append_status": "write_failed",
            "path": str(path),
            "error": str(exc),
        }
    # Verify by byte search
    try:
        verify_bytes = path.read_bytes()
    except OSError as exc:
        return {
            "append_status": "verify_failed",
            "path": str(path),
            "error": str(exc),
        }
    if marker in verify_bytes:
        return {
            "append_status": "appended",
            "path": str(path),
            "backup_path": str(backup_path),
            "marker_found": True,
            "appended_bytes": len(payload),
        }
    return {
        "append_status": "verify_missed",
        "path": str(path),
        "marker_found": False,
    }


def safe_append_with_utf8_attempt(path: Path, marker: bytes, text_payload: str) -> dict[str, object]:
    """Try to decode original to validate UTF-8; if decode fails use raw byte append."""
    if not path.exists():
        return safe_append_bytes(path, marker, text_payload.encode("utf-8", errors="replace"))
    try:
        original_bytes = path.read_bytes()
        original_bytes.decode("utf-8")  # validate
    except UnicodeDecodeError:
        # Fallback to byte append without decoding
        payload_bytes = text_payload.encode("utf-8", errors="replace")
        return safe_append_bytes(path, marker, payload_bytes)
    except OSError as exc:
        return {
            "append_status": "read_failed",
            "path": str(path),
            "error": str(exc),
        }
    return safe_append_bytes(path, marker, text_payload.encode("utf-8"))


def json_dump_safe(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, default=str)
