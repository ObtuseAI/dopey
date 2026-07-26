"""Autonomous threshold adaptation that can only tighten protected rules."""

from __future__ import annotations

from .schema import GateComparator, GatePolicy, ThresholdRule


def _is_stricter(rule: ThresholdRule, proposed: float | bool | str) -> bool:
    current = rule["threshold"]
    protected = rule["protected_boundary"]
    if rule["comparator"] == GateComparator.EQUAL:
        return proposed == current == protected
    if isinstance(current, (bool, str)) or isinstance(protected, (bool, str)) or isinstance(proposed, (bool, str)):
        return False
    if rule["comparator"] == GateComparator.GREATER_THAN_OR_EQUAL:
        return float(proposed) >= float(current) and float(proposed) >= float(protected)
    if rule["comparator"] == GateComparator.LESS_THAN_OR_EQUAL:
        return float(proposed) <= float(current) and float(proposed) <= float(protected)
    return False


def propose_stricter_policy(
    policy: GatePolicy,
    rule_id: str,
    proposed_threshold: float | bool | str,
    evidence_ids: tuple[str, ...],
) -> dict[str, object]:
    matches = tuple(rule for rule in policy["rules"] if rule["rule_id"] == rule_id)
    if len(matches) != 1:
        raise ValueError(f"threshold adaptation rule must resolve exactly once: policy_id={policy['policy_id']}, rule_id={rule_id}")
    rule = matches[0]
    accepted = bool(evidence_ids) and _is_stricter(rule, proposed_threshold)
    updated_rules = tuple(
        {**candidate, "threshold": proposed_threshold, "source_ids": tuple(sorted(set((*candidate["source_ids"], *evidence_ids))))}
        if candidate["rule_id"] == rule_id and accepted
        else candidate
        for candidate in policy["rules"]
    )
    return {
        "artifact_type": "autonomous_threshold_adaptation_proposal",
        "policy_id": policy["policy_id"],
        "rule_id": rule_id,
        "current_threshold": rule["threshold"],
        "proposed_threshold": proposed_threshold,
        "protected_boundary": rule["protected_boundary"],
        "adaptation_status": "accepted_stricter" if accepted else "rejected_not_stricter_or_missing_evidence",
        "updated_policy": {**policy, "rules": updated_rules},
        "lowering_protected_threshold_allowed": False,
        "positive_promotion_allowed": False,
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
