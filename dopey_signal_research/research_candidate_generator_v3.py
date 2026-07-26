"""Selective research candidate generator V3."""
from __future__ import annotations

import hashlib
from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v3_common import (
    CANDIDATES_V3_PATH,
    MINIMUM_CANDIDATE_CAP,
    RESEARCH_V3_ROOT,
    STABLE_FAMILY_CONTINUATION,
    STABLE_FAMILY_VOLUME,
    WATCHDOG_CANDIDATE_CAP,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import (
    active_rows_by_symbol,
    is_test_symbol,
    read_jsonl_file,
    record_with_hash,
    sector_for_symbol,
    write_jsonl_file,
)
from dopey_signal_research.public_feature_miner_v1 import compute_features
from dopey_signal_research.research_candidate_density_scheduler_v3 import build_v3_density_schedule
from dopey_signal_research.research_no_trade_filter_v3 import evaluate_no_trade_filters_v3, no_trade_record
from dopey_signal_research.research_universe_coverage_v2 import build_universe
from dopey_signal_research.stable_family_template_repair_v3 import (
    matches_continuation_v3,
    matches_volume_dry_up_v3,
)
from dopey_strategy_cohorts.strategy_id_canonicalizer import attach_cohort_ids


EXECUTION_RECORDS_PATH = RESEARCH_V3_ROOT / "research_mutation_execution_records_v3.jsonl"
SCHEDULE_PATH = RESEARCH_V3_ROOT / "research_candidate_density_schedule_v3.jsonl"
NO_TRADE_PATH = RESEARCH_V3_ROOT / "research_no_trade_filter_records_v3.jsonl"
RANKINGS_PATH = RESEARCH_V3_ROOT / "research_candidate_quality_rankings_v3.jsonl"
SUMMARY_PATH = RESEARCH_V3_ROOT / "research_candidate_generator_v3_summary.json"
PROOF_PATH = RESEARCH_V3_ROOT / "research_candidate_generator_v3_proof.jsonl"

DTE_OPTIONS = [10, 14, 21]
MONEYNESS_OPTIONS = ["ATM", "1pct_otm", "2pct_otm"]
FORBIDDEN_TOKENS = ("SIM", "TEST", "FIXTURE", "SYNTH")


def run_research_candidate_generator_v3(candidate_cap: int = WATCHDOG_CANDIDATE_CAP) -> dict[str, object]:
    RESEARCH_V3_ROOT.mkdir(parents=True, exist_ok=True)
    cap = max(min(candidate_cap, WATCHDOG_CANDIDATE_CAP), MINIMUM_CANDIDATE_CAP)
    universe = build_universe(target_symbols=100)
    symbols = list(universe.get("symbols", []))[: max(int(universe.get("symbol_count", 80)), 80)]
    mutations = read_jsonl_file(EXECUTION_RECORDS_PATH)
    mutation_by_family = index_mutations(mutations)
    rows_by_symbol = active_rows_by_symbol()
    spy_rows = rows_by_symbol.get("SPY", [])
    schedule = build_v3_density_schedule(symbols, cap)

    candidates: list[dict[str, object]] = []
    no_trade_records: list[dict[str, object]] = []
    intent_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    per_symbol: Counter[str] = Counter()
    per_family_symbol: dict[str, Counter[str]] = {
        STABLE_FAMILY_CONTINUATION: Counter(),
        STABLE_FAMILY_VOLUME: Counter(),
    }
    family_targets = {STABLE_FAMILY_CONTINUATION: cap // 2, STABLE_FAMILY_VOLUME: cap // 2}
    step = 2

    family_order = [STABLE_FAMILY_VOLUME, STABLE_FAMILY_CONTINUATION]
    for family_id in family_order:
        target = family_targets[family_id]
        matcher = matches_volume_dry_up_v3 if family_id == STABLE_FAMILY_VOLUME else matches_continuation_v3
        for symbol in symbols:
            if family_counts[family_id] >= target:
                break
            if is_test_symbol(symbol) or any(token in symbol.upper() for token in FORBIDDEN_TOKENS):
                continue
            rows = rows_by_symbol.get(symbol, [])
            if len(rows) < 200:
                continue
            for index in range(120, len(rows) - 20, step):
                if family_counts[family_id] >= target or len(candidates) >= cap:
                    break
                if per_symbol[symbol] >= max(cap // max(len(symbols), 1) + 80, 350):
                    continue
                features = compute_features(symbol, rows, index, spy_rows)
                if not matcher(features):
                    continue
                ok, reasons = evaluate_no_trade_filters_v3(features, family_id)
                for dte in DTE_OPTIONS:
                    for moneyness in MONEYNESS_OPTIONS:
                        candidate = build_v3_candidate(
                            symbol,
                            rows[index],
                            features,
                            family_id,
                            dte,
                            moneyness,
                            mutation_by_family.get(family_id),
                            reasons if not ok else [],
                        )
                        if not ok:
                            no_trade_records.append(no_trade_record(str(candidate.get("candidate_id", "")), reasons))
                            intent_counts["no_trade"] += 1
                            if len(no_trade_records) > 5000:
                                continue
                        candidates.append(candidate)
                        intent_counts[str(candidate.get("trade_intent", ""))] += 1
                        family_counts[family_id] += 1
                        per_symbol[symbol] += 1
                        per_family_symbol[family_id][symbol] += 1
                        if family_counts[family_id] >= target or len(candidates) >= cap:
                            break
                    if family_counts[family_id] >= target or len(candidates) >= cap:
                        break
                if family_counts[family_id] >= target or len(candidates) >= cap:
                    break

    monopolized = record_family_monopoly(family_counts, cap)
    rankings = [
        record_with_hash(
            {
                "artifact_type": "research_candidate_quality_ranking_v3",
                "discovery_family_id": family_id,
                "candidate_count": count,
                **live_safety_fields(),
            },
            "record_hash",
        )
        for family_id, count in family_counts.most_common()
    ]
    summary = {
        "artifact_type": "research_candidate_generator_v3_summary",
        "research_candidate_generator_v3_version": "dopey-public-research-candidate-generator-v3",
        "research_candidate_generator_v3_status": "research_candidates_generated_v3",
        "candidate_count": len(candidates),
        "family_count": len(family_counts),
        "stable_template_count": 2,
        "source_mutation_count": len(mutations),
        "symbol_count": len({c.get("symbol") for c in candidates}),
        "sector_count": len({c.get("sector") for c in candidates}),
        "continuation_candidate_count": family_counts.get(STABLE_FAMILY_CONTINUATION, 0),
        "volume_candidate_count": family_counts.get(STABLE_FAMILY_VOLUME, 0),
        "long_call_count": intent_counts.get("long_call", 0),
        "long_put_count": intent_counts.get("long_put", 0),
        "no_trade_count": intent_counts.get("no_trade", 0),
        "no_trade_filtered_count": len(no_trade_records),
        "family_monopoly_recorded": monopolized,
        "public_data_only": True,
        "fixture_candidate_count": 0,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(CANDIDATES_V3_PATH, candidates)
    write_jsonl_file(SCHEDULE_PATH, schedule)
    write_jsonl_file(NO_TRADE_PATH, no_trade_records[:10_000])
    write_jsonl_file(RANKINGS_PATH, rankings)
    write_stage_proof(PROOF_PATH, "research-candidate-generator-v3", str(summary["research_candidate_generator_v3_status"]), summary)
    return {**summary, "artifact_paths": {"research_candidate_generator_v3_summary": str(SUMMARY_PATH)}}


def index_mutations(mutations: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    indexed: dict[str, dict[str, object]] = {}
    for row in mutations:
        family = str(row.get("parent_family_id", ""))
        if family and family not in indexed:
            indexed[family] = row
    return indexed


def record_family_monopoly(family_counts: Counter[str], cap: int) -> bool:
    if not family_counts:
        return False
    top = family_counts.most_common(1)[0]
    return top[1] / max(cap, 1) > 0.70


def build_v3_candidate(
    symbol,
    row,
    features,
    family_id,
    dte,
    moneyness,
    mutation,
    no_trade_reasons,
) -> dict[str, object]:
    mutation_id = str(mutation.get("mutation_id", "")) if mutation else ""
    seed_id = str(mutation.get("watchlist_seed_id", "")) if mutation else ""
    intent = "no_trade" if no_trade_reasons else "long_call"
    candidate_id = hashlib.sha256(f"{symbol}|{row['date']}|{family_id}|{dte}|{moneyness}|v3".encode()).hexdigest()[:16]
    signal = {
        "artifact_type": "research_signal_candidate_v3",
        "candidate_id": f"rcv3-{candidate_id}",
        "signal_id": f"rsv3-{candidate_id}",
        "source_mutation_id": mutation_id,
        "watchlist_seed_id": seed_id,
        "discovery_family_id": family_id,
        "research_family_id": family_id,
        "stable_family_template_id": family_id,
        "setup_family": family_id.split("|")[0],
        "strategy_id": family_id,
        "cohort_id": family_id.split("|")[0],
        "directional_cohort_id": f"bullish|{family_id.split('|')[0]}",
        "regime_cohort_id": str(features.get("regime", {}).get("broad_market_regime", "0")),
        "symbol_cluster_cohort_id": sector_for_symbol(symbol),
        "symbol": symbol,
        "sector": sector_for_symbol(symbol),
        "date": row["date"],
        "timestamp": row["date"],
        "direction": "bullish",
        "trade_intent": intent,
        "DTE": dte,
        "dte_bucket": dte,
        "moneyness": moneyness,
        "moneyness_bucket": moneyness,
        "exit_policy": "trend_follow",
        "hold_window": 5,
        "stop_target_profile": "normal_stop",
        "invalidation_level": 0.0,
        "target_price": 0.0,
        "stop": "structure_invalidation",
        "target": "trend_extension",
        "risk_filters": ["public_data_only", "no_short_options"],
        "no_trade_filter_reasons": no_trade_reasons,
        "feature_vector": features,
        "market_data_source_type": "public_live_fetch",
        "official_robinhood_market_data_allowed": True,
        "public_data_only": True,
        "live_trading_enabled": False,
    }
    return attach_cohort_ids(record_with_hash(signal, "record_hash"))
