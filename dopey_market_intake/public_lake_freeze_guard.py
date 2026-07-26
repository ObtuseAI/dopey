"""Freeze guard for the active public market lake."""
from __future__ import annotations

from pathlib import Path

from dopey_autonomy.public_champion_common import (
    ACTIVE_DAILY_ROOT,
    CACHE_ROOT,
    DATA_ROOT,
    MANIFEST_PATH,
    PUBLIC_CHAMPION_ROOT,
    PUBLIC_DAILY_ROOT,
    PUBLIC_SOURCE_TYPES,
    active_manifest,
    fixture_manifest_files,
    is_test_symbol,
    load_rows_for_file_record,
    manifest_files,
    proof_record,
    provider_from_rows,
    public_manifest_files,
    record_with_hash,
    sha256_file,
    stable_hash,
    write_jsonl_file,
    write_summary_with_hash,
)


SUMMARY_PATH = PUBLIC_CHAMPION_ROOT / "public_lake_freeze_guard_summary.json"
INVENTORY_PATH = PUBLIC_CHAMPION_ROOT / "public_lake_file_inventory.jsonl"
RESTORE_RECORDS_PATH = PUBLIC_CHAMPION_ROOT / "public_lake_restore_records.jsonl"
QUALITY_FLAGS_PATH = PUBLIC_CHAMPION_ROOT / "public_lake_quality_flags.jsonl"
PROOF_PATH = PUBLIC_CHAMPION_ROOT / "public_lake_freeze_guard_proof.jsonl"


