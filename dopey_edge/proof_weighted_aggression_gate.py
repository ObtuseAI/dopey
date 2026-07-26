"""Dopey proof-weighted aggression gate (Dummy doctrine).

DOPEY-native. The core Dummy "aggressive adaptive edge" doctrine, realized as a deterministic
proof-weighted aggression gate. Research conviction and execution eligibility are deliberately
separate: broker state can block execution but cannot rewrite measured edge.

Penalize: overfit, low liquidity, bad slippage, weak proof, drawdown
acceleration, signal decay. Reward: OOS edge, walk-forward consistency, paper-fill quality,
regime alignment, capital efficiency, family proof. Deterministic — given identical inputs the
gate always returns the same score and the same promotion decision (testable with fixtures).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AggressionScore:
    score: float            # 0..1, higher = more aggressive
    penalties: list[str] = field(default_factory=list)
    rewards: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PromotionDecision:
    decision: str           # "promote" | "hold" | "demote"
    aggression: AggressionScore
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"decision": self.decision, "aggression": self.aggression.to_dict(), "reasons": self.reasons}


@dataclass(frozen=True)
class ExecutionEligibility:
    eligible: bool
    status: str
    reason_codes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AggressionEvaluation:
    edge_decision: PromotionDecision
    execution_eligibility: ExecutionEligibility

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_decision": self.edge_decision.to_dict(),
            "execution_eligibility": self.execution_eligibility.to_dict(),
        }


class ProofWeightedAggressionGate:
    """Deterministic proof-weighted aggression gate. Recommend-only; never places live trades."""

    def __init__(self, *,
                 overfit_penalty: float = 0.25,
                 low_liquidity_penalty: float = 0.20,
                 slippage_penalty: float = 0.15,
                 weak_proof_penalty: float = 0.30,
                 drawdown_penalty: float = 0.20,
                 signal_decay_penalty: float = 0.15,
                 oos_reward: float = 0.25,
                 walk_forward_reward: float = 0.20,
                 paper_fill_reward: float = 0.15,
                 regime_reward: float = 0.15,
                 capital_efficiency_reward: float = 0.10,
                 family_proof_reward: float = 0.10,
                 promote_threshold: float = 0.55,
                 demote_threshold: float = 0.30):
        self.overfit_penalty = overfit_penalty
        self.low_liquidity_penalty = low_liquidity_penalty
        self.slippage_penalty = slippage_penalty
        self.weak_proof_penalty = weak_proof_penalty
        self.drawdown_penalty = drawdown_penalty
        self.signal_decay_penalty = signal_decay_penalty
        self.oos_reward = oos_reward
        self.walk_forward_reward = walk_forward_reward
        self.paper_fill_reward = paper_fill_reward
        self.regime_reward = regime_reward
        self.capital_efficiency_reward = capital_efficiency_reward
        self.family_proof_reward = family_proof_reward
        self.promote_threshold = promote_threshold
        self.demote_threshold = demote_threshold

    def score(self, genome: dict, proof: dict, liquidity: float, regime: str,
              broker_capability: dict) -> AggressionScore:
        """Compatibility wrapper; broker state cannot change measured edge."""
        _ = broker_capability
        return self.score_edge_conviction(genome, proof, liquidity, regime)

    def score_edge_conviction(
        self,
        genome: dict[str, Any],
        proof: dict[str, Any],
        liquidity: float,
        regime: str,
    ) -> AggressionScore:
        penalties, rewards = [], []
        s = 0.5  # neutral baseline

        # ---- Penalties ----
        if proof.get("overfit_flag"):
            s -= self.overfit_penalty
            penalties.append("overfit_flag")
        if liquidity < 0.4:
            s -= self.low_liquidity_penalty
            penalties.append("low_liquidity")
        if proof.get("slippage_bps", 0) > 10:
            s -= self.slippage_penalty
            penalties.append("bad_slippage")
        if proof.get("proof_strength", 0) < 0.5:
            s -= self.weak_proof_penalty
            penalties.append("weak_proof")
        if proof.get("drawdown_slope", 0) > 0.05:
            s -= self.drawdown_penalty
            penalties.append("drawdown_acceleration")
        if proof.get("signal_decay", 0) > 0.4:
            s -= self.signal_decay_penalty
            penalties.append("signal_decay")

        # ---- Rewards ----
        oos = float(proof.get("oos_edge", 0.0))
        if oos > 0:
            s += self.oos_reward
            rewards.append("oos_edge")
        if proof.get("walk_forward_consistency", 0) > 0.6:
            s += self.walk_forward_reward
            rewards.append("walk_forward_consistency")
        if proof.get("paper_fill_quality", 0) > 0.7:
            s += self.paper_fill_reward
            rewards.append("paper_fill_quality")
        if proof.get("regime_alignment", False) or genome.get("preferred_regime") == regime:
            s += self.regime_reward
            rewards.append("regime_alignment")
        if proof.get("capital_efficiency", 0) > 0.6:
            s += self.capital_efficiency_reward
            rewards.append("capital_efficiency")
        if proof.get("family_proof", False):
            s += self.family_proof_reward
            rewards.append("family_proof")

        s = max(0.0, min(1.0, round(s, 6)))
        return AggressionScore(score=s, penalties=penalties, rewards=rewards)

    def decide(self, genome: dict, proof: dict, liquidity: float, regime: str,
               broker_capability: dict) -> PromotionDecision:
        """Compatibility wrapper returning a research-only edge decision."""
        _ = broker_capability
        return self.decide_edge(genome, proof, liquidity, regime)

    def decide_edge(
        self,
        genome: dict[str, Any],
        proof: dict[str, Any],
        liquidity: float,
        regime: str,
    ) -> PromotionDecision:
        agg = self.score_edge_conviction(genome, proof, liquidity, regime)
        if agg.score >= self.promote_threshold:
            decision = "promote"
        elif agg.score <= self.demote_threshold:
            decision = "demote"
        else:
            decision = "hold"
        reasons = list(agg.penalties) + list(agg.rewards)
        return PromotionDecision(decision=decision, aggression=agg, reasons=reasons)

    def execution_eligibility(self, broker_capability: dict[str, Any]) -> ExecutionEligibility:
        reason_codes: list[str] = []
        if not bool(broker_capability.get("options_exec_supported", False)):
            reason_codes.append("options_execution_unsupported")
        if not bool(broker_capability.get("live_trading_enabled", False)):
            reason_codes.append("live_trading_disabled")
        if not bool(broker_capability.get("human_approval_present", False)):
            reason_codes.append("human_approval_missing")
        eligible = not reason_codes
        return ExecutionEligibility(
            eligible=eligible,
            status="execution_eligible" if eligible else "execution_blocked",
            reason_codes=reason_codes,
        )

    def evaluate(
        self,
        genome: dict[str, Any],
        proof: dict[str, Any],
        liquidity: float,
        regime: str,
        broker_capability: dict[str, Any],
    ) -> AggressionEvaluation:
        return AggressionEvaluation(
            edge_decision=self.decide_edge(genome, proof, liquidity, regime),
            execution_eligibility=self.execution_eligibility(broker_capability),
        )
