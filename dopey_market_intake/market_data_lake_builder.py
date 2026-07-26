"""Build the tiered market data lake for market vision and paper tournaments."""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path

from dopey_wealth_engine.common import ARTIFACT_ROOT, DATA_ROOT, proof_record, read_csv, read_json, stable_hash, write_csv, write_json, write_jsonl
from dopey_wealth_engine.fixtures import DEFAULT_UNIVERSE, OHLCV_FIELDS, ensure_wealth_engine_fixtures

from .market_data_tier_models import assign_data_tier, tier_permissions
from .market_source_registry import build_market_source_registry
from .market_lake_public_promotion import run_market_lake_public_promotion
from .openbb_market_intake_adapter import run_openbb_market_intake_adapter
from .public_market_intake_fallbacks import fetch_stooq_daily, load_local_fixture_daily
from .yfinance_market_intake_adapter import run_yfinance_market_intake_adapter


ARTIFACT_DIR = ARTIFACT_ROOT / "market_intake"
RAW_ROOT = DATA_ROOT / "market_lake" / "raw"
NORMALIZED_ROOT = DATA_ROOT / "market_lake" / "normalized" / "daily_ohlcv"
CONTEXT_ROOT = DATA_ROOT / "market_lake" / "normalized" / "context"
MANIFEST_PATH = DATA_ROOT / "market_lake" / "manifests" / "market_lake_manifest.json"
FETCH_RECORDS_PATH = ARTIFACT_DIR / "market_data_fetch_records.jsonl"
FETCH_REJECTIONS_PATH = ARTIFACT_DIR / "market_data_fetch_rejections.jsonl"
NORMALIZATION_RECORDS_PATH = ARTIFACT_DIR / "market_data_normalization_records.jsonl"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "market_data_quality_flags.jsonl"
TIER_ASSIGNMENTS_PATH = ARTIFACT_DIR / "market_data_tier_assignments.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "market_data_lake_summary.json"
PROOF_PATH = ARTIFACT_DIR / "market_data_lake_proof.jsonl"


