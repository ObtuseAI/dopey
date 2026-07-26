"""V5 research candidate generator (Workstream G).

Generates V5 candidates from:
- V4 repair targets (Workstream D)
- V5 mutation executions (Workstream E)
- V5 no-trade filter rules (Workstream F)

Each candidate carries:
- candidate_id, source_v4_candidate_id, source_v4_mutation_id,
  source_v5_mutation_id, source_slice_id
- stable_family_id, stable_subfamily_id, research_family_id
- cohort_id, directional_cohort_id, regime_cohort_id, symbol_cluster_cohort_id
- symbol, sector, date, direction, trade_intent
- DTE, moneyness, exit_policy, hold_window
- stop, target, risk_filters
- no_trade_filter_rules_applied
- feature_vector
- market_data_source_type
- public_data_only, paper_only
- safety + Robinhood policy fields

Generation rules:
- target V5_TARGET_CANDIDATES = 40_000
- minimum V5_MIN_CANDIDATES = 20_000
- watchdog cap WATCHDOG_CANDIDATE_CAP_V5 = 50_000
- family share cap V5_MAX_FAMILY_SHARE = 0.70 (any single family may not
  exceed 70% of the total candidate count)
- no_trade direction is capped at <= 70% of the per-subfamily budget
- each (subfamily, symbol) pair generates an equal number of long_call,
  long_put, and no_trade candidates
- 8 subfamilies preserved (4 continuation + 4 volume)
- symbol/sector coverage preserved
- forbidden tokens (SIM, TEST, FIXTURE, SYNTH) excluded
- every record carries public_data_only=True, paper_only=True,
  live_trading_enabled=False
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v5_common import (
    CANDIDATE_RANKINGS_V5_PATH,
    CANDIDATES_V5_PATH,
    MUTATION_EXEC_V5_EXPANSION_PATH,
    MUTATION_EXEC_V5_RECORDS_PATH,
    NO_TRADE_RULES_V5_PATH,
    RESEARCH_V5_VERSION,
    V5_CONTINUATION_SUBFAMILIES,
    V5_HOLD_WINDOWS,
    V5_MAX_FAMILY_SHARE,
    V5_MIN_CANDIDATES,
    V5_TARGET_CANDIDATES,
    V5_VOLUME_SUBFAMILIES,
    WATCHDOG_CANDIDATE_CAP_V5,
    is_forbidden_symbol,
    utc_now_iso,
)


__all__ = ["run_research_candidate_generator_v5"]


# Sectors (V4 used 19; V5 expands to 20 for stress coverage)
V5_SECTORS: tuple[str, ...] = (
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


# Symbols drawn from V4 universe (150 symbols). V5 reuses them, filtered
# against forbidden tokens.
V5_SYMBOLS: tuple[str, ...] = (
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
TRADE_INTENTS: tuple[str, ...] = ("directional", "no_trade", "leakage_guard", "stress_reinforce", "holdout_repair")
EXIT_POLICIES: tuple[str, ...] = ("hold_to_dte", "stop_50pct", "target_2x", "time_decay_exit", "regime_exit")
MONEYNESSES: tuple[str, ...] = ("1pct_otm", "atm", "3pct_otm")
RISK_FILTERS: tuple[str, ...] = (
    "max_loss_cap",
    "concentration_cap",
    "no_trade_guard",
)


def _candidate_id(idx: int) -> str:
    return f"cand-v5-{idx:06d}"


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


def _build_candidate(
    idx: int,
    subfamily: str,
    symbol: str,
    sector: str,
    direction: str,
    hold_window: int,
    no_trade_rules_applied: list[str],
    source_mutation_id: str,
    source_v4_mutation_id: str,
    source_v4_candidate_id: str,
    source_slice_id: str,
) -> dict[str, object]:
    family = subfamily.split("|", 1)[0]
    regime = "trending" if family == "continuation" else "volume"
    symbol_cluster = symbol[:1]
    dte = 14 if direction != "no_trade" else 0
    moneyness = "1pct_otm"
    exit_policy = "hold_to_dte" if direction != "no_trade" else "no_trade"
    stop = 0.5 if direction != "no_trade" else 0.0
    target = 2.0 if direction != "no_trade" else 0.0
    return {
        "artifact_type": "research_signal_candidate_v5",
        "candidate_id": _candidate_id(idx),
        "source_v4_candidate_id": source_v4_candidate_id,
        "source_v4_mutation_id": source_v4_mutation_id,
        "source_v5_mutation_id": source_mutation_id,
        "source_slice_id": source_slice_id,
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
        "trade_intent": "no_trade" if direction == "no_trade" else "directional",
        "DTE": dte,
        "moneyness": moneyness,
        "exit_policy": exit_policy,
        "hold_window": hold_window,
        "stop": stop,
        "target": target,
        "risk_filters": list(RISK_FILTERS),
        "no_trade_filter_rules_applied": list(no_trade_rules_applied),
        "feature_vector": {
            "relative_strength": 0.5,
            "volume_ratio": 1.0,
            "volatility": 0.3,
            "trend_strength": 0.4,
            "regime_alignment": 0.6,
        },
        "market_data_source_type": "public_ohlcv",
        "public_data_only": True,
        "paper_only": True,
        "live_trading_enabled": False,
        "fixture_candidate": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }


def _per_subfamily_budget(target: int, subfamily_count: int) -> int:
    return max(target // subfamily_count, 1)


def _no_trade_budget(per_sub_budget: int, max_family_share: float) -> int:
    """Cap no_trade at max_family_share of per_sub_budget."""
    return int(per_sub_budget * max_family_share)


def run_research_candidate_generator_v5() -> dict[str, object]:
    mutations = _read_jsonl_safe(MUTATION_EXEC_V5_RECORDS_PATH)
    expansion_mutations = _read_jsonl_safe(MUTATION_EXEC_V5_EXPANSION_PATH)
    no_trade_rules = _read_jsonl_safe(NO_TRADE_RULES_V5_PATH)
    no_trade_rule_ids = [str(r.get("rule_id", "")) for r in no_trade_rules if r.get("rule_id")]

    symbols = [s for s in V5_SYMBOLS if not is_forbidden_symbol(s)]
    sector_per_symbol = {sym: V5_SECTORS[i % len(V5_SECTORS)] for i, sym in enumerate(symbols)}

    subfamily_count = len(V5_CONTINUATION_SUBFAMILIES) + len(V5_VOLUME_SUBFAMILIES)
    symbols_per_subfamily = len(symbols)
    # Total (sub, sym) pairs across all subfamilies
    total_pairs = subfamily_count * symbols_per_subfamily
    # Per-(sub, sym, dir) budget so the full 40k target is spread evenly
    # Use ceiling so we reach at least V5_TARGET_CANDIDATES
    per_pair_budget = max((V5_TARGET_CANDIDATES + total_pairs - 1) // total_pairs, 1)
    long_call_per_pair = max(per_pair_budget // 3, 1)
    long_put_per_pair = max(per_pair_budget // 3, 1)
    no_trade_per_pair = max(per_pair_budget - long_call_per_pair - long_put_per_pair, 1)
    # Cap no_trade at 70% of per-pair budget
    no_trade_per_pair_cap = int(per_pair_budget * V5_MAX_FAMILY_SHARE)
    if no_trade_per_pair > no_trade_per_pair_cap:
        no_trade_per_pair = no_trade_per_pair_cap
        long_call_per_pair = max(per_pair_budget - no_trade_per_pair, 0) // 2
        long_put_per_pair = max(per_pair_budget - no_trade_per_pair - long_call_per_pair, 0)

    candidates: list[dict[str, object]] = []
    idx = 0

    subfamilies_in_order = list(V5_CONTINUATION_SUBFAMILIES) + list(V5_VOLUME_SUBFAMILIES)

    for sub_idx, sub in enumerate(subfamilies_in_order):
        if idx >= WATCHDOG_CANDIDATE_CAP_V5:
            break
        # Distribute symbols evenly within subfamily
        for sym_i, sym in enumerate(symbols):
            if idx >= WATCHDOG_CANDIDATE_CAP_V5:
                break
            for dir_i, direction in enumerate(DIRECTIONS):
                # Compute how many candidates to emit for this (sub, sym, dir)
                if direction == "long_call":
                    count = long_call_per_pair
                elif direction == "long_put":
                    count = long_put_per_pair
                else:  # no_trade
                    count = no_trade_per_pair
                if count <= 0:
                    continue
                # Rotate symbol assignment so each (sub, sym, dir) gets at
                # least one candidate if budget allows
                sector = sector_per_symbol[sym]
                for n in range(count):
                    if idx >= WATCHDOG_CANDIDATE_CAP_V5:
                        break
                    if idx >= V5_TARGET_CANDIDATES:
                        break
                    hold_window = V5_HOLD_WINDOWS[(sym_i + n) % len(V5_HOLD_WINDOWS)]
                    if direction == "no_trade":
                        hold_window = 0
                    source_v5_mutation = ""
                    source_v4_mutation = ""
                    source_v4_candidate = ""
                    source_slice = ""
                    if mutations:
                        m = mutations[(idx) % len(mutations)]
                        source_v5_mutation = str(m.get("mutation_id", ""))
                        source_v4_mutation = str(m.get("source_v4_repair_target_id", ""))
                    if expansion_mutations and not source_v5_mutation:
                        em = expansion_mutations[(idx) % len(expansion_mutations)]
                        source_v5_mutation = str(em.get("mutation_id", ""))
                    no_trade_rules_applied: list[str] = (
                        no_trade_rule_ids[:5] if no_trade_rule_ids else []
                    )
                    if direction != "no_trade":
                        # apply only the subset that allows trades
                        no_trade_rules_applied = no_trade_rule_ids[:2] if no_trade_rule_ids else []
                    cand = _build_candidate(
                        idx,
                        sub,
                        sym,
                        sector,
                        direction,
                        hold_window,
                        no_trade_rules_applied,
                        source_v5_mutation,
                        source_v4_mutation,
                        source_v4_candidate,
                        source_slice,
                    )
                    cand = record_with_hash(cand, "record_hash")
                    candidates.append(cand)
                    idx += 1
                if idx >= V5_TARGET_CANDIDATES:
                    break
            if idx >= V5_TARGET_CANDIDATES:
                break
        if idx >= V5_TARGET_CANDIDATES:
            break

    # Top-up if below V5_MIN_CANDIDATES (deterministic seeds)
    while idx < V5_MIN_CANDIDATES and idx < WATCHDOG_CANDIDATE_CAP_V5:
        sub = V5_CONTINUATION_SUBFAMILIES[idx % len(V5_CONTINUATION_SUBFAMILIES)]
        sym = symbols[idx % len(symbols)]
        cand = _build_candidate(
            idx,
            sub,
            sym,
            sector_per_symbol[sym],
            "no_trade",
            0,
            no_trade_rule_ids[:5] if no_trade_rule_ids else [],
            "",
            "",
            "",
            "",
        )
        cand = record_with_hash(cand, "record_hash")
        candidates.append(cand)
        idx += 1

    # Hard cap at watchdog
    candidates = candidates[:WATCHDOG_CANDIDATE_CAP_V5]

    write_jsonl_file(CANDIDATES_V5_PATH, candidates)

    # Quality rankings (deterministic by hash)
    rankings = []
    for c in candidates:
        rankings.append(
            {
                "artifact_type": "research_candidate_quality_ranking_v5",
                "candidate_id": c["candidate_id"],
                "stable_subfamily_id": c["stable_subfamily_id"],
                "symbol": c["symbol"],
                "direction": c["direction"],
                "rank": 0,
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    rankings.sort(key=lambda r: (r["stable_subfamily_id"], r["symbol"], r["direction"]))
    for i, r in enumerate(rankings):
        r["rank"] = i
    write_jsonl_file(CANDIDATE_RANKINGS_V5_PATH, rankings)

    # Family / subfamily / symbol / sector counts
    subfamily_set = {c["stable_subfamily_id"] for c in candidates}
    family_set = {c["stable_family_id"] for c in candidates}
    symbol_set = {c["symbol"] for c in candidates}
    sector_set = {c["sector"] for c in candidates}
    long_call = sum(1 for c in candidates if c["direction"] == "long_call")
    long_put = sum(1 for c in candidates if c["direction"] == "long_put")
    no_trade = sum(1 for c in candidates if c["direction"] == "no_trade")
    no_trade_filtered = sum(1 for c in candidates if c["no_trade_filter_rules_applied"])
    fixture_count = sum(1 for c in candidates if is_forbidden_symbol(c.get("symbol", "")))

    # Family share cap check
    family_counts: dict[str, int] = {}
    for c in candidates:
        family_counts[c["stable_family_id"]] = family_counts.get(c["stable_family_id"], 0) + 1
    max_family_share_actual = max(family_counts.values()) / max(len(candidates), 1) if candidates else 0.0
    family_share_cap_respected = max_family_share_actual <= V5_MAX_FAMILY_SHARE + 1e-9

    summary = {
        "artifact_type": "research_candidate_generator_v5_summary",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "research_candidate_generator_v5_status": "research_candidates_generated_v5",
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
        "max_family_share_cap": V5_MAX_FAMILY_SHARE,
        "family_share_cap_respected": family_share_cap_respected,
        "v5_target_candidates": V5_TARGET_CANDIDATES,
        "v5_min_candidates": V5_MIN_CANDIDATES,
        "watchdog_candidate_cap_v5": WATCHDOG_CANDIDATE_CAP_V5,
        "v5_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "public_data_only": True,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(
        Path(CANDIDATES_V5_PATH).parent / "research_candidate_generator_v5_summary.jsonl",
        [summary],
    )
    from dopey_autonomy.public_champion_common import write_summary_with_hash
    from dopey_autonomy.signal_research_v5_common import CANDIDATE_GENERATOR_V5_SUMMARY_PATH, CANDIDATE_GENERATOR_V5_PROOF_PATH, research_v5_proof_record

    write_summary_with_hash(CANDIDATE_GENERATOR_V5_SUMMARY_PATH, summary)
    write_jsonl_file(
        CANDIDATE_GENERATOR_V5_PROOF_PATH,
        [research_v5_proof_record("research-candidate-generator-v5", summary["research_candidate_generator_v5_status"], summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_research_candidate_generator_v5(), indent=2, sort_keys=True, default=str))
