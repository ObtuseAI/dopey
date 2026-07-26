"""Watchlist-driven research candidate generator V2."""
from __future__ import annotations

import hashlib
from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v2_common import CANDIDATES_V2_PATH, RESEARCH_V2_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import active_rows_by_symbol, is_test_symbol, record_with_hash, sector_for_symbol, write_jsonl_file
from dopey_signal_research.discovery_signal_family_generator_v1 import matches_family
from dopey_signal_research.discovery_signal_family_models_v1 import FAMILY_TEMPLATES, DiscoveryFamilyTemplate
from dopey_signal_research.public_feature_miner_v1 import compute_features
from dopey_signal_research.research_candidate_density_scheduler_v2 import build_v2_density_schedule
from dopey_signal_research.symbol_sector_density_scheduler_v2 import load_scheduled_symbols
from dopey_signal_research.watchlist_candidate_extractor_v2 import load_watchlist_seeds
from dopey_strategy_cohorts.strategy_id_canonicalizer import attach_cohort_ids


WATCHDOG_CAP = 75_000
MINIMUM_CAP = 30_000
SCHEDULE_PATH = RESEARCH_V2_ROOT / "research_candidate_density_schedule_v2.jsonl"
RANKINGS_PATH = RESEARCH_V2_ROOT / "research_candidate_quality_rankings_v2.jsonl"
SUMMARY_PATH = RESEARCH_V2_ROOT / "research_candidate_generator_v2_summary.json"
PROOF_PATH = RESEARCH_V2_ROOT / "research_candidate_generator_v2_proof.jsonl"

DTE_OPTIONS = [10, 14, 21, 30]
MONEYNESS_OPTIONS = ["ATM", "1pct_otm", "2pct_otm"]


