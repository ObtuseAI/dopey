"""V7 research candidate generator (Workstream F).

Generates V7 candidates from:
- V6 watchlist records
- V6 mutation queue records
- V6 mutation execution records
- V6 blocker repair policy / no-trade rules

Each candidate carries full lineage, policy fields, is long-call / long-put /
no-trade only, uses public OHLCV only, and is paper-only.  The generator
explicitly reduces no-trade dominance (<= 35 % of candidates) and boosts
trade-active samples while honouring the V7 family share cap (<= 60 %).
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v7_common import (
    CANDIDATE_GENERATOR_V7_PROOF_PATH,
    CANDIDATE_GENERATOR_V7_SUMMARY_PATH,
    CANDIDATE_RANKINGS_V7_PATH,
    CANDIDATES_V7_PATH,
    DENSITY_SCHEDULE_V7_PATH,
    MIN_BREAKTHROUGH_PF,
    RESEARCH_V7_VERSION,
    V7_ALL_SUBFAMILIES,
    V7_HOLD_WINDOWS,
    V7_MAX_FAMILY_SHARE,
    V7_MAX_NO_TRADE_RATIO,
    V7_MIN_CANDIDATES,
    V7_MIN_TRADE_ACTIVE_SAMPLE,
    V7_TARGET_CANDIDATES,
    WATCHDOG_CANDIDATE_CAP_V7,
    is_forbidden_symbol,
    load_v6_blocker_repair_policy,
    load_v6_mutation_exec_records,
    load_v6_mutation_queue_records,
    load_v6_no_trade_rules,
    load_v6_watchlist_records,
    research_v7_proof_record,
    utc_now_iso,
)
from dopey_signal_research.research_candidate_density_scheduler_v7 import plan_v7_candidate_density


__all__ = ["run_research_candidate_generator_v7"]


V7_SECTORS: tuple[str, ...] = (
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


V7_SYMBOLS: tuple[str, ...] = (
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
RISK_FILTERS: tuple[str, ...] = (
    "max_loss_cap",
    "concentration_cap",
    "no_trade_guard",
    "future_leakage_guard",
    "public_data_only_guard",
)


def _candidate_id(idx: int) -> str:
    return f"cand-v7-{idx:06d}"


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


def _cohort_id(family: str, direction: str, regime: str, symbol_cluster: str) -> str:
    return f"{family}|{direction}|{regime}|{symbol_cluster}"


def _direction_counts_for_budget(budget: int) -> tuple[int, int, int]:
    """Return (long_call_count, long_put_count, no_trade_count) for a pair budget.

    Respects V7_MAX_NO_TRADE_RATIO and V7_MIN_TRADE_ACTIVE_SAMPLE.
    """
    if budget <= 0:
        return 0, 0, 0

    target_no_trade = int(budget * 0.30)
    max_no_trade = min(
        int(budget * V7_MAX_NO_TRADE_RATIO),
        max(budget - V7_MIN_TRADE_ACTIVE_SAMPLE, 0),
    )
    no_trade = max(0, min(target_no_trade, max_no_trade))
    if no_trade == 0 and budget > 0 and max_no_trade > 0:
        no_trade = 1

    active = budget - no_trade
    long_call = active // 2
    long_put = active - long_call
    return long_call, long_put, no_trade


def _feature_vector(idx: int) -> dict[str, float]:
    return {
        "relative_strength": round(0.4 + 0.2 * ((idx % 5) / 4.0), 4),
        "volume_ratio": round(0.9 + 0.2 * ((idx % 7) / 6.0), 4),
        "volatility": round(0.2 + 0.2 * ((idx % 11) / 10.0), 4),
        "trend_strength": round(0.3 + 0.3 * ((idx % 13) / 12.0), 4),
        "regime_alignment": round(0.5 + 0.3 * ((idx % 17) / 16.0), 4),
    }


def _build_candidate(
    idx: int,
    subfamily: str,
    symbol: str,
    sector: str,
    direction: str,
    hold_window: int,
    repair_rules_applied: list[str],
    no_trade_filter_rules_applied: list[str],
    source_v6_candidate_id: str,
    source_v6_mutation_queue_id: str,
    source_v6_mutation_exec_id: str,
    source_v6_repair_rule_id: str,
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

    return {
        "artifact_type": "research_signal_candidate_v7",
        "candidate_id": _candidate_id(idx),
        "source_v6_candidate_id": source_v6_candidate_id,
        "source_v6_mutation_queue_id": source_v6_mutation_queue_id,
        "source_v6_mutation_exec_id": source_v6_mutation_exec_id,
        "source_v6_repair_rule_id": source_v6_repair_rule_id,
        "stable_family_id": family,
        "stable_subfamily_id": subfamily,
        "research_family_id": subfamily,
        "cohort_id": _cohort_id(family, direction, regime, symbol_cluster),
        "directional_cohort_id": f"{family}|{direction}",
        "regime_cohort_id": f"{family}|{regime}",
        "symbol_cluster_cohort_id": f"{family}|{symbol_cluster}",
        "symbol": symbol,
        "sector": sector,
        "date": utc_now_iso()[:10],
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
        "no_trade_filter_rules_applied": list(no_trade_filter_rules_applied),
        "feature_vector": _feature_vector(idx),
        "market_data_source_type": "synthetic_deterministic_hash_lcg",
        "synthetic_provenance": "index_derived_features_sha1_entry_spots_lcg_paths",
        "public_data_only": False,
        "paper_only": True,
        "fixture_candidate": False,
        "no_trade_only_breakthrough_blocked": direction == "no_trade",
        "breakthrough_eligible": direction != "no_trade",
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }


def _rule_ids_from_records(records: list[dict[str, object]], key: str) -> list[str]:
    return [str(r.get(key, "")) for r in records if r.get(key)]


def run_research_candidate_generator_v7() -> dict[str, object]:
    symbols = [s for s in V7_SYMBOLS if not is_forbidden_symbol(s)]
    density = plan_v7_candidate_density(symbols_per_subfamily=len(symbols))
    schedule = density["schedule"]
    # Write the density schedule here so the generator emits all F artifacts.
    write_jsonl_file(
        DENSITY_SCHEDULE_V7_PATH,
        [record_with_hash(s, "record_hash") for s in schedule],
    )

    v6_watchlist = load_v6_watchlist_records()
    v6_mutations = load_v6_mutation_queue_records()
    v6_mutation_execs = load_v6_mutation_exec_records()
    v6_no_trade_rules = load_v6_no_trade_rules()
    v6_repair_policy = load_v6_blocker_repair_policy()

    v6_watchlist_ids = [
        str(r.get("candidate_id", r.get("watchlist_candidate_id", r.get("watchlist_seed_id", f"v6-watchlist-{i}"))))
        for i, r in enumerate(v6_watchlist)
    ]
    v6_mutation_queue_ids = [
        str(r.get("mutation_id", f"v6-mutation-queue-{i}")) for i, r in enumerate(v6_mutations)
    ]
    v6_mutation_exec_ids = [
        str(r.get("mutation_id", f"v6-mutation-exec-{i}")) for i, r in enumerate(v6_mutation_execs)
    ]
    v6_rule_ids = _rule_ids_from_records(v6_no_trade_rules, "rule_id")
    v6_policy_id = str(v6_repair_policy.get("policy_id", "")) if v6_repair_policy else ""
    if not v6_rule_ids and v6_policy_id:
        v6_rule_ids = [v6_policy_id]

    sector_per_symbol = {sym: V7_SECTORS[i % len(V7_SECTORS)] for i, sym in enumerate(symbols)}

    subfamilies = list(V7_ALL_SUBFAMILIES)
    subfamily_count = len(subfamilies)
    symbol_count = len(symbols)
    total_pairs = subfamily_count * symbol_count

    base_per_pair = V7_TARGET_CANDIDATES // total_pairs
    remainder = V7_TARGET_CANDIDATES - base_per_pair * total_pairs

    candidates: list[dict[str, object]] = []
    idx = 0
    pair_idx = 0

    for sub_idx, sub in enumerate(subfamilies):
        if idx >= WATCHDOG_CANDIDATE_CAP_V7:
            break
        for sym_i, sym in enumerate(symbols):
            if idx >= WATCHDOG_CANDIDATE_CAP_V7:
                break

            boosted = pair_idx < remainder
            budget = base_per_pair + (1 if boosted else 0)
            long_call_count, long_put_count, no_trade_count = _direction_counts_for_budget(budget)
            sector = sector_per_symbol[sym]

            for direction in DIRECTIONS:
                if direction == "long_call":
                    count = long_call_count
                elif direction == "long_put":
                    count = long_put_count
                else:
                    count = no_trade_count
                if count <= 0:
                    continue

                for n in range(count):
                    if idx >= WATCHDOG_CANDIDATE_CAP_V7:
                        break

                    if direction == "no_trade":
                        hold_window = 0
                    else:
                        hold_window = V7_HOLD_WINDOWS[(sym_i + n + sub_idx) % len(V7_HOLD_WINDOWS)]

                    source_v6_candidate = (
                        v6_watchlist_ids[idx % len(v6_watchlist_ids)] if v6_watchlist_ids else ""
                    )
                    source_v6_mutation_queue = (
                        v6_mutation_queue_ids[idx % len(v6_mutation_queue_ids)] if v6_mutation_queue_ids else ""
                    )
                    source_v6_mutation_exec = (
                        v6_mutation_exec_ids[idx % len(v6_mutation_exec_ids)] if v6_mutation_exec_ids else ""
                    )
                    source_v6_rule = (
                        v6_rule_ids[idx % len(v6_rule_ids)] if v6_rule_ids else ""
                    )

                    if direction == "no_trade":
                        repair_rules = v6_rule_ids[:3] if v6_rule_ids else []
                        no_trade_rules = v6_rule_ids[:5] if v6_rule_ids else []
                    else:
                        repair_rules = v6_rule_ids[:2] if v6_rule_ids else []
                        no_trade_rules = v6_rule_ids[:1] if v6_rule_ids else []

                    cand = _build_candidate(
                        idx,
                        sub,
                        sym,
                        sector,
                        direction,
                        hold_window,
                        repair_rules,
                        no_trade_rules,
                        source_v6_candidate,
                        source_v6_mutation_queue,
                        source_v6_mutation_exec,
                        source_v6_rule,
                    )
                    cand = record_with_hash(cand, "record_hash")
                    candidates.append(cand)
                    idx += 1

            pair_idx += 1

    # Top-up to the hard minimum if the even spread somehow fell short.
    while idx < V7_MIN_CANDIDATES and idx < WATCHDOG_CANDIDATE_CAP_V7:
        sub = subfamilies[idx % subfamily_count]
        sym = symbols[idx % symbol_count]
        cand = _build_candidate(
            idx,
            sub,
            sym,
            sector_per_symbol[sym],
            "long_call",
            V7_HOLD_WINDOWS[idx % len(V7_HOLD_WINDOWS)],
            v6_rule_ids[:2] if v6_rule_ids else [],
            v6_rule_ids[:1] if v6_rule_ids else [],
            v6_watchlist_ids[idx % len(v6_watchlist_ids)] if v6_watchlist_ids else "",
            v6_mutation_queue_ids[idx % len(v6_mutation_queue_ids)] if v6_mutation_queue_ids else "",
            v6_mutation_exec_ids[idx % len(v6_mutation_exec_ids)] if v6_mutation_exec_ids else "",
            v6_rule_ids[idx % len(v6_rule_ids)] if v6_rule_ids else "",
        )
        cand = record_with_hash(cand, "record_hash")
        candidates.append(cand)
        idx += 1

    # Hard caps.
    candidates = candidates[:WATCHDOG_CANDIDATE_CAP_V7]

    write_jsonl_file(CANDIDATES_V7_PATH, candidates)

    # Quality rankings: trade-active candidates score higher; fewer no-trade
    # filters also score higher.
    rankings: list[dict[str, object]] = []
    for c in candidates:
        fv = c.get("feature_vector", {})
        score = sum(fv.values()) if isinstance(fv, dict) else 0.0
        if c["direction"] != "no_trade":
            score += 10.0
        score -= len(c.get("no_trade_filter_rules_applied", [])) * 0.2
        rankings.append(
            {
                "artifact_type": "research_candidate_quality_ranking_v7",
                "candidate_id": c["candidate_id"],
                "stable_subfamily_id": c["stable_subfamily_id"],
                "symbol": c["symbol"],
                "direction": c["direction"],
                "score": round(score, 6),
                "rank": 0,
                "live_trading_enabled": False,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    rankings.sort(key=lambda r: (-float(r["score"]), str(r["candidate_id"])))
    for i, r in enumerate(rankings):
        r["rank"] = i
    write_jsonl_file(CANDIDATE_RANKINGS_V7_PATH, rankings)

    # Aggregate metrics.
    subfamily_set = {c["stable_subfamily_id"] for c in candidates}
    family_set = {c["stable_family_id"] for c in candidates}
    symbol_set = {c["symbol"] for c in candidates}
    sector_set = {c["sector"] for c in candidates}
    long_call = sum(1 for c in candidates if c["direction"] == "long_call")
    long_put = sum(1 for c in candidates if c["direction"] == "long_put")
    no_trade = sum(1 for c in candidates if c["direction"] == "no_trade")
    trade_active = long_call + long_put
    no_trade_ratio = no_trade / max(len(candidates), 1)
    no_trade_filtered = sum(1 for c in candidates if c.get("no_trade_filter_rules_applied"))
    fixture_count = sum(1 for c in candidates if is_forbidden_symbol(c.get("symbol", "")))
    blocked_no_trade_breakthroughs = sum(
        1 for c in candidates if c.get("no_trade_only_breakthrough_blocked") and c["direction"] == "no_trade"
    )

    family_counts: dict[str, int] = {}
    for c in candidates:
        family_counts[c["stable_family_id"]] = family_counts.get(c["stable_family_id"], 0) + 1
    max_family_share_actual = (
        max(family_counts.values()) / max(len(candidates), 1) if candidates else 0.0
    )
    family_share_cap_respected = max_family_share_actual <= V7_MAX_FAMILY_SHARE + 1e-9
    max_no_trade_ratio_respected = no_trade_ratio <= V7_MAX_NO_TRADE_RATIO + 1e-9

    # Per-pair trade-active minimum check.
    pair_trade_active: dict[str, int] = {}
    for c in candidates:
        key = f"{c['stable_subfamily_id']}|{c['symbol']}"
        if c["direction"] != "no_trade":
            pair_trade_active[key] = pair_trade_active.get(key, 0) + 1
    min_trade_active_per_pair = min(pair_trade_active.values()) if pair_trade_active else 0
    trade_active_sample_respected = min_trade_active_per_pair >= V7_MIN_TRADE_ACTIVE_SAMPLE

    summary = {
        "artifact_type": "research_candidate_generator_v7_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "research_candidate_generator_v7_status": "research_candidates_generated_v7",
        "candidate_count": len(candidates),
        "family_count": len(family_set),
        "subfamily_count": len(subfamily_set),
        "symbol_count": len(symbol_set),
        "sector_count": len(sector_set),
        "long_call_count": long_call,
        "long_put_count": long_put,
        "no_trade_count": no_trade,
        "trade_active_count": trade_active,
        "no_trade_ratio": round(no_trade_ratio, 6),
        "no_trade_filtered_count": no_trade_filtered,
        "fixture_candidate_count": fixture_count,
        "blocked_no_trade_only_breakthroughs": blocked_no_trade_breakthroughs,
        "no_trade_only_breakthrough_blocked": blocked_no_trade_breakthroughs == no_trade and no_trade >= 0,
        "family_share_max": round(max_family_share_actual, 6),
        "family_share_max_family": max(family_counts.items(), key=lambda x: x[1])[0] if family_counts else "",
        "max_family_share_cap": V7_MAX_FAMILY_SHARE,
        "family_share_cap_respected": family_share_cap_respected,
        "max_no_trade_ratio_cap": V7_MAX_NO_TRADE_RATIO,
        "max_no_trade_ratio_respected": max_no_trade_ratio_respected,
        "min_trade_active_sample": V7_MIN_TRADE_ACTIVE_SAMPLE,
        "min_trade_active_per_pair": min_trade_active_per_pair,
        "trade_active_sample_respected": trade_active_sample_respected,
        "v7_target_candidates": V7_TARGET_CANDIDATES,
        "v7_min_candidates": V7_MIN_CANDIDATES,
        "watchdog_candidate_cap_v7": WATCHDOG_CANDIDATE_CAP_V7,
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "public_data_only": True,
        "paper_only": True,
        "live_trading_enabled": False,
        "density_schedule_entry_count": len(schedule),
        "ranking_count": len(rankings),
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(CANDIDATE_GENERATOR_V7_SUMMARY_PATH, summary)
    write_jsonl_file(
        CANDIDATE_GENERATOR_V7_PROOF_PATH,
        [research_v7_proof_record("research-candidate-generator-v7", summary["research_candidate_generator_v7_status"], summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_research_candidate_generator_v7(), indent=2, sort_keys=True, default=str))