def run_market_data_lake_builder(use_network: bool, fixture_on_failure: bool) -> dict:
    public_root = DATA_ROOT / "market_lake" / "public" / "daily_ohlcv"
    if use_network and any(public_root.glob("*.csv")):
        return _build_from_public_active_lake(fixture_on_failure)
    fixture_summary = ensure_wealth_engine_fixtures(DATA_ROOT / "fixtures" / "wealth_engine", 720)
    sources = build_market_source_registry()
    symbols = list(DEFAULT_UNIVERSE)
    openbb = run_openbb_market_intake_adapter(symbols)
    yfinance = run_yfinance_market_intake_adapter(symbols)

    fetch_records: list[dict] = []
    rejections: list[dict] = []
    normalization_records: list[dict] = []
    quality_flags: list[dict] = []
    tier_records: list[dict] = []
    manifest_files: list[dict] = []
    successful_sources: set[str] = set()
    fallback_source_count = 0

    for symbol in symbols:
        fetch = fetch_stooq_daily(symbol, 3) if use_network else {"source": "stooq", "symbol": symbol, "status": "network_disabled", "rows": [], "error": "network_disabled"}
        if not fetch["rows"] and fixture_on_failure:
            fixture_path = DATA_ROOT / "fixtures" / "wealth_engine" / "ohlcv" / f"{symbol}.csv"
            rejection = {
                "artifact_type": "market_data_fetch_rejection",
                "source": fetch["source"],
                "symbol": symbol,
                "status": fetch["status"],
                "error": fetch["error"],
            }
            rejection["record_hash"] = stable_hash(rejection)
            rejections.append(rejection)
            fetch = load_local_fixture_daily(symbol, fixture_path)
            fallback_source_count += 1
        rows = _normalize_rows(fetch["rows"])
        raw_path = RAW_ROOT / fetch["source"] / f"{symbol}.csv"
        normalized_path = NORMALIZED_ROOT / f"{symbol}.csv"
        if rows:
            successful_sources.add(fetch["source"])
            write_csv(raw_path, rows, OHLCV_FIELDS)
            write_csv(normalized_path, rows, OHLCV_FIELDS)
        quality = _quality(symbol, rows, fetch["source"])
        tier = assign_data_tier(
            int(quality["row_count"]),
            bool(quality["sanity_pass"]),
            bool(quality["continuity_pass"]),
            bool(quality["freshness_pass"]),
            "synthetic_fixture" if fetch["source"] == "fixture_fallback" else "public_no_key",
        )
        fetch_record = {
            "artifact_type": "market_data_fetch_record",
            "source": fetch["source"],
            "symbol": symbol,
            "status": fetch["status"],
            "row_count": len(rows),
            "raw_path": str(raw_path) if rows else "",
            "credentials_created": False,
            "env_created": False,
            "broker_connection_used": False,
            "live_trading_enabled": False,
        }
        fetch_record["record_hash"] = stable_hash(fetch_record)
        fetch_records.append(fetch_record)
        norm = {
            "artifact_type": "market_data_normalization_record",
            "symbol": symbol,
            "source": fetch["source"],
            "status": "normalized" if rows else "empty",
            "row_count": len(rows),
            "normalized_path": str(normalized_path) if rows else "",
        }
        norm["record_hash"] = stable_hash(norm)
        normalization_records.append(norm)
        quality_flags.append(with_record_hash_quality(quality))
        tier_record = {
            "artifact_type": "market_data_tier_assignment",
            "symbol": symbol,
            "source": fetch["source"],
            "data_tier": tier,
            "row_count": len(rows),
            **tier_permissions(tier),
            "live_gate_allowed": False,
        }
        tier_record["record_hash"] = stable_hash(tier_record)
        tier_records.append(tier_record)
        if rows:
            manifest_files.append({
                "symbol": symbol,
                "source": fetch["source"],
                "data_tier": tier,
                "row_count": len(rows),
                "path": str(normalized_path),
                "start_date": rows[0]["date"],
                "end_date": rows[-1]["date"],
                "market_data_source_type": "fixture_fallback" if fetch["source"] == "fixture_fallback" else "public_live_fetch",
                "fallback_status": "fixture_used_no_public_data" if fetch["source"] == "fixture_fallback" else "public_fetch",
            })

    tier_counts = Counter(record["data_tier"] for record in tier_records)
    row_count = sum(file_record["row_count"] for file_record in manifest_files)
    date_values = [file_record["start_date"] for file_record in manifest_files] + [file_record["end_date"] for file_record in manifest_files]
    context_record = {
        "artifact_type": "market_context_record",
        "context_id": "public-benchmark-context-v1",
        "symbols": symbols,
        "notes": "Context lane is public/no-key only; no evidence-grade or live claim is made.",
        "paper_only": True,
        "live_blocked": True,
    }
    context_record["record_hash"] = stable_hash(context_record)
    write_jsonl(CONTEXT_ROOT / "public_context_records.jsonl", [context_record], False)
    manifest = {
        "artifact_type": "market_lake_manifest",
        "manifest_version": "dopey-tiered-market-lake-v1",
        "files": manifest_files,
        "file_count": len(manifest_files),
        "row_count": row_count,
        "symbols": [file_record["symbol"] for file_record in manifest_files],
        "data_tier_counts": dict(sorted(tier_counts.items())),
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    write_json(MANIFEST_PATH, manifest)
    only_fixture_fallback = row_count > 0 and fallback_source_count == len(symbols)
    market_data_status = "internal_fixture_fallback_loaded_blocked_no_public_market_data" if only_fixture_fallback else ("loaded" if row_count else "blocked_no_market_data")
    summary = {
        "artifact_type": "market_data_lake_summary",
        "market_data_status": market_data_status,
        "source_count": len(sources),
        "attempted_source_count": 4,
        "successful_source_count": len(successful_sources),
        "symbols_fetched": len(manifest_files),
        "symbols_loaded": [file_record["symbol"] for file_record in manifest_files],
        "row_count": row_count,
        "daily_ohlcv_rows": row_count,
        "date_range": {"start": min(date_values) if date_values else "", "end": max(date_values) if date_values else ""},
        "market_vision_file_count": int(tier_counts.get("market_vision", 0)),
        "research_sandbox_file_count": int(tier_counts.get("research_sandbox", 0)),
        "paper_trading_file_count": int(tier_counts.get("paper_trading", 0)),
        "evidence_grade_file_count": int(tier_counts.get("evidence_grade", 0)),
        "failed_source_count": len(rejections),
        "fallback_source_count": fallback_source_count,
        "openbb_used": bool(openbb["openbb_used"]),
        "openbb_status": openbb["status"],
        "yfinance_used": bool(yfinance["yfinance_used"]),
        "yfinance_status": yfinance["status"],
        "fixture_case_count": fixture_summary["case_count"],
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(FETCH_RECORDS_PATH, fetch_records, False)
    write_jsonl(FETCH_REJECTIONS_PATH, rejections, False)
    write_jsonl(NORMALIZATION_RECORDS_PATH, normalization_records, False)
    write_jsonl(QUALITY_FLAGS_PATH, quality_flags, False)
    write_jsonl(TIER_ASSIGNMENTS_PATH, tier_records, False)
    write_jsonl(PROOF_PATH, [proof_record("market-data-lake-builder", summary["market_data_status"], summary)], False)
    return {**summary, "artifact_paths": artifact_paths(), "manifest_path": str(MANIFEST_PATH)}


def with_record_hash_quality(record: dict) -> dict:
    output = dict(record)
    output["record_hash"] = stable_hash(output)
    return output


def _build_from_public_active_lake(fixture_on_failure: bool) -> dict:
    promotion = run_market_lake_public_promotion(fixture_on_failure)
    manifest = read_json(MANIFEST_PATH)
    files = manifest.get("files", []) if isinstance(manifest.get("files", []), list) else []
    fetch_records: list[dict] = []
    normalization_records: list[dict] = []
    tier_records: list[dict] = []
    quality_flags: list[dict] = []
    accepted_public_files: list[dict] = []
    accepted_fixture_files: list[dict] = []
    loaded_symbols: list[str] = []
    dates: list[str] = []
    row_count = 0
    parsed_rejected_row_count = 0
    parsed_rejected_symbols: list[str] = []
    failed_file_count = 0
    for file_record in files:
        if not isinstance(file_record, dict):
            failed_file_count += 1
            continue
        quality, rows, active_path = _validate_active_lake_file(file_record)
        source_type = str(file_record.get("market_data_source_type", ""))
        source = str(file_record.get("source", ""))
        symbol = str(file_record.get("symbol", ""))
        quality_pass = quality["quality_status"] == "pass"
        if not quality_pass:
            failed_file_count += 1
        if rows and quality_pass:
            row_count += len(rows)
            loaded_symbols.append(symbol)
            dates.extend((rows[0]["date"], rows[-1]["date"]))
            if source_type.startswith("public"):
                accepted_public_files.append(file_record)
            elif source_type == "fixture_fallback":
                accepted_fixture_files.append(file_record)
        elif rows:
            parsed_rejected_row_count += len(rows)
            parsed_rejected_symbols.append(symbol)
        provenance = (
            "synthetic_fixture"
            if source_type == "fixture_fallback"
            else "public_no_key"
        )
        tier = assign_data_tier(
            len(rows),
            bool(quality["sanity_pass"]),
            bool(quality["continuity_pass"]),
            bool(quality["freshness_pass"]),
            provenance,
        )
        fetch_record = {
            "artifact_type": "market_data_fetch_record",
            "source": source,
            "symbol": symbol,
            "status": (
                "active_public_lake_validated"
                if quality_pass
                else "active_public_lake_quality_rejected"
            ),
            "row_count": len(rows),
            "raw_path": str(active_path) if active_path is not None else "",
            "market_data_source_type": source_type,
            "credentials_created": False,
            "env_created": False,
            "broker_connection_used": False,
            "live_trading_enabled": False,
        }
        fetch_record["record_hash"] = stable_hash(fetch_record)
        fetch_records.append(fetch_record)
        norm = {
            "artifact_type": "market_data_normalization_record",
            "symbol": symbol,
            "source": source,
            "status": (
                "validated_active_rows"
                if quality_pass
                else "rejected_invalid_active_rows"
            ),
            "row_count": len(rows),
            "normalized_path": str(file_record.get("path", "")),
            "market_data_source_type": source_type,
        }
        norm["record_hash"] = stable_hash(norm)
        normalization_records.append(norm)
        tier_record = {
            "artifact_type": "market_data_tier_assignment",
            "symbol": symbol,
            "source": source,
            "data_tier": tier,
            "row_count": len(rows),
            "market_data_source_type": source_type,
            **tier_permissions(tier),
            "active_lake_accepted": quality_pass,
            "live_gate_allowed": False,
        }
        tier_record["record_hash"] = stable_hash(tier_record)
        tier_records.append(tier_record)
        quality_flags.append(with_record_hash_quality(quality))
    tier_counts = Counter(
        str(record["data_tier"])
        for record in tier_records
        if record["active_lake_accepted"] is True
    )
    any_quality_warning = any(
        record["quality_status"] != "pass"
        for record in quality_flags
    )
    if failed_file_count and not loaded_symbols:
        market_data_status = "blocked_invalid_active_market_data"
    elif any_quality_warning:
        market_data_status = "degraded_active_market_data_quality"
    elif accepted_public_files:
        market_data_status = "public_market_data_loaded"
    elif accepted_fixture_files:
        market_data_status = (
            "internal_fixture_fallback_loaded_blocked_no_public_market_data"
        )
    else:
        market_data_status = "blocked_no_market_data"
    summary = {
        "artifact_type": "market_data_lake_summary",
        "market_data_status": market_data_status,
        "source_count": len(build_market_source_registry()),
        "attempted_source_count": 1,
        "successful_source_count": 1 if loaded_symbols else 0,
        "symbols_fetched": len(loaded_symbols),
        "symbols_loaded": sorted(loaded_symbols),
        "row_count": row_count,
        "daily_ohlcv_rows": row_count,
        "parsed_but_rejected_row_count": parsed_rejected_row_count,
        "parsed_but_rejected_symbol_count": len(
            set(parsed_rejected_symbols)
        ),
        "parsed_but_rejected_symbols": sorted(
            set(parsed_rejected_symbols)
        ),
        "date_range": {"start": min([value for value in dates if value], default=""), "end": max([value for value in dates if value], default="")},
        "market_vision_file_count": int(tier_counts.get("market_vision", 0)),
        "research_sandbox_file_count": int(tier_counts.get("research_sandbox", 0)),
        "paper_trading_file_count": int(tier_counts.get("paper_trading", 0)),
        "evidence_grade_file_count": int(tier_counts.get("evidence_grade", 0)),
        "failed_source_count": failed_file_count,
        "fallback_source_count": len(accepted_fixture_files),
        "openbb_used": False,
        "openbb_status": "not_installed_adapter_ready",
        "yfinance_used": False,
        "yfinance_status": "provider_ladder_separate",
        "public_data_preferred": True,
        "active_symbols_public": len(accepted_public_files),
        "active_symbols_fixture": len(accepted_fixture_files),
        "promotion_reported_active_symbols_public": promotion[
            "active_symbols_public"
        ],
        "promotion_reported_active_symbols_fixture": promotion[
            "active_symbols_fixture"
        ],
        "quality_warning_count": sum(
            record["quality_status"] != "pass"
            for record in quality_flags
        ),
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(FETCH_RECORDS_PATH, fetch_records, False)
    write_jsonl(FETCH_REJECTIONS_PATH, [], False)
    write_jsonl(NORMALIZATION_RECORDS_PATH, normalization_records, False)
    write_jsonl(QUALITY_FLAGS_PATH, quality_flags, False)
    write_jsonl(TIER_ASSIGNMENTS_PATH, tier_records, False)
    write_jsonl(PROOF_PATH, [proof_record("market-data-lake-builder", summary["market_data_status"], summary)], False)
    return {**summary, "artifact_paths": artifact_paths(), "manifest_path": str(MANIFEST_PATH)}


def _resolve_active_lake_path(file_record: Mapping[str, object]) -> Path:
    raw_value = file_record.get("active_path", file_record.get("path"))
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError("active lake manifest row lacks active_path or path")
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        candidate = DATA_ROOT / "market_lake" / candidate
    resolved = candidate.resolve()
    lake_root = (DATA_ROOT / "market_lake").resolve()
    if not resolved.is_relative_to(lake_root):
        raise ValueError(
            "active lake path escapes the governed market lake: "
            f"path={resolved}, root={lake_root}"
        )
    return resolved


def _validate_active_lake_file(
    file_record: Mapping[str, object],
) -> tuple[dict, list[dict], Path | None]:
    symbol = str(file_record.get("symbol", ""))
    source = str(file_record.get("source", ""))
    source_type = str(file_record.get("market_data_source_type", ""))
    try:
        active_path = _resolve_active_lake_path(file_record)
    except ValueError as error:
        quality = _quality(symbol, [], source)
        return {
            **quality,
            "sanity_pass": False,
            "quality_status": "fail",
            "active_path_status": "invalid_manifest_path",
            "quality_error": str(error),
            "manifest_row_count": file_record.get("row_count"),
            "invalid_row_count": 0,
            "manifest_row_count_matches": False,
            "manifest_date_range_matches": False,
            "market_data_source_type": source_type,
        }, [], None
    if not active_path.is_file():
        quality = _quality(symbol, [], source)
        return {
            **quality,
            "sanity_pass": False,
            "quality_status": "fail",
            "active_path_status": "missing",
            "quality_error": f"active lake file is missing: path={active_path}",
            "manifest_row_count": file_record.get("row_count"),
            "invalid_row_count": 0,
            "manifest_row_count_matches": False,
            "manifest_date_range_matches": False,
            "market_data_source_type": source_type,
        }, [], active_path
    try:
        raw_rows = read_csv(active_path)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        quality = _quality(symbol, [], source)
        return {
            **quality,
            "sanity_pass": False,
            "quality_status": "fail",
            "active_path_status": "unreadable",
            "quality_error": str(error),
            "manifest_row_count": file_record.get("row_count"),
            "invalid_row_count": 0,
            "manifest_row_count_matches": False,
            "manifest_date_range_matches": False,
            "market_data_source_type": source_type,
        }, [], active_path
    rows = _normalize_rows(raw_rows)
    invalid_row_count = len(raw_rows) - len(rows)
    manifest_row_count = file_record.get("row_count")
    row_count_matches = (
        isinstance(manifest_row_count, int)
        and not isinstance(manifest_row_count, bool)
        and manifest_row_count == len(rows)
    )
    date_range_matches = bool(rows) and (
        file_record.get("start_date") == rows[0]["date"]
        and file_record.get("end_date") == rows[-1]["date"]
    )
    base_quality = _quality(symbol, rows, source)
    sanity_pass = bool(base_quality["sanity_pass"]) and (
        invalid_row_count == 0
        and row_count_matches
        and date_range_matches
    )
    quality_status = (
        "pass"
        if (
            sanity_pass
            and bool(base_quality["continuity_pass"])
            and bool(base_quality["freshness_pass"])
        )
        else ("fail" if not sanity_pass else "warning")
    )
    return {
        **base_quality,
        "sanity_pass": sanity_pass,
        "quality_status": quality_status,
        "active_path_status": "validated",
        "quality_error": "",
        "manifest_row_count": manifest_row_count,
        "invalid_row_count": invalid_row_count,
        "manifest_row_count_matches": row_count_matches,
        "manifest_date_range_matches": date_range_matches,
        "market_data_source_type": source_type,
    }, rows, active_path


def _normalize_rows(rows: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for row in rows:
        try:
            open_value = float(row["open"])
            high_value = float(row["high"])
            low_value = float(row["low"])
            close_value = float(row["close"])
            raw_volume = float(row["volume"])
            parsed_date = date.fromisoformat(str(row["date"])[:10])
        except (KeyError, OverflowError, TypeError, ValueError):
            continue
        numeric_values = (
            open_value,
            high_value,
            low_value,
            close_value,
            raw_volume,
        )
        if not all(math.isfinite(value) for value in numeric_values):
            continue
        if min(open_value, high_value, low_value, close_value) <= 0:
            continue
        if high_value < max(open_value, close_value, low_value):
            continue
        if low_value > min(open_value, close_value, high_value):
            continue
        if raw_volume < 0:
            continue
        volume_value = int(raw_volume)
        normalized.append({
            "date": parsed_date.isoformat(),
            "open": f"{open_value:.4f}",
            "high": f"{high_value:.4f}",
            "low": f"{low_value:.4f}",
            "close": f"{close_value:.4f}",
            "volume": str(volume_value),
        })
    return sorted(normalized, key=lambda item: item["date"])


def _quality(symbol: str, rows: list[dict], source: str) -> dict:
    row_count = len(rows)
    sanity = row_count > 0
    gaps = 0
    if row_count > 1:
        previous = date.fromisoformat(rows[0]["date"])
        for row in rows[1:]:
            current = date.fromisoformat(row["date"])
            if (current - previous).days > 10:
                gaps += 1
            previous = current
    end_date = date.fromisoformat(rows[-1]["date"]) if rows else date(1970, 1, 1)
    freshness = end_date >= date.today() - timedelta(days=14) if source != "fixture_fallback" else True
    continuity = gaps <= 3
    return {
        "artifact_type": "market_data_quality_flag",
        "symbol": symbol,
        "source": source,
        "row_count": row_count,
        "sanity_pass": sanity,
        "continuity_pass": continuity,
        "freshness_pass": freshness,
        "large_gap_count": gaps,
        "quality_status": (
            "pass"
            if sanity and continuity and freshness
            else "warning"
        ),
        "paper_only": True,
        "live_blocked": True,
    }


def artifact_paths() -> dict[str, str]:
    return {
        "market_source_registry": str(ARTIFACT_DIR / "market_source_registry.jsonl"),
        "market_data_fetch_records": str(FETCH_RECORDS_PATH),
        "market_data_fetch_rejections": str(FETCH_REJECTIONS_PATH),
        "market_data_normalization_records": str(NORMALIZATION_RECORDS_PATH),
        "market_data_quality_flags": str(QUALITY_FLAGS_PATH),
        "market_data_tier_assignments": str(TIER_ASSIGNMENTS_PATH),
        "market_data_lake_summary": str(SUMMARY_PATH),
        "market_data_lake_proof": str(PROOF_PATH),
        "market_lake_manifest": str(MANIFEST_PATH),
    }