def run_research_candidate_generator_v2(candidate_cap: int = WATCHDOG_CAP) -> dict[str, object]:
    RESEARCH_V2_ROOT.mkdir(parents=True, exist_ok=True)
    cap = max(min(candidate_cap, WATCHDOG_CAP), MINIMUM_CAP)
    seeds = load_watchlist_seeds()
    symbols = load_scheduled_symbols()
    rows_by_symbol = active_rows_by_symbol()
    spy_rows = rows_by_symbol.get("SPY", [])
    templates = templates_for_seeds(seeds)
    schedule = build_v2_density_schedule(symbols, seeds, cap)
    candidates: list[dict[str, object]] = []
    intent_counts: Counter[str] = Counter()
    per_symbol_count: Counter[str] = Counter()

    for symbol in symbols:
        if len(candidates) >= cap:
            break
        rows = rows_by_symbol.get(symbol, [])
        if len(rows) < 200 or is_test_symbol(symbol):
            continue
        for index in range(120, len(rows) - 20, 1):
            if len(candidates) >= cap:
                break
            if per_symbol_count[symbol] >= max(cap // max(len(symbols), 1) + 50, 400):
                continue
            features = compute_features(symbol, rows, index, spy_rows)
            for template in templates:
                if not matches_family(features, template):
                    continue
                for dte in DTE_OPTIONS:
                    for moneyness in MONEYNESS_OPTIONS:
                        candidate = build_v2_candidate(symbol, rows[index], features, template, seeds, dte, moneyness)
                        candidates.append(candidate)
                        intent_counts[str(candidate.get("trade_intent", ""))] += 1
                        per_symbol_count[symbol] += 1
                        if len(candidates) >= cap:
                            break
                    if len(candidates) >= cap:
                        break
                if len(candidates) >= cap:
                    break

    rankings = [
        record_with_hash({"artifact_type": "research_candidate_quality_ranking_v2", "discovery_family_id": family_id, "candidate_count": count, **live_safety_fields()}, "record_hash")
        for family_id, count in Counter(str(c.get("discovery_family_id", "")) for c in candidates).most_common()
    ]
    summary = {
        "artifact_type": "research_candidate_generator_v2_summary",
        "research_candidate_generator_v2_version": "dopey-public-research-candidate-generator-v2",
        "research_candidate_generator_v2_status": "research_candidates_generated_v2",
        "candidate_count": len(candidates),
        "family_count": len({c.get("discovery_family_id") for c in candidates}),
        "watchlist_seed_count": len(seeds),
        "symbol_count": len({c.get("symbol") for c in candidates}),
        "sector_count": len({c.get("sector") for c in candidates}),
        "long_call_count": intent_counts.get("long_call", 0),
        "long_put_count": intent_counts.get("long_put", 0),
        "no_trade_count": intent_counts.get("no_trade", 0),
        "public_data_only": True,
        "fixture_candidate_count": 0,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(CANDIDATES_V2_PATH, candidates)
    write_jsonl_file(SCHEDULE_PATH, [record_with_hash({**row, **live_safety_fields()}, "record_hash") for row in schedule])
    write_jsonl_file(RANKINGS_PATH, rankings[:5000])
    write_stage_proof(PROOF_PATH, "research-candidate-generator-v2", str(summary["research_candidate_generator_v2_status"]), summary)
    return {**summary, "artifact_paths": {"research_candidate_generator_v2_summary": str(SUMMARY_PATH)}}


def templates_for_seeds(seeds: list[dict[str, object]]) -> list[DiscoveryFamilyTemplate]:
    seed_ids = {str(seed.get("discovery_family_id", "")) for seed in seeds}
    matched: list[DiscoveryFamilyTemplate] = []
    for template in FAMILY_TEMPLATES:
        if template.direction == "no_trade":
            continue
        for seed_id in seed_ids:
            if template.family_id in seed_id or seed_id.startswith(template.family_id):
                matched.append(template)
                break
    if matched:
        return matched
    types = {seed_id.split("|")[0] for seed_id in seed_ids}
    return [template for template in FAMILY_TEMPLATES if template.family_type in types or template.family_id.split("|")[0] in types]


def build_v2_candidate(symbol, row, features, template, seeds, dte, moneyness) -> dict[str, object]:
    seed = next((s for s in seeds if template.family_id.startswith(str(s.get("discovery_family_id", "")).split("|")[0]) or str(s.get("discovery_family_id", "")) in template.family_id), seeds[0] if seeds else {})
    intent = "long_call" if template.direction == "bullish" else "long_put"
    discovery_id = str(seed.get("discovery_family_id", template.family_id))
    candidate_id = hashlib.sha256(f"{symbol}|{row['date']}|{discovery_id}|{dte}|{moneyness}".encode()).hexdigest()[:16]
    signal = {
        "artifact_type": "research_signal_candidate_v2",
        "candidate_id": f"rcv2-{candidate_id}",
        "watchlist_seed_id": seed.get("watchlist_seed_id", ""),
        "discovery_family_id": discovery_id,
        "research_family_id": discovery_id,
        "family_cohort_id": discovery_id,
        "cohort_id": discovery_id.split("|")[0],
        "directional_cohort_id": f"{template.direction}|{discovery_id.split('|')[0]}",
        "regime_cohort_id": str(features.get("regime", {}).get("broad_market_regime", "0")),
        "symbol_cluster_cohort_id": sector_for_symbol(symbol),
        "signal_id": f"rsv2-{candidate_id}",
        "symbol": symbol,
        "sector": sector_for_symbol(symbol),
        "timestamp": row["date"],
        "date": row["date"],
        "trade_intent": intent,
        "setup_family": template.family_type,
        "strategy_id": discovery_id,
        "feature_vector": features,
        "dte_bucket": dte,
        "moneyness_bucket": moneyness,
        "exit_policy": template.exit_policy,
        "stop_target_profile": "normal_stop",
        "hold_window": 5,
        "invalidation_level": 0.0,
        "target_price": 0.0,
        "risk_filters": ["public_data_only", "no_short_options"],
        "new_branch_from_watchlist": bool(seed.get("watchlist_seed_id")),
        "market_data_source_type": "public_live_fetch",
        "official_robinhood_market_data_allowed": True,
        "public_data_only": True,
        "live_trading_enabled": False,
    }
    return attach_cohort_ids(record_with_hash(signal, "record_hash"))
