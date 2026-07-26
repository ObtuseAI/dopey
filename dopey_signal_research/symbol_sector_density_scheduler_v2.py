"""Symbol and sector density scheduler V2."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v2_common import MIN_V2_SECTORS, MIN_V2_SYMBOLS, RESEARCH_V2_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import record_with_hash, sector_for_symbol, write_json_file, write_jsonl_file
from dopey_signal_research.research_universe_coverage_v2 import TARGET_SECTORS, build_universe


SCHEDULE_PATH = RESEARCH_V2_ROOT / "symbol_sector_density_schedule_v2.jsonl"
COVERAGE_PATH = RESEARCH_V2_ROOT / "research_universe_coverage_v2.json"
REJECTIONS_PATH = RESEARCH_V2_ROOT / "symbol_sector_density_rejections_v2.jsonl"
SUMMARY_PATH = RESEARCH_V2_ROOT / "symbol_sector_density_scheduler_v2_summary.json"
PROOF_PATH = RESEARCH_V2_ROOT / "symbol_sector_density_scheduler_v2_proof.jsonl"


def run_symbol_sector_density_scheduler_v2() -> dict[str, object]:
    RESEARCH_V2_ROOT.mkdir(parents=True, exist_ok=True)
    universe = build_universe(target_symbols=120)
    symbols = list(universe["symbols"])
    schedule: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    per_symbol = max(75000 // max(len(symbols), 1), 200)
    sector_symbols: dict[str, list[str]] = {}
    for symbol in symbols:
        sector = sector_for_symbol(symbol)
        sector_symbols.setdefault(sector, []).append(symbol)
        schedule.append(record_with_hash({
            "artifact_type": "symbol_sector_density_schedule_v2",
            "scope": "symbol",
            "scope_id": symbol,
            "sector": sector,
            "target_count": per_symbol,
            **live_safety_fields(),
        }, "record_hash"))

    covered_sectors = set(sector_symbols)
    for sector in TARGET_SECTORS:
        if sector not in covered_sectors:
            rejections.append(record_with_hash({
                "artifact_type": "symbol_sector_density_rejection_v2",
                "scope": "sector",
                "scope_id": sector,
                "reason": "no_eligible_symbols_in_sector",
                **live_safety_fields(),
            }, "record_hash"))
        else:
            schedule.append(record_with_hash({
                "artifact_type": "symbol_sector_density_schedule_v2",
                "scope": "sector",
                "scope_id": sector,
                "target_count": max(75000 // max(len(covered_sectors), 1), 500),
                "symbol_count": len(sector_symbols[sector]),
                **live_safety_fields(),
            }, "record_hash"))

    coverage = {
        "artifact_type": "research_universe_coverage_v2",
        "target_symbol_count": 100,
        "covered_symbol_count": len(symbols),
        "covered_sector_count": len(covered_sectors),
        "sector_counts": universe["sector_counts"],
        "symbols": symbols,
    }
    undercovered_symbols = max(0, MIN_V2_SYMBOLS - len(symbols))
    undercovered_sectors = max(0, MIN_V2_SECTORS - len(covered_sectors))
    summary = {
        "artifact_type": "symbol_sector_density_scheduler_v2_summary",
        "symbol_sector_density_scheduler_version": "dopey-public-symbol-sector-density-v2",
        "symbol_sector_density_status": "symbol_sector_density_scheduled",
        "target_symbol_count": 100,
        "covered_symbol_count": len(symbols),
        "covered_sector_count": len(covered_sectors),
        "coverage_quota_count": len(schedule),
        "undercovered_symbol_count": undercovered_symbols,
        "undercovered_sector_count": undercovered_sectors,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(SCHEDULE_PATH, schedule)
    write_json_file(COVERAGE_PATH, coverage)
    write_jsonl_file(REJECTIONS_PATH, rejections)
    write_stage_proof(PROOF_PATH, "symbol-sector-density-scheduler-v2", str(summary["symbol_sector_density_status"]), summary)
    return {**summary, "artifact_paths": {"symbol_sector_density_scheduler_v2_summary": str(SUMMARY_PATH)}, "universe": coverage}


def load_scheduled_symbols() -> list[str]:
    from dopey_autonomy.public_champion_common import read_json_file
    coverage = read_json_file(COVERAGE_PATH) if COVERAGE_PATH.exists() else build_universe()
    return list(coverage.get("symbols", []))
