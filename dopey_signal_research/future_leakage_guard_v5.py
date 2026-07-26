"""Future leakage guard for V5.

Validates that no V5 filter, scorer, or candidate rule uses:
- future path data
- realized P&L labels at candidate time
- holdout-outcome information
- post-exit P&L

Each rule is checked and recorded as a leakage audit record. Any rule
that fails the check is recorded as a leakage failure.
"""
from __future__ import annotations

from typing import Iterable

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v5_common import (
    FUTURE_LEAKAGE_GUARD_V5_PATH,
    utc_now_iso,
)


__all__ = ["audit_v5_no_leakage"]


# Tokens that indicate future / realized-label leakage.
# Matched with word boundaries to avoid false positives on field names
# like `uses_realized_outcome_label` that legitimately contain these
# tokens as part of a feature flag.
FORBIDDEN_LEAKAGE_TOKENS = (
    "future_ohlcv",
    "realized_pnl",
    "actual_outcome",
    "holdout_outcome",
    "post_exit_pnl",
    "future_path",
    "tomorrow_close",
    "leakage",
)


def _contains_leakage(rule: dict[str, object]) -> tuple[bool, str]:
    """Check a rule dict for any forbidden token (case-insensitive, word-boundary).

    Only inspects free-text fields (description, intent, applies_to, rule_id).
    Boolean feature flags are checked semantically below.
    """
    import re

    fields_to_check = (
        str(rule.get("description", "")),
        str(rule.get("intent", "")),
        str(rule.get("applies_to", "")),
        str(rule.get("rule_id", "")),
    )
    blob = " ".join(fields_to_check).lower()
    for token in FORBIDDEN_LEAKAGE_TOKENS:
        if re.search(r"\b" + re.escape(token) + r"\b", blob):
            return True, f"forbidden_token:{token}"
    # Direct semantic checks on feature flags
    if bool(rule.get("uses_future_information")):
        return True, "uses_future_information_true"
    if bool(rule.get("uses_realized_outcome_label")):
        return True, "uses_realized_outcome_label_true"
    if bool(rule.get("uses_holdout_outcome")):
        return True, "uses_holdout_outcome_true"
    return False, "leakage_free"


def audit_v5_no_leakage(rules: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Run the future leakage audit on a set of V5 rules."""
    out: list[dict[str, object]] = []
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        is_leak, reason = _contains_leakage(rule)
        rec = {
            "artifact_type": "future_leakage_guard_record_v5",
            "rule_id": str(rule.get("rule_id", f"rule-{idx:04d}")),
            "rule_type": str(rule.get("rule_type", "")),
            "is_leakage_free": not is_leak,
            "leakage_reason": "" if not is_leak else reason,
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        out.append(record_with_hash(rec, "record_hash"))
    return out


def run_v5_leakage_guard_audit(rules: list[dict[str, object]]) -> dict[str, object]:
    records = audit_v5_no_leakage(rules)
    write_jsonl_file(FUTURE_LEAKAGE_GUARD_V5_PATH, records)
    leak_count = sum(1 for r in records if not r["is_leakage_free"])
    return {
        "rule_count": len(records),
        "leakage_count": leak_count,
        "future_leakage_detected": leak_count > 0,
        "coverage_preservation_status": "preserved" if leak_count == 0 else "at_risk",
        "v5_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
    }


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v5_leakage_guard_audit([]), indent=2, sort_keys=True, default=str))
