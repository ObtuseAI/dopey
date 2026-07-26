"""Shared helpers for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.signal_research_common import is_quarantined_signature, quarantine_overlap  # noqa: F401

__all__ = [
    "is_quarantined_signature",
    "quarantine_overlap",
]
from dopey_autonomy.signal_research_v2_common import (
    ARTIFACT_GUARD_PATH,
    BREAKTHROUGH_V2_PATH,
    CANDIDATES_V2_PATH,
    LEADERBOARD_V2_PATH,
    MUTATION_QUEUE_V2_PATH,
    RESEARCH_V2_ROOT,
    TRADES_V2_PATH,
    WATCHLIST_V2_PATH,
    load_v1_gate_summary,
    load_v1_summary,
    stable_family_id_from_label,
)
from dopey_autonomy.public_champion_common import ARTIFACT_ROOT, read_json_file, record_with_hash, write_summary_with_hash


RESEARCH_V3_VERSION = "dopey-public-signal-research-breakthrough-v3"
RESEARCH_V3_ROOT = ARTIFACT_ROOT / "signal_research_v3"

STABLE_FAMILY_CONTINUATION = "continuation|pullback|high_volume|trend_follow|dte14|1pct_otm"
STABLE_FAMILY_VOLUME = "volume|dry_up_breakout|trend_follow|dte14|1pct_otm"
STABLE_FAMILY_IDS = (STABLE_FAMILY_CONTINUATION, STABLE_FAMILY_VOLUME)

V2_SUMMARY_PATH = RESEARCH_V2_ROOT / "public_signal_research_breakthrough_v2_summary.json"
V2_GATE_SUMMARY_PATH = RESEARCH_V2_ROOT / "research_breakthrough_gate_v2_summary.json"
V2_TOURNAMENT_SUMMARY_PATH = RESEARCH_V2_ROOT / "research_tournament_v2_summary.json"
V2_CANDIDATE_SUMMARY_PATH = RESEARCH_V2_ROOT / "research_candidate_generator_v2_summary.json"
V2_MUTATION_QUEUE_SUMMARY_PATH = RESEARCH_V2_ROOT / "research_mutation_queue_v2_summary.json"

MUTATION_EXECUTION_RECORDS_PATH = RESEARCH_V3_ROOT / "research_mutation_execution_records_v3.jsonl"
STABLE_TEMPLATES_PATH = RESEARCH_V3_ROOT / "stable_family_templates_v3.jsonl"
CANDIDATES_V3_PATH = RESEARCH_V3_ROOT / "research_signal_candidates_v3.jsonl"
PRIORITY_V3_PATH = RESEARCH_V3_ROOT / "candidate_pre_simulation_priority_v3.jsonl"
TRADES_V3_PATH = RESEARCH_V3_ROOT / "research_path_trades_v3.jsonl"
LEADERBOARD_V3_PATH = RESEARCH_V3_ROOT / "research_tournament_leaderboard_v3.jsonl"
BREAKTHROUGH_V3_PATH = RESEARCH_V3_ROOT / "research_breakthrough_candidates_v3.jsonl"
WATCHLIST_V3_PATH = RESEARCH_V3_ROOT / "research_watchlist_candidates_v3.jsonl"
MUTATION_QUEUE_V3_PATH = RESEARCH_V3_ROOT / "research_mutation_queue_v3.jsonl"

MIN_V3_SYMBOLS = 8
MIN_V3_SECTORS = 8
MIN_BREAKTHROUGH_SAMPLE = 30
MIN_BREAKTHROUGH_SYMBOLS = 8
MIN_BREAKTHROUGH_SECTORS = 8
MIN_BREAKTHROUGH_PF = 1.10
MIN_BREAKTHROUGH_SPLIT_PASS = 0.55

WATCHDOG_CANDIDATE_CAP = 60_000
MINIMUM_CANDIDATE_CAP = 25_000
WATCHDOG_SIM_CAP = 35_000
MINIMUM_SIM_CAP = 20_000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def research_v3_proof_record(proof_id: str, status: str, payload: dict[str, object]) -> dict[str, object]:
    record = {
        "artifact_type": "public_signal_research_v3_proof",
        "proof_id": proof_id,
        "status": status,
        "timestamp": utc_now_iso(),
        "bundle_version": RESEARCH_V3_VERSION,
        "payload": dict(payload),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(record, "proof_hash")


def write_stage_proof(path: Path, proof_id: str, status: str, summary: dict[str, object]) -> None:
    from dopey_autonomy.public_champion_common import write_jsonl_file

    write_jsonl_file(path, [research_v3_proof_record(proof_id, status, summary)])


def load_v2_summary() -> dict[str, object]:
    return read_json_file(V2_SUMMARY_PATH)


def load_v2_gate_summary() -> dict[str, object]:
    return read_json_file(V2_GATE_SUMMARY_PATH)


def load_v2_tournament_summary() -> dict[str, object]:
    return read_json_file(V2_TOURNAMENT_SUMMARY_PATH)


def normalize_stable_family_id(family_id: str) -> str:
    label = family_id.strip()
    if label in STABLE_FAMILY_IDS:
        return label
    if label in {"continuation", "volume"}:
        return stable_family_id_from_label(label)
    if label.startswith("continuation|"):
        return STABLE_FAMILY_CONTINUATION
    if label.startswith("volume|"):
        return STABLE_FAMILY_VOLUME
    return label
