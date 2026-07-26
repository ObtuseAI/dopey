"""Build a credit-risk proxy from hash-pinned HYG and Treasury ETF history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from dopey.constitution.evidence_law import validate_evidence_record
from dopey.protocols.identity import canonical_hash
from dopey.technical.history_adapter import load_default_validated_symbol_history
from dopey_data.history_store import HISTORY_MANIFEST_PATH, load_history_manifest


def _return_over_window(closes: list[float], window: int) -> float:
    if len(closes) <= window:
        raise ValueError(
            "credit proxy history is too short for requested return window: "
            f"row_count={len(closes)}, window={window}"
        )
    return closes[-1] / closes[-1 - window] - 1.0


def _credit_record(
    evidence_type: str,
    evidence_status: str,
    observed_at: str,
    provenance: str,
    values: dict[str, Any],
    limitations: list[str],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "evidence_type": evidence_type,
        "evidence_status": evidence_status,
        "symbol": "HYG_IEF_SHY",
        "observed_at": observed_at,
        "source_uri": "local://dopey_data/history/history_dataset_manifest.json",
        "schema_version": "dopey-credit-proxy-evidence-v1",
        "provenance": provenance,
        "values": values,
        "limitations": limitations,
        "not_trade_decision": True,
        "not_readiness_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    content_hash = canonical_hash(body)
    record = {
        **body,
        "evidence_id": f"{evidence_type}:{content_hash[:24]}",
        "content_hash": content_hash,
    }
    validate_evidence_record(record)
    return record


def _credit_data_gap(
    observed_at: str,
    status: str,
    missing_symbols: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    return _credit_record(
        "credit_proxy_data_gap",
        status,
        observed_at,
        "governed_history_manifest_checked_without_complete_credit_proxy_inputs",
        {
            "state": "unknown",
            "probability": 0.0,
            "required_symbols": ["HYG", "IEF", "SHY"],
            "missing_symbols": missing_symbols,
        },
        limitations,
    )


def build_credit_proxy_evidence(event_time: str, market_time: str) -> dict[str, Any]:
    event = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
    market = datetime.fromisoformat(market_time.replace("Z", "+00:00"))
    if event.tzinfo is None or market.tzinfo is None or market > event:
        raise ValueError(
            "credit proxy requires aware event/market time with market not after event: "
            f"event_time={event_time}, market_time={market_time}"
        )
    required_symbols = ("HYG", "IEF", "SHY")
    manifest = load_history_manifest(HISTORY_MANIFEST_PATH)
    available_symbols = {
        symbol.upper()
        for file_reference in manifest.data_files
        for symbol in file_reference.symbols
    }
    missing_manifest_symbols = sorted(set(required_symbols) - available_symbols)
    if missing_manifest_symbols:
        return _credit_data_gap(
            market_time,
            "unavailable_missing_hash_pinned_history_symbols",
            missing_manifest_symbols,
            [
                "credit_proxy_requires_hash_pinned_hyg_ief_shy_history",
                "absence_is_not_credit_risk_evidence",
                "no_proxy_state_was_synthesized",
            ],
        )
    histories: dict[str, list[dict[str, Any]]] = {}
    proofs: dict[str, dict[str, Any]] = {}
    missing_point_in_time_symbols: list[str] = []
    for symbol in required_symbols:
        history, proof = load_default_validated_symbol_history(symbol)
        filtered = [row for row in history if str(row["date"]) <= market.date().isoformat()]
        if not filtered:
            missing_point_in_time_symbols.append(symbol)
            continue
        histories[symbol] = filtered
        proofs[symbol] = proof
    if missing_point_in_time_symbols:
        return _credit_data_gap(
            market_time,
            "unavailable_no_point_in_time_credit_proxy_history",
            missing_point_in_time_symbols,
            [
                "available_history_begins_after_research_market_time",
                "absence_is_not_credit_risk_evidence",
                "no_proxy_state_was_synthesized",
            ],
        )
    short_symbols = sorted(symbol for symbol, rows in histories.items() if len(rows) <= 20)
    if short_symbols:
        return _credit_data_gap(
            market_time,
            "unavailable_insufficient_credit_proxy_lookback",
            short_symbols,
            [
                "twenty_session_relative_return_window_is_incomplete",
                "no_short_window_substitute_was_used",
                "no_proxy_state_was_synthesized",
            ],
        )
    returns_20d = {
        symbol: _return_over_window([float(row["close"]) for row in rows], 20)
        for symbol, rows in histories.items()
    }
    excess_vs_ief = returns_20d["HYG"] - returns_20d["IEF"]
    excess_vs_shy = returns_20d["HYG"] - returns_20d["SHY"]
    composite = (excess_vs_ief + excess_vs_shy) / 2.0
    state = "risk_appetite_firm" if composite >= 0.015 else "credit_risk_aversion" if composite <= -0.015 else "mixed_or_stable"
    probability = min(0.78, 0.55 + abs(composite) * 5.0)
    return _credit_record(
        "validated_credit_proxy",
        "complete_hash_pinned_relative_return_proxy",
        market_time,
        "deterministic_point_in_time_relative_returns_from_hash_pinned_local_history",
        {
            "state": state,
            "probability": round(probability, 6),
            "returns_20d": {key: round(value, 6) for key, value in returns_20d.items()},
            "hyg_excess_vs_ief_20d": round(excess_vs_ief, 6),
            "hyg_excess_vs_shy_20d": round(excess_vs_shy, 6),
            "input_proofs": proofs,
        },
        [
            "etf_relative_return_proxy_not_option_adjusted_credit_spread",
            "duration_and_fund_flow_effects_are_not_separated",
            "not_a_causal_default_risk_model",
        ],
    )
