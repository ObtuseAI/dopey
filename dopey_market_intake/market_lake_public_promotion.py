"""Promote public OHLCV files into the active market lake before fixtures."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from dopey_wealth_engine.common import ARTIFACT_ROOT, DATA_ROOT, proof_record, read_csv, stable_hash, write_csv, write_json, write_jsonl
from dopey_wealth_engine.fixtures import DEFAULT_UNIVERSE, OHLCV_FIELDS, ensure_wealth_engine_fixtures

from .market_data_tier_models import assign_data_tier, tier_permissions
from .public_ohlcv_provider_models import PUBLIC_OHLCV_FIELDS


ARTIFACT_DIR = ARTIFACT_ROOT / "market_intake"
PUBLIC_ROOT = DATA_ROOT / "market_lake" / "public" / "daily_ohlcv"
FIXTURE_ROOT = DATA_ROOT / "market_lake" / "fixture_fallback" / "daily_ohlcv"
ACTIVE_ROOT = DATA_ROOT / "market_lake" / "active" / "daily_ohlcv"
NORMALIZED_ROOT = DATA_ROOT / "market_lake" / "normalized" / "daily_ohlcv"
MANIFEST_PATH = DATA_ROOT / "market_lake" / "manifests" / "market_lake_manifest.json"
RECORDS_PATH = ARTIFACT_DIR / "market_lake_public_promotion_records.jsonl"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "market_lake_public_promotion_quality_flags.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "market_lake_public_promotion_summary.json"
PROOF_PATH = ARTIFACT_DIR / "market_lake_public_promotion_proof.jsonl"


def run_market_lake_public_promotion(include_fixture_fallback: bool) -> dict:
    if include_fixture_fallback:
        ensure_wealth_engine_fixtures(DATA_ROOT / "fixtures" / "wealth_engine", 720)
    symbols = sorted({path.stem for path in PUBLIC_ROOT.glob("*.csv")} | set(DEFAULT_UNIVERSE))
    records: list[dict] = []
    quality_flags: list[dict] = []
    manifest_files: list[dict] = []
    active_public = 0
    active_fixture = 0
    public_rows_active = 0
    fixture_rows_active = 0
    for symbol in symbols:
        public_path = PUBLIC_ROOT / f"{symbol}.csv"
        fixture_path = FIXTURE_ROOT / f"{symbol}.csv"
        if not fixture_path.exists():
            candidate_fixture = DATA_ROOT / "fixtures" / "wealth_engine" / "ohlcv" / f"{symbol}.csv"
            if candidate_fixture.exists():
                fixture_path = candidate_fixture
        public_rows = _valid_rows(read_csv(public_path))
        fixture_rows = _valid_rows(read_csv(fixture_path))
        source_type = "public_live_fetch"
        source_path = public_path
        rows = public_rows
        fallback_status = "public_preferred"
        if not rows and include_fixture_fallback and fixture_rows:
            rows = _fixture_labeled_rows(fixture_rows)
            source_type = "fixture_fallback"
            source_path = fixture_path
            fallback_status = "fixture_used_no_public_data"
        if not rows:
            quality_flags.append(_quality_flag(symbol, "missing-active-rows", "warning"))
            continue
        quality = _quality(symbol, rows, source_type)
        provenance = "public_no_key" if source_type != "fixture_fallback" else "synthetic_fixture"
        tier = assign_data_tier(int(quality["row_count"]), bool(quality["sanity_pass"]), bool(quality["continuity_pass"]), bool(quality["freshness_pass"]), provenance)
        active_path = ACTIVE_ROOT / f"{symbol}.csv"
        normalized_path = NORMALIZED_ROOT / f"{symbol}.csv"
        fieldnames = PUBLIC_OHLCV_FIELDS if source_type != "fixture_fallback" else OHLCV_FIELDS + ["market_data_source_type"]
        write_csv(active_path, rows, fieldnames)
        write_csv(normalized_path, rows, fieldnames)
        if source_type == "fixture_fallback":
            active_fixture += 1
            fixture_rows_active += len(rows)
        else:
            active_public += 1
            public_rows_active += len(rows)
        record = {
            "artifact_type": "market_lake_public_promotion_record",
            "symbol": symbol,
            "source_path": str(source_path),
            "active_path": str(active_path),
            "normalized_path": str(normalized_path),
            "row_count": len(rows),
            "data_tier": tier,
            "market_data_source_type": source_type,
            "fallback_status": fallback_status,
            **tier_permissions(tier),
        }
        record["record_hash"] = stable_hash(record)
        records.append(record)
        manifest_files.append({
            "symbol": symbol,
            "source": "public_ohlcv" if source_type != "fixture_fallback" else "fixture_fallback",
            "data_tier": tier,
            "row_count": len(rows),
            "path": str(normalized_path),
            "active_path": str(active_path),
            "start_date": rows[0]["date"],
            "end_date": rows[-1]["date"],
            "market_data_source_type": source_type,
            "fallback_status": fallback_status,
        })
    tier_counts = Counter(str(record["data_tier"]) for record in records)
    manifest = {
        "artifact_type": "market_lake_manifest",
        "manifest_version": "dopey-tiered-market-lake-public-first-v2",
        "files": manifest_files,
        "file_count": len(manifest_files),
        "row_count": sum(int(file_record["row_count"]) for file_record in manifest_files),
        "symbols": [file_record["symbol"] for file_record in manifest_files],
        "data_tier_counts": dict(sorted(tier_counts.items())),
        "public_data_preferred": True,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    active_status = "public_data_active" if active_public else ("fixture_fallback_only" if active_fixture else "empty")
    summary = {
        "artifact_type": "market_lake_public_promotion_summary",
        "market_lake_public_promotion_version": "dopey-market-lake-public-promotion-v2",
        "public_symbols_available": len(list(PUBLIC_ROOT.glob("*.csv"))),
        "active_symbols_public": active_public,
        "active_symbols_fixture": active_fixture,
        "public_rows_active": public_rows_active,
        "fixture_rows_active": fixture_rows_active,
        "active_lake_status": active_status,
        "paper_trading_symbols": [record["symbol"] for record in records if record["data_tier"] == "paper_trading"],
        "research_sandbox_symbols": [record["symbol"] for record in records if record["data_tier"] == "research_sandbox"],
        "market_vision_symbols": [record["symbol"] for record in records if record["data_tier"] == "market_vision"],
        "fixture_only_symbols": [record["symbol"] for record in records if record["market_data_source_type"] == "fixture_fallback"],
        "public_data_preferred": True,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(MANIFEST_PATH, manifest)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(RECORDS_PATH, records, False)
    write_jsonl(QUALITY_FLAGS_PATH, quality_flags, False)
    write_jsonl(PROOF_PATH, [proof_record("market-lake-public-promotion", active_status, summary)], False)
    return {**summary, "artifact_paths": artifact_paths(), "manifest_path": str(MANIFEST_PATH)}


def _valid_rows(rows: list[dict]) -> list[dict]:
    valid: list[dict] = []
    for row in rows:
        try:
            if min(float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])) <= 0:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        valid.append(row)
    return sorted(valid, key=lambda item: str(item["date"]))


def _fixture_labeled_rows(rows: list[dict]) -> list[dict]:
    return [{**row, "market_data_source_type": "fixture_fallback"} for row in rows]


def _quality(symbol: str, rows: list[dict], source_type: str) -> dict:
    gaps = 0
    if len(rows) > 1:
        previous = date.fromisoformat(str(rows[0]["date"])[:10])
        for row in rows[1:]:
            current = date.fromisoformat(str(row["date"])[:10])
            if (current - previous).days > 10:
                gaps += 1
            previous = current
    end_date = date.fromisoformat(str(rows[-1]["date"])[:10]) if rows else date(1970, 1, 1)
    freshness = end_date >= date.today() - timedelta(days=14) if source_type != "fixture_fallback" else True
    return {
        "symbol": symbol,
        "row_count": len(rows),
        "sanity_pass": bool(rows),
        "continuity_pass": gaps <= 12,
        "freshness_pass": freshness,
    }


def _quality_flag(symbol: str, flag_id: str, severity: str) -> dict:
    record = {"artifact_type": "market_lake_public_promotion_quality_flag", "symbol": symbol, "flag_id": flag_id, "severity": severity}
    record["flag_hash"] = stable_hash(record)
    return record


def artifact_paths() -> dict[str, str]:
    return {
        "market_lake_public_promotion_records": str(RECORDS_PATH),
        "market_lake_public_promotion_quality_flags": str(QUALITY_FLAGS_PATH),
        "market_lake_public_promotion_summary": str(SUMMARY_PATH),
        "market_lake_public_promotion_proof": str(PROOF_PATH),
    }
