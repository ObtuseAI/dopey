"""Shared helpers for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V2."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.signal_research_common import (
    QUARANTINE_SIGNATURES,
    RESEARCH_ROOT as V1_RESEARCH_ROOT,
    is_quarantined_signature,
    quarantine_overlap,
)
from dopey_autonomy.public_champion_common import ARTIFACT_ROOT, read_json_file, record_with_hash, write_summary_with_hash


RESEARCH_V2_VERSION = "dopey-public-signal-research-breakthrough-v2"
RESEARCH_V2_ROOT = ARTIFACT_ROOT / "signal_research_v2"

V1_SUMMARY_PATH = V1_RESEARCH_ROOT / "public_signal_research_breakthrough_v1_summary.json"
V1_GATE_SUMMARY_PATH = V1_RESEARCH_ROOT / "research_breakthrough_gate_v1_summary.json"
V1_LEADERBOARD_PATH = V1_RESEARCH_ROOT / "research_tournament_leaderboard_v1.jsonl"
V1_QUARANTINE_PATH = V1_RESEARCH_ROOT / "failed_champion_family_quarantine_v1.jsonl"
ARTIFACT_GUARD_PATH = ARTIFACT_ROOT / "champion_repair" / "public_champion_artifact_guard_v1_summary.json"

WATCHLIST_PATH = RESEARCH_V2_ROOT / "watchlist_candidates_v2.jsonl"
DENSITY_SCHEDULE_PATH = RESEARCH_V2_ROOT / "symbol_sector_density_schedule_v2.jsonl"
MUTATION_PLAN_PATH = RESEARCH_V2_ROOT / "watchlist_mutation_plan_v2.jsonl"
CANDIDATES_V2_PATH = RESEARCH_V2_ROOT / "research_signal_candidates_v2.jsonl"
TRADES_V2_PATH = RESEARCH_V2_ROOT / "research_path_trades_v2.jsonl"
LEADERBOARD_V2_PATH = RESEARCH_V2_ROOT / "research_tournament_leaderboard_v2.jsonl"
BREAKTHROUGH_V2_PATH = RESEARCH_V2_ROOT / "research_breakthrough_candidates_v2.jsonl"
WATCHLIST_V2_PATH = RESEARCH_V2_ROOT / "research_watchlist_candidates_v2.jsonl"
MUTATION_QUEUE_V2_PATH = RESEARCH_V2_ROOT / "research_mutation_queue_v2.jsonl"

GENERIC_LABELS = frozenset({"continuation", "volume", "reversal", "regime", "volatility", "hybrid", "relative_strength"})

MIN_V2_SYMBOLS = 8
MIN_V2_SECTORS = 8
MIN_BREAKTHROUGH_SAMPLE = 30
MIN_BREAKTHROUGH_SYMBOLS = 8
MIN_BREAKTHROUGH_SECTORS = 8
MIN_BREAKTHROUGH_PF = 1.10
MIN_BREAKTHROUGH_SPLIT_PASS = 0.55

LABEL_TO_STABLE_ID = {
    "continuation": "continuation|pullback|high_volume|trend_follow|dte14|1pct_otm",
    "volume": "volume|dry_up_breakout|trend_follow|dte14|1pct_otm",
    "reversal": "reversal|overextension|mean_revert|invalidation_strict|dte14|2pct_otm",
    "regime": "regime|risk_on|continuation|trend_follow|dte30|1pct_otm",
    "volatility": "volatility|compression_break|call|volatility_expansion_hunter|dte21|ATM",
    "hybrid": "hybrid|continuation_reversal_filter|trend_follow|dte21|1pct_otm",
    "relative_strength": "relative_strength|sector_lead|trend_follow|dte21|1pct_otm",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def research_v2_proof_record(proof_id: str, status: str, payload: dict[str, object]) -> dict[str, object]:
    record = {
        "artifact_type": "public_signal_research_v2_proof",
        "proof_id": proof_id,
        "status": status,
        "timestamp": utc_now_iso(),
        "bundle_version": RESEARCH_V2_VERSION,
        "payload": dict(payload),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(record, "proof_hash")


def write_stage_proof(path: Path, proof_id: str, status: str, summary: dict[str, object]) -> None:
    from dopey_autonomy.public_champion_common import write_jsonl_file

    write_jsonl_file(path, [research_v2_proof_record(proof_id, status, summary)])


def load_v1_summary() -> dict[str, object]:
    return read_json_file(V1_SUMMARY_PATH)


def load_v1_gate_summary() -> dict[str, object]:
    return read_json_file(V1_GATE_SUMMARY_PATH)


def is_generic_label(label: str) -> bool:
    return label.lower() in GENERIC_LABELS


def stable_family_id_from_label(label: str) -> str:
    return LABEL_TO_STABLE_ID.get(label.lower(), f"discovery|{label}|v2_repair")
