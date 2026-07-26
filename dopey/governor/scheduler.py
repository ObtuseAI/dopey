"""Research continuation scheduling based on metacognitive controls."""

from __future__ import annotations


def schedule_from_control(control: str) -> dict[str, bool | str]:
    if control in {"ABSTAIN", "TERMINATE"}:
        return {"schedule_status": "stopped", "reason": control, "additional_stage_allowed": False}
    if control in {"EXPAND_EVIDENCE", "ADD_ADVERSARY", "REPLAY_HISTORY"}:
        return {"schedule_status": "bounded_followup_requested", "reason": control, "additional_stage_allowed": True}
    return {"schedule_status": "complete", "reason": control, "additional_stage_allowed": False}
