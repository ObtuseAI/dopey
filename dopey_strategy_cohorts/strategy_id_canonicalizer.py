"""Canonical strategy cohort ID assignment.

Cohort levels:
* variant_id            - exact setup + exit + DTE + moneyness + thresholds (the prior strategy_id).
* micro_cohort_id       - setup + exit style group + DTE bucket group + moneyness group.
* setup_cohort_id        - setup family + direction + exit style group.
* family_cohort_id      - setup family only.
* regime_cohort_id      - setup family + regime.
* symbol_cluster_cohort_id - setup family + sector/symbol cluster.
* canonical_champion_id - stable ID selected for champion gating.
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from typing import Mapping

from dopey_autonomy.public_champion_common import (
    PUBLIC_SOURCE_TYPES,
    record_with_hash,
    safe_float,
    sector_for_symbol,
    write_json_file,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_deepening_common import DEEPENING_ROOT, deepening_proof_record

from .strategy_cohort_models import (
    COHORT_LEVELS,
    dte_bucket_group,
    exit_style_group,
    moneyness_group,
)


REGISTRY_PATH = DEEPENING_ROOT / "strategy_cohort_registry.jsonl"
ASSIGNMENT_RECORDS_PATH = DEEPENING_ROOT / "strategy_cohort_assignment_records.jsonl"
SUMMARY_PATH = DEEPENING_ROOT / "strategy_cohort_summary.json"
PROOF_PATH = DEEPENING_ROOT / "strategy_cohort_proof.jsonl"

DIRECTION_BY_FAMILY = {
    "volatility_squeeze_breakout": "bullish",
    "volatility_squeeze_breakdown": "bearish",
    "trend_pullback_continuation": "bullish",
    "trend_exhaustion_reversal": "bearish",
    "gap_continuation": "bullish",
    "gap_fade": "bearish",
    "relative_strength_vs_spy": "bullish",
    "relative_weakness_vs_spy": "bearish",
    "sector_relative_strength": "bullish",
    "sector_relative_weakness": "bearish",
    "moving_average_reclaim": "bullish",
    "moving_average_rejection": "bearish",
    "atr_expansion": "bullish",
    "atr_compression_breakout": "bullish",
    "bollinger_expansion": "bullish",
    "bollinger_mean_reversion": "bearish",
    "rsi_reclaim": "bullish",
    "rsi_failure": "bearish",
    "macd_cross_continuation": "bullish",
    "macd_divergence_proxy": "bearish",
    "support_bounce": "bullish",
    "support_failure": "bearish",
    "resistance_breakout": "bullish",
    "resistance_rejection": "bearish",
    "high_volume_breakout": "bullish",
    "low_volume_fakeout": "bearish",
}


def assign_cohort_ids(record: Mapping[str, object]) -> dict[str, str]:
    """Compute the seven cohort IDs for a single signal/trade/score record."""
    setup_family = str(record.get("setup_family", ""))
    exit_policy = str(record.get("exit_policy", ""))
    dte_bucket = record.get("dte_bucket", record.get("dte_bucket", 0))
    moneyness = str(record.get("moneyness_bucket", "ATM"))
    direction = str(record.get("direction", DIRECTION_BY_FAMILY.get(setup_family, "neutral")))
    regime = str(record.get("regime", record.get("volatility_regime", ""))) or "unknown"
    sector = str(record.get("sector", sector_for_symbol(str(record.get("symbol", ""))))) or "other"
    variant_id = str(record.get("variant_id", record.get("strategy_id", "")))

    exit_group = exit_style_group(exit_policy)
    dte_group = dte_bucket_group(dte_bucket)
    money_group = moneyness_group(moneyness)

    micro_cohort_id = f"{setup_family}|{exit_group}|{dte_group}|{money_group}"
    setup_cohort_id = f"{setup_family}|{direction}|{exit_group}"
    family_cohort_id = setup_family or "unspecified_family"
    regime_cohort_id = f"{setup_family}|{regime}"
    symbol_cluster_cohort_id = f"{setup_family}|{sector}"

    canonical_seed = f"{family_cohort_id}::{setup_cohort_id}"
    canonical_champion_id = "champ-" + hashlib.sha256(canonical_seed.encode("utf-8")).hexdigest()[:12]

    return {
        "variant_id": variant_id,
        "micro_cohort_id": micro_cohort_id,
        "setup_cohort_id": setup_cohort_id,
        "family_cohort_id": family_cohort_id,
        "regime_cohort_id": regime_cohort_id,
        "symbol_cluster_cohort_id": symbol_cluster_cohort_id,
        "canonical_champion_id": canonical_champion_id,
    }


def attach_cohort_ids(record: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of record with all cohort ID fields attached."""
    output = dict(record)
    output.update(assign_cohort_ids(record))
    return output


