"""Preserve the current public-data lake as the foundation for the V2 deepening bundle."""
from __future__ import annotations

from pathlib import Path

from dopey_autonomy.public_champion_common import (
    ACTIVE_DAILY_ROOT,
    CACHE_ROOT,
    DATA_ROOT,
    MANIFEST_PATH,
    PUBLIC_DAILY_ROOT,
    PUBLIC_SOURCE_TYPES,
    active_manifest,
    fixture_manifest_files,
    is_test_symbol,
    load_rows_for_file_record,
    manifest_files,
    provider_from_rows,
    public_manifest_files,
    record_with_hash,
    safe_int,
    sha256_file,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_deepening_common import (
    DEEPENING_ROOT,
    deepening_proof_record,
    is_contaminated_symbol,
)


SUMMARY_PATH = DEEPENING_ROOT / "public_lake_final_state_lock_v2_summary.json"
INVENTORY_PATH = DEEPENING_ROOT / "public_lake_final_state_inventory_v2.jsonl"
QUALITY_FLAGS_PATH = DEEPENING_ROOT / "public_lake_final_state_quality_flags_v2.jsonl"
RESTORE_RECORDS_PATH = DEEPENING_ROOT / "public_lake_final_state_restore_records_v2.jsonl"
PROOF_PATH = DEEPENING_ROOT / "public_lake_final_state_lock_v2_proof.jsonl"

MINIMUM_PUBLIC_ROWS = 1_000_000


def run_public_lake_final_state_lock_v2() -> dict[str, object]:
    inventory = build_final_state_inventory()
    flags = build_quality_flags(inventory)
    restore_records: list[dict[str, object]] = []
    restored = False
    if should_restore_lake(inventory, flags):
        restore_records = attempt_lake_restore()
        restored = bool(restore_records)
        inventory = build_final_state_inventory()
        flags = build_quality_flags(inventory)
    status = final_state_status(inventory, flags)
    manifest = active_manifest()
    public_rows = sum(int(record["row_count"]) for record in inventory if str(record.get("source_kind")) == "public")
    summary = {
        "artifact_type": "public_lake_final_state_lock_v2_summary",
        "public_lake_final_state_version": "dopey-public-lake-final-state-lock-v2",
        "public_lake_final_state_status": status,
        "active_public_symbol_count": count_source(inventory, "public"),
        "active_fixture_symbol_count": count_source(inventory, "fixture"),
        "public_cache_symbol_count": public_cache_symbol_count(),
        "public_rows_active": public_rows,
        "minimum_public_rows_expected": MINIMUM_PUBLIC_ROWS,
        "public_rows_above_minimum": public_rows >= MINIMUM_PUBLIC_ROWS,
        "test_symbol_residue_count": sum(1 for record in inventory if bool(record["test_symbol_residue"])),
        "public_lake_restored": restored,
        "manifest_has_market_data_source_type": all("market_data_source_type" in file_record for file_record in manifest_files()),
        "yfinance_cache_present": any((CACHE_ROOT / "yfinance").glob("*.csv")),
        "public_cache_provenance_present": public_cache_symbol_count() > 0,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(INVENTORY_PATH, inventory)
    write_jsonl_file(QUALITY_FLAGS_PATH, flags)
    write_jsonl_file(RESTORE_RECORDS_PATH, restore_records)
    write_jsonl_file(PROOF_PATH, [deepening_proof_record("public-lake-final-state-lock-v2", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def build_final_state_inventory() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for file_record in manifest_files():
        symbol = str(file_record.get("symbol", ""))
        active_path = Path(str(file_record.get("active_path") or file_record.get("path") or ""))
        rows = load_rows_for_file_record(file_record)
        source_type = str(file_record.get("market_data_source_type", ""))
        source_kind = "public" if source_type in PUBLIC_SOURCE_TYPES else ("fixture" if source_type == "fixture_fallback" else "unknown")
        record = {
            "artifact_type": "public_lake_final_state_inventory_v2",
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
            "test_symbol_residue": is_test_symbol(symbol) or is_contaminated_symbol(symbol),
            "simulated_public_only": provider_from_rows(rows) == "simulated_public" or "simulated_public" in str(active_path),
        }
        records.append(record_with_hash(record, "record_hash"))
    return records


def build_quality_flags(inventory: list[dict[str, object]]) -> list[dict[str, object]]:
    flags: list[dict[str, object]] = []
    if not public_manifest_files():
        flags.append(flag("no-public-active-symbols", "error", "active manifest has no public source files", ""))
    manifest_symbols = {str(record.get("symbol", "")) for record in inventory}
    public_symbols = {path.stem for path in PUBLIC_DAILY_ROOT.glob("*.csv")}
    active_symbols = {path.stem for path in ACTIVE_DAILY_ROOT.glob("*.csv")}
    for symbol in sorted(public_symbols - manifest_symbols):
        flags.append(flag("unmanifested-public-file", "error", "public OHLCV exists but is absent from the active manifest", symbol))
    for symbol in sorted(active_symbols - manifest_symbols):
        flags.append(flag("unmanifested-active-file", "error", "active OHLCV exists but is absent from the active manifest", symbol))
    for record in inventory:
        symbol = str(record["symbol"])
        if bool(record["test_symbol_residue"]):
            flags.append(flag("test-symbol-residue", "error", "test/fixture/synth-only symbol present in active lake", symbol))
        if record["source_kind"] == "fixture":
            flags.append(flag("fixture-active-symbol", "error", "fixture fallback present in active lake", symbol))
        if not bool(record["active_file_exists"]):
            flags.append(flag("missing-active-file", "error", "manifest active path does not exist", symbol))
        if int(record["row_count"]) <= 0:
            flags.append(flag("empty-active-file", "error", "active file has no valid OHLCV rows", symbol))
        if bool(record["simulated_public_only"]):
            flags.append(flag("simulated-public-provenance", "error", "active file uses simulated-public-only provenance", symbol))
        if not str(record["market_data_source_type"]):
            flags.append(flag("missing-market-data-source-type", "error", "active file lacks market_data_source_type", symbol))
    public_rows = sum(int(record["row_count"]) for record in inventory if str(record.get("source_kind")) == "public")
    if 0 < public_rows < MINIMUM_PUBLIC_ROWS:
        flags.append(flag("public-rows-below-minimum", "warning", f"public rows {public_rows} below minimum {MINIMUM_PUBLIC_ROWS}", ""))
    return flags


def should_restore_lake(inventory: list[dict[str, object]], flags: list[dict[str, object]]) -> bool:
    has_public_files = any(PUBLIC_DAILY_ROOT.glob("*.csv"))
    has_active_files = any(ACTIVE_DAILY_ROOT.glob("*.csv"))
    has_contamination = any(str(flag["severity"]) == "error" for flag in flags)
    return has_public_files and has_active_files and has_contamination


def attempt_lake_restore() -> list[dict[str, object]]:
    restore_records: list[dict[str, object]] = []
    try:
        from dopey_market_intake.market_lake_public_promotion import run_market_lake_public_promotion

        before_hash = sha256_file(MANIFEST_PATH) if MANIFEST_PATH.exists() else ""
        promotion_summary = run_market_lake_public_promotion(False)
        after_hash = sha256_file(MANIFEST_PATH) if MANIFEST_PATH.exists() else ""
        record = {
            "artifact_type": "public_lake_final_state_restore_record_v2",
            "restore_reason": "fixture_or_test_contamination_detected_public_files_available",
            "restore_action": "market_lake_public_promotion_rerun_preserve_public_lake",
            "before_manifest_hash": before_hash,
            "after_manifest_hash": after_hash,
            "promotion_active_public_symbols": promotion_summary.get("active_symbols_public", 0),
            "promotion_active_fixture_symbols": promotion_summary.get("active_symbols_fixture", 0),
            "preserve_existing_public_lake": True,
            "network_fetch_attempted": False,
        }
        restore_records.append(record_with_hash(record, "record_hash"))
    except Exception as exc:  # noqa: BLE001 - restore must never crash the lock
        record = {
            "artifact_type": "public_lake_final_state_restore_record_v2",
            "restore_reason": "restore_attempt_failed_public_lake_preserved",
            "restore_action": "preserve_existing_public_lake_network_safe",
            "error": f"{type(exc).__name__}: {exc}",
            "preserve_existing_public_lake": True,
            "network_fetch_attempted": False,
        }
        restore_records.append(record_with_hash(record, "record_hash"))
    return restore_records


def final_state_status(inventory: list[dict[str, object]], flags: list[dict[str, object]]) -> str:
    error_count = sum(1 for flag in flags if str(flag["severity"]) == "error")
    public_count = count_source(inventory, "public")
    fixture_count = count_source(inventory, "fixture")
    if error_count == 0 and public_count > 0 and fixture_count == 0:
        return "public_lake_locked_clean"
    if public_count == 0:
        return "public_lake_broken_no_public_active_symbols"
    return "public_lake_broken_contamination_detected"


def public_cache_symbol_count() -> int:
    symbols = {path.stem for path in CACHE_ROOT.glob("*/*.csv") if path.parent.name != "simulated_public"}
    return len(symbols)


def count_source(inventory: list[dict[str, object]], source_kind: str) -> int:
    return sum(1 for record in inventory if str(record.get("source_kind", "")) == source_kind)


def flag(flag_id: str, severity: str, message: str, symbol: str) -> dict[str, object]:
    record = {
        "artifact_type": "public_lake_final_state_quality_flag_v2",
        "flag_id": flag_id,
        "severity": severity,
        "message": message,
        "symbol": symbol,
    }
    return record_with_hash(record, "flag_hash")


def final_state_status_for_records(file_records: list[dict[str, object]]) -> str:
    fixture_count = sum(1 for record in file_records if str(record.get("market_data_source_type", "")) == "fixture_fallback")
    test_count = sum(1 for record in file_records if is_test_symbol(str(record.get("symbol", ""))) or is_contaminated_symbol(str(record.get("symbol", ""))))
    public_count = sum(1 for record in file_records if str(record.get("market_data_source_type", "")) in PUBLIC_SOURCE_TYPES)
    if public_count > 0 and fixture_count == 0 and test_count == 0:
        return "public_lake_locked_clean"
    return "public_lake_broken_contamination_detected"


def artifact_paths() -> dict[str, str]:
    return {
        "public_lake_final_state_lock_v2_summary": str(SUMMARY_PATH),
        "public_lake_final_state_inventory_v2": str(INVENTORY_PATH),
        "public_lake_final_state_quality_flags_v2": str(QUALITY_FLAGS_PATH),
        "public_lake_final_state_restore_records_v2": str(RESTORE_RECORDS_PATH),
        "public_lake_final_state_lock_v2_proof": str(PROOF_PATH),
    }
