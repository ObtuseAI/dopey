"""Map computed directional setup signals into paper-only backtest intents."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .backtest_models import (
    BACKTEST_ENGINE_VERSION,
    BacktestQualityFlag,
    BacktestSignalInput,
    BacktestTradeIntent,
)


DISALLOWED_TRUTHY_FIELDS: frozenset[str] = frozenset({
    "spread_created",
    "short_vol_created",
    "naked_selling_created",
    "same_day_churn_allowed",
    "real_sizing_used",
    "broker_required",
    "broker_connection",
    "order_id",
    "account_balance",
    "buying_power",
    "real_capital",
    "scheduler_enabled",
    "live_order",
    "live_trading_enabled",
})


def load_directional_setup_signals(path: Path | str) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            rows.append(json.loads(stripped))
    return rows


def map_signal_records_to_trade_intents(signal_records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    signal_inputs: list[dict[str, Any]] = []
    trade_intents: list[dict[str, Any]] = []
    quality_flags: list[dict[str, Any]] = []
    for signal_record in signal_records:
        violations = policy_violation_reason_codes(signal_record)
        if violations:
            quality_flags.append(_policy_quality_flag(signal_record, violations).to_dict())
            continue
        signal_input = _signal_input(signal_record)
        signal_inputs.append(signal_input)
        trade_intents.append(_trade_intent(signal_record).to_dict())
    return {
        "signal_inputs": signal_inputs,
        "trade_intents": trade_intents,
        "quality_flags": quality_flags,
    }


def policy_violation_reason_codes(signal_record: dict[str, Any]) -> list[str]:
    reason_codes: list[str] = []
    candidate_strategy = str(signal_record.get("candidate_strategy", ""))
    option_structure = str(signal_record.get("option_structure", ""))
    if candidate_strategy not in {"long_call", "long_put", "no_trade"}:
        reason_codes.append("unsupported_candidate_strategy")
    if option_structure not in {"long_call", "long_put", "none"}:
        reason_codes.append("unsupported_option_structure")
    if candidate_strategy == "long_call" and option_structure != "long_call":
        reason_codes.append("long_call_requires_long_call_structure")
    if candidate_strategy == "long_put" and option_structure != "long_put":
        reason_codes.append("long_put_requires_long_put_structure")
    if candidate_strategy == "no_trade" and option_structure != "none":
        reason_codes.append("no_trade_requires_none_structure")
    for field_name in sorted(DISALLOWED_TRUTHY_FIELDS):
        if bool(signal_record.get(field_name, False)):
            reason_codes.append(f"disallowed_{field_name}")
    if bool(signal_record.get("paper_only", True)) is not True:
        reason_codes.append("paper_only_required")
    if bool(signal_record.get("live_blocked", True)) is not True:
        reason_codes.append("live_blocked_required")
    if bool(signal_record.get("quote_priced", False)):
        reason_codes.append("quote_priced_signal_input_forbidden")
    return sorted(set(reason_codes))


def _signal_input(signal_record: dict[str, Any]) -> dict[str, Any]:
    candidate_strategy = str(signal_record.get("candidate_strategy", "no_trade"))
    option_structure = str(signal_record.get("option_structure", "none"))
    record = BacktestSignalInput(
        artifact_type="backtest_signal_input",
        signal_id=str(signal_record["signal_id"]),
        symbol=str(signal_record["symbol"]),
        signal_family=str(signal_record.get("source_signal_family", signal_record.get("signal_family", ""))),
        signal_date=str(signal_record["signal_date"]),
        direction=str(signal_record["direction"]),
        candidate_strategy=candidate_strategy,
        option_structure=option_structure,
        normalized_score=float(signal_record.get("normalized_score", 0.0)),
        confidence_proxy=float(signal_record.get("confidence_proxy", 0.0)),
        data_source_tier=str(signal_record.get("data_source_tier", "fixture_only")),
        real_history_used=bool(signal_record.get("real_history_used", False)),
        fixture_only=bool(signal_record.get("fixture_only", True)),
        not_real_signal_evidence=bool(signal_record.get("not_real_signal_evidence", True)),
        not_real_backtest_evidence=True,
        paper_only=True,
        live_blocked=True,
        reason_codes=[str(code) for code in signal_record.get("reason_codes", [])],
        input_hash="",
    )
    return record.to_dict()


def _trade_intent(signal_record: dict[str, Any]) -> BacktestTradeIntent:
    candidate_strategy = str(signal_record.get("candidate_strategy", "no_trade"))
    option_structure = str(signal_record.get("option_structure", "none"))
    pricing_source_tier = "model_priced" if candidate_strategy in {"long_call", "long_put"} else "fixture_only"
    model_priced = candidate_strategy in {"long_call", "long_put"}
    reason_codes = [str(code) for code in signal_record.get("reason_codes", [])]
    reason_codes.append("signal_to_trade_mapping_paper_only")
    if candidate_strategy == "long_call":
        reason_codes.append("bullish_setup_long_call_backtest_intent")
    elif candidate_strategy == "long_put":
        reason_codes.append("bearish_setup_long_put_backtest_intent")
    else:
        reason_codes.append("neutral_setup_no_trade_backtest_record")
    return BacktestTradeIntent(
        artifact_type="backtest_trade_intent",
        intent_id=f"{signal_record['signal_id']}-backtest-intent",
        symbol=str(signal_record["symbol"]),
        signal_id=str(signal_record["signal_id"]),
        signal_family=str(signal_record.get("source_signal_family", signal_record.get("signal_family", ""))),
        signal_date=str(signal_record["signal_date"]),
        direction=str(signal_record["direction"]),
        candidate_strategy=candidate_strategy,
        option_structure=option_structure,
        entry_date="",
        exit_date="",
        entry_premium=0.0,
        exit_premium=0.0,
        path_pnl=0.0,
        max_adverse_excursion=0.0,
        max_favorable_excursion=0.0,
        pricing_source_tier=pricing_source_tier,
        data_source_tier=str(signal_record.get("data_source_tier", "fixture_only")),
        real_history_used=bool(signal_record.get("real_history_used", False)),
        real_option_chain_used=False,
        fixture_only=bool(signal_record.get("fixture_only", True)),
        model_priced=model_priced,
        quote_priced=False,
        not_real_backtest_evidence=True,
        paper_only=True,
        live_blocked=True,
        reason_codes=reason_codes,
        record_hash="",
    )


def _policy_quality_flag(signal_record: dict[str, Any], reason_codes: list[str]) -> BacktestQualityFlag:
    return BacktestQualityFlag(
        artifact_type="backtest_quality_flag",
        flag_id=f"{signal_record.get('signal_id', 'missing-signal')}-policy-block",
        severity="error",
        symbol=str(signal_record.get("symbol", "")),
        signal_id=str(signal_record.get("signal_id", "")),
        reason_code="blocked_policy_violation",
        message="directional setup was rejected by long-premium-only offline backtest policy",
        pricing_source_tier="fixture_only",
        data_source_tier=str(signal_record.get("data_source_tier", "fixture_only")),
        real_history_used=False,
        real_option_chain_used=False,
        fixture_only=True,
        model_priced=False,
        quote_priced=False,
        not_real_backtest_evidence=True,
        paper_only=True,
        live_blocked=True,
        flag_hash="",
    )


def mapper_proof_record(signal_count: int, intent_count: int, blocked_count: int) -> dict[str, Any]:
    return {
        "artifact_type": "backtest_mapper_proof",
        "backtest_engine_version": BACKTEST_ENGINE_VERSION,
        "signal_count": signal_count,
        "intent_count": intent_count,
        "blocked_policy_violation_count": blocked_count,
        "long_premium_only": True,
        "no_spreads": True,
        "no_short_vol": True,
        "no_naked_selling": True,
        "no_same_day_churn": True,
        "paper_only": True,
        "live_blocked": True,
        "not_real_backtest_evidence": True,
    }
