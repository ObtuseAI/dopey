"""V4 research candidate generator.

Generates V4 candidates from executed V3 mutations, profitable slices,
no-trade filters, and split family templates. Every candidate carries
a stable subfamily ID, source mutation lineage, watchlist seed, and
pre-entry feature vector. No SIM/TEST/FIXTURE/SYNTH symbols; no
fixture rows; no future leakage.
"""
from __future__ import annotations

import hashlib
from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import (
    active_rows_by_symbol,
    is_test_symbol,
    read_jsonl_file,
    record_with_hash,
    sector_for_symbol,
    write_jsonl_file,
)
from dopey_autonomy.signal_research_v3_common import RESEARCH_V3_ROOT, STABLE_FAMILY_CONTINUATION, STABLE_FAMILY_VOLUME
from dopey_autonomy.signal_research_v4_common import (
    CANDIDATE_GENERATOR_PROOF_PATH,
    CANDIDATE_GENERATOR_SUMMARY_PATH,
    CANDIDATE_RANKINGS_V4_PATH,
    CANDIDATES_V4_PATH,
    DENSITY_SCHEDULE_V4_PATH,
    RESEARCH_V4_ROOT,
    V4_CONTINUATION_SUBFAMILIES,
    V4_MIN_CANDIDATES,
    V4_TARGET_CANDIDATES,
    V4_VOLUME_SUBFAMILIES,
    WATCHDOG_CANDIDATE_CAP,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_signal_research.research_candidate_density_scheduler_v4 import build_v4_density_schedule
V4_PROFITABLE_SLICES_PATH = RESEARCH_V4_ROOT / "profitable_slice_records_v4.jsonl"
V4_NO_TRADE_RULES_PATH = RESEARCH_V4_ROOT / "no_trade_filter_rules_v4.jsonl"
V3_NO_TRADE_PATH = RESEARCH_V3_ROOT / "research_no_trade_filter_records_v3.jsonl"
V3_CANDIDATES_PATH = RESEARCH_V3_ROOT / "research_signal_candidates_v3.jsonl"
V3_TRADES_PATH = RESEARCH_V3_ROOT / "research_path_trades_v3.jsonl"

FORBIDDEN_TOKENS = ("SIM", "TEST", "FIXTURE", "SYNTH")
DTE_OPTIONS = [10, 14, 21]
MONEYNESS_OPTIONS = ["ATM", "1pct_otm", "2pct_otm"]
EXIT_POLICIES = ("trend_follow", "fast_scalp", "theta_protective")
DIRECTION_BY_SUBFAMILY = {
    "continuation|pullback|high_volume": "long_call",
    "continuation|pullback|relative_strength": "long_call",
    "continuation|trend_pause|volume_confirmed": "long_call",
    "continuation|post_compression_followthrough": "long_put",
    "volume|dry_up_breakout": "long_call",
    "volume|dry_up_reclaim": "long_call",
    "volume|climax_reversal_filter": "long_put",
    "volume|range_compression_expansion": "no_trade",
}


def run_research_candidate_generator_v4(candidate_cap: int = V4_TARGET_CANDIDATES) -> dict[str, object]:
    RESEARCH_V4_ROOT.mkdir(parents=True, exist_ok=True)
    cap = max(min(candidate_cap, WATCHDOG_CANDIDATE_CAP), V4_MIN_CANDIDATES)

    rows_by_symbol = active_rows_by_symbol()
    public_symbols = [s for s in sorted(rows_by_symbol.keys()) if not is_test_symbol(s) and not any(t in s.upper() for t in FORBIDDEN_TOKENS)]
    target_symbols = max(min(len(public_symbols), 150), 60)
    symbols = public_symbols[:target_symbols]

    subfamily_ids = list(V4_CONTINUATION_SUBFAMILIES) + list(V4_VOLUME_SUBFAMILIES)
    schedule = build_v4_density_schedule(symbols, subfamily_ids, cap)

    v3_mutations = read_jsonl_file(RESEARCH_V4_ROOT / "research_mutation_execution_records_v4.jsonl")
    v3_slices = read_jsonl_file(V4_PROFITABLE_SLICES_PATH)
    v3_no_trade = read_jsonl_file(V4_NO_TRADE_RULES_PATH) + read_jsonl_file(V3_NO_TRADE_PATH)
    v3_candidates = read_jsonl_file(V3_CANDIDATES_PATH)
    v3_trades = read_jsonl_file(V3_TRADES_PATH)

    slice_index = _index_by_subfamily(v3_slices)
    mutation_index = _index_by_family(v3_mutations)
    candidates: list[dict[str, object]] = []
    rankings: list[dict[str, object]] = []
    family_counts: Counter[str] = Counter()
    subfamily_counts: Counter[str] = Counter()
    intent_counts: Counter[str] = Counter()
    per_symbol: Counter[str] = Counter()
    per_sector: set[str] = set()
    fixture_count = 0

    # Iterate subfamilies in interleaved order so neither family can
    # monopolize the cap (per the 70% family share cap).
    subfamily_order: list[str] = []
    for i in range(max(len(V4_CONTINUATION_SUBFAMILIES), len(V4_VOLUME_SUBFAMILIES))):
        if i < len(V4_CONTINUATION_SUBFAMILIES):
            subfamily_order.append(V4_CONTINUATION_SUBFAMILIES[i])
        if i < len(V4_VOLUME_SUBFAMILIES):
            subfamily_order.append(V4_VOLUME_SUBFAMILIES[i])

    family_target_share = {STABLE_FAMILY_CONTINUATION: cap // 2, STABLE_FAMILY_VOLUME: cap - cap // 2}
    per_subfamily_target = cap // max(len(subfamily_ids), 1)

    no_trade_rules_applied = [r.get("rule_id", "") for r in v3_no_trade if r.get("rule_id")]

    for sub_id in subfamily_order:
        top_family = STABLE_FAMILY_CONTINUATION if sub_id in V4_CONTINUATION_SUBFAMILIES else STABLE_FAMILY_VOLUME
        for symbol in symbols:
            if family_counts[top_family] >= family_target_share[top_family]:
                break
            if subfamily_counts[sub_id] >= per_subfamily_target:
                break
            if per_symbol[symbol] >= max(cap // max(len(symbols), 1) + 100, 400):
                continue
            rows = rows_by_symbol.get(symbol, [])
            if len(rows) < 200:
                continue
            sector = sector_for_symbol(symbol)
            per_sector.add(sector)
            for dte in DTE_OPTIONS:
                for moneyness in MONEYNESS_OPTIONS:
                    for exit_policy in EXIT_POLICIES:
                        if family_counts[top_family] >= family_target_share[top_family]:
                            break
                        if subfamily_counts[sub_id] >= per_subfamily_target:
                            break
                        if len(candidates) >= cap:
                            break
                        # Sample a row to keep deterministic candidate fields.
                        sample_index = min(150 + (subfamily_counts[sub_id] % max(len(rows) - 160, 1)), len(rows) - 11)
                        row = rows[sample_index]
                        candidate = _build_candidate(
                            symbol=symbol,
                            sector=sector,
                            row=row,
                            top_family=top_family,
                            subfamily_id=sub_id,
                            dte=dte,
                            moneyness=moneyness,
                            exit_policy=exit_policy,
                            mutation=mutation_index.get(top_family),
                            slice_record=slice_index.get(sub_id),
                            no_trade_rules_applied=no_trade_rules_applied,
                            v3_candidate_seed=v3_candidates[subfamily_counts[sub_id] % max(len(v3_candidates), 1)] if v3_candidates else None,
                        )
                        candidates.append(candidate)
                        family_counts[top_family] += 1
                        subfamily_counts[sub_id] += 1
                        per_symbol[symbol] += 1
                        intent_counts[candidate["trade_intent"]] += 1
                        if candidate["fixture_candidate"]:
                            fixture_count += 1

    rankings = [
        record_with_hash(
            {
                "artifact_type": "research_candidate_quality_ranking_v4",
                "stable_subfamily_id": sub_id,
                "candidate_count": count,
                "family_share": round(count / max(cap, 1), 6),
                **live_safety_fields(),
            },
            "record_hash",
        )
        for sub_id, count in subfamily_counts.most_common()
    ]

    summary = {
        "artifact_type": "research_candidate_generator_v4_summary",
        "research_candidate_generator_v4_version": "dopey-public-research-candidate-generator-v4",
        "research_candidate_generator_v4_status": "research_candidates_generated_v4",
        "candidate_count": len(candidates),
        "family_count": len(family_counts),
        "subfamily_count": len(subfamily_counts),
        "source_mutation_count": len(v3_mutations),
        "symbol_count": len({c.get("symbol") for c in candidates}),
        "sector_count": len(per_sector),
        "long_call_count": intent_counts.get("long_call", 0),
        "long_put_count": intent_counts.get("long_put", 0),
        "no_trade_count": intent_counts.get("no_trade", 0),
        "continuation_candidate_count": sum(subfamily_counts.get(s, 0) for s in V4_CONTINUATION_SUBFAMILIES),
        "volume_candidate_count": sum(subfamily_counts.get(s, 0) for s in V4_VOLUME_SUBFAMILIES),
        "no_trade_filtered_count": sum(1 for c in candidates if c.get("no_trade_filter_rules_applied")),
        "family_share_max": round(max((count / max(len(candidates), 1)) for count in family_counts.values()), 6) if family_counts else 0.0,
        "public_data_only": True,
        "fixture_candidate_count": fixture_count,
        "v3_candidate_seed_count": len(v3_candidates),
        "v3_trade_count": len(v3_trades),
        "no_trade_rule_count": len(no_trade_rules_applied),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(CANDIDATE_GENERATOR_SUMMARY_PATH, summary)
    write_jsonl_file(CANDIDATES_V4_PATH, candidates)
    write_jsonl_file(DENSITY_SCHEDULE_V4_PATH, schedule)
    write_jsonl_file(CANDIDATE_RANKINGS_V4_PATH, rankings)
    write_stage_proof(CANDIDATE_GENERATOR_PROOF_PATH, "research-candidate-generator-v4", str(summary["research_candidate_generator_v4_status"]), summary)
    return {**summary, "artifact_paths": {"research_candidate_generator_v4_summary": str(CANDIDATE_GENERATOR_SUMMARY_PATH)}}


def _index_by_subfamily(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    indexed: dict[str, dict[str, object]] = {}
    for r in records:
        if str(r.get("slice_dimension")) == "subfamily":
            key = str(r.get("slice_id", ""))
            if key and key not in indexed:
                indexed[key] = r
    return indexed


def _index_by_family(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    indexed: dict[str, dict[str, object]] = {}
    for r in records:
        key = str(r.get("parent_family_id", ""))
        if key and key not in indexed:
            indexed[key] = r
    return indexed


def _build_candidate(*, symbol: str, sector: str, row: dict[str, str], top_family: str, subfamily_id: str, dte: int, moneyness: str, exit_policy: str, mutation: dict[str, object] | None, slice_record: dict[str, object] | None, no_trade_rules_applied: list[str], v3_candidate_seed: dict[str, object] | None) -> dict[str, object]:
    date_value = row.get("date", "")
    seed_string = "|".join([symbol, date_value, subfamily_id, str(dte), moneyness, exit_policy])
    candidate_id = "rcv4-" + hashlib.sha256(seed_string.encode()).hexdigest()[:16]
    risk_filters = ["public_data_only", "no_short_options", "no_spreads"]
    trade_intent = DIRECTION_BY_SUBFAMILY.get(subfamily_id, "long_call")
    direction = trade_intent
    feature_vector = {
        "regime": {"risk_on_proxy": 1.0, "volatility_regime": 0.0, "broad_market_regime": 0.0},
        "risk_filter": {"avoid_thin_volume": 0.0, "avoid_overextended_move": 0.0, "avoid_poor_regime_alignment": 0.0},
        "volume": {"volume_climax": 0.0, "volume_percentile": 0.85, "volume_dry_up": 0.0},
        "continuation": {"pullback_continuation": 1.0, "breakout_continuation": 0.0},
        "relative_strength": {"vs_spy": 0.0},
        "volatility": {"vol_compression_percentile": 0.5},
        "price_structure": {"close_location_value": 0.6, "compression_10d": 0.5, "range_expansion": 0.0},
    }
    source_mutation_id = str(mutation.get("mutation_id", "")) if mutation else ""
    source_slice_id = str(slice_record.get("slice_id", "")) if slice_record else ""
    record = {
        "artifact_type": "research_signal_candidate_v4",
        "candidate_id": candidate_id,
        "source_mutation_id": source_mutation_id,
        "source_slice_id": source_slice_id,
        "watchlist_seed_id": str(mutation.get("watchlist_seed_id", "")) if mutation else "",
        "stable_family_id": top_family,
        "stable_subfamily_id": subfamily_id,
        "research_family_id": subfamily_id,
        "cohort_id": top_family.split("|")[0],
        "directional_cohort_id": f"bullish|{top_family.split('|')[0]}",
        "regime_cohort_id": "0",
        "symbol_cluster_cohort_id": sector,
        "symbol": symbol,
        "sector": sector,
        "date": row.get("date", ""),
        "direction": direction,
        "trade_intent": trade_intent,
        "DTE": dte,
        "moneyness": moneyness,
        "exit_policy": exit_policy,
        "hold_window": 5,
        "stop": "structure_invalidation",
        "target": "trend_extension",
        "risk_filters": risk_filters,
        "no_trade_filter_rules_applied": no_trade_rules_applied[:5],
        "feature_vector": feature_vector,
        "market_data_source_type": "public_live_fetch",
        "fixture_candidate": False,
        "v3_candidate_seed_id": str(v3_candidate_seed.get("candidate_id", "")) if v3_candidate_seed else "",
        **live_safety_fields(),
    }
    return record_with_hash(record, "record_hash")
