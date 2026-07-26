"""Structural audit for the autonomous threshold fabric."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash

from .schema import GatePolicy


def audit_threshold_fabric(policies: Sequence[GatePolicy], issued_at: datetime) -> dict[str, Any]:
    if issued_at.tzinfo is None:
        raise ValueError("threshold fabric audit issued_at must be timezone-aware")
    policy_ids = tuple(policy["policy_id"] for policy in policies)
    duplicate_policy_ids = sorted({policy_id for policy_id in policy_ids if policy_ids.count(policy_id) > 1})
    violations: list[str] = []
    if duplicate_policy_ids:
        violations.append(f"duplicate_policy_ids:{duplicate_policy_ids}")
    rule_count = 0
    source_ids: set[str] = set()
    for policy in policies:
        rule_ids = tuple(rule["rule_id"] for rule in policy["rules"])
        duplicates = sorted({rule_id for rule_id in rule_ids if rule_ids.count(rule_id) > 1})
        if duplicates:
            violations.append(f"duplicate_rule_ids:{policy['policy_id']}:{duplicates}")
        if policy["paper_only"] is not True or policy["live_blocked"] is not True:
            violations.append(f"unsealed_policy:{policy['policy_id']}")
        if policy["positive_promotion_allowed"] or policy["execution_effect"] != "none":
            violations.append(f"forbidden_authority:{policy['policy_id']}")
        for rule in policy["rules"]:
            rule_count += 1
            source_ids.update(rule["source_ids"])
    body: dict[str, Any] = {
        "artifact_type": "autonomous_threshold_fabric_audit",
        "audit_version": "dopey-autonomous-threshold-fabric-audit-v1",
        "audit_status": "complete" if not violations else "failed_closed",
        "issued_at": issued_at.isoformat(),
        "policy_count": len(policies),
        "rule_count": rule_count,
        "policy_ids": tuple(sorted(policy_ids)),
        "source_ids": tuple(sorted(source_ids)),
        "violations": tuple(violations),
        "tighten_only_adaptation": True,
        "autonomous_negative_and_routing_authority": True,
        "autonomous_positive_promotion_authority": False,
        "operator_promotion_required": True,
        "order_authority": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "audit_hash": canonical_hash(body)}


def write_threshold_audit(path: Path, audit: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(audit), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
