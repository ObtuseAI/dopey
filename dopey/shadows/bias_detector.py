"""Detect consensus collapse and missing adversarial balance."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def inspect_bias(hypotheses: Mapping[str, float], counterevidence_count: int) -> dict[str, Any]:
    if counterevidence_count < 0:
        raise ValueError(f"counterevidence count cannot be negative: count={counterevidence_count}")
    maximum = max((float(value) for value in hypotheses.values()), default=1.0)
    findings: list[str] = []
    if maximum >= 0.8:
        findings.append("consensus_collapse_or_single_hypothesis_dominance")
    if counterevidence_count == 0:
        findings.append("counterevidence_absent")
    return {
        "guard": "bias_detector",
        "status": "request_adversary" if findings else "pass",
        "findings": findings,
        "may_increase_readiness": False,
    }
