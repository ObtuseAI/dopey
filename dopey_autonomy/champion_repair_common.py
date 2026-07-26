"""Shared helpers for DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import (
    CORE_MAX_DRAWDOWN_ABS,
    CORE_MIN_EXPECTANCY,
    CORE_MIN_PROFIT_FACTOR,
    HARDENING_ROOT,
    live_safety_fields,
    robinhood_policy_fields,
)
from dopey_autonomy.public_champion_common import (
    ARTIFACT_ROOT,
    CHAMPION_ROOT,
    LIVE_GATE_ROOT,
    OPTIONS_ENGINE_ROOT,
    SCOREBOARD_ROOT,
    SIGNAL_ROOT,
    TOURNAMENT_ROOT,
    read_json_file,
    read_jsonl_file,
    record_with_hash,
    write_summary_with_hash,
)


REPAIR_VERSION = "dopey-public-champion-repair-and-retune-v1"
REPAIR_ROOT = ARTIFACT_ROOT / "champion_repair"
SCRATCH_ROOT = REPAIR_ROOT / "scratch"

HARDENING_GATE_SUMMARY_PATH = HARDENING_ROOT / "public_champion_hardening_gate_v1_summary.json"
HARDENING_REPAIR_QUEUE_PATH = HARDENING_ROOT / "public_champion_hardening_repair_queue_v1.jsonl"
HARDENING_VALIDATION_PATH = HARDENING_ROOT / "public_paper_champion_hardening_and_deep_stress_v1_validation_summary.json"

CONDITIONAL_CHAMPION_IDS = (
    "bollinger_expansion|trend_follow|dte14|1pct_otm",
    "bollinger_expansion|theta_protective|near_dte|otm",
)
DEMOTED_CHAMPION_IDS = (
    "volatility_squeeze_breakout|fast_scalp|dte7|ATM",
    "volatility_squeeze_breakout|scalp|short_dte|atm",
    "volatility_squeeze_breakout|bullish|scalp",
    "volatility_squeeze_breakout",
    "champ-5264fd3b2fed",
    "bollinger_expansion|vol_hunter|short_dte|otm",
    "bollinger_expansion|volatility_expansion_hunter|dte10|ATM",
)

RETUNE_CANDIDATES_PATH = SIGNAL_ROOT / "conditional_champion_retune_candidates_v1.jsonl"
RETUNE_TRADES_PATH = OPTIONS_ENGINE_ROOT / "conditional_champion_retune_trades_v1.jsonl"
RETUNE_LEADERBOARD_PATH = TOURNAMENT_ROOT / "conditional_champion_retune_leaderboard_v1.jsonl"

ARTIFACT_MODES = frozenset({"canonical", "test", "fixture", "scratch"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def repair_proof_record(proof_id: str, status: str, payload: dict[str, object]) -> dict[str, object]:
    record = {
        "artifact_type": "public_champion_repair_proof",
        "proof_id": proof_id,
        "status": status,
        "timestamp": utc_now_iso(),
        "bundle_version": REPAIR_VERSION,
        "payload": dict(payload),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(record, "proof_hash")


def write_stage_proof(path: Path, proof_id: str, status: str, summary: dict[str, object]) -> None:
    from dopey_autonomy.public_champion_common import write_jsonl_file

    write_jsonl_file(path, [repair_proof_record(proof_id, status, summary)])


def load_hardening_gate_summary() -> dict[str, object]:
    return read_json_file(HARDENING_GATE_SUMMARY_PATH)


def conditional_champion_names() -> list[str]:
    summary = load_hardening_gate_summary()
    names = [str(name) for name in summary.get("conditional_champion_names", [])]
    return names or list(CONDITIONAL_CHAMPION_IDS)


def demoted_champion_names() -> list[str]:
    summary = load_hardening_gate_summary()
    names = [str(name) for name in summary.get("demoted_champion_names", [])]
    return names or list(DEMOTED_CHAMPION_IDS)


def resolve_mode(artifact_mode: str | None) -> str:
    mode = str(artifact_mode or "canonical").lower()
    if mode not in ARTIFACT_MODES:
        return "scratch"
    return mode


def scratch_artifact_path(canonical_path: Path, mode: str) -> Path:
    if mode == "canonical":
        return canonical_path
    relative = canonical_path.name
    parent = canonical_path.parent.name
    return SCRATCH_ROOT / mode / parent / relative
