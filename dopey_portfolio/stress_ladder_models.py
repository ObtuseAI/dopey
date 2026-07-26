"""Deterministic portfolio stress ladder models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash


ALLOWED_STRESS_LEVELS = {"normal", "elevated", "defensive", "severe", "crisis", "lockdown"}
ALLOWED_THROTTLE_TYPES = {
    "reduce_allocation",
    "block_new_entries",
    "block_zero_dte",
    "swing_only",
    "delay_rotation",
    "paper_shadow_only",
    "watchlist_only",
    "no_trade_only",
    "block_family",
    "block_regime",
    "block_high_gamma",
    "block_high_theta",
    "block_iv_crush",
    "block_event_macro",
    "lockdown_allocation",
}


@dataclass(frozen=True)
class PortfolioStressLadder:
    ladder_id: str
    ladder_version: str
    stress_levels: list[dict[str, Any]]
    transition_rules: list[dict[str, Any]]
    crisis_modes: list[dict[str, Any]]
    throttle_profiles: list[dict[str, Any]]
    paper_only: bool
    live_blocked: bool
    ladder_hash: str

    def __post_init__(self) -> None:
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("stress ladder must be paper_only and live_blocked")
        if self.ladder_hash and self.ladder_hash != stress_ladder_hash(self):
            raise ValueError("stress ladder hash mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PortfolioStressLadder":
        return cls(
            ladder_id=str(record["ladder_id"]),
            ladder_version=str(record["ladder_version"]),
            stress_levels=list(record["stress_levels"]),
            transition_rules=list(record["transition_rules"]),
            crisis_modes=list(record["crisis_modes"]),
            throttle_profiles=list(record["throttle_profiles"]),
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            ladder_hash=str(record.get("ladder_hash", "")),
        )


@dataclass(frozen=True)
class PortfolioStressLevel:
    stress_level_id: str
    level_name: str
    level_rank: int
    trigger_conditions: list[str]
    allowed_actions: list[str]
    blocked_actions: list[str]
    allocation_multiplier: float
    zero_dte_multiplier: float
    swing_multiplier: float
    delayed_rotation_multiplier: float
    paper_shadow_multiplier: float
    required_throttles: list[str]
    paper_only: bool
    live_blocked: bool
    level_hash: str

    def __post_init__(self) -> None:
        if self.level_name not in ALLOWED_STRESS_LEVELS:
            raise ValueError(f"unsupported stress level: {self.level_name}")
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("stress level must be paper_only and live_blocked")
        if self.level_hash and self.level_hash != stress_level_hash(self):
            raise ValueError("stress level hash mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PortfolioStressLevel":
        return cls(
            stress_level_id=str(record["stress_level_id"]),
            level_name=str(record["level_name"]),
            level_rank=int(record["level_rank"]),
            trigger_conditions=[str(value) for value in record["trigger_conditions"]],
            allowed_actions=[str(value) for value in record["allowed_actions"]],
            blocked_actions=[str(value) for value in record["blocked_actions"]],
            allocation_multiplier=float(record["allocation_multiplier"]),
            zero_dte_multiplier=float(record["zero_dte_multiplier"]),
            swing_multiplier=float(record["swing_multiplier"]),
            delayed_rotation_multiplier=float(record["delayed_rotation_multiplier"]),
            paper_shadow_multiplier=float(record["paper_shadow_multiplier"]),
            required_throttles=[str(value) for value in record["required_throttles"]],
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            level_hash=str(record.get("level_hash", "")),
        )


@dataclass(frozen=True)
class CrisisModeThrottle:
    throttle_id: str
    stress_level: str
    throttle_type: str
    trigger_reason_codes: list[str]
    affected_strategy_types: list[str]
    affected_underlying_families: list[str]
    affected_regime_families: list[str]
    new_entry_allowed: bool
    exit_allowed: bool
    same_day_close_allowed: bool
    zero_dte_allowed: bool
    swing_allowed: bool
    delayed_rotation_allowed: bool
    paper_shadow_allowed: bool
    allocation_multiplier: float
    paper_attention_cap: float
    paper_premium_risk_cap: float
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    throttle_hash: str

    def __post_init__(self) -> None:
        if self.stress_level not in ALLOWED_STRESS_LEVELS:
            raise ValueError(f"unsupported stress level: {self.stress_level}")
        if self.throttle_type not in ALLOWED_THROTTLE_TYPES:
            raise ValueError(f"unsupported throttle type: {self.throttle_type}")
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("crisis throttle must be paper_only and live_blocked")
        if self.same_day_close_allowed is True:
            raise ValueError("crisis throttle cannot allow same-day close")
        if self.throttle_hash and self.throttle_hash != crisis_throttle_hash(self):
            raise ValueError("crisis throttle hash mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "CrisisModeThrottle":
        return cls(
            throttle_id=str(record["throttle_id"]),
            stress_level=str(record["stress_level"]),
            throttle_type=str(record["throttle_type"]),
            trigger_reason_codes=[str(value) for value in record["trigger_reason_codes"]],
            affected_strategy_types=[str(value) for value in record["affected_strategy_types"]],
            affected_underlying_families=[str(value) for value in record["affected_underlying_families"]],
            affected_regime_families=[str(value) for value in record["affected_regime_families"]],
            new_entry_allowed=bool(record["new_entry_allowed"]),
            exit_allowed=bool(record["exit_allowed"]),
            same_day_close_allowed=bool(record["same_day_close_allowed"]),
            zero_dte_allowed=bool(record["zero_dte_allowed"]),
            swing_allowed=bool(record["swing_allowed"]),
            delayed_rotation_allowed=bool(record["delayed_rotation_allowed"]),
            paper_shadow_allowed=bool(record["paper_shadow_allowed"]),
            allocation_multiplier=float(record["allocation_multiplier"]),
            paper_attention_cap=float(record["paper_attention_cap"]),
            paper_premium_risk_cap=float(record["paper_premium_risk_cap"]),
            reason_codes=[str(value) for value in record["reason_codes"]],
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            throttle_hash=str(record.get("throttle_hash", "")),
        )


@dataclass(frozen=True)
class StressTransitionDecision:
    transition_id: str
    from_stress_level: str
    to_stress_level: str
    triggering_snapshot_id: str
    triggering_stressors: list[str]
    transition_allowed: bool
    transition_reason_codes: list[str]
    allocator_feedback: list[str]
    threshold_feedback: list[str]
    paper_only: bool
    live_blocked: bool
    transition_hash: str

    def __post_init__(self) -> None:
        if self.from_stress_level not in ALLOWED_STRESS_LEVELS or self.to_stress_level not in ALLOWED_STRESS_LEVELS:
            raise ValueError("transition uses unsupported stress level")
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("stress transition must be paper_only and live_blocked")
        if self.transition_hash and self.transition_hash != stress_transition_hash(self):
            raise ValueError("stress transition hash mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "StressTransitionDecision":
        return cls(
            transition_id=str(record["transition_id"]),
            from_stress_level=str(record["from_stress_level"]),
            to_stress_level=str(record["to_stress_level"]),
            triggering_snapshot_id=str(record["triggering_snapshot_id"]),
            triggering_stressors=[str(value) for value in record["triggering_stressors"]],
            transition_allowed=bool(record["transition_allowed"]),
            transition_reason_codes=[str(value) for value in record["transition_reason_codes"]],
            allocator_feedback=[str(value) for value in record["allocator_feedback"]],
            threshold_feedback=[str(value) for value in record["threshold_feedback"]],
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            transition_hash=str(record.get("transition_hash", "")),
        )


def stress_ladder_hash(record: PortfolioStressLadder) -> str:
    return _hash_without(record.to_dict(), "ladder_hash")


def stress_level_hash(record: PortfolioStressLevel) -> str:
    return _hash_without(record.to_dict(), "level_hash")


def crisis_throttle_hash(record: CrisisModeThrottle) -> str:
    return _hash_without(record.to_dict(), "throttle_hash")


def stress_transition_hash(record: StressTransitionDecision) -> str:
    return _hash_without(record.to_dict(), "transition_hash")


def _hash_without(record: dict[str, Any], field_name: str) -> str:
    return reproducibility_hash({key: value for key, value in record.items() if key != field_name})