def run_strategy_id_canonicalizer(records: list[dict[str, object]] | None = None) -> dict[str, object]:
    if records is None:
        records = load_default_records()
    assignments: list[dict[str, object]] = []
    cohort_children: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    fixture_count = 0
    public_only = True
    for record in records:
        cohort_ids = assign_cohort_ids(record)
        assignment = {
            "artifact_type": "strategy_cohort_assignment_record",
            "source_id": str(record.get("signal_id", record.get("trade_id", record.get("strategy_id", "")))),
            "strategy_id": str(record.get("strategy_id", record.get("variant_id", ""))),
            **cohort_ids,
            "market_data_source_type": str(record.get("market_data_source_type", "")),
            "live_trading_enabled": False,
        }
        assignments.append(record_with_hash(assignment, "record_hash"))
        for level in COHORT_LEVELS:
            cohort_children[level][cohort_ids[level]].add(assignment["source_id"])
        source_type = str(record.get("market_data_source_type", ""))
        if source_type not in PUBLIC_SOURCE_TYPES and source_type != "":
            public_only = False
        if source_type == "fixture_fallback":
            fixture_count += 1
            public_only = False

    registry = build_cohort_registry(cohort_children, records)
    counts = {level: len(cohort_children[level]) for level in COHORT_LEVELS}
    summary = {
        "artifact_type": "strategy_cohort_summary",
        "strategy_cohort_version": "dopey-strategy-cohort-canonicalizer-v1",
        "strategy_cohort_status": "strategy_cohort_canonicalization_complete" if records else "blocked_no_input_records",
        "variant_count": counts["variant_id"],
        "micro_cohort_count": counts["micro_cohort_id"],
        "setup_cohort_count": counts["setup_cohort_id"],
        "family_cohort_count": counts["family_cohort_id"],
        "regime_cohort_count": counts["regime_cohort_id"],
        "symbol_cluster_cohort_count": counts["symbol_cluster_cohort_id"],
        "canonical_cohort_count": counts["canonical_champion_id"],
        "assignment_count": len(assignments),
        "public_data_only": public_only,
        "fixture_trade_count": fixture_count,
        "live_trading_enabled": False,
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(REGISTRY_PATH, registry)
    write_jsonl_file(ASSIGNMENT_RECORDS_PATH, assignments)
    write_jsonl_file(PROOF_PATH, [deepening_proof_record("strategy-cohort-canonicalizer", str(summary["strategy_cohort_status"]), summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def load_default_records() -> list[dict[str, object]]:
    from dopey_autonomy.public_champion_common import read_jsonl_file, OPTIONS_ENGINE_ROOT

    trades_path = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v4_trades.jsonl"
    if trades_path.exists():
        return read_jsonl_file(trades_path)
    signals_path = OPTIONS_ENGINE_ROOT.parent / "signals" / "public_signal_mutation_candidates_v4.jsonl"
    return read_jsonl_file(signals_path)


def build_cohort_registry(
    cohort_children: dict[str, dict[str, set[str]]],
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    registry: list[dict[str, object]] = []
    record_by_id: dict[str, dict[str, object]] = {}
    for record in records:
        rid = str(record.get("signal_id", record.get("trade_id", record.get("strategy_id", ""))))
        if rid:
            record_by_id[rid] = dict(record)
    for level in COHORT_LEVELS:
        for cohort_id, child_ids in cohort_children[level].items():
            child_records = [record_by_id[cid] for cid in child_ids if cid in record_by_id]
            dispersion = child_variant_dispersion(child_records, level)
            entry = {
                "artifact_type": "strategy_cohort_registry_entry",
                "cohort_level": level,
                "cohort_id": cohort_id,
                "child_count": len(child_ids),
                "child_variant_dispersion": dispersion,
                "public_data_only": all(str(r.get("market_data_source_type", "")).startswith("public") for r in child_records) if child_records else True,
                "fixture_trade_count": sum(1 for r in child_records if str(r.get("market_data_source_type", "")) == "fixture_fallback"),
                "live_trading_enabled": False,
            }
            registry.append(record_with_hash(entry, "record_hash"))
    return registry


def child_variant_dispersion(records: list[dict[str, object]], level: str) -> dict[str, object]:
    if not records:
        return {"sample_count": 0, "unique_variants": 0}
    variants = {str(r.get("variant_id", r.get("strategy_id", ""))) for r in records}
    symbols = {str(r.get("symbol", "")) for r in records}
    pnl_values = [safe_float(r.get("paper_pnl")) for r in records if "paper_pnl" in r]
    return {
        "sample_count": len(records),
        "unique_variants": len(variants),
        "unique_symbols": len(symbols),
        "net_pnl": round(sum(pnl_values), 6) if pnl_values else 0.0,
        "expectancy": round(sum(pnl_values) / len(pnl_values), 6) if pnl_values else 0.0,
    }


def artifact_paths() -> dict[str, str]:
    return {
        "strategy_cohort_registry": str(REGISTRY_PATH),
        "strategy_cohort_assignment_records": str(ASSIGNMENT_RECORDS_PATH),
        "strategy_cohort_summary": str(SUMMARY_PATH),
        "strategy_cohort_proof": str(PROOF_PATH),
    }
