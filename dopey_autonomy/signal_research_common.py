"""Shared helpers for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.champion_repair_common import REPAIR_ROOT
from dopey_autonomy.public_champion_common import (
    ARTIFACT_ROOT,
    LIVE_GATE_ROOT,
    SCOREBOARD_ROOT,
    read_json_file,
    record_with_hash,
    write_summary_with_hash,
)


RESEARCH_VERSION = "dopey-public-signal-research-breakthrough-v1"
RESEARCH_ROOT = ARTIFACT_ROOT / "signal_research"

REPAIR_SUMMARY_PATH = REPAIR_ROOT / "public_champion_repair_and_retune_v1_summary.json"
ARTIFACT_GUARD_PATH = REPAIR_ROOT / "public_champion_artifact_guard_v1_summary.json"

CANDIDATES_PATH = RESEARCH_ROOT / "research_signal_candidates_v1.jsonl"
TRADES_PATH = RESEARCH_ROOT / "research_path_trades_v1.jsonl"
LEADERBOARD_PATH = RESEARCH_ROOT / "research_tournament_leaderboard_v1.jsonl"
BREAKTHROUGH_PATH = RESEARCH_ROOT / "research_breakthrough_candidates_v1.jsonl"
FAMILY_REGISTRY_PATH = RESEARCH_ROOT / "discovery_signal_family_registry_v1.jsonl"
FEATURE_REGISTRY_PATH = RESEARCH_ROOT / "public_feature_registry_v1.jsonl"
QUARANTINE_PATH = RESEARCH_ROOT / "failed_champion_family_quarantine_v1.jsonl"

QUARANTINE_SIGNATURES = (
    "volatility_squeeze_breakout",
    "volatility_squeeze",
    "bollinger_expansion|trend_follow|dte14|1pct_otm",
    "bollinger_expansion|theta_protective|near_dte|otm",
    "bollinger_expansion|vol_hunter|short_dte|otm",
    "bollinger_expansion|volatility_expansion_hunter|dte10|ATM",
    "champ-5264fd3b2fed",
)

MIN_BREAKTHROUGH_SAMPLE = 30
MIN_BREAKTHROUGH_SYMBOLS = 5
MIN_BREAKTHROUGH_PF = 1.10
MIN_BREAKTHROUGH_SPLIT_PASS = 0.55


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def research_proof_record(proof_id: str, status: str, payload: dict[str, object]) -> dict[str, object]:
    record = {
        "artifact_type": "public_signal_research_proof",
        "proof_id": proof_id,
        "status": status,
        "timestamp": utc_now_iso(),
        "bundle_version": RESEARCH_VERSION,
        "payload": dict(payload),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(record, "proof_hash")


def write_stage_proof(path: Path, proof_id: str, status: str, summary: dict[str, object]) -> None:
    from dopey_autonomy.public_champion_common import write_jsonl_file

    write_jsonl_file(path, [research_proof_record(proof_id, status, summary)])


def load_repair_summary() -> dict[str, object]:
    return read_json_file(REPAIR_SUMMARY_PATH)


def quarantine_overlap(family_id: str) -> bool:
    normalized = family_id.lower()
    return any(signature.lower() in normalized for signature in QUARANTINE_SIGNATURES)


def is_quarantined_signature(text: str) -> bool:
    return quarantine_overlap(text)
