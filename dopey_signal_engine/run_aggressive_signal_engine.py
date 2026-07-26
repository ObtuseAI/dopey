"""Run the aggressive signal engine."""
from __future__ import annotations

import json
from collections import Counter

from dopey_wealth_engine.common import ARTIFACT_ROOT, DATA_ROOT, proof_record, read_json, read_jsonl, stable_hash, write_json, write_jsonl

from .aggressive_signal_factory import generate_aggressive_signals
from .signal_mutation_engine import mutate_signal_candidates
from .signal_quality_ranker import rank_signal_candidates


ARTIFACT_DIR = ARTIFACT_ROOT / "signals"
CANDIDATES_PATH = ARTIFACT_DIR / "aggressive_signal_candidates.jsonl"
MUTATIONS_PATH = ARTIFACT_DIR / "signal_mutation_records.jsonl"
RANKINGS_PATH = ARTIFACT_DIR / "signal_quality_rankings.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "aggressive_signal_engine_summary.json"
PROOF_PATH = ARTIFACT_DIR / "aggressive_signal_engine_proof.jsonl"


def run_aggressive_signal_engine() -> dict:
    features = read_jsonl(ARTIFACT_ROOT / "chart_vision" / "chart_feature_records.jsonl")
    manifest = read_json(DATA_ROOT / "market_lake" / "manifests" / "market_lake_manifest.json")
    tier_by_symbol = {
        str(file_record["symbol"]): str(file_record.get("data_tier", "market_vision"))
        for file_record in manifest.get("files", [])
        if isinstance(file_record, dict)
    }
    source_by_symbol = {
        str(file_record["symbol"]): str(file_record.get("market_data_source_type", "fixture_fallback"))
        for file_record in manifest.get("files", [])
        if isinstance(file_record, dict)
    }
    latest_by_symbol: dict[str, dict] = {}
    for record in features:
        record["market_data_source_type"] = record.get("market_data_source_type", source_by_symbol.get(str(record["symbol"]), "fixture_fallback"))
        latest_by_symbol[str(record["symbol"])] = record
    candidates = generate_aggressive_signals(latest_by_symbol, tier_by_symbol)
    mutations = mutate_signal_candidates(candidates)
    rankings = rank_signal_candidates(candidates)
    counts = Counter(candidate["trade_intent"] for candidate in candidates)
    family_counts = Counter(candidate["setup_family"] for candidate in candidates)
    summary = {
        "artifact_type": "aggressive_signal_engine_summary",
        "signal_engine_version": "dopey-aggressive-signal-engine-v1",
        "signal_generation_status": "candidates_generated" if candidates else "blocked_no_market_data",
        "signal_candidate_count": len(candidates),
        "long_call_candidate_count": int(counts.get("long_call", 0)),
        "long_put_candidate_count": int(counts.get("long_put", 0)),
        "no_trade_count": int(counts.get("no_trade", 0)),
        "mutation_count": len(mutations),
        "ranked_count": len(rankings),
        "setup_family_counts": dict(sorted(family_counts.items())),
        "paper_only": True,
        "live_blocked": True,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(CANDIDATES_PATH, candidates, False)
    write_jsonl(MUTATIONS_PATH, mutations, False)
    write_jsonl(RANKINGS_PATH, rankings, False)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("aggressive-signal-engine", summary["signal_generation_status"], summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "aggressive_signal_candidates": str(CANDIDATES_PATH),
        "signal_mutation_records": str(MUTATIONS_PATH),
        "signal_quality_rankings": str(RANKINGS_PATH),
        "aggressive_signal_engine_summary": str(SUMMARY_PATH),
        "aggressive_signal_engine_proof": str(PROOF_PATH),
    }


def main() -> int:
    summary = run_aggressive_signal_engine()
    print(json.dumps({
        "signal_generation_status": summary["signal_generation_status"],
        "signal_candidate_count": summary["signal_candidate_count"],
        "long_call_candidate_count": summary["long_call_candidate_count"],
        "long_put_candidate_count": summary["long_put_candidate_count"],
        "summary_path": summary["artifact_paths"]["aggressive_signal_engine_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
