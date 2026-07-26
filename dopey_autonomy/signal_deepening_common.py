"""Shared helpers for the public-market signal mutation deepening V2 bundle."""
from __future__ import annotations

from datetime import datetime, timezone

from dopey_autonomy.public_champion_common import (
    ARTIFACT_ROOT,
    CHAMPION_ROOT,
    EVOLUTION_ROOT,
    LIVE_GATE_ROOT,
    OPTIONS_ENGINE_ROOT,
    SCOREBOARD_ROOT,
    SIGNAL_ROOT,
    TOURNAMENT_ROOT,
    proof_record,
    record_with_hash,
    write_summary_with_hash,
)


DEEPENING_VERSION = "dopey-public-market-signal-mutation-deepening-v2"
DEEPENING_ROOT = ARTIFACT_ROOT / "public_signal_deepening"

TEST_SYMBOL_PREFIXES = ("SIM", "TEST", "FIXTURE", "SYNTH")

NEAR_CHAMPION_SEEDS = [
    "bollinger_expansion|fast_scalp|dte7|ATM",
    "atr_compression_breakout|fast_scalp|dte7|ATM",
    "sector_relative_strength|invalidation_strict|dte14|1pct_otm",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def deepening_proof_record(proof_id: str, status: str, payload) -> dict[str, object]:
    record = {
        "artifact_type": "public_signal_deepening_proof",
        "proof_id": proof_id,
        "status": status,
        "timestamp": utc_now_iso(),
        "bundle_version": DEEPENING_VERSION,
        "payload": dict(payload) if isinstance(payload, dict) else payload,
        "paper_only": True,
        "live_blocked": True,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "real_orders_placed": False,
        "live_trading_enabled": False,
    }
    return record_with_hash(record, "proof_hash")


def is_contaminated_symbol(symbol: str) -> bool:
    normalized = symbol.upper()
    return any(normalized.startswith(prefix) for prefix in TEST_SYMBOL_PREFIXES)


def live_safety_fields() -> dict[str, object]:
    return {
        "paper_only": True,
        "public_data_only": True,
        "fixture_trade_count": 0,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "broker_connection_enabled": False,
        "real_orders_placed": False,
        "real_order_enabled": False,
        "live_trading_enabled": False,
        "live_blocked": True,
    }
