"""Pure fail-closed evaluation for autonomous threshold policies."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from dopey.protocols.identity import canonical_hash

from .schema import GateComparator, GateDecision, GatePolicy, GateRuleResult


def _compare(observed: object, comparator: GateComparator, threshold: float | bool | str) -> bool:
    if comparator == GateComparator.EQUAL:
        return observed == threshold
    if isinstance(observed, bool) or not isinstance(observed, (int, float)):
        return False
    value = float(observed)
    if not math.isfinite(value) or isinstance(threshold, (bool, str)):
        return False
    boundary = float(threshold)
    if comparator == GateComparator.GREATER_THAN_OR_EQUAL:
        return value >= boundary
    if comparator == GateComparator.LESS_THAN_OR_EQUAL:
        return value <= boundary
    raise ValueError(f"unsupported gate comparator: comparator={comparator}")


def evaluate_gate(
    policy: GatePolicy,
    subject_id: str,
    metrics: Mapping[str, object],
    causal_parent_ids: Sequence[str],
) -> GateDecision:
    normalized_subject = subject_id.strip()
    if not normalized_subject:
        raise ValueError("autonomous gate requires a non-empty subject_id")
    if policy["paper_only"] is not True or policy["live_blocked"] is not True:
        raise ValueError(f"autonomous gate rejects an unsealed policy: policy_id={policy['policy_id']}")
    if policy["execution_effect"] != "none" or policy["positive_promotion_allowed"]:
        raise ValueError(f"autonomous gate cannot carry execution or positive promotion authority: policy_id={policy['policy_id']}")
    results: list[GateRuleResult] = []
    missing: list[str] = []
    failed: list[str] = []
    for rule in policy["rules"]:
        available = rule["metric"] in metrics
        observed = metrics.get(rule["metric"])
        passed = available and _compare(observed, rule["comparator"], rule["threshold"])
        if not available:
            missing.append(rule["metric"])
        elif not passed:
            failed.append(rule["rule_id"])
        results.append(
            {
                "rule_id": rule["rule_id"],
                "metric": rule["metric"],
                "comparator": rule["comparator"].value,
                "threshold": rule["threshold"],
                "observed": observed,
                "observed_available": available,
                "passed": passed,
                "critical": rule["critical"],
                "source_ids": rule["source_ids"],
            }
        )
    passed = not missing and not failed
    decision = policy["pass_action"] if passed else policy["missing_action"] if missing else policy["fail_action"]
    body: dict[str, Any] = {
        "artifact_type": "autonomous_threshold_gate_decision",
        "gate_version": "dopey-autonomous-threshold-gate-v1",
        "policy_id": policy["policy_id"],
        "policy_version": policy["policy_version"],
        "subject_id": normalized_subject,
        "scope": policy["scope"],
        "authority": policy["authority"].value,
        "decision": decision.value,
        "passed": passed,
        "missing_metrics": tuple(sorted(set(missing))),
        "failed_rules": tuple(sorted(set(failed))),
        "rule_results": tuple(results),
        "causal_parent_ids": tuple(sorted(set(str(value) for value in causal_parent_ids if str(value).strip()))),
        "positive_promotion_allowed": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "decision_hash": canonical_hash(body)}  # type: ignore[return-value]
