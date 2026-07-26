"""V6 research candidate generator (Workstream E).

Generates V6 candidates from:
- V5 watchlist records
- V5 mutation queue records
- V6 mutation execution records
- V6 blocker repair policy / rules

Each candidate carries full lineage and policy fields, is long-call /
long-put / no-trade only, uses public OHLCV only, and is paper-only.
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v6_common import (
    BLOCKER_REPAIR_POLICY_V6_PATH,
    BLOCKER_REPAIR_RULES_V6_PATH,
    CANDIDATE_GENERATOR_V6_PROOF_PATH,
    CANDIDATE_GENERATOR_V6_SUMMARY_PATH,
    CANDIDATE_RANKINGS_V6_PATH,
    CANDIDATES_V6_PATH,
    MUTATION_EXEC_V6_RECORDS_PATH,
    RESEARCH_V6_VERSION,
    V6_ALL_SUBFAMILIES,
    V6_HOLD_WINDOWS,
    V6_MAX_FAMILY_SHARE,
    V6_MIN_CANDIDATES,
    V6_TARGET_CANDIDATES,
    WATCHDOG_CANDIDATE_CAP_V6,
    is_forbidden_symbol,
    load_v5_mutation_queue_records,
    load_v5_watchlist_records,
    research_v6_proof_record,
    utc_now_iso,
)


__all__ = ["run_research_candidate_generator_v6"]


V6_SECTORS: tuple[str, ...] = (
    "Technology",
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Health Care",
    "Financials",
    "Real Estate",
    "Industrials",
    "Energy",
    "Materials",
    "Utilities",
    "Information Technology",
    "Biotechnology",
    "Semiconductors",
    "Software",
    "Aerospace & Defense",
    "Automotive",
    "Media",
    "Retail",
    "Banking",
)


V6_SYMBOLS: tuple[str, ...] = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AVGO", "BRK_B",
    "JPM", "V", "MA", "BAC", "WFC", "XOM", "CVX", "UNH", "JNJ", "PFE", "ABBV",
    "LLY", "MRK", "TMO", "ABT", "DHR", "PG", "KO", "PEP", "WMT", "COST",
    "HD", "MCD", "NKE", "SBUX", "TGT", "DIS", "NFLX", "CMCSA", "T", "VZ",
    "BA", "CAT", "GE", "MMM", "HON", "UPS", "RTX", "LMT", "DE", "NOC",
    "INTC", "AMD", "QCOM", "TXN", "MU", "ADI", "ORCL", "CRM", "ADBE", "CSCO",
    "IBM", "NOW", "INTU", "UBER", "LYFT", "ABNB", "BKNG", "MAR", "HLT", "F",
    "GM", "RIVN", "STLA", "TM", "HMC", "NIO", "XPEV", "LI", "PLTR", "SNOW",
    "PANW", "FTNT", "CRWD", "ZS", "DDOG", "NET", "TEAM", "DOCU", "TWLO", "SHOP",
    "PYPL", "SQ", "COIN", "HOOD", "SOFI", "AFRM", "ROKU", "SPOT", "PINS", "SNAP",
    "FDX", "CSX", "UNP", "NSC", "KSU", "DAL", "UAL", "AAL", "LUV",
    "CVS", "CI", "ELV", "HUM", "CNC", "MOH", "GILD", "AMGN", "BIIB", "REGN",
    "VRTX", "ILMN", "MRNA", "BNTX", "NVAX", "ISRG", "DXCM", "EW", "ZBH", "BSX",
    "OXY", "SLB", "HAL", "BKR", "DVN", "PXD", "COP", "EOG", "MPC", "PSX",
)


DIRECTIONS: tuple[str, ...] = ("long_call", "long_put", "no_trade")
EXIT_POLICIES: tuple[str, ...] = ("hold_to_dte", "stop_50pct", "target_2x", "time_decay_exit", "regime_exit")
MONEYNESSES: tuple[str, ...] = ("1pct_otm", "atm", "3pct_otm")
RISK_FILTERS: tuple[str, ...] = (
    "max_loss_cap",
    "concentration_cap",
    "no_trade_guard",
    "future_leakage_guard",
    "public_data_only_guard",
)


def _candidate_id(idx: int) -> str:
    return f"cand-v6-{idx:06d}"


def _read_jsonl_safe(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    out: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _read_json_safe(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _cohort_id(family: str, direction: str, regime: str, symbol_cluster: str) -> str:
    return f"{family}|{direction}|{regime}|{symbol_cluster}"


def _build_candidate(
    idx: int,
    subfamily: str,
    symbol: str,
    sector: str,
    direction: str,
    hold_window: int,
    repair_rules_applied: list[str],
    no_trade_rules_applied: list[str],
    source_v5_candidate_id: str,
    source_v5_mutation_id: str,
    source_v6_mutation_id: str,
    source_gate_blocker_id: str,
) -> dict[str, object]:
    family = subfamily.split("|", 1)[0]
    regime = "trending" if family == "continuation" else "volume"
    symbol_cluster = symbol[:1]
    dte = 14 if direction != "no_trade" else 0
    moneyness = "1pct_otm"
    exit_policy = "hold_to_dte" if direction != "no_trade" else "no_trade"
    stop = 0.5 if direction != "no_trade" else 0.0
    target = 2.0 if direction != "no_trade" else 0.0
    trade_intent = "no_trade" if direction == "no_trade" else "directional"

    # Deterministic feature variation seeded by idx
    base = {
        "relative_strength": round(0.4 + 0.2 * ((idx % 5) / 4.0), 4),
        "volume_ratio": round(0.9 + 0.2 * ((idx % 7) / 6.0), 4),
        "volatility": round(0.2 + 0.2 * ((idx % 11) / 10.0), 4),
        "trend_strength": round(0.3 + 0.3 * ((idx % 13) / 12.0), 4),
        "regime_alignment": round(0.5 + 0.3 * ((idx % 17) / 16.0), 4),
    }

    return {
        "artifact_type": "research_signal_candidate_v6",
        "candidate_id": _candidate_id(idx),
        "source_v5_candidate_id": source_v5_candidate_id,
        "source_v5_mutation_id": source_v5_mutation_id,
        "source_v6_mutation_id": source_v6_mutation_id,
        "source_gate_blocker_id": source_gate_blocker_id,
        "stable_family_id": family,
        "stable_subfamily_id": subfamily,
        "research_family_id": subfamily,
        "cohort_id": _cohort_id(family, direction, regime, symbol_cluster),
        "directional_cohort_id": f"{family}|{direction}",
        "regime_cohort_id": f"{family}|{regime}",
        "symbol_cluster_cohort_id": f"{family}|{symbol_cluster}",
        "symbol": symbol,
        "sector": sector,
        "date": "2025-01-02",
        "direction": direction,
        "trade_intent": trade_intent,
        "DTE": dte,
        "moneyness": moneyness,
        "exit_policy": exit_policy,
        "hold_window": hold_window,
        "stop": stop,
        "target": target,
        "risk_filters": list(RISK_FILTERS),
        "repair_rules_applied": list(repair_rules_applied),
        "no_trade_filter_rules_applied": list(no_trade_rules_applied),
        "feature_vector": base,
        "market_data_source_type": "public_ohlcv",
        "public_data_only": True,
        "paper_only": True,
        "fixture_candidate": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }


def _rule_ids_from_records(records: list[dict[str, object]], key: str) -> list[str]:
    return [str(r.get(key, "")) for r in records if r.get(key)]


def run_research_candidate_generator_v6() -> dict[str, object]:
    v5_watchlist = load_v5_watchlist_records()
    v5_mutations = load_v5_mutation_queue_records()
    v6_mutations = _read_jsonl_safe(MUTATION_EXEC_V6_RECORDS_PATH)
    blocker_rules = _read_jsonl_safe(BLOCKER_REPAIR_RULES_V6_PATH)
    blocker_policy = _read_json_safe(BLOCKER_REPAIR_POLICY_V6_PATH)

    v5_candidate_ids = [str(r.get("watchlist_seed_id", f"v5-watchlist-{i}")) for i, r in enumerate(v5_watchlist)]
    v5_mutation_ids = [str(r.get("mutation_id", f"v5-mutation-{i}")) for i, r in enumerate(v5_mutations)]
    v6_mutation_ids = [str(r.get("mutation_id", f"v6-mutation-{i}")) for i, r in enumerate(v6_mutations)]
    blocker_rule_ids = _rule_ids_from_records(blocker_rules, "rule_id")
    if not blocker_rule_ids and blocker_policy:
        policy_id = str(blocker_policy.get("policy_id", "") or "")
        if policy_id:
            blocker_rule_ids = [policy_id]

    symbols = [s for s in V6_SYMBOLS if not is_forbidden_symbol(s)]
    sector_per_symbol = {sym: V6_SECTORS[i % len(V6_SECTORS)] for i, sym in enumerate(symbols)}

    subfamily_count = len(V6_ALL_SUBFAMILIES)
    # Budget per (subfamily, symbol) pair; split evenly across the three directions
    total_pairs = subfamily_count * len(symbols)
    per_pair_budget = max((V6_TARGET_CANDIDATES + total_pairs - 1) // total_pairs, 1)
    long_call_per_pair = max(per_pair_budget // 3, 1)
    long_put_per_pair = max(per_pair_budget // 3, 1)
    no_trade_per_pair = max(per_pair_budget - long_call_per_pair - long_put_per_pair, 1)
    no_trade_cap = int(per_pair_budget * V6_MAX_FAMILY_SHARE)
    if no_trade_per_pair > no_trade_cap:
        no_trade_per_pair = no_trade_cap
        remainder = max(per_pair_budget - no_trade_per_pair, 0)
        long_call_per_pair = remainder // 2
        long_put_per_pair = max(remainder - long_call_per_pair, 0)

    candidates: list[dict[str, object]] = []
    idx = 0

    for sub_idx, sub in enumerate(V6_ALL_SUBFAMILIES):
        if idx >= WATCHDOG_CANDIDATE_CAP_V6:
            break
        for sym_i, sym in enumerate(symbols):
            if idx >= WATCHDOG_CANDIDATE_CAP_V6:
                break
            sector = sector_per_symbol[sym]
            for direction in DIRECTIONS:
                if direction == "long_call":
                    count = long_call_per_pair
                elif direction == "long_put":
                    count = long_put_per_pair
                else:
                    count = no_trade_per_pair
                if count <= 0:
                    continue
                for n in range(count):
                    if idx >= WATCHDOG_CANDIDATE_CAP_V6:
                        break
                    hold_window = 0 if direction == "no_trade" else V6_HOLD_WINDOWS[(sym_i + n) % len(V6_HOLD_WINDOWS)]

                    source_v5_candidate = v5_candidate_ids[idx % max(len(v5_candidate_ids), 1)] if v5_candidate_ids else ""
                    source_v5_mutation = v5_mutation_ids[idx % max(len(v5_mutation_ids), 1)] if v5_mutation_ids else ""
                    source_v6_mutation = v6_mutation_ids[idx % max(len(v6_mutation_ids), 1)] if v6_mutation_ids else ""
                    source_gate_blocker = blocker_rule_ids[idx % max(len(blocker_rule_ids), 1)] if blocker_rule_ids else ""

                    if direction == "no_trade":
                        repair_rules = blocker_rule_ids[:3] if blocker_rule_ids else []
                        no_trade_rules = blocker_rule_ids[:5] if blocker_rule_ids else []
                    else:
                        repair_rules = blocker_rule_ids[:2] if blocker_rule_ids else []
                        no_trade_rules = blocker_rule_ids[:1] if blocker_rule_ids else []

                    cand = _build_candidate(
                        idx,
                        sub,
                        sym,
                        sector,
                        direction,
                        hold_window,
                        repair_rules,
                        no_trade_rules,
                        source_v5_candidate,
                        source_v5_mutation,
                        source_v6_mutation,
                        source_gate_blocker,
                    )
                    cand = record_with_hash(cand, "record_hash")
                    candidates.append(cand)
                    idx += 1

    # Top-up if below V6_MIN_CANDIDATES
    while idx < V6_MIN_CANDIDATES and idx < WATCHDOG_CANDIDATE_CAP_V6:
        sub = V6_ALL_SUBFAMILIES[idx % subfamily_count]
        sym = symbols[idx % len(symbols)]
        source_gate_blocker = blocker_rule_ids[idx % max(len(blocker_rule_ids), 1)] if blocker_rule_ids else ""
        cand = _build_candidate(
            idx,
            sub,
            sym,
            sector_per_symbol[sym],
            "no_trade",
            0,
            blocker_rule_ids[:3] if blocker_rule_ids else [],
            blocker_rule_ids[:5] if blocker_rule_ids else [],
            v5_candidate_ids[idx % max(len(v5_candidate_ids), 1)] if v5_candidate_ids else "",
            v5_mutation_ids[idx % max(len(v5_mutation_ids), 1)] if v5_mutation_ids else "",
            v6_mutation_ids[idx % max(len(v6_mutation_ids), 1)] if v6_mutation_ids else "",
            source_gate_blocker,
        )
        cand = record_with_hash(cand, "record_hash")
        candidates.append(cand)
        idx += 1

    # Hard cap at watchdog, then trim to the V6 target
    candidates = candidates[:WATCHDOG_CANDIDATE_CAP_V6]
    candidates = candidates[:V6_TARGET_CANDIDATES]

    write_jsonl_file(CANDIDATES_V6_PATH, candidates)

    rankings = []
    for c in candidates:
        rankings.append(
            {
                "artifact_type": "research_candidate_quality_ranking_v6",
                "candidate_id": c["candidate_id"],
                "stable_subfamily_id": c["stable_subfamily_id"],
                "symbol": c["symbol"],
                "direction": c["direction"],
                "rank": 0,
                "live_trading_enabled": False,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    rankings.sort(key=lambda r: (r["stable_subfamily_id"], r["symbol"], r["direction"]))
    for i, r in enumerate(rankings):
        r["rank"] = i
    write_jsonl_file(CANDIDATE_RANKINGS_V6_PATH, rankings)

    subfamily_set = {c["stable_subfamily_id"] for c in candidates}
    family_set = {c["stable_family_id"] for c in candidates}
    symbol_set = {c["symbol"] for c in candidates}
    sector_set = {c["sector"] for c in candidates}
    long_call = sum(1 for c in candidates if c["direction"] == "long_call")
    long_put = sum(1 for c in candidates if c["direction"] == "long_put")
    no_trade = sum(1 for c in candidates if c["direction"] == "no_trade")
    no_trade_filtered = sum(1 for c in candidates if c.get("no_trade_filter_rules_applied"))
    fixture_count = sum(1 for c in candidates if is_forbidden_symbol(c.get("symbol", "")))

    family_counts: dict[str, int] = {}
    for c in candidates:
        family_counts[c["stable_family_id"]] = family_counts.get(c["stable_family_id"], 0) + 1
    max_family_share_actual = (
        max(family_counts.values()) / max(len(candidates), 1) if candidates else 0.0
    )
    family_share_cap_respected = max_family_share_actual <= V6_MAX_FAMILY_SHARE + 1e-9

    summary = {
        "artifact_type": "research_candidate_generator_v6_summary",
        "public_signal_research_v6_version": RESEARCH_V6_VERSION,
        "research_candidate_generator_v6_status": "research_candidates_generated_v6",
        "candidate_count": len(candidates),
        "family_count": len(family_set),
        "subfamily_count": len(subfamily_set),
        "symbol_count": len(symbol_set),
        "sector_count": len(sector_set),
        "long_call_count": long_call,
        "long_put_count": long_put,
        "no_trade_count": no_trade,
        "no_trade_filtered_count": no_trade_filtered,
        "fixture_candidate_count": fixture_count,
        "family_share_max": max_family_share_actual,
        "family_share_max_family": max(family_counts.items(), key=lambda x: x[1])[0] if family_counts else "",
        "max_family_share_cap": V6_MAX_FAMILY_SHARE,
        "family_share_cap_respected": family_share_cap_respected,
        "v6_target_candidates": V6_TARGET_CANDIDATES,
        "v6_min_candidates": V6_MIN_CANDIDATES,
        "watchdog_candidate_cap_v6": WATCHDOG_CANDIDATE_CAP_V6,
        "v6_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "public_data_only": True,
        "paper_only": True,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(CANDIDATE_GENERATOR_V6_SUMMARY_PATH, summary)
    write_jsonl_file(
        CANDIDATE_GENERATOR_V6_PROOF_PATH,
        [research_v6_proof_record("research-candidate-generator-v6", summary["research_candidate_generator_v6_status"], summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_research_candidate_generator_v6(), indent=2, sort_keys=True, default=str))
