"""Active-policy compliance helpers for strategy, mutation, and structures."""
from __future__ import annotations

from dataclasses import asdict, dataclass


ACTIVE_POLICY_COMPLIANCE_VERSION = "dopey-active-policy-compliance-v1"

ACTIVE_STRUCTURE_TYPES: frozenset[str] = frozenset({"long_call", "long_put", "single"})
ACTIVE_GENERATION_STRUCTURES: tuple[str, ...] = (
    "long_call",
    "long_put",
    "zero_dte_long_call_special_lifecycle",
    "zero_dte_long_put_special_lifecycle",
    "swing_call",
    "swing_put",
    "rotation_call",
    "rotation_put",
)
UNSUPPORTED_ACTIVE_STRUCTURES: frozenset[str] = frozenset({
    "vertical",
    "long_call_vertical",
    "long_put_vertical",
    "call_debit_spread",
    "put_debit_spread",
    "short_straddle",
    "short_strangle",
    "iron_condor",
    "credit_spread_pair_proxy",
    "iron_condor_proxy",
    "butterfly_proxy",
})


@dataclass(frozen=True)
class ActivePolicyComplianceDecision:
    subject_id: str
    compliant: bool
    status: str
    reasons: list[str]
    active_policy_compliance_version: str = ACTIVE_POLICY_COMPLIANCE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def active_strategy_generation_universe() -> list[dict]:
    return [
        {
            "template_id": structure,
            "structure_type": structure,
            "paper_only": True,
            "live_blocked": True,
            "active_policy_compliant": True,
        }
        for structure in ACTIVE_GENERATION_STRUCTURES
    ]


def classify_structure_for_active_policy(structure_type: str, leg_count: int) -> ActivePolicyComplianceDecision:
    reasons: list[str] = []
    if structure_type in UNSUPPORTED_ACTIVE_STRUCTURES:
        reasons.append("unsupported_multileg_structure_rejected")
    if structure_type not in ACTIVE_STRUCTURE_TYPES:
        reasons.append("not_active_trading_policy_compliant")
    if leg_count != 1:
        reasons.append("unsupported_multileg_structure_rejected")
    compliant = not reasons
    return ActivePolicyComplianceDecision(
        subject_id=structure_type,
        compliant=compliant,
        status="active_policy_compliant" if compliant else "research_legacy_unsupported",
        reasons=_dedupe(reasons),
    )


def classify_mutation_for_active_policy(mutation_record: dict) -> ActivePolicyComplianceDecision:
    genome = mutation_record.get("genome", mutation_record)
    parameters = genome.get("parameters", {}) if isinstance(genome, dict) else {}
    subject_id = str(genome.get("genome_id", mutation_record.get("mutation_id", "mutation")))
    reasons: list[str] = []
    structure = str(parameters.get("structure", parameters.get("spread_structure_proxy", "")))
    action = str(parameters.get("order_action", ""))
    lifecycle = str(parameters.get("lifecycle_state", ""))
    if "short" in structure or str(parameters.get("structure_risk", "")) == "undefined":
        reasons.append("unsupported_short_option_leg")
    if "same_day" in action or "same_day" in lifecycle or parameters.get("same_day_round_trip") is True:
        reasons.append("same_day_round_trip_rejected")
    if structure in UNSUPPORTED_ACTIVE_STRUCTURES or "vertical" in structure or "spread" in structure:
        reasons.append("unsupported_multileg_structure_rejected")
    if genome.get("live_allowed") is True:
        reasons.append("live_order_rejected")
    compliant = not reasons
    return ActivePolicyComplianceDecision(
        subject_id=subject_id,
        compliant=compliant,
        status="active_policy_compliant" if compliant else "rejected_by_active_policy",
        reasons=_dedupe(reasons),
    )


def tournament_candidate_active_policy_compliant(candidate: dict) -> bool:
    structure = str(candidate.get("structure_type", candidate.get("structure", "")))
    leg_count = int(candidate.get("leg_count", 1))
    return classify_structure_for_active_policy(structure, leg_count).compliant


def active_policy_mutation_pressure() -> dict:
    return {
        "reward": [
            "evidence_backed_long_call_long_put_rotation",
            "hold_discipline",
            "next_day_or_later_exit_discipline",
        ],
        "penalize": [
            "same_day_churn",
            "unsupported_structure_complexity",
            "expiry_risk_misuse",
            "liquidity_slippage_violation",
            "proof_gap",
        ],
    }


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
