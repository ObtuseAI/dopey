"""Paper-only kill-switch decisions."""
from __future__ import annotations

from dopey_wealth_engine.common import stable_hash


def build_kill_switch_records(throttles: list[dict]) -> list[dict]:
    records: list[dict] = []
    for throttle in throttles:
        if throttle["action"] in {"kill_or_shadow", "throttle_strategy"}:
            record = {
                "artifact_type": "kill_switch_record",
                "target": throttle["target"],
                "trigger": throttle["throttle_type"],
                "kill_switch_action": "paper_shadow_only" if throttle["action"] == "kill_or_shadow" else "paper_allocation_cut",
                "live_order_cancel_attempted": False,
                "real_capital_affected": False,
                "paper_only": True,
                "live_blocked": True,
            }
            record["record_hash"] = stable_hash(record)
            records.append(record)
    return records

