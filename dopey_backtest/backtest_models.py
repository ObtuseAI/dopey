"""Typed records for DOPEY's honest offline backtester spine."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


BACKTEST_ENGINE_VERSION = "dopey-honest-backtester-v1"
ALLOWED_BACKTEST_STATUSES: frozenset[str] = frozenset({
    "missing_real_history_fixture_validation_only",
    "model_priced_backtest_validation_only",
    "valid_real_history_backtest_ready",
    "invalid_backtest_input",
    "blocked_policy_violation",
})
ALLOWED_BACKTEST_DIRECTIONS: frozenset[str] = frozenset({"bullish", "bearish", "neutral"})
ALLOWED_CANDIDATE_STRATEGIES: frozenset[str] = frozenset({"long_call", "long_put", "no_trade"})
ALLOWED_OPTION_STRUCTURES: frozenset[str] = frozenset({"long_call", "long_put", "none"})
ALLOWED_PRICING_SOURCE_TIERS: frozenset[str] = frozenset({"fixture_only", "model_priced", "quote_priced"})
ALLOWED_DATA_SOURCE_TIERS: frozenset[str] = frozenset({"fixture_only", "local_real_history", "missing_real_history"})
BACKTEST_HASH_FIELDS: frozenset[str] = frozenset({
    "record_hash",
    "input_hash",
    "flag_hash",
    "run_hash",
    "proof_hash",
    "reproducibility_hash",
})


@dataclass(frozen=True)
class BacktestSignalInput:
    artifact_type: str
    signal_id: str
    symbol: str
    signal_family: str
    signal_date: str
    direction: str
    candidate_strategy: str
    option_structure: str
    normalized_score: float
    confidence_proxy: float
    data_source_tier: str
    real_history_used: bool
    fixture_only: bool
    not_real_signal_evidence: bool
    not_real_backtest_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    input_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["symbol"] = normalize_symbol(str(record["symbol"]))
        record["direction"] = validate_direction(str(record["direction"]))
        record["candidate_strategy"] = validate_candidate_strategy(str(record["candidate_strategy"]))
        record["option_structure"] = validate_option_structure(str(record["option_structure"]))
        record["pricing_policy"] = "long_premium_only_no_spreads_no_short_vol_no_naked_selling"
        record["data_source_tier"] = validate_data_source_tier(str(record["data_source_tier"]))
        record["normalized_score"] = round(float(record["normalized_score"]), 6)
        record["confidence_proxy"] = round(float(record["confidence_proxy"]), 6)
        record["reason_codes"] = _sorted_codes(record["reason_codes"])
        record["not_real_backtest_evidence"] = True
        record["paper_only"] = True
        record["live_blocked"] = True
        record["input_hash"] = stable_backtest_hash(record)
        return record


@dataclass(frozen=True)
class BacktestTradeIntent:
    artifact_type: str
    intent_id: str
    symbol: str
    signal_id: str
    signal_family: str
    signal_date: str
    direction: str
    candidate_strategy: str
    option_structure: str
    entry_date: str
    exit_date: str
    entry_premium: float
    exit_premium: float
    path_pnl: float
    max_adverse_excursion: float
    max_favorable_excursion: float
    pricing_source_tier: str
    data_source_tier: str
    real_history_used: bool
    real_option_chain_used: bool
    fixture_only: bool
    model_priced: bool
    quote_priced: bool
    not_real_backtest_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _trade_record_dict(asdict(self), "backtest_trade_intent")


@dataclass(frozen=True)
class BacktestEntryDecision:
    artifact_type: str
    decision_id: str
    intent_id: str
    symbol: str
    signal_id: str
    signal_family: str
    signal_date: str
    direction: str
    candidate_strategy: str
    option_structure: str
    entry_date: str
    entry_premium: float
    decision: str
    pricing_source_tier: str
    data_source_tier: str
    real_history_used: bool
    real_option_chain_used: bool
    fixture_only: bool
    model_priced: bool
    quote_priced: bool
    not_real_backtest_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _base_decision_dict(asdict(self))
        record["entry_premium"] = _round_model_units(record["entry_premium"])
        record["decision"] = str(record["decision"])
        record["record_hash"] = stable_backtest_hash(record)
        return record


@dataclass(frozen=True)
class BacktestExitDecision:
    artifact_type: str
    decision_id: str
    intent_id: str
    trade_id: str
    symbol: str
    signal_id: str
    signal_family: str
    signal_date: str
    direction: str
    candidate_strategy: str
    option_structure: str
    entry_date: str
    exit_date: str
    entry_premium: float
    exit_premium: float
    exit_reason: str
    holding_steps: int
    pricing_source_tier: str
    data_source_tier: str
    real_history_used: bool
    real_option_chain_used: bool
    fixture_only: bool
    model_priced: bool
    quote_priced: bool
    not_real_backtest_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _base_decision_dict(asdict(self))
        record["entry_premium"] = _round_model_units(record["entry_premium"])
        record["exit_premium"] = _round_model_units(record["exit_premium"])
        record["holding_steps"] = int(record["holding_steps"])
        if record["holding_steps"] <= 0 and record["candidate_strategy"] != "no_trade":
            raise ValueError("holding_steps must be positive for simulated trades")
        record["exit_reason"] = str(record["exit_reason"])
        record["record_hash"] = stable_backtest_hash(record)
        return record


@dataclass(frozen=True)
class BacktestPositionState:
    artifact_type: str
    state_id: str
    trade_id: str
    intent_id: str
    symbol: str
    signal_id: str
    candidate_strategy: str
    option_structure: str
    state_date: str
    step_index: int
    premium_mark: float
    unrealized_pnl: float
    drawdown_from_trade_peak: float
    pricing_source_tier: str
    data_source_tier: str
    real_history_used: bool
    real_option_chain_used: bool
    fixture_only: bool
    model_priced: bool
    quote_priced: bool
    not_real_backtest_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _position_or_mark_dict(asdict(self))
        record["state_date"] = str(record["state_date"])
        record["step_index"] = int(record["step_index"])
        record["premium_mark"] = _round_model_units(record["premium_mark"])
        record["unrealized_pnl"] = _round_model_units(record["unrealized_pnl"])
        record["drawdown_from_trade_peak"] = _round_model_units(record["drawdown_from_trade_peak"])
        record["record_hash"] = stable_backtest_hash(record)
        return record


@dataclass(frozen=True)
class BacktestMarkRecord:
    artifact_type: str
    mark_id: str
    trade_id: str
    intent_id: str
    symbol: str
    signal_id: str
    candidate_strategy: str
    option_structure: str
    mark_date: str
    step_index: int
    premium_mark: float
    entry_premium: float
    mark_pnl: float
    pricing_source_tier: str
    data_source_tier: str
    real_history_used: bool
    real_option_chain_used: bool
    fixture_only: bool
    model_priced: bool
    quote_priced: bool
    not_real_backtest_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _position_or_mark_dict(asdict(self))
        record["mark_date"] = str(record["mark_date"])
        record["step_index"] = int(record["step_index"])
        record["premium_mark"] = _round_model_units(record["premium_mark"])
        record["entry_premium"] = _round_model_units(record["entry_premium"])
        record["mark_pnl"] = _round_model_units(record["mark_pnl"])
        record["record_hash"] = stable_backtest_hash(record)
        return record


@dataclass(frozen=True)
class BacktestTradeRecord:
    artifact_type: str
    trade_id: str
    symbol: str
    signal_id: str
    signal_family: str
    signal_date: str
    direction: str
    candidate_strategy: str
    option_structure: str
    entry_date: str
    exit_date: str
    entry_premium: float
    exit_premium: float
    path_pnl: float
    max_adverse_excursion: float
    max_favorable_excursion: float
    trade_return_model_units: float
    holding_steps: int
    exit_reason: str
    win_loss_marker: str
    pricing_source_tier: str
    data_source_tier: str
    real_history_used: bool
    real_option_chain_used: bool
    fixture_only: bool
    model_priced: bool
    quote_priced: bool
    not_real_backtest_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _trade_record_dict(asdict(self), "backtest_trade_record")
        record["trade_return_model_units"] = _round_model_units(record["trade_return_model_units"])
        record["holding_steps"] = int(record["holding_steps"])
        record["exit_reason"] = str(record["exit_reason"])
        record["win_loss_marker"] = str(record["win_loss_marker"])
        record["not_profitability_claim"] = True
        record["not_live_ready"] = True
        record["record_hash"] = stable_backtest_hash(record)
        return record


@dataclass(frozen=True)
class BacktestQualityFlag:
    artifact_type: str
    flag_id: str
    severity: str
    symbol: str
    signal_id: str
    reason_code: str
    message: str
    pricing_source_tier: str
    data_source_tier: str
    real_history_used: bool
    real_option_chain_used: bool
    fixture_only: bool
    model_priced: bool
    quote_priced: bool
    not_real_backtest_evidence: bool
    paper_only: bool
    live_blocked: bool
    flag_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["symbol"] = normalize_symbol_or_empty(str(record["symbol"]))
        record["pricing_source_tier"] = validate_pricing_source_tier(str(record["pricing_source_tier"]))
        record["data_source_tier"] = validate_data_source_tier(str(record["data_source_tier"]))
        record["real_history_used"] = bool(record["real_history_used"])
        record["real_option_chain_used"] = bool(record["real_option_chain_used"])
        record["fixture_only"] = bool(record["fixture_only"])
        record["model_priced"] = bool(record["model_priced"])
        record["quote_priced"] = bool(record["quote_priced"])
        record["not_real_backtest_evidence"] = True
        record["paper_only"] = True
        record["live_blocked"] = True
        record["flag_hash"] = stable_backtest_hash(record)
        return record


@dataclass(frozen=True)
class BacktestRunResult:
    artifact_type: str
    backtest_engine_version: str
    backtest_status: str
    history_dataset_status: str
    real_history_used: bool
    pricing_source_tier_distribution: dict[str, int]
    data_source_tier_distribution: dict[str, int]
    trade_intent_count: int
    trade_record_count: int
    long_call_trade_count: int
    long_put_trade_count: int
    no_trade_count: int
    blocked_policy_violation_count: int
    model_priced_trade_count: int
    quote_priced_trade_count: int
    fixture_only_trade_count: int
    total_path_pnl_model_units: float
    average_path_pnl_model_units: float
    max_drawdown_model_units: float
    win_count: int
    loss_count: int
    quality_flags: list[str]
    not_real_backtest_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    paper_only: bool
    live_blocked: bool
    next_recommended_target: str
    artifact_paths: dict[str, str]
    run_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["backtest_status"] = validate_backtest_status(str(record["backtest_status"]))
        record["pricing_source_tier_distribution"] = dict(sorted(record["pricing_source_tier_distribution"].items()))
        record["data_source_tier_distribution"] = dict(sorted(record["data_source_tier_distribution"].items()))
        record["total_path_pnl_model_units"] = _round_model_units(record["total_path_pnl_model_units"])
        record["average_path_pnl_model_units"] = _round_model_units(record["average_path_pnl_model_units"])
        record["max_drawdown_model_units"] = _round_model_units(record["max_drawdown_model_units"])
        record["quality_flags"] = sorted(str(code) for code in record["quality_flags"])
        record["not_real_backtest_evidence"] = True
        record["not_profitability_claim"] = True
        record["not_live_ready"] = True
        record["paper_only"] = True
        record["live_blocked"] = True
        record["run_hash"] = stable_backtest_hash(record)
        return record


@dataclass(frozen=True)
class BacktestProofRecord:
    artifact_type: str
    proof_id: str
    backtest_engine_version: str
    backtest_status: str
    history_dataset_status: str
    real_history_used: bool
    trade_intent_count: int
    trade_record_count: int
    not_real_backtest_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    no_broker: bool
    no_credentials: bool
    no_scheduler: bool
    no_real_sizing: bool
    no_orders: bool
    paper_only: bool
    live_blocked: bool
    next_recommended_target: str
    proof_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["backtest_status"] = validate_backtest_status(str(record["backtest_status"]))
        record["not_real_backtest_evidence"] = True
        record["not_profitability_claim"] = True
        record["not_live_ready"] = True
        record["no_broker"] = True
        record["no_credentials"] = True
        record["no_scheduler"] = True
        record["no_real_sizing"] = True
        record["no_orders"] = True
        record["paper_only"] = True
        record["live_blocked"] = True
        record["proof_hash"] = stable_backtest_hash(record)
        return record


def stable_backtest_hash(payload: dict[str, Any]) -> str:
    normalized = _strip_hash_fields(payload)
    encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty")
    return normalized


def normalize_symbol_or_empty(symbol: str) -> str:
    normalized = symbol.strip().upper()
    return normalized


def validate_backtest_status(status: str) -> str:
    if status not in ALLOWED_BACKTEST_STATUSES:
        raise ValueError(f"unsupported backtest_status: {status}")
    return status


def validate_direction(direction: str) -> str:
    if direction not in ALLOWED_BACKTEST_DIRECTIONS:
        raise ValueError(f"unsupported backtest direction: {direction}")
    return direction


def validate_candidate_strategy(candidate_strategy: str) -> str:
    if candidate_strategy not in ALLOWED_CANDIDATE_STRATEGIES:
        raise ValueError(f"unsupported candidate_strategy: {candidate_strategy}")
    return candidate_strategy


def validate_option_structure(option_structure: str) -> str:
    if option_structure not in ALLOWED_OPTION_STRUCTURES:
        raise ValueError(f"unsupported option_structure: {option_structure}")
    return option_structure


def validate_pricing_source_tier(pricing_source_tier: str) -> str:
    if pricing_source_tier not in ALLOWED_PRICING_SOURCE_TIERS:
        raise ValueError(f"unsupported pricing_source_tier: {pricing_source_tier}")
    return pricing_source_tier


def validate_data_source_tier(data_source_tier: str) -> str:
    if data_source_tier not in ALLOWED_DATA_SOURCE_TIERS:
        raise ValueError(f"unsupported data_source_tier: {data_source_tier}")
    return data_source_tier


def _trade_record_dict(record: dict[str, Any], expected_type: str) -> dict[str, Any]:
    if str(record["artifact_type"]) != expected_type:
        raise ValueError(f"expected artifact_type {expected_type}, got {record['artifact_type']}")
    record["symbol"] = normalize_symbol(str(record["symbol"]))
    record["direction"] = validate_direction(str(record["direction"]))
    record["candidate_strategy"] = validate_candidate_strategy(str(record["candidate_strategy"]))
    record["option_structure"] = validate_option_structure(str(record["option_structure"]))
    record["entry_premium"] = _round_model_units(record["entry_premium"])
    record["exit_premium"] = _round_model_units(record["exit_premium"])
    record["path_pnl"] = _round_model_units(record["path_pnl"])
    record["max_adverse_excursion"] = _round_model_units(record["max_adverse_excursion"])
    record["max_favorable_excursion"] = _round_model_units(record["max_favorable_excursion"])
    record["pricing_source_tier"] = validate_pricing_source_tier(str(record["pricing_source_tier"]))
    record["data_source_tier"] = validate_data_source_tier(str(record["data_source_tier"]))
    _enforce_trade_safety(record)
    record["reason_codes"] = _sorted_codes(record["reason_codes"])
    record["record_hash"] = stable_backtest_hash(record)
    return record


def _base_decision_dict(record: dict[str, Any]) -> dict[str, Any]:
    record["symbol"] = normalize_symbol(str(record["symbol"]))
    record["direction"] = validate_direction(str(record["direction"]))
    record["candidate_strategy"] = validate_candidate_strategy(str(record["candidate_strategy"]))
    record["option_structure"] = validate_option_structure(str(record["option_structure"]))
    record["pricing_source_tier"] = validate_pricing_source_tier(str(record["pricing_source_tier"]))
    record["data_source_tier"] = validate_data_source_tier(str(record["data_source_tier"]))
    _enforce_trade_safety(record)
    record["reason_codes"] = _sorted_codes(record["reason_codes"])
    return record


def _position_or_mark_dict(record: dict[str, Any]) -> dict[str, Any]:
    record["symbol"] = normalize_symbol(str(record["symbol"]))
    record["candidate_strategy"] = validate_candidate_strategy(str(record["candidate_strategy"]))
    record["option_structure"] = validate_option_structure(str(record["option_structure"]))
    record["pricing_source_tier"] = validate_pricing_source_tier(str(record["pricing_source_tier"]))
    record["data_source_tier"] = validate_data_source_tier(str(record["data_source_tier"]))
    _enforce_trade_safety(record)
    record["reason_codes"] = _sorted_codes(record["reason_codes"])
    return record


def _enforce_trade_safety(record: dict[str, Any]) -> None:
    real_history_used = bool(record["real_history_used"])
    real_option_chain_used = bool(record["real_option_chain_used"])
    quote_priced = bool(record["quote_priced"])
    model_priced = bool(record["model_priced"])
    pricing_source_tier = str(record["pricing_source_tier"])
    if quote_priced and pricing_source_tier != "quote_priced":
        raise ValueError("quote_priced records must use pricing_source_tier=quote_priced")
    if pricing_source_tier == "quote_priced" and not quote_priced:
        raise ValueError("pricing_source_tier=quote_priced requires quote_priced=true")
    if model_priced and pricing_source_tier == "quote_priced":
        raise ValueError("model_priced and quote_priced cannot both describe the same backtest record")
    if real_history_used and bool(record["fixture_only"]):
        raise ValueError("fixture_only cannot be true when real_history_used=true")
    if real_option_chain_used and not quote_priced:
        raise ValueError("real_option_chain_used requires quote_priced=true")
    record["real_history_used"] = real_history_used
    record["real_option_chain_used"] = real_option_chain_used
    record["fixture_only"] = bool(record["fixture_only"])
    record["model_priced"] = model_priced
    record["quote_priced"] = quote_priced
    record["not_real_backtest_evidence"] = True
    record["paper_only"] = True
    record["live_blocked"] = True


def _round_model_units(value: Any) -> float:
    if isinstance(value, bool):
        raise TypeError("model unit values must be numeric")
    return round(float(value), 6)


def _sorted_codes(codes: Any) -> list[str]:
    if not isinstance(codes, list):
        raise TypeError("reason_codes must be a list")
    return sorted(str(code) for code in codes)


def _strip_hash_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_hash_fields(item)
            for key, item in value.items()
            if key not in BACKTEST_HASH_FIELDS
        }
    if isinstance(value, list):
        return [_strip_hash_fields(item) for item in value]
    return value

