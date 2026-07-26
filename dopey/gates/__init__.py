"""Autonomous, fail-closed threshold gates for governed paper research."""

from .adaptation import propose_stricter_policy
from .audit import audit_threshold_fabric
from .evaluator import evaluate_gate
from .policy import AUTONOMOUS_GATE_POLICIES, policy_by_id
from .sequential import confidence_sequence, conformal_abstention_threshold, online_alpha_budget

__all__ = [
    "AUTONOMOUS_GATE_POLICIES",
    "audit_threshold_fabric",
    "confidence_sequence",
    "conformal_abstention_threshold",
    "evaluate_gate",
    "online_alpha_budget",
    "policy_by_id",
    "propose_stricter_policy",
]