def run_public_lake_freeze_guard() -> dict[str, object]:
    first_inventory = build_public_lake_inventory()
    first_flags = build_quality_flags(first_inventory)
    restored = False
    restore_records: list[dict[str, object]] = []
    if should_restore_public_lake(first_inventory, first_flags):
        from dopey_market_intake.market_lake_public_promotion import run_market_lake_public_promotion

        before_hash = sha256_file(MANIFEST_PATH) if MANIFEST_PATH.exists() else ""
        removed_test_files = remove_test_symbol_files(first_inventory)
        promotion_summary = run_market_lake_public_promotion(False)
        after_hash = sha256_file(MANIFEST_PATH) if MANIFEST_PATH.exists() else ""
        restore_record = {
            "artifact_type": "public_lake_restore_record",
            "restore_reason": "fixture_or_test_contamination_detected_public_files_available",
            "before_manifest_hash": before_hash,
            "after_manifest_hash": after_hash,
            "removed_test_files": removed_test_files,
            "promotion_active_public_symbols": promotion_summary.get("active_symbols_public", 0),
            "promotion_active_fixture_symbols": promotion_summary.get("active_symbols_fixture", 0),
        }
        restore_records.append(record_with_hash(restore_record, "record_hash"))
        restored = True
    inventory = build_public_lake_inventory()
    flags = build_quality_flags(inventory)
    status = guard_status(inventory, flags)
    manifest = active_manifest()
    summary = {
        "artifact_type": "public_lake_freeze_guard_summary",
        "public_lake_guard_version": "dopey-public-lake-freeze-guard-v1",
        "public_lake_guard_status": status,
        "active_public_symbol_count": count_inventory_source(inventory, "public"),
        "active_fixture_symbol_count": count_inventory_source(inventory, "fixture"),
        "public_cache_symbol_count": public_cache_symbol_count(),
        "test_symbol_residue_count": sum(1 for record in inventory if bool(record["test_symbol_residue"])),
        "public_lake_restored": restored,
        "public_data_preferred": bool(manifest.get("public_data_preferred", True)),
        "manifest_has_market_data_source_type": all("market_data_source_type" in file_record for file_record in manifest_files()),
        "inventory_record_count": len(inventory),
        "quality_flag_count": len(flags),
        "yfinance_cache_file_count": len(list((CACHE_ROOT / "yfinance").glob("*.csv"))),
        "simulated_public_cache_file_count": len(list((CACHE_ROOT / "simulated_public").glob("*.csv"))),
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(INVENTORY_PATH, inventory)
    write_jsonl_file(RESTORE_RECORDS_PATH, restore_records)
    write_jsonl_file(QUALITY_FLAGS_PATH, flags)
    write_jsonl_file(PROOF_PATH, [proof_record("public-lake-freeze-guard", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def build_public_lake_inventory() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for file_record in manifest_files():
        symbol = str(file_record.get("symbol", ""))
        active_path = Path(str(file_record.get("active_path") or file_record.get("path") or ""))
        rows = load_rows_for_file_record(file_record)
        source_type = str(file_record.get("market_data_source_type", ""))
        source_kind = "public" if source_type in PUBLIC_SOURCE_TYPES else ("fixture" if source_type == "fixture_fallback" else "unknown")
        record = {
            "artifact_type": "public_lake_file_inventory",
            "symbol": symbol,
            "row_count": len(rows),
            "first_date": rows[0]["date"] if rows else "",
            "last_date": rows[-1]["date"] if rows else "",
            "provider": provider_from_rows(rows),
            "source_type": source_type,
            "market_data_source_type": source_type,
            "source_kind": source_kind,
            "tier": str(file_record.get("data_tier", "")),
            "path": str(active_path),
            "hash": sha256_file(active_path) if active_path.exists() else "",
            "active_file_exists": active_path.exists(),
            "test_symbol_residue": is_test_symbol(symbol),
            "simulated_public_only": provider_from_rows(rows) == "simulated_public" or "simulated_public" in str(active_path),
        }
        records.append(record_with_hash(record, "record_hash"))
    return records


def build_quality_flags(inventory: list[dict[str, object]]) -> list[dict[str, object]]:
    flags: list[dict[str, object]] = []
    if not public_manifest_files():
        flags.append(flag_record("no-public-active-symbols", "error", "active manifest has no public source files", ""))
    for record in inventory:
        symbol = str(record["symbol"])
        if bool(record["test_symbol_residue"]):
            flags.append(flag_record("test-symbol-residue", "error", "test-only symbol present in active lake", symbol))
        if record["source_kind"] == "fixture":
            flags.append(flag_record("fixture-active-symbol", "error", "fixture fallback present in active lake", symbol))
        if not bool(record["active_file_exists"]):
            flags.append(flag_record("missing-active-file", "error", "manifest active path does not exist", symbol))
        if int(record["row_count"]) <= 0:
            flags.append(flag_record("empty-active-file", "error", "active file has no valid OHLCV rows", symbol))
        if bool(record["simulated_public_only"]):
            flags.append(flag_record("simulated-public-provenance", "error", "active file uses simulated-public-only provenance", symbol))
        if not str(record["market_data_source_type"]):
            flags.append(flag_record("missing-market-data-source-type", "error", "active file lacks market_data_source_type", symbol))
    if len(list((CACHE_ROOT / "yfinance").glob("*.csv"))) == 0 and len(list(CACHE_ROOT.glob("*/*.csv"))) > 0:
        flags.append(flag_record("yfinance-cache-absent", "note", "public cache has no yfinance-backed files", ""))
    return flags


def should_restore_public_lake(inventory: list[dict[str, object]], flags: list[dict[str, object]]) -> bool:
    has_public_files = any(PUBLIC_DAILY_ROOT.glob("*.csv"))
    has_active_files = any(ACTIVE_DAILY_ROOT.glob("*.csv"))
    has_contamination = any(str(flag["severity"]) == "error" for flag in flags)
    has_fixture = bool(fixture_manifest_files()) or any(record["source_kind"] == "fixture" for record in inventory)
    has_test_residue = any(bool(record.get("test_symbol_residue", False)) for record in inventory)
    has_simulated_public = any(bool(record.get("simulated_public_only", False)) for record in inventory)
    return has_public_files and has_active_files and has_contamination and (has_fixture or has_test_residue or has_simulated_public)


def remove_test_symbol_files(inventory: list[dict[str, object]]) -> list[str]:
    removed: list[str] = []
    test_symbols = {str(record.get("symbol", "")) for record in inventory if bool(record.get("test_symbol_residue", False))}
    for symbol in sorted(test_symbols):
        candidate_paths = [
            PUBLIC_DAILY_ROOT / f"{symbol}.csv",
            ACTIVE_DAILY_ROOT / f"{symbol}.csv",
            DATA_ROOT / "market_lake" / "normalized" / "daily_ohlcv" / f"{symbol}.csv",
        ]
        candidate_paths.extend(CACHE_ROOT.glob(f"*/{symbol}.csv"))
        for path in candidate_paths:
            if path.exists() and path.is_file():
                path.unlink()
                removed.append(str(path))
    return removed


def guard_status(inventory: list[dict[str, object]], flags: list[dict[str, object]]) -> str:
    error_count = sum(1 for flag in flags if str(flag["severity"]) == "error")
    public_count = count_inventory_source(inventory, "public")
    fixture_count = count_inventory_source(inventory, "fixture")
    if error_count == 0 and public_count > 0 and fixture_count == 0:
        return "public_lake_clean"
    if public_count == 0:
        return "public_lake_broken_no_public_active_symbols"
    return "public_lake_broken_contamination_detected"


def public_cache_symbol_count() -> int:
    symbols = {path.stem for path in CACHE_ROOT.glob("*/*.csv") if path.parent.name != "simulated_public"}
    return len(symbols)


def count_inventory_source(inventory: list[dict[str, object]], source_kind: str) -> int:
    return sum(1 for record in inventory if str(record.get("source_kind", "")) == source_kind)


def flag_record(flag_id: str, severity: str, message: str, symbol: str) -> dict[str, object]:
    record = {
        "artifact_type": "public_lake_quality_flag",
        "flag_id": flag_id,
        "severity": severity,
        "message": message,
        "symbol": symbol,
    }
    return record_with_hash(record, "flag_hash")


def freeze_guard_status_for_records(file_records: list[dict[str, object]]) -> str:
    fixture_count = sum(1 for record in file_records if str(record.get("market_data_source_type", "")) == "fixture_fallback")
    test_count = sum(1 for record in file_records if is_test_symbol(str(record.get("symbol", ""))))
    public_count = sum(1 for record in file_records if str(record.get("market_data_source_type", "")) in PUBLIC_SOURCE_TYPES)
    if public_count > 0 and fixture_count == 0 and test_count == 0:
        return "public_lake_clean"
    return "public_lake_broken_contamination_detected"


def artifact_paths() -> dict[str, str]:
    return {
        "public_lake_freeze_guard_summary": str(SUMMARY_PATH),
        "public_lake_file_inventory": str(INVENTORY_PATH),
        "public_lake_restore_records": str(RESTORE_RECORDS_PATH),
        "public_lake_quality_flags": str(QUALITY_FLAGS_PATH),
        "public_lake_freeze_guard_proof": str(PROOF_PATH),
    }
