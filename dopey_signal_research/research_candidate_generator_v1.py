"""Research candidate generator V1."""
from __future__ import annotations

import hashlib
from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_common import CANDIDATES_PATH, RESEARCH_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import (
    active_rows_by_symbol,
    is_test_symbol,
    record_with_hash,
    sector_for_symbol,
    write_jsonl_file,
)
from dopey_signal_research.discovery_signal_family_generator_v1 import matches_family
from dopey_signal_research.discovery_signal_family_models_v1 import FAMILY_TEMPLATES
from dopey_signal_research.public_feature_miner_v1 import compute_features
from dopey_signal_research.research_candidate_density_scheduler_v1 import build_density_schedule
from dopey_strategy_cohorts.strategy_id_canonicalizer import attach_cohort_ids


WATCHDOG_CAP = 50_000
MINIMUM_CAP = 20_000
SCHEDULE_PATH = RESEARCH_ROOT / "research_candidate_density_schedule_v1.jsonl"
RANKINGS_PATH = RESEARCH_ROOT / "research_candidate_quality_rankings_v1.jsonl"
SUMMARY_PATH = RESEARCH_ROOT / "research_candidate_generator_v1_summary.json"
PROOF_PATH = RESEARCH_ROOT / "research_candidate_generator_v1_proof.jsonl"


def run_research_candidate_generator_v1(candidate_cap: int = WATCHDOG_CAP) -> dict[str, object]:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    cap = max(min(candidate_cap, WATCHDOG_CAP), MINIMUM_CAP)
    rows_by_symbol = active_rows_by_symbol()
    spy_rows = rows_by_symbol.get("SPY", [])
    symbols = [symbol for symbol, rows in rows_by_symbol.items() if len(rows) >= 200 and not is_test_symbol(symbol)]
    templates = [template for template in FAMILY_TEMPLATES if template.direction != "no_trade"]
    schedule = build_density_schedule(symbols, len(templates), cap)

    candidates: list[dict[str, object]] = []
    intent_counts: Counter[str] = Counter()
    fixture_count = 0

    for symbol in symbols:
        if len(candidates) >= cap:
            break
        rows = rows_by_symbol[symbol]
        for index in range(120, len(rows) - 20, 2):
            if len(candidates) >= cap:
                break
            if is_test_symbol(symbol):
                fixture_count += 1
                continue
            features = compute_features(symbol, rows, index, spy_rows)
            for template in templates:
                if not matches_family(features, template):
                    continue
                candidate = build_candidate(symbol, rows[index], features, template)
                candidates.append(candidate)
                intent_counts[str(candidate.get("trade_intent", ""))] += 1
                if len(candidates) >= cap:
                    break

    rankings = rank_candidates(candidates)
    summary = {
        "artifact_type": "research_candidate_generator_v1_summary",
        "research_candidate_generator_version": "dopey-public-research-candidate-generator-v1",
        "research_candidate_generator_status": "research_candidates_generated",
        "candidate_count": len(candidates),
        "family_count": len({candidate.get("family_cohort_id") for candidate in candidates}),
        "symbol_count": len({candidate.get("symbol") for candidate in candidates}),
        "sector_count": len({candidate.get("sector") for candidate in candidates}),
        "long_call_count": intent_counts.get("long_call", 0),
        "long_put_count": intent_counts.get("long_put", 0),
        "no_trade_count": intent_counts.get("no_trade", 0),
        "public_data_only": True,
        "fixture_candidate_count": fixture_count,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(CANDIDATES_PATH, candidates)
    write_jsonl_file(SCHEDULE_PATH, [record_with_hash({**row, **live_safety_fields()}, "record_hash") for row in schedule])
    write_jsonl_file(RANKINGS_PATH, rankings[:5000])
    write_stage_proof(PROOF_PATH, "research-candidate-generator-v1", str(summary["research_candidate_generator_status"]), summary)
    return {**summary, "artifact_paths": {"research_candidate_generator_v1_summary": str(SUMMARY_PATH)}}


def build_candidate(symbol: str, row: dict[str, str], features: dict[str, dict[str, float]], template) -> dict[str, object]:
    intent = "long_call" if template.direction == "bullish" else "long_put"
    signal_id = hashlib.sha256(f"{symbol}|{row['date']}|{template.family_id}".encode()).hexdigest()[:16]
    signal = {
        "artifact_type": "research_signal_candidate_v1",
        "signal_id": f"rs-{signal_id}",
        "symbol": symbol,
        "sector": sector_for_symbol(symbol),
        "timestamp": row["date"],
        "date": row["date"],
        "trade_intent": intent,
        "setup_family": template.family_type,
        "strategy_id": template.family_id,
        "family_cohort_id": template.family_id,
        "setup_cohort_id": template.family_type,
        "regime_cohort_id": str(features.get("regime", {}).get("broad_market_regime", "0")),
        "symbol_cluster_cohort_id": sector_for_symbol(symbol),
        "feature_vector": features,
        "dte_bucket": template.dte,
        "moneyness_bucket": template.moneyness,
        "exit_policy": template.exit_policy,
        "stop_target_profile": "normal_stop",
        "hold_window": 5,
        "invalidation_level": 0.0,
        "target_price": 0.0,
        "risk_filters": ["public_data_only", "no_short_options"],
        "market_data_source_type": "public_live_fetch",
        "official_robinhood_market_data_allowed": True,
        "public_data_only": True,
        "live_trading_enabled": False,
    }
    return attach_cohort_ids(record_with_hash(signal, "record_hash"))


def rank_candidates(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    scores: Counter[str] = Counter()
    for candidate in candidates:
        scores[str(candidate.get("family_cohort_id", ""))] += 1
    return [
        record_with_hash({
            "artifact_type": "research_candidate_quality_ranking_v1",
            "family_cohort_id": family_id,
            "candidate_count": count,
            **live_safety_fields(),
        }, "record_hash")
        for family_id, count in scores.most_common()
    ]
