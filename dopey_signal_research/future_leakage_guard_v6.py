"""Future leakage guard for V6.

Validates that no V6 repair rule uses:
- future path data
- realized P&L labels at candidate time
- holdout-outcome information
- post-exit P&L
- pruning that invalidates gate coverage unless labeled experimental
"""
from __future__ import annotations

import re
from typing import Iterable

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash
from dopey_autonomy.signal_research_v6_common import MIN_BREAKTHROUGH_PF, utc_now_iso


__all__ = ["audit_v6_no_leakage", "run_v6_leakage_guard_audit"]


FORBIDDEN_LEAKAGE_TOKENS = (
    "future_ohlcv",
    "realized_pnl",
    "actual_outcome",
    "holdout_outcome",
    "post_exit_pnl",
    "future_path",
    "tomorrow_close",
)


def _contains_leakage(rule: dict[str, object]) -> tuple[bool, str]:
    """Check a rule dict for forbidden leakage tokens and unsafe flags."""
    fields_to_check = (
        str(rule.get("description", "")),
        str(rule.get("intent", "")),
        str(rule.get("applies_to", "")),
        str(rule.get("rule_id", "")),
        str(rule.get("allowed_features", "")),
    )
    blob = " ".join(fields_to_check).lower()
    for token in FORBIDDEN_LEAKAGE_TOKENS:
        if re.search(r"\b" + re.escape(token) + r"\b", blob):
            return True, f"forbidden_token:{token}"
    if bool(rule.get("uses_future_information")):
        return True, "uses_future_information_true"
    if bool(rule.get("uses_realized_outcome_label")):
        return True, "uses_realized_outcome_label_true"
    if bool(rule.get("uses_holdout_outcome")):
        return True, "uses_holdout_outcome_true"
    coverage_invalidated = bool(rule.get("invalidates_gate_coverage"))
    labeled_experimental = bool(rule.get("experimental"))
    if coverage_invalidated and not labeled_experimental:
        return True, "invalidates_coverage_without_experimental_label"
    return False, "leakage_free"


def audit_v6_no_leakage(rules: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Run the future leakage audit on a set of V6 rules."""
    out: list[dict[str, object]] = []
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        is_leak, reason = _contains_leakage(rule)
        rec = {
            "artifact_type": "future_leakage_guard_record_v6",
            "rule_id": str(rule.get("rule_id", f"rule-{idx:04d}")),
            "rule_type": str(rule.get("rule_type", "")),
            "is_leakage_free": not is_leak,
            "leakage_reason": "" if not is_leak else reason,
            "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
            "thresholds_lowered": False,
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        out.append(record_with_hash(rec, "record_hash"))
    return out


def run_v6_leakage_guard_audit(rules: list[dict[str, object]]) -> dict[str, object]:
    records = audit_v6_no_leakage(rules)
    leak_count = sum(1 for r in records if not r["is_leakage_free"])
    return {
        "rule_count": len(records),
        "leakage_count": leak_count,
        "future_leakage_detected": leak_count > 0,
        "coverage_preservation_status": "preserved" if leak_count == 0 else "at_risk",
        "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
    }
