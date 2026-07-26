"""Typed records for DOPEY's truth-gated fitness replacement layer."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


FITNESS_VERSION = "dopey-fitness-function-replacement-v1"
ALLOWED_FITNESS_STATUSES: frozenset[str] = frozenset({
    "fixture_model_diagnostic_only",
    "truth_gate_blocked",
    "real_data_fitness_ready",
    "manual_review_required",
    "terminal_block",
})
ALLOWED_FITNESS_DECISIONS: frozenset[str] = frozenset({
    "diagnostic_score_only",
    "hold_no_promotion",
    "eligible_for_real_data_fitness_after_truth_gate",
    "manual_review_required",
    "terminal_block",
})
FITNESS_HASH_FIELDS: frozenset[str] = frozenset({
    "input_hash",
    "component_hash",
    "scorecard_hash",
    "penalty_hash",
    "rank_hash",
    "gate_hash",
    "decision_hash",
    "flag_hash",
    "proof_hash",
    "run_hash",
    "finding_hash",
    "case_hash",
    "reproducibility_hash",
})


@dataclass(frozen=True)
class FitnessInput:
    artifact_type: str
    fitness_version: str
    truth_summary_path: str
    truth_decision_path: str
    metric_set_path: str
    bootstrap_ci_path: str
    baseline_comparisons_path: str
    backtest_trade_records_path: str
    backtest_summary_path: str
    truth_status: str
    truth_decision: str
    statistical_promotion_allowed: bool
    real_sample_size: int
    fixture_model_sample_size: int
    sample_count: int
    quote_priced_trade_count: int
    real_history_used: bool
    real_option_chain_used: bool
    not_real_statistical_evidence: bool
    not_real_backtest_evidence: bool
    not_real_fitness_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    paper_only: bool
    live_blocked: bool
    input_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["fitness_version"] = FITNESS_VERSION
        _force_safety(record)
        record["input_hash"] = stable_fitness_hash(record)
        return record


@dataclass(frozen=True)
class FitnessMetricComponent:
    artifact_type: str
    fitness_version: str
    component_id: str
    component_name: str
    raw_value: float
    normalized_value: float
    weight: float
    weighted_score: float
    diagnostic_only: bool
    source_metric: str
    reason_codes: list[str]
    not_real_fitness_evidence: bool
    paper_only: bool
    live_blocked: bool
    component_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _rounded(asdict(self))
        record["fitness_version"] = FITNESS_VERSION
        record["diagnostic_only"] = True
        _force_safety(record)
        record["reason_codes"] = _sorted_codes(record["reason_codes"])
        record["component_hash"] = stable_fitness_hash(record)
        return record


@dataclass(frozen=True)
class FitnessPenalty:
    artifact_type: str
    fitness_version: str
    penalty_id: str
    penalty_name: str
    applies: bool
    penalty_value: float
    reason_code: str
    message: str
    diagnostic_only: bool
    terminal_block: bool
    manual_review_required: bool
    not_real_fitness_evidence: bool
    paper_only: bool
    live_blocked: bool
    penalty_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _rounded(asdict(self))
        record["fitness_version"] = FITNESS_VERSION
        record["applies"] = bool(record["applies"])
        record["diagnostic_only"] = True
        _force_safety(record)
        record["penalty_hash"] = stable_fitness_hash(record)
        return record


@dataclass(frozen=True)
class FitnessScorecard:
    artifact_type: str
    fitness_version: str
    scorecard_id: str
    strategy_id: str
    diagnostic_score: float
    gross_component_score: float
    total_penalty: float
    component_count: int
    penalty_count: int
    promotion_allowed: bool
    strategy_promoted: bool
    diagnostic_only: bool
    reason_codes: list[str]
    not_real_fitness_evidence: bool
    not_real_statistical_evidence: bool
    not_real_backtest_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    paper_only: bool
    live_blocked: bool
    scorecard_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _rounded(asdict(self))
        record["fitness_version"] = FITNESS_VERSION
        record["promotion_allowed"] = False
        record["strategy_promoted"] = False
        record["diagnostic_only"] = True
        record["reason_codes"] = _sorted_codes(record["reason_codes"])
        _force_safety(record)
        record["scorecard_hash"] = stable_fitness_hash(record)
        return record


@dataclass(frozen=True)
class FitnessRankRecord:
    artifact_type: str
    fitness_version: str
    rank_id: str
    strategy_id: str
    diagnostic_rank: int
    diagnostic_score: float
    promotion_allowed: bool
    strategy_promoted: bool
    rank_basis: str
    reason_codes: list[str]
    not_real_fitness_evidence: bool
    paper_only: bool
    live_blocked: bool
    rank_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _rounded(asdict(self))
        record["fitness_version"] = FITNESS_VERSION
        record["promotion_allowed"] = False
        record["strategy_promoted"] = False
        record["reason_codes"] = _sorted_codes(record["reason_codes"])
        _force_safety(record)
        record["rank_hash"] = stable_fitness_hash(record)
        return record


@dataclass(frozen=True)
class FitnessPromotionGate:
    artifact_type: str
    fitness_version: str
    promotion_gate_status: str
    promotion_allowed: bool
    strategy_promoted: bool
    promotion_block_reason: str
    real_sample_size: int
    quote_priced_trade_count: int
    real_history_used: bool
    real_option_chain_used: bool
    blocked_reason_codes: list[str]
    terminal_block: bool
    manual_review_required: bool
    not_real_fitness_evidence: bool
    not_real_statistical_evidence: bool
    not_real_backtest_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    paper_only: bool
    live_blocked: bool
    gate_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["fitness_version"] = FITNESS_VERSION
        record["promotion_allowed"] = bool(record["promotion_allowed"])
        if record["not_real_fitness_evidence"] or record["not_real_statistical_evidence"] or record["not_real_backtest_evidence"]:
            record["promotion_allowed"] = False
        record["strategy_promoted"] = False
        record["blocked_reason_codes"] = _sorted_codes(record["blocked_reason_codes"])
        _force_safety(record)
        record["gate_hash"] = stable_fitness_hash(record)
        return record


@dataclass(frozen=True)
class FitnessDecision:
    artifact_type: str
    fitness_version: str
    fitness_status: str
    fitness_decision: str
    diagnostic_score: float
    promotion_allowed: bool
    strategy_promoted: bool
    significance_claim_allowed: bool
    real_alpha_claim_allowed: bool
    profitability_claim_allowed: bool
    live_readiness_claim_allowed: bool
    truth_status: str
    truth_decision: str
    reason_codes: list[str]
    not_real_fitness_evidence: bool
    not_real_statistical_evidence: bool
    not_real_backtest_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    paper_only: bool
    live_blocked: bool
    decision_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _rounded(asdict(self))
        record["fitness_version"] = FITNESS_VERSION
        record["fitness_status"] = validate_fitness_status(str(record["fitness_status"]))
        record["fitness_decision"] = validate_fitness_decision(str(record["fitness_decision"]))
        record["promotion_allowed"] = False
        record["strategy_promoted"] = False
        record["significance_claim_allowed"] = False
        record["real_alpha_claim_allowed"] = False
        record["profitability_claim_allowed"] = False
        record["live_readiness_claim_allowed"] = False
        record["reason_codes"] = _sorted_codes(record["reason_codes"])
        _force_safety(record)
        record["decision_hash"] = stable_fitness_hash(record)
        return record


@dataclass(frozen=True)
class FitnessQualityFlag:
    artifact_type: str
    fitness_version: str
    flag_id: str
    severity: str
    reason_code: str
    message: str
    not_real_fitness_evidence: bool
    paper_only: bool
    live_blocked: bool
    flag_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["fitness_version"] = FITNESS_VERSION
        _force_safety(record)
        record["flag_hash"] = stable_fitness_hash(record)
        return record


@dataclass(frozen=True)
class FitnessProofRecord:
    artifact_type: str
    fitness_version: str
    proof_id: str
    fitness_status: str
    fitness_decision: str
    promotion_allowed: bool
    strategy_promoted: bool
    not_real_fitness_evidence: bool
    not_real_statistical_evidence: bool
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
        record["fitness_version"] = FITNESS_VERSION
        record["fitness_status"] = validate_fitness_status(str(record["fitness_status"]))
        record["fitness_decision"] = validate_fitness_decision(str(record["fitness_decision"]))
        record["promotion_allowed"] = False
        record["strategy_promoted"] = False
        record["no_broker"] = True
        record["no_credentials"] = True
        record["no_scheduler"] = True
        record["no_real_sizing"] = True
        record["no_orders"] = True
        _force_safety(record)
        record["proof_hash"] = stable_fitness_hash(record)
        return record


def stable_fitness_hash(payload: dict[str, Any]) -> str:
    normalized = _strip_hash_fields(payload)
    encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_fitness_status(status: str) -> str:
    if status not in ALLOWED_FITNESS_STATUSES:
        raise ValueError(f"unsupported fitness_status: {status}")
    return status


def validate_fitness_decision(decision: str) -> str:
    if decision not in ALLOWED_FITNESS_DECISIONS:
        raise ValueError(f"unsupported fitness_decision: {decision}")
    return decision


def _force_safety(record: dict[str, Any]) -> None:
    record["not_real_fitness_evidence"] = True
    record["paper_only"] = True
    record["live_blocked"] = True


def _rounded(record: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, float):
            output[key] = round(value, 6)
        else:
            output[key] = value
    return output


def _sorted_codes(codes: Any) -> list[str]:
    if not isinstance(codes, list):
        raise TypeError("reason_codes must be a list")
    return sorted(str(code) for code in codes)


def _strip_hash_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_hash_fields(item)
            for key, item in value.items()
            if key not in FITNESS_HASH_FIELDS
        }
    if isinstance(value, list):
        return [_strip_hash_fields(item) for item in value]
    return value

