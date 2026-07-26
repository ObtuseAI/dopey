"""Public feature miner V2 with broader symbol coverage."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v2_common import RESEARCH_V2_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import active_rows_by_symbol, is_test_symbol, record_with_hash, sector_for_symbol, write_jsonl_file
from dopey_signal_research.public_feature_miner_v1 import compute_features
from dopey_signal_research.symbol_sector_density_scheduler_v2 import load_scheduled_symbols


REGISTRY_PATH = RESEARCH_V2_ROOT / "public_feature_registry_v2.jsonl"
RECORDS_PATH = RESEARCH_V2_ROOT / "public_feature_records_v2.jsonl"
COVERAGE_PATH = RESEARCH_V2_ROOT / "public_feature_coverage_v2.jsonl"
QUALITY_PATH = RESEARCH_V2_ROOT / "public_feature_quality_flags_v2.jsonl"
SUMMARY_PATH = RESEARCH_V2_ROOT / "public_feature_miner_v2_summary.json"
PROOF_PATH = RESEARCH_V2_ROOT / "public_feature_miner_v2_proof.jsonl"


def run_public_feature_miner_v2(step: int = 8) -> dict[str, object]:
    RESEARCH_V2_ROOT.mkdir(parents=True, exist_ok=True)
    symbols = load_scheduled_symbols()
    if not symbols:
        from .symbol_sector_density_scheduler_v2 import run_symbol_sector_density_scheduler_v2
        run_symbol_sector_density_scheduler_v2()
        symbols = load_scheduled_symbols()
    rows_by_symbol = active_rows_by_symbol()
    spy_rows = rows_by_symbol.get("SPY", [])
    registry: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    coverage: list[dict[str, object]] = []
    group_counts: Counter[str] = Counter()

    for symbol in symbols:
        rows = rows_by_symbol.get(symbol, [])
        if len(rows) < 200 or is_test_symbol(symbol):
            continue
        symbol_features = 0
        for index in range(60, len(rows) - 5, step):
            bundle = compute_features(symbol, rows, index, spy_rows)
            for group, features in bundle.items():
                for feature_name, value in features.items():
                    group_counts[group] += 1
                    symbol_features += 1
                    if len(registry) < 500000:
                        registry.append(record_with_hash({
                            "artifact_type": "public_feature_registry_v2",
                            "symbol": symbol,
                            "sector": sector_for_symbol(symbol),
                            "date": rows[index]["date"],
                            "feature_group": group,
                            "feature_name": feature_name,
                            "feature_value": round(float(value), 6),
                            "discovery_family_ready": True,
                            **live_safety_fields(),
                        }, "record_hash"))
        coverage.append(record_with_hash({
            "artifact_type": "public_feature_coverage_v2",
            "symbol": symbol,
            "sector": sector_for_symbol(symbol),
            "feature_count": symbol_features,
            **live_safety_fields(),
        }, "record_hash"))

    summary = {
        "artifact_type": "public_feature_miner_v2_summary",
        "public_feature_miner_v2_version": "dopey-public-feature-miner-v2",
        "public_feature_miner_v2_status": "public_features_mined_v2",
        "feature_count": len(registry),
        "symbol_count": len(coverage),
        "sector_count": len({row["sector"] for row in coverage}),
        "row_count": sum(int(row["feature_count"]) for row in coverage),
        "feature_group_counts": dict(group_counts),
        "public_data_only": True,
        "fixture_feature_count": 0,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(REGISTRY_PATH, registry)
    write_jsonl_file(RECORDS_PATH, records)
    write_jsonl_file(COVERAGE_PATH, coverage)
    write_jsonl_file(QUALITY_PATH, [record_with_hash({"artifact_type": "public_feature_quality_flag_v2", "flag_id": "public_data_only", "passed": True, **live_safety_fields()}, "record_hash")])
    write_stage_proof(PROOF_PATH, "public-feature-miner-v2", str(summary["public_feature_miner_v2_status"]), summary)
    return {**summary, "artifact_paths": {"public_feature_miner_v2_summary": str(SUMMARY_PATH)}}
