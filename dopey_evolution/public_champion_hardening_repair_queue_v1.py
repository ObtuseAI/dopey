"""Targeted repair queue for champions that fail hardening."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import (
    EVOLUTION_ROOT,
    HARDENING_ROOT,
    live_safety_fields,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, write_jsonl_file


GATE_REPAIR_PATH = HARDENING_ROOT / "public_champion_hardening_repair_queue_v1.jsonl"
SUMMARY_PATH = HARDENING_ROOT / "public_champion_hardening_repair_summary_v1.json"
PROOF_PATH = HARDENING_ROOT / "public_champion_hardening_repair_proof_v1.jsonl"
EVOLUTION_REPAIR_PATH = EVOLUTION_ROOT / "public_champion_hardening_repair_queue_v1.jsonl"


def run_public_champion_hardening_repair_queue_v1() -> dict[str, object]:
    repair_records = read_jsonl_file(GATE_REPAIR_PATH)
    repair_counts = Counter(str(record.get("repair_type", "")) for record in repair_records)
    champion_counts = Counter(str(record.get("champion_name", "")) for record in repair_records)
    write_jsonl_file(EVOLUTION_REPAIR_PATH, repair_records)
    summary = {
        "artifact_type": "public_champion_hardening_repair_summary_v1",
        "public_champion_hardening_repair_version": "dopey-public-champion-hardening-repair-queue-v1",
        "repair_queue_status": "repair_queue_written",
        "repair_queue_count": len(repair_records),
        "repair_type_counts": dict(repair_counts),
        "champion_repair_counts": dict(champion_counts),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_stage_proof(PROOF_PATH, "public-champion-hardening-repair-queue-v1", str(summary["repair_queue_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_hardening_repair_queue_v1": str(EVOLUTION_REPAIR_PATH),
        "public_champion_hardening_repair_summary_v1": str(SUMMARY_PATH),
        "public_champion_hardening_repair_proof_v1": str(PROOF_PATH),
    }
