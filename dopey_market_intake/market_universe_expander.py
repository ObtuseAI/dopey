"""Expand the market universe after the primary public provider path succeeds."""
from __future__ import annotations

from dopey_wealth_engine.common import ARTIFACT_ROOT, proof_record, stable_hash, write_json, write_jsonl

from .provider_ladder_v2 import run_public_ohlcv_provider_ladder_v2
from .public_ohlcv_provider_models import PRIMARY_UNIVERSE, SECONDARY_EXPANSION_UNIVERSE


ARTIFACT_DIR = ARTIFACT_ROOT / "market_intake"
SUMMARY_PATH = ARTIFACT_DIR / "market_universe_expansion_summary.json"
SYMBOLS_PATH = ARTIFACT_DIR / "market_universe_expansion_symbols.jsonl"
FETCH_RECORDS_PATH = ARTIFACT_DIR / "market_universe_expansion_fetch_records.jsonl"
PROOF_PATH = ARTIFACT_DIR / "market_universe_expansion_proof.jsonl"


def run_market_universe_expander(timeout_seconds: int) -> dict:
    symbols = list(dict.fromkeys([*PRIMARY_UNIVERSE, *SECONDARY_EXPANSION_UNIVERSE]))
    ladder = run_public_ohlcv_provider_ladder_v2(symbols, False, timeout_seconds)
    symbol_records = [_symbol_record(symbol, symbol in set(ladder["symbols_loaded"])) for symbol in symbols]
    fetch_records = [
        {
            "artifact_type": "market_universe_expansion_fetch_record",
            "symbol": symbol,
            "loaded": symbol in set(ladder["symbols_loaded"]),
            "provider": ladder["best_provider_by_symbol"].get(symbol, ""),
        }
        for symbol in symbols
    ]
    for record in fetch_records:
        record["record_hash"] = stable_hash(record)
    summary = {
        "artifact_type": "market_universe_expansion_summary",
        "market_universe_expansion_status": "expanded" if ladder["symbol_success_count"] > len(PRIMARY_UNIVERSE) else "primary_only_or_partial",
        "symbols_attempted": len(symbols),
        "symbols_loaded": ladder["symbol_success_count"],
        "added_symbol_count": max(0, ladder["symbol_success_count"] - len(PRIMARY_UNIVERSE)),
        "provider_ladder_status": ladder["provider_ladder_status"],
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(SYMBOLS_PATH, symbol_records, False)
    write_jsonl(FETCH_RECORDS_PATH, fetch_records, False)
    write_jsonl(PROOF_PATH, [proof_record("market-universe-expander", summary["market_universe_expansion_status"], summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def _symbol_record(symbol: str, loaded: bool) -> dict:
    record = {"artifact_type": "market_universe_expansion_symbol", "symbol": symbol, "loaded": loaded}
    record["record_hash"] = stable_hash(record)
    return record


def artifact_paths() -> dict[str, str]:
    return {
        "market_universe_expansion_summary": str(SUMMARY_PATH),
        "market_universe_expansion_symbols": str(SYMBOLS_PATH),
        "market_universe_expansion_fetch_records": str(FETCH_RECORDS_PATH),
        "market_universe_expansion_proof": str(PROOF_PATH),
    }
