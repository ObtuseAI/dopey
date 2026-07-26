"""Future leakage guard for V7 trade-active repair policy.

Validates that no V7 repair rule uses:
- future path data
- realized P&L labels at candidate time
- holdout-outcome information
- post-exit P&L
- tomorrow's close or future OHLCV
- pruning that invalidates gate coverage unless labeled experimental
"""
from __future__ import annotations

import re
from typing import Iterable

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash
from dopey_autonomy.signal_research_v7_common import (
    FUTURE_LEAKAGE_GUARD_V7_PATH,
    MIN_BREAKTHROUGH_PF,
    utc_now_iso,
)
from dopey_autonomy.public_champion_common import write_jsonl_file


__all__ = ["audit_v7_no_leakage", "run_v7_leakage_guard_audit"]


FORBIDDEN_LEAKAGE_TOKENS = (
    "future_ohlcv",
    "future_path",
    "future_close",
    "future_open",
    "future_high",
    "future_low",
    "future_volume",
    "tomorrow_close",
    "tomorrow_open",
    "realized_pnl",
    "actual_outcome",
    "holdout_outcome",
    "post_exit_pnl",
    "realized_outcome",
    "exit_pnl",
    "future_return",
    "future_performance_rank",
    "future_outlier_flag",
    "future_sector_performance",
)


def _contains_leakage(rule: dict[str, object]) -> tuple[bool, str]:
    """Check a rule dict for forbidden leakage tokens and unsafe flags."""
    fields_to_check = (
        str(rule.get("description", "")),
        str(rule.get("intent", "")),
        str(rule.get("applies_to", "")),
        str(rule.get("rule_id", "")),
        str(rule.get("allowed_features", "")),
        str(rule.get("conversion_logic", "")),
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


def audit_v7_no_leakage(rules: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Run the future leakage audit on a set of V7 trade-active repair rules."""
    out: list[dict[str, object]] = []
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        is_leak, reason = _contains_leakage(rule)
        rec = {
            "artifact_type": "future_leakage_guard_record_v7",
            "rule_id": str(rule.get("rule_id", f"rule-{idx:04d}")),
            "rule_type": str(rule.get("rule_type", "")),
            "is_leakage_free": not is_leak,
            "leakage_reason": "" if not is_leak else reason,
            "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
            "thresholds_lowered": False,
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        out.append(record_with_hash(rec, "record_hash"))
    return out


def run_v7_leakage_guard_audit(rules: list[dict[str, object]]) -> dict[str, object]:
    records = audit_v7_no_leakage(rules)
    leak_count = sum(1 for r in records if not r["is_leakage_free"])
    return {
        "rule_count": len(records),
        "leakage_count": leak_count,
        "future_leakage_detected": leak_count > 0,
        "coverage_preservation_status": "preserved" if leak_count == 0 else "at_risk",
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
    }


if __name__ == "__main__":
    import json as _json

    # Lazy import avoids circular dependency with the policy module.
    from dopey_signal_research.trade_active_repair_policy_v7 import _REPAIR_RULES

    guard_summary = run_v7_leakage_guard_audit(_REPAIR_RULES)
    guard_records = audit_v7_no_leakage(_REPAIR_RULES)
    write_jsonl_file(FUTURE_LEAKAGE_GUARD_V7_PATH, guard_records)
    print(_json.dumps(guard_summary, indent=2, sort_keys=True, default=str))
